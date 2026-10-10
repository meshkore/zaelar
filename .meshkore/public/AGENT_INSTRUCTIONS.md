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

9. **The team (§25, §28, revised v38).** The project has a roster of agent
   profiles at `.meshkore/team/*.md`. A project is seeded with a small base
   team: `a01` (the Architect Agent, which coordinates), `developer`,
   `git-manager`, `deployer` and the public `consultant`. Each card is a
   short prompt plus the slice of the project's knowledge that member
   needs — a deployer does not load the data model.

   **`delegate`** — the default way to use a teammate:
   `POST <daemon>/chat/delegate {parent_conv, member, brief}`, then END
   your turn; the daemon wakes you when that member reports, naming your
   `request_id`. The member runs in its own session with its own profile
   and slice, so your thread stays about the plan. Chain the next step
   from the report (build → commit → deploy) and give independent steps
   to different members at once. **A member is ONE session** (§28.6): your
   brief joins whatever that member is already holding.

   **`become`** — `⟦become⟧ <member id>` on its own line adopts a profile
   for your next turn in this same conversation. Only for one short step;
   never to chain a pipeline through one thread.

   **Or neither.** Most work is just work: a small fix and its test are
   one agent's job. Never delegate to spread a task thin or to avoid
   reading code. When the team has a `git-manager`, commits are its job:
   leave your change in the working tree and list the files in your
   report.

   **Talk to the operator in sentences.** Report objects and markers are
   agent-to-agent; never paste them into prose the operator reads.

   **If YOU are the member holding briefs**, you will see the whole batch:
   read it together, merge what collapses into one piece of work, and name
   every request id you answered in the report's `"for"` field. **If YOU
   were delegated**, three duties follow: anchor to the `(initiative,
   task)` your brief names (never mint a new one for a delegated step),
   end your final reply with the `⟦report⟧` line (once, as the last line —
   never echo the object elsewhere), and add
   `Parent: <parent member id>@<parent conv>` to any commit trailers.
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

Esto es lo que él ha pedido explícitamente, repetido y por escrito. Está arriba del todo porque es lo que más se incumple.

- **Respuestas hipercomprimidas.** Al grano, sin narrar el proceso, lo esencial en pocas líneas; el detalle
  solo si lo pide. Al CERRAR una tanda —no en cada turno— se acaba con un bloque de **una línea por tarea
  completada**, lo último de todo: él trabaja con muchas pestañas abiertas y lee solo el final para saber qué
  se acaba de terminar ahí.
- **No reinicies el motor con alguien dentro ni con un encargo vivo.** Antes de `make restart`: mirar los
  últimos eventos de `.meshkore/logs/sessions/` (si hay `transcript`/`brain` recientes, hay alguien hablando)
  y `curl -s localhost:43917/api/tasks` (si `sessions` no está vacío, hay trabajo en vuelo). Un reinicio mata
  su sesión de LiveKit y cancela los workers en curso. Pagado dos veces: 2026-07-14 y 2026-09-15.
- **Una pasada ancha se lanza con `tests/watchdog.py`, no con `pytest` a pelo.** Ver la primera de las «Hard rules».
- **Commitea con pathspec** (`git commit -- <rutas>`), tras comprobar que `git diff --cached --name-only` está
  VACÍO. Hay varias sesiones sobre el MISMO checkout y el índice es compartido. Ver «Hard rules».
- **Los commits llevan `Co-Authored-By`.** Override del operador a §9.1 del preámbulo (que lo prohíbe): cada commit añade, tras los trailers MeshKore, `Co-Authored-By: <quién escribió el cambio>` (el agente/CLI que redactó el commit). El operador lo daba por supuesto desde el principio (2026-09-19).
- **Si encuentras trabajo sin commitear de otra sesión, no lo pises ni lo commitees.** Ni siquiera para pagar
  un trinquete: extraer del fichero en vuelo de otro es peor que dejar la deuda.
- **Nada de pasadas de diseño autónomas.** Un cambio visual se acuerda antes; no se «mejora» la interfaz por
  iniciativa propia.
- **Lo VIGENTE está en `.meshkore/docs/criteria.md`** — un criterio por línea, con fecha y nodo de test, sin
  histórico. Se lee ANTES de tocar el comportamiento del motor; el diario (`decisions.md`) cuenta por qué.
- **Lo que no se ha verificado, se dice.** «No verificado en vivo» es una respuesta aceptable; afirmar que algo
  funciona sin haberlo medido, no. Si un test se pone verde al romper el producto, el sospechoso es el TEST.

## Dónde está cada cosa

| Qué buscas | Dónde está |
|---|---|
| Las **reglas** para trabajar en este repo | este fichero |
| Los **criterios vigentes** del motor — lo que obedece HOY, una línea cada uno, con su test | `.meshkore/docs/criteria.md` |
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

## ⭐⭐ LO PRIMERO: mecanismos, no reglas (CRIT-W1)

> «Necesitamos un sistema que no esté educado, es decir, que sea inteligente y que sepa qué hacer. Yo no
> puedo decirte todo caso por caso. Eso sería un sistema de if-elses… Al final estamos creando un SISTEMA,
> no una banda de reglas predefinidas o de carriles preseteados. **Lo único que tiene carriles son los
> widgets.**»

La línea que decide si un cambio entra en este motor: **¿lo que estoy añadiendo acota una CONSECUENCIA o
acota un JUICIO?** Acotar la consecuencia es un mecanismo y se queda (`party.py` no ofrece NINGUNA tool y
el motor ejecuta solo lo que permite el mandato; `contract.guard` rechaza una acción destructiva sin
selector; `book.unbook` solo puede deshacer la fila que ese encargo escribió). Acotar el juicio es un
carril y se quita («no discutas», «acúsale recibo en una frase», una tabla de verbos que decide intención).

Y la tercera pregunta, después de las dos de la doctrina de abajo: **¿esto que escribo es una frase sobre
cómo comportarse?** Si lo es, bórrala y busca el mecanismo que estaba sustituyendo.

Completo, con la cita entera del operador, la tabla de las dos clases de carril y el **hueco abierto** (no
existe un almacén de política POR OPERADOR que convierta su respuesta en el criterio de la próxima
decisión): **`.meshkore/context/principles.md`**.

## ⭐ Cómo se orienta CUALQUIER arreglo del agente (CRIT-E3)

No hay lista de encargos soportados y no puede haberla. Dos mitades con tratamientos opuestos: **RECURSOS
clavados, completos y probados** (navegador, datos en tiempo real, parseo, capturas, puentes, evidencia, entrega
— aquí un fallo es un bug) y **RAZONAMIENTO abierto** (los prompts de los Brain Workers llevan fórmulas, recursos
y maneras de resolver, nunca un guion). Lo prohibido es adaptarse al caso de uso: *cambia una palabra del encargo
—hotel→restaurante, Sevilla→Los Ángeles— ¿sigue en pie?* Duda razonable → es un problema de RECURSOS. Doctrina
completa en `.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`.

**Otras formas de arrancar**: `BRAIN=direct`/`BRAIN=local` son baselines de modelo pelado (sin memoria ni
tools); `make lk-server` y `make agent-worker` levantan las dos mitades por separado para depurar.

## Documentación canónica y estándar MeshKore

Este repo sigue el **MeshKore Standard v27**. Toda la documentación, módulos y roadmap viven en `.meshkore/`.
Los agentes DEBEN trabajar dentro de esta estructura — no crear `docs/` ni carpetas ad-hoc fuera de ella.
Instalación y arranque para quien clona: **[`README.md`](README.md)** (multi-plataforma); el detalle, en
`zaelar-ops.md`. Mantener ambos alineados.

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
| **Reference docs by mechanism** (action map, jobs, task lists, decision model, daemon, connectors…) | `.meshkore/docs/modules/zaelar-module-map.md` §«Reference docs by mechanism» |
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
| **⭐ Superficie NATIVA nueva (panel, pestaña del muro, overlay) — los 13 puntos que fallan en silencio** | `.meshkore/docs/ops/zaelar-native-surface-workflow.md` |
| **Memory change workflow** | `.meshkore/docs/ops/zaelar-memory-workflow.md` |
| **Alignment review** | `.meshkore/docs/ops/zaelar-alignment-review.md` |
| **Model/latency benchmarks** | `.meshkore/docs/ops/zaelar-model-benchmarks.md` |
| **Changing a model (checklist + traps)** | `.meshkore/docs/ops/zaelar-model-change.md` |
| **Testing playbook** | `.meshkore/docs/ops/zaelar-testing.md` |
| **Monitorización de conversaciones de cluster** | `.meshkore/docs/ops/zaelar-cluster-conversation-monitoring.md` |
| Observabilidad / debug | `.meshkore/docs/ops/zaelar-observability.md` |

### Workflows — la frase del operador y el doc que la ejecuta

Los pasos NO se recuerdan de memoria: viven en su doc. Cada fila es un procedimiento completo.

| Cuando el operador dice… | Ejecutar |
|---|---|
| «pasa el protocolo» | `.meshkore/docs/ops/zaelar-change-protocol.md` — reiniciar+verificar → versión → diario/iniciativa/contexto → commit → push → deploy |
| «pasa la auditoría» / «audita el sistema» | `.meshkore/docs/ops/zaelar-audit-workflow.md` — reconocimiento → fan-out por 4 dominios → síntesis → informe + plan P0-P3 |
| (todo cambio de ESTRUCTURA o de invariantes) | `.meshkore/docs/ops/zaelar-docs-sync.md` — README, `CLAUDE.md`, `cluster.yaml`, doc de categoría, diagramas de `web/` |
| «pasa la revisión de alineación» (al cerrar un cambio de arquitectura/módulo/flujo) | `.meshkore/docs/ops/zaelar-alignment-review.md` — código ↔ contexto ↔ docs ↔ diagramas ↔ roadmap ↔ tests cuentan la MISMA historia |
| «pasa el workflow de widgets» (cambio del SISTEMA de widgets) | `.meshkore/docs/ops/zaelar-widgets-workflow.md` — «qué tocaste → qué actualizar»; un cambio trivial dentro de un widget no lo dispara |
| «añade un conector de X» / «haz un widget de Y» | `.meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md` — las cuatro decisiones previas, los 14 puntos de cableado que fallan VACÍOS, el último metro, declararlo HECHO, diez traps medidos |
| «pasa el workflow de memoria» (cambio ESTRUCTURAL de la memoria) | `.meshkore/docs/ops/zaelar-memory-workflow.md` — mapa de escritores y lectores, migración, docs, tests; termina con la revisión de alineación |
| «lanza un test del bot» / «lanza la batería» | `.meshkore/docs/ops/zaelar-testing.md` — Paso 0 ALINEACIÓN de escenarios → lanzar → JUEZ (bug real vs ruido STT vs rigidez) → informe archivado |
| «cierra esto» / «documenta lo que has hecho» / «pasa el cierre» | los 8 pasos en el `.meshkore/` de la RAÍZ (privado); lo que es de ESTE repo, abajo |

**Cerrar una tanda (lo que se salta siempre):** (1) el test con su NODO en `tests/run_testmap.py` — no está en el
mapa = no existe para «¿está todo verde?»; (2) el WHY en `.meshkore/docs/decisions.md`, y una línea en
`criteria.md` SOLO si una regla cambió; (3) la **bitácora del módulo** `.meshkore/modules/<módulo>/logs/<YYYY-MM>/`
(las palabras del operador, lo medido, los commits; numeración `T-NNN` GLOBAL, prefijos `N-`/`MK-`/`S-`/`TS-`/`C-`;
gitignoreada, en la lengua del operador).

**Contrato de testing para agentes:** antes de probar, `tests/README.md`. La entrada es
`./.venv/bin/python -m tests run <suite> [--case ID] --no-open` (exit code + Test Observatory en
`http://127.0.0.1:8765`; la app real sigue en `43917`). No dos runs gestionados en paralelo; nunca contra la
memoria real si hay fixture; todo test nuevo bajo `tests/<suite>/`; lo que cruce memoria + conversación +
widgets/workers se cierra además con `-m tests run journey --no-open`.

> Los diagramas de arquitectura viven como contenido público en `web/src/pages/technology/*.astro` (foto curada,
> NO espejo del código); `frontend/pages/architecture.html` se retiró el 2026-07-24. Si tocas topología, modelo o
> proveedor, actualízalos a mano; la fuente detallada sigue siendo `.meshkore/docs/architecture/`.

### Módulos — el mapa corto

Antes de crear un módulo nuevo, declararlo en `.meshkore/public/cluster.yaml`. Raíz SIN `.py`/`.html` sueltos;
arranque `make run` → `python -m server`.

| Módulo | Qué es |
|---|---|
| `voice/` | Motor **LiveKit** (`voice/engine/`): STT/TTS, turnos, VAD, barge-in. Encima, el contrato del cerebro agnóstico del transporte: `attention.py` (qué turno va dirigido a zaelar), `speech.py`, `observer.py` (SSE). |
| `nucleo/` | El **cerebro «Colmena»**: `flash/` (reflejo sub-segundo, enruta y responde), `workers/` (Brain Workers para lo que no cabe en un turno), `errands/` (un encargo que sobrevive al turno), `loop.py`+`scheduler.py` (pulso, crons, proactividad), `memory_agent.py`+`mem_processor.py` (único escritor de la memoria). A request's life: `spec.py` (born with its end state) → `circuit.py` (one loop, one bound, one report) → `tasks.py` (the durable row); `consent.py` (the one act-or-ask rule), `turn/` (decisions both channels share), `batch/` (several tasks → a list), `actionmap/` (a known phrase skips the model), `jev.py`, `susurro/`, `context_packs/`. |
| `search/` | El **servicio de búsqueda** (V2-782): una puerta (`find()`), una forma de resultado (candidato ≠ página que los lista), la ruta por veredicto, los proveedores declarados una vez con su sonda de salud (`python -m search.health`) y la cara HTTP `/api/search/*`. No importa al turno ni al motor; el servidor le enchufa sus costuras al arrancar. Mapa: `.meshkore/docs/modules/zaelar-search.md`. |
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

### Roadmap, iniciativas y daemon

Las iniciativas activas están en `.meshkore/roadmap/initiatives/`; anclar cada tarea a una. El diseño del cerebro
«Colmena»: `.meshkore/roadmap/EPIC-v2-colmena.md`. El daemon de MeshKore es un **servicio único compartido**
(`daemon.meshkore.com`): este repo NO arranca ni incluye uno — no crear `.meshkore/daemon.py`, ni targets
`make meshkore`, ni bindear el puerto 5570.

## Lo que el agente puede AFIRMAR, y a qué se pide permiso

Un «sí» se contesta con un ARRANQUE, nunca con una terminación (CRIT-V3); una op transaccional no entra en la
lista de tareas (CRIT-C7); la agenda va DIRECTA y un borrado no pregunta, con papelera y `restore`
(CRIT-C3). Todo en `.meshkore/docs/criteria.md` §1-2; el porqué, en el diario (V2-743, V2-748).

## Quién decide a qué tarjeta va una orden

Una tabla de verbos no es un enrutador: la gramática PROPONE, el modelo de decisión elige entre lo DECLARADO y
un backstop no desmiente un veredicto ya pagado (CRIT-K1). El veredicto COMPLETA al modelo, nunca lo desmiente
(CRIT-K2); un descriptor se escribe bajo el corte y se mide contra su VECINDARIO (CRIT-K7); un clasificador
delante del modelo es un PRECIO que solo se paga donde la decisión no se puede leer después (CRIT-K9).
`.meshkore/docs/criteria.md` §3; las alertas —lo que ya se probó y lo que costó— en
`.meshkore/docs/architecture/zaelar-architecture.md` §«ALERTS», que se lee ANTES de escribir una regla que lea
las PALABRAS del operador. ⚠️ Un desarme puede dejar bytecode rancio: el arnés borra `__pycache__` al restaurar
(CRIT-W5).

## Un fallo nuestro no es un proveedor caído

La excepción decide de quién es la culpa (un status HTTP es suyo, un error de Python pelado es nuestro), la
MISMA petición releva al suplente en el bucle de conexión, y los embeddings no tienen relevo (CRIT-R1, CRIT-R3).
`.meshkore/docs/criteria.md` §6; el incidente, en el diario (V2-758).

## Decisiones clave — están en su propio fichero

El diario del motor (una entrada por tanda: qué se decidió, por qué, y el fallo real que lo motivó) vive en
**`.meshkore/docs/decisions.md`**, y lo más viejo en `.meshkore/docs/decisions-archive.md`. Se lee ANTES de
tocar una pieza — te dice qué se intentó ya y qué se descartó, que es la mitad del trabajo que no se repite.

Al cerrar una tanda, la entrada se escribe allí, no aquí. Este fichero es de REGLAS y PUNTEROS, y el diario es
HISTORIA: lo que el motor obedece HOY está, una línea por regla, en `.meshkore/docs/criteria.md`.

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

**La pasada ancha se lanza con `tests/watchdog.py`** (primera de las «Hard rules»): detecta y NOMBRA el test
que se cuelga, mata el grupo de procesos y no admite dos barridos a la vez. Mientras iteras sigue siendo el
FICHERO que has tocado y su DESARME; `pytest` a pelo sobre el árbol, nunca.

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

- ⚠️ **UNA PASADA ANCHA SE LANZA CON EL VIGILANTE, NUNCA CON `pytest` A PELO** (CRIT-W5):

  ```sh
  ./.venv/bin/python tests/watchdog.py                           # todo lo determinista (~7 min, 10.8k verdes)
  ./.venv/bin/python tests/watchdog.py tests/voice/unit          # una carpeta
  ./.venv/bin/python tests/watchdog.py --impacted origin/main    # solo lo que tu diff alcanza
  ```

  Nombra el test que se cuelga, mata el GRUPO de procesos y se niega a dos barridos a la vez (nodo 7.53). Mientras
  iteras: el FICHERO que has tocado y su DESARME. `tests/run_testmap.py` sin argumentos es una pasada ancha a pelo;
  `--list` solo imprime. Un rojo dentro de una pasada ancha se reproduce en su carpeta a solas antes de tocar nada
  (CRIT-W6). La causa medida el 2026-09-20 —un test que leía un vídeo de 84 GB del operador— está en el diario.
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
- No commitear `~/.hermes/memories/USER.md` — es perfil personal, no va
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


## La columna del chat es la conversación

Una línea de voz se DEBE cuando la boca la empieza, su identidad es el `trace` del turno y un fragmento
retenido solo se pega al siguiente si el siguiente lo continúa (CRIT-V7); una queja sobre lo recién hecho es una
orden de rehacerlo, con la licencia de la op que corrige; el nombre del asistente cambia por veredicto y falla
CERRADO (CRIT-V8). `.meshkore/docs/criteria.md` §1; el porqué, V2-752 y V2-747 en el diario.

## Construir o reescribir una tarjeta suya se le pregunta antes

En la única puerta por la que se enciende un worker (`dispatch._run_session`, `kind == code`), con el
confirm-gate entero; exento el dev-worker de cluster (CRIT-C4). ⚠️ `widgets/_user/<id>/` ENSOMBRECE al
built-in y está gitignoreado: antes de diagnosticar un widget, **qué fichero corre**. Una pregunta educada es
una orden; un turno que es SOLO un número no mueve nada (CRIT-K7). `.meshkore/docs/criteria.md` §2-3.

<!-- OPERATOR_CONTENT_END -->
