#!/usr/bin/env python3
"""
Pipeline: feeds RSS -> texto limpio -> MP3 (edge-tts) -> feed de podcast.

Corre automaticamente en GitHub Actions (ver .github/workflows/generar.yml).
Publica los audios y el feed.xml en /docs para servirlos con GitHub Pages.

Uso local:  python generar.py
"""

import asyncio
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import edge_tts
import feedparser
import trafilatura

# ----------------------------- Configuracion -----------------------------

RAIZ = Path(__file__).parent
ARCHIVO_FEEDS = RAIZ / "feeds.txt"
DIR_DOCS = RAIZ / "docs"
DIR_EPISODIOS = DIR_DOCS / "episodios"
DIR_ESTADO = RAIZ / "estado"
ARCHIVO_VISTOS = DIR_ESTADO / "vistos.json"
ARCHIVO_EPISODIOS = DIR_ESTADO / "episodios.json"

VOZ = os.environ.get("VOZ_TTS", "es-MX-DaliaNeural")  # alternativa: es-MX-DaliaNeural
VELOCIDAD = os.environ.get("VELOCIDAD_TTS", "+0%")     # ej. "+10%" para mas rapido
MAX_NUEVOS_POR_CORRIDA = int(os.environ.get("MAX_NUEVOS", "10"))
MAX_EPISODIOS_GUARDADOS = int(os.environ.get("MAX_EPISODIOS", "100"))
MAX_CARACTERES = 60_000  # corte de seguridad para articulos larguisimos

TITULO_PODCAST = os.environ.get("TITULO_PODCAST", "Mis articulos en audio")
DESCRIPCION_PODCAST = "Articulos de mis feeds RSS convertidos a audio automaticamente."


def url_base() -> str:
    """Construye la URL de GitHub Pages a partir del repo, o usa BASE_URL."""
    if os.environ.get("BASE_URL"):
        return os.environ["BASE_URL"].rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")  # "usuario/repo"
    if "/" in repo:
        usuario, nombre = repo.split("/", 1)
        return f"https://{usuario}.github.io/{nombre}"
    return "http://localhost:8000"  # pruebas locales


# ----------------------------- Utilidades -----------------------------

def cargar_json(ruta: Path, defecto):
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return defecto


def guardar_json(ruta: Path, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def id_entrada(entrada) -> str:
    base = entrada.get("id") or entrada.get("link") or entrada.get("title", "")
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def limpiar_texto(texto: str) -> str:
    texto = html.unescape(texto)
    texto = re.sub(r"https?://\S+", "", texto)          # URLs no se escuchan bien
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()[:MAX_CARACTERES]


def extraer_texto(entrada) -> str | None:
    """Intenta bajar el articulo completo; si falla, usa el contenido del feed."""
    enlace = entrada.get("link")
    if enlace:
        try:
            descargado = trafilatura.fetch_url(enlace)
            if descargado:
                texto = trafilatura.extract(
                    descargado, include_comments=False, include_tables=False
                )
                if texto and len(texto) > 300:
                    return limpiar_texto(texto)
        except Exception as e:
            print(f"    aviso: no pude extraer {enlace}: {e}")
    # Respaldo: contenido incluido en el propio feed
    contenido = ""
    if entrada.get("content"):
        contenido = entrada["content"][0].get("value", "")
    elif entrada.get("summary"):
        contenido = entrada["summary"]
    contenido = re.sub(r"<[^>]+>", " ", contenido)  # quitar HTML
    contenido = limpiar_texto(contenido)
    return contenido if len(contenido) > 200 else None


async def texto_a_mp3(texto: str, destino: Path):
    comunicador = edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD)
    await comunicador.save(str(destino))


# ----------------------------- Feed de podcast -----------------------------

def generar_feed(episodios: list[dict], base: str):
    items = []
    for ep in episodios:
        fecha = email.utils.formatdate(ep["timestamp"], usegmt=True)
        items.append(f"""
    <item>
      <title>{escape(ep['titulo'])}</title>
      <description>{escape(ep.get('fuente', ''))} — {escape(ep.get('enlace', ''))}</description>
      <link>{escape(ep.get('enlace', base))}</link>
      <guid isPermaLink="false">{ep['id']}</guid>
      <pubDate>{fecha}</pubDate>
      <enclosure url="{base}/episodios/{ep['archivo']}" length="{ep['bytes']}" type="audio/mpeg"/>
    </item>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(TITULO_PODCAST)}</title>
    <link>{base}</link>
    <description>{escape(DESCRIPCION_PODCAST)}</description>
    <language>es</language>
    <itunes:author>Pipeline automatico</itunes:author>
    {''.join(items)}
  </channel>
</rss>
"""
    (DIR_DOCS / "feed.xml").write_text(xml, encoding="utf-8")


def podar_episodios(episodios: list[dict]) -> list[dict]:
    """Conserva solo los N mas recientes y borra los MP3 viejos."""
    episodios.sort(key=lambda e: e["timestamp"], reverse=True)
    for viejo in episodios[MAX_EPISODIOS_GUARDADOS:]:
        ruta = DIR_EPISODIOS / viejo["archivo"]
        if ruta.exists():
            ruta.unlink()
            print(f"  borrado episodio viejo: {viejo['archivo']}")
    return episodios[:MAX_EPISODIOS_GUARDADOS]


# ----------------------------- Principal -----------------------------

def main():
    if not ARCHIVO_FEEDS.exists():
        sys.exit("No existe feeds.txt — agrega ahi tus feeds RSS, uno por linea.")

    feeds = [
        linea.strip()
        for linea in ARCHIVO_FEEDS.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.strip().startswith("#")
    ]
    vistos: dict = cargar_json(ARCHIVO_VISTOS, {})
    episodios: list = cargar_json(ARCHIVO_EPISODIOS, [])
    DIR_EPISODIOS.mkdir(parents=True, exist_ok=True)

    pendientes = []
    for url_feed in feeds:
        print(f"Leyendo feed: {url_feed}")
        parseado = feedparser.parse(url_feed)
        fuente = parseado.feed.get("title", url_feed)
        for entrada in parseado.entries[:10]:
            eid = id_entrada(entrada)
            if eid not in vistos:
                pendientes.append((eid, fuente, entrada))

    if not pendientes:
        print("Sin articulos nuevos.")
        return

    print(f"{len(pendientes)} articulos nuevos; procesando hasta {MAX_NUEVOS_POR_CORRIDA}.")
    nuevos = 0
    for eid, fuente, entrada in pendientes:
        if nuevos >= MAX_NUEVOS_POR_CORRIDA:
            # Los demas quedan pendientes para la siguiente corrida
            break
        titulo = entrada.get("title", "Sin titulo")
        print(f"  -> {titulo}")
        texto = extraer_texto(entrada)
        vistos[eid] = int(time.time())  # marcar visto aunque falle, para no reintentar en bucle
        if not texto:
            print("     omitido: no se pudo obtener texto suficiente.")
            continue

        narracion = f"{titulo}. De {fuente}.\n\n{texto}"
        archivo = f"{eid}.mp3"
        destino = DIR_EPISODIOS / archivo
        try:
            asyncio.run(texto_a_mp3(narracion, destino))
        except Exception as e:
            print(f"     error de TTS: {e}")
            continue

        episodios.append({
            "id": eid,
            "titulo": titulo,
            "fuente": fuente,
            "enlace": entrada.get("link", ""),
            "archivo": archivo,
            "bytes": destino.stat().st_size,
            "timestamp": int(time.time()),
        })
        nuevos += 1

    episodios = podar_episodios(episodios)
    generar_feed(episodios, url_base())
    guardar_json(ARCHIVO_VISTOS, vistos)
    guardar_json(ARCHIVO_EPISODIOS, episodios)
    print(f"Listo: {nuevos} episodios nuevos. Feed: {url_base()}/feed.xml")


if __name__ == "__main__":
    main()
