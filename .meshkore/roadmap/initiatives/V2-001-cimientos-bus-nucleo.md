---
id: V2-001
title: Cimientos v2 — sistema nervioso (bus/) + esqueleto nucleo/ + config v2 aditiva
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [bus, nucleo, config, voice, server]
depends_on: []
wall_order: 1
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T01:37:56.421Z
commit_sha: 814ed219742d85c767e2813e3698a4909a97ef1f
---
## Goal

Poner los **cimientos** del sistema v2 SIN cambiar ningún comportamiento: un bus de eventos in-process
("Sistema Nervioso"), el esqueleto vacío del cerebro `nucleo/`, y el esquema de config v2 de forma **aditiva**.
Al terminar, zaelar arranca EXACTAMENTE igual que hoy (`BRAIN=duo`/`hermes`) — cero regresión — pero la
infraestructura nueva existe, está declarada y testeada.

## Qué se construye

### 1. `bus/` — Sistema Nervioso (pub/sub in-process)
Transporte HÍBRIDO: la voz sigue por llamada directa; el bus es para señales async/fan-out. NADA de Kafka.
- `bus/__init__.py` — `publish(topic, payload)`, `subscribe(topic) -> async iterator`, `emit_sync` para
  hilos que no son el loop principal (patrón loop-agnóstico ya usado en `runtime.locked_ask`).
- `bus/log.py` — log durable de eventos en SQLite (mismo fichero `zaelar.db` de memoria, tabla `events`, o
  fichero propio si memoria aún no existe — decidir en implementación; preferible tabla en zaelar.db).
- `bus/sse.py` — puente al frontend: `voice/observer.py` se RE-EXPRESA sobre el bus (back-compat: `GET /events`
  sigue emitiendo lo mismo). El observer queda como un suscriptor más.
- Topics iniciales: `memory.updated`, `widget.*`, `brain.*`, `connector.msg`, `loop.tick`, `escalate.*`.

### 2. `nucleo/` — esqueleto vacío del cerebro (sin cablear)
Paquetes con docstrings + firmas (stubs que levantan `NotImplementedError`), para fijar el contrato:
- `nucleo/flash/{router,fast_client,frontend,procs,escalate}.py`
- `nucleo/{loop,dispatch,memory_agent}.py`
- `nucleo/agentes/{base,claude_code,codex}.py`
- `nucleo/__init__.py` con la doc del contrato (qué es FlashBrain vs SlowBrain).

### 3. config v2 (aditiva)
- `config/v2.py` (o ampliar `config/settings.py`) con el esquema nuevo (routing de modelos fast + code-agent,
  flags) **conviviendo** con el actual. Nada se borra todavía (eso es V2-009). Vista pública redactada.

### 4. Declaración de módulos
- Añadir `bus`, `nucleo` y `memory` (aunque memory se construya en V2-002) a `.meshkore/public/cluster.yaml`.

## Tareas

- [ ] `bus/__init__.py` — pub/sub in-process (asyncio) + `emit_sync` loop-agnóstico + tests.
- [ ] `bus/log.py` — log durable de eventos (tabla `events`) + tests de persistencia.
- [ ] `bus/sse.py` — re-expresar `voice/observer.py` sobre el bus; `GET /events` idéntico (test de back-compat).
- [ ] `nucleo/` — crear el árbol de stubs con docstrings + firmas (no cablear a voz).
- [ ] `config/v2.py` — esquema v2 aditivo + vista pública redactada + tests.
- [ ] Declarar `bus`, `nucleo`, `memory` en `.meshkore/public/cluster.yaml`.
- [ ] Montar el bus en el lifespan de `server/__init__.py` (arranca/para; sin suscriptores nuevos aún).
- [ ] Verificar arranque `make run` sin cambios de comportamiento (BRAIN actual intacto).

## Aceptación

- `make run` arranca con el cerebro actual, `GET /events` emite lo de siempre (observer sobre bus).
- `pytest` de `bus/` verde (pub/sub, emit_sync entre loops, log durable).
- `cluster.yaml` declara los 3 módulos nuevos; `import nucleo` funciona (stubs).
- Cero cambios en la ruta de voz.

## Riesgos

- El `emit_sync` entre el loop del job-thread de LiveKit y el de uvicorn: reutilizar el patrón ya resuelto en
  `brains/hermes/runtime.py` (threading.Lock / call_soon_threadsafe). No reinventar.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T34 — `bus/__init__.py` construido: pub/sub in-process (patrones fnmatch), `Subscription` async-iterator + `.get()` (compat observer), `emit_sync` loop-agnóstico (call_soon_threadsafe, arregla la entrega cross-loop job-thread→uvicorn) y sinks síncronos para el log durable. 10 tests verdes (`bus/test_bus.py`).
- 2026-07-09 · T35 — `bus/log.py` construido: log durable de eventos en SQLite (tabla `events`, WAL) sobre el fichero compartido `zaelar.db` (`db_path()`/`ZAELAR_DB`, reusable por la memoria de V2-002). Se engancha como sink síncrono del bus (`attach`, idempotente); lectura `recent()`/`count()` con filtro por topic/prefijo. Best-effort (nunca revienta el reparto). 6 tests verdes (`bus/test_log.py`). `.gitignore`: `zaelar.db*` + `memory/_data/`.
- 2026-07-09 · T36 — `bus/sse.py` + `voice/observer.py` re-expresado sobre el bus: el observer es ahora un suscriptor más del topic `observer`; `emit()` publica por `emit_sync` (entrega cross-loop segura, elimina el `put_nowait` cross-loop a pelo) y `subscribe()/unsubscribe()` delegan en el bus. `GET /events` byte-idéntico (test lo verifica). 21 tests de `bus/` verdes + 73 tests existentes sin regresión.
- 2026-07-09 · T37 — esqueleto de `nucleo/` (cerebro v2): árbol de stubs con docstrings + firmas que fijan el contrato — `flash/{router,fast_client,frontend,procs,escalate}`, `loop`, `dispatch`, `memory_agent`, `agentes/{base(CodeAgent ABC),claude_code,codex}`. Reglas duras codificadas en las firmas (modelo POR INVOCACIÓN, no-razonador, deny-tools para input no confiable). `WIRED_TO_VOICE=False` — nada cableado a la voz. 6 tests verdes (`nucleo/test_skeleton.py`: imports + contrato + stubs levantan NotImplementedError).
- 2026-07-09 · T38 — `config/v2.py`: esquema de config v2 ADITIVO (convive con settings/connectors sin tocarlos) — routing de modelos `fast` (FlashBrain) + `code_agent` (SlowBrain) + `flags` de despliegue. Modelo POR INVOCACIÓN (guarda defaults, no fija env global); store MANDA sobre `.env` (fallback power-user); **vista pública REDACTADA** (`api_key`→`api_key_set:bool`, nunca en claro). 8 tests verdes (`config/test_v2.py`, incl. invariante de no-fuga de secretos). `.gitignore`: `config/v2.json`.
- 2026-07-09 · T39 — `cluster.yaml`: `bus`/`nucleo`/`memory` declarados; descripciones de `bus` (CONSTRUIDO) y `nucleo` (ESQUELETO) actualizadas al estado real (docs-sync), `memory` sigue PLANNED (V2-002). (El parseo estricto de PyYAML ya fallaba antes de este cambio por el estilo de `: ` sin comillas en las descripciones existentes — house style tolerado por el daemon; mis entradas siguen ese mismo estilo, no lo introduzco yo.)
- 2026-07-09 · T40 — bus montado en el lifespan de `server/__init__.py`: ciclo de vida del log durable (attach al boot / detach+close al shutdown), **sin suscriptores nuevos** — la voz ya fluye por el bus (T36) y el hot path queda intacto. El log durable (sink SÍNCRONO) va **OFF por defecto** (`ZAELAR_BUS_LOG=0`) para garantizar cero cambio en la ruta de voz + no crecer `zaelar.db` con spam de tokens; se activará cuando la memoria (V2-002/003) defina qué merece persistencia durable. Import del server + módulos v2 OK.
- 2026-07-09 · T41 — VERIFICACIÓN de arranque en vivo (`make run-duo`, reinicio limpio tras tocar `.py`): `GET /api/brain` = `{"brain":"duo"}` (cerebro actual intacto), `GET /events` emite el frame SSE de siempre (observer sobre bus), log de boot muestra «Sistema Nervioso (bus/) montado — log durable en standby (ZAELAR_BUS_LOG=0)» + «LiveKit agent worker started EMBEDDED», sin errores/tracebacks (los 2 warnings — EspeakG2P g2p, longitud de la dev-key JWT — son pre-existentes del entorno, ajenos al cambio).
- 2026-07-09 · **V2-001 CERRADA** — Aceptación cumplida: `make run` arranca con el cerebro actual y `/events` emite lo de siempre; `pytest bus/` verde (21) + `config/test_v2.py` (8) + `nucleo/test_skeleton.py` (6); `cluster.yaml` declara los 3 módulos e `import nucleo` funciona; cero cambios en la ruta de voz (73 tests existentes sin regresión). Siguiente: **V2-002 — Memoria núcleo**.
