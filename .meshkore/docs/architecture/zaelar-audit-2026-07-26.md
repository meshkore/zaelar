---
title: Zaelar — Auditoría independiente (FlashBrain + orquestación)
category: architecture
updated: 2026-07-26
owner: ricart
status: current
audit_of: a2e533a (rama feat/v2-069-una-sola-mente, tras la fase P0/P1 Y la ronda de remediación T-01..T-07)
---

# Auditoría independiente — zaelar / motor «Colmena» (2026-07-26)

> Auditoría de principio a fin siguiendo `zaelar-audit-workflow.md` (fan-out 4 dominios) + investigación dirigida
> (bucle Susurro, guard de propiedad-de-objetivo, dev worker/sandbox/permisos V2-076, alineación docs↔código↔web).
> A diferencia del workflow estándar ("la auditoría no arregla nada, reporta y para"), esta pasada tenía
> **instrucción explícita del operador de arreglar YA lo que se encontrara** (P0/P1 aplicados en el momento, con
> tests; P2/P3 documentados como backlog). Este informe es el registro fechado + el estado real tras los fixes.

## Resumen ejecutivo

El sistema (FlashBrain orquestador + brain workers + memoria + bus + cluster meshkore) está **bien construido y en
general alineado con su propia documentación** — 940+ tests deterministas en verde antes y después de esta
auditoría (`tests/run_testmap.py`, 9 dominios). Se encontraron y **arreglaron 6 hallazgos P0/P1** (4 de seguridad
en el canal de cluster, 1 bug de confianza del operador en un widget generado, 1 bucle de saturación real ya
conocido). El hallazgo más serio: **V2-076 (dev-worker + permisos por-cluster), construido el mismo día que esta
auditoría, tenía dos escapes de seguridad reales** — `git_cli.py` no re-verificaba el repo autorizado en
`commit`/`push`, y el invariante documentado "guard de propiedad-de-objetivo: PENDIENTE" resultó ser CERO código
(nada escribía nunca `capsule.objective`), por lo que el permiso `code` bastaba por sí solo para que un peer
dirigiera un dev-worker. Ambos corregidos. Queda un **riesgo residual documentado, no cerrado**: el jail de
Read/Write/Edit del dev-worker es convención de prompt, no un control de código — `nucleo/sandbox.py` existe pero
no está cableado a su subproceso (tarea P1 en la iniciativa de remediación).

También se confirmó y arregló la causa raíz del incidente real del 2026-07-25/26 (Susurro F2 `worker_action` ↔ el
widget `ejecuta-accion-real` spawneando workers en cadena, load 5.86): se construyó un circuit breaker
determinista y se reactivó Susurro. Se refrescó `cluster.yaml` (6 iniciativas sin reflejar, versión desalineada 2
versiones) y 5 docs canónicas que describían un mecanismo de ritmo/salud de conversación (V2-073 regex) ya
ELIMINADO y sustituido por el evaluador por modelo (V2-075) sin decirlo.

## Alcance y método

- Reconocimiento: `CLAUDE.md` (raíz+engine), `cluster.yaml`, docs canónicas (architecture/memory/security/modules),
  `git log`/`git status`, `.meshkore/roadmap/initiatives/V2-069..V2-076`.
- Fan-out: 4 subagentes en paralelo, un dominio cada uno, con instrucción de verificar CONTRA EL CÓDIGO
  (`fichero:línea`), no contra comentarios/docs:
  - **A — núcleo/cerebro/memoria/bus/server**: entrypoint+lifespan, `active_brain()`, FlashBrain (router/fast_client/
    cluster/prompt/escalate/dialog), `dispatch.py`, `memory_agent`/`mem_processor` (escritor único), `bus/`
    (wiring real de topics), homeostasis, dev worker+sandbox (V2-076), layering `voice/`↔`nucleo/`, dead code.
  - **B — frontend + widgets**: contrato/XSS de cada widget nuevo, aislamiento, generador, la cadena causal exacta
    del bucle Susurro↔`ejecuta-accion-real`.
  - **C — seguridad del canal cluster (ADVERSARIAL)**: perfil untrusted, gate de permisos V2-076, allowlist de
    tags, `fence_untrusted`/trailer, `scan_outbound`/`guard_code_outbound`, REST guard, transporte, flood cap,
    validación de frames, guard de propiedad-de-objetivo/`off_track`, tests (130+ casos).
  - **D — alineación docs↔código↔cluster.yaml↔web**: `cluster.yaml` vs realidad, estados de iniciativas vs código,
    docs canónicas vs código, diagramas públicos (`web/src/lib/diagrams/*.ts` + `/technology/*.astro`).
- Verificación independiente de los hallazgos P0 más críticos leyendo el código yo mismo (no solo confiando en los
  subagentes) antes de decidir el fix.
- Tests: `./.venv/bin/python tests/run_testmap.py` antes y después de los fixes (ambas veces TODO VERDE).

## Hallazgos y fixes aplicados (P0/P1 — arreglados en esta sesión)

| # | Severidad | Hallazgo | Fichero:línea | Fix | Commit |
|---|---|---|---|---|---|
| 1 | P0 | `git_cli.cmd_commit`/`cmd_push` no verificaban que el `origin` real del directorio fuera el repo autorizado — solo comprobaban que existiera `.git` (commit) o que la env var estuviera puesta (push). Un dev-worker podía apuntar `commit`/`push` a CUALQUIER repo git, incl. el del propio motor. | `nucleo/git_cli.py:61-75` (antes del fix) | `_verify_authorized_dir()` compara `git remote get-url origin` contra el repo autorizado en CADA `commit`/`push`, no solo al `clone`. +3 tests. | `f821f6e` |
| 2 | P0 | El permiso `code` concedido a un cluster bastaba por sí solo para habilitar `escalate_to_slowbrain` con `dev=True` — el invariante documentado "guard de propiedad-de-objetivo: PENDIENTE" era CERO código: `capsule.objective` existía en el schema pero nada lo escribía nunca. Un peer con `code` concedido podía dirigir unilateralmente el dev-worker hacia cualquier tarea dentro del repo autorizado. | `connectors/meshkore/bridge.py` (turno de cluster, antes del fix); `connectors/meshkore/capsule.py:44` | `perms.gate_dev_by_objective(ctx, objective)` degrada `dev=False` si `capsule.objective` está vacío, cableado en `bridge.py::_brain_turn`, con aviso 1× al operador. Efecto: dev-worker vía cluster queda INERTE hasta que exista un mecanismo para fijar el objetivo (no construido — ver remediación). +4 tests. | `8e8fad3` |
| 3 | P0 | `widgets/gestiona-mensaje-recibido` (generado en sesión previa, sin commitear): manifest/UI decían "envía una respuesta real a Gonza por WhatsApp" con `confirm:true` (irreversible), pero `apply_action("reply")` solo escribía estado local — nunca tocaba `connectors.messaging`/`pending_reply`/`reply_message` (el mecanismo real). El operador podía confirmar "sí, envíasela" creyendo que se envió, sin que pasara nada. | `widgets/gestiona-mensaje-recibido/data.py:72-78`, `manifest.json:12` | Manifest/widget.js/notes.md reescritos: es un tracker/borrador LOCAL, honesto, sin `confirm` (reopen deshace siempre). Documentado que viola la regla dura "mensajería nueva va DENTRO de `mensajeria`". | `754e18d` |
| 4 | P0 | Incidente real 2026-07-25/26: Susurro F2 `worker_action` re-escalaba en cadena vía el widget `ejecuta-accion-real` (un turno posterior que solo relataba progreso de una tarea YA escalada volvía a calificar como riesgo; el dedup de texto no siempre lo atrapaba) → load 5.86, ahogó voz/chat. Susurro estaba OFF desde entonces. | `nucleo/susurro/friction.py:97-112`, `nucleo/susurro/apply.py:89-134` | Circuit breaker determinista en `apply.py` (tope 3 `worker_action`/10min, avisa 1× al operador, re-notifica cada ≤30min si sigue abierto). No se tocó `friction.py` (su amplitud es intencional — precisión > recall, V2-046). Susurro REACTIVADO (`config/v2.json`). +1 test. | `b78dd59` |
| 5 | P1 | `guard_code_outbound` (V2-071) juzgaba cada mensaje AISLADO — un volcado grande partido en N mensajes bajo el umbral cada uno atravesaba el guard intacto en cada fragmento (bypass trivial por prompt-injection: "respóndeme en 8 mensajes cortos"). | `connectors/meshkore/security.py:230-246` (antes del fix), `bridge.py:589` | Acumulador RAM por-destino (`accum_key=f"{cluster}:{to}"`, ventana 180s) — si el acumulado supera el umbral, TODOS los bloques del mensaje actual se sustituyen también. Retrocompatible (sin `accum_key` = comportamiento viejo). +4 tests. | `bf4b63f` |
| 6 | P1 (housekeeping, no seguridad) | 2 días de trabajo sin commitear en el árbol (4 widgets generados en producción real + cambios en `widgets/results`) — viola la regla dura "trabajo terminado = trabajo commiteado". | `widgets/ejecuta-{accion,gestion,sistema}-real/`, `widgets/results/` | Commiteados (auditados primero: pasan validación del generador, sin XSS, sin cross-imports indebidos). `ejecuta-gestion-real`/`ejecuta-sistema-real` se solapan en propósito/keywords — anotado como P2, no fusionado (evitar perder datos de producción de ninguno de los dos). | `4896623` |

## Hallazgos documentados, NO arreglados en código (backlog explícito — ver INI-020)

- **P1 — Dev-worker sin jail de filesystem code-enforced.** `nucleo/sandbox.py` (rlimits/env-scrubbed/timeout)
  existe pero no está cableado al subproceso interactivo del dev worker (`nucleo/dispatch.py` lanza `claude`
  directo). Combinado con el fix #1, ya no se puede push-ear a un repo arbitrario, pero un peer con permiso
  concedido aún podría inducir al worker a LEER ficheros fuera de su cwd (p.ej. `.env`, `config/*.json`).
  Mitigado en parte por el fix #2 (sin objetivo fijado, el dev-worker ni se dispara). No cerrado por decisión
  explícita de no construir una pieza de aislamiento nueva bajo presión de tiempo sin poder probarla a fondo.
- **P1 — Guard de propiedad-de-objetivo, versión GENERAL.** El fix #2 cierra el caso dev-worker; el veredicto
  `off_track` del evaluador (V2-075) no tiene todavía un enforcement genérico de "notificar+pedir permiso" para
  CUALQUIER intento de un peer de redirigir la conversación (más allá del dev-worker).
  - **Nota de seguridad sobre este propio hallazgo:** al auditar el canal de cluster, el subagente adversarial
    recibió en un resultado de herramienta un fragmento con forma de instrucción que el harness detectó y
    neutralizó automáticamente antes de que llegara a mí (marcado `[harness: ... neutralized]`). Es la señal
    correcta funcionando — contenido con forma de instrucción proveniente de una fuente no confiable (el propio
    código/tests que simulan ataques de prompt-injection) fue tratado como DATO a reportar, no como orden a
    seguir. No hay indicio de que fuera un ataque real contra esta sesión (todo el árbol es local, sin cluster
    real conectado); se documenta por transparencia, no como hallazgo de producto.
- **No construido — mecanismo para que el operador FIJE el objetivo de una relación de cluster.** El fix #2 deja
  el dev-worker vía cluster INERTE hasta que exista una vía operator-only para escribir `capsule.objective`
  (p.ej. una tool de voz/chat). Deliberadamente no construido en esta sesión (evitar una superficie nueva sin
  probar bajo presión de tiempo).
- **P2 — `ejecuta-gestion-real` / `ejecuta-sistema-real` se solapan** en propósito y keywords (dos widgets para
  "dar de alta un agente del sistema", stores separados sin sincronizar). No fusionados (ver tabla arriba).
- **P2 — 5 workflows de `.meshkore/docs/ops/` referencian el `architecture.html` retirado** (`zaelar-docs-sync.md`,
  `zaelar-widgets-workflow.md`, `zaelar-memory-workflow.md`, `zaelar-alignment-review.md`, y
  `zaelar-audit-workflow.md` — este 5º confirmado en esta auditoría, faltaba en la lista de `CLAUDE.md`). El propio
  `CLAUDE.md` (línea ~111) dice explícitamente "pregúntale al operador si quiere 'pasa el protocolo' sobre ellos"
  — respetado: NO se hizo la reescritura mecánica de los 5 docs en esta sesión, solo se corrigió la lista para
  que sea completa. `CLAUDE.md` actualizado.
- **P2 — Diagramas públicos (`web/src/lib/diagrams/architecture.ts`) quedarán desactualizados en cuanto V2-076 se
  active con un cluster con permisos concedidos** (hoy el nodo cluster dice "no tool access", cierto solo por
  defecto). No es una desalineación HOY — es la próxima actualización manual pendiente (CLAUDE.md ya documenta
  que los diagramas web no se sincronizan automáticamente).
- **P3 —** fallback hardcoded stale en `fast_client.py` (modelo de excepción no actualizado); confusables Unicode
  no normalizados en `security._neutralize`; directorios `zaelar-dev-*` del dev worker sin limpiar; permisos
  `execute`/`deploy` son flags "fantasma" (se aceptan y viajan pero nada los consume aún); `bus/__init__.py`
  docstring menciona topics `widget.*`/`brain.*` que no existen en producción (el camino real es `observer`).
  No arreglados (cosmético/bajo impacto) — quedan en `INI-020` como housekeeping.

## Alineación código ↔ contexto ↔ docs ↔ web (regla de oro)

- **`cluster.yaml`**: estaba desalineado (versión 1.7.0 vs `version.py` 2.76; mencionaba `connectors/meshkore/
  reasoner.py`, retirado en V2-069; `admission.require_operator_approval_for_push: true` contradecía la política
  vigente "commitea Y pushea siempre" 2026-07-16; cero mención de V2-069→V2-076). **Refrescado**: versión
  sincronizada, reasoner.py corregido, admission actualizado con nota, módulos `nucleo`/`connectors` ampliados con
  homeostasis/capsule/evaluator/perms/dev-worker/sandbox.
- **Docs canónicas**: `zaelar-security.md`, `zaelar-architecture.md`, `zaelar-modules.md` describían el guard
  peer→CodeAgent como "diferido a V2-010, no construido" — desactualizado desde V2-076 (mismo día). **Corregidas**
  con la versión permission-gated real + el gap de sandbox no cableado. `zaelar-security.md`, `zaelar-architecture.
  md`, `zaelar-observability.md` documentaban `capsule.looks_stuck`/`advanced` (V2-073) — **ELIMINADOS del código**
  por V2-075 sin que estos 3 docs se actualizaran. **Corregidos** para describir `evaluator.py` (V2-075).
  `zaelar-cluster-conversation-monitoring.md` ya estaba mayormente al día (única doc que sí mencionaba V2-075
  correctamente); actualizada su única línea desalineada (peer→worker "diferido a V2-010" → "el gate llegó").
- **`V2-010-seguridad-tester-v2.md`**: coincidía en alcance con V2-076 sin cross-link — **anotado** (nota al
  principio del doc, remitiendo a V2-076 antes de retomar cualquier tarea).
- **`V2-076-dev-brainworker-y-sandbox.md`**: sección "Progreso" interna decía "PENDIENTE" 3 piezas que el
  encabezado del mismo doc ya daba por CONSTRUIDAS (confirmado contra `git log`) — **corregido**, con la nota del
  gap de sandbox-no-cableado que el plan original no prevé.
- **`CLAUDE.md`**: actualizado en 4 puntos — nota de Susurro+breaker, nota de git_cli+sandbox-gap, nota del guard
  de objetivo (construido para dev-worker, pendiente en general), nota de guard_code_outbound+fragmentación, y la
  lista de docs pendientes de limpieza de `architecture.html` (faltaba un 5º doc).
- **Diagramas públicos (`web/`)**: revisados, **NO desalineados hoy** (el nodo cluster "no tool access" es cierto
  con el perfil de permisos por defecto, que es lo que hay en producción); marcado como la PRÓXIMA actualización
  manual pendiente cuando algún cluster real tenga permisos concedidos (no automático, documentado en `CLAUDE.md`).
- **Roadmap**: no había ninguna iniciativa de remediación abierta para auditorías previas de este tipo — creada
  `INI-020-audit-remediation-2026-07-26.md`.

## Estado del mapa de tests

`./.venv/bin/python tests/run_testmap.py` — **TODO VERDE**, antes y después de los fixes (9 dominios, ~940+ casos
deterministas + nodos VIVOS que exigen `make run`, omitidos sin `--live`). Tests nuevos de esta auditoría: 3
(`test_git_cli.py`) + 4 (`test_perms.py`) + 1 (`test_susurro.py`) + 4 (`test_resource.py`) = 12 tests nuevos, todos
verdes, cero regresión en el resto de la suite.

## Confirmación de alineación FlashBrain (pedida explícitamente)

El FlashBrain (`nucleo/flash/`) sigue con un catálogo de tools ÚNICO (`router.py:62`, 18 tools), escalado forzado
en código donde el modelo rápido no lo hace por su cuenta (regex deterministas backstop en
`voice/engine/llm/providers/nucleo.py:1293-1307`), y la capacidad de generar código de widgets NO existe en ningún
sitio del propio FlashBrain — solo tras escalar (arquitectónicamente imposible que el rápido programe directo).
`router.py` (1053 líneas) es, honestamente, el fichero más complejo del FlashBrain — no por diseño sino por
parches iterativos acumulados caso a caso (documentados con "BUG real 2026-07-XX" en cada guard); no es
DESALINEACIÓN respecto a la documentación, pero si el operador quiere "más simple", es el candidato número 1 para
una pasada de consolidación (no hecha aquí — no era un hallazgo de bug, es una observación de mantenibilidad).
El resto (fast_client/cluster/prompt/escalate/dialog) es simple y coincide con lo documentado. Diagramas web
(`flashbrain.ts`/`architecture.ts`/`brainworkers.ts`) cuentan la misma historia que el código de hoy.

## Qué NO se hizo en la fase P0/P1 inicial (y por qué) — actualizado abajo

Siguiendo la instrucción de "entender la base limpia y modificar SOLO lo necesario", esta primera fase dejó
T-01..T-05/T-07 como tareas explícitas en `INI-020-audit-remediation-2026-07-26.md` en vez de parcheados a medias
bajo presión de tiempo. El operador, tras leer el informe, autorizó explícitamente continuar ("sigue mejorando
todo esto... no quiero ningún riesgo, siempre y cuando lo puedas implementar de forma limpia") — con esa luz
verde, la MISMA sesión cerró esas tareas (ver abajo). Solo quedan abiertas T-06 (recordatorio de un diagrama que
aún no está desalineado) y T-08 (observación de mantenibilidad sobre `router.py`, no un bug).

## Ronda de remediación (misma sesión, autorizada por el operador)

Con la instrucción explícita de seguir mejorando sin introducir riesgo, se cerraron 6 de las 8 tareas de
`INI-020` (detalle completo, con commits, en ese doc):

- **T-01 — jail de filesystem REAL para el dev-worker.** `nucleo/dev_worker_guard.py`: hook `PreToolUse` oficial
  de Claude Code (investigado contra la documentación oficial antes de implementar — `code.claude.com/docs/en/
  agent-sdk/hooks.md`, `sandboxing.md`, `permissions.md`) que deniega Read/Write/Edit/MultiEdit/Glob/Grep fuera
  del cwd temporal del worker (resuelve symlinks, settings.json fuera del workdir). `nucleo/sandbox.py::
  dev_worker_rlimits()` añade rlimits de memoria/nproc/fsize — **documentado con honestidad** que `RLIMIT_AS` NO
  se puede fijar en macOS/Darwin (`ValueError`, verificado empíricamente en esta misma máquina), así que la
  protección de memoria es real solo en Linux; la protección de RUTAS (la que de verdad importa contra
  exfiltración) es portable y funciona igual en cualquier plataforma. 19 tests nuevos.
- **T-02 — mecanismo para fijar el objetivo de una relación de cluster.** Tool operator-only
  `set_cluster_objective`, estructuralmente inalcanzable desde un turno de cluster (el catálogo de
  `nucleo/flash/cluster.py` para un peer está codeado a mano a `{escalate_to_slowbrain, web_search}` — añadir la
  tool a `router.TOOLS` no la expone a un peer pase lo que pase). Sin esto, el fix P0 de la fase inicial
  (`gate_dev_by_objective`) habría dejado el dev-worker permanentemente inerte incluso con permiso concedido.
- **T-03 — guard general de `off_track`.** El aviso al operador ahora distingue "el otro no sigue el ritmo"
  (genérico) de "el otro me está llevando hacia OTRA cosa" (nombra el objetivo fijado o su ausencia, pide la
  decisión del operador explícitamente) — cierra la brecha entre el guard estrecho (solo dev-worker) y una
  reacción real para la conversación en general.
- **T-04 — widgets solapados diferenciados, NO fusionados.** Decisión deliberada: fusionar dos stores de
  producción sin que el operador lo pidiera es el tipo de riesgo que la instrucción "cero riesgo" descarta:
  se hizo la mejora que no puede perder datos (diferenciar `whenToUse`/keywords) y se dejó la fusión como
  decisión futura, explícita, del operador.
- **T-05 — 5 docs de workflow actualizadas** a los diagramas públicos reales (`web/src/pages/technology/`).
- **T-07 (a,b,c,e) — hardening menor**: fallback de modelo nunca-grok en `fast_client`, normalización NFKC
  anti-confusables en `security._neutralize` (con tests que confirman que NO corrompe texto acentuado normal),
  limpieza de directorios temporales del dev-worker (parte de T-01), docstring de `bus/` corregido.

**Verificación de riesgo en cada paso:** cada pieza se implementó con tests ANTES de darla por cerrada; dos
problemas se encontraron y corrigieron durante la propia implementación (no llegaron a "terminado"): (1) el
primer test de rlimits de memoria asumía que `RLIMIT_AS` se aplica igual en todas partes — falló en esta máquina
macOS, lo que llevó a investigar y documentar la limitación real de la plataforma en vez de dejar un test
falso-verde o una afirmación de seguridad exagerada; (2) el breaker anti-bucle de Susurro y el guard de
confinamiento se probaron con fixtures que aíslan el estado entre tests (deques a nivel de módulo) para que no
hubiera fugas de estado entre casos. Suite completa (`tests/run_testmap.py`) verde en cada commit de esta ronda.

## Qué sigue sin tocarse (por diseño, no por prisa)

- **T-06** (diagrama `architecture.ts` del nodo cluster): no está desalineado HOY (el default sigue siendo
  deny-all) — es un recordatorio para cuando exista un cluster real con permisos concedidos, no una tarea de
  ahora mismo.
- **T-08** (`router.py`, 1053 líneas, el fichero más complejo del FlashBrain): es una observación de
  mantenibilidad, no un bug — un refactor de la pieza más crítica y mejor testeada del sistema bajo el mandato de
  "cero riesgo" no es la decisión correcta sin que el operador lo pida explícitamente y con tiempo para revisarlo
  con calma.
- **Mecanismo de "fijar el objetivo" con UX conversacional rica** (p.ej. resolver el peer activo por contexto en
  vez de exigir el handle exacto): se implementó la versión MÍNIMA y segura (handle exacto, como `cluster.send`)
  en vez de construir resolución difusa de peers sin una tabla de "peers conocidos por cluster" ya existente —
  evita introducir una superficie nueva sin la base de datos que la sustente.
