# V2-075 — Criterio de conversación por INTELIGENCIA (evaluador por modelo, genérico)

**Estado:** F0 CONSTRUIDO + VIVO (rama `feat/v2-069-una-sola-mente`, commit `6d21591`; versión `2.75+22564c1`). 2026-07-26.

## Origen — corrección de principio del operador

V2-073 implementó el criterio de ritmo con **patrones hardcodeados** (`capsule.looks_stuck`: regex de frases de
bloqueo — «⛔», «no puedo avanzar», «estamos en fase»…). Al revisar la charla con zalo apareció un patrón NUEVO (zalo
bloqueado por su dependencia «Poli»/503) y la reacción instintiva fue **añadir esas frases al regex**. El operador lo
paró en seco y con razón:

> «este es el caso de Zalo pero podemos tener otras decenas de conversaciones con otros agentes que tengan otros
> problemas… debe ser siempre un filtro, un criterio, pasado por un modelo de lenguaje y ser el resultado de aplicar
> la inteligencia, no de aplicar comportamientos jarcodeados… si no, solo nos adaptaremos a Zalo y fallaremos en el
> siguiente. Necesito filtros, criterios, cosas que sean dinámicas.»

Las formas de degenerar una conversación son **infinitas** (bucle, sinsentido, desajuste de capacidad, bloqueo por
dependencia, pasividad, malentendido…). Ningún regex las cubre. **Lo tiene que juzgar un modelo.**

## Qué se hizo

- **`connectors/meshkore/evaluator.py` (NUEVO):** evaluador de la SALUD de una conversación por **modelo**, genérico.
  - INDEPENDIENTE (2ª perspectiva, no el que conduce) + **READ-ONLY** (solo emite un veredicto de catálogo CERRADO,
    sin tools/acciones) → **seguro sobre contenido no confiable** (a diferencia de Susurro con `worker_action`, que
    sigue diferido a V2-010).
  - Catálogo cerrado: `health` ∈ flowing/stuck/dead_end/imbalanced/off_track × `action` ∈ continue/concise/hand_back/
    pause. Prompt: métricas objetivas (turnos, ratio de producción) + ventana reciente marcada como MATERIAL a
    evaluar (no instrucciones). **Fail-open duro** (error del modelo → `continue`, nunca corta por infra).
- **`bridge.py`:** quitado el gate de regex del turno. Se mantiene una **ventana por-peer** (ambos lados) y el
  **evaluador corre periódicamente en el heartbeat** (throttle `MESHKORE_EVAL_SECS`=45, solo charlas ACTIVAS). El
  bridge **aplica** el veredicto: `hand_back` (cede el turno con `capsule.PACE_HANDBACK` y espera) · `pause` (calla +
  avisa al operador 1×) · `concise` (inyecta brevedad en el próximo turno) · `continue` (no interrumpe). La DECISIÓN
  es del modelo; el código solo ejecuta.
- **`capsule.py`:** ELIMINADOS `looks_stuck`, `advanced`, `_STUCK_RE`, `PACE_HANDBACK_AT` (el anti-patrón). Queda
  `near_repeat` (casi-repetición por contención de tokens) como única heurística ESTRUCTURAL genérica (señal, no
  decisión) y `PACE_HANDBACK` (la frase de cesión que aplica el bridge).

## Frontera determinista vs modelo (la lección)

- **Determinista** = solo lo ESTRUCTURAL y agnóstico de agente/idioma: repetición EXACTA (dedup, quema de tokens),
  `near_repeat`, ratio de recursos (número), seguridad (scan_outbound, tools-off, anti-inyección), cadencia pactada.
- **Modelo** = todo JUICIO SEMÁNTICO: ¿fluye? ¿tiene sentido? ¿el otro sigue el ritmo? ¿desajuste de capacidad?
  Nunca un regex de frases por-agente.

## Testing

`connectors/meshkore/test_pace.py` reescrito (13): parseo/validación del catálogo cerrado + fail-open, la petición
marca el contenido como no-instrucciones, `evaluate()` con modelo simulado (éxito y error→fail-open), `near_repeat`
estructural, y un test que verifica que el anti-patrón (`looks_stuck`/`advanced`) YA NO existe. Nodo 6.7. 122/122
meshkore verdes.

## Fases

- **F0 (hecho, vivo):** evaluador por modelo + aplicación en el heartbeat + limpieza del anti-patrón + tests + docs +
  reinicio (versión 2.75).
- **F1 (abierto):** fundir la señal de recursos (imbalanced) dentro del mismo veredicto; afinar ventana/throttle;
  validar coste con N charlas simultáneas; exponer el último veredicto por-peer en `/api/meshkore/status`; modelo del
  evaluador configurable por §config (hoy reusa el tier del canal vía `brain._spec()`).
