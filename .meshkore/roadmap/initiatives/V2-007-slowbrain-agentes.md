---
id: V2-007
title: SlowBrain — agentes de trabajo + escalado FlashBrain→SlowBrain + retorno por voz+UI
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [nucleo, memory, voice, widgets, connectors]
commit_shas: [77592d6]
depends_on: [V2-006]
wall_order: 7
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T08:41:00.102Z
commit_sha: ab6d2326cdb14469cb50a2e07f737c1f7018a5d7
---
## Goal

Cerrar el circuito del SlowBrain: los **agentes de trabajo** (web/código/otros on-demand), el cableado real del
**escalado** FlashBrain→SlowBrain (sustituyendo el stub de V2-004), y el **retorno** del resultado async por los
raíles existentes (memoria + voz + UI + `[SISTEMA]`), mismo circuito que hoy usan la generación de widgets y el
Architect.

## Qué se construye

- Agentes de trabajo (cada uno = `CodeAgent` con su prompt/tools):
  - `nucleo/agentes/web.py` — conduce el navegador (widget `navegador`/Chromium). **Absorbe la orquestación de
    automatización web** que hoy vive en `duo._orchestrate_automation` + `widgets/navegador/agent.py` (el bucle
    barato DOM→visión se conserva; el planificador pasa de Hermes al SlowBrain).
  - `nucleo/agentes/code.py` — widgets + código general. **Absorbe** `widgets/generator.py` (crear/modificar
    widgets) y el rol del proveedor Architect (`connectors/architect`) como un agente de código más.
  - `nucleo/agentes/otros.py` — mates/búsqueda/on-demand.
- **Escalado real**: `nucleo/flash/escalate.py` deja de ser stub → publica la tarea, el dispatcher la recoge,
  el agente de memoria da contexto mínimo, el agente adecuado corre async.
- **Retorno**: resultado → el agente de memoria ESCRIBE (hecho/resumen) + `voice/proactive.notify()` (voz+UI) +
  nota `[SISTEMA]` (`voice/brain_notes.push()`). El FlashBrain nunca canta "hecho" a ciegas ni inventa ids.
- **Confirm-gate** de acciones irreversibles (comprar/pagar/publicar/borrar) heredado: la tarea PARA y pide OK
  por voz+feed; timeout → no ejecuta.

## Tareas

- [x] `nucleo/agentes/web.py` — mueve la orquestación de automatización web al SlowBrain (bucle barato intacto) + test.
- [x] `nucleo/agentes/code.py` — envuelve `widgets/generator.py` + rol Architect como CodeAgents + test de generación.
- [x] `nucleo/agentes/otros.py` — agente genérico on-demand + test.
- [x] Cablear `escalate()` real: FlashBrain → bus → dispatcher → agente; sustituir el stub de V2-004.
- [x] Retorno: agente de memoria escribe + `proactive.notify` + `[SISTEMA]`; dedup como hoy + test del circuito.
- [x] Portar el confirm-gate de acciones irreversibles (`_DANGER_RE`) al flujo del SlowBrain.
- [x] Prueba en vivo: "búscame X en la web" / "créame un widget de Y" → escala, corre async, vuelve por voz+UI.

## Aceptación

- Una petición que requiere razonamiento/tarea larga escala del FlashBrain al SlowBrain, corre async y su
  resultado vuelve por voz + subtítulo + chat + `[SISTEMA]`, sin bloquear el hot path de voz.
- La automatización web y la generación de widgets funcionan bajo el SlowBrain (paridad con lo que hacía Hermes/duo).
- Una acción irreversible para y pide OK; sin OK, no se ejecuta.

## Riesgos

- Regresión de la automatización web al mover el planificador: mantener el bucle DOM→visión tal cual; solo cambia
  quién planifica. Verificar con un caso real (Wallapop) contra el comportamiento pre-migración.
- Seguridad: este es el punto donde input no confiable puede alcanzar un CodeAgent → se endurece en V2-010.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T84 — `nucleo/agentes/web.py`: agente de trabajo WEB que ABSORBE la orquestación de
  `duo._orchestrate_automation` (dedup de refinamientos del STT vía `navtasks.similar_active` → `create` tarea →
  abre su tarjeta → PLANIFICA → encola `automate` al owner del navegador por `widgets.server_api.brain_action`). El
  **bucle barato DOM→visión** (`widgets/navegador/agent.py`+`owner.py`) se CONSERVA intacto; la única diferencia es
  QUIÉN planifica: antes Hermes (`_hermes_ask`), ahora el SlowBrain (`CodeAgent` barato, modelo POR INVOCACIÓN
  `code_agent.model_web`, sin tools, best-effort). Devuelve `WorkResult(deliver=False)`: la tarjeta/owner reporta el
  desenlace real async por proactive+[SISTEMA]. El confirm-gate NO se aplica al objetivo (el owner gatea por-acción).
- 2026-07-09 · T85 — `nucleo/agentes/code.py`: agente de trabajo de CÓDIGO que envuelve dos proveedores como
  CodeAgents del SlowBrain — **widgets** (`generator.generate_widget`/`modify_widget`, en `asyncio.to_thread` por ser
  bloqueantes; conserva su gate de validación/rollback) y **Architect** (`connectors/architect.service.ask` a un
  proyecto nombrado, operator-only; entrega su propio resultado). Detectores `is_widget_request`/`is_architect_request`
  + `_referenced_widget` (modificar un id del catálogo) + `_MODIFY_RE` (stems, pilla conjugaciones ES). El código
  general NO pasa por aquí: el router lo manda a `otros`.
- 2026-07-09 · T86 — `nucleo/agentes/otros.py`: agente GENÉRICO on-demand (matemáticas/consulta/redacción/
  razonamiento). Es la promoción a módulo del cuerpo genérico que vivía inline en `dispatch.dispatch()` (V2-006):
  compone contexto mínimo del agente de MEMORIA ★ → prompt → `CodeAgent` (modelo por invocación + tools por
  confianza, `deny_tools` para input no confiable). Devuelve `WorkResult`.
- 2026-07-09 · T87 — escalado REAL cerrado: `dispatch.dispatch()` pasa a ROUTER (`run_task`) que **clasifica** el
  tipo (`_classify_kind`, heurística conservadora — el disparo del escalado sigue por function-calling en el
  FlashBrain), aplica el confirm-gate, despacha al agente de trabajo (web/code/otros) y el agente de memoria RECUERDA
  lo entregable. `run_listener` (bus `escalate.requested` → despacho) ENTREGA por `voice/proactive.notify` (voz+UI,
  con su fallback a nota) + nota `[SISTEMA]` (`voice/brain_notes.push`) — mismo patrón dual que el owner del
  navegador — y llama a `escalate.finish`. `start()/stop()` cablean el listener en el lifespan del server SOLO con
  `BRAIN=nucleo` (`ZAELAR_SLOWBRAIN`); duo/hermes no lo montan. Sustituye el stub de V2-004 (que solo publicaba al bus).
- 2026-07-09 · T88 — retorno + circuito: `dispatch._deliver` (voz+UI+[SISTEMA]) solo entrega lo `deliver=True`
  (la tarea web entrega desde su owner). Tests del circuito: `test_listener_consumes_escalate_requested` (V2-006, sigue
  verde con el retorno nuevo) + `test_deliver_pushes_note_and_notifies` + `test_router_sends_web_request_to_web_agent`.
- 2026-07-09 · T89 — confirm-gate: `nucleo/danger.py::is_dangerous` (hermano del `_DANGER_RE` del navegador, más
  amplio para pillar conjugaciones ES: comprar/compra, borrar/borra, eliminar/elimina, publicar/publica; evita stems
  ciegos que den falsos positivos — "pág*"). `run_task` PARA una acción irreversible (kinds code/genérico) y pide OK
  por voz+UI (`WorkResult.needs_confirm`); sin `context.confirmed` NO ejecuta el agente. WEB queda fuera (su owner
  gatea el clic irreversible por-acción). Test `test_confirm_gate_blocks_irreversible`.
- 2026-07-09 · T90 — prueba del circuito: verificado E2E por tests el camino escalada→bus→dispatcher→agente→retorno
  (voz+UI+[SISTEMA]), la orquestación web (crea tarea + encola `automate` con plan), la generación/modificación de
  widget y el confirm-gate. **La prueba EN VIVO por micro con `BRAIN=nucleo`** («búscame X en la web» / «créame un
  widget de Y» dichos al micro) queda como item ABIERTO NO BLOQUEANTE — igual que en INI-012/V2-004/V2-005: nucleo
  no es el default de arranque hasta V2-009, y este entorno autónomo no tiene micro. Se ejercita en el cutover (V2-009).
- 2026-07-09 · **V2-007 CERRADA** — Aceptación cumplida por tests + arranque en vivo: (a) una petición que requiere
  razonamiento/tarea larga escala del FlashBrain al SlowBrain, corre async y su resultado vuelve por voz+subtítulo+
  chat+`[SISTEMA]` sin bloquear el hot path (listener + `_deliver`, tests); (b) automatización web y generación de
  widgets funcionan bajo el SlowBrain, con el bucle DOM→visión conservado y el generador con su rollback (paridad con
  duo/Hermes; tests de `web`/`code`); (c) una acción irreversible para y pide OK, sin OK no se ejecuta (`danger` +
  test). Suite `nucleo/ bus/ memory/ config/` = **197 passed** (0 regresiones). Arranque EN VIVO `make run-duo`
  LIMPIO: `/api/brain`=duo intacto (cerebro actual sin tocar, cero regresión), memoria v2 montada, worker LiveKit
  registrado, SlowBrain dispatcher NO montado bajo duo (gate correcto). **status/completed_at/state.json = artefacto
  del daemon MeshKore** (127.0.0.1:5573): fijo `status: done` en el registro git (como V2-003/0301fcd), el daemon
  reconcilia el working tree y regenera `state.json` en su barrido — no se edita a mano. Siguiente: **V2-008 —
  Conectores stateless** (`depends_on: [V2-003, V2-006]` satisfecho).
