---
id: T-30-33
title: "T-30…T-33 · housekeeping: dirs vacíos, dead code, docstrings obsoletos, batching evaluado"
status: done
priority: low
owner: ricart
initiative: INI-006
created: 2026-07-03
updated: 2026-07-03
---

# T-30…T-33 — Cosmético / housekeeping (INI-006 · P3)

## Qué se hizo

- **T-30 · dirs vacíos** — borrados `voice/brains/` (solo `__pycache__`, resto de la restructura) y `voice/logs/`.
- **T-31 · dead code** —
  - `voice/tts/__init__.py`: fuera `S2S` (OpenAI Realtime jamás integrado), su rama en `make_tts()` y
    `available_providers()` (sin ningún caller); docstring saneado (`brain/tts/` → `voice/tts/`, fuera la
    jerga de "entrevista").
  - `server/common.py`: fuera `page()` (sin callers).
  - `server/state.py`: `reset_session_state()` NO se borra (tiene 2 callers) — se documenta por qué es un no-op
    deliberado (nombre/voz persisten entre reconexiones; queda como hook para estado transitorio futuro).
- **T-32 · docstrings obsoletos** —
  - `voice/agent.py`: cabecera reescrita (era "English assistant, sibling of interview/voice_agent.py, silence
    watchdog ON" — hoy es es-first, brain enchufable, watchdog OFF, STT local-first); fallback de `LLM_MODEL`
    `gpt-4.1` → `deepseek/deepseek-v4-flash`; comentario TTS sin refs de la era entrevista.
  - `voice/silence.py`: docstring sin "candidato/personas/_comun.md" + nota de que va OFF por diseño.
  - `Makefile`: primera línea sin refs muertas (NOTES.md / prototype_candidate); `.PHONY` completo
    (+run-hermes, sim-hermes, test-widgets).
  - Fallbacks de modelo en `brains/reasoner.py` y `tests/agent_headless/harness/run.py` → deepseek (remate de T-25).
- **T-33 · batching de logs en observer** — **evaluado y diferido a propósito**: el volumen actual (decenas de
  eventos por turno) no justifica batching, y bufferizar añade riesgo de perder eventos en un crash justo cuando
  más se necesitan (/debug es la herramienta de diagnóstico). Revisar solo si el volumen sube un orden de
  magnitud (p. ej. tráfico de cluster sostenido).

## Verificación

- `make test` OK · `make test-widgets` OK (7 widgets, 0 fallos) · `py_compile` de todos los ficheros tocados.
- `make run-hermes` sano tras la limpieza (`/api/brain`, `/api/settings` responden; 0 errores en log).
