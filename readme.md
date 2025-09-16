# Health Tweets (X API) – Prueba de descarga por hashtags

Este repositorio contiene un script simple para descargar posts de X (antes Twitter) usando la API v2, orientado a una prueba rápida sobre temas de salud.

## Brief del cliente
“Queremos hacer una prueba bajando tuits sobre una enfermedad. Averiguar cómo funciona la API. ¿Se busca por hashtags? ¿Se puede poner más de uno? Abajo van 2 ejemplos que queremos probar.”

- Ejemplo 1: Enfermedad de nicho – Fabry
- Ejemplo 2: GLP‑1 para obesidad

## Qué hace este repo
- Descarga posts recientes de X por conjuntos de hashtags (o términos) con la API v2.
- Permite filtros de idioma y rango de fechas.
- Guarda cada corrida en un archivo con timestamp: `data/tweets_YYYYMMDD_HHMMSS.csv` (o `.json`).
- Incluye URL canónica del post en X y URLs externas expandidas (t.co, etc.).

## Limitaciones importantes de la API de X
- Acceso por plan: el plan Free suele permitir SOLO 100 posts por mes (no 500) y puede no incluir historial más allá de ~7 días. Si el plan se agota, la API devuelve 0 resultados.
- Rate limit de ventana (~15 min): aunque tengas cupo mensual, si saturás la ventana, la API puede devolver 0 temporalmente. Puedes usar `--no-wait` para no “dormir” y guardar parciales.
- “--limit” es un máximo: puedes recibir menos resultados si no hay suficientes posts recientes que cumplan la query.

## Requisitos
- Windows + PowerShell
- Python 3.11 recomendado
- Credenciales de X API v2 (Bearer Token) con acceso a “Recent search”

## Instalación
```powershell
# (Opcional) Crear entorno virtual
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Configurar credenciales
```powershell
# Crear .env y pegar tu Bearer Token de X API
Set-Content -NoNewline -Path .env -Value "X_BEARER_TOKEN=PEGAR_AQUI"
```

## Uso rápido (desde la raíz del repo)
```powershell
# Fabry en español (hasta 100 posts máx; puede devolver menos)
py .\scripts\x_search.py --preset fabry --lang es --limit 100 --no-wait

# GLP‑1 (hasta 200 posts máx)
py .\scripts\x_search.py --preset glp1 --limit 200 --no-wait

# Manual: varios hashtags/terminos (se combinan con OR)
py .\scripts\x_search.py --hashtags "#Fabry" "#FabryDisease" --limit 100 --no-wait
```

Salida: siempre en `data/tweets_YYYYMMDD_HHMMSS.csv` (o usar `--format json`). No es necesario `--out`.

## Parámetros
- `--preset fabry|glp1`: usa listas predefinidas de hashtags/terminos.
- `--hashtags ...`: términos/hashtags personalizados (se combinan con OR). Puedes pasar más de uno.
- `--lang es|en`: filtra por idioma.
- `--since YYYY-MM-DD` y `--until YYYY-MM-DD`: rango temporal (UTC). El script ajusta automáticamente `end_time` cuando `until` es “hoy”.
- `--limit N`: tope máximo a traer (puede devolver menos).
- `--no-wait`: si hay rate limit, termina y guarda parciales (no espera ~15 min).
- `--format csv|json`: formato de salida (por defecto CSV).
- `--debug`: imprime detalles de la respuesta de la API (conteos por página, tokens, tips).

## Ejemplos (alineados al brief)
- Fabry (nicho):
```powershell
py .\scripts\x_search.py --preset fabry --lang es --limit 100 --no-wait
```
- GLP‑1 (masivo):
```powershell
py .\scripts\x_search.py --preset glp1 --limit 200 --no-wait
```

## Por qué puedo recibir menos que lo pedido en `--limit`
- Historial reciente insuficiente (el endpoint Recent Search cubre ~7 días según plan).
- Rate limit de ventana (~15 minutos) alcanzado; con `--no-wait` el script guarda parciales.
- Cuota mensual del plan agotada (por ejemplo, Free = 100 posts/mes).

## Solución de problemas
- 0 resultados pero hay cupo mensual: espera 15 minutos (rate limit de ventana) o reintenta con `--limit` menor.
- Resultados muy bajos: quita filtros estrictos (por ejemplo, prueba sin `--lang`) o amplía términos.
- Verifica que el Bearer Token corresponda al mismo Project/App/Environment donde ves la cuota.
- Activa el modo diagnóstico:
```powershell
py .\scripts\x_search.py --preset fabry --limit 10 --no-wait --debug
```

## Estructura del repo
```
./
  requirements.txt
  readme.md
  .env               # no versionado (agregar tu token)
  /scripts
    x_search.py
  /data              # se crea automáticamente con archivos timestamped
```

## Columnas del CSV
- `id, date, user_username, user_displayname, content, like_count, retweet_count, reply_count, quote_count, lang, url, external_urls`
- `url`: enlace canónico del post en X: `https://x.com/i/web/status/<id>`
- `external_urls`: URLs expandidas (por ejemplo, los `t.co` del contenido)
