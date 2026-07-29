---
id: INI-006
title: "Audit Remediation — Parte 1: Core & Arquitectura (2026-07-02)"
status: done
owner: ricart
modules: [brains, widgets, voice, server, config, frontend]
updated: 2026-07-03
model_note: run on Fable 5 — refactorización de core/arquitectura, sin contenido dual-use
split_note: "Parte 2 (seguridad, dual-use) → [[INI-007]], se aplica DESPUÉS sobre este árbol"
---

## Goal

**Parte 1 de 2** de la remediación de la **auditoría completa del 2026-07-02**
([[harbee-audit-2026-07-02]], ejecutada con [[zaelar-audit-workflow]]). Esta parte cubre la **refactorización de
core, arquitectura, bugs de correctitud, deriva de docs, widgets y cosmético** — todo lo que **NO** es sensible a
seguridad. La maneja **Fable 5** (el modelo más capaz) de un tirón, sin fricción de safeguards. Prioridad:
**P1 bugs de arquitectura → P2 deriva doc → P3 cosmético**, más el backlog del módulo widgets (W-1…W-6).

> **Split del operador (2026-07-02).** Todo el dominio de **seguridad** (P0 completo + SEC-3: inyección, exfil,
> XSS, DNS-rebind, tirith) se movió a **[[INI-007]] — Parte 2**, que se ejecuta en **Opus/Mythos DESPUÉS** de esta
> parte, sobre el árbol ya refactorizado. Motivo: razonar sobre vectores de ataque y redactar payloads de test
> dispara los safeguards dual-use de Fable 5 aunque el contexto sea 100% defensivo. Aquí queda **cero** contenido
> ofensivo. Ver INI-007 para S-01…S-11 (fixes + tests juntos).

Cada tarea se cierra individualmente con [[zaelar-change-protocol]] (verificar → versión → diario → commit). La
auditoría NO tocó código; todo lo de aquí requiere OK del operador antes de aplicarse.

> Estado global: **DONE (2026-07-03)** — Parte 1 completa: P1 (T-13…T-20), backlog widgets (W-1…W-6),
> P2 docs (T-21…T-29) y P3 cosmético (T-30…T-33), cada tarea cerrada con el change protocol
> (v0.8.1 → v0.9.7). Única excepción: **T-24** (state.json) ⏸ pendiente del operador — artefacto del
> daemon, se regenera onboardeando el repo desde el Architect. La Parte 2 (seguridad) sigue en [[INI-007]].

> **Reconciliación 2026-07-02 (post-commits):** entre la ejecución de la auditoría y ahora entraron commits — el
> hardening de widgets **W-001** (ver `.meshkore/modules/widgets/logs/2026-07/W-001-widget-system-hardening.md`,
> [[project-widget-system]]) y otros. Estado actualizado por tarea abajo (✅ hecho · ◐ parcial · ⬜ pendiente).
> Se añade el **backlog del módulo widgets** (sección propia al final) alineado con los invariantes decididos:
> (a) un widget nunca rompe el sistema · (b) storage independiente por widget · (c) comms mediadas por el brain ·
> (d) JS sin build + data.py stdlib. Descartados por el operador (NO incluir): bus de eventos, store compartido,
> frameworks JS con build.

---

## P0 — Seguridad → movido a Parte 2 ([[INI-007]])

> Los hallazgos T-01…T-11 (fence de handles V1/V2, exfil por media V3, XSS agenda SEC-1, guard `/status` V4,
> DNS-rebind V5, redacción inbound V6, endurecimientos V7/V8/V9, tirith V10, tests) se aplican en **INI-007** sobre
> Opus/Mythos, tras esta parte. **No implementar aquí.** (T-05/SEC-2 XSS en `search` ya quedó ✅ resuelto por W-001.)

## P1 — Bugs de arquitectura / correctitud

> **T-12 · SEC-3** (validación estática de reglas de la casa en el generador) → movido a **Parte 2 ([[INI-007]] S-10)**
> por ser seguridad (anti-XSS/exfil en widgets generados). No implementar aquí.

- [x] **T-13 · A1 ✅ (2026-07-02, diario `brains/logs/2026-07/T-13`) — `/api/hermes/update` debe reiniciar el agente compartido.** `update_api.py:90-91` no llama
  `runtime.shutdown_shared()` → sigue el binario viejo tras "✓"; y `_acp_healthcheck` (:52-66) arranca un 2º Hermes
  concurrente. Fix: `shutdown_shared()` antes de `hermes update`; que el healthcheck sea el arranque nuevo.
- [x] **T-14 · A2 ✅ (2026-07-02, diario `voice/logs/2026-07/T-14`) — evitar el stall del event loop en el primer connect.** `voice/agent.py:167` `get_shared_acp()`
  bloqueante en el loop. Fix: `await asyncio.to_thread(get_shared_acp)`.
- [x] **T-15 · A3 ✅ (2026-07-02, diario `config/logs/2026-07/T-15`) — `set_brain_model` gate + sanitización.** `config/settings.py:93-104,178-180`: gate a
  `active_brain()=="hermes"` y validar charset del modelo (evitar corromper `config.yaml` / inyección vía `/api/settings`).
- [x] **T-16 · A4 ✅ (2026-07-02, diario `config/logs/2026-07/T-16`) — quitar razonadores del ⚙ panel de cerebro de voz.** `config/settings.py:40-41` (GLM top) +
  `voice_api.py:209` (default `zhipu/glm-5-2`). Fix: curar solo no-razonadores validados; razonadores tras aviso.
- [x] **T-17 · BUG-1 ✅ (cerrado vía W-1, 2026-07-02) — `view_data()` fuera del event loop → ver W-1 (widgets-P0).** Sigue vivo:
  `widgets/server_api.py:65` ejecuta `view_data()`/`apply_action()` SÍNCRONO en el loop de voz (solo `/generate`
  y `/modify` usan `run_in_executor`). **Elevado a P0 del módulo widgets** con requisito más fuerte que un simple
  `run_in_executor` — ver **W-1** abajo (timeout duro + respuesta degradada; materializa el invariante (a)).
- [x] **T-18 · A5 ✅ (2026-07-02, diario `brains/logs/2026-07/T-18`) — registro de tasks para tags cluster/cron.** `llm_processor.py:119,127` fire-and-forget. Fix: set de tasks / `ensure_future` en registro.
- [x] **T-19 · A6/A7/A8 ✅ (2026-07-02, diario `voice/logs/2026-07/T-19`) — bugs menores:** `voice/llm.py:15` path de `.env`; `/api/doc/{name}` apuntar a `.meshkore/docs/`
  o borrar endpoint+llamada; fetch TURN fuera de import (`voice_api.py:78`); `await proc.wait()` en `cron.py:56-61`.
- [x] **T-20 ✅ (2026-07-02, diario `widgets/logs/2026-07/T-20`) · Auditar `widgets/cluster-informe/`** (widget nuevo aparecido tras el fan-out): contrato + XSS + data.py. *(Nota: `cluster-informe/` era debris ya limpiado por W-001; el widget vivo auditado es `cluster-registro/` — contrato OK, textContent OK, data.py stdlib OK; único fix: import sin uso.)*

## P2 — Deriva doc ↔ código (empezar por la página servida)

- [x] **T-21 · D1 ✅ (2026-07-03, diario `frontend/logs/2026-07/T-21`) — reescribir la página servida `/architecture`** (`frontend/pages/architecture.html`): rutas
  post-restructura, modelo deepseek, arreglar/quitar pestaña Context (+`server/pages.py`), añadir connectors/meshkore,
  sección seguridad, brains pluggability + self-update, ChatWall, importers/harness, caja cluster en el diagrama, STT MLX/faster-whisper.
- [x] **T-22 · D2 ✅ (2026-07-03, quitado de cluster.yaml/modules.md/CLAUDE.md/architecture.html — no hay código) — resolver `importers/` fantasma:** crear el dir o quitar de `cluster.yaml:31-33`+`modules.md:18`+CLAUDE.md.
- [x] **T-23 · D3 ✅ (2026-07-03, resuelto por la realidad: ambos ya no existen; el sucesor `cluster-registro/` está commiteado y auditado en T-20) — commitear `widgets/conexiones/` + `widgets/cluster-informe/`** (anclar INI-005) o borrar si abandonados.
- [ ] **T-24 · D4 ⏸ PENDIENTE DEL OPERADOR (artefacto del daemon compartido; regenerar onboardeando el repo desde el Architect — sin vía local) — regenerar `state.json`** vía daemon (NO editar a mano): faltan INI-003/004/005; ids `brain`/`hermes` obsoletos.
- [x] **T-25 · D5 ✅ (2026-07-03) — barrido de nombre de modelo** gpt-4.1 → `deepseek/deepseek-v4-flash` (actual; gpt-4.1 = ejemplo
  validado): `zaelar-ops.md`, `zaelar-product.md`, `zaelar-architecture.md`, `zaelar-deploy.md`, `.env.example:38`, `CLAUDE.md:80`.
  (Actualizar también la memoria [[project-model-costs]] si procede.)
- [x] **T-26 · D6 ✅ (2026-07-03) — `zaelar-change-protocol.md:59`** quitar "no hay remote" (origin existe).
- [x] **T-27 · D7 ✅ (2026-07-03, 14 vars MESHKORE_* + knobs widgets + refs muertas) — `config/.env.example`** añadir las 14 vars `MESHKORE_*`; arreglar refs `docs/SETUP.md`, `brain/tts/`.
- [x] **T-28 · D8/D9/D10 ✅ (2026-07-03) — claims desfasadas:** "cero cross-imports" (`product.md §2`) → "solo bridges guarded";
  añadir `status.js`/`CronPanel`/`Notice`/`StatusPanel` a `modules.md:47,49`; "one warm acp per connection"→process-wide;
  "cron via gateway launchd"→ticker in-process; orden del pipeline (+EchoSuppressor/ClientTextInjector); UI debe consultar `/api/brain`.
- [x] **T-29 · D11 ✅ (2026-07-03) — `zaelar-audit.md`** marcar histórico; `conventions.md` trailer vs `Co-Authored-By`; `INI-001` paths
  muertos; `make test-hermes` (implementar o relabelar como entregado por `make hermes-check`).

## P3 — Cosmético / housekeeping

- [x] **T-30 ✅ (2026-07-03, diario `voice/logs/2026-07/T-30-33`) — borrar dirs vacíos** `voice/brains/` y `voice/logs/` (restos de la restructura).
- [x] **T-31 ✅ (2026-07-03; `reset_session_state` se documenta como no-op deliberado, tiene callers) — dead code:** `voice/tts/__init__.py:43-47`+`S2S`; `server/common.py:18-19 page()`; `server/state.py:5-6` no-op.
- [x] **T-32 ✅ (2026-07-03) — docstrings obsoletos:** `voice/agent.py:1-6,39`; `voice/silence.py`; `Makefile:1` comentario + `.PHONY` (add run-hermes/sim-hermes).
- [x] **T-33 ✅ (2026-07-03, evaluado y DIFERIDO a propósito — volumen actual no lo justifica y bufferizar arriesga perder eventos en crash) — `voice/observer.py:84-91`** batch de logs si sube el volumen de eventos (no urgente).

---

## Módulo widgets — backlog de mejora (pre-audit W-001)

Arquitectura de widgets **VALIDADA, no rediseñar** (una carpeta autónoma por widget: manifest.json + widget.js
ES-module sin build + data.py stdlib-only + notes.md; catálogo auto-descubierto; Hermes DECIDE vía
`[[create:id]]spec[[/create]]`, un Claude Code headless PROGRAMA vía `generator.py`; resultado async al brain como
nota `[SISTEMA]` en `voice/brain_notes.py`). Mejoras acordadas, en orden de prioridad:

- [x] **W-1 (P0) ✅ (2026-07-02, diario `widgets/logs/2026-07/W-002`) — aislar la ejecución de `data.py` del proceso del servidor.** Hoy `server_api.py:65` importa y
  ejecuta `view_data()`/`apply_action()` SÍNCRONO en el mismo proceso/event-loop que la voz: un widget lento (fetch
  6s) o con bucle infinito **bloquea el pipeline de voz entero**, y "stdlib-only" es convención, no enforcement.
  Objetivo: ejecutar `data.py` FUERA del hot path — **mínimo** threadpool con **timeout duro**; **ideal** subprocess
  pool con límite CPU/mem — devolviendo `{"error": …}` (respuesta degradada) al vencer el timeout. Materializa el
  invariante (a). *(Reemplaza y amplía T-17.)*
- [x] **W-2 (P1) ✅ (2026-07-02, diario `widgets/logs/2026-07/W-003`) — ciclo de vida completo por voz: `[[delete:id]]`.** Hoy solo hay create/modify/show/close
  (`voice/tag_protocol.py`). Añadir el tag `delete` + su ruta, y al borrar un widget **borrar también su
  `widgets/_data/<id>.json`** huérfano (`store.py`). Respeta el invariante (b).
- [x] **W-3 (P1) ✅ (2026-07-02, diario `widgets/logs/2026-07/W-004`) — progreso de generación audible.** Los ~84s de `claude -p` (`generator.py`) solo muestran spinner:
  emitir notas de progreso intermedias (`voice/proactive` / notice) para que el operador sepa que sigue vivo, y
  **sobrevivir reinicios del server** (generación en curso → re-lanzar o reportar fallo al arrancar).
- [x] **W-4 (P2) ✅ (2026-07-02, diario `widgets/logs/2026-07/W-005`) — anti-colisión de keywords en `_validate()`.** Rechazar/avisar si el manifest nuevo pisa keywords
  de otro widget del catálogo (hoy solo lo pide la prosa de `AGENTS.md`, sin enforcement). *(Relacionado con T-12.)*
- [x] **W-5 (P2) ✅ (2026-07-03, diario `widgets/logs/2026-07/W-006`; tier léxico-semántico stdlib implementado, plan de embeddings documentado en modules.md) — evolución de `identify()` a matching semántico.** `runtime.py identify()` hace matching por
  keywords: suficiente para decenas, débil para el objetivo de **miles** de widgets. Plan: embeddings locales o
  índice semántico, manteniendo el catálogo como fuente de verdad.
- [x] **W-6 (P3) ✅ (2026-07-03, diario `widgets/logs/2026-07/W-007`; `make test-widgets`) — versionado del store + harness por widget.** Campo `_v` en el store por widget + migración
  perezosa en `data.py`; y un harness mínimo por widget (`view_data()` dorada + smoke de render en CI local).

> **Fuera de alcance (descartado por el operador):** bus de eventos entre widgets, store compartido, frameworks JS
> con build. Los widgets son **tontos y aislados**; el brain es el único orquestador (invariante c).

---

## Notas de ejecución
- **Seguridad → Parte 2:** todo el dominio de seguridad (P0 + SEC-3) vive en [[INI-007]] y se aplica en Opus/Mythos
  DESPUÉS de esta parte, sobre el árbol ya refactorizado. Aquí NO se toca nada de seguridad.
- **Empezar por W-1** (aislar `data.py` fuera del event loop con timeout duro + respuesta degradada): protege el
  pipeline de voz y es la prioridad real del módulo widgets. Luego W-2..W-6. No reabrir los invariantes (a-d).
- **La página `/architecture` (T-21) es user-facing** — máxima prioridad dentro de P2.
- Antes de aplicar cada tarea, re-verificar que el hallazgo sigue vivo en el código actual (el árbol se movió tras
  la auditoría). Marcar `[x]` al cerrar.
- Al aplicar, actualizar `status:` de esta iniciativa (`proposed`→`in-progress`→`done`) y el diario por módulo tocado.
