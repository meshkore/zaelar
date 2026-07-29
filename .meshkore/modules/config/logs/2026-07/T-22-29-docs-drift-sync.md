---
id: T-22-29
title: "T-22…T-29 · sincronización de deriva docs ↔ código (P2 de INI-006)"
status: done
priority: medium
owner: ricart
initiative: INI-006
created: 2026-07-03
updated: 2026-07-03
---

# T-22…T-29 — Deriva doc ↔ código (INI-006 · P2, tras T-21)

## Qué se hizo, tarea a tarea

- **T-22 · importers/ fantasma** — no existe código de importadores en ninguna parte del repo. Eliminado el
  módulo declarado de `cluster.yaml`, `zaelar-modules.md`, `CLAUDE.md`, la página `/architecture` y el
  scaffolding vacío `.meshkore/modules/importers/`. Cuando los importadores existan, se re-declaran.
- **T-23 · widgets sin commitear** — resuelto por la realidad: `conexiones/` y `cluster-informe/` ya no existen
  (`cluster-informe` era debris limpiado por W-001); el sucesor vivo `cluster-registro/` está commiteado y
  auditado (T-20). Nada que hacer.
- **T-24 · state.json** — **pendiente del operador**: es artefacto del daemon compartido (daemon.meshkore.com)
  y se regenera onboardeando el repo desde el front del Architect; no hay vía local y la regla dura prohíbe
  editarlo a mano. Está desfasado (faltan INI-003…007; ids `brain`/`hermes`/`importers` obsoletos).
- **T-25 · barrido de modelo** — `gpt-4.1` → `deepseek/deepseek-v4-flash` como modelo ACTUAL en `CLAUDE.md`,
  `config/.env.example` (`LLM_MODEL`/`ASSISTANT_LLM_MODEL` + prosa), `zaelar-ops.md`, `zaelar-product.md`,
  `zaelar-notes.md`, `zaelar-architecture.md`, `zaelar-deploy.md`. Las menciones de la validación 2026-06-29
  conservan gpt-4.1 como **ejemplo validado histórico** (es el experimento que fijó la regla).
- **T-26 · change-protocol** — quitado "no hay remote configurado"; documentado `origin`
  (github.com:meshkore/zaelar) con push solo bajo OK del operador.
- **T-27 · .env.example** — añadido el bloque `MESHKORE_*` completo (14 vars reales del código, con la postura
  strict/fail-closed anotada) y los knobs nuevos de widgets (`WIDGETS_DATA_TIMEOUT`, `WIDGETS_PROGRESS_SECS`);
  arregladas refs muertas: `docs/SETUP.md` → README + zaelar-ops, `brain/tts/` → `voice/tts/`,
  `docs/hermes-MEMORY.seed.md` → `.meshkore/docs/ops/hermes-MEMORY.seed.md`.
- **T-28 · claims desfasadas** — `product.md`: "zero cross-imports" → bridges guarded (brief/brain_notes/
  proactive) + data.py off-loop; "one warm acp per connection" → UN agente caliente POR PROCESO compartido
  (runtime + turn_lock); "Hermes gateway (cron) launchd" → ticker in-process (`hermes cron tick`) ×2; orden
  real del pipeline (+EchoSuppressor OFF, ClientSTTInjector, ClientTextInjector, assistant-agg).
  `modules.md`: añadidos `status.js` (services) y `StatusPanel · CronPanel · Notice` (components).
- **T-29 · varios** — `zaelar-audit.md` (2026-06-27) marcado **HISTÓRICO** con banner (paths/claims del árbol
  antiguo; foto vigente en la auditoría 2026-07-02); `conventions.md` trailer `Agent:/Model:/MeshKore-Version:`
  → la práctica real `Co-Authored-By: Claude …`; `INI-001` paths muertos (`voice/hermes_*` → `brains/hermes/*`,
  `brain/llm.py` → `voice/llm.py`); `make test-hermes` (inexistente) relabelado — el contract-check ACP es
  `make hermes-check` y el update lo re-corre post-update; el "Next: identify()" de product.md marcado DONE.

## Verificación

- `cluster.yaml` parsea y declara los 8 módulos reales (sin importers).
- `grep gpt-4.1` sobre CLAUDE.md + .env.example + docs canónicos: solo quedan menciones marcadas como ejemplo
  validado / histórico (y el informe de auditoría, que es un registro fechado).
- Servidor vivo sano tras los cambios (`/api/brain` → hermes).
