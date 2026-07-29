---
id: W-009
title: "Bug: widget.js se servía sin Cache-Control — un fix podía quedar invisible indefinidamente"
status: done
priority: high
owner: ricart
initiative: INI-011
created: 2026-07-06
updated: 2026-07-06
---

# Bug — caché HTTP de widget.js sin invalidar

## Síntoma (reportado por el operador)

Tras migrar los widgets al tema dark/light (`W-008`), el widget `results` ("Proyectos") seguía viéndose con
cartas blancas/texto oscuro sobre el canvas oscuro — como si no se hubiera migrado.

## Causa raíz

El fichero en disco (`widgets/results/widget.js`) ya usaba `var(--hb-*)` correctamente (confirmado por
`curl`). El bug era de **caché del navegador**: la ruta `GET /widgets/{wid}/widget.js`
(`widgets/server_api.py`) usaba `FileResponse` sin ninguna cabecera `Cache-Control`, a diferencia de
`frontend/` (que sí manda `no-cache` explícito, ver `server/__init__.py`, puesto ahí para este MISMO problema).
Encima, `desktop.js` carga el módulo con `import(`/widgets/${id}/widget.js`)` **sin query de cache-busting** en
la carga inicial (solo se añade `?v=timestamp` tras un `modify` explícito) — así que cualquier navegador que ya
hubiera cacheado un widget.js podía seguir sirviéndolo indefinidamente tras cualquier edición futura del
fichero, no solo esta.

## Fix

`widgets/server_api.py::widget_js` — `FileResponse(..., headers={"Cache-Control": "no-cache"})`. Fuerza
revalidación condicional (`If-None-Match`/`If-Modified-Since`) en cada carga: barato (304 si no cambió), y
garantiza que un widget.js editado se sirva fresco sin depender de que el usuario limpie caché o de que
`desktop.js` recuerde añadir un `?v=`.

**Requiere reinicio del servidor** para tomar efecto (es código Python ya cargado en el proceso vivo, no un
asset estático) — reiniciado con `make run-duo` (mismo `BRAIN=duo` que la instancia previa), verificado con
`/api/brain` + `make test`.

## Ficheros tocados

`widgets/server_api.py`.

## Verificación

`curl -sD -` a `/widgets/results/widget.js` confirma `cache-control: no-cache` en la respuesta. Playwright
(browser context nuevo) confirma `results` ya renderiza correctamente en dark tras el reinicio.
