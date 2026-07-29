---
id: V2-010
title: Endurecimiento v2 — seguridad del SlowBrain + tester v2 + benchmarks de latencia/modelo
epic: v2-colmena
status: next
priority: high
owner: ricart
modules: [nucleo, memory, connectors, tester, config]
depends_on: [V2-007, V2-009]
wall_order: 10
created: 2026-07-09
updated: 2026-07-09
---

## Goal

Endurecer el sistema v2 y cerrar la rueda de mejora. Dos frentes: **seguridad** (con SlowBrain, input NO
confiable puede alcanzar un CodeAgent con terminal/ficheros — es la superficie de ataque grande del entierro) y
**calidad** (re-apuntar el tester de INI-013 al cerebro v2 + benchmarks de latencia/modelo del fast layer y del
code-agent).

> **Nota (auditoría 2026-07-26):** `V2-076-dev-brainworker-y-sandbox.md` (2026-07-26) construyó la versión
> **permission-gated** de "Deny-tools para turnos no confiables" y "Sandbox del CodeAgent" de abajo — el turno de
> cluster sigue tools-off por DEFECTO, pero un permiso `code` concedido por el operador (`connectors/meshkore/
> perms.py`+`store.py`) + un objetivo fijado para esa relación (`capsule.objective`, guard añadido en la misma
> auditoría) puede abrir un dev-worker acotado (cwd temporal + `Bash` solo a `nucleo/git_cli.py`). El sandbox
> (`nucleo/sandbox.py`) EXISTE (rlimits/env-scrubbed/timeout) pero **no está cableado** al subproceso interactivo
> del dev worker todavía — ese hueco concreto sigue siendo trabajo de ESTA iniciativa (V2-010), no repetir el
> diseño, solo cerrar el cableado que falta. Antes de retomar cualquier tarea de abajo, leer V2-076 primero para no
> duplicar lo ya construido.

## Qué se construye

### 1. Seguridad del SlowBrain (controles DUROS, no solo prompts)
- **Deny-tools para turnos no confiables**: input de peers de cluster, mensajes entrantes y contenido web que
  llegue a un `CodeAgent` corre con herramientas DENEGADAS por defecto (hereda la postura de
  `brains/hermes/acp_client.py` + `connectors/meshkore/security.py`). zaelar, no el modelo, decide el permiso.
- **Sandbox del CodeAgent**: `spec.cwd` aislado, `spec.timeout` obligatorio, allowlist de tools por tipo de agente.
- **`scan_outbound` heredado** en la salida a cluster/mensajería (bloquea secretos, redacta huellas).
- **Privacidad de memoria**: el triaje y los embeddings corren locales por defecto; nada personal sale de la
  máquina sin permiso. Revisar que `memory/` no filtra a ningún API salvo lo explícito.

### 2. Tester v2 (INI-013 re-apuntado)
- Oleadas re-apuntadas al cerebro v2: A=fiabilidad de escalada (ahora FlashBrain→SlowBrain), B=directiva de
  estilo, C=memoria de arranque (desde `memory.state()`), D=widgets, E/F=WA/TG (triaje en widget), I=latencia,
  L=cron/proactividad (loop propio).
- El juez sigue leyendo el bus (`GET /events`): ahora observa `escalate.*`, `loop.*`, `memory.updated`.

### 3. Benchmarks
- Latencia del fast layer (local Ollama vs Grok/AIMLAPI, modelo por invocación) → elegir default por hardware.
- Coste/latencia del code-agent por tipo de tarea → default de modelo por invocación en config.
- Registrar en `.meshkore/docs/ops/zaelar-model-benchmarks.md`.

## Tareas

- [ ] Deny-tools por defecto para turnos originados en input no confiable que alcancen un CodeAgent + tests adversariales.
- [ ] Sandbox del CodeAgent (cwd aislado, timeout, allowlist de tools por agente) + test.
- [ ] Portar `scan_outbound` a la salida del SlowBrain hacia cluster/mensajería + test.
- [ ] Auditoría de privacidad de memoria: confirmar que nada personal sale a un API salvo lo explícito.
- [ ] Re-apuntar las oleadas del tester (INI-013) al cerebro v2; verificar que el juez observa los nuevos eventos.
- [ ] Benchmark fast layer (local vs Grok) + code-agent por tarea → defaults en config + doc en zaelar-model-benchmarks.md.
- [ ] Pasar la auditoría completa (`zaelar-audit-workflow.md`) sobre el sistema v2.

## Aceptación

- Un input no confiable (peer/mensaje/web) NO puede ejecutar comandos/ficheros vía un CodeAgent (deny-tools verificado).
- El tester v2 corre las oleadas contra el cerebro nucleo y el juez emite veredictos sobre eventos v2.
- Benchmarks registrados; el default del fast layer está justificado por medición, no por intuición.
- La auditoría v2 no deja P0/P1 abiertos.

## Riesgos

- La superficie de ataque del CodeAgent es real y nueva → tratar deny-tools como fail-closed (denegar por defecto,
  permitir explícito), igual que el canal de cluster hoy.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
