---
id: S-08
title: "S-08 · endurecimientos V7/V8/V9 — permission match, redacción de _classify, compare constant-time"
status: done
priority: low
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-08 — Endurecimientos menores (INI-007 · V7/V8/V9)

## Fixes

- **V7 · `brains/hermes/acp_client.py _decide_permission`** — en un turno NO confiable (cluster) el matcher de
  "reject" incluía un `"no"` suelto; `"no"` es substring de muchas etiquetas del lado allow ("Allow, no
  confirmation", "annotate", "Notebook") → podía **seleccionar una opción allow y devolverla como el "reject"**,
  aprobando de facto una tool en un turno no confiable. Ahora matchea solo `reject`/`deny` (prioriza el campo
  ACP `kind`), y si no hay reject → `cancelled` (nunca allow).
- **V8 · `connectors/meshkore/client.py _classify`** — el detalle de una excepción de conexión (o el `reason` de
  un close del servidor) puede contener la URL `wss://` **con el token**, y ese detalle va a logs/timeline. Ahora
  el detalle pasa por `store.redact()`.
- **V9 · `connectors/meshkore/server_api.py _guard`** — el compare del `X-MeshKore-Token` era `==` (oráculo de
  timing). Ahora `hmac.compare_digest` (constant-time).

## Verificación (adversarial — V7/V8 rojos pre-fix)

`test_security.py` (+4): turno no confiable con una opción allow que contiene "no" → se elige el reject real (no
la allow); solo-allow → `cancelled`; `_classify` de un OSError con token en la URL → detalle redactado; guard
por token acepta el correcto y da 403 al incorrecto/ausente. V7 y V8 confirmados rojos contra el código
pre-fix; V9 es constant-time (sin cambio observable, su test valida la ruta de autorización). Suite: 42 passed.
`make run-hermes` sano.
