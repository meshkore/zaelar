---
id: INI-004
title: Hermes Self-Update
status: done
owner: ricart
modules: [brains, server, frontend]
updated: 2026-06-30
---

## Goal

Let the operator update the Hermes brain binary (`~/.local/bin/hermes`) from the zaelar UI —
detection → confirmation → live progress → resumed session — without touching a terminal or
restarting the Python server, and **without silently breaking the voice path** when the new
binary ships a different ACP contract.

## Scope

- `GET /api/hermes/status` — parse `hermes --version`, report `{available, version, behind}`
- `POST /api/hermes/update` (SSE) — stop live sessions → `hermes update` → **ACP health-check** → done/error
- UI — amber banner + live-log overlay (`frontend/app/components/UpdateBanner.js`)
- Brain-agnostic mounting — `/api/hermes/*` and the banner exist ONLY when `BRAIN=hermes`
- Makefile parity — `make update-hermes` / `make hermes-check` mirror the UI command + guard

## Lineage

Originally specced as **H001** in `asimovia/vala.voice` (`.meshkore/modules/zaelar/log/2026-06/`,
subtasks H001.1–H001.3) before zaelar adopted its own `.meshkore/` (MeshKore Standard v27).
Hardening + brain-agnostic rework tracked locally — see brains module log.

## State

**Shipped** (commit `75a35d9`, 2026-06-30). Functional and verified locally: status reports `v0.17.0 behind 1`;
ACP health-check brings up `hermes-agent v0.17.0 · protocol 1`; `direct` runs correctly hide the Hermes
routes/banner. Operator runbook: `.meshkore/docs/ops/zaelar-ops.md` §3.1 (Upgrading Hermes).
Only open follow-up (not blocking): the `hermes --version` parser is text-fragile if Hermes changes its CLI.
