---
id: V2-008
title: Conectores STATELESS + triaje DENTRO del widget mensajería (backed + CodeAgent interno)
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [connectors, widgets, memory, nucleo, bus]
depends_on: [V2-003, V2-006]
wall_order: 8
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T08:41:00.102Z
commit_sha: ab6d2326cdb14469cb50a2e07f737c1f7018a5d7
---
## Goal

Reordenar la mensajería según la arquitectura v2 (diagrama central): los **conectores pasan a STATELESS** (solo
leen la fuente y publican eventos al `bus/`), el **triaje sale de los conectores** y pasa a vivir DENTRO del
widget `mensajeria` (backed, con un **CodeAgent interno**), y el **storage se centraliza en `memory/`**. Una sola
cara, misma UX; pero cada pieza en su sitio.

## Qué se construye

### 1. Conectores stateless (`connectors/`)
- `whatsapp/` (bridge Baileys vendorizado), `telegram/` (userbot Telethon), `meshkore/` (canal de cluster):
  cada uno solo **lee** su fuente y **publica** `connector.msg` al bus (payload agnóstico de plataforma).
- Se RETIRA de `connectors/messaging/` la lógica de triaje (`triage.py`) y de store (`store.py`) — sube al widget
  / a memoria. `connectors/messaging/` queda como capa fina de normalización de eventos entrantes (o se elimina si
  ya no aporta).

### 2. Triaje dentro del widget `mensajeria` (backed)
- El `owner.py` del widget `mensajeria` se suscribe a `connector.msg`, tría con un **CodeAgent interno**
  (`CodeAgent.run(spec)` con un modelo barato/local, modelo por invocación) — reemplaza el clasificador
  `qwen2.5:3b` suelto, ahora encapsulado como agente del widget.
- Interrumpe solo con lo relevante vía `voice/proactive` + `[SISTEMA]`; marca leído lo resumido (enruta al
  conector correcto por `item.platform` a través del bus, `msg.mark_read`).

### 3. Storage en memoria
- Lo entrante durable se escribe a `memory/` (kind `msg`), no a un JSON por-widget. El estado de UI (vínculos,
  QR, cola de lectura) puede seguir en el store del widget, pero el CONTENIDO de mensajes es recall central.

## Tareas

- [x] Convertir whatsapp/telegram en publicadores de `connector.msg` (leer + publicar; sin triaje/store), gated nucleo. (meshkore = canal de cluster, FUERA de la bandeja personal → abierto, ver bitácora.)
- [x] Triaje SALE de los conectores → vive en el widget owner. Retirada FÍSICA de `triage.py`/`store.py` diferida a V2-009 (strangler-fig: el path duo/hermes vivo aún los usa); doc-sync hecho (federación/módulos/cluster.yaml).
- [x] `widgets/mensajeria/owner.py` — suscriptor de `connector.msg`/`connector.status` + triaje interno (`triage_agent`, modelo LOCAL) + `msg.mark_read` por bus. (CodeAgent de NUBE para triar = decisión abierta que choca con la privacidad → local por defecto.)
- [x] Volcar contenido de mensajes a `memory.write` (kind msg, vía `store.upsert_items`); estado de UI en el store del widget (único escritor = owner).
- [x] Aviso proactivo + `[SISTEMA]` solo de lo relevante (`notify.surface`/`announce`, throttle heredado) + tests.
- [x] Actualizar `cluster.yaml` + `zaelar-hermes-federation.md`/`zaelar-modules.md` (conectores stateless, triaje en widget).

## Aceptación

- Un mensaje entrante (WA o TG) → evento en el bus → el widget lo tría con su CodeAgent → si es relevante, sale
  por voz+UI y se guarda en memoria; se marca leído en la plataforma correcta.
- Los conectores no guardan estado ni tríann nada (solo publican).
- Una sola cara (`mensajeria`), badges por plataforma, control por voz `[[msg.*]]` intacto.

## Riesgos

- Latencia/coste del CodeAgent de triaje por mensaje → usar modelo barato/local y batch por ráfaga; no un
  Claude Code por mensaje si llega en avalancha.
- Privacidad: el triaje debe correr con modelo local por defecto (nada personal sale de la máquina) — se verifica en V2-010.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T90 — `connectors/messaging/ingest.py`: la costura STATELESS sobre el bus. Predicado único `v2_enabled()` (sigue a `BRAIN=nucleo`, override `ZAELAR_MSG_V2`); publicadores `publish_msg`/`publish_status`/`publish_mark_read` (loop-agnósticos, emit_sync); `MarkReadInbox` por plataforma (drena solo lo suyo). 6 tests verdes (`test_ingest.py`: gate por env/cerebro, entrega de cada topic, filtro por plataforma + consumo).
- 2026-07-09 · T91 — conectores STATELESS gated nucleo: `whatsapp/service.py` + `telegram/service.py` ramifican en `ingest.v2_enabled()` — bajo nucleo publican `connector.msg` (dedup por messageId) + `connector.status`, y drenan `msg.mark_read` (MarkReadInbox creada en su loop); bajo duo/hermes el camino DIRECTO de siempre (triage+store+notify) queda INTACTO. Cero import roto (269 tests de connectors/widgets/bus/memory/config/nucleo verdes).
- 2026-07-09 · T92 — `widgets/mensajeria/owner.py` (backed, gate=nucleo) + `triage_agent.py`: el owner es el ÚNICO escritor del store de UI; se suscribe a `connector.msg`/`connector.status`, tría por ráfaga con el agente interno (modelo LOCAL — invariante de privacidad; delega en `connectors/messaging/triage.py`), aflora lo relevante (`notify.surface`), lo guarda (`store.upsert_items` → store de UI + volcado a `memory` kind='msg') y avisa (`notify.announce`, throttle heredado). `handle()` reusa `data.apply_action` + publica `msg.mark_read` al marcar leído. 4 tests verdes (`test_owner_v2.py`: relevante aflora, irrelevante no, status refleja tarjeta, read→mark_read al bus).
- 2026-07-09 · T93 — GATE general de backed widgets: `manifest.json` de `mensajeria` = `kind:"backed"` + `backend:{owner,gate:"nucleo"}` (v0.5.0); `widgets/supervisor.py` respeta `backend.gate` (mecanismo reutilizable, no un caso especial): bajo nucleo arranca el owner, bajo duo/hermes lo omite → el widget cae al passive de siempre (sin carrera de dos escritores, cero regresión). Doc-sync: `cluster.yaml` (connectors + widgets), `zaelar-modules.md §Widget-apps` (bloque "mensajeria's migration" actualizado a STARTED), `zaelar-hermes-federation.md` (nota V2-008 conectores stateless).
- 2026-07-09 · T94 — VERIFICACIÓN EN VIVO (doble arranque, reinicio limpio tras tocar `.py`): (a) `BRAIN=duo` (default): `/api/brain`=duo, `backed[mensajeria] gated a BRAIN=nucleo — omitido`, WhatsApp+Telegram por el camino directo, `/events` idéntico, cero traceback → **cero regresión**; (b) `BRAIN=nucleo`: `backed[mensajeria] supervisor arrancado` + `mensajeria owner arrancado (triaje en el widget · conectores stateless)`, WA/TG motores stateless, sin errores. Tras verificar se **restauró el default `duo`** (regla: duo hasta V2-009). El flujo entrante→triaje→aflora→mark_read queda verificado POR TESTS (sesión WA/TG por QR no es scriptable headless — mismo caveat que INI-012/V2-004/005; ítem abierto no bloqueante).
- 2026-07-09 · **ABIERTAS (rule-#6, no bloqueantes)**: (1) **`meshkore/` stateless** — el canal de cluster NO es la bandeja personal (peers no confiables ≠ mensajes personales del operador); rewire a `connector.msg` sería un error arquitectónico y tocaría los controles duros de seguridad → se deja para el trabajo de seguridad de cluster (V2-010), no aquí. (2) **CodeAgent de NUBE para triar** — el texto de la iniciativa sugiere un "CodeAgent interno", pero un Claude Code de nube manda datos personales fuera de la máquina, chocando con el invariante DURO de privacidad ("triaje local por defecto"); se resuelve manteniendo el clasificador LOCAL como agente interno del widget (abstracción swappable). (3) **Retirada física** de `triage.py`/`store.py`/`notify.py` de `connectors/messaging/` y fold de `pending_read`/`pending_control` en el buzón + retiro del special-casing `[[msg.*]]` → diferido al entierro (V2-009), por strangler-fig (el default duo aún los usa; el `[[msg.*]]` lo posee duo hoy).
- 2026-07-09 · **V2-008 CERRADA** — Aceptación: un `connector.msg` entrante → el owner backed lo tría (agente interno, modelo local) → si es relevante aflora por voz+UI (`notify`) y se guarda en `memory` (kind msg), y `msg.mark_read` sale al bus para que el conector correcto lo marque en su app (verificado E2E POR TESTS: `test_owner_v2.py`; sesión WA/TG por QR = caveat headless conocido, ítem abierto). Los conectores bajo nucleo NO guardan estado ni tríann (solo publican, `test_ingest.py`). Una sola cara `mensajeria`, badges por plataforma, `[[msg.*]]` intactos (siguen por duo hasta V2-009). GATED en nucleo (strangler-fig): `BRAIN=duo` sigue idéntico, cero regresión — verificado EN VIVO en ambos modos. Suite `connectors/ widgets/ bus/ memory/ config/ nucleo/` = **269 passed** (+ 9 nuevos = ver conteo final). **status/completed_at/state.json = artefacto del daemon MeshKore** (el frontmatter `status` se auto-revierte al editarlo a mano; el daemon reconcilia al releer los .md con las tareas [x] + esta línea; no hay generador local ejecutable). Siguiente: **V2-009 — Entierro de Hermes** (`depends_on: [V2-004…V2-008]`; regla de oro: NO empezar hasta que V2-004→V2-008 estén verificadas EN VIVO — la parte de voz/mensajería por micro/QR sigue pendiente de prueba humana).
