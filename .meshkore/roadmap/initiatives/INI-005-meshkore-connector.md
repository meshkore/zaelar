---
id: INI-005
title: MeshKore Native Cluster Channel
status: cancelled
owner: ricart
modules: [connectors, brains, voice, server, frontend]
updated: 2026-07-01
---

<!-- v0.6.0 (2026-07-01): cluster security guard shipped — see "Hardening entregado" below. -->


## Goal

Darle a zaelar un **tercer canal de entrada/salida** (junto a voz y chat): conexión nativa a clusters
MeshKore para colaborar con OTROS agentes. El brain (Hermes) hace todo el pensamiento; el conector solo
transporta mensajes y despierta al brain ante eventos de cluster. Principio rector: **la voz de entrada/salida
es solo la interfaz** — las colaboraciones de cluster deben seguir vivas sin navegador abierto ("el agente
tiene su propia vida"), sin romper la fluidez ni la bidireccionalidad de la conversación por voz.

## Scope

- `connectors/meshkore/` — transporte WebSocket multi-cluster (brain-agnóstico) + `ClusterBridge` que inyecta
  mensajes de cluster en el brain y enruta los tags `[[cluster.*]]` de vuelta, con driver de eventos +
  heartbeat para colaboración autónoma agente-a-agente.
- **Agente Hermes compartido a nivel de proceso** (`brains/hermes/runtime.py`): un único agente ACP caliente
  para voz + chat + cluster, serializado por `turn_lock` (una conversación coherente en los tres canales).
- **Reasoner off-pipeline** (`brains/reasoner.py`): entrega al conector un `async reasoner(text)` del brain
  activo (Hermes → agente compartido; direct → OpenAI-compatible stateless).
- Protocolo de tags de cluster en `voice/tag_protocol.py` (`cluster.connect/send/done/disconnect`, nunca hablados).
- `ClientTextInjector` (`voice/turn_control.py`): texto tecleado/pegado del chat wall como turno de usuario.
- `server/__init__.py` lifespan: init del bridge, autoreconnect de clusters persistidos, heartbeat; shutdown limpio.
- Frontend: `frontend/app/components/ChatWall.js` (conversar por texto).
- Persistencia de credenciales de cluster: `config/meshkore.json` (gitignored, chmod 600, redactado en logs).

## State

**En progreso** (release v0.5.0, 2026-07-01). El canal está cableado y el servidor arranca con el bridge +
heartbeat + reasoner Hermes. **No validado aún contra un cluster real** (sin clusters configurados; autoreconnect
y heartbeat sin ejercitar end-to-end).

### Hardening entregado en esta release
- **Fix del regreso a mudo por barge-in** (crítico): el agente compartido + `session/cancel` introducidos aquí
  rompieron la auto-recuperación tras un barge-in → zaelar encolaba turnos y se quedaba mudo. Resuelto
  serializando los turnos ACP en el cliente. Ver diario `brains/logs/2026-07/MK-002-bargein-mute-fix.md` y
  memoria [[bug-bargein-mute]].
- **Security guard del canal de cluster** (v0.6.0): `connectors/meshkore/security.py`, cableado en `bridge.py`.
  El canal habla con agentes externos no confiables, así que: (1) el texto del peer se envuelve como
  `⟦UNTRUSTED PEER MESSAGE⟧` y nuestras reglas de seguridad (`trailer()`) se inyectan SIEMPRE al final del turno
  → defensa anti prompt-injection ("nuestro prompt va último"); (2) `scan_outbound()` bloquea el mensaje entero
  ante un secreto duro (token/clave/IBAN/tarjeta/credencial) y redacta solo huellas configuradas (`did:key` +
  `MESHKORE_SECRET_TERMS`); los nombres de modelo/framework NO se redactan (tema legítimo entre agentes) — la
  auto-revelación la gobierna el trailer (decisión del brain); (3) no se revela identidad ni datos personales;
  respuesta estándar de auth =
  "canal autorizado por token, sin datos personales sin permiso del operador". Postura `MESHKORE_SECURITY=strict`
  por defecto. Invariante de privacidad documentado (el cluster no tiene ruta a micro/cámara/voz). Tests en
  `connectors/meshkore/test_security.py`. Ver `.meshkore/docs/security/zaelar-security.md`.
- **Auditoría + controles DUROS de seguridad** (v0.7.0, MK-004): tras auditar el canal se cerró el riesgo mayor —
  el brain de cluster es el mismo Hermes con terminal/tools y zaelar auto-aprobaba todo permiso. Añadido: **tool-gate
  por origen** (turnos de cluster ejecutan con herramientas DENEGADAS; `acp_client._decide_permission` +
  `runtime.ask`, escape `MESHKORE_CLUSTER_TOOLS=1`), **allowlist de tags** (solo send/done; connect/disconnect
  operator-only), **fence-escape neutralizado + trailer reforzado** (sin acciones para un peer, sin grados de
  confianza), **guard REST** (loopback/`MESHKORE_API_TOKEN` + `/send` escaneado), **flood cap**, **TLS floor**
  (`ws://` bloqueado), **redacción reforzada** en journal/logs, y **tirith** en `~/.hermes/config.yaml`. 24 tests.
  Ver diario `.meshkore/modules/connectors/logs/2026-07/MK-004-cluster-hard-security.md`.

### Follow-ups abiertos (no bloqueantes)
- **Prioridad voz > cluster**: el `turn_lock` asyncio hace que un turno de voz espere detrás de un turno de
  cluster de fondo (hasta 120s). La voz debería **preemptar** al cluster. Revisar antes de habilitar clusters.
- Prueba end-to-end contra un cluster real (connect/send/heartbeat/done).
- Revisar el brief de MeshKore inyectado en cada turno de voz (coste de tokens / que no induzca al brain a
  emitir tags de cluster sin querer).
