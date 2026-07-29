---
id: T118
title: "Esquema del observer: campos agent + agent_model en el evento, persistidos en el timeline jsonl"
status: next
priority: high
owner: ricart
category: voice
initiative: V2-012
depends_on: []
created: 2026-07-09
updated: 2026-07-09
---

# T118 — Esquema del observer: campos agent + agent_model en el evento, persistidos en el timeline jsonl

Añadir a los eventos del observer/bus dos campos opcionales: `agent` (tipo de agente que atiende el proceso; hoy
`cloud-code`, extensible) y `agent_model` (el modelo que usa ese agente, por invocación). Persistir ambos en el
timeline jsonl para poder reconstruir a posteriori qué agente/modelo atendió cada proceso. Loop-agnóstico
(thread-safe: sirve desde el hilo separado del agente del navegador).
