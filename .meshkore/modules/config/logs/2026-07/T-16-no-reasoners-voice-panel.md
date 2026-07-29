---
id: T-16
title: "T-16 · panel ⚙ de cerebro de voz: solo no-razonadores validados"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# T-16 — Quitar razonadores del ⚙ panel de cerebro de voz (INI-006 · A4)

## Qué se hizo

Regla dura del proyecto: **NO razonadores en el path de voz** (un modelo de razonamiento no cierra el turno ACP
→ zaelar se queda muda). Sin embargo la lista curada del panel ⚙ (`config/settings.py _BRAIN_MODELS`) ofrecía
GLM-5.2 y GLM-4.6 (razonadores) en cabeza, y el catálogo `/api/providers` (`server/voice_api.py`) usaba
`zhipu/glm-5-2` como default de display.

Fix:

- `_BRAIN_MODELS` curado a **no-razonadores validados** (cierran el turno ACP): `deepseek/deepseek-v4-flash`
  (actual) y `gpt-4.1` (validado). Los razonadores solo entran por free-text, a sabiendas del operador
  (el campo sigue siendo `free_text`).
- `voice_api.py /api/providers`: fallback de display `deepseek/deepseek-v4-flash`; la alternativa listada pasa
  de `glm-4.6` a `gpt-4.1`.

Observación para el operador (no tocada — config local): el `.env` tiene `LLM_MODEL=zhipu/glm-5-2`, que es el
modelo del brain `direct` (`make run` sin Hermes) y del harness. Si se usa el modo direct por voz, conviene
cambiarlo a un no-razonador.

## Ficheros tocados

- `config/settings.py` — `_BRAIN_MODELS` curado + comentario con la regla.
- `server/voice_api.py` — default de display + alternativa en el catálogo de providers.

## Verificación

- Servidor reiniciado (`make run-hermes`): `/api/settings` → knob `brain_model` con opciones
  `['deepseek/deepseek-v4-flash', 'gpt-4.1']` y value actual `deepseek/deepseek-v4-flash`;
  `/api/providers` → LLM sin GLM en las opciones curadas (la 1ª línea refleja el `LLM_MODEL` del `.env`, que es
  reporting fiel de lo configurado).
