# V2-034 — FlashBrain: modelo más inteligente (Haiku 4.5) + guards de canvas META

**Estado:** DONE (2026-07-12). Origen: sesión MANUAL de voz del operador (21:22). Diagnóstico con el canal de
prueba headless (V2-032, `nucleo/flash/probe.py`).

## Qué falló en la sesión (observabilidad, 21:22–21:27)

1. **"Parece tonto" / alucina en vez de buscar:** ante "¿quiénes son los cuatro finalistas del Mundial 2026?" el
   FlashBrain (grok-4-fast) respondió de imaginación ("Argentina, Brasil, Francia, España") SIN buscar; al
   presionarlo, buscó y se CONTRADIJO, y no supo explicar de dónde salió "Brasil". El operador lo notó y se frustró.
2. **Widgets espurios:** cuando el operador PREGUNTABA/se quejaba de un widget ("¿por qué has abierto el de
   proyectos si no te lo he pedido?"), zaelar ABRÍA widgets (`mensajeria`, `results`) — el modelo emitía `[[show]]`
   sobre una pregunta META, no una orden. Y una queja de LATENCIA se escaló y acabó mostrando `meteo-soria`.
3. **Latencia** percibida alta (mezcla de TTFT del modelo + STT/TTS locales).

## Qué se hizo

### A) Modelo del FlashBrain: grok-4-fast → **claude-haiku-4.5** (por A/B medido, no a ojo)
A/B con el canal de prueba (`make flash`, `probe.run_turn(model=…)`) sobre los turnos reales de la sesión, 3
no-razonadores:

| | busca cuando debe | razona su propio error | pregunta META | latencia |
|---|---|---|---|---|
| grok-4-fast (antes) | inconsistente | no | acción espuria (widget_data) | 1–5 s |
| gemini-2.5-flash | **no** (deflecta) | débil | ok pero **trunca** | 1–3 s |
| **claude-haiku-4.5** | **sí** | **sí, introspecciona** | explica, no actúa | 2–3 s p50 |

Haiku gana claramente en inteligencia a latencia comparable, y es NO-razonador (respeta la regla dura). Cambiado el
default (`config/v2.py::_DEFAULTS.fast`) y el `.env` local (`FAST_MODEL`). Reversible: `FAST_MODEL=x-ai/grok-4-fast-non-reasoning`.

### B) Guard determinista de canvas para preguntas META (`voice/engine/llm/providers/nucleo.py`)
`_is_meta_widget_question()`: una pregunta/queja sobre una acción de widget YA ocurrida ("¿por qué has abierto X?",
"no deberías haber abierto nada", verbo en pasado/participio) NUNCA es una orden de mostrar → se ignora el `[[show]]`
del modelo Y no se dispara `_widget_fallback`. NO pisa una orden educada ("¿me muestras la agenda?"). Test:
`voice/engine/llm/providers/test_nucleo_guards.py`.

## Validación (canal de prueba, memoria aislada)
Re-corrida la sesión con Haiku: busca en las dos preguntas factuales, INTROSPECCIONA el error de Brasil ("no
debería habértelo dicho sin verificarlo"), en la pregunta META responde `chat` ("no he abierto nada, es raro")
SIN abrir widget, y "muéstrame la agenda" sigue disparando `canvas:show`. Latencia p50 2.9 s (el pico de 7 s es
cold-start; el prewarm lo absorbe en el server vivo).

## Pendiente / notas
- La latencia STT→voz (Kokoro/Whisper local, Metal) es un eje SEPARADO del modelo del cerebro; Haiku va por AIMLAPI
  (nube) igual que grok → libera la GPU, sin regresión.
- La precisión de escritura de memoria (identidad polucionada) es **V2-033** (equipo de memoria).
