# V2-053 — «Susurro»: auto-auditoría conversacional y mejora continua (F1 CONSTRUIDO · F2/F3 pendientes)

**Origen (operador, 2026-07-17):** tras 4 rondas de test→fix recursivo, la observación estratégica: *"cada vez que
pasamos los tests salen errores… eso significa que no estamos haciendo mejoras significativas capaces de absorber
diferentes casos de uso… probablemente nos falta una pieza que permita que el sistema se autocorrija y tenga mejora
continua, más allá de colocar reglas."* Propuesta del operador: un servicio (lo llamó **"whisper"**) al que el
FlashBrain manda **conversación + eventos filtrados** y que devuelve **correcciones estructuradas** sobre el
comportamiento — reparar lo dicho, recomponer el ESTADO, dirigir procesos en marcha, tocar USER RULES — con la
cautela explícita de **NO auto-modificar el prompt de sistema** ("si se corrompiera, el agente ya no podría volver
a funcionar bien jamás").

> **Nombre:** "whisper" COLISIONA con el Whisper STT (mlx-whisper vive en el stack). Propuesta: **«Susurro»**
> (`nucleo/susurro.py`) — mismo concepto, sin ambigüedad. Pendiente de OK del operador.

Estado: **EN CURSO — GO del operador 2026-07-17** (decisiones en §4, plan de tareas en §5). Rama
`feat/v2-053-susurro` sobre la release estable `v1.8.0`.

---

## 1 · El diagnóstico: taxonomía honesta de los fallos (datos, no especulación)

**81 commits `fix`/guard entre 2026-07-12 y 2026-07-17** (~16/día con testing intensivo). Clasificados:

| Clase | Ejemplos reales | % aprox | Cómo se arregló |
|---|---|---|---|
| **A · Routing/comprensión del turno** (el no-razonador elige mal tool/acción) | juego→`play_video` en vez de show; "créame un widget"→show_widget; "para todas las tareas" silencioso; respuesta-a-worker→escalada nueva; lang-lock rechazaba inglés; "pongas a Bruce"→reloj; memoria-Q→`widget_data` (grok) | **~55%** | Guard determinista nuevo o retoque de descripción de tool |
| **B · Contexto/estado desincronizado** | escalada sin conversación reciente; `memory_cache` pisando estado con vacío; canvas desync; ventana sin sembrar | ~15% | Costura determinista (adjuntar/sembrar/reconciliar) |
| **C · Escritura de memoria imprecisa** | olvido con coletilla "al final no"; email malformado durable; petición reificada como identidad; nombre garbleado | ~15% | Gates de precisión (V2-033/V2-050) |
| **D · Infra/proveedores** | LiveKit ICE; AIMLAPI 403/Groq 429; mem_processor apuntando a un Ollama inexistente | ~10% | Config + verificación por curl |
| **E · Toolkit gaps** | `select_option` para formularios; presupuesto research | ~5% | Añadir la pieza |

**La conclusión que el operador intuye es correcta y medible:** la clase A domina, y su patrón de arreglo es
**lineal** — un guard/retoque por casuística. El FlashBrain es (por regla dura) un no-razonador: no generaliza a
partir de N ejemplos de guard; cada conversación nueva del mundo real trae una variación que ningún guard cubre.
C y B ya tienen su sistema propio (gates del CORAZÓN, costuras deterministas) y su tasa de fallo BAJA con cada
ronda. **A no baja — es la clase para la que falta la pieza.** D/E no son de inteligencia.

Lo que el bucle test→fix NO puede hacer: estar presente en las conversaciones REALES del operador. Hoy el único
"auditor" del sistema en vivo es el propio operador quejándose — y su queja se pierde como un turno más.

## 2 · Encaje: el 70% del Susurro YA está construido (patrón V2-046)

Como en el sistema-arena, la visión no exige un sistema nuevo — exige **conectar costuras existentes**:

| Pieza de la visión del operador | Qué EXISTE hoy | Hueco real |
|---|---|---|
| "mandarle eventos filtrados junto con el diálogo" | **V2-044 trazas**: cada estímulo nace con `trace` id y TODA su cadena (tools, tags, rails, workers, memoria) llega sellada; `memory.recent_window` = conversación verbatim | Un ensamblador `susurro.compose_audit_window()` que junta ambos y comprime (~2-4k tokens). Trivial |
| "modelo poderoso que devuelva correcciones estructuradas" | El patrón exacto ya corre en producción: el **CORAZÓN** (`mem_processor`) = LLM off-hot-path que devuelve JSON estructurado con catálogo cerrado de decisiones, fail-open | El Susurro es el **hermano CONDUCTUAL del CORAZÓN**: mismo esqueleto (cliente + prompt + catálogo + validación), otro dominio |
| "que el FlashBrain las entienda sin mucho jaleo" | **`brain_notes` [SISTEMA]** ya inyecta notas al siguiente turno; `set_state` parchea el ESTADO; **`memory.add_user_rule`/`remove_user_rule`** (V2-046 A1, construido) persisten reglas; `dispatch.inject_soon/cancel_soon` dirigen workers | Casi ninguno: **la mayoría de correcciones se aplican MECÁNICAMENTE** sin pasar por el modelo de voz; solo la frase de reparación va por [SISTEMA] |
| "recomponer el estado" | `memory.set_state()` + el visor 🧠 para verificar | Allowlist de campos parcheables (NUNCA identidad — mismo criterio que los workers) |
| "solo cuando el operador se queja / o cada X mensajes" | `escalate` ya deduplica peticiones repetidas (señal de insistencia); V2-047 tiene el concepto de turno-de-corrección; rails marcan `sin_resolver`; el fast client marca turnos degradados | Un **detector de FRICCIÓN determinista** que agregue esas señales existentes + léxico de queja |
| "no modificar el prompt de sistema" (cautela) | Doctrina V2-046 ya lo consagra: **BRAIN RULES se cambian por desarrollo, nunca por el uso** | Nada — el diseño lo respeta por construcción (§4) |

## 3 · Diseño propuesto

**`nucleo/susurro.py`** — auditor conversacional off-hot-path. Un ciclo = *(disparador) → ensamblar ventana →
LLM potente → correcciones estructuradas → aplicadores mecánicos*. Fire-and-forget, fail-open, NUNCA en el turno
(V2-011 intacto: la voz no espera al Susurro jamás).

### 3a · Disparadores (híbrido, en este orden de prioridad)

1. **FRICCIÓN (principal, determinista, gratis):** el detector agrega señales que YA existen —
   (a) léxico de queja/corrección en el turno ("te he dicho", "otra vez", "no era eso", "¿me estás escuchando?",
   "te lo pedí hace rato"); (b) la MISMA petición repetida ≥2 veces en la ventana (el dedup de escalada ya lo ve);
   (c) rail/worker `sin_resolver` o timeout; (d) turno degradado del fast client (fallback "se me ha ido un
   momento"); (e) barge-in inmediato repetido (el operador corta a zaelar 2+ veces seguidas). Cualquiera dispara
   una auditoría del tramo con su trace.
2. **PULSO (secundario, barato):** cada N turnos (def. 8, configurable) o al cerrarse la ventana de atención,
   una auditoría ligera del tramo desde la anterior. Apagable (`susurro.pulse=0`).
3. Jamás dos auditorías solapadas (lock + coalescing, como el consolidador).

### 3b · Entrada

`compose_audit_window()`: conversación reciente verbatim (`memory.recent_window`, cap agresivo) + **eventos
filtrados por trace** (tool calls con args resumidos, tags, escaladas+fases de worker, rails, errores, latencias
anómalas, correcciones de memoria) + ESTADO actual compacto + catálogo de widgets abiertos. Comprimido ~2-4k tokens.

### 3c · Salida = catálogo CERRADO de correcciones (JSON validado, como el CORAZÓN)

| Tipo | Qué hace | Aplicador (mecánico) | Riesgo |
|---|---|---|---|
| `repair_say` | Frase de reparación/disculpa contextual ("antes te dije X; era Y") | `brain_notes` [SISTEMA] → sale en el siguiente turno con naturalidad | Bajo |
| `state_patch` | Corregir ESTADO polucionado (tema, situacional) | `memory.set_state` sobre **allowlist estrecha** — NUNCA identidad (mismo veto que workers) | Medio → allowlist |
| `user_rule` add/remove | "El operador quiere respuestas más cortas por la noche" | `memory.add_user_rule`/`remove_user_rule` (V2-046, ya construido: cap 8, dedup, retirable por voz) | Bajo (capa mutable DISEÑADA para esto) |
| `worker_action` | Redirigir/parar un worker desviado del objetivo real | `dispatch.inject_soon`/`cancel_soon` | Medio → solo inject de contexto + stop, nunca lanzar |
| `memory_fix` | Superseder una píldora errónea detectada en conversación | Vía `memory_agent` con TODOS los gates vigentes (escritor único intacto, identidad vetada) | Medio → mismos gates que un worker |
| `finding` | Hallazgo que NO debe aplicarse en runtime: propuesta de cambio de BRAIN RULES, guard nuevo, descripción de tool, bug | **Cola persistente** (`.meshkore/logs/susurro/findings.jsonl` + evento bus) que consume el **bucle de desarrollo** (cron test→fix / sesión de agente) | Cero en runtime |

El prompt del Susurro declara este catálogo con sus límites (exactamente lo que pidió el operador: "indicarle
cuáles son las posibilidades que tiene a la hora de responder"). Todo lo que no encaje → `finding`, nunca acción.

### 3d · La línea roja — mejora continua SIN auto-modificación de la genética

La cautela del operador es correcta y se eleva a **invariante**: el Susurro **JAMÁS modifica BRAIN RULES en
runtime** (prompt de sistema, descripciones de `router.TOOLS`, guards). Un auto-modificador corrompido no tiene
punto fijo: corrompería también al corrector. El circuito de mejora continua queda en DOS velocidades:

- **Runtime (segundos):** correcciones sobre la capa MUTABLE diseñada para ello — ESTADO, USER RULES, workers,
  memoria. Reversibles, capadas, con gates.
- **Desarrollo (horas):** los `finding` alimentan el bucle test→fix (el cron ya existe) — el agente de código los
  convierte en guards/tools/prompts CON tests + alignment review + git. La genética solo cambia por desarrollo.

Esto ES el aprendizaje continuo que pide el operador: cada conversación real se convierte en un caso de test
vivo, sin el riesgo de corrupción irreversible.

### 3e · Modelo y coste

Off-del-camino-de-voz → **aquí SÍ puede ser un razonador** (la regla dura solo veta el path de voz). Candidatos a
BENCHMARK (doctrina: pruebas, no especulación — añadir §10 a `zaelar-model-benchmarks.md`): gpt-5.x mini / o-series
mini vía OpenAI (coherente con la directiva "memoria SIEMPRE OpenAI"), GLM vía Z.AI (ya en el stack del juez).
Coste estimado: ~3k in + ~500 out por auditoría; con fricción + pulso c/8 turnos ≈ **céntimos/día** — el propio
operador ya aceptó el trade-off ("quizás no tanto gasto si comprimimos").

### 3f · Observabilidad y seguridad

- Evento `susurro` en el observer (disparador, latencia, nº correcciones por tipo) + chip en /debug con su trace.
- Cada corrección aplicada se registra en `memory.journal` con procedencia `source="susurro"` → auditable en el 🧠.
- Fail-open duro: sin key/timeout/JSON inválido → no pasa nada (la conversación ni se entera).
- El Susurro solo ve conversación del OPERADOR (trust operator); NUNCA contenido `untrusted` de cluster (la
  cuarentena anti prompt-injection se respeta — si no, un peer podría inyectar "correcciones").

## 4 · Decisiones del operador (GO, 2026-07-17)

El operador dio el **GO** con estos requisitos adicionales (verbatim resumido):

1. **Modularidad PRIMERO**: antes de añadir la pieza, revisar la arquitectura — "asegurando que todas las piezas
   son modulares… aisladas, que se manejan desde los orquestadores y que tienen ciertos puntos de conexión, ya sea
   a través de eventos, de llamadas/requests o de puntos como la base de datos" — y que el Susurro se pueda
   **desactivar perfectamente** (kill-switch de 1ª clase).
2. **Observabilidad TOTAL**: "todas esas correcciones, incluso los registros de ENVÍO y RESPUESTA de esos modelos
   más potentes, tienen que quedar registrados en los eventos" — eventos en la línea del tiempo con el payload de
   la petición y de la respuesta del LLM auditor, para poder valorar "lo que le mandamos, lo que recibimos y lo
   que se acaba corrigiendo".
3. **Antes/después**: eventos que digan "las reglas del usuario estaban ASÍ / los datos del rail estaban ASÍ →
   después del cambio, ESTE es el resultado" — snapshot previo y resultante de TODO lo que el Susurro toque
   (incluidas, en F3, las píldoras de memoria: dato previo + dato resultante, solo de lo tocado).
4. **Config**: el modelo del Susurro entra en la configuración (config/v2.json §susurro + área ⚙ V2-043).
5. **Tests de integración, no solo unit**: grupo ESPECIAL "susurro" en los workloads de testing actuales, para
   monitorizar cómo el modelo potente discierne los problemas y corrige — y medir la MEJORA del sistema en el tiempo.
6. **Findings → instancia de Claude Code**: "se puede utilizar una instancia de Claude Code para escribir y
   aplicar todo eso" — la cola de findings la consume el bucle de desarrollo (cron test→fix / worker CC).
7. **Alcance por fases**: F1 solo sobre el FlashBrain y la comprensión de instrucciones del operador (cualquier
   fuente de input: voz, texto, canales externos — el Susurro audita las ACCIONES derivadas, no el transporte);
   escalar después a la ejecución/ajuste de widgets (funcionalidad diseñada por usuarios que se comporta mal).
8. **Release estable previa**: código commiteado+pusheado+etiquetado antes de empezar → **`v1.8.0`** (2026-07-17).
   Trabajo en rama **`feat/v2-053-susurro`**, merge a main al terminar (autorizado).

Decisiones §5 viejas resueltas: nombre **«Susurro»** (evita colisión con Whisper STT; renombrable si el operador
prefiere otro); disparador F1 = **fricción** + pulso configurable (off por defecto); escalera de mutación
F1→F2→F3 aprobada; modelo **configurable por UI** (default OpenAI, benchmark §10 pendiente); findings = **jsonl**
consumido por el dev-loop.

## 5 · Plan de implementación (tareas)

### T0 · Pre-flight — HECHO 2026-07-17
- [x] T0.1 Release estable `v1.8.0` etiquetada y pusheada (158 commits desde v1.7.0).
- [x] T0.2 Rama `feat/v2-053-susurro` creada y pusheada.

### T1 · Modularidad (tarea PREVIA pedida por el operador)
- [x] T1.1 Mapa de acoplamiento real de los dominios (nucleo / memory+bus / widgets / voice+provider): imports
      fachada vs profundos, señales de bus, estado global, kill-switches existentes.
- [x] T1.2 Doc canónica **`zaelar-modularity.md`** (categoría architecture): módulos, contratos de conexión
      (evento/llamada/BD), inventario de kill-switches, reglas para piezas nuevas.
- [x] T1.3 Fixes de desacoplo NECESARIOS (solo los que bloqueen la enchufabilidad del Susurro o sean violaciones
      claras; nada de refactor grande — regla de oro V2-046: no romper lo que funciona).

### F1 · Susurro sobre el FlashBrain (esta rama)
- [x] F1.1 Módulo **`nucleo/susurro/`** aislado: `friction.py` (detector determinista), `window.py`
      (`compose_audit_window`: conversación + eventos filtrados por trace + ESTADO compacto), `client.py`
      (LLM potente, config §susurro, fail-open), `catalog.py` (schema JSON cerrado + validación),
      `apply.py` (aplicadores F1: `repair_say`→brain_notes, `finding`→cola), `engine.py` (orquestación:
      suscripción a bus, lock anti-solape, ciclo auditoría).
- [x] F1.2 Enchufe por BUS/observer (cero acoplamiento con el provider): suscripción a los eventos del turno +
      señales de fricción existentes; montado en el lifespan SOLO si `susurro.enabled` (kill-switch 1ª clase).
- [x] F1.3 Config **`config/v2.py` §susurro** (`enabled`, `provider/model/base_url/api_key` con resolución por
      endpoint, `pulse_turns` def 0=off, `max_window_tokens`) + catálogo en `server/config_api.py` (área ⚙).
- [x] F1.4 Observabilidad TOTAL: eventos observer `susurro` con subtipos `trigger` (motivo+señales),
      **`request` (payload ENVIADO al LLM)**, **`response` (respuesta CRUDA)**, `apply` (por corrección:
      tipo + **snapshot ANTES → DESPUÉS**), `skip`/`error` — todos con trace id, al timeline + /debug + bus/log.
- [x] F1.5 Cola de findings `.meshkore/logs/susurro/findings.jsonl` (append-only, dedup por hash) + evento bus
      `susurro.finding` para el dev-loop.
- [x] F1.6 Tests unit (fricción es/en, ventana, validación de catálogo, fail-open, kill-switch) — colocados
      junto al módulo (patrón test_*.py de nucleo/flash/).
- [x] F1.7 **Grupo de integración "susurro"** en el workload de testing: escenarios probe que SIMULAN fricción
      (queja tras acción errónea, misma petición ×2, corrección "no era eso") y verifican por /events que el
      Susurro disparó, qué mandó/recibió y qué corrigió; + métrica longitudinal (nº fricciones/sesión) para
      medir la mejora del sistema en el tiempo. Anclado a `zaelar-testing.md`.
- [x] F1.8 Docs-sync completo: CLAUDE.md (módulo + decisión clave), `zaelar-architecture.md`, **diagrama
      `/architecture`** (nodo Susurro en pestaña FlashBrain + Sistema, modelo-en-uso, sello Actualizado),
      `zaelar-observability.md` (eventos nuevos), `zaelar-model-benchmarks.md` §10 (candidatos a medir).
- [x] F1.9 Revisión de alineación (`zaelar-alignment-review.md`) + merge a main + push.

### F2 · Correcciones activas (siguiente)
- [ ] F2.1 Aplicador `user_rule` add/remove (vía memory.add_user_rule/remove_user_rule) con antes/después.
- [ ] F2.2 Aplicador `worker_action` (inject/stop vía dispatch, marshaleo cross-loop) con antes/después de fase.
- [ ] F2.3 Escenarios de integración F2.

### F3 · Estado y memoria (después, con gates)
- [ ] F3.1 `state_patch` con ALLOWLIST estrecha (identidad vetada) + snapshot antes/después.
- [ ] F3.2 `memory_fix` vía memory_agent (mismos gates que un worker; journal `source="susurro"`) + registro del
      dato PREVIO y RESULTANTE de cada píldora tocada (solo lo tocado).
- [ ] F3.3 Pulso periódico por UI; benchmark de modelo §10 ejecutado.

### F4 · Escalado de alcance (futuro, placeholder)
- [ ] F4.1 Auditoría de EJECUCIÓN de widgets (criterios de triaje, playlists, funcionalidad generada por usuarios
      que se comporta mal) → correcciones vía `[[modify]]`/generator con gate.
- [ ] F4.2 Findings auto-aplicados por worker Claude Code (con tests + gate humano/CI).
- [ ] F4.3 Susurro ∪ memoria auto-evaluativa T5 (V2-031).

## 6 · Bitácora

- **2026-07-17 (batería de pruebas del operador)** · Test general del sistema (7/7 rutas core verdes, gpt-4o-mini
  sin el bug de grok) + batería de fricción del Susurro (3 escenarios) leyendo la nueva observabilidad. La batería
  destapó 3 hallazgos, los 3 ARREGLADOS:
  - **Detector de fricción, gap 1:** «eso está mal, no es así» no disparaba → añadido `no es así` como señal débil
    (9/10→10/10 quejas, 0 falsos positivos, incluso «no está mal»=elogio y «así es»=acuerdo).
  - **Detector de fricción, gap 2:** «te lo estoy preguntando otra vez» (presente continuo) no disparaba → patrón
    fuerte `te lo estoy pidiendo/preguntando/diciendo/repitiendo`.
  - **Contaminación de la ventana de auditoría (el importante):** un escenario diagnosticaba el fallo de OTRO
    anterior porque los anillos de turnos/eventos son GLOBALES → acotado por RECENCIA (`recency_window_s`, def 120s)
    + `ts` en el anillo de eventos + nudge en el prompt del auditor («el sujeto es la fricción MÁS RECIENTE; lo
    anterior es contexto»). Verificado: con anillo limpio (1ª fricción tras reinicio) el diagnóstico es LIMPIO
    (habla solo del tema real). **Limitación conocida (F1):** dos fricciones DISTINTAS separadas por MENOS de
    `recency_window_s` aún pueden conflarse en el diagnóstico; en producción es una conversación continua (el
    solape es «contexto reciente», aceptable). Scoping por clúster-de-trace = mejora para F2/F3.
  - Diagnósticos del auditor de ALTA calidad cuando el contexto es limpio (escenario reloj-vs-agenda: causa exacta,
    repair natural, finding P1 bien clasificado); ciclo ~3s con gpt-4.1-mini. Observabilidad TOTAL confirmada: se
    lee request/response/diagnóstico/correcciones de cada auditoría.
  - Hallazgo colateral (NO del Susurro): el FlashBrain alucinó el nombre «Johnny» en un saludo aunque el ESTADO
    tiene «Ricart Juncadella» correcto → es exactamente el tipo de fallo que el Susurro capturaría con una queja;
    anotado, no es dato polucionado (el estado está bien).

- **2026-07-17** · GO del operador (§4). v1.8.0 etiquetada; rama creada; audit de modularidad lanzado (4 dominios
  en paralelo).
- **2026-07-17 (tarde)** · **T1 + F1 COMPLETOS.** T1: doc canónica `zaelar-modularity.md` (fachadas, contratos de
  evento, kill-switches, violaciones+estado, checklist) + 5 fixes de desacoplo (fachada pública
  `widgets.server_api.run_widget_hook`, lazy import messaging→widgets, docstring duo.py muerto, `__all__` en
  `memory/api.py`, **topic semántico `turn.completed`** desde `observer.turn_detail`). F1: módulo
  `nucleo/susurro/` completo (friction/window/catalog/client/apply/engine) + config §susurro + área ⚙ + lifespan
  con kill-switch + paridad probe (drena brain_notes) + 13 tests unit + suite e2e
  `tests/agent_headless/e2e/susurro/run_probe_suite.py` (histórico `history.jsonl`) + escenario `susurro_reparacion` en la
  batería de voz. **Verificado e2e EN VIVO** (server reiniciado, OpenAI real): queja simulada reloj-vs-agenda →
  diagnóstico correcto («abrió el reloj en lugar de la agenda») → `repair_say` hablado en el turno siguiente +
  finding P1 en la cola; ciclo 2.4-2.9s con gpt-4.1-mini. Docs-sync completo: CLAUDE.md (módulo + decisión
  clave), zaelar-architecture §5f, zaelar-observability (kind susurro + turn.completed), zaelar-testing (grupo
  susurro), benchmarks §10, cluster.yaml, diagrama /architecture (nodo Susurro + ruta al bus + MODELOS EN USO
  corregidos al estado real 2026-07-17 —gpt-4o-mini voz, gpt-4.1-mini memoria— + sellos). De paso el diagrama
  tenía DRIFT de modelos del cambio de la mañana (grok/qwen) — corregido.
