# V2-036 — SmartBrain conducido por Claude Code (el FlashBrain orquesta, los agentes CLI son los workers)

**Origen (operador, 2026-07-13):** las pruebas manuales mostraron que las tareas WEB "parecían tontas" porque las
conduce un bucle barato (Haiku vía API), no un agente inteligente. Decisión: los **procesos complejos los conducen
agentes Claude Code headless** (inteligencia + contexto por tarea + memoria). Al hacerlo, emerge una simplificación
de arquitectura de fondo.

## Giro de arquitectura (el corazón de esta iniciativa)

**El "SlowBrain como cerebro razonador aparte" se DISUELVE.** Antes: dos cerebros (Flash rápido + Slow razonador).
Ahora:
- **FlashBrain = ORQUESTADOR ÚNICO.** Atiende el front y las peticiones en tiempo real, responde charla, controla
  widgets, y **lanza y sigue** los procesos largos. Puede, EN EL TURNO, escalar a un modelo un poco mejor si una
  respuesta necesita más elaboración (capacidad conversacional, NO lanzar un worker).
- **Cada agente Claude Code headless = un "slow brain" POR TAREA.** Toma una tarea grande (buscar/comprar, investigar,
  informe, código, modificar widget), la conduce con su propia inteligencia + tools + acceso a memoria, y reporta.
- **`nucleo/dispatch.py` = gestor de sesiones/runner SIN cerebro.** Consume escaladas del FlashBrain, aplica el pool,
  registra las sesiones vivas, entrega resultados. Ya NO tiene `_plan` (planificación con LLM) ni el bucle Haiku del
  navegador. No razona.
- **Piezas MUERTAS (apartadas, NO borradas):** `nucleo/agentes/web.py` (orquestación vieja + `_plan`), el bucle
  DOM→visión Haiku de `widgets/navegador/agent.py`, `nucleo/agentes/otros.py`. Se mueven a `nucleo/agentes/_legacy/`
  o se marcan `_DEAD`, desenganchados del router; se decide más adelante si se borran.

Esto simplifica el sistema y el **diagrama principal** (docs-sync pendiente al cerrar): un orquestador + un pool de
workers CLI + memoria + bus.

## Requisitos del operador (invariantes de esta iniciativa)

- **P1 · Memoria concurrente, no serial-global.** "Serial" = cada sesión Claude Code trabaja LINEALMENTE (pide dato →
  recibe → sigue). Pero la memoria puede accederse **a la vez** desde el FlashBrain y desde N sesiones Claude Code —
  eso NO es problema. Lecturas concurrentes (WAL) y escrituras concurrentes (encolan; el writer serializa el I/O de
  SQLite, que es correcto). **NUNCA un lock global grueso** que serialice el acceso entre sesiones. [Puente V2-036:
  `POST /api/memory/recall|remember` + `nucleo/mem_cli` — ya cumple: recall lee directo, remember encola sin bloquear.]
- **P4 · El ESTADO y las SESIONES VIVAS SIEMPRE claros en el prompt del FlashBrain.** Cuando el operador pregunta u
  ordena ("¿cómo va la búsqueda de la moto?", "¿y el estudio sobre el universo?", "para la tarea del mercado de
  valores…"), el FlashBrain DEBE ver, en su prompt, las sesiones en curso (id + objetivo + fase) para **asociar cada
  petición/pregunta a la sesión correcta**. Es un requisito DURO tras el cambio de esta parte.
- **Pool con máximo** (`code_agent.max_parallel`, def 3; env `CODE_AGENT_MAX_PARALLEL`): no saturar equipo/tokens.
- **Comunicación constante CC→FlashBrain** por el bus: progreso (fase), datos entregables, resultados. Las sesiones
  son lentas; basta con que actualicen widgets + avisen al operador al preguntar o de vez en cuando.

## Fases

- **F1 — Fundaciones. ✅ HECHO Y VERIFICADO.**
  - Puente de memoria serial-por-sesión, concurrente entre sesiones: `memory/server_api.py` (recall/remember) +
    `nucleo/mem_cli.py` (CLI que habla por HTTP, preserva escritor único) + tool acotada en `claude_code.py`.
  - Pool (`config/v2.py code_agent.max_parallel=3`) + semáforo + **concurrencia real** del listener (`dispatch.py`
    `_run_and_deliver` bajo `_pool()`).
  - Registro de sesiones vivas en el ESTADO (`memory/state.py sessions`) + `dispatch.session_phase(tid, fase)`.
- **F1-remate — Estado/sesiones en el prompt del FlashBrain (P4). ✅ HECHO.**
  - `memory/api.py::compose_state`: inyecta SIEMPRE las sesiones vivas (id+objetivo+fase) como "PROCESOS EN MARCHA"
    para que el FlashBrain asocie cada pregunta/orden a su sesión. `memory/state.py` declara `sessions`;
    `set_state` emite `memory.updated` → el caché del prompt recompone.
  - `hbmem`/`hbnote` documentados en el prompt del worker (`nucleo/agentes/worker.py::_TOOLS_DOC`).
- **F2 — Ejecutor GENÉRICO por Claude Code + canal de reporte por el bus. ✅ HECHO Y VERIFICADO (plumbing).**
  - `nucleo/agentes/worker.py`: conduce tareas genéricas con un agente Claude Code que USA `hbmem` (memoria) +
    reporta fase con `nucleo/agent_report.py` (`hbnote`) → `POST /api/agent/report` (`nucleo/agent_api.py`) →
    `dispatch.session_phase` + observer. `ZAELAR_TASK_ID` viaja por env. Corre bajo el pool.
  - `nucleo/agentes/otros.py` PARKEADO (pieza muerta, revertible); dispatcher enruta el genérico a `worker`.
- **F3 — RECETA CONCRETA (reutiliza el owner, NO reinventa). Primitivas ya existentes en `widgets/navegador/owner.py`:**
  `TaskBrowser` (línea ~1363) ya expone TODO lo que necesita el agente: `ensure()`, `snapshot_for_agent()` (~1475,
  devuelve elementos interactivos con refs), `agent_act(action, args)` (~1512: navigate/click/type/scroll/press),
  `extract_listings(limit)` (~1601). El registro `_task_browsers[task_id]` (~489) mapea task→pestaña. Pasos:
  1. **Endpoint** `POST /api/navegador/act {task_id, action, args}` (nuevo router o en widgets/server_api) que hace
     `tb = _task_browsers.get(task_id) or TaskBrowser(task_id); await tb.ensure()` y despacha:
     `navigate/click/type/scroll` → `await tb.agent_act(action, args)`; `snapshot` → `await tb.snapshot_for_agent()`;
     `extract` → `await tb.extract_listings()`. Devuelve `{url,title,snapshot|listings|ok,msg}` (request/response
     SÍNCRONO — corre en el loop de uvicorn, igual que el owner; NO por el mailbox fire-and-forget).
  2. **`nucleo/nav_cli.py` (`hbweb`)**: CLI que lee `ZAELAR_TASK_ID` del env, postea a `/api/navegador/act` e imprime
     el snapshot/listings en texto para que el agente razone el siguiente paso. Añadir su Bash acotado a
     `_MEM_TOOLS` de claude_code.py (ya está el patrón).
  3. **`nucleo/agentes/web_cc.py`**: crea la tarea + tarjeta (`navtasks.create` + `[[show]]`), sintetiza goal_summary
     (ya existe), y corre UN `claude -p` agéntico con prompt: "conduce el navegador con hbweb para cumplir GOAL;
     tras cada acción recibes el snapshot; razona y elige la siguiente; CATEGORÍA EXACTA (enduro≠trial); al acabar
     `hbweb extract` + `hbnote`; usa `hbmem` si necesitas contexto del operador". Claude Code hace el bucle multi-paso
     ÉL SOLO (es agéntico) — su inteligencia sustituye al bucle Haiku. Timeout generoso (p.ej. 300-600s), bajo pool.
  4. **Enrutar** dispatch `kind=="web"` → `web_cc.run`. **PARKA** `nucleo/agentes/web.py` + el bucle Haiku
     (`widgets/navegador/agent.py::run_task` + `summarize_results`/`_plan`) marcándolos `_DEAD` (no borrar).
  5. Cuidado: `agent_act` usa refs del snapshot de ESE paso → el agente debe pedir `snapshot` antes de `click`. El
     login-wall determinista del owner (`_looks_like_login`) sigue protegiendo. Confirm-gate irreversible intacto.

- **F3 — WEB por Claude Code. ✅ HECHO Y VERIFICADO (plumbing).** Puente `POST /api/navegador/act`
  (`widgets/navegador/act_api.py`, reusa `TaskBrowser.snapshot_for_agent/agent_act/extract_listings`) + CLI `hbweb`
  (`nucleo/nav_cli.py`) + worker `nucleo/agentes/web_cc.py` (Claude Code agéntico conduce el navegador). Dispatcher
  enruta `kind=="web"` → `web_cc`. `web.py` + bucle Haiku (`widgets/navegador/agent.py`) PARKEADOS. Smoke-test:
  `hbweb navigate example.com` → lanzó Chromium, navegó, devolvió estado + refs. Falta validación e2e en vivo (un
  `claude -p` real conduciendo Wallapop) — es la prueba del operador.
- **F3 (histórico) — WEB por Claude Code vía puente de navegador. [hecho arriba]**
  - Puente de tools del navegador (`POST /api/navegador/act` navigate/click/type/screenshot/extract) que un CLI
    **`nucleo/nav_cli.py` (`hbweb`)** expone al agente Claude Code; el agente DIRIGE el Chromium de zaelar con su
    inteligencia (respeta categoría excluyente, filtra, decide local/amplio, login), reportando por `hbnote`.
  - Aparta `nucleo/agentes/web.py` + el bucle Haiku de `widgets/navegador/agent.py` (piezas muertas).
- **F4 — docs-sync + diagrama. ✅ NÚCLEO HECHO (2026-07-13).** CLAUDE.md: decisión «Colmena» reescrita (FlashBrain
  orquestador + workers Claude Code; SlowBrain disuelto) + nueva decisión de puentes (hbmem/hbnote/hbweb) + módulo
  `nucleo/` actualizado. Diagrama `/architecture`: pestaña SlowBrain reencuadrada a "workers Claude Code" + narrativa
  de Arquitectura + sello (2026-07-13); sirve 200 OK. Esta iniciativa. **REMATE pendiente (polish):** redibujar el
  SVG de NODOS de `/architecture` (aún pinta el modelo viejo de 2 cerebros) + tocar `zaelar-architecture.md` y
  `zaelar-memory.md` (§puente de memoria). Revisión de alineación formal al validar en vivo.

## Rendimiento — fix #1 (voz entrecortada, 2026-07-13)

Síntoma: con una búsqueda de navegador en curso, la voz se entrecortaba y el equipo iba lento. Causa: contención de
GIL — el driver de Playwright corre en el loop de uvicorn y le robaba ciclos al pump de audio (hilo del job LiveKit).
Diagnóstico del proceso: el server Python en idle está a ~0.2% CPU; el 87% del pantallazo era la búsqueda ACTIVA +
el Chrome PROPIO del operador (48%+35%+…) + superwhisper + 2 daemons meshkore, NO un bucle loco de zaelar.

**Aplicado (Python, diseño actual — sin proceso aparte, sin Rust):**
- **Snapshot del navegador en BLOQUE** (`widgets/navegador/owner.py`, `_JS_DESCRIBE`/`_bulk_metas`/`_snapshot_lines`):
  el `_describe_el` per-elemento (~7 awaits × 60 = ~420 round-trips que RETIENEN el GIL por snapshot) → **1 sola
  llamada `page.eval_on_selector_all`**. Es el hog #1 que hambreaba la voz. Se conservan los handles (click por ref).
- (ya en V2-035) escrituras del observer off-thread + cursor PIL a `to_thread` + dedup de eventos widget/navegador.
- **Barrido de HUÉRFANOS al arrancar** (`scripts/run-livekit.sh`): mata `chrome-headless-shell` + bridges sueltos de
  un kill-9 anterior (consumían CPU/RAM). Estabilidad.
- Verificado: idle 0.2% CPU, snapshot devuelve elementos correctos, 0 headless huérfanos.

**Transparencia:** esto es la realización de bajo riesgo de "sacar el trabajo pesado del navegador de encima del hilo
de voz" MANTENIENDO nuestra tecnología/diseño. El aislamiento en PROCESO APARTE (mover el driver Playwright a un
subproceso) es el fix definitivo pero exige partir la memoria de estado `navtasks` + SSE cross-process (refactor con
riesgo) → queda como siguiente paso SI, bajo una búsqueda pesada real, la voz aún se entrecorta. Rust = fuera de
alcance (decisión del operador: quedarnos en la tecnología actual).

## Notas
- El FlashBrain sigue NO-razonador en el turno; su "pensar mejor" es un 2º pase opcional a un modelo mejor, no un
  worker. Los workers (Claude Code) son los únicos que razonan en profundidad.
- Event bus: `bus/` ya existe (pub/sub + SSE). El ajuste V2-036 es el **canal HTTP de reporte** para que los
  subprocesos Claude Code publiquen al bus del proceso vivo (progreso/datos/resultados) → FlashBrain/UI/conectores.
