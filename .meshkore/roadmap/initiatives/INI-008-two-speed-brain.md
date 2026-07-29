---
id: INI-008
title: Cerebro de dos velocidades (fast orchestrator + Hermes async)
status: done
owner: ricart
modules: [brains, voice, server]
updated: 2026-07-08
depends_on: INI-005
---

## Goal

Que la voz **parezca siempre viva** (respuesta ~sub-segundo) sin perder la cognición profunda de Hermes. Problema
medido (2026-07-05): con `BRAIN=hermes` el turno de voz tarda **5-8s** (dominado por el `think` del modelo vía
AIMLAPI) → no hay sensación de conversación. La arquitectura de dos velocidades estaba **decidida pero no
implementada** (ver arquitectura §8). El operador dio go-ahead a la **Fase 1** el 2026-07-05.

## Diseño

Tercer cerebro enchufable **`BRAIN=duo`** (`brains/duo/`) que ocupa el slot del LLM en el pipeline igual que
Hermes — **el frontend no cambia**. Reparto:

- **Rápido** (Gemini Flash, `reasoning_effort=none`, NO-razonador): atiende cada turno. Charla, control de widgets
  (`[[show]]/[[close]]/[[push]]`), Q&A de estado (operativo / canal cluster / hora) desde un **bloque de estado
  vivo** sin tools, y triaje.
- **Profundo** (`[[deep]]`): cuando hace falta memoria/tools/razonamiento/crear widgets/cluster, el rápido dice una
  frase de espera y emite `[[deep]]petición[[/deep]]` → turno de Hermes en segundo plano (`runtime.ask(...,
  deny_tools=False)`, path del operador con tools; serializado por `turn_lock`). El resultado se entrega por
  `voice/proactive` (voz + UI) y se pliega en la memoria corta del rápido. `brains/duo/tasks.py` registra las
  tareas en curso → nunca dice «hecho» antes de tiempo.
- **Proactivo**: sin cambios — Hermes cron sigue entregando por `voice/proactive`.

Memoria: Hermes sigue siendo el **único dueño** de la memoria larga; el rápido es memoria corta de sesión. Cada
`[[deep]]` lleva la petición reformulada; Fase 2 añadirá el digest de sesión → memoria de Hermes.

## Tareas

- [x] T-1 · `[[deep]]` en el protocolo compartido (`voice/tag_protocol.py`) + hold de streaming.
- [x] T-2 · `runtime.ask(deny_tools=...)` — override de confianza (operador=tools ON, cluster=fail-closed).
- [x] T-3 · `brains.uses_hermes()` + gates (cron ticker, `/api/hermes/*`, cluster reasoner) para hermes+duo.
- [x] T-4 · `brains/duo/`: fast_client (Gemini streaming), prompt (persona+estado+triaje), tasks, llm_processor.
- [x] T-5 · Wiring `BRAIN=duo` en `voice/agent.py` + etiqueta de boot.
- [x] T-6 · Declarar módulo en `cluster.yaml` + docs (arquitectura §8, CLAUDE.md).
- [x] T-7 · Validación: Gemini alcanzable (~1s full, TTFT streaming sub-s); turno rápido vs escalado; hold de
      streaming del `[[deep]]` sin fuga a voz.

> **Estado: Fase 1 DONE (2026-07-05, v0.10.0)** — implementada, validada E2E y corriendo (`make run-duo`).
> Nota post-estreno: el free tier de `gemini-2.5-flash` se agotó en una sesión (429) → default cambiado a
> `gemini-2.5-flash-lite` + modo degradado (rápido caído ⇒ el turno pasa síncrono a Hermes, lento pero vivo).

## Fase 2 (go-ahead del operador 2026-07-05 «sigue» — HECHA)

- [x] **Preempción — la voz del operador manda**: `voice/proactive.notify` ya no habla encima. Espera un hueco de
      silencio (sin turno de usuario abierto — `turn_control.user_turn_open()` — ni bot hablando, con 1.2s de
      respiro tras su última frase); si la conversación no da tregua en `PROACTIVE_MAX_WAIT` (45s), el mensaje NO
      se pierde: entra como nota `[SISTEMA]` al siguiente turno y el cerebro lo dice él mismo, en contexto. La UI
      lo muestra siempre al instante. Aplica a entregas profundas Y al cron (mismo canal).
- [x] **Digest de sesión → memoria de Hermes**: al colgar, `DuoLLMProcessor.session_digest_task()` empuja el
      transcript corto de la capa rápida a Hermes en background ("guarda solo lo que valga la pena; no respondas")
      — su diario ya no queda ciego de charlas que nunca escalaron.
- [x] **Knob ⚙ del modelo rápido**: `fast_model` en el panel (solo visible con BRAIN=duo), persiste en
      settings.json → env `FAST_MODEL`, que el cliente lee POR PETICIÓN (aplica al reconectar, sin reiniciar).

## Fase 2b — memoria de arranque (HECHA, 2026-07-07)

El digest de sesión (Fase 2) es la mitad OUTBOUND (rápido→Hermes, al colgar). Faltaba la mitad INBOUND: sin
memoria propia, cada `DuoLLM` era una sesión en blanco y se re-presentaba ("hola, ¿quién eres?") aunque Hermes
llevara semanas conociendo al operador.

- [x] **`brains/duo/briefing.py`**: al arrancar la sesión (`voice/engine/pipeline/agent.py`, antes de
      `session.start()`), pide a Hermes un briefing brevísimo vía `runtime.locked_ask` — cacheado en proceso
      (TTL 5 min). El timeout acota TAMBIÉN la espera del lock de turno (`_proc_turn_lock`, compartido con
      `[[deep]]`/digest), no solo la llamada ACP — sin esto, un Hermes ocupado podía colgar el arranque de la voz
      indefinidamente (bug real, encontrado en pruebas E2E con Playwright antes de cerrar esta fase).
- [x] **`build_fast_system()`** añade el briefing como bloque "MEMORIA DE ARRANQUE" y neutraliza la instrucción
      de "pregunta el nombre" de la persona base (`voice/prompt.py`, nuevo flag `has_context`) cuando hay
      briefing — evita la contradicción de pedir el nombre mientras la memoria ya lo da.
- [x] **`BootOverlay.js`** (frontend): pantalla de carga bloqueante desde la carga hasta `bus.event("ready")`
      (canal de datos LiveKit, topic `vl2`, tras el kickoff) — cubre arranque de agentes + voz + esta memoria.
      Salvaguarda de 60s en `session-lk.js` (nunca deja la UI encerrada); solo bloquea el primer arranque.
- Validado E2E con un navegador real (Playwright, mic simulado) contra `make run-duo`: transcript confirmado
  referenciando la memoria en el saludo, y degradación correcta (saludo genérico + overlay desbloqueado por la
  salvaguarda) cuando Hermes está ocupado/lento.

## Fase 2c — escalada fiable vía tool-calling + directiva de estilo (HECHA, 2026-07-08)

Bug real en producción (sesión de voz 2026-07-07 23:08, capa rápida = `moonshotai/kimi-k2-0905` vía AIMLAPI,
ver `.meshkore/logs/timeline-latest.jsonl` de esa franja): **el rápido nunca emitió `[[deep]]`** en toda la
sesión (`escalated: False` en cada turno de `kind=brain`) pese a que el operador pedía depurar el bridge de
WhatsApp/Baileys y modificar widgets. En vez de escalar, confabulaba un plan técnico ficticio ("voy a mirar el
commit/los logs...") — nada real pasaba, y repetir "no me lo cuentes, hazlo" no lo arreglaba porque el fallo no
era la narración, era que JAMÁS pedía ayuda. Un texto-tag pseudo-XML (`[[deep]]...[[/deep]]`) solo existe si el
modelo decide escribirlo literalmente en medio de prosa libre — un modelo más pequeño/terso lo salta con
frecuencia. Mismo síntoma para una instrucción de estilo dada por voz ("no me narres los pasos"): el operador la
repitió 3 veces en la misma sesión y las 3 veces se ignoró, porque solo vivía en el historial de turnos, compitiendo
por atención contra un prompt de sistema enorme.

- [x] **`escalate_to_hermes` y `set_style_directive` como function-calling real** (OpenAI-compatible,
      `brains/duo/fast_client.py::FastClient.stream(tools=…, on_tool_call=…)` + `voice/engine/llm/providers/
      duo.py::_TOOLS`), sustituyendo el texto-tag `[[deep]]` para la capa rápida (el resto del protocolo de tags —
      `[[show]]`/`[[close]]`/`[[widget.data]]`/etc — sigue como texto, sin cambios). Function-calling es el
      mecanismo estándar/entrenado para que un LLM dispare una acción de forma fiable, y es **agnóstico del
      idioma**: decide el propio modelo semánticamente, sin listas de palabras clave por idioma que mantener (se
      descartó ex profeso un primer intento con regex/keywords en español — no escala, se rompe con el catálogo
      multilenguaje `es/en/fr/it/pt/de` de `voice/engine/core/langs.py`). Validado en vivo contra la API real
      (streaming, con la clave AIMLAPI de producción): dada la frase exacta de la sesión que falló, Kimi K2 llamó
      correctamente a AMBAS funciones con argumentos limpios.
- [x] **`set_style_directive(directive)`** fija `DuoLLM._directive` — se re-inyecta en `build_fast_system()` cada
      turno (`brains/duo/prompt.py::_directive_block`) desde el turno siguiente en adelante, así una preferencia
      de sesión ("sé breve", "no narres pasos") no depende de que el modelo la "recuerde" del historial. Vive solo
      dentro de la sesión — persistir para SIEMPRE sigue siendo trabajo de Hermes vía `escalate_to_hermes` (memoria
      larga, sin cambios ahí).
- [x] **Filler multilenguaje** (`LangSpec.filler_holding`, `voice/engine/core/langs.py`, catálogo es/en): si el
      modelo llama a `escalate_to_hermes` sin decir nada en voz en la misma respuesta (visto en pruebas — pasa),
      se dice una frase neutra de espera EN EL IDIOMA ACTIVO en vez de quedarse mudo. Neutra a propósito: no
      parafrasea la petición (sería reintroducir la narración fabricada que este cambio elimina).
- [x] Reiniciado y verificado en vivo (`make run-duo`) tras el cambio.
- [ ] Pendiente: pasada del tester (INI-013) contra una sesión de voz real completa (lo validado hasta ahora es
      contra la API/streaming directamente, con las mismas piezas de código, pero no una sesión LiveKit end-to-end).

## Fase 2d — vuelta a LOCAL con Qwen más grande (HECHA, 2026-07-08)

Petición del operador: priorizar CAPACIDAD sobre latencia mínima para la capa rápida — "estamos dispuestos a
renunciar un poquito a esta latencia por la capacidad intelectual". Benchmark en M4 Max/48GB (Ollama, con el
`build_fast_system()` real + las dos funciones `_TOOLS`), tres tamaños, 5 escenarios cada uno (chit-chat,
show-widget, needs-escalation, style-directive, memory-save):

| modelo | TTFT caliente | fiabilidad tool-calling | nota |
|---|---|---|---|
| `qwen2.5:7b-instruct` | ~0.3-1.0s | baja — a veces ESCRIBE la llamada como texto (`[[escalate_to_hermes {...`) en vez de invocarla | descartado |
| `qwen2.5:14b-instruct` | ~0.5-2.0s | media — no confabula texto, pero a veces simplemente NO escala (declina y para) | **elegido** |
| `qwen2.5:32b-instruct` | ~0.9-4.0s (+ un stall de 150s, probable presión de memoria con 3 tamaños cargados a la vez) | media — funcionó mejor en la mayoría de casos, pero la huella de memoria es demasiado ajustada en una máquina que también corre STT+TTS locales | descartado por riesgo |

**Decisión: `qwen2.5:14b-instruct` LOCAL** (`.env`: `FAST_BASE_URL=http://127.0.0.1:11434/v1`,
`FAST_MODEL=qwen2.5:14b-instruct`, `FAST_API_KEY=ollama`). Reiniciado y verificado arriba (`make run-duo`).

⚠️ **HALLAZGO ABIERTO — prioridad #1 del loop nocturno (INI-013):** NINGÚN tamaño local llamó a
`escalate_to_hermes`/`set_style_directive` el 100% de las veces que debía — Kimi K2 vía AIMLAPI fue más fiable en
las mismas pruebas. Es un trade-off real de "todo local": más privado/gratis, pero el tool-calling de Ollama con
Qwen2.5 vía su plantilla de chat no es tan robusto como el de un flagship de pago. El loop nocturno debe: (a)
cuantificar la tasa de fallo real en conversación (no solo estos 5 casos sintéticos), (b) probar variantes
(`qwen2.5-coder`, otra cuantización, `tool_choice="required"` en vez de `"auto"`, subir `num_ctx`), (c) decidir si
el trade-off vale la pena o si hay que volver a Kimi K2 para producción y quedarse con Qwen local solo para dev.

**Primera manifestación real encontrada y arreglada (2026-07-08, madrugada, ver INI-013 "Iteración 1"):** un
fallo de escalada con `qwen2.5:14b-instruct` no era solo "no llama a la función" — el modelo escribía el JSON
del argumento de la llamada COMO TEXTO (`{"request": "..."}`), y ese texto se filtraba a la voz porque el
mecanismo anti-JSON-leak de `voice/tag_protocol.py` solo detectaba el patrón completo, no en streaming
incremental. Arreglado en `tag_protocol.py` (retiene desde CUALQUIER `{` sin cerrar) + `duo.py` (recupera la
llamada real desde el JSON descartado en vez de perderla). No resuelve el hallazgo abierto de arriba (el modelo
sigue sin llamar a la función de forma nativa el 100% de las veces), pero SÍ evita las dos peores consecuencias
(hablar JSON crudo + perder la acción en silencio) cuando falla.

**Generalizado (INI-013 Iteración 10, 04:24):** con más muestras (31 frases en total) aparecieron 2 formas de
fuga NUEVAS que el guard original no cubría — JSON con clave sin comillas (`{q: "..."}`) y una tag inventada
(`[[search]]`, confundiendo un id de widget con un nombre de tag real). Mismo principio, ampliado: `JSON_LEAK_RE`
ahora acepta claves sin comillas, y una nueva pasada `UNKNOWN_BRACKET_RE` retira cualquier `[[...]]` que no sea
una tag real conocida. Sigue sin ser un problema de "faltan más parches" — es la confirmación de que el modelo
local, cuando falla, lo hace de formas variadas e impredecibles; los parches acotan el daño (nunca hablar la
fuga, recuperar la acción cuando se puede) pero no sustituyen la necesidad de un modelo/mecanismo más fiable.

## Fase 2e — ronda de búsqueda del mejor modelo local FREE (HECHA, 2026-07-08, madrugada)

Petición del operador: buscar el modelo local "más rápido y potente" disponible gratis, sin techo de tamaño fijo
(hasta 70B+ si el benchmark lo justifica), priorizando **fiabilidad de tool-calling + latencia** (el cuello de
botella real, no benchmarks genéricos de razonamiento) — pero con un criterio adicional clave: **el Mac tiene
que poder seguir haciendo otras cosas**, zaelar no puede acaparar toda la máquina. Arnés: mismos 13 casos de la
oleada A + 2 controles negativos (chit-chat / show-widget, que NO deben escalar), contra el prompt real y las
2 funciones reales, más `ollama ps` para huella de memoria/CPU-GPU tras cada uno.

| modelo | tamaño disco | aciertos | latencia | CPU/GPU | veredicto |
|---|---|---|---|---|---|
| `qwen2.5:14b-instruct` (baseline, en producción) | 9 GB | 6/13 (46%) nativo | TTFT ~0.3-2s | 100% GPU | **el mejor de la ronda** |
| `hermes3:8b` (especialista function-calling, Nous Research) | 5 GB | ~2/9 antes de un crash del arnés | variable | — | peor que el baseline; además filtró un tag `<THINKING>` crudo — descartado |
| `firefunction-v2` (especialista function-calling) | 39 GB | 0/15 — TODOS los turnos con timeout | — | **10%/90% CPU/GPU** | no cabe entero en GPU, inviable — descartado |
| `qwen3:14b` | 9.3 GB | 3/15 (solo los 2 controles negativos + 1) | 15-78s por turno | 100% GPU | modo "thinking" activado por defecto — genera razonamiento oculto antes de cualquier contenido, viola la regla dura de "no razonadores en el path de voz" — descartado sin más pruebas |
| `qwen3:30b-a3b` (MoE) | 18 GB | 2/15 | ~8-32s por turno | 100% GPU | mismo problema de "thinking" que 14b — TODA la familia qwen3 descartada por defecto |
| `gemma3:27b` | 17 GB | 0/15 — error 400 en cada turno | — | — | Ollama: "does not support tools" — sin soporte de function-calling en absoluto, descartado de raíz |
| `mistral-small` | 14 GB | 3/15 | TTFT ~0.7s salvo un pico de 100s | 100% GPU | peor que el baseline; además inventó una fuga NUEVA en formato `[[escalate_to_hermes request: "...` (ni JSON ni tool-call real) — descartado |
| `llama3.3:70b` | 42 GB (53 GB cargado) | no completado — descartado antes de terminar | timeout >240s en el warm-up | **28%/72% CPU/GPU** | no cabe en 48GB compartidos con STT/TTS locales; fallback a CPU severo — inviable en esta máquina, descartado sin gastar más tiempo/cuota |

**Decisión: se mantiene `qwen2.5:14b-instruct` en producción.** Ningún candidato probado esta noche lo superó —
la mayoría eran claramente peores (menos aciertos, latencias absurdas, o directamente sin soporte de tools), y
los dos que en teoría debían ser mejores para ESTO específicamente (`hermes3`, `firefunction-v2`, especialistas
en function-calling) resultaron los más flojos o directamente inviables en este hardware.

**Nota metodológica (para no sobre-interpretar los datos):** cambiar de modelo cada pocos minutos durante horas
(8 modelos distintos, de 5 a 53 GB, cargados/descargados en secuencia) probablemente causó presión de memoria y
cold-loads que inflan algunos picos aislados (68s, 100s, 150s en distintos modelos) — esos outliers NO son
representativos de "un modelo, en caliente, solo". La comparación de TASA DE ACIERTOS entre modelos sigue siendo
válida (todos corrieron bajo la misma metodología imperfecta), pero la latencia absoluta de cualquier candidato
debería re-confirmarse en una sesión donde sea el ÚNICO modelo cargado antes de tomarla como definitiva.

**CORREGIDO con causa raíz real (INI-013 Iteración 11, 04:35)** — la nota de abajo (Iteración 4, "reiniciar
Ollama") no estaba mal del todo pero era incompleta: el pico de 55.68s (y los de 59-71s vistos después, incluso
recién reiniciado Ollama) no era degradación del proceso — era que `brains/duo/fast_client.py` nunca pasaba
`keep_alive` en las peticiones normales, así que Ollama descargaba el modelo tras ~5 min de silencio (su
default) y el turno siguiente pagaba una recarga completa. **Arreglado de raíz**: `FastClient.stream()` ahora
pasa `keep_alive: "30m"` en CADA turno (solo con Ollama local). Ver detalle completo y verificación en INI-013
Iteración 11. La nota de "reiniciar Ollama" de abajo se conserva como historia (fue una observación real en su
momento, solo que la explicación causal era incompleta), no como recomendación operativa vigente — ya no hace
falta reiniciar Ollama por esto.

~~**CONFIRMADO tras el hecho (INI-013 Iteración 4, 03:53):** incluso `qwen2.5:14b-instruct` — el modelo ganador,
ya en producción, sin ningún cambio de código — dio un pico de **55.68s** en una prueba justo después de cerrar
esta ronda. `brew services restart ollama` + repetir la misma petición → latencia volvió a **2.05-2.66s**
(el rango sano). Confirma que los outliers de 55-150s de TODA esta sección son degradación acumulada del propio
proceso `ollama serve`, no un problema de ningún modelo concreto. **Aprendizaje operativo: reiniciar el servicio
Ollama tras una sesión de benchmarking pesada, antes de fiarse de cualquier medición de latencia absoluta.**~~

**Nota para hardware menos potente (petición del operador, para decidir en otros equipos en el futuro):**
- `firefunction-v2` (39GB) y `llama3.3:70b` (42GB) mostraron fallback a CPU (10% y 28% respectivamente) ya en
  este M4 Max/48GB — en una máquina con menos RAM unificada o sin GPU Apple Silicon serían con toda seguridad
  **inutilizables** para una capa de voz "rápida" (el fallback a CPU en LLMs es 10-50x más lento que GPU/ANE).
- La familia `qwen3` necesita desactivar expresamente el modo "thinking" (no probado esta noche — pendiente,
  ver hallazgo abierto de la Fase 2d) antes de ser un candidato serio en CUALQUIER hardware; con la config por
  defecto de Ollama, descártala directamente.
- Para una máquina con bastante menos RAM (16-24GB), la elección razonable seguiría el mismo patrón que aquí:
  `qwen2.5:Xb-instruct` en el tamaño más grande que quepa con margen para STT+TTS+SO (aquí: 14b con 48GB de
  margen; en 16GB probablemente el techo realista sea 7b, ya evaluado en Fase 2d con fiabilidad más baja).
- `gemma3` queda descartada en CUALQUIER hardware para este uso concreto — no es un problema de tamaño/máquina,
  es que Ollama no expone function-calling para esa familia en absoluto.

## Fase 2f — revisión de código: bug crítico en `tag_protocol.py` encontrado y arreglado (2026-07-08, 05:00)

Una revisión de código dedicada (`/code-review high`, 8 agentes, ver INI-013 Iteración 14 para el detalle
completo) encontró que el guard `UNKNOWN_BRACKET_RE` añadido en la Fase 2e (para no hablar tags inventadas como
`[[search]]`) borraba el ABRIDOR de cualquier tag de dos partes (`[[widget.data]]`, `[[push]]`, `[[deep]]`,
`[[cluster.*]]`, `[[cron.create]]`, `[[architect.*]]`) antes de que llegara su cierre bajo streaming real —
rompiendo potencialmente el mecanismo COMPLETO de mutación de widgets de Hermes, no solo el tool-calling de esta
iniciativa. **Arreglado** con un lookahead negativo que excluye los prefijos de tag conocidos. Estuvo en
producción ~40 minutos sin causar daño detectado (ninguna prueba de esa ventana ejercitó una tag de dos partes
real por streaming). Ver INI-013 Iteración 14 para la lista completa de 5 arreglos de esta ronda.

## Fase 3 (futuro, requiere go-ahead)

- Evaluar Groq para <500ms; evaluar razonador real en Hermes (ya fuera del hot-path).
