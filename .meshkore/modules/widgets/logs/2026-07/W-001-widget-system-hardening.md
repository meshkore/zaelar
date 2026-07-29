---
id: W-001
title: "Widget system — auditoría + hardening (feedback loop, aislamiento, anti-debris)"
status: done
priority: high
owner: ricart
initiative: INI-002
created: 2026-07-02
updated: 2026-07-02
---

# W-001 — Auditoría y hardening del sistema de widgets

## Síntoma (reportado)

El operador pidió por voz un widget que capturase el chat del cluster para storage permanente. En los logs
(`.meshkore/logs/sessions/20260701-210526.jsonl` i=277 y `…-210922.jsonl` i=56): el brain emitió
`[[create:cluster-registro]]` con buen spec, dijo **"Hecho"** al instante, pero el widget **nunca aterrizó**;
en la sesión siguiente emitió `[[show:cluster-chat]]` — un id **alucinado** que ni estaba en su brief. Percepción:
"no funciona / me muestra un widget que no es".

## Causa raíz (tres, ninguna era la reestructuración)

1. **Create fire-and-forget sin feedback.** Generar tarda ~84s (headless `claude -p`); el `[[create]]` no devuelve
   nada al brain, que canta "Hecho" a ciegas y luego referencia ids fantasma. Un reinicio de server a media
   generación mató el job → sin widget.
2. **Debris en el catálogo.** Una generación anterior muerta a medias dejó `widgets/cluster-informe/` con
   `manifest.json` pero **sin `widget.js`**. El manifest bastaba para entrar al catálogo y al brief de Hermes, pero
   al mostrarlo no renderizaba → "no funcionó". El `_validate` viejo no borraba folders fallidos.
3. **Validación floja.** `_validate` solo comprobaba compilación de `data.py`, no ejecutaba `view_data()`.

## Qué se hizo

- **Bucle de feedback create/modify → brain.** Nueva cola process-level `voice/brain_notes.py` (one-shot,
  thread-safe, acotada); el brain adapter la drena y **prepende** al siguiente prompt. Los endpoints
  `/widgets/{generate,modify}` empujan el resultado real: éxito → nota silenciosa con el id exacto; fallo → nota +
  `voice.proactive.notify` (voz+UI inmediata). El brain deja de mentir y de inventar ids.
- **Brief:** enseñado que crear/modificar es asíncrono (no decir "hecho"; esperar la nota `[SISTEMA]`) y usar SOLO
  ids exactos del catálogo/confirmación (`widgets/brief.py`).
- **Store enseñado al generador.** El contrato (`generator.py`) y `widgets/AGENTS.md` ahora documentan la
  persistencia (store aislado por widget), los tiers de storage y el modelo de comunicación mediada por el brain.
- **Anti-debris (invariante "un widget no rompe el resto"):**
  - `_validate` ejecuta `view_data(q="")` (smoke-test runtime): un widget que peta no entra al catálogo.
  - Create fallido **borra** el folder parcial (`generator._discard`); modify ya tenía rollback.
  - `runtime.catalog()` exige `widget.js` presente → un folder roto es invisible al brain y al canvas.
- **Limpieza:** borrados `widgets/cluster-informe/` (roto) y `widgets/conexiones/` (válido, descartado por el
  operador). Creado y validado `widgets/cluster-registro/` (el que se pidió; lee `kind==cluster` de los logs).

## Decisiones (versión ideal, aprobadas por el operador)

- **Storage INDEPENDIENTE por widget** (`widgets/_data/<id>.json`), NO un store compartido en Hermes — el
  aislamiento manda: un widget solo puede corromper su propio estado. (Contra la dirección pure-frontend de INI-003;
  se mantiene full-stack por-widget de momento.)
- **Comunicación mediada por el brain**: widgets tontos, Hermes orquesta.
- **JS sin build + `data.py` stdlib-only**: se mantiene (ideal para tarjetas, seguro, portable).

## Ficheros tocados

- `voice/brain_notes.py` (nuevo) · `brains/hermes/llm_processor.py` (drena+inyecta notas)
- `widgets/server_api.py` (`_report_to_brain` en generate/modify)
- `widgets/generator.py` (contrato: store/comms · smoke-test view_data · `_discard`)
- `widgets/runtime.py` (catálogo exige widget.js) · `widgets/brief.py` (disciplina async + ids exactos)
- `widgets/AGENTS.md` · `.meshkore/docs/modules/zaelar-modules.md` (§Widgets, nuevo) · `CLAUDE.md` (decisión)
- Borrados: `widgets/cluster-informe/`, `widgets/conexiones/` · Añadido: `widgets/cluster-registro/`

## Verificación

- `make test` → `OK zaelar imports + prompt`. Server reiniciado (`make run-hermes`): `Hermes ACP v0.17.0`,
  `shared agent ready`, catálogo por HTTP = 7 widgets válidos + `cluster-registro`, sin debris.
- Smoke-tests dirigidos: `_validate` acepta widgets buenos y **rechaza** uno cuyo `view_data` lanza; `brain_notes`
  push/drain y `_report_to_brain` (éxito/fallo/existed) OK; generación end-to-end reproducida (84s, validada).
