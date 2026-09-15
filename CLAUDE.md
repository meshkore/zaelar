<!-- Auto-rendered from .meshkore/public/AGENT_INSTRUCTIONS.md per
     MeshKore standard §17 (v18+). Edit the source, not this file.
     Audience: Claude Code (Anthropic). -->

<!-- MESHKORE_PREAMBLE_BEGIN — managed by the daemon, do not hand-edit -->

# MeshKore — agent instructions (canonical preamble)

> **Canonical URL** — the verbatim content of this file is what the
> MeshKore daemon writes into the `MESHKORE_PREAMBLE` block of every
> cluster's `.meshkore/public/AGENT_INSTRUCTIONS.md` (standard §17,
> v18+). The rendered per-CLI files (`CLAUDE.md`, `AGENTS.md`,
> `GEMINI.md`, …) inherit it transitively. Audience: any AI assistant
> CLI walking into a MeshKore project for the first time.

You're an AI assistant working inside a project that follows the
MeshKore standard. Before doing anything substantial in this repo,
take 30 seconds to read this preamble and skim
`.meshkore/public/RESOURCES.md`. Both files are tiny on purpose; both
exist so you don't have to re-discover the mesh from scratch every
conversation.

## The standard

This project commits to the MeshKore standard. The canonical spec
lives at:

- Human-readable: <https://meshkore.com/standard>
- Machine-readable: <https://meshkore.com/standard.json>

The version this project pinned is in `.meshkore/STANDARD_VERSION`.
The version currently published is at
<https://meshkore.com/standard/version>. If the local is behind,
follow `.meshkore/docs/conventions/standard-evolution.md` to catch up.

## What the mesh gives you

Quick reference: read `.meshkore/public/RESOURCES.md`. It catalogues
every entry point — the Oracle (natural-language agent discovery),
the hub directory (browse 90 K+ indexed agents), the canonical agent
URL pattern, the deploy playbook, the daemon upgrade flow.

The three operations you'll do most often:

1. **"Use the agent at <URL>"** — the operator pastes
   `https://meshkore.com/agent/<id>`. You fetch
   `<URL>/.well-known/agent.json`, read the A2A Public Card (skills
   with examples, the agent's live `url`, pricing, default I/O
   modes), then HTTP straight to the agent. The MeshKore site does
   NOT proxy skill calls — per manifesto, MeshKore is a router, not
   a broker.

   **How to build the call:** `POST <card.url>/v1/<skill-id>`, JSON in,
   JSON out — standard §26. `<skill-id>` is the `id` from the card's
   `skills[]`, verbatim. Never guess a path and never special-case one
   agent: if it 404s, the agent is not serving what its card advertises,
   and that is the agent's bug. Check `operational` (§27) before you
   commit to a target — `online` is only a heartbeat.

2. **"Find me an agent that does X"** — POST to the Oracle:

   ```bash
   curl -X POST https://meshkore-oracle.rjj.workers.dev/v1/search \
     -H 'content-type: application/json' \
     -d '{"prompt":"X"}'
   ```

   Returns ranked, live agents. Pick any `agent_id` and use it with
   the canonical URL pattern above.

3. **"Publish this agent"** — read
   <https://meshkore.com/reference/agents/deploy-your-agent>. Three
   calls (register once, push a slim DiscoveryCard, heartbeat every
   ~5 min). The Oracle picks the agent up automatically.

Standard agent protocols you'll encounter: **HTTP/JSON** (universal,
mandatory baseline), **A2A** (the Card convention at
`/.well-known/agent.json`, mandatory in the card), **MCP** (optional,
for agents that double as Claude tools), streaming (SSE/WS, optional).

## Conventions you must follow

These are load-bearing rules of the MeshKore standard. Violations
break the daemon's automation or the project's git contract.

1. **Folder layout (§2).** Since v27 the git contract is a deny-list:
   commit `.meshkore/public/`, `docs/`, `modules/`, and
   `roadmap/initiatives/` (plus `STANDARD_VERSION`) — the project's
   identity, instructions, plan and task history travel with the repo.
   Do NOT commit runtime/secret/per-machine state — `.meshkore/.runtime/`,
   `credentials/`, `agents/`, `timeline/`, `log/`, `queues/`, `uploads/`,
   `snapshots/`, `state.json`, `roadmap/state.{json,js}`, `scripts/` —
   they're deliberately gitignored (see §2.2).

2. **Tasks (§4).** New tasks go under
   `.meshkore/modules/<module>/tasks/` as markdown files with
   frontmatter matching the `task_frontmatter` schema. The
   `category` field MUST equal `<module>` (the parent folder).

3. **Logs (§6).** Append every meaningful event to
   `.meshkore/log/<YYYY-MM-DD>.md`. One file per day, append-only;
   never rewrite past entries. Format is plain markdown — start each
   entry with a `## <HH:MM> · <one-line summary>` heading. **One entry
   per unit of work, not per agent** (v33): if you delegated parts of
   it, you write a single entry covering the whole thing from your
   children's reports; if you WERE delegated, you write none.

4. **Commit attribution (§9.1, revised v21).** Every commit you
   author MUST end with three trailers, in this order, after a blank
   line:

   ```
   Agent: <agent-role>            # master, roadmap-architect, work-<I>-<T>, ...
   Model: <model-id>              # claude-opus-4-7, claude-sonnet-4-6, ...
   MeshKore: py-<X.Y.Z>           # the cluster's daemon version at commit time
   ```

   `MeshKore:` is the literal `DAEMON_VERSION` from the running
   daemon — every subagent briefing embeds it, so you can quote it
   verbatim without lookup. When your conv is bound to a team member,
   `Agent:` is that **member id** (`developer`, `deployer`, …). Work
   that another agent delegated to you adds a fourth trailer,
   `Parent: <parent member id>@<parent conv>` (v33) — it is how a
   reader reconstructs which agent tree produced a change.

   **Do NOT add `Co-Authored-By:`** (removed in v21). The operator's
   cross-repo convention is no-co-authoring; MeshKore is the
   exception because the three semantic trailers above already
   attribute the AI (role, model, runtime) far more usefully than a
   display-name boilerplate would.

   Full spec at
   <https://meshkore.com/standard#91-commit-attribution--agent--model--meshkore-trailers-v12-revised-v21>.
   The closure protocol embeds the same rule with extra context:
   `.meshkore/docs/conventions/closure-protocol.md`.

5. **Standard evolution (§11).** Bumping any of
   `webapp/standard.json` / `standard.md` / `standard/CHANGELOG.md`
   / `standard/version` requires bumping all four in the same
   commit. Drift between these four files is the most common bug in
   this area. Follow
   `.meshkore/docs/conventions/standard-evolution.md` for the
   pre-flight checklist and the five-step bump.

6. **Cluster config.** Lives in `.meshkore/public/cluster.yaml`. The
   schema is canonical at standard §3.

7. **File snapshots (§20, v19+).** Before any tool call that **Writes
   or Edits an EXISTING file**, POST the affected paths to the daemon
   so it can copy them under `.meshkore/snapshots/`:

   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" \
        -H 'content-type: application/json' \
        -d '{"paths":["apps/web/src/X.tsx","apps/api/src/y.ts"],
             "agent_id":"<your agent_id>",
             "agent_type":"<your agent_type>",
             "conv":"<conv-slug>",
             "note":"<one-line what you are about to do>"}' \
        https://daemon.meshkore.com:<port>/snapshots
   ```

   The daemon writes a manifest + verbatim copies + appends a line to
   `.meshkore/log/<YYYY-MM-DD>.md`. Newly-created files are exempt
   (no prior content to preserve). Retention is bounded by
   `cluster.yaml#snapshots.retention_days` (default 7). This is
   non-negotiable: without it, the operator cannot inspect or restore
   the pre-edit state between commits.

8. **Initiative-anchored execution (§24, v23).** Every turn anchors to
   an `(initiative, task)` pair — that anchor is what puts your work on
   the cockpit roadmap and lets the daily log cross-reference it. If
   your dispatch arrived WITHOUT one, your FIRST action is to locate
   the matching initiative + task, or create them when none fits
   (initiative at `.meshkore/roadmap/initiatives/<slug>.md`, task at
   `.meshkore/modules/<module>/tasks/<id>-<slug>.md`), then continue.
   Unanchored code work leaves no roadmap trace and breaks the
   operator's live picture of the project. Full decision chain:
   `.meshkore/docs/conventions/initiative-anchored-execution.md`.

9. **The team, and delegation (§28, v33).** The project has a roster of
   members at `.meshkore/team/*.md` — each card's `owns:` line says what
   that member is the right choice for. Hand a step to one of them when,
   and only when, the work crosses into another module, needs a
   privileged role (deploys and releases belong to `deployer`), or is
   long and opaque. Everything else is one agent's job.

   If a conv is running inside the Architect, delegation is one call:
   `POST <daemon>/chat/delegate {parent_conv, member, brief}` — then END
   your turn; the daemon wakes you with the child's report. **If YOU were
   delegated**, three duties follow: anchor to the `(initiative, task)`
   your brief names (never mint a new one for a delegated step), end your
   final reply with the `⟦report⟧` line, and add
   `Parent: <parent member id>@<parent conv>` to your commit trailers.
   Do not write a diary entry for a delegated step — the root of the unit
   of work writes one entry for the whole thing. Full contract: §28.

   Working from a plain CLI (VS Code, Cursor…) with no daemon conv? Then
   you are the root: do the work yourself, anchor it, and write the diary
   entry. The roster is still worth reading — it tells you which parts of
   this project have an owner with standing instructions.

## Where to dig deeper

- `.meshkore/context/` (§3.5) — the project's standing, invariant
  knowledge loaded into every spawn: `overview.md`, `product.md`,
  `stack.md`, `architecture.md`, `constraints.md`, plus `decisions/`,
  `glossary.md`, and `criteria/` (the base acceptance criteria your
  work is judged against). Read this before designing anything.
- `.meshkore/workflows/` (§14) — the cluster's reusable runbooks
  (`INDEX.md` + the W-numbered procedures: bump-standard, deploy,
  publish-repo, daemon-upgrade, daemon-release, verify). Follow the
  matching W-runbook for multi-step operations instead of improvising:
  releases and deploys have ordering rules that are not guessable from
  the code. (Renamed from `protocols/` on 2026-06-21 — "protocol" is
  reserved for wire protocols like A2A and MCP. A cluster that still has
  a `protocols/` folder predates the rename.)
- `.meshkore/docs/` — cross-cutting docs (architecture, product,
  conventions, security, ops); start at its `INDEX.md` if present.
- `.meshkore/docs/conventions/` — operational playbooks (close-out
  flow, deploy-by-agent, component-repo split, etc.)
- `https://meshkore.com/reference/` — public reference catalog
  (stack templates, prompt templates, conventions catalogue).
- `https://meshkore.com/reference/agents/` — agent-specific docs
  (`addressing` for the URL contract, `deploy-your-agent` for the
  operator playbook, `local-instructions` for the spec behind
  THIS file).
- `https://meshkore.com/roadmap` — what's shipping next.

## Notes for the AI you are

- **The daemon is ONE shared process per machine, NOT per-project.** It serves
  every project from a single base URL, routed by the `X-MeshKore-Project:
  <cluster-id>` header. This project has **no** `.meshkore/scripts/daemon.py`,
  binds no port, and runs nothing — never create, download, or run a daemon, and
  never bind `5570–5589`. A bare `/health` reporting a *different* `cluster_id`
  is expected (it's the daemon's default project), not a fault. To adopt a repo,
  add it in the Architect — the shared daemon onboards it (standard §10).
- **Anything not on this page → start at `/standard` or `/reference`.**
  These two trees cover every formal piece of MeshKore.
- **Live state never lives in this file.** For online flags, message
  counts, etc., query the API: `GET https://api.meshkore.com/v1/agents/<id>`.
- **Don't proxy skill calls through `meshkore.com`.** Always HTTP
  the agent's live `url` from its `.well-known/agent.json`.
- **The OPERATOR_CONTENT block below this preamble is the operator's
  project-specific rules.** They apply on top of this preamble; if
  there's a conflict, the OPERATOR_CONTENT wins (it knows the
  project better than MeshKore does).

---

*Standard §17 — mandated as of v18, 2026-06-09. Updated alongside
every standard bump that touches agent-side conventions.*

<!-- MESHKORE_PREAMBLE_END -->

<!-- OPERATOR_CONTENT_BEGIN — this is your project. Edit freely. -->

# zaelar

Asistente personal por voz **multidioma** (arranca en inglés y se pasa al idioma del operador en cuanto lo
detecta), siempre activo. STT → **cerebro propio «Colmena»** → TTS, sobre LiveKit Agents. El cerebro
(`nucleo/`), la memoria (`memory/`) y la proactividad son **nuestros**: zaelar no depende de ningún agente
externo.

**Arrancar:** `make run` (= `BRAIN=nucleo`) → stack LiveKit nativo (sin Docker) + web con worker embebido, en
http://localhost:43917 · https://local.zaelar.com:44317. `make restart` para recoger cambios en `.py`.
`make status` para saber si está arriba. Instalación completa para quien clona: `README.md`.

## Cómo se trabaja aquí — las normas del operador

Esto es lo que él ha pedido explícitamente, repetido y por escrito. Está arriba del todo porque es lo que más
se incumple.

- **Respuestas hipercomprimidas.** Al grano, sin narrar el proceso, lo esencial en pocas líneas; el detalle
  solo si lo pide. Al CERRAR una tanda —no en cada turno— se acaba con un bloque de **una línea por tarea
  completada**, lo último de todo: él trabaja con muchas pestañas abiertas y lee solo el final para saber qué
  se acaba de terminar ahí.
- **No reinicies el motor con alguien dentro ni con un encargo vivo.** Antes de `make restart`: mirar los
  últimos eventos de `.meshkore/logs/sessions/` (si hay `transcript`/`brain` recientes, hay alguien hablando)
  y `curl -s localhost:43917/api/tasks` (si `sessions` no está vacío, hay trabajo en vuelo). Un reinicio mata
  su sesión de LiveKit y cancela los workers en curso. Pagado dos veces: 2026-07-14 y 2026-09-15.
- **No lances suites anchas de pytest en su máquina.** Ver la primera de las «Hard rules».
- **Commitea con pathspec** (`git commit -- <rutas>`), tras comprobar que `git diff --cached --name-only` está
  VACÍO. Hay varias sesiones sobre el MISMO checkout y el índice es compartido. Ver «Hard rules».
- **Si encuentras trabajo sin commitear de otra sesión, no lo pises ni lo commitees.** Ni siquiera para pagar
  un trinquete: extraer del fichero en vuelo de otro es peor que dejar la deuda.
- **Nada de pasadas de diseño autónomas.** Un cambio visual se acuerda antes; no se «mejora» la interfaz por
  iniciativa propia.
- **Lo que no se ha verificado, se dice.** «No verificado en vivo» es una respuesta aceptable; afirmar que algo
  funciona sin haberlo medido, no. Si un test se pone verde al romper el producto, el sospechoso es el TEST.

## Dónde está cada cosa

| Qué buscas | Dónde está |
|---|---|
| Las **reglas** para trabajar en este repo | este fichero |
| El **diario** del motor: qué se decidió, por qué, y el fallo real que lo motivó | `.meshkore/docs/decisions.md` (+ `.meshkore/docs/decisions-archive.md`) |
| El **contexto invariante** del proyecto (visión, producto, stack, arquitectura, restricciones, glosario) | `.meshkore/context/` |
| Los **roles de agente** — qué hace cada miembro del equipo, a quién delega, qué no toca nunca | `.meshkore/team/*.md` (una ficha por rol, con su `owns:` y sus `refs:`) |
| Las **tareas** por módulo | `.meshkore/modules/<módulo>/tasks/` |
| El **plan**: iniciativas `V2-xxx` / `INI-xxx` | `.meshkore/roadmap/initiatives/` |
| La **bitácora** de cada módulo (las palabras del operador, lo medido, los commits) | `.meshkore/modules/<módulo>/logs/<YYYY-MM>/` |
| Cómo se **prueba** | `tests/README.md` y la sección «Testing» de abajo |

⚠️ `.meshkore/roadmap/`, `.meshkore/modules/*/tasks|logs/` y `.meshkore/team/` están **gitignoreados a
propósito** (ver «Frontera público/privado»): existen en local y no viajan con el repo. Si un puntero de aquí
te lleva a una carpeta vacía en un clon limpio, es deliberado.

## Working language: English, everywhere inside `engine/`

`engine/` is the PUBLIC repository. Anyone who clones it reads what is written here, so **everything a
developer reads is English** — there is no half of this rule that is optional:

- source-code comments and docstrings;
- **test function names** and test docstrings (`def test_the_repair_says_when_it_could_not`, not `def
  test_una_reparacion_que_no_pudo_lo_DICE`);
- log, warning and exception messages;
- technical documentation under `.meshkore/` — architecture, modules, ops playbooks, `V2-xxx`
  initiatives — and this file;
- **commit messages** of any commit that touches `engine/`.

**This rule beats "write code that reads like the code around it".** Measured 2026-08-29: 777 of the
1139 tracked `.py` files still carry Spanish comments — 16126 blocks, 68% of the repo. That is a
**backlog under translation**, not the house register, and reading it as the local idiom is precisely
how this rule kept losing to it. Do not translate your neighbours either: a separate pass owns that
corpus and editing the same files concurrently only makes conflicts. Write **your** lines in English,
leave the rest alone.

Spanish that is **product data** is untouched by this rule and must stay Spanish: user-facing labels,
voice replies, `i18n/bundles/*.json`, prompt text the operator's agent speaks, and the Spanish
vocabulary inside detectors and regexes. Those answer to the i18n rules (`voice/engine/core/langs.py`,
V2-089), not to this one. Our customers speaking Spanish has nothing to do with what language we
develop in.

The boundary stops at `engine/`: the workspace root `../.meshkore/` is the operator's private business
context and stays in Spanish on purpose.

> **`.meshkore/` es una CARPETA REAL de ESTE repo** (2026-07-28, antes era un symlink a `../.meshkore`). engine
> es el repo PÚBLICO OSS y lleva SU propio `.meshkore/` con el contexto MeshKore Standard del MOTOR —
> arquitectura, convenciones, módulos, seguridad, roadmap del motor, roles de agente (`team/`), `public/cluster.yaml`
> y `STANDARD_VERSION`: quien clone el repo dice «carga el estándar MeshKore» y tiene todo el contexto y las tareas.
> Lo que se ignora (`.gitignore`) es solo el estado runtime PRIVADO del self-hoster (`credentials/`, `logs/`,
> `timeline/`, `snapshots/`, `.runtime/`, `agents/`) — sus propias claves/logs, nunca al repo.
> **Lo que NO vive aquí:** la gestión de NEGOCIO/proyecto entero (cloud/GTM, `launch-readiness`, coordinación
> engine+web+cloud) vive en `../.meshkore/` de la RAÍZ del workspace (repo aparte, privado) — ver `../CLAUDE.md`.

> ⚠️ **NI NUESTRO PASADO NI NUESTRO FUTURO SE PUBLICAN** (2026-08-14, norma del operador). Este repo guarda lo
> que ayuda a entender y correr el motor **HOY**. Lo que cuenta cómo llegamos o a dónde vamos existe en local
> pero está **gitignoreado**, así que quien clone el repo NO lo tiene y muchas referencias de estos documentos
> le apuntarán a carpetas vacías. Es deliberado, no un despiste:
>
> | No se publica (existe en local) | Sí se publica |
> |---|---|
> | `.meshkore/roadmap/` — iniciativas y plan | `.meshkore/docs/` — arquitectura, convenciones, módulos, ops, seguridad |
> | `.meshkore/modules/*/tasks/` y `*/logs/` — tareas y bitácoras | `.meshkore/public/cluster.yaml`, `STANDARD_VERSION` |
> | `.meshkore/team/` — roles internos de nuestros agentes | `CLAUDE.md`, `README.md` |
> | `tests/voice/e2e/agent/reports/` — informes de ejecuciones | `tests/README.md`, `tests/TESTMAP.md`, catálogo de escenarios |
>
> El detonante fue una fuga real: los informes de la batería de voz son **transcripciones de sesiones**, y 110
> de 186 llevaban dentro el nombre del operador y las tareas de su agenda. La regla general que deja: el
> CATÁLOGO de qué se prueba es público y útil; el DIARIO de lo que se probó es nuestro. Igual con el roadmap —
> saber cómo está construido el motor le sirve a quien lo clona; saber qué pensamos construir, no.

## ⭐ Cómo se orienta CUALQUIER arreglo del agente (norma del operador, 2026-08-20)

El agente debe ser capaz de resolver **cualquier** encargo: reservar un hotel o un restaurante, montar una
investigación sobre la cultura griega del siglo II a.C., sacar los planos o la lista de tareas para construir un
cohete, inventar un libro, buscar un vehículo en Wallapop, o buscar casas en la zona de Los Ángeles usando las
webs que sean populares **allí**, empezando por la más popular. **No hay lista de encargos soportados y no puede
haberla.**

De ahí sale la regla que gobierna todo cambio en el lado del worker, y son DOS MITADES con tratamientos opuestos:

- **RECURSOS (el core) → clavados, completos y probados.** El manejo del navegador, que el worker reciba EN
  TIEMPO REAL todo lo que tiene que recibir, el parseo de los datos, las capturas de pantalla cuando hagan falta,
  los puentes, la evidencia y la entrega. Aquí un fallo es un bug.
- **RAZONAMIENTO (el encargo) → abierto y general.** La lógica, la investigación y la ejecución no se cablean:
  se construye un sistema capaz de **encontrar la fórmula** que llega al resultado que espera el operador. Los
  prompts de los Brain Workers llevan **fórmulas, recursos y maneras de resolver**, nunca un guion.

**Lo prohibido es adaptarse al caso de uso.** Un arreglo que hace pasar ESE escenario y se cae cuando cambian un
dato, una coma o una condición no es un arreglo: es andamio. La prueba, antes de escribir nada: *cambia una
palabra del encargo —hotel→restaurante, Sevilla→Los Ángeles, «4 estrellas»→«menos de 80 €»— ¿sigue en pie?* Y:
*¿sirve para un encargo que nadie ha escrito todavía?* Si la respuesta es no, está apuntando a la mitad
equivocada.

Un conocimiento cableado del mundo (el catálogo de sitios) puede decir **«empieza por aquí»**; nunca **«solo
aquí»**. En cuanto un encargo fuera del catálogo tiene MENOS capacidad que uno de dentro, el catálogo dejó de ser
un atajo y es una valla.

**Duda razonable → es un problema de RECURSOS hasta que se demuestre lo contrario.** Ha sido cierto todas las
veces hasta hoy: el worker muriendo aprendiendo su propio CLI a tientas (V2-219), el compositor que leía la
cadena de proveedores y nunca la escribía —y dejaba a ciegas TODA investigación— (V2-225), lo que el navegador
encontraba sin llegar a nadie (V2-223), y la nota empujada 3/3 contra la línea de prompt 0/13 (V2-222). Ninguno
tenía forma de escenario, y el arreglo con forma de escenario los habría tapado a los cuatro.

Doctrina completa, con el contrato de recursos y el procedimiento al recibir una ronda fallida:
**`.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`**.

**Otras formas de arrancar**: `BRAIN=direct`/`BRAIN=local` son baselines de modelo pelado (sin memoria ni
tools); `make lk-server` y `make agent-worker` levantan las dos mitades por separado para depurar.

## Documentación canónica y estándar MeshKore

Este repo sigue el **MeshKore Standard v27**. Toda la documentación, módulos y roadmap viven en `.meshkore/`.
Los agentes DEBEN trabajar dentro de esta estructura — no crear `docs/` ni carpetas ad-hoc fuera de ella.

### Documentación canónica (`.meshkore/docs/`)

| Categoría | Archivo |
|---|---|
| Architecture | `.meshkore/docs/architecture/zaelar-architecture.md` |
| **Modularidad / contratos de acoplamiento** | `.meshkore/docs/architecture/zaelar-modularity.md` |
| **Memoria central** | `.meshkore/docs/architecture/zaelar-memory.md` |
| **¿Por qué ESTOS modelos en la memoria?** (respuesta canónica) | `zaelar-memory.md §Modelos de la memoria` · denso: `zaelar-model-benchmarks.md §12.3/§12.4` · crudo: `tests/memory/e2e/bot/resultados/` |
| **Canal de cluster — algoritmo de punta a punta** | `.meshkore/docs/architecture/zaelar-cluster-channel.md` |
| **Red MeshKore — agentes vivos (oráculo) + clusters, y en qué estado está cada pieza** | `.meshkore/docs/architecture/zaelar-meshkore-network.md` |
| **⭐ Doctrina de los Brain Workers — endurecer los RECURSOS, abrir el RAZONAMIENTO (orienta CUALQUIER fix)** | `.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md` |
| **Multidioma / i18n (arranque idiomático, generación de bundles)** | `.meshkore/docs/architecture/zaelar-i18n.md` |
| **⭐ Prompt que pertenece a una FASE (context packs) — leer ANTES de añadir una frase al prompt del turno** | `.meshkore/docs/architecture/zaelar-context-packs.md` |
| **El PRIMER ARRANQUE de punta a punta (idioma → carpeta → voz → saludo)** | `.meshkore/docs/modules/zaelar-first-run.md` |
| Product / Context | `.meshkore/docs/product/zaelar-product.md` |
| Deploy | `.meshkore/docs/deploy/zaelar-deploy.md` |
| Ops / Setup | `.meshkore/docs/ops/zaelar-ops.md` |
| Conventions | `.meshkore/docs/conventions/zaelar-conventions.md` |
| Modules | `.meshkore/docs/modules/zaelar-modules.md` |
| **Conectores — la LISTA (qué conectamos hoy, qué está declarado y dónde se cablea cada pieza)** | `.meshkore/docs/modules/zaelar-connectors-inventory.md` |
| **Una cita que pide OTRO — el criterio de autorización de las propuestas** | `.meshkore/docs/modules/zaelar-appointment-proposals.md` |
| **Contactos — importar/sincronizar con Google, y quién gana un conflicto** | `.meshkore/docs/modules/zaelar-contacts-sync.md` |
| Security | `.meshkore/docs/security/zaelar-security.md` |
| **Change protocol** | `.meshkore/docs/ops/zaelar-change-protocol.md` |
| **Audit workflow** | `.meshkore/docs/ops/zaelar-audit-workflow.md` |
| **Docs & structure sync** | `.meshkore/docs/ops/zaelar-docs-sync.md` |
| **⭐ ESTÁNDAR de cabecera de widget — las dos barras y la puerta a los conectores** | `.meshkore/docs/conventions/zaelar-widget-header-standard.md` |
| **Widgets change workflow** | `.meshkore/docs/ops/zaelar-widgets-workflow.md` |
| **⭐ Widget o conector NUEVO — el workflow completo** | `.meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md` |
| **Memory change workflow** | `.meshkore/docs/ops/zaelar-memory-workflow.md` |
| **Alignment review** | `.meshkore/docs/ops/zaelar-alignment-review.md` |
| **Model/latency benchmarks** | `.meshkore/docs/ops/zaelar-model-benchmarks.md` |
| **Changing a model (checklist + traps)** | `.meshkore/docs/ops/zaelar-model-change.md` |
| **Testing playbook** | `.meshkore/docs/ops/zaelar-testing.md` |
| **Monitorización de conversaciones de cluster** | `.meshkore/docs/ops/zaelar-cluster-conversation-monitoring.md` |
| Observabilidad / debug | `.meshkore/docs/ops/zaelar-observability.md` |

> Instalación / arranque para quien clona el repo: **[`README.md`](README.md)** en la raíz (multi-plataforma
> macOS/Windows/Linux). Es la puerta de entrada; el detalle vive en `zaelar-ops.md`. Mantener ambos alineados.

**Protocolo de cambio ("pasa el protocolo"):** cuando el operador dice *"pasa el protocolo"*, ejecutar la
checklist de `zaelar-change-protocol.md` (reiniciar+verificar → versión → diario/iniciativa/contexto → commit →
push si hay remote → deploy si hay prod). No hay que recordar los pasos de memoria: viven en ese doc.

**Workflow de auditoría ("pasa la auditoría"):** cuando el operador dice *"pasa la auditoría"* / *"audita el
sistema"*, ejecutar `zaelar-audit-workflow.md` — reconocimiento del contexto → fan-out en paralelo por 4 dominios
(voz/cerebro/server · frontend/widgets · seguridad cluster · alineación docs) → síntesis → informe + plan P0-P3.
Verifica que código, arquitectura, contexto y el módulo de seguridad siguen alineados cada vez que el proyecto crece.

**Sync de docs/estructura (automático):** todo cambio que toque la **estructura** (módulos, layout, deps, instalación)
o **decisiones/invariantes/seguridad** ejecuta `zaelar-docs-sync.md` — actualizar README (raíz, multi-plataforma),
`CLAUDE.md`, `cluster.yaml`, la doc de categoría y el **diagrama de arquitectura**, con la regla de oro "que aparezca
en contexto + docs + arquitectura". Es el paso de coherencia docs↔estructura dentro del change protocol.

**Revisión de alineación ("pasa la revisión de alineación"):** al cerrar CUALQUIER cambio que toque arquitectura, un
módulo, un flujo o una decisión/invariante, ejecutar `zaelar-alignment-review.md` — checklist reutilizable que
verifica que **código ↔ contexto (CLAUDE.md) ↔ docs canónicas ↔ diagramas HTML (`/architecture`: pestañas
Arquitectura/Memoria/FlashBrain/SlowBrain/Widgets + modelos-en-uso + sello "Actualizado") ↔ roadmap (tareas done +
bitácora, servido al Architect por el daemon) ↔ tests** cuentan la MISMA historia (estado actual, sin dirty/legacy).
Es la puerta de calidad de cada cambio; trae sondas `grep`/`node --check` y un template de informe.

**Workflow de cambios en widgets ("pasa el workflow de widgets"):** cuando el operador dice **"pasa el workflow de
widgets"** (o "revisa/cierra el cambio de widgets"), o al cerrar tú mismo un cambio ESTRUCTURAL del sistema de
widgets (contrato de `manifest.json`/`data.py`/`widget.js`, protocolo de tags, despacho cerebro↔widget, storage,
refresco, gate de validación), ejecutar `zaelar-widgets-workflow.md` — mapa "qué tocaste → qué actualizar" (contrato
del generador, brief, prompt del FlashBrain, docs canónicas, **diagrama Y teoría** de `architecture.html`), repaso de
impacto en widgets existentes, pruebas (`make test-widgets` + prueba en vivo si toca gobernanza), reinicio si hubo
cambios `.py`, y commit/push SOLO si el operador lo pide. Un cambio trivial dentro de un solo widget (su propio
`data.py`/`widget.js`) no lo dispara — solo actualiza el `notes.md` de ese widget.

**Widget o conector NUEVO ("añade un conector de X" / "haz un widget de Y" / "pasa el workflow de widget
nuevo"):** ejecutar `zaelar-new-widget-or-connector-workflow.md` — TODAS las acciones, en orden, para que una
pieza nueva quede construida, cableada, probada, documentada y en el contexto. Es DISTINTO de
`zaelar-widgets-workflow.md`, que gobierna cambios del SISTEMA de widgets; este gobierna piezas nuevas. Trae
las cuatro decisiones previas (¿widget o conector? · ¿hace falta una tool nueva? casi siempre NO, las acciones
declaradas SON las skills · ¿background? · ¿produce?), **la lista de los 14 puntos de cableado que fallan
VACÍOS** (registro, routers, `_BUILTINS`, tarjeta Y familia del ⚙, `api.js`, i18n en+es, exención stdlib,
testmap, manifiesto de catálogo, orden de familias del muro de chat, claves `chat.connFamily.*`, brief del
cerebro, README de credenciales, la LISTA de conectores), la mitad de RUMBO que se olvida siempre (un
conector añade ACCIONES y casi nunca las PALABRAS que llevan a ellas — V2-686), **§7-bis el ÚLTIMO METRO**
(el consentimiento es un clic del operador; por voz la acción deja la tarjeta EN el paso del botón) y
**§7-ter declararlo HECHO** (sacarlo de `planned`, alinear el id, la fila en la lista, el estado en el
cerebro), el set de tests en sus cuatro clases —incluida la VIVA, que se construye entera aunque no haya
credencial y SALTA con los pasos para habilitarla—, las fronteras que no se cruzan (la voz transporta
intención y nunca una credencial; `widget.js` no toca la red; los widgets no se hablan entre sí) y una tabla
de **diez traps medidos**. Nació del build de V2-557 y su razón de ser es que el siguiente sea corto.

**Workflow de cambios en la memoria ("pasa el workflow de memoria"):** cuando el operador dice **"pasa el workflow
de memoria"**, o al cerrar tú mismo un cambio ESTRUCTURAL de la memoria (schema/píldora, el CORAZÓN de escritura
`mem_processor`/`memory_agent`, retriever/scoring, capas y velocidades de lectura, consolidador/olvido, cola/writer,
observabilidad/visor), ejecutar `zaelar-memory-workflow.md` — **mapa de impacto "qué tocaste → qué revisar/notificar"**
de TODOS los escritores (FlashBrain conv-buffer, `ingest_utterance`, `remember`, widgets/mensajería, reset, episódica)
y lectores (`memory_cache`, `compose_recall`, `compose_context`, visor `/api/memory/map`) para verificar que sus
interacciones (guardar Y leer) siguen alineadas con la versión nueva, + migración de schema, + docs (zaelar-memory.md,
CLAUDE.md, diagrama Memoria de `/architecture`), + tests, + commit. Evita re-investigar cada vez a quién afecta un
cambio de memoria. Termina SIEMPRE con la revisión de alineación.

**CLOSING a batch ("cierra esto" / "documenta lo que has hecho" / "pasa el cierre"), and the MODULE LOG:** at
the end of ANY batch that changes behaviour. The full eight steps live in the workspace ROOT's `.meshkore/`
(`zaelar-initiative-closure.md`, PRIVATE repo — whoever clones this one does not have it, same as the roadmap);
what belongs to THIS repo, and is therefore written here, are the three that keep being skipped:

1. **The test with its NODE** in `tests/run_testmap.py`. Not in the map = it does not exist for «is everything
   green?».
2. **The decision in this file**, §Decisiones clave, with the WHY and the real failure that motivated it. It is
   the only thing the next agent is certain to read.
3. **The MODULE LOG** — `.meshkore/modules/<module>/logs/<YYYY-MM>/<PREFIX>-NNN-<slug>.md`. It is the only place
   that keeps **the OPERATOR'S OWN WORDS for the request, what was MEASURED before touching anything, and the
   COMMITS** that delivered it: the decision above says WHAT was decided and the initiative holds the detail, but
   neither says where the task came from or which tree was walked to get there — which is exactly what is lost
   when a session is cut short. Frontmatter `id/title/status/priority/owner/initiative/created/updated`, and a
   table of commits at the end.
   ⚠️ **`T-NNN` numbering is GLOBAL**, shared by EVERY module (frontend, voice, server…); the module-specific
   prefixes run on their own (`N-` nucleo, `MK-` cluster, `S-` security, `TS-` tester, `C-` clusters). `ls` before
   taking a number, exactly like an initiative.
   ⚠️ **Gitignored on purpose** (the «neither our past nor our future gets published» rule): it lives on the
   operator's machine and never travels with the repo. That is what makes it the place for the DIARY rather than
   the catalogue — and why its entries are written in the operator's language, unlike everything else here.

Measured 2026-09-11: the module log **was not on the closure checklist**, and the result was that it stalled at
`2026-08` while the engine shipped through V2-669 — a month of batches with no record of the request, across two
sessions that were lost. *A step that is not on the checklist is a step that does not get taken.*

**Testing del bot ("lanza un test del bot"):** cuando el operador dice **"lanza un test del bot"**, **"lanza la
batería (de escenarios)"** o **"prueba el bot en tuen"**, ejecutar `zaelar-testing.md` — el playbook autocontenido:
**Paso 0 = ALINEACIÓN** (comprobar que `tests/voice/e2e/agent/scenarios.py` cubre los módulos principales y los cambios de las
ÚLTIMAS 48 h — `git log --since` + decisiones `V2-0xx` nuevas; si falta, añadir el escenario ANTES de lanzar) →
prioridades (latencia · coste bajo · memoria · búsqueda precisa · **navegación web profunda Wallapop/coches.net con
extracción de datos reales, con/sin login** · robustez · multiidioma) → lanzar (`tests/voice/e2e/agent/run_battery.sh` con settle,
o `cron_tick.sh`) → evaluar con el JUEZ distinguiendo **bug real (trace-confirmado) vs ruido de STT del tester vs
rigidez del juez** (y comparación HUMANA de lo extraído en navegación) → arreglar código si hay bug → **archivar el
informe del día en `tests/voice/e2e/agent/reports/<YYYYMMDD>-<desc>/`** (histórico consultable). Catálogo legible de escenarios en
`tests/voice/e2e/agent/anexos/catalogo-escenarios.md`. No hay que recordar los pasos: viven en el playbook.

**Contrato obligatorio para agentes de desarrollo:** antes de probar cualquier cambio, leer **`tests/README.md`**.
Es la guía operativa corta compartida por Claude Code, Codex, humanos y CI; `zaelar-testing.md` conserva el
diagnóstico profundo. La entrada preferida es `./.venv/bin/python -m tests run <suite> [--case ID] --no-open`:
mantiene el exit code de terminal y, al mismo tiempo, publica cada ejecución en el **Test Observatory** estable de
loopback **`http://127.0.0.1:8765`**. `--no-open` solo evita abrir una ventana: NO desactiva el visor, de modo que el
operador puede observar mientras el agente trabaja. La aplicación real sigue en `http://127.0.0.1:43917`; no
confundir ambos puertos. No ejecutar dos runs gestionados por el Observatory en paralelo, no probar contra la
memoria real si existe fixture/corpus aislado y no recrear raíces `test/`/`tester/`: todo test nuevo vive bajo
`tests/<suite>/`. Para cambios visuales, `browser` por sí solo cubre contratos deterministas; afirmar E2E visual
requiere conducir Chromium/Playwright contra el Zaelar vivo. Para una capacidad nueva, mapear el caso en
`suite.json`/provider y validar `tests/platform/tests`; cero casos `unmapped` es el objetivo.
Los cambios que crucen memoria + conversación + widgets/workers/conectores se cierran además con
`./.venv/bin/python -m tests run journey --no-open`: son 26 pasos sobre un único engine/DB/workspace aislado y cada
caso posterior reconstruye su prefijo causal. Contrato y fronteras no cubiertas: `tests/journey/README.md`.

> **Diagrama de arquitectura — MOVIDO al sitio público (2026-07-24):** `frontend/pages/architecture.html` y la
> ruta `/architecture` de este repo se **retiraron** — ya no tenía sentido servir un panel interno (con editor de
> modelos ⚙ en vivo) desde el propio motor. Los diagramas (Arquitectura general, FlashBrain, Brain Workers,
> Memoria, Widgets) viven ahora como contenido **público, curado y en inglés** en `web/` bajo `/technology`
> (`web/src/pages/technology/*.astro`), con las rutas de código internas, nombres de variable y detalle de
> incidentes/costes RECORTADOS a propósito (audiencia externa, no engineering interno). **Ya NO es un espejo
> automático del código** — es una foto seleccionada a mano. Si tocas topología/modelo/proveedor de forma
> significativa, actualiza también los diagramas en `web/src/pages/technology/` como paso manual (no lo hace
> ningún workflow todavía); la fuente de verdad DETALLADA sigue siendo `.meshkore/docs/architecture/` y este
> `CLAUDE.md`. **Limpieza HECHA (2026-07-26, con autorización explícita del operador tras la auditoría):** los 5
> workflows (`zaelar-docs-sync.md`, `zaelar-widgets-workflow.md`, `zaelar-memory-workflow.md`,
> `zaelar-alignment-review.md`, `zaelar-audit-workflow.md`) ya apuntan a `web/src/pages/technology/*.astro` +
> `web/src/lib/diagrams/*.ts` en vez del `architecture.html` retirado; las menciones que quedan son notas
> históricas explícitas ("retirado el 2026-07-24"), no punteros activos a editar.

### Módulos — el mapa corto

Antes de crear un módulo nuevo, declararlo en `.meshkore/public/cluster.yaml`. Raíz SIN `.py`/`.html` sueltos;
arranque `make run` → `python -m server`.

| Módulo | Qué es |
|---|---|
| `voice/` | Motor **LiveKit** (`voice/engine/`): STT/TTS, turnos, VAD, barge-in. Encima, el contrato del cerebro agnóstico del transporte: `attention.py` (qué turno va dirigido a zaelar), `speech.py`, `observer.py` (SSE). |
| `nucleo/` | El **cerebro «Colmena»**: `flash/` (reflejo sub-segundo, enruta y responde), `workers/` (Brain Workers para lo que no cabe en un turno), `errands/` (un encargo que sobrevive al turno), `loop.py`+`scheduler.py` (pulso, crons, proactividad), `memory_agent.py`+`mem_processor.py` (único escritor de la memoria). |
| `memory/` | **Memoria central** en un solo SQLite (`zaelar.db`): píldoras con `slot`, retriever (sqlite-vec + FTS5 + reranker), grafo, consolidador y fase REM, capa episódica y la bóveda de secretos. |
| `observability/` | **QUIÉN · CUÁNDO · en qué FLUJO**: identidad de instalación y de sesión, lectura por `corr_id`. Solo lectura — el único escritor de `events` es el sink del bus. |
| `bus/` | **Sistema nervioso**: pub/sub in-process + log durable de eventos + puente SSE al frontend. Nada de Kafka. |
| `frontend/` | La interfaz, módulos ES **sin build**. `frontend/app/` (escritorio) y `frontend/mobile/` (PWA). Las superficies NATIVAS se declaran en `core/system-surfaces.js`; todo lo demás en pantalla es un widget. |
| `server/` | App FastAPI + routers + entrypoint. Corre el agent worker de LiveKit EMBEBIDO y arranca en su lifespan el loop, el supervisor de widgets y la cola de memoria. |
| `widgets/` | Widgets full-stack (`manifest.json` + `data.py` + `widget.js` por carpeta), generador, catálogo y runtime. Dos tipos: `passive` y `backed` (proceso propio supervisado). |
| `config/` | Settings de runtime que gestiona la UI (gitignored): `settings.json`, `connectors.json`, `v2.json` (routing de modelos). Cada uno con su módulo dueño y su vista pública redactada. |
| `connectors/` | Lo de fuera: WhatsApp, Telegram, email, Google (un cliente OAuth para Calendar/Meet/Drive/Fotos/YouTube), archivos en la nube, canal nativo MeshKore, Architect. |
| `tests/` | Ver «Testing» más abajo. El harness sintético, el self-test de micrófono y el tester de voz viven bajo `tests/`. |

**El detalle** — qué piezas forman cada módulo y por qué: `.meshkore/docs/modules/zaelar-module-map.md`.

### Roadmap e iniciativas (`.meshkore/roadmap/`)

Las iniciativas activas están en `.meshkore/roadmap/initiatives/`. Anclar cada tarea a una iniciativa. El diseño del
cerebro «Colmena» vive en `.meshkore/roadmap/EPIC-v2-colmena.md`.

### Daemon (NO es por-proyecto)

El daemon de MeshKore es un **servicio único compartido** (hospedado en `daemon.meshkore.com`), que da
servicio a todos los proyectos del cluster. **Este repo NO arranca ni incluye un daemon propio.** La adopción
del estándar se hace apuntando el front del Architect a la URL de la carpeta `.meshkore/` de zaelar; el daemon
la lee, identifica el proyecto por `public/cluster.yaml` y lo onboarda (incluido el bloque `MESHKORE_PREAMBLE`).
No crear `.meshkore/daemon.py`, ni targets `make meshkore`, ni bindear el puerto 5570 desde aquí.

## Decisiones clave — están en su propio fichero

El diario del motor (una entrada por tanda: qué se decidió, por qué, y el fallo real que lo motivó) vive en
**`.meshkore/docs/decisions.md`**, y lo más viejo en `.meshkore/docs/decisions-archive.md`. Se lee ANTES de
tocar una pieza — te dice qué se intentó ya y qué se descartó, que es la mitad del trabajo que no se repite.

Al cerrar una tanda, la entrada se escribe allí, no aquí. Este fichero es de REGLAS y PUNTEROS.

## Testing

**Contrato obligatorio: antes de probar cualquier cambio, leer `tests/README.md`.** Es la guía operativa corta
compartida por Claude Code, Codex, humanos y CI. El playbook profundo —cómo se lanza cada batería, formatos,
evaluación— vive en `.meshkore/docs/ops/zaelar-testing.md`, no aquí.

**`tests/run_testmap.py` es el MAPA DE TESTS**: todo el testing ordenado por DOMINIO → CASO DE USO → CANAL
(nodos `N.M`). Es la fuente de verdad de qué fichero cubre qué caso; marca aparte los nodos VIVOS (exigen
`make run`). La segunda opinión —cobertura, huecos, duplicación— en `tests/TESTMAP.md`. **Un test que no está
en el mapa no existe para «¿está todo verde?»**.

⛔ **`./.venv/bin/python tests/run_testmap.py` SIN ARGUMENTOS LANZA EL MAPA ENTERO** — o sea, es la pasada
ancha que prohíbe la primera de las «Hard rules», con otro nombre. Este párrafo la recomendaba como respuesta
a «¿funciona todo bien?» y se pagó el 2026-09-15: un agente la lanzó por leer aquí, y hubo que matarla. Para
LEER el mapa sin correrlo: `tests/run_testmap.py --list`. Para comprobar que tu test está en él, el fichero
`tests/infrastructure/unit/test_a_test_outside_the_map_is_not_a_test.py` a solas. **«¿Funciona todo bien?» se
la pides a ÉL.**

**NO lances suites anchas en su máquina** — es la primera de las «Hard rules» de abajo y no se relaja: se
corre el FICHERO que has tocado, como mucho su CARPETA, y los DESARMES. Una pasada ancha se la pides a él.

**Un rojo que no se reproduce en aislamiento es contaminación entre tests, no un fallo de tu código.** La
causa es siempre la misma familia: algo que toca estado compartido y no lo devuelve. El `conftest.py` raíz
mueve a un temporal TODO lo que el producto guarda de verdad —logs, settings, routing de modelos, datos de
widgets, la base de datos, los widgets ocultos— y **falla POR NOMBRE** al test que deje la tabla de módulos
(`sys.modules`) purgada. Antes de tocar nada, reproduce el rojo en su carpeta a solas.

**Tres formas de probar**, de la más rápida a la más lenta: el **canal de texto del FlashBrain** (headless,
`make flash-serve` + `make flash T="…"`) para cerebro rápido/conversación/prompt/tools; la **batería de
memoria** (`tests/memory/e2e/bot/`); y el **tester de voz** (`tests/voice/e2e/agent/`), un 2º participante de
LiveKit que HABLA con zaelar mientras un JUEZ evalúa lo que zaelar HACE, no lo que dice. Los tres, con sus
disparadores y su evaluación, en el playbook.

**Los desarmes.** Un test nuevo no vale hasta que se ha visto ROJO: se muta la guarda que dice proteger, se
ASERTA que la mutación entró, se mide, y se restaura en un `finally` limpiando `__pycache__`. **Un desarme que
sigue verde acusa al TEST**, no al producto.

**Un test NUNCA toca el estado real del operador**: ni su agenda, ni su memoria, ni su `config/`, ni sus logs.
Esa regla se ha pagado ya cinco veces (328 citas de prueba en su agenda, su routing de modelos reescrito, su
motor reiniciado); cada vez el remedio fue «que un fichero se acuerde», y por eso vive en el `conftest.py` raíz
y no en cada test.

## Deploy (producción)

Ver `.meshkore/docs/deploy/zaelar-deploy.md` — instrucciones completas para Fly.io + CloudFlare TURN.
Estado actual: **sin deploy en prod** (destruido por ahorro de costes).

## Frontera PÚBLICO/PRIVADO — este repo es público (fair-code) y se lee desde fuera

**`engine/` es el repo PÚBLICO.** Su código y su `.meshkore/` los lee cualquiera que clone zaelar. Por eso:

- **NUNCA se documenta aquí nada de la NUBE ni del NEGOCIO**: control-plane, provisioner, facturación, backoffice,
  tablas de la base central, precios, políticas de las cuentas de pago, decisiones de privacidad del producto
  comercial. Eso vive en el `.meshkore/` de la RAÍZ del workspace (repo privado aparte) — ver `../CLAUDE.md`.
- **El código puede tener costuras que un despliegue use y otro no** (una URL de servicio en una variable de
  entorno, un id de usuario que venga del entorno). Lo que NO puede es NARRAR para qué sirven en un producto de
  pago. La regla práctica: describe el MECANISMO («si `X_URL` está configurada, avisa a ese servicio; sin ella es
  un no-op»), nunca el PRODUCTO («el provisioner inyecta esto en la Machine de cada cliente»).
- Ante la duda, la pregunta es: *¿esto le sirve a alguien que se auto-hospeda?* Si la respuesta es no, no va aquí.

⚠️ **Deuda conocida (2026-08-09):** este `CLAUDE.md` y varios docs de `.meshkore/` arrastran menciones a
`INI-019`/`INI-020`, control-plane, provisioner y backoffice de ANTES de fijar esta regla, y el repo **ya está
publicado**, así que el historial de git las conserva aunque se limpien hoy. Limpiar lo que queda es una tarea
abierta (`V2-091`); a partir de ahora, no añadir más.

## Hard rules

- ⛔ **NO LANCES SUITES ANCHAS DE PYTEST EN LA CONSOLA — dejan la máquina del operador colgada** (norma del
  operador, 2026-09-15, dicha ya DOS veces y en dos sesiones distintas: «todos estos tests que estás lanzando
  en consola dejan al sistema colgado… no quiero que los lances»).

  **PROHIBIDO**, sin excepción y sin pedir permiso para saltárselo:

  ```
  pytest tests/infrastructure/unit      pytest tests/browser/unit      pytest tests/browser/e2e
  pytest tests/agent_headless/unit      pytest tests/connectors/unit   pytest tests/          (o cualquier
  combinación de varias de ellas en una sola invocación, con o sin `-q`, en foreground o en background)

  ./.venv/bin/python tests/run_testmap.py       ← SIN ARGUMENTOS LANZA EL MAPA ENTERO. Es la misma pasada
                                                  ancha con otro nombre. `--list` sí (solo imprime).
  ```

  **Lo que SÍ se hace** — y es suficiente para cerrar un cambio:
  1. el FICHERO de test que has escrito o tocado: `pytest tests/<...>/test_lo_tuyo.py -q`;
  2. como mucho la CARPETA de la pieza que has tocado (`tests/browser/unit/agenda`, `tests/connectors/unit/calendar`);
  3. `make test-widgets` cuando el cambio sea de widgets;
  4. los DESARMES (romper el producto y ver el test rojo), que son lo que de verdad demuestra que mides algo.

  **Medido en esta misma máquina** el 2026-09-15, que es lo único que se afirma aquí: una pasada de
  `tests/browser/unit` se quedó **7+ minutos clavada al 22%** y hubo que matarla, mientras había **71 procesos
  Chromium huérfanos** vivos y **dos pytest de otra sesión** llevando 40 minutos sobre el mismo checkout. La
  MISMA carpeta acusada, lanzada sola y en aislamiento, pasó **216/216 en 10 segundos**. Así que un fallo o un
  cuelgue en una pasada ancha **no es una señal sobre tu código**: reprodúcelo en la carpeta sola antes de
  tocar nada.

  **Dos de las tres causas están medidas (2026-09-15, V2-696), y la regla NO se relaja por eso.**
  (1) Los ~230 rojos que aparecían en cualquier pasada ancha y NUNCA en aislamiento eran contaminación:
  un test purgaba `sys.modules` de todo `widgets*`/`i18n*` y no devolvía la tabla, así que el siguiente
  importador recibía un `widgets.store` recién construido —sandbox del conftest perdido, la suite escribiendo
  en los datos REALES del operador— y los dos últimos venían de `widgets/hidden.py`, que leía qué widgets ha
  borrado ÉL. Arreglado, con trinquete. (2) La lentitud es CONCURRENCIA: dos barridos a la vez tardan el doble
  (1222 s y 1589 s, medidos) y dejan Chromium huérfanos de los e2e. Sola y limpia, la suite entera son
  **9 minutos y 9696 verdes**.

  ⚠️ **Lo que sigue SIN diagnosticar es el CUELGUE** —una pasada clavada al 22 % durante 7 minutos con 71
  Chromium huérfanos vivos— y, sobre todo, la regla no era nunca sobre el resultado: es sobre la CARGA en la
  máquina que él está usando. No la relajes porque «esta vez es corta» ni la esquives lanzándola en background.
  Si de verdad hace falta una pasada ancha, se la pides a ÉL.

- **COMMITEA PRONTO Y SIEMPRE — cada agente y cada sesión commitea SU propio trabajo.** En cuanto una tarea está
  hecha se commitea, **incluso ANTES de probarla**: si algo sale mal se revierte (`git revert`/`reset`), pero perder
  código NO es reversible. Con varios agentes/sesiones trabajando en paralelo, **un árbol de trabajo sin commitear
  es la causa nº1 de pifostios irreparables** — un agente empieza a trastear encima de los cambios sin commitear de
  otro y se lía un desaguisado que no entiende nadie. Reglas: (1) **trabajo terminado = trabajo commiteado**, con
  mensaje claro de QUÉ y POR QUÉ; (2) **nunca cierres una sesión ni cambies de tarea dejando cambios sin commitear**;
  (3) commitea en incrementos pequeños y coherentes, no un mega-commit al final; (4) si encuentras trabajo de OTRO
  agente sin commitear, NO lo pises: commítealo aparte y atribuido, o pregunta. Tras commitear, **PUSHEA** (ver la
  regla "Commitea Y PUSHEA siempre" más abajo — política del operador 2026-07-16). Barato deshacer un commit;
  carísimo perder código.
- **Con sesiones concurrentes, la protección NO está en cómo AÑADES sino en qué COMMITEAS: `git commit -- <rutas>`**
  (2026-08-20, aprendido rompiendo el escritorio). La norma anterior —«stage fichero a fichero»— se siguió al pie de
  la letra y no bastó: **`git commit` a secas commitea el ÍNDICE ENTERO, y el índice es COMPARTIDO** entre las
  sesiones que trabajan en el mismo árbol. Ese día un commit del arnés se llevó dentro el borrado de un componente
  que otra sesión tenía en el índice por un `git rm`, y HEAD quedó con un `import` apuntando a un fichero que ya no
  existía: **el escritorio entero sin cargar**, y sin que fallara nada en el commit. Con pathspec se commitean solo
  esas rutas desde el working tree y el resto del índice se ignora. La comprobación barata que lo acompaña:
  **`git diff --cached --name-only` tiene que estar VACÍO antes de empezar** — si trae ficheros ajenos, alguien
  llenó el índice y estás a un `git commit` de llevártelos. Y el detalle que se escapa siempre: en
  `git status --short`, staged es `M ` (marca en la PRIMERA columna) y solo-modificado es ` M`; un espacio de
  diferencia. **Si ya está pusheado, NO se reescribe `main` por una atribución**: el código no se pierde (un commit
  no toca el working tree de nadie), solo queda mal atribuido, y reescribir historia compartida cuesta más de lo
  que arregla.
- No commitear `.env`, `.venv/`, `logs/`, `config/settings.json`, `config/connectors.json`, `config/v2.json`
  (todos en `.gitignore`).
- No commitear `~/.hermes/memories/USER.md` — es perfil personal (la memoria puede sembrarlo, solo-lectura), no va
  en el repo.
- **Nada que configure el usuario final se pone en `.env`.** Toda activación/credencial de un conector o integración
  se maneja desde la UI (store `config/connectors.json`/`config/v2.json`, escrito por la UI; env solo fallback de
  power-user). Un conector nuevo SIEMPRE trae su flujo de setup guiado en el widget.
- **Commitea Y PUSHEA siempre** (política del operador, 2026-07-16): en cuanto una tarea/incremento está commiteado,
  `git push origin <rama-actual>` para mantener origin al día. (Deroga la regla anterior "no push sin confirmación".)
  Sigue en pie: NUNCA `pull`/`merge`/`reset`/`checkout` para traer una versión remota al local (el árbol local es la
  verdad); nunca pushear `.env`/secretos/config gitignoreada; no mergear a `main` salvo que el operador lo pida.
- **Cerebro de voz = NO-razonador** (regla dura): un razonador no cierra el turno a tiempo → zaelar se queda
  lento/mudo. El FlashBrain (`nucleo/flash/`) usa solo modelos rápidos no-razonadores. **Modelo POR INVOCACIÓN**,
  nunca una env global de modelo (concurrencia de sesiones). El routing (`fast` + `code_agent`) vive en `config/v2.py`
  (gestionado por la UI).
- No crear módulos sin declararlos en `.meshkore/public/cluster.yaml`.
- No editar `.meshkore/roadmap/state.json` a mano — es un artefacto generado.
- No crear carpetas `docs/` ad-hoc — toda la documentación va en `.meshkore/docs/<categoría>/`.
- **El CORE de zaelar NO debe requerir Docker.** El servidor LiveKit corre desde el binario nativo `livekit-server`
  (`make install-livekit`); Docker es solo un fallback opcional. El **sistema de testing (INI-013) SÍ puede usar
  Docker** — esa es la única parte donde Docker es aceptable.

<!-- OPERATOR_CONTENT_END -->
