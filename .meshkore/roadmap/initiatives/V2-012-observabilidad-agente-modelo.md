---
id: V2-012
title: Observabilidad — columna de AGENTE + modelo del agente en el timeline
epic: v2-colmena
status: next
priority: high
owner: ricart
modules: [voice, nucleo, frontend]
depends_on: [V2-006, V2-007]
wall_order: 12
created: 2026-07-09
updated: 2026-07-09
---

## Goal

El timeline de observabilidad (`/debug`, la columna derecha de actividad que usamos para debuguear) hoy registra
por evento: **módulo principal** que se ejecuta (STT / TRANSCRIPT / FLASH BRAIN / WIDGET / NAVEGADOR / BOT_SPEECH /
BRAIN), **latencia**, y el **modelo LLM** (hoy el del FlashBrain, p. ej. `x-ai/grok-4-fast-non-reasoning`). Falta
ver **qué trabajo corre a través de un AGENTE** y **con qué modelo lo hace ese agente**.

Contexto: el SlowBrain delibera con un **agente Cloud Code** (hilo separado), y el FlashBrain lanza procesos que
también corren por un agente Cloud Code — p. ej. organizar una búsqueda en el navegador (buscar una moto concreta
en Wallapop). El agente usa **modelo POR INVOCACIÓN**: una tarea de búsqueda/estudio de producto puede arrancar con
**Haiku** (barato), pero una tarea que requiere razonar mucho o dar una opinión compleja puede correr con
**Opus 4.8**. Eso no se ve en el registro y es justo lo que hace falta para debuguear.

## Qué se construye

1. **Nueva columna "Agente"** en el timeline (antes o después de la del modelo LLM): indica si el evento corre a
   través de un agente y **cuál** — hoy solo **Cloud Code**, pero diseñado extensible (mañana habrá más agentes).
2. **La columna del modelo LLM, cuando corre un agente, muestra el modelo que usa ESE agente** (el modelo
   por-invocación del CodeAgent: Haiku para búsqueda/estudio, Opus 4.8 para razonamiento/opinión compleja), no solo
   el modelo rápido del FlashBrain.
3. Se refleja **en todos los datos que guardamos** (eventos del observer / timeline jsonl), no solo en la UI —
   para poder debuguear a posteriori y medir coste/latencia por agente y por modelo.

Aplica a: dispatch del SlowBrain (`nucleo/dispatch.py` + `nucleo/agentes/*`) y a los procesos lanzados desde el
FlashBrain (el agente del navegador, `NAVEGADOR_AGENT_MODEL` / `NAVEGADOR_AGENT_MODEL_STRONG`).

## Tareas

- [ ] T118 — Esquema de evento del observer/bus: añadir `agent` (tipo, hoy `cloud-code`; extensible) + `agent_model` (modelo por invocación del agente); persistir en el timeline jsonl (`voice/observer.py`).
- [ ] T119 — El SlowBrain/CodeAgent emite `agent`+`agent_model` por tarea al despachar (`nucleo/dispatch.py` + `nucleo/agentes/base.py`/`claude_code.py`), tomando el modelo del `RunSpec` (por invocación).
- [ ] T120 — Los procesos lanzados desde el FlashBrain (agente del navegador / búsqueda) emiten `agent`+`agent_model` (`NAVEGADOR_AGENT_MODEL`/`_STRONG`), incluido el hilo separado.
- [ ] T121 — Frontend `/debug` timeline: nueva columna **Agente** + la columna de modelo muestra el modelo del agente cuando hay agente; layout extensible a >1 tipo de agente. Alinear con la vista SSE del observer.
- [ ] T122 — Alineación: `zaelar-observability.md` + diagrama `/architecture` (dónde corre cada agente y con qué modelo) + **pasar la revisión de alineación** (`zaelar-alignment-review.md`).

## Aceptación

- En `/debug`, un turno que escala al SlowBrain o lanza una búsqueda en el navegador muestra la columna **Agente =
  Cloud Code** y, en la columna de modelo, **el modelo que usa el agente** (p. ej. Haiku o Opus 4.8), no el del FlashBrain.
- El evento persistido (timeline jsonl) incluye `agent` + `agent_model`; se puede reconstruir a posteriori qué agente
  y qué modelo atendió cada proceso.
- El diseño admite añadir un segundo tipo de agente sin tocar el esquema (solo un valor nuevo en `agent`).

## Riesgos

- El agente del navegador corre en un **hilo separado**: la emisión del evento debe ser loop-agnóstica (usar la
  costura del bus/observer que ya es thread-safe), no asumir el event loop de la voz.
- Modelo por invocación: `agent_model` debe leerse del `RunSpec` real de esa invocación, no de un default global.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
