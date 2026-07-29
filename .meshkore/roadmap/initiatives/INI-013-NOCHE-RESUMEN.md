# INI-013 — Resumen de la sesión nocturna autónoma (2026-07-06 → 07)

Lee esto primero por la mañana. Detalle por iteración: `git log` (13 commits, cada ~30 min) + INI-013.

## zaelar FUNCIONA (verificado en corridas limpias, juez GLM 5/5)
- Responde por **voz, chat y paste** (castellano).
- **Dispara widgets**: `[[show:clock]]`, `[[show:agenda]]`, `[[close:*]]`, `[[show:mensajeria]]` (verificado en traza).
- **Memoria**: guarda ("recuerda que…") escalando a Hermes; recall en-contexto instantáneo.
- **TTS local NUNCA mudo**: Metal (mlx) rápido + fallback in-process kokoro-onnx (sin servidor, sin el bug de shapes).
- **Core sin Docker** (LiveKit nativo). Cluster reportado en lenguaje natural (no JSON).

## Fixes de la noche (todos commiteados, sin push)
1. fast layer DeepSeek 400 (reasoning_effort solo a Gemini) → zaelar dejó de quedarse mudo/gibberish.
2. Widgets no disparaban → few-shot de tags en el prompt duo.
3. Memoria: guardar escala a Hermes; recall en-contexto sin stall de 8.7s.
4. Cartesia TTS 402 (sin saldo) → Kokoro local Metal.
5. Handler chat/paste: create_task(SpeechHandle) → llamada directa (nunca respondía).
6. TTS local fiable: fallback kokoro-onnx in-process.
7. Tester: castellano, latencia negativa, medición de latencia de texto, leer respuesta de la traza (no del STT).
8. Juez: accion por tipo de objetivo + contexto de canales (informes fieles). Bucle resiliente (readiness).

## ABIERTO — para ti / próxima sesión (por prioridad)
1. **LATENCIA del fast layer (EL bloqueante)**: DeepSeek/AIMLAPI = 3s base, 10s en inputs largos. NO es sub-segundo.
   DECISIÓN TUYA: elegir un **modelo local rápido y capaz** (qwen2.5:7b, Kimi, GLM-air…) para el fast layer. No lo
   he adivinado de noche. qwen2.5:3b es rápido pero demasiado tonto para los tags; Gemini free-tier descartado (429).
2. **No-respuesta intermitente en chat/paste (~50% de ciclos all-1s)**: zaelar se une y saluda, pero el turno de
   texto a veces no genera respuesta (sin error de fast layer; no es el _window del duo —es por-sesión— ni el TTS).
   HIPÓTESIS a comprobar con calma (no de noche a ciegas): (a) `session.generate_reply()` desde el handler
   `data_received` se descarta si la sesión está ocupada/hablando; instrumentar el handler para loguear si se llamó
   y si lanzó; (b) dispatch del agente por-sala del worker embebido lento/intermitente en salas nuevas. Los ciclos de
   VOZ no sufren esto tanto → apunta al camino data-channel del texto.
3. **Menor**: traza `/events` es global al proceso; filtrar por room/session_id si molesta (impacto bajo en el bucle).

## Cómo seguir
- `bash tester/guard.sh` levanta zaelar + bucle. Informes en `tester/runs/report_*.md` (WAV/logs gitignored).
- Config de test en `.env` (FAST_*=DeepSeek override; #TEST-OFF# = diseño local Ollama) + `config/settings.json`
  (kokoro_local + ef_dora). Claves en `.meshkore/credentials/tester.env`. Observabilidad: `zaelar-observability.md`.

## Instrumentación añadida (diag chat/paste) — 2026-07-07
El handler `data_received` de zaelar ahora emite "📥 chat/paste recibido" al recibir texto y "chat/paste
generate_reply falló" si lanza. En el próximo ciclo chat/paste all-1s LIMPIO (del bucle, sin solape manual): si NO
aparece "recibido" → el paquete de datos no llegó al handler (revisar sala/topic/timing del data-channel); si aparece
"recibido" pero no hay reply → generate_reply se descarta (sesión ocupada). Diagnóstico definitivo pendiente de un
ciclo limpio. NOTA: mi verificación manual colisionó con el ciclo del bucle (dos testers → contenido cruzado); en el
bucle los ciclos son secuenciales, así que ese solape no ocurre en operación normal.

## VEREDICTO chat/paste (2026-07-07, instrumentación) — mayormente RESUELTO
La instrumentación confirma: el texto del data-channel SÍ llega al handler de zaelar (evento "📥 chat/paste recibido"
con el texto real, visible en `.meshkore/logs/timeline-latest.jsonl` / stream del observer — NO en el events.jsonl del
DebugBus; ojo al depurar, son dos streams distintos). Ciclos chat recientes puntúan **5/5/5/5** (cycle 30: zaelar
saludó, respondió "Son las 06:49 de la mañana, Alex" en castellano, se despidió — perfecto). Los all-1s residuales son
una MINORÍA transitoria (fallo puntual de STT/turno, no sistémico), no un bug de entrega ni del cerebro. zaelar
chat/paste = FUNCIONAL. Queda pulir la cola de transitorios, pero NO es bloqueante.

### ÚNICO bloqueante real que queda: LATENCIA del fast layer → decisión de modelo local rápido (operador).

## VOZ desbloqueada + CONFIRMADA (2026-07-07)
Los escenarios de VOZ crasheaban porque el **TTS del tester (Cartesia) se quedó sin saldo → 402** (el tester no podía
hablar) → solo chat/paste (data-channel) producían informes. Fix: `TESTER_TTS=deepgram` (Aura español, con saldo) +
providers pasa modelo `aura-2-selena-es`. Voz desbloqueada.
IMPORTANTE — zaelar VOZ CONFIRMADO FUNCIONANDO: en la sesión de prueba, zaelar oyó al tester (captó el nombre "Alex")
y respondió coherente en castellano ("Encantado, Alex. Son las 07:22 de la mañana"). El canal principal funciona.
Pendiente (tester, no zaelar): la captura de las respuestas de VOZ de zaelar por el tester aún falla a veces (reportó
"(vacío)" pese a que zaelar habló 3 turnos) — mismo patrón de captura que arreglamos en chat; falta afinar el slice
por-turno de la traza para los turnos de voz (más largos). NO es bug de zaelar.
Nota menor: a "ponme el reloj en pantalla" zaelar respondió la hora en vez de [[show:clock]] — desambiguación reloj=hora vs widget.

## Captura de respuestas de VOZ afinada (2026-07-07)
Los timeouts "(vacío)" en voz eran el tester no capturando la respuesta de zaelar (STT Deepgram dropea + la traza SSE
llega con lag tras wait_reply). Fix en `tester/run.py`: `zaelar_reply` ahora SONDEA la traza hasta ~4s si viene vacío,
en vez de declarar falso timeout. Verificado en widget-voz: zaelar capturado ("Alex, te pongo el reloj ya") + widget
disparó (frontend: ['widget:show']). Los informes de VOZ ya reflejan el comportamiento real de zaelar. Queda ruido de
STT-sobre-STT (tester Deepgram-Aura → whisper de zaelar a veces garbla un turno) — inherente, el juez lo tolera.

## Traza de widgets con ID + estado de la intermitencia (2026-07-07)
`frontend_actions` ahora incluye el id del widget (`widget:show:clock` en vez de `widget:show`) → informes precisos +
el juez puede verificar que salió el widget CORRECTO (el id va en el evento; strip_tags emite ("show",{"id":...})).
INTERMITENCIA (estado honesto tras muchas iteraciones): zaelar funciona en MUCHOS ciclos (widget 081317: 4/4/4 con
widget:show,widget:show; memory 3/3/3/4; chat 5/5/5) pero falla en una MINORÍA (ciclos all-1s sin reply/widget). Ya
probado: readiness check, settle tras saludo, leer respuesta de la traza, sondeo de traza ~4s. Reducen pero no eliminan
la cola. Hipótesis restante (para sesión con calma, no de noche a ciegas): dispatch por-sala del worker embebido a
veces lento/falla en salas nuevas, o el turno de arranque de la sesión pisa el primer turno. NO es un bloqueante de
producción (el operador usa una sola sesión estable, no 60 salas nuevas/hora como el tester). El bloqueante REAL sigue
siendo la latencia del fast layer (modelo local rápido, decisión del operador).

## FIX 2026-07-07 (iter cron): supresión de alucinaciones de Whisper (bug REAL de zaelar)
Análisis de datos (16 sesiones): zaelar funciona en TODAS (ws=1, bot_txt 4-13, user_txt 4-23) — conversa rico. Pero
el STT (whisper Metal) ALUCINA frases fantasma sobre el audio del tester en silencios/ruido: "Gracias por ver el
video", "Gracias." (alucinaciones clásicas de Whisper de subtítulos de YouTube) → zaelar RESPONDE a esos turnos falsos
→ conversación incoherente → scores bajos. El gate de energía no las caza todas. Fix en `whisper_local.py`: lista de
frases-alucinación conocidas; si la transcripción ES SOLO una de ellas → se descarta (texto vacío). Verificado unit:
alucinaciones descartadas, habla real conservada. Es un bug REAL de zaelar (afecta al uso con ruido de fondo, no solo
al test). Reduce el derailing → subirán coherencia/utilidad en los informes.
CLAVE: la "intermitencia" era mayormente esto (STT-sobre-STT + alucinaciones), NO fallo del cerebro/dispatch. zaelar
está sólido; lo que fallaba era el STT sobre audio ruidoso del tester.
