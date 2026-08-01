# V2-033 — Precisión de escritura de la memoria (el CORAZÓN no ensucia el largo plazo)

> **HANDOFF al equipo de MEMORIA.** Esta tarea la separo a propósito del arreglo del FlashBrain (V2-032, ya hecho):
> es trabajo del CORAZÓN de escritura (`nucleo/mem_processor.py` + `nucleo/memory_agent.py`), que es dominio del
> workflow de memoria (`.meshkore/docs/ops/zaelar-memory-workflow.md`). El FlashBrain (conversación) y su canal de
> prueba ya están resueltos y son la herramienta con la que validaréis esto (ver §Cómo probar).

## Contexto — de dónde sale

Informe de iteración del **2026-07-12** (test de persona de voz "Alex", memoria vacía, juez GLM-4.6). Bloqueante #1
= estabilidad conversacional del FlashBrain (**resuelto en V2-032**). Bloqueante #2 = **calidad de ESCRITURA de la
memoria**, que es esto. La lectura (retriever, ESTADO cacheado, recall time-boxed) va bien; el problema es **QUÉ se
guarda como durable**.

## Los 3 fallos medidos (P0/P1)

1. **[P0] Guarda RUIDO CRUDO como hecho durable.** Fragmentos de PETICIÓN/PREGUNTA del operador entran al largo
   plazo como si fueran hechos: *"Sí, búscame algo con más detalle"*, *"¿Puedes mirar eso por mí?"*. Resultado: 146
   "durables", muchos basura. El CORAZÓN debe **DESCARTAR peticiones/preguntas/ack** y destilar solo **afirmaciones
   con sustancia** (perfil, hechos, preferencias, compromisos).

2. **[P0] Propaga el GARBLE del STT como HECHOS.** El CORAZÓN destila fielmente lo mal transcrito: *"proyecto actual
   = HeartKey"* (era **Charms**), *"marcas FOI/FOE/Electric"* (era **efoil**), *"Alex de Hígado"* (era **Delgado**).
   Sin validación de plausibilidad, un hecho durable se escribe aunque sea improbable. (El garble es artefacto del
   arnés de voz, pero expone que **no hay control de plausibilidad al escribir un durable**.) En la prueba en vivo
   del canal nuevo se ve el efecto: el FlashBrain llegó a decir *"Me llamo Alex Teigano"* — confundió la identidad
   del operador con la suya por un `state` polucionado.

3. **[P1] Sobre-generaliza preferencias EFÍMERAS a durables GLOBALES.** Un *"no me muestres"* puntual se guardó como
   *"prefiere sin mostrar en pantalla"* → **suprimió la visualización de widgets** en otra prueba (un "muéstrame" no
   abrió nada). Una preferencia de UN turno no debe convertirse en regla de comportamiento permanente.

## Qué resolver (propuesta, ajustadla)

- **Filtro de tipo de enunciado en el CORAZÓN** (`mem_processor.py`): antes de destilar, clasificar el turno —
  PETICIÓN / PREGUNTA / ACK / CHARLA vs AFIRMACIÓN-CON-DATO. Solo las afirmaciones con dato entran a CORTO/LARGO;
  lo demás → DESCARTAR (ya existe esa rama; hay que **subir su recall**). Cuidado con no perder afirmaciones
  envueltas en petición ("recuérdame que soy alérgico al marisco" SÍ es un hecho).
- **Control de plausibilidad ligero al escribir un durable**: nombres propios/marcas/proyectos que aparecen UNA vez,
  con baja confianza de STT o que contradicen un `slot` ya establecido → **cuarentena/menor peso**, no durable
  directo. No hace falta LLM caro: heurística + el propio `slot` (supersede) + quizá un umbral de repetición.
- **Preferencias efímeras**: una preferencia de comportamiento ("no me muestres", "habla más corto") solo se hace
  durable si se **repite** o el operador la marca como permanente; si no, vive como estilo de sesión
  (`set_style_directive`, que ya es efímero) y NO toca `state`/long.
- Cruza con **V2-031** (fidelidad máxima): el eje NO es el embedding — es **write-completeness + precisión**. Esto
  es la cara "precisión" de esa misma palanca.

## Cómo probar — usad el CANAL DE PRUEBA nuevo (V2-032, 3ª forma de testing)

Ya no hace falta la voz ni el arnés para iterar sobre la memoria. Flujo rápido desde Claude Code / terminal:

```bash
make reset                 # memoria + observabilidad a CERO (conserva credenciales)
make flash-serve           # server headless (sin voz/navegador); en otra terminal:
# inyecta turnos que INTENTAN ensuciar y comprueba qué se guardó:
make flash T="¿puedes mirar eso por mí?"        # PETICIÓN → NO debe crear durable
make flash T="soy alérgico al marisco"           # AFIRMACIÓN con dato → SÍ durable
make flash T="no me muestres nada ahora"         # preferencia efímera → NO durable global
curl -s localhost:8473/api/memory/map | python -m json.tool   # inspecciona state/long: ¿qué entró?
```

El endpoint `POST /api/flash/say` corre el turno REAL del FlashBrain con `ingest=true` por defecto (llama a
`memory_agent.ingest_utterance`, el mismo camino que la voz) → lo que se escriba es lo que escribiría en producción.
Contrastad con `/api/memory/map` (ESTADO + corto + largo). Objetivo: tras esos 3 turnos, el largo plazo tiene el
alérgeno y NADA más; `state` no queda con una preferencia "sin mostrar".

## Fuera de alcance de este handoff (ya hecho, no tocar)

- Estabilidad conversacional del FlashBrain (break-loop, anti-degeneración, poda de historial) → **V2-032**,
  `nucleo/flash/dialog.py`, cableado en voz + probe.
- El canal de prueba headless (`nucleo/flash/probe.py`, `make flash*`) → **V2-032**, es vuestra herramienta.

## Cierre

Termina SIEMPRE con la **revisión de alineación** (`zaelar-alignment-review.md`) y el **workflow de memoria**
(`zaelar-memory-workflow.md`): tocáis el CORAZÓN de escritura → hay que repasar todos los escritores/lectores.

## CERRADA (2026-07-12) — equipo de MEMORIA

Resuelta con **GATES DETERMINISTAS** en `nucleo/memory_agent.py` (el modelo pequeño no obedece por prompt; se
aplican a la salida del LLM Y de la heurística), simétricos a los backstops (que rescatan) pero FILTRANDO lo que el
CORAZÓN guarda de más:

- **[P0a]** pre-LLM: `_is_ephemeral_directive` + `_is_vague_request` descartan directivas efímeras y peticiones vagas
  sin referente; post-LLM: `_ATOM_NONFACT_RE` tira preguntas reificadas e interrogativos. Preserva TAREAS CONCRETAS
  (`_COMMITMENT_RE`) y AFIRMACIONES envueltas ("recuérdame que soy alérgico…").
- **[P0b]** `_plausibility_demote`: valor de slot de identidad que contradice el `state` establecido → no sobrescribe;
  se degrada a `long` en CUARENTENA (`trust=untrusted`, invisible al recall/prompt). Correcciones explícitas pasan;
  perfil vacío admite el primer dato.
- **[P1]** directiva efímera ("no me muestres ahora") = estilo de sesión, no durable; durable solo con marca
  ("prefiero/siempre…").

**Verificación:** `tests/memory/integration/test_write_precision_v2033.py` (16 casos, `MEM_PROCESSOR=0` → determinista,
cero GPU: los 3 turnos del brief dan largo = SOLO el alérgeno, `state` sin pref, identidad protegida) + **smoke con el
destilador LLM real** (qwen2.5 vía Ollama, DB aislada): el LLM reifica/garblea y los gates lo atrapan; `operator_name`
queda intacto. **291 tests de memoria sin regresión.** Camino de prueba del brief (`make flash`) validado por la vía
in-process equivalente (`ingest_utterance`, mismo camino que la voz).

**Mapa de impacto (workflow de memoria):** los gates viven SOLO en `ingest_utterance` (turno del operador). NO afectan
a otros escritores (`ingest_message` de fuentes, `remember` directo de resultados/widgets, buffer conv del FlashBrain)
ni a NINGÚN lector (retriever/state/recent_short/compose_state intactos). Cerrado con revisión de alineación.

**Docs:** `zaelar-memory.md §CORAZÓN` (gates de precisión), `CLAUDE.md` (módulo `mem_processor`), diagrama `/architecture`
(pestaña Memoria). Cruza con **V2-031** (cara "precisión" de write-completeness).
