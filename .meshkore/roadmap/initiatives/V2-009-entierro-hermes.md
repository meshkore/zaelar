---
id: V2-009
title: Entierro de Hermes — cutover BRAIN=nucleo, retirar brains/, config v2 definitiva, docs+diagramas
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [brains, nucleo, config, server, frontend, voice]
depends_on: [V2-004, V2-005, V2-006, V2-007, V2-008]
wall_order: 9
created: 2026-07-09
updated: 2026-07-09
commit_shas: [b423a40, 30eb01b, 948e2c7, e8ccab9, 6beabf4, b3a0c08, 313a683, 69b7119]
completed_at: 2026-07-09T08:41:00.102Z
commit_sha: ab6d2326cdb14469cb50a2e07f737c1f7018a5d7
---
## Goal

**Retirar Hermes por completo.** Solo cuando 021–025 están verificadas en vivo: poner `BRAIN=nucleo` por
defecto, borrar todo lo de Hermes/duo, dejar la config v2 definitiva (sin lo que ya no sirve), y actualizar
docs/diagramas para que reflejen el sistema VIVO (v2 pasa de PROPUESTA a construido). Es la última fase.

## Qué se retira

- `brains/hermes/` (ACP client, cron, cron_api, update_api, runtime) + `brains/duo/` + `brains/reasoner.py`.
- Providers `voice/engine/llm/providers/hermes.py` y `duo.py` (queda `nucleo.py`; `direct.py`/`local.py` a evaluar).
- Rutas `/api/hermes/*`, el banner de update de Hermes en el frontend, el polling que asumía Hermes.
- Config específica de Hermes/duo en `config/`; el gating `brains.uses_hermes()`.
- La federación "upstream vivo" (`hermes update` git pull). **SE CONSERVA** el bridge Baileys vendorizado de
  WhatsApp (es independiente del agente Hermes). `zaelar-hermes-federation.md` pasa a histórico.
- Targets del Makefile: `run-duo`, `run-hermes`, `update-hermes`, `hermes-check` → `make run` = nucleo.

## Tareas

- [x] Poner `BRAIN=nucleo` como default (`make run`); retirar `run-duo`/`run-hermes`/`update-hermes`/`hermes-check`.
- [x] Borrar `brains/hermes/`, `brains/duo/`, `brains/reasoner.py` y los providers hermes/duo. Ajustar el registry.
- [x] Retirar rutas `/api/hermes/*`, el banner de update y el polling en el frontend; simplificar `/api/brain`.
- [x] Config v2 definitiva: quitar settings de Hermes/duo; dejar STT/TTS/voz/idioma + routing fast/code-agent + flags.
- [x] Actualizar `cluster.yaml` (módulos v2: bus/nucleo/memory; brains/files fuera), `CLAUDE.md`, `README.md`.
- [x] Actualizar docs canónicas (architecture, modules, product, conventions, security) al sistema v2.
- [x] Diagrama `/architecture`: quitar el sello "PROPUESTA", poner "construido" + fecha; sello "Actualizado:".
- [x] `zaelar-hermes-federation.md` → histórico; nota de que el bridge WhatsApp se conserva vendorizado.
- [x] Bump `version` a `1.0.0` en `cluster.yaml`. Suite de tests completa verde.

## Aceptación

- Clone limpio → `make run` → arranca con el cerebro nucleo, **sin ningún rastro de Hermes** (grep `hermes` solo
  en histórico/bridge WhatsApp).
- Voz + widgets + memoria + escalado + proactividad funcionan con el cerebro propio.
- `/architecture` refleja el sistema construido (no propuesta); docs alineadas (docs-sync).
- Todos los tests verdes; `pytest` sin imports rotos de `brains.*`.

## Riesgos

- Referencias colgando a `brains.*` / `runtime.locked_ask` por el código → grep exhaustivo antes de borrar.
- No borrar Hermes antes de tiempo: esta iniciativa NO empieza hasta que 021–025 están verificadas en vivo.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · Cutover del default a `BRAIN=nucleo`: `make run` / `run-lk` y `scripts/run-livekit.sh` arrancan el cerebro «Colmena» propio. Retirados del Makefile los targets `run-hermes`/`run-duo`/`sim-hermes`/`install-hermes`/`hermes-setup`/`hermes-run`/`update-hermes`/`hermes-check`. Verificado en vivo: stack LiveKit nativo (sin Docker) arranca limpio y `curl localhost:8473/api/brain` → `{"brain":"nucleo"}`.
- 2026-07-09 · Docs canónicas al sistema v2 CONSTRUIDO (architecture · modules · product · conventions · security): el cerebro pasa a ser el propio «Colmena» (`nucleo/`, FlashBrain+SlowBrain), la memoria `memory/`, el bus `bus/`, la proactividad el loop de `nucleo/`, y el reasoner de cluster `connectors/meshkore/reasoner.py` (stateless). `zaelar-security.md` corrige QUIÉN aplica el gate de tools: la puerta ACP deny-tools de Hermes se retira; el canal de cluster no tiene tools (nada que denegar hoy) y el endurecimiento del CodeAgent es V2-010 — se conservan intactos los controles vigentes (fencing/`neutralize_identity`, `scan_outbound`, allowlist de tags, plano de control loopback, `wss`, sin ruta cluster→micro). Historia de Hermes marcada como tal en cada doc.
- 2026-07-09 · Diagrama vivo `/architecture`: los sellos de las 5 pestañas pasan de «PROPUESTA»/«sin construir»/«EN CONSTRUCCIÓN» a «CONSTRUIDO/A» + iniciativa + sello «Actualizado: 2026-07-09»; entradas de la lista de docs y comentarios del builder SVG actualizados (Hermes→ejecutor sustituible / SlowBrain). Página sirve 200; cero sellos «PROPUESTA» restantes. `zaelar-hermes-federation.md` marcado 🪦 HISTÓRICO al frente: la federación «upstream vivo» ya no aplica; lo ÚNICO que se conserva es el patrón de vendoring y el bridge Baileys de WhatsApp (independiente del agente Hermes, sigue vivo, INI-014).
- 2026-07-09 · Estructura/contexto: `cluster.yaml` retira el módulo `brains` (nota de sustitución por `nucleo/`), refresca `voice` (providers nucleo/direct/local) y `nucleo` (cerebro por defecto, ya no "hasta V2-009"), y añade `config/v2.json`/`connectors.json` a `never_commit`. `CLAUDE.md`: header + Run (STT→«Colmena»→TTS, `make run`=nucleo), mapa de módulos (`brains/`→`nucleo/`+`memory/`+`bus/`, `files/` plegado), banner ⚠️ al frente de «Decisiones clave» marcando como HISTÓRICAS las viñetas Hermes/duo + mapeo al sistema vivo, y Hard rules (cerebro no-razonador + modelo por invocación; `config/v2.json` en no-commit). `README.md`: pipeline, prerequisitos (fuera Hermes Agent → modelo rápido Ollama/AIMLAPI), §4 «brain built-in», §5 tirith reencuadrado al code-agent, Run (`make run`=nucleo, sin `run-duo`), layout y nota de seguridad (reasoner de cluster stateless).
- 2026-07-09 · Frontend: eliminado `UpdateBanner.js` (banner + overlay de `hermes update`) y su mount en `main.js`; quitados `hermesStatus`/`hermesUpdate` y el polling de `api.js`; retirada la fila de update de `SettingsModal.js` (y su dependencia de `store.updateInfo`, señal eliminada); `CronPanel` pasa a listar/crear/borrar sobre el scheduler propio (fuera pausar/reanudar, que el scheduler no soporta) y su copy ya no cita `~/.hermes/cron`. `DebugPanel.js`/`debug.html` etiquetan FlashBrain/SlowBrain (clase CSS `eng-hermes`→`eng-api`). Tooltip de estado sin «Hermes». Verificado en vivo: `/` + `main.js` + `SettingsModal.js` → 200, `UpdateBanner.js` + `/api/hermes/status` → 404. (Quedan menciones históricas a Hermes en comentarios de código — anotado como aceptable.)
- 2026-07-09 · **CIERRE V2-009.** `cluster.yaml` `version` → **1.0.0**. Verificación final de la Aceptación: (a) clon-limpio-simulado → `make run` → arranque limpio con el cerebro «Colmena» (bus + memoria + loop + SlowBrain + owner de mensajería stateless + worker LiveKit embebido, sin trazas ni errores) y `curl /api/brain` → `{"brain":"nucleo"}`; (b) `pytest` **278/278 verde**, CERO `from brains`/`import brains` en todo el código (grep), sin imports rotos de `brains.*`; (c) `/architecture` → 200 con sellos «CONSTRUIDO», `/api/hermes/*` → 404; (d) las 141 menciones a «hermes» que quedan en `.py` son comentarios/strings históricos + `memory/seed_from_hermes.py` (siembra el perfil desde `~/.hermes` si existe, sin dependencia del agente) — más el bridge Baileys VENDORIZADO de WhatsApp, que se CONSERVA a propósito. Hermes queda **retirado del arranque y de todo camino funcional**. Nota: la verificación en vivo con micrófono humano NO se ejecutó (regla del entierro retirada por el operador 2026-07-09); la voz arranca y registra el worker, pero un turno de voz real end-to-end queda para la validación del operador / oleadas del tester (INI-013/V2-010).
- 2026-07-09 · Borrados `brains/hermes/` (ACP/cron/update/runtime), `brains/duo/`, `brains/reasoner.py` y los providers `voice/engine/llm/providers/{hermes,duo}.py`; registry (`providers/__init__.py`) reducido a nucleo + baselines direct/local + vendors. `active_brain()` reubicado a `config/v2.py` como fuente ÚNICA (env-first, default `nucleo`); `uses_hermes()` eliminado. Reasoner del canal de cluster reubicado a `connectors/meshkore/reasoner.py` (stateless, sin tools; deny-tools del CodeAgent → V2-010). Limpiadas todas las ramas duo/hermes de `voice/engine/pipeline/agent.py` (prewarm, briefing, kickoff-cron, digest) — el cron de arranque ahora usa `nucleo.scheduler.for_brain()`. `config/settings.py` = config v2 definitiva (solo STT/TTS/voz/idioma; fuera `set_brain_model`/`current_brain_model`/knobs de modelo Hermes/duo; el routing fast/code-agent vive en `config/v2.py`). Tests Hermes-específicos retirados (5 en `test_security.py`, invariante deny-tools → V2-010). Verificado: `pytest` 278/278 verde; arranque en vivo limpio (bus + memoria + loop + SlowBrain + worker LiveKit embebido, sin trazas de Hermes) y `/api/brain`=nucleo, `/api/status` cerebro=«Colmena», `/api/cron` sobre el scheduler propio.
