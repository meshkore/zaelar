---
id: S-04
title: "S-04 · XSS en el widget agenda — render por textContent (SEC-1 alta)"
status: done
priority: high
owner: ricart
initiative: INI-007
created: 2026-07-03
updated: 2026-07-03
---

# S-04 — XSS en `widgets/agenda/widget.js` (INI-007 · SEC-1)

## Vector

`render()` construía todo el widget con `el.innerHTML` interpolando campos que el brain puede **empujar** vía
`[[push:agenda]]` (por tanto no confiables): `data.date`, `data.now`, `active.label`, `b.label`/`b.start`/
`b.end`, `f.label`/`f.objective`, `data.coaching[]`, `data.warnings[]`. Un payload en cualquiera de ellos
ejecutaba HTML en el canvas. Seguía vivo tras W-001.

## Fix

`render()` reescrito a **construcción DOM con `textContent`** (convención de la casa en `AGENTS.md`: nunca
`innerHTML` para datos no confiables), preservando exactamente estructura, clases, estilos, el contador en vivo y
los botones de acción. El `title` de los chips se pone con `setAttribute` (atributo, no HTML) y el color de la
barra viene del mapa fijo `KIND` (paleta cerrada, no interpolación). agenda es el widget de referencia, así que
ahora modela la convención.

## Verificación (adversarial — rojo pre-fix, verde post-fix)

`widgets/agenda/test_xss.mjs` (node, shim DOM mínimo que registra cualquier escritura a `innerHTML`): con un
payload `<img src=x onerror=alert(1)>` en label/coaching/warnings/date/etc. → **0 escrituras a innerHTML** y el
payload aparece como `textContent` en 7 nodos. Confirmado que FALLA contra el widget.js pre-fix (registraba
escrituras a innerHTML). `make test-widgets` → agenda golden estable (8 keys) + parsea; `/widgets/agenda/data`
sirve en vivo.
