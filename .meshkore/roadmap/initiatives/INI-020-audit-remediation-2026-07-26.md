---
id: INI-020
title: Auditoría independiente 2026-07-26 — remediación
epic: v2-colmena
status: active
priority: high
owner: ricart
modules: [nucleo, connectors, widgets, memory]
depends_on: [V2-069, V2-070, V2-071, V2-075, V2-076]
wall_order: 20
created: 2026-07-26
updated: 2026-07-26
---

## Goal

Registrar el trabajo de remediación de la auditoría independiente del 2026-07-26 (informe completo:
`.meshkore/docs/architecture/zaelar-audit-2026-07-26.md`). Los hallazgos P0/P1 de fix directo se arreglaron en la
propia sesión de auditoría; el operador después dio luz verde explícita ("sigue mejorando... sin ningún riesgo,
implementado de forma limpia") para cerrar también el resto — T-01 a T-05 y T-07 se completaron en la MISMA
sesión, en incrementos propios con tests. Quedan abiertas T-06 (recordatorio, no bug) y T-08 (observación de
mantenibilidad, no bug).

## Tareas

- [x] **T-01 (P1, seguridad) — CERRADA.** Jail de filesystem REAL para el dev-worker: `nucleo/dev_worker_guard.py`
  (hook PreToolUse oficial de Claude Code, `--settings`) deniega Read/Write/Edit/MultiEdit/Glob/Grep fuera del cwd
  temporal (realpath, sigue symlinks); settings.json fuera del workdir (el worker no puede tocarlo);
  `nucleo/sandbox.py::dev_worker_rlimits()` añade rlimits de memoria/nproc/fsize (memoria best-effort en macOS,
  documentado honestamente — `RLIMIT_AS` es no-op ahí, verificado empíricamente). Limpieza de workdir+settings al
  terminar la sesión (de paso cierra la fuga de disco de T-07c). 19 tests nuevos. Commit `c44f597`.

- [x] **T-02 (P1, seguridad/producto) — CERRADA.** Tool operator-only `set_cluster_objective(cluster, peer,
  objective)` en `router.TOOLS` (mismo gate situacional que `connect_cluster`; estructuralmente inalcanzable desde
  un turno de cluster — `nucleo/flash/cluster.py` filtra su propio catálogo a solo escalate/web_search). Persiste
  vía `capsule.patch(...)`. 2 tests nuevos + cobertura ya existente de `capsule.objective`/`gate_dev_by_objective`.
  Commit `55b9ae0`.

- [x] **T-03 (P1, arquitectura) — CERRADA.** `bridge._evaluate_and_apply` da un aviso DIFERENCIADO cuando
  `health=="off_track"` (nombra el objetivo fijado o su ausencia, pide explícitamente la decisión del operador),
  en vez del aviso genérico de `dead_end`/`stuck`. 3 tests nuevos. Commit `40314d5`.

- [x] **T-04 (P2, widgets) — CERRADA (diferenciados, NO fusionados).** `ejecuta-gestion-real` = gestión de
  agentes ya conocidos + alta rápida manual; `ejecuta-sistema-real` = flujo CANÓNICO de alta con verificación real.
  `whenToUse`/keywords ya no se solapan; cross-referenciados en manifest+notes. Fusión de stores queda para si el
  operador la pide explícitamente (riesgo de pérdida de datos). Commit `a2e533a`.

- [x] **T-05 (P2, docs) — CERRADA.** Los 5 workflows de `.meshkore/docs/ops/` ya apuntan a
  `web/src/pages/technology/*.astro` + `web/src/lib/diagrams/*.ts` en vez de `architecture.html` (retirado
  2026-07-24); las menciones que quedan son notas históricas explícitas. `.meshkore/` no es un repo git — cambios
  solo en filesystem, sin commit propio (ver el de `CLAUDE.md` que lo referencia, `a2e533a`).

- [ ] **T-06 (P2, web).** Actualizar `web/src/lib/diagrams/architecture.ts` (nodo cluster, hoy "no tool access")
  en cuanto algún cluster real tenga un perfil de permisos V2-076 concedido — hoy es cierto (default deny-all) y
  no es una desalineación, pero será la primera cosa que quede stale. No hay workflow que lo haga automático
  (documentado en `CLAUDE.md`); recordatorio manual, no bug.

- [x] **T-07 (P3, housekeeping) — CERRADA (a, b, c, e; d dejado como está).** (a) fallback de
  `fast_client.spec_from_config()` ya no es grok (era el modelo BANEADO en el FlashBrain) sino
  `claude-haiku-4.5`, +test; (b) `security._neutralize` normaliza NFKC antes de buscar los sentinels (cierra el
  bypass por fullwidth/compatibility Unicode, sin pérdidas para texto acentuado normal), +3 tests; (c) limpieza de
  `zaelar-dev-*` cerrada como parte de T-01 (el mismo `finally` que borra el workdir); (e) `bus/__init__.py`
  docstring corregido a los topics reales. (d) permisos `execute`/`deploy` siguen sin consumirse en ningún sitio —
  dejado así a propósito (implementar esa semántica es una FEATURE nueva, no un fix de auditoría; re-auditar
  cuando se construya). Commit `5813df7`.

- [ ] **T-08 (P2, mantenibilidad, no es un bug).** `nucleo/flash/router.py` (1053 líneas) es honestamente el
  fichero más complejo del FlashBrain — no por diseño sino por guards deterministas (`looks_like_*`) acumulados
  uno a uno para parchear fallos observados del modelo rápido, cada uno con su propio comentario "BUG real
  2026-07-XX". Funciona y está bien testeado (`test_router.py`), pero es el candidato nº1 si el operador quiere
  una pasada de consolidación/simplificación. Deliberadamente NO tocado en esta ronda — un refactor de la pieza
  más crítica y compleja del FlashBrain no es un fix de "sin riesgo"; anotarlo aquí para que no se pierda la
  observación, pendiente de que el operador decida si lo quiere.

## Ya arreglado en la propia auditoría (fase P0/P1 inicial, no repetir)

Ver la tabla completa en `zaelar-audit-2026-07-26.md §Hallazgos y fixes aplicados`. Resumen: `git_cli.py`
re-verifica el repo autorizado en commit/push (`f821f6e`); guard de objetivo para el dev-worker
(`8e8fad3`); `gestiona-mensaje-recibido` ya no finge un envío real (`754e18d`); circuit breaker anti-bucle en
Susurro F2 + reactivación (`b78dd59`); `guard_code_outbound` acumulado anti-fragmentación (`bf4b63f`); 4 widgets +
`widgets/results` commiteados (`4896623`); `cluster.yaml` + docs canónicas + `CLAUDE.md` refrescados.

## Bitácora

- **2026-07-26** — Iniciativa creada al cierre de la auditoría independiente. 6 hallazgos P0/P1 arreglados con
  tests (12 tests nuevos, cero regresión).
- **2026-07-26 (mismo día, continuación autorizada por el operador)** — T-01 a T-05 y T-07(a,b,c,e) cerradas: 6
  commits más (`c44f597`, `55b9ae0`, `40314d5`, `5813df7`, `a2e533a` + docs canónicas sin commit propio por vivir
  fuera de un repo git), ~38 tests nuevos adicionales, `tests/run_testmap.py` verde en cada paso. Quedan T-06
  (recordatorio) y T-08 (observación de mantenibilidad) abiertas, ninguna es un bug de seguridad/correctitud.
