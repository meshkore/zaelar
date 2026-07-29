---
id: S-10
title: "S-10 · escaneo estático de reglas de la casa en el generador (SEC-3)"
status: done
priority: medium
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-10 — Validación estática de reglas de la casa (INI-007 · SEC-3)

## Qué faltaba

El smoke-test de W-001 prueba que `view_data()` CORRE, no que el código respeta el aislamiento/no-red/no-XSS
(AGENTS.md, hasta ahora solo prosa). Un agente headless podía emitir `innerHTML` interpolado (XSS), `fetch`/
`WebSocket` (red desde el cliente), `import()`/`eval` (código dinámico), o un import no-stdlib / secreto
hardcodeado en `data.py`.

## Fix (`widgets/generator.py`, gates en `_validate`)

- **`_scan_widget_js`**: rechaza sinks de red/código dinámico (`fetch(`, `XMLHttpRequest`, `WebSocket`,
  `EventSource`, `import(`, `eval(`, `new Function`, import externo `from "…"`) y sinks de HTML **con
  interpolación** (`innerHTML`/`outerHTML` cuyo RHS lleva `${…}` o concatenación con variable;
  `insertAdjacentHTML`/`document.write` siempre). El `innerHTML` estático (string fijo) se permite.
- **`_scan_data_py`** (AST): rechaza imports absolutos no-stdlib (allowlist `sys.stdlib_module_names` + relativos
  `from ..` + paquete `widgets`) y secretos hardcodeados (private key, sk-/ghp_/AKIA/AIza, asignación
  api_key/secret/password/token = "…").
- Cableados en `_validate` antes del compile/smoke.

## Traído a conformidad

`widgets/search/widget.js` interpolaba `data.query` (web/usuario) en `el.innerHTML` (línea de "Estoy
buscando…") — un sink XSS real; reescrito a construcción DOM con `textContent` para que todo el catálogo pase el
nuevo gate.

## Verificación (adversarial — rojo pre-fix, verde post-fix)

`test_security.py` (+6): innerHTML interpolado / fetch / import() / WebSocket → rechazados; innerHTML estático +
textContent → OK; `import requests`/`from bs4` → rechazados; stdlib + relativos → OK; secreto hardcodeado →
rechazado. Rojo contra el código pre-fix. `make test-widgets` → 7/7 (search ya conforme). Suite: 48 passed.
`make run-hermes` sano; `/widgets/search/data` sirve.
