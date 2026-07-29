---
id: T121
title: "Frontend /debug: columna Agente + la columna de modelo muestra el modelo del agente; extensible a >1 agente"
status: next
priority: high
owner: ricart
category: frontend
initiative: V2-012
depends_on: [T119]
created: 2026-07-09
updated: 2026-07-09
---

# T121 — Frontend /debug: columna Agente + la columna de modelo muestra el modelo del agente; extensible a >1 agente

En `/debug` (timeline): añadir la columna **Agente** (antes o después de la del modelo) que muestra el agente
(Cloud Code) cuando el evento corre por un agente; y hacer que la columna de **modelo** muestre el `agent_model`
cuando hay agente (si no, el modelo del FlashBrain como hoy). Layout preparado para >1 tipo de agente. Consumir los
campos nuevos de la vista SSE del observer.
