---
id: INI-003
title: Widgets pure-frontend + generic data layer
status: cancelled
owner: ricart
modules: [widgets, frontend, server]
updated: 2026-06-30
---

## Goal

Evaluate evolving widgets from **full-stack** (per-widget `data.py` on the server) toward **pure-frontend**:
a widget is just `widget.js` + a manifest that *declares* its data needs, and the UI server provides a **generic
data layer** (fetch/proxy/persistence/secrets) that serves every widget. Lighter and safer at the "thousands of
widgets" scale, and it matches the operator's mental model (widgets live and run in the frontend; the server keeps
their data).

## Background — how widgets work today (A)

A widget is a self-contained folder `widgets/<id>/`:
- `widget.js` — runs in the **frontend** (browser): `export render(el, data, ctx)`. The visual.
- `data.py` — runs on the **server** (Python), OPTIONAL: `view_data(q)` → JSON, `apply_action()`, `coach_context()`.
- `manifest.json` — metadata; `seed.json` / `planner.py` for some.
- Persistence: `widgets/_data/<id>.json`, isolated per widget (`widgets/store.py`, atomic writes). No shared DB.

The frontend desktop does `import('/widgets/<id>/widget.js')` + `fetch('/widgets/<id>/data')`. `data.py` exists for
live/external data (weather, agenda, search), server-side compute (planner), and mutations+persistence. The audit
(`.meshkore/docs/architecture/zaelar-audit.md`) confirms the three layers (voice/brain/widgets) are decoupled with
zero cross-imports — so A is sound, not broken. This initiative is about scale + simplicity, not a fix.

## The two designs

- **(A) current — full-stack widget.** `widget.js` + `data.py` + isolated json. Powerful (arbitrary server compute),
  built, isolated. Cost at scale: each widget ships server Python (written by the code-gen agent) → wider trust +
  import surface per widget.
- **(B) proposed — pure-frontend widget + generic data layer.** Widget = `widget.js` + a manifest that DECLARES its
  data sources (e.g. `{fetch: url, auth: keyref}`, `{store: key}`). The server exposes GENERIC endpoints for
  fetch/proxy (CORS + secrets), key/value persistence, and live polling. Widgets carry NO Python. The code-gen agent
  only writes JS. Lighter, safer, uniform.

## Scope to evaluate

- A manifest schema for declared data sources (fetch/proxy, store keys, poll interval, auth/key references).
- A generic data layer in the server: `GET/POST /widgets/data` (key/value over the existing per-widget store),
  `GET /widgets/proxy` (server-side fetch with secrets + CORS handling), live-poll support.
- A credential/secret reference mechanism (today the brain asks the user inline; see the credentials seam in the
  architecture doc) so a pure-frontend widget can use a key without embedding it.
- Migration path for the current widgets that have `data.py` (agenda/planner is the hardest — server-side compute).
- Decide what stays server-side by necessity (heavy compute, secret-bound logic) vs. what moves to declared data.

## State

Proposed. Not started. Spun out of the 2026-06-30 folder restructure discussion. Decide A-vs-B (or hybrid: keep
`data.py` allowed but make it the exception, default to declared data) before implementing.
