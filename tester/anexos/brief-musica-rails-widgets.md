# Brief de test — MÚSICA (V2-041) + RAILS (V2-042) + WIDGETS (acceso/uso/creación)

> Para el **test agent**: incorpora esto a los workflows de prueba (batería + cron). Cubre las features nuevas del
> 2026-07-15 para que **no quede nada sin probar ni verificar**. Escenarios ejecutables ya añadidos a
> `tester/scenarios.py`: **`musica`**, **`musica_difusa`**, **`musica_spotify_connect`**, **`widget_conducciones`**
> (+ el existente `youtube_voice`, que NO debe confundirse con música: es VÍDEO). El JUEZ evalúa por la TRAZA
> (`GET /events`, `.meshkore/logs/timeline-latest.jsonl`), distinguiendo **bug real (trace-confirmado)** de ruido de
> STT del tester y de rigidez del juez (ver `.meshkore/docs/ops/zaelar-testing.md`).

## Qué cambió (contexto para juzgar bien)

1. **Música por voz (V2-041)** — nueva tool `play_music`. Conector agnóstico `connectors/music` con dos proveedores:
   **Spotify** (Web API + OAuth PKCE, requiere Premium + dispositivo) y **YouTube-audio** (GRATIS, sin login,
   reproduce el AUDIO de un vídeo OCULTO dentro del widget **`musica`**). Regla: **"pon música" SIEMPRE suena algo**
   (si no hay Spotify, cae al fallback gratis). El widget `musica` es **distinto** del widget de vídeo `youtube`.
2. **RAILS (V2-042)** — patrón para comportamientos comunes CONDUCIDOS. Un rail lleva su estado en **`state.rails`**
   → el prompt del turno muestra **«Rails en curso»**. Un intento FALLIDO queda **AISLADO como `sin_resolver`**
   (con la pista + nº de intentos) y se **RETOMA** cuando el operador aporta un dato ("era de Sinatra"). Cada
   resultado durable se vuelca a memoria (`recent_by_source("music")` → gustos/historial). Eventos `rail` en /debug.
   El **FlashBrain sigue NO-razonador**: la cadena resolver→validar→actuar vive en código (`nucleo/flash/music_flow.py`).
3. **Widgets = rail FUNDACIONAL, TRES conducciones que NO se confunden**: (a) **operar datos** = `widget_data`→
   `apply_action` al instante (rápido, sin escalar); (b) **crear/modificar código** = escala a un worker; (c)
   **abrir/cerrar/borrar** en el canvas = tags `[[show]]`/`[[close]]` + `delete_widget`.

## Cómo probarlo (arco por escenario)

- **`musica`** — "pon música" → luego "ponme a Frank Sinatra" → "sube la música" → "siguiente" → "pausa".
  PASS: usa `play_music`; se ABRE `musica` (no `youtube`); suena algo aun sin Spotify; los controles actúan; en la
  traza hay evento `music` (con `provider`, `action`, `surface`) y un `rail` `music.playing`. FAIL: llama a
  `web_search`, abre el widget de vídeo `youtube`, o se queda mudo.
- **`musica_difusa`** — pide una canción por una frase de la letra SIN el nombre. Si pregunta, dale UN dato al turno
  siguiente. PASS: intenta resolver solo (no exige el nombre exacto), ANUNCIA qué pone; si falla, lo dice, deja el
  run `sin_resolver` (visible como «Rails en curso … SIN RESOLVER» en el prompt del turno siguiente) y al darle el
  dato lo RETOMA con la pista enriquecida. Traza: `rail` `music.search` searching→sin_resolver→(resuelto).
- **`musica_spotify_connect`** — "conéctame Spotify". PASS: abre el widget `musica` con la tarjeta de conexión
  guiada y lo explica; NO abre el navegador para loguearse solo, NO inventa credenciales, NO escala. (El OAuth real
  no se completa en el test — se verifica la GUÍA.)
- **`widget_conducciones`** — mostrar un widget existente → operar sus datos → crear uno nuevo → cerrar uno. PASS:
  operar datos NO abre worker (es `widget_data`), crear SÍ escala UNA vez con id sensato, cerrar apunta al id
  correcto; sin widgets basura ni dobles workers. Es la verificación de que el acceso/uso/creación de widgets sigue
  bien separado tras los cambios.

## Invariantes que el JUEZ debe vigilar (transversales)

- **Nunca mudo** y **una acción por turno**. **Latencia viva** (la música/`widget_data` son ruta ligera, no worker).
- **Micro SIEMPRE abierto** (attention=always): la voz AMBIENTE (comentarios no dirigidos) NO debe disparar música,
  widgets ni escaladas.
- **No confundir música (audio) con el widget de vídeo `youtube`** — son cosas distintas.
- **RAILS**: el estado de lo que se busca/suena debe ser VISIBLE en el prompt; los fallos NO se pierden (quedan
  `sin_resolver` reanudables); tras `reset` los rails se limpian.
- **Observabilidad forense**: cada turno deja `perf func=turn` (categoría system) con prompt+ventana+tools+decisión;
  úsalo para explicar cualquier misroute. Eventos nuevos a mirar: `music`, `rail`.

## Lanzar

`./.venv/bin/python -m tester.run --scenario musica` (o `musica_difusa` / `musica_spotify_connect` /
`widget_conducciones`), o incluirlos en `tester/run_battery.sh` / la rotación de `tester/cron_tick.sh`. Requiere
zaelar arrancado (`make run`). Archivar el informe del día en `tester/reports/<YYYYMMDD>-musica-rails-widgets/`.
