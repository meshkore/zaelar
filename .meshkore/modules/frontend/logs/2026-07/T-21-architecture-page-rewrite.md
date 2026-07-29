---
id: T-21
title: "T-21 · reescritura de la página servida /architecture (user-facing)"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-03
updated: 2026-07-03
---

# T-21 — Reescribir `/architecture` (INI-006 · D1)

## Qué se hizo

La página servida `frontend/pages/architecture.html` (user-facing) llevaba la foto pre-restructura: paths
muertos (`voice_agent.py`, `hermes_llm.py`, `static/widgets-desktop.js`, `assistant.html`, `docs/ARCHITECTURE.md`),
modelo `gpt-4.1`, pestaña Context rota (fetch a `/api/doc/CONTEXT`, endpoint borrado en T-19), sin
connectors/meshkore, sin brains pluggables ni self-update, sin ChatWall/importers/harness ni caja de cluster.

Actualizado:

- **Recorrido del turno**: paso 4 = Hermes caliente compartido (una conversación voz+chat+cluster, un turno ACP
  a la vez); paso 5 = `deepseek/deepseek-v4-flash` + regla dura de no-razonadores (picker curado).
- **Tabla de módulos** reescrita con la estructura real: voice/ (STT MLX/faster-whisper), brains/ (pluggables,
  `BRAIN=…`, rutas por-brain montadas condicionalmente, self-update con health-check, cron nativo),
  connectors/meshkore (3er I/O), widgets (data.py off-loop + store versionado + harness), frontend (módulos ES
  sin build: core/services/components — ChatWall, StatusPanel, CronPanel, Notice, UpdateBanner… — y desktop),
  config ⚙ (gates de T-15/T-16), importers/, harness/, observer con timing ⏱.
- Claim "cero cross-imports" → "solo bridges guarded (brief, brain_notes, proactive)".
- **Nota de seguridad del cluster** (resumen de alto nivel: tools denegadas en turnos de cluster, allowlist de
  tags, wrapping de entrada, escaneo de salida, loopback-only, wss, strict/fail-closed) apuntando a
  `zaelar-security.md` — sin detalle de explotación.
- **Tabla de tags** completa: + `[[delete:ID]]` (W-2), `[[cluster.*]]`, `[[cron.*]]`; create/modify con progreso
  y rollback.
- **Diagrama SVG**: modelo deepseek, caja «Canal cluster MeshKore» en el servidor + caja externa «CLUSTER
  MeshKore (peers no confiables · wss)» con su ruta por el corredor; paths reales en los nodos
  (`voice/agent.py`, `brains/hermes/`, `app/widgets/desktop.js`, `frontend/index.html + app/`); viewBox/grupos
  reajustados sin solapes.
- **Pestaña Context** = mapa estático de la doc canónica `.meshkore/docs/` (categorías + operativa + roadmap).
- Sección «Sustituir/actualizar el cerebro» reescrita sobre `brains/` + self-update; referencia canónica a
  `.meshkore/docs/architecture/zaelar-architecture.md`.

## Verificación

- `/architecture` → 200 con el servidor vivo; el contenido nuevo presente (deepseek, delete:ID,
  connectors/meshkore, MLX, ChatWall, brains/hermes) y **0 menciones** de gpt-4.1 en la página; el diagrama
  renderiza (SVG se construye client-side, sin errores de sintaxis — página cargada y grep del payload).
