# V2-069 — Una sola mente (operador + agentes, el mismo motor)

**Estado:** F0 CONSTRUIDO (rama `feat/v2-069-una-sola-mente`). 2026-07-25.

## Origen

Forense de la conversación zaelar↔zalo (cluster `meshcore`, 71 h de registro durable). El canal degeneró en un
bucle de cortesías sin producto: **331 auto-presentaciones**, **671 "entendido, espero"** por nuestro lado, y el peer
repitiendo "un momento, consultando" **1.333 veces** (59 % de sus mensajes). Causa raíz: el canal lo conducía un
**segundo cerebro paralelo, stateless y sin la maquinaria del FlashBrain** → cada turno se re-presentaba porque no
recordaba nada, y nada detectaba el bucle.

## Principio (decisión del operador)

Emular a un humano = **una sola mente**, no piezas paralelas. Hablar con el operador o con otro agente es el MISMO
acto. El acto se modula por **dos perillas**:

- **QUIÉN** (operador / agente) → de ahí cae la **CONFIANZA** (tools y memoria permitidas) y la saliencia de memoria.
- **PROFUNDIDAD** (reflejo / razonar / actuar) → de ahí cae el **modelo** (rápido / razonador / worker). La voz pone
  el tope duro no-razonador; off-voz puede razonar. Los procesos complejos (investigar/tools) son la profundidad
  «actuar» del MISMO acto (misma vía de workers), no un sistema aparte.

Balance de complejidad NEGATIVO: se **borra** un sistema (el cerebro paralelo), no se añade ninguno.

## Arquitectura

- **Motor único:** el turno de cluster corre por el motor del FlashBrain en **perfil UNTRUSTED**
  (`nucleo/flash/cluster.py::respond` → `FastClient.complete` no-streaming + `prompt.build_cluster_system`
  identidad-safe + defensas de `dialog`, **tools apagadas en código**). `connectors/meshkore/brain.py` adapta el
  canal (resuelve el tier de modelo off-voz) y delega.
- **Memoria scope-partido:** una sola memoria central, particionada. La **cápsula** (`connectors/meshkore/capsule.py`)
  es la memoria-de-relación por `(cluster, peer)` sobre `sys_kv` (`memory.kv_get/kv_set`) + trust `untrusted` en
  cuarentena: dossier + resumen + objetivo + bucles abiertos + FASE + contadores de atasco. La raíz (operador) es
  confiable; la cápsula (peer) nunca entra en el prompt del operador → **PII del operador incorruptible**.
- **Identidad-safe:** `build_cluster_system` NUNCA llama a `compose_state` → un peer no ve nombre/PII del operador ni
  el catálogo de widgets/tools.

## Inteligencia de conducción (lo que arregla los males de la forense)

- **FASE** (saludo→sondeo→trabajo→cierre), derivada del estado de la relación → **no re-presentarse** en trabajo/sondeo.
- **Objetivo presente + bucles abiertos** → conducir hacia el objetivo y "ya te dije que no, no re-negociemos".
- **Guardia de atasco** determinista en el bridge (umbrales 2/4): repetición → **1 mensaje asertivo** anclado al
  objetivo → si sigue, **callar** y avisar al operador **una vez**. Corta el bucle a los 2-3, no a los 1.333.
- **Susurro** (auto-auditoría) hereda el canal por `turn.completed` (2ª línea semántica).

## Fases

- **F0 (hecho):** cápsula + KV de memoria + cableado al bridge (mata re-presentación) + guardia de atasco + motor
  único (perfil untrusted, tools off, identidad-safe). Retirado el cerebro paralelo. Tests verdes.
- **F1 (hecho, salvo lo deferido):**
  - ✅ Consistencia de clave del peer (handle NEUTRALIZADO) en dedup/stall/cápsula.
  - ✅ Cierre en `cluster.done` → cápsula fase CIERRE + reset del contador de atasco.
  - ✅ Identidad-safe blindado (test del framing COMPLETO: build_cluster_system + brief.for_brain + cápsula).
  - ✅ Robustez: retry en blips transitorios del LLM (fast_client) — un blip no tira el turno.
  - ⛔ **Susurro sobre cluster — DEFERIDO a V2-010 (justificado, NO es deuda de F1):** enchufar Susurro al canal
    metería contenido UNTRUSTED del peer en un auditor POTENTE cuyo catálogo incluye `worker_action` (escalar a un
    worker) → es exactamente la frontera deny-tools/sandbox que posee V2-010. El **guardia de atasco DETERMINISTA**
    (en código, probado en vivo con zalo: 7 asertivos) ya cubre la degeneración de conversación SIN exponer contenido
    untrusted a un modelo potente. Reabrir solo dentro de V2-010, con el gate de untrusted→tools.
  - La profundidad «actuar» desde una charla de agente (peer→worker) es V2-010 (fuera de scope por seguridad).
- **F2 (hecho):** SMOKE INTEGRAL de todo el sistema (`tests/infrastructure/e2e/smoke/run_full_smoke.py`, 20 checks) + e2e del CHAT
  por transporte REAL (`tests/infrastructure/e2e/smoke/run_chat_over_livekit.py`: cliente LiveKit → data-channel → agent → reply) —
  este último cierra el hueco que dejó pasar la degradación del motor LiveKit del 2026-07-25.

## Incidente 2026-07-25 (motor LiveKit degradado — NO era V2-069)

El chat del operador quedó sin respuesta + el micro desincronizado tras un refresco. Causa: el motor LiveKit
embebido llevaba ~7h y entró en bucle `wait_pc_connection timed out` → el agent no formaba la sala → el handler del
data-channel `zaelar-text` nunca se activaba (voice=off server-side pese al frontend conectado). El probe funcionaba
porque no usa LiveKit. Fix: reinicio limpio (worker re-registrado, 0 timeouts). Lección: hacía falta un e2e que
ejerciera el TRANSPORTE real (creado en F2) — el smoke server-side no lo cazaba.

## Selección de modelo

No es prioridad ahora (cambiable en el futuro). Hoy el tier del canal es GLM-5.2 vía config/.env; el motor es
agnóstico del modelo (por invocación). Nota técnica: un tier razonador vía AIMLAPI no emite deltas hasta terminar →
el canal usa `FastClient.complete()` (no-streaming) con timeout.
