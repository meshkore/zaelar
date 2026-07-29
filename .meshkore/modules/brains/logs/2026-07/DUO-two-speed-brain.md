---
id: DUO-two-speed-brain
title: "Cerebro de dos velocidades: BRAIN=duo (fast Gemini + Hermes async) — Fase 1"
status: done
priority: high
owner: ricart
initiative: INI-008
created: 2026-07-05
updated: 2026-07-05
---

# Cerebro de dos velocidades — Fase 1 (go-ahead del operador 2026-07-05)

## Qué se hizo

Con `BRAIN=hermes` el turno de voz tardaba 5-8s (medido: `think` 4.8-6.0s vía AIMLAPI) → sin sensación de
conversación. Se implementó la arquitectura decidida en junio (arquitectura §8): un tercer cerebro enchufable
**`brains/duo/`** que pone un orquestador rápido NO-razonador en el slot del LLM y saca a Hermes del camino
crítico. El frontend no cambia.

- `fast_client.py` — streaming AsyncOpenAI contra el endpoint OpenAI-compat de Google. `reasoning_effort=none`
  (~1s el turno completo; TTFT sub-s). Default **`gemini-2.5-flash-lite`**: el `flash` normal quemó su cuota
  free-tier (20 req/día) en UNA sesión en vivo → 429. Cliente lazy (sin key no revienta la sesión).
- `prompt.py` — system prompt reconstruido POR TURNO: persona compartida + briefs de capacidades (widgets,
  cluster, cron — los mismos de Hermes) + **bloque de estado vivo** (hora, canal cluster, tareas de fondo) +
  reglas de triaje. Endurecido tras la sesión del coche: NUNCA escalar quejas/charla sobre el sistema; NUNCA
  adoptar nombres de transcripciones ruidosas (llamó "Van" al operador).
- `tasks.py` — registro en memoria de escaladas en vuelo → el rápido dice "sigo con ello, llevo 40s" y nunca
  "hecho" antes de tiempo.
- `llm_processor.py` — `DuoLLMProcessor`: streaming a TTS con el `strip_tags`/`speech` compartidos; `[[deep]]`
  dispara `runtime.ask(deny_tools=False)` en background (turno del OPERADOR → tools permitidas, a diferencia del
  path de cluster fail-closed) y entrega por `voice/proactive` (voz+UI), plegando el resultado en su ventana
  corta. **Modo degradado**: si el rápido cae (cuota/red), el turno pasa síncronamente a Hermes — lento pero vivo.
- `brains/__init__.py` — `uses_hermes()` (hermes+duo) para los gates de cron / `/api/hermes/*` / reasoner.
- `runtime.ask(deny_tools=None|False|True)` — override de confianza; default sigue fail-closed (cluster).
- Además: fix del desync **"Queued for the next turn"** en `acp_client.py` (+ `test_acp_client.py`): si Hermes
  encola el prompt tras un turno colgado, el cliente reinicia el agente y reenvía — antes dejaba a zaelar muda
  (visto en vivo con N=19 encolados).

## Ficheros

`brains/duo/{__init__,fast_client,prompt,tasks,llm_processor}.py` + `AGENTS.md` · `brains/__init__.py` ·
`brains/hermes/{runtime,acp_client}.py` · `brains/hermes/test_acp_client.py` · `brains/reasoner.py` ·
`voice/agent.py` (wiring) · `voice/tag_protocol.py` (`[[deep]]`) · `Makefile` (`run-duo`).

## Verificación

Gemini validado por curl (~1s; flash-lite 0.7s). E2E del procesador con Gemini real: turno instant ("¿estás
operativo?") responde sin escalar; turno de búsqueda habla la frase de espera + `[[deep]]` correcto; el resultado
de Hermes dispara sus tags de widget y llega por proactive. Hold de streaming: `[[deep]]` partido entre chunks
jamás se habla. Tests ACP 51+ y suite de seguridad en verde. Servidor corriendo con `make run-duo`.

## Pendiente (Fase 2, requiere go-ahead)

Preempción de voz sobre entregas profundas · digest de sesión → memoria Hermes · knob ⚙ del modelo rápido · Groq.
