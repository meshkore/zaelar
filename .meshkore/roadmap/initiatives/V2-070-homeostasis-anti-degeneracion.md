# V2-070 — «Homeostasis»: el latido autónomo (anti-degeneración)

**Estado:** F0 CONSTRUIDO (rama `feat/v2-069-una-sola-mente`). 2026-07-25.

## Origen

Regla del operador: **«nada puede ni debe degenerar con el tiempo».** Detonante concreto: el 2026-07-25 el chat del
operador se quedó sin respuesta y el micro desincronizado tras un refresco. Causa raíz — el motor LiveKit embebido
llevaba ~7h y entró en bucle `wait_pc_connection timed out` / `entrypoint did not exit` → el agent no formaba la
sala → el handler del data-channel `zaelar-text` nunca se activaba. **Nada lo detectaba ni lo curaba** salvo un
reinicio manual. Auditoría posterior: la **memoria** ya se auto-cura (decay/dedup/heal_slots/REM), pero **el motor de
voz, los logs y las cápsulas NO** — crecen o se degradan sin límite.

## Principio (decisión del operador)

El sistema emula a un humano en **TRES niveles, y solo dos piensan**:

| Nivel | Pieza | Rol | ¿Piensa? |
|-------|-------|-----|----------|
| **Mente** | FlashBrain (`nucleo/flash`) | conduce y decide (operador + agentes) | Sí (modelo) |
| **Conciencia** | Susurro (`nucleo/susurro`) | «¿lo hago bien?» audita la CONVERSACIÓN | Sí (modelo) |
| **Autónomo** | **homeostasis** (`nucleo/homeostasis.py`) | «¿mi CUERPO sigue sano?» mantiene la MÁQUINA | **No. Cero LLM.** |

Como el latido o el sistema inmune: **no se decide, se ejecuta.** Por eso vive **AL LADO** del cerebro, no dentro —
meter reintentos/reciclados/rotación en el FlashBrain lo ensuciaría con lógica que no es inteligencia. **Binario
(regla del operador):** cada recurso tiene DOS estados, sano/degradado → curar. No 200 estados. Es el **watchdog de
sesión promovido a código durable** que no muere al cerrar la sesión. Balance de complejidad: se añade UNA pieza
pequeña y determinista, el cerebro queda intacto.

## Arquitectura

- **Un lazo `start(app)`/`stop()`** en el `lifespan` del server, hermano de los otros supervisores
  (messaging/widgets), fuera del bucle de voz. `app` para poder reciclar el worker LiveKit embebido
  (`app.state.lk_server`/`lk_task`).
- **Funciones PURAS testeables** para cada decisión (detección, seguridad, eviction, rotación) + heals con IO. Un
  fallo del propio mantenimiento nunca toca voz/chat (**fail-open duro**, cada chequeo aislado).
- **Detección del motor IN-PROCESS**: un `logging.Handler` sobre el logger `livekit` (y sus hijos) estampa una marca
  cada vez que el SDK loguea la señal de bucle WebRTC. No depende de leer ficheros de log externos.

## Los tres chequeos (F0)

1. **MOTOR LiveKit** — si acumula ≥ umbral de señales de degradación en la ventana: si es **SEGURO** (voz apagada +
   canal inactivo ≥ `IDLE_S`) **recicla el worker embebido** (`aclose` + `make_server` + nueva task) SIN reiniciar el
   proceso, con cooldown anti-bucle; si NO es seguro (voz/canal vivos), **avisa al operador 1×** (voz+UI+chat, sin
   toasts) y no toca nada. Clava el incidente del 25/07 en caliente.
2. **LOGS** — rota `timeline-latest.jsonl` / `meshkore.jsonl` por rename (seguros: ambos abren `"a"` por escritura →
   el siguiente append recrea el fichero) al superar el tope + poda archivos rotados viejos (`keep`).
3. **CÁPSULAS** — evicta las CONCLUIDAS (fase cierre) y viejas + acota el total (`sys_kv capsule:*`), con
   `memory.kv_keys(prefix)` / `memory.kv_del(key)` nuevos.

## Invariantes

- NUNCA toca el FlashBrain, la memoria del operador ni su PII.
- Reciclar SOLO cuando es seguro; si no, avisar, nunca cortar una conversación viva.
- Determinista, sin LLM. Kill-switch de 1ª clase `ZAELAR_HOMEOSTASIS`. Observabilidad TOTAL (evento `homeostasis`).
- **Testeable SIN incidente real** (que es raro): funciones puras + watcher IN-PROCESS + rotación real en disco →
  `tests/infrastructure/unit/core/test_homeostasis.py` (13 tests), **dominio 9 del mapa de tests** (`tests/run_testmap.py`).

## Config (env, infra — no UI)

`HOMEOSTASIS_PERIOD_S`=60 · `HOMEOSTASIS_LK_WINDOW_S`=180 · `HOMEOSTASIS_LK_THRESHOLD`=3 ·
`HOMEOSTASIS_IDLE_S`=120 · `HOMEOSTASIS_RECYCLE_COOLDOWN_S`=600 · `HOMEOSTASIS_LOG_CAP_BYTES`=64MiB ·
`HOMEOSTASIS_LOG_KEEP`=3 · `HOMEOSTASIS_CAPSULE_MAX`=200 · `HOMEOSTASIS_CAPSULE_TTL_S`=30d · `ZAELAR_HOMEOSTASIS`=1.

## Anti-degeneración — cobertura por recurso (auditoría 2026-07-25)

| Recurso | ¿Degenera? | Quién lo cura |
|---------|-----------|---------------|
| Memoria (schema/peso/dedup/vectores) | Sí | **YA** — consolidador + REM + heal_slots |
| Motor LiveKit (worker embebido) | Sí (visto el 25/07) | **V2-070** — reciclado seguro |
| Logs (timeline/meshkore) | Sí (crecen sin fin) | **V2-070** — rotación + poda |
| Cápsulas (sys_kv por peer muerto) | Sí (crecen con N peers) | **V2-070** — eviction |
| Chromium de búsqueda (huérfanos) | Parcial | barrido al arranque (`run-livekit.sh`); runtime = follow-up |

## Sobre RUST (respuesta a la pregunta del operador)

La degeneración era de **arquitectura, no de lenguaje** — un reinicio manual la arreglaba; el fix es una pieza de
supervisión, no reescribir. Recomendación: **NO** reescritura masiva. Mantener el cerebro en Python (velocidad de
iteración + ecosistema LLM). Rust SELECTIVO tiene sentido más adelante para el control-plane cloud y, si acaso, un
keeper/launcher OUT-OF-PROCESS (el nivel «el proceso entero está muerto», que un lazo in-process no puede cubrir) —
no para el motor conversacional.

## Fases

- **F0 (hecho):** lazo + tres chequeos + detección in-process + cableado al lifespan + tests + docs + web. Estado:
  ~940 tests deterministas verdes, dominio 9 nuevo.
- **F1 (abierto, no deuda):** keeper OUT-OF-PROCESS (launchd/systemd) para el «proceso entero muerto» (cloud-relevante);
  reciclado de Chromium huérfano en runtime; métricas de salud históricas.
