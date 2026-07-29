# V2-059 — Observabilidad ESTRUCTURADA de los brain workers

**Origen (operador, 2026-07-21):** «los brain workers abren sesiones locales de Claude Code con trabajo INTERNO
opaco; de todo ese output hay que ver cómo van las cosas. Pedir a Claude Code que informe de forma ESTRUCTURADA
del progreso y de la lista de tareas, para registrar una observabilidad CONTROLADA, actualizar el estado, y que el
FlashBrain tenga acceso a cómo está todo (por si el usuario pregunta o queremos informarle del progreso). El gráfico
—un progreso circular en el hexágono— es secundario; lo que importa son los DATOS de observabilidad para debug,
saber qué pasa, corregir y mejorar.» Detonante directo: al conducir el worker de música (V2-058) solo se veía la
fase «creando un widget», sin ver los pasos internos → costó pillar la contaminación de notas.

Estado: **CONSTRUIDO** (rama `feat/musica-spotify`, se fusiona con V2-058).

---

## Qué había
- El stream-json del worker ya se parseaba a `WorkerEvent` (`spawned/phase/step/result/done/error`), con un `step`
  RICO (V2-048: `{where, action, target}` — dónde trabaja + qué usa). Pero el `step` solo pintaba una fila del
  panel; **no se guardaba**. El handler de `progress` existía pero **nada lo alimentaba**. No había PLAN ni %.
- El FlashBrain solo recibía la `phase` coarse (una frase), sin paso/porcentaje.

## Qué se añade (dos vías, se combinan)
1. **REPORTE estructurado del worker** (lo que pidió el operador — pedírselo a Claude Code): `hbnote` gana
   `plan` y `progress`:
   - `python -m nucleo.agent_report plan "paso1|paso2|paso3"` → declara la lista de tareas al empezar.
   - `python -m nucleo.agent_report progress "<hecho>" --done N` (o `--pct P`) → avance.
   El prompt del worker (`dispatch._build_prompt` header + `_web_prompt`) lo INSTRUYE explícitamente: declara plan al
   empezar, reporta al terminar cada paso.
2. **Derivación del STREAM** (sin depender del modelo): cada `tool_use` → `step` rico ya se guarda en el registro
   (`SessionRecord.steps`, anillo cap 12) → actividad REAL aunque el worker no reporte.

## Dónde queda el dato (registro RAM = fuente de verdad)
`SessionRecord` gana `plan`/`done`/`pct`/`note`/`steps`. `dispatch.session_plan()` y `session_progress()` los
actualizan (desde `/api/agent/report`). Se proyecta:
- **FlashBrain**: `pending_summaries()` lleva `pct`/`done`/`total`/`note` → `prompt.live_state()` compone «TAREAS DE
  FONDO … [paso 2/4, 50%] — <nota> (llevas Ns)» → responde «¿cómo va?» con el paso real, no una frase vaga.
- **UI**: `active_sessions()` (→ `GET /api/tasks`) lleva `plan`/`done`/`total`/`pct`/`note`/`steps`. El chip del
  orbe muestra la nota + paso/% (`store.setTaskProgress`, evento SSE `task/progress`). El ring del hexágono queda
  para después (el dato ya está).
- **Debug/observabilidad**: eventos `task` kind `plan`/`progress` (+ los `step`/`note` que ya salían) → timeline +
  `/debug` + bus/log, sellados con el `trace` de la sesión (V2-044).

## Invariantes
- Fail-soft TOTAL: si el worker no reporta, se ve la actividad derivada del stream; si el stream calla, la fase +
  el tiempo. Nunca rompe al worker ni la voz.
- No floodea: `sync_state` sigue coalescada (~1 Hz); los `step` son un anillo (cap 12); el chip se actualiza in-place.

## Abierto (siguiente)
- [ ] Ring de progreso circular en el hexágono/orbe (gráfico) — el dato ya viaja (`pct` en el chip y /api/tasks).
- [ ] Que el worker de curación (V2-058) reporte plan/progreso → primer consumidor real en vivo.

## Bitácora
- **2026-07-21** · Construido: `hbnote plan/progress` + `/api/agent/report` extendido + `SessionRecord`
  plan/done/pct/note/steps + proyección a `pending_summaries`/`active_sessions` + `live_state` con paso/% + chip
  de progreso en el frontend + tests. Detonado por la ceguera al conducir el worker de música.
