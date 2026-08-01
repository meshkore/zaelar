---
id: V2-077
title: Plataforma única de testing y observatorio realtime
status: delivered
owner: ricart
modules: [tests]
updated: 2026-08-01
---

# V2-077 — Plataforma única de testing y observatorio realtime

## Objetivo

Unificar toda la superficie de calidad bajo `tests/` y ofrecer una sola entrada para operador, Codex, Claude Code
y CI. Una ejecución local abre un visor loopback que permite seguir suites largas paso a paso, correlacionando
input, output, assertions, observabilidad del agente, latencias, artefactos y score.

## Decisiones

- `tests/run_testmap.py` conserva la taxonomía dominio→caso→canal; el catálogo nuevo la consume, no la duplica.
- `tests/platform/events.py` define un protocolo JSONL append-only, versionado, recuperable tras crash y con
  redacción estructural de credenciales.
- El dashboard solo escucha en `127.0.0.1:8765`; cada run hace handoff y reemplaza al anterior sin procesos huérfanos.
- La UI rechaza un nuevo lanzamiento mientras el run visible siga `running`; el operador es espectador seguro de
  una ejecución de Codex/Claude Code y solo toma el control cuando termina.
- Pass/fail determinista y valoración del juez LLM son señales separadas.
- Los ejecutores especializados viven dentro de su dominio y comparten eventos, catálogo y directorio de runs.
- Las salidas viven en `tests/runs/` y nunca se versionan.

## Entregado — fase vertical

- [x] CLI `python -m tests list|run|replay`.
- [x] Suites memoria, agent-headless, voz, browser, conectores, cluster e infraestructura.
- [x] Adaptador pytest con collection/test lifecycle, duration, error y exit code.
- [x] Dashboard realtime de tres columnas, progreso, timeline, filtros, observabilidad y score separado.
- [x] Tester de voz integrado en `tests/voice/e2e/agent/` y conectado al protocolo común.
- [x] Catálogo `suite.json` por dominio, con pasos ordenados y tests concretos anidados en el UI.
- [x] Ejecución manual de suite, test individual y batería live (con confirmación) desde el UI.
- [x] Ejecución individual de pasos live; `3.3 Mic→STT` usa una sala LiveKit real y publica `SOURCE_MICROPHONE`.
- [x] Todo el código de testing Python y JavaScript movido físicamente bajo `tests/<dominio>/`.
- [x] Harness conversacional en `tests/agent_headless/harness/`; salidas históricas en `tests/runs/`.
- [x] Contratos JavaScript Agenda/WhatsApp adaptados al lifecycle común mediante pytest.
- [x] Runs durables, reabribles y gitignored.
- [x] Contrato operativo `tests/README.md` enlazado desde `CLAUDE.md`, `AGENTS.md`, el contexto raíz y el playbook
  `.meshkore`; documenta terminal, UI, aislamiento, headless, Playwright, voz, puertos y extensión de runners.
- [x] Gateway conversacional real de memoria como acción primaria: 15 turnos naturales con evidencia de extracción,
  descarte, capas, slots, correcciones y recall; un caso aislado reconstruye su prefijo causal.
- [x] Memoria cronológica de 180 días/966 pasos y 180 fases REM diarias; un caso aislado reconstruye su prefijo causal.

## Mejoras posteriores

- [ ] Adaptador Playwright con trace.zip, screenshots y vídeo como artefactos enlazables.
- [ ] Eventos finos para pasos headless y memoria-bot, no solo lifecycle de proceso.
- [ ] Comparativa de baseline, tendencias y detección explícita de flaky/infra-failure.

## Aceptación final

1. No queda ningún fichero `test_*.py` fuera de `tests/`.
2. Los comandos históricos tienen alias probado o se documentan como retirados.
3. Una suite de 1.000 pasos muestra el actual arriba y conserva los 1.000 eventos navegables.
4. Una conversación muestra cada input/output, traza correlacionada, latencia, evidencia y score del juez.
5. CI usa el mismo runner con `--no-open` y conserva el exit code correcto.

Los criterios 1, 2, 3 y 5 quedan cubiertos por la plataforma actual. El criterio 4 ya acepta eventos finos del
tester de voz; ampliar la misma instrumentación a todos los runners históricos queda como mejora incremental.
