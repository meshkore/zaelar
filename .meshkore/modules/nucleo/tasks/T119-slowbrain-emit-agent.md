---
id: T119
title: "SlowBrain/CodeAgent emite agent + agent_model (modelo del RunSpec, por invocación) al despachar"
status: next
priority: high
owner: ricart
category: nucleo
initiative: V2-012
depends_on: [T118]
created: 2026-07-09
updated: 2026-07-09
---

# T119 — SlowBrain/CodeAgent emite agent + agent_model (modelo del RunSpec, por invocación) al despachar

`nucleo/dispatch.py` + `nucleo/agentes/{base,claude_code}.py`: al despachar una tarea al CodeAgent, emitir el evento
con `agent="cloud-code"` y `agent_model` = el modelo del `RunSpec` de ESA invocación (Haiku búsqueda/estudio, Opus
4.8 razonamiento complejo). Nunca un default global.
