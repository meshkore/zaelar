---
id: T120
title: "Procesos del FlashBrain (agente navegador/búsqueda, hilo separado) emiten agent + agent_model"
status: next
priority: high
owner: ricart
category: nucleo
initiative: V2-012
depends_on: [T118]
created: 2026-07-09
updated: 2026-07-09
---

# T120 — Procesos del FlashBrain (agente navegador/búsqueda, hilo separado) emiten agent + agent_model

Los procesos que el FlashBrain lanza por un agente (el del navegador: organizar/ejecutar una búsqueda) emiten
`agent`+`agent_model` (`NAVEGADOR_AGENT_MODEL` def Haiku / `NAVEGADOR_AGENT_MODEL_STRONG` al atascarse), incluido
desde el hilo separado del owner del navegador.
