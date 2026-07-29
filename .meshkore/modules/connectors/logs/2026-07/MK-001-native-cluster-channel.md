---
id: MK-001
title: "Canal nativo MeshKore (cluster) — transporte + bridge + agente Hermes compartido"
status: in-progress
priority: high
owner: ricart
initiative: INI-005
created: 2026-07-01
updated: 2026-07-01
---

# MK-001 — Canal nativo de clusters MeshKore

Tercer canal de I/O de zaelar (junto a voz y chat): colaboración autónoma con otros agentes sobre clusters
MeshKore. El brain piensa; el conector transporta. Ver iniciativa INI-005.

## Qué se añadió

### 1. Conector `connectors/meshkore/`
- `manager.py` — hub de conexiones WebSocket multi-cluster; `client.py` — cliente por cluster; `store.py` —
  persistencia de credenciales (`config/meshkore.json`, chmod 600) + staging + redacción de secretos;
  `journal.py` — traza post-mortem; `brief.py` — instrucciones de cluster para el brain; `identity.py`,
  `server_api.py` (rutas REST/paste `/api/meshkore/*`, siempre montadas por ser canal nativo).
- `bridge.py` (`ClusterBridge`) — convierte cada frame entrante en input etiquetado para el brain, lo pasa por
  el `reasoner`, parsea los tags `[[cluster.*]]` de la respuesta y los enruta; `_engaged` + heartbeat para
  seguir/concluir colaboraciones sin spamear.

### 2. Agente Hermes compartido a nivel de proceso — `brains/hermes/runtime.py`
Un único agente ACP caliente para voz + chat + cluster (antes cada sesión de voz levantaba y mataba el suyo).
Serializado por `turn_lock` (asyncio) → una conversación coherente en los tres canales y las colaboraciones
sobreviven al cierre del navegador. El servidor (lifespan) lo apaga; la sesión de voz **ya no** lo mata.

### 3. Reasoner off-pipeline — `brains/reasoner.py`
`make_reasoner()` entrega al conector el brain activo como `async reasoner(text)` (Hermes → agente compartido;
direct → OpenAI-compatible stateless), manteniendo el conector brain-agnóstico.

### 4. Protocolo de tags + inyección de texto (voice/)
- `tag_protocol.py`: tags `[[cluster.connect|send|done|disconnect]]` (JSON, nunca hablados).
- `turn_control.py` `ClientTextInjector`: texto tecleado/pegado del chat wall → turno de usuario completo.
- `agent.py`: brief de MeshKore inyectado en el turno de voz; el agente compartido ya no se para al desconectar.

### 5. Server + Frontend
- `server/__init__.py`: `_lifespan` con init del bridge, autoreconnect de clusters persistidos, heartbeat, y
  shutdown limpio del agente compartido. `meshkore_router` montado siempre (canal nativo).
- `frontend/app/components/ChatWall.js` + servicios/estilos: conversar por texto.

## Ficheros tocados
- `connectors/meshkore/*` (nuevo módulo, declarado en `cluster.yaml`)
- `brains/hermes/runtime.py`, `brains/reasoner.py` (nuevos), `brains/hermes/llm_processor.py`
- `voice/agent.py`, `voice/turn_control.py`, `voice/tag_protocol.py`
- `server/__init__.py`
- `frontend/app/**` (ChatWall + core/store/services/components/styles)
- `requirements.txt`, `.gitignore`, `.meshkore/docs/**`, `.meshkore/public/cluster.yaml`

## Estado / Verificación (2026-07-01)
- Servidor arranca con el bridge + heartbeat + reasoner Hermes; `GET /api/brain → {"brain":"hermes"}`.
- **No validado contra un cluster real** (sin clusters configurados). Follow-ups en INI-005: prioridad
  voz>cluster, prueba end-to-end, coste del brief.
- Regresión crítica introducida aquí (barge-in → mudo) **resuelta** en `brains/logs/2026-07/MK-002`.
