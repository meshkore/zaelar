---
id: DUO-phase2
title: "Duo Fase 2: preempción de voz, digest de sesión → memoria Hermes, knob ⚙ del modelo rápido"
status: done
priority: medium
owner: ricart
initiative: INI-008
created: 2026-07-05
updated: 2026-07-05
---

# Duo — Fase 2 (go-ahead del operador «sigue», 2026-07-05)

## Qué se hizo

1. **Preempción — la voz del operador manda** (`voice/proactive.py` + `voice/turn_control.py`): las entregas
   proactivas (resultados `[[deep]]` y cron) ya no hablan encima del operador. `notify()` espera un hueco de
   silencio — sin turno de usuario abierto (`turn_control.user_turn_open()`, estado nuevo `_turn["open"]`) ni bot
   hablando, con 1.2s de respiro tras su última frase. Sin tregua en `PROACTIVE_MAX_WAIT` (45s) → el mensaje entra
   como nota `[SISTEMA]` al siguiente turno (nunca se pierde; la UI lo muestra siempre al instante).
2. **Digest de sesión → memoria de Hermes** (`brains/duo/llm_processor.py` + hook en `voice/agent.py` shutdown):
   al colgar, `session_digest_task()` manda el transcript corto de la capa rápida a Hermes en background
   (`runtime.ask(deny_tools=False)` — escribir memoria necesita tools) con la instrucción de guardar solo lo
   relevante y no responder. Su diario ya no queda ciego de charlas que nunca escalaron.
3. **Knob ⚙ `fast_model`** (`config/settings.py` + `brains/duo/fast_client.py`): visible SOLO con BRAIN=duo
   (regla del repo de features por-brain), persiste en settings.json → env `FAST_MODEL`. El cliente rápido ahora
   lee modelo/max_tokens/reasoning POR PETICIÓN (antes constantes de import — el knob habría sido un no-op
   silencioso): aplica al reconectar.

## Ficheros

`voice/proactive.py` · `voice/turn_control.py` · `voice/agent.py` · `brains/duo/llm_processor.py` ·
`brains/duo/fast_client.py` · `brains/duo/AGENTS.md` · `config/settings.py` · iniciativa INI-008.

## Verificación

Preempción probada en los 3 escenarios (libre → habla ya; ocupado → habla al liberarse a los 0.6s; sin tregua →
False → nota). Knob: presente con duo, oculto con hermes; `FAST_MODEL` dinámico verificado. Endpointing 9/9 y
`make test` OK. Servidor reiniciado con `make run-duo` y sano (brain=duo, cron, cluster arena).
