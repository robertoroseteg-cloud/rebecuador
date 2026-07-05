# Artículos → Podcast automático

Convierte tus feeds RSS en un podcast privado: cada artículo nuevo se transforma
en un MP3 con voz neuronal en español y se publica en un feed que tu app de
podcasts (AntennaPod) descarga automáticamente.

## Instalación (una sola vez, ~10 minutos, todo desde el navegador)

1. **Crea un repositorio en GitHub** (público) y sube estos archivos.
   Puedes hacerlo sin instalar nada: en github.com → New repository →
   "uploading an existing file" y arrastras el contenido de esta carpeta.

2. **Edita `feeds.txt`** directamente en GitHub (icono de lápiz) y pon tus
   feeds RSS, uno por línea.

3. **Activa GitHub Pages**: Settings → Pages → Source: "Deploy from a branch"
   → Branch: `main`, carpeta `/docs` → Save.

4. **Da permisos al workflow**: Settings → Actions → General →
   Workflow permissions → "Read and write permissions" → Save.

5. **Primera ejecución**: pestaña Actions → "Generar episodios" →
   Run workflow. A partir de ahí corre solo todos los días.

6. **En tu Android**: instala AntennaPod (F-Droid o Play Store) →
   "+" → "Agregar podcast por dirección RSS" → pega:
   `https://TU_USUARIO.github.io/TU_REPO/feed.xml`
   Luego en ajustes del podcast activa la descarga automática de episodios.

## Personalización

Variables de entorno en `.github/workflows/generar.yml` (paso "Generar audios"):

- `VOZ_TTS`: voz a usar. Recomendadas: `es-MX-JorgeNeural` (hombre),
  `es-MX-DaliaNeural` (mujer). Lista completa: `edge-tts --list-voices`.
- `VELOCIDAD_TTS`: p. ej. `+15%`.
- `MAX_NUEVOS`: artículos por corrida (defecto 5).
- `MAX_EPISODIOS`: episodios que se conservan (defecto 40; los viejos se borran
  para no llenar el repositorio).

## Nota de privacidad

GitHub Pages en un repo público es accesible para cualquiera que tenga la URL
(no está indexado, pero no es privado). Si el contenido es sensible, usa solo
feeds de fuentes públicas, o considera un repo privado con otro hosting para
los audios.
