---
id: T-31
title: "T-31 · Proveedor Architect: voz sobre el daemon MeshKore (connectors/architect/)"
status: done
priority: high
owner: ricart
initiative: INI-010
created: 2026-07-05
updated: 2026-07-05
---

# T-31 — Proveedor Architect (INI-010) — módulo `connectors/architect/`

## Qué se hizo

El daemon MeshKore compartido de la máquina (`https://127.0.0.1:5573`, remote control del Architect) entra en
el catálogo de **proveedores de código/agentes** de zaelar, junto a los que ya programan widgets. El brain
transmite la intención del operador con tags silenciosas; el architect-master de cada proyecto hace el trabajo.

- `client.py` — REST del daemon: `GET /projects`, `POST /team/architect-master/ask` (202 → request_id),
  `GET /team/requests/{id}`, `POST /projects`. Bearer + `X-MeshKore-Project`; TLS autofirmado solo loopback;
  429 → `ArchitectBusy`.
- `service.py` — ciclo async (patrón del generador de widgets): ask → poll 3s→5s hasta `ARCHITECT_ASK_TIMEOUT`
  (900s) → entrega por `voice/proactive` (hablado recortado si >600 chars) + nota `[SISTEMA]`
  (`voice/brain_notes`). Un ask por proyecto; el segundo rebota con nota, no se encola.
- `brief.py` — protocolo + proyectos vivos (caché 60s, refresh en background, nunca bloquea) + encargos en vuelo.
- Seguridad: tags operator-only (la allow-list del bridge de cluster no las admite); token en `.env`, nunca en
  briefs/voz. Sección nueva en `zaelar-security.md`.

## Ficheros tocados

`connectors/architect/{__init__,client,service,brief,test_architect}.py` (nuevos) · `voice/tag_protocol.py`
(ARCH_ASK_RE/ARCH_NEW_RE + hold) · `brains/hermes/llm_processor.py` + `brains/duo/llm_processor.py` (dispatch)
· `voice/agent.py` + `brains/duo/prompt.py` (brief) · `cluster.yaml` · docs (CLAUDE.md, modules, architecture,
security, seed) · `config/.env.example` · `INI-010`.

## Verificación

- `pytest connectors/architect/` — 7/7 (parsing/hold de tags, happy path, busy, error, config ausente).
- Suite completa 73/73 en verde.
- **E2E real 2026-07-05**: `list_projects` → 7 proyectos; ask al architect-master de `zaelar` → `done` en ~20s
  con respuesta grounded del roadmap. `build_fast_system()` muestra `[Proyectos ahora] …` tras el refresh.
