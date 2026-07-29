---
id: W-007
title: "W-6 · versionado del store (_v + migración perezosa) + harness mínimo por widget"
status: done
priority: medium
owner: ricart
initiative: INI-006
created: 2026-07-03
updated: 2026-07-03
---

# W-007 — Versionado del store + harness por widget (INI-006 · W-6)

## Qué se hizo

1. **Versionado del store** (`widgets/store.py`): `store.load(id, seed, version=N, migrate=fn)` — el store guarda
   el esquema en el campo reservado `_v` y, si el fichero trae una versión anterior, llama `migrate(db, from_v)`
   **perezosamente en la lectura** (sin scripts de migración: los datos viejos se actualizan la primera vez que
   el código nuevo los lee). Una migración rota degrada al seed (nunca lanza). 100% retrocompatible: `load(id,
   default)` sin `version` se comporta exactamente igual que antes. `widgets/agenda/data.py` adopta el patrón
   como referencia (`DB_VERSION = 1` + `_migrate`), y `AGENTS.md` lo enseña a los agentes generadores.

2. **Harness por widget** (`widgets/harness.py`, `make test-widgets`): tres checks locales y rápidos por widget —
   - **contract**: la misma puerta que la generación (`generator._validate`: manifest + `export function render`
     + data.py compila + `view_data()` corre y devuelve dict + anti-colisión de keywords);
   - **golden**: la **forma** de `view_data()` (claves top-level → tipos) contra `widgets/<id>/golden.json`
     (se auto-graba la primera vez; los datos vivos cambian, la estructura no debe — clave desaparecida o tipo
     cambiado = la regresión típica de un modify descuidado);
   - **render**: `widget.js` parsea como módulo ES (`node --input-type=module --check`; se salta si no hay node).

## Ficheros tocados

- `widgets/store.py` — `load()` con `version`/`migrate` (+`_v`).
- `widgets/harness.py` — nuevo runner (`python -m widgets.harness [ids…]`).
- `widgets/agenda/data.py` — `DB_VERSION`/`_migrate` de referencia.
- `widgets/*/golden.json` — snapshots iniciales de los 7 widgets.
- `widgets/AGENTS.md` — patrón de versionado + nota del harness + regla de keywords con enforcement.
- `Makefile` — target `test-widgets` (+ help + .PHONY).

## Verificación

- Test dirigido (scratchpad `test_w6.py`): migración v0→v2 corre exactamente una vez y `_v` queda registrado;
  migración rota degrada al seed; `load` sin versión intacto; drift de golden detectado ("missing keys ['b'];
  retyped a:int→str"); widget.js roto detectado por el parse de node.
- `make test-widgets` → 7 widgets, 0 checks fallando. Servidor reiniciado sano; `agenda` sirve datos con el
  store versionado (`_v=1`).
