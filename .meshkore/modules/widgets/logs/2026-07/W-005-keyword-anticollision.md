---
id: W-005
title: "W-4 · anti-colisión de keywords con enforcement en _validate()"
status: done
priority: medium
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# W-005 — Anti-colisión de keywords (INI-006 · W-4)

## Qué se hizo

`widgets/AGENTS.md` pedía keywords "precisas y no solapadas" pero era solo prosa: un widget generado podía
copiar las keywords de otro y **usurpar su identidad** en `identify()` (o quedar inidentificable). Enforcement
añadido en `generator._validate()`:

- **`_keyword_collisions(wid, keywords)`**: mapa keyword → widgets del catálogo que ya la usan
  (case-insensitive, excluye al propio wid).
- **Colisión total** (todas las keywords ya tienen dueño) → **rechazo** de la validación con error claro
  (en create se descarta el folder; en modify hace rollback — mecanismos ya existentes).
- **Colisión parcial** → **pasa con warning** logueado (lista keyword → dueños). No se recortan las keywords:
  `identify()` ya desambigua con candidatos, y recortar regresaría el recall de widgets antiguos (hay solapes
  legítimos preexistentes: meteo-soria/meteo-tarragona «previsión», agenda/meteo «hoy»).

## Ficheros tocados

- `widgets/generator.py` — `_keyword_collisions()` + gate en `_validate()`.

## Verificación

- Test dirigido (scratchpad `test_w4.py`): manifest que copia íntegras las keywords de `agenda` → rechazado
  ("would be unidentifiable"); solape parcial → pasa y loguea la colisión con sus dueños; keywords únicas →
  pasa limpio sin warning.
- `make run-hermes` sano tras el cambio.
