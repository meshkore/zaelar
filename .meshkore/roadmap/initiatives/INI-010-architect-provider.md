---
id: INI-010
title: Architect Provider — voz sobre el daemon MeshKore
status: done
owner: ricart
modules: [connectors, brains, voice]
updated: 2026-07-08
---

## Goal

Incorporar el **daemon MeshKore compartido** (remote control del Architect, `https://127.0.0.1:5573`) al
**catálogo de proveedores de código/agentes** de zaelar, junto a los que ya programan widgets (Claude Code
headless, Hermes). Por voz, el operador puede preguntar por sus proyectos, encargar trabajo ("mejora el módulo
de imágenes de ikamiro"), o crear proyectos nuevos; el brain solo TRANSMITE la intención — quien planifica,
ancla tareas y despacha agentes es el **architect-master** de cada proyecto, con toda la actividad visible en
el cockpit. Lo que el daemon produce puede quedarse en su repo o adoptarse después (p.ej. como widget).

## Scope (entregado 2026-07-05)

- `connectors/architect/` — módulo nuevo (declarado en `cluster.yaml`):
  - `client.py` — REST del daemon: `GET /projects`, `POST /team/architect-master/ask` (202 → request_id),
    `GET /team/requests/{id}` (poll), `POST /projects`. Bearer + `X-MeshKore-Project`; TLS autofirmado aceptado
    solo en loopback; 429 → `ArchitectBusy`.
  - `service.py` — ciclo de encargo async (patrón del generador de widgets): ask → poll 3s→5s hasta
    `ARCHITECT_ASK_TIMEOUT` (900s) → entrega por `voice/proactive` (voz+UI, hablado recortado si es largo) +
    nota `[SISTEMA]` (`voice/brain_notes`) para que el brain sepa el desenlace real. **Un ask por proyecto**;
    el segundo rebota con nota.
  - `brief.py` — protocolo + lista de proyectos viva (caché 60s, refresh en background, nunca bloquea el prompt
    por-turno del duo) + encargos en vuelo.
- Tags nuevas en `voice/tag_protocol.py` (con hold anti-split en streaming):
  `[[architect.ask:<proyecto>]]<intención en lenguaje natural>[[/architect.ask]]` y
  `[[architect.new]]{"name","parent"?}[[/architect.new]]`.
- Dispatch en los tres caminos del operador: Hermes (`brains/hermes/llm_processor.py`), duo rápido y duo deep
  (`brains/duo/llm_processor.py`). **Nunca desde turnos de cluster** (allow-list del bridge intacta).
- Brief inyectado en el kickoff de voz (`voice/agent.py`) y en el system por-turno del duo (`brains/duo/prompt.py`).
- Config en `.env`: `ARCHITECT_URL`, `ARCHITECT_TOKEN` (rotable desde el cockpit), `ARCHITECT_PARENT`,
  `ARCHITECT_ASK_TIMEOUT` (documentado en `config/.env.example`, sin valores).
- Tests: `tests/connectors/unit/architect/test_architect.py` (7 casos — parsing/hold de tags, happy path, rechazo por
  encargo en curso, status error, config ausente, brief sin token).

## Validación

- Unit: 7/7 en verde (`pytest connectors/architect/`).
- **E2E real 2026-07-05**: `list_projects` devolvió los 7 proyectos del daemon; ask al architect-master de
  `zaelar` → poll → `done` en ~20s con respuesta grounded del roadmap.

## Security

Tags **operator-only** (un peer de cluster no puede dirigir los proyectos del operador); token en `.env`, jamás
en briefs/notas/voz; TLS relajado solo loopback; alcance del token limitado por diseño del daemon (listar/crear
proyectos + hablar con architect-master). Sección nueva en `zaelar-security.md §Architect provider channel`.

## Operación — cómo se prueba y dónde está todo (guía para una sesión futura)

> Cuando el operador diga *"probemos el conector de meshkore para gestionar los proyectos por voz"*, esto es
> TODO lo que hay que saber. Guía operativa completa: **`zaelar-ops.md §3.3`**.

- **Dónde está el código**: `connectors/architect/` — `client.py` (REST del daemon), `service.py` (ask→poll→
  entrega por `voice/proactive` + nota `[SISTEMA]`, con timing `architect_ms` en /debug), `brief.py` (protocolo +
  proyectos vivos que se inyectan al brain cada conexión/turno).
- **Dónde está el token**: `ARCHITECT_TOKEN` en **`.env` de la raíz** (gitignored). Se rota desde el **cockpit
  del Architect → Config → Remote control** (síntoma de rotación: 401/403). Daemon: `https://127.0.0.1:5573`
  (compartido de la máquina, TLS autofirmado, zaelar NO lo arranca). Resto de vars: `ARCHITECT_URL`,
  `ARCHITECT_PARENT`, `ARCHITECT_ASK_TIMEOUT` (ver `config/.env.example`).
- **Smoke test sin voz**: `./.venv/bin/python -c "import asyncio, server.common; from connectors.architect
  import client; print(asyncio.run(client.list_projects()))"` → lista de proyectos (2026-07-08: daemon OK,
  4 proyectos — la lista CAMBIA, re-listar siempre).
- **Prueba por voz**: con zaelar corriendo, *«pregúntale al arquitecto de <proyecto> qué hay en el roadmap»* →
  frase de espera + tag `[[architect.ask:…]]`; el resultado llega solo por voz/nota en 30s-10min. Órdenes de
  trabajo van igual (*«dile al arquitecto de X que mejore Y»*). Observabilidad: eventos `🏗️ Architect` en
  `/debug`; encargos en curso en el brief (el brain responde «¿cómo va?» sin inventar).
- **Tests**: `./.venv/bin/pytest connectors/architect/ -q` (7 casos).
- **Estado real a 2026-07-08**: unit ✓ · e2e API real ✓ (ask→done ~20s) · daemon accesible con el token vigente ✓
  · **la pasada end-to-end POR VOZ (micro → tag → daemon → entrega hablada) aún no se ha ejercitado** — es el
  primer paso natural de "probemos el conector".

## Pendiente / ideas futuras

- **Primera prueba end-to-end por voz** (ver §Operación — único eslabón no ejercitado aún).
- Adopción formal de un proyecto creado por el daemon como widget/módulo de zaelar (flujo "adopta X").
- Cron + Architect: seguimiento proactivo de encargos largos ("avísame cuando ikamiro termine").
