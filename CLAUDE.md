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

Asistente personal por voz **multidioma** (**inglés por defecto**, y se pasa SOLO al idioma del operador en
cuanto lo detecta — ver «Arranque idiomático» abajo), siempre activo. Arquitectura: STT →
**cerebro propio «Colmena»** → TTS, sobre **LiveKit Agents**. El cerebro (`nucleo/`), la memoria (`memory/`) y la
proactividad son **nuestros**: zaelar no depende de ningún agente externo.

**Run**: `make run` (= `BRAIN=nucleo`) → levanta el stack LiveKit (servidor LiveKit **nativo, sin Docker** + web con
worker EMBEBIDO) en http://localhost:43917 (Chrome). **El core NO requiere Docker**: usa el binario `livekit-server`
(`make install-livekit`); Docker es solo fallback si falta el binario. `BRAIN=direct`/`BRAIN=local` = baselines de
modelo pelado (sin memoria/tools). `make lk-server` / `make agent-worker` para depurar por separado.

## MeshKore Standard v27

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
| Security | `.meshkore/docs/security/zaelar-security.md` |
| **Change protocol** | `.meshkore/docs/ops/zaelar-change-protocol.md` |
| **Audit workflow** | `.meshkore/docs/ops/zaelar-audit-workflow.md` |
| **Docs & structure sync** | `.meshkore/docs/ops/zaelar-docs-sync.md` |
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

### Módulos declarados (`.meshkore/public/cluster.yaml`)

Antes de crear un módulo nuevo, declararlo en `.meshkore/public/cluster.yaml`. Raíz SIN `.py`/`.html` sueltos;
arranque `make run` → `python -m server`.

- `voice/` — **motor LiveKit** en `voice/engine/` (INI-012): `AgentSession` (streaming, turnos, VAD, barge-in,
  preemptive-gen) + registry de providers + perfiles remote/local (`core/`, `speech/`, `llm/`, `pipeline/agent.py`
  con `make_server()` embebible, `speech/voices.py`). El turn-taking/VAD/barge-in los gobierna LiveKit (VAD Silero +
  turn-detector `MultilingualModel` + `allow_interruptions`). Nivel superior = contrato del cerebro **puro y
  agnóstico del transporte**: `tag_protocol.py`, `speech.py`, `brain_notes.py`, `proactive.py`, `prompt.py`,
  `health_state.py`, `llm_health.py`, `observer.py` (SSE), `attention.py` (gate de atención V2-015 — decide qué
  turno va dirigido a zaelar; ambient vs atendiendo).
- `nucleo/` — **cerebro propio «Colmena»**: FlashBrain ORQUESTADOR + workers Claude Code (V2-036; el "SlowBrain
  cerebro aparte" se disolvió). Se expone al motor como provider
  `livekit.agents.llm.LLM` (`voice/engine/llm/providers/nucleo.py`, `BRAIN=nucleo` = default). `nucleo/flash/` =
  **FlashBrain** reflejo sub-segundo (`router.py` clasifica el input + `fast_client.py` cliente de modelo rápido
  no-razonador **por invocación** + `frontend.py` gestor de frontend/widgets + `procs.py` lanzador de procesos +
  `escalate.py` escalado + `prompt.py` [ensambla el prompt del turno V2-027: ESTADO compuesto + capa TERSA de
  recursos, ~30 líneas] + `memory_cache.py` [cachea `memory.compose_state()` fuera del turno + siembra la misión] +
  `prewarm.py` [calienta FlashBrain+browser en el arranque, V2-024] + `dialog.py` [estabilidad conversacional V2-032:
  break-loop + poda de historial + anti-degeneración, COMPARTIDO por voz y probe] + `probe.py` [canal de PRUEBA
  headless, 3ª forma de testing: `POST /api/flash/say`]). `nucleo/websearch.py` (hermano de `flash/`) = **búsqueda web COMPARTIDA** por los dos cerebros
  (V2-022, ver decisión clave); `nucleo/browser_search.py` = capa **Google GRATIS vía Chromium persistente** (V2-024). **Latencia — la memoria NO está en el turno síncrono**
  (V2-011): el bloque de ESTADO (nombre/trato/temas) sale de `memory_cache` (caché de sesión, TTL + refresco async
  + invalidación por `memory.updated`), y el recall semántico (`prompt.compose_recall`) es **bajo demanda**
  (`prompt.needs_recall`) y **fuera del event loop** (`asyncio.to_thread`) — el turno de charla nunca dispara el
  retriever. `nucleo/loop.py` (~1 Hz) + `nucleo/scheduler.py` (**cron PROPIO** respaldado
  por `memory.journal`) + `nucleo/cron_api.py` (`/api/cron`, panel ⏰) + `nucleo/sparks.py` (chispas doble-gate) =
  **loop orquestador** (tareas programadas + proactividad + dispara el consolidador de memoria off-hot-path + reporta
  por voz+UI; montado en el lifespan con `BRAIN=nucleo`). `nucleo/dispatch.py` (dispatcher: compone prompt
  [contexto+tarea] → CodeAgent con modelo por invocación, consume `escalate.requested` del bus, entrega por voz+UI) +
  `nucleo/memory_agent.py` ★ (agente de MEMORIA, único escritor a `memory/`; su `compose_context` = **dossier v2
  multi-eje** del worker V2-056: perfil sin misión + reglas + ⚠️ críticos SIEMPRE + recall + `by_concepts` + agenda,
  solo durables, `to_thread`) + `nucleo/mem_processor.py` ★ (el CORAZÓN de escritura V2-013:
  **`deepseek/deepseek-v4-flash` DIRECTO** (`api.deepseek.com` desde 2026-08-16; antes vía AIMLAPI) por config
  `§memory` desde 2026-08-09 — bench §12.3: iguala a
  `gpt-4.1-mini` en completeness (98,5 vs 98,9%) y precisión (100%) por **−55% de coste**; `gpt-4o-mini` VETADO
  (mete una alergia en inglés en `slot=operator.diet`, que la borraría al cambiar de dieta); key
  POR ENDPOINT + salud con alerta por racha de fallos [incidente 2026-07-17/19: 2 días caído en silencio];
  escribir puede ser lento, prioriza escribir BIEN — DESTILA cada turno en píldoras curadas — dato+metadatos,
  decide DESCARTAR/ESTADO/CORTO/LARGO + importancia + `slot`; off-hot-path, fail-open a la heurística [que ya NO
  ensucia: degrada a short+TTL]; **GATES de PRECISIÓN deterministas V2-033**:
  descarta peticiones/preguntas/ack reificadas, no deja que un nombre garbleado del STT pise la identidad del `state`
  —cuarentena— y no hace durable una preferencia efímera) + **`nucleo/workers/`** (**Brain Workers V2-038** —
  sustrato AGNÓSTICO: `base.py` [`WorkerBackend`/`WorkerEvent`/`WorkerSpec`], `claude_session.py` [stream-json vivo],
  `generator_session.py` [widgets, envuelve el generador matable], `codex_session.py` [Codex CLI, `exec --json`],
  **`grok_session.py`** [Grok Build; HEREDA de `claude_session` porque su wire format es el MISMO, ver decisión clave],
  `registry.py`
  [`get_backend` por config, mezclable], `session.py` [`WorkerSession` + `SessionRecord`], **`providers.py`**
  [CADENA de endpoints Anthropic-compatible + relevo por cuota agotada, ver decisión clave]) = capa de trabajo async
  INTERACTIVA. `nucleo/agentes/` (interfaz `CodeAgent` one-shot V2-036 — `worker/web/web_cc/otros.py` **PARKEADOS**
  en V2-038; solo se reutilizan sus helpers de detección de widget). **Puentes de los workers**: `nucleo/mem_cli.py`
  (`hbmem` — memoria serial, recall/remember por HTTP) · `nucleo/agent_report.py`+`nucleo/agent_api.py` (`hbnote` —
  reporte de fase al bus) · **`nucleo/worker_bridge.py`+`nucleo/worker_api.py`** (`hbask`/`hbact`/`hbsay` —
  pregunta/pide-tool/dice al usuario, plano request/response V2-038, `/api/worker/act`, política + piggyback + token) ·
  `nucleo/nav_cli.py`+`widgets/navegador/act_api.py` (`hbweb` — conducir el navegador) · **`nucleo/widget_cli.py`**
  (`hbwidget` — LEER/OPERAR un widget del canvas: `read`/`data`/`show`/`close`, acción `widget_data` de
  `/api/worker/act` con gate del catálogo canónico + provenance worker; V2-061, el PUENTE que refleja en los widgets
  lo hecho en la realidad). `nucleo/danger.py` = gate de
  acciones irreversibles. **`nucleo/susurro/`** (V2-053) = **auto-auditoría conversacional «Susurro»** — enchufado
  SOLO por el bus (topic `turn.completed` + fricción), modelo potente configurable §susurro, correcciones de
  catálogo cerrado (ver decisión clave). **`nucleo/homeostasis.py`** (V2-070) = **LATIDO AUTÓNOMO** — el tercer
  nivel, HERMANO del cerebro (no parte de él): mantiene la MÁQUINA sana (recicla el motor LiveKit degradado cuando es
  seguro, rota logs, evicta cápsulas muertas), determinista y SIN LLM, `start()/stop()` en el lifespan como los otros
  supervisores; ver decisión clave «Homeostasis».
- `memory/` — **memoria central** tipo humana, SUBSTRATO 100% local (los LLM de escritura van por API — ver
  decisión clave), un solo fichero SQLite `zaelar.db` (WAL, en
  `memory/_data/`): substrato compartido que escriben el FlashBrain, el agente de memoria y los widgets, y lee el
  retriever en la ruta caliente (ms). **`memory.compose_state()`** (V2-027) compone el **ESTADO COMPARTIDO** que
  ven los dos cerebros — misión (`state.mission`) + situacional + conversación reciente sintetizada — como lectura
  DIRECTA (µs, sin LLM ni retriever); lo cachea `nucleo/flash/memory_cache` fuera del turno. Cada recuerdo es una
  **PÍLDORA**: dato canónico (`text`) + metadatos (`slot`/`meta`, schema v2). **`slot`** = clave canónica del hecho singular (`operator.name`, `goal.current`…) →
  el writer hace **supersede/dedup EXACTO sin LLM** ("el más reciente MANDA": mismo dato = refuerza; dato cambiado =
  invalida TODOS los vigentes — auto-curativo). El **vocabulario de slots vive en el REGISTRO ÚNICO
  `memory/slots.py`** (auditoría 2026-07-14): alias + campo de `state` + flag de identidad, consumido por writer
  (`canon_slot`), memory_agent (gate P0b) y el prompt del procesador (catálogo GENERADO) — las tres capas no pueden
  divergir; el consolidador añade `heal_slots()` (normaliza legacy + colapsa multi-vigentes en cada sueño). El
  **contrato v2 del átomo** añade `value` (→ `state_patch` sintetizado MECÁNICAMENTE del registro) y `change:
  none|update|correction` (señal de cambio del PROPIO procesador multilingüe → el gate anti-garble la consume; las
  regex es/en quedan de backstop, no de mecanismo único). Tablas `state·memories·vec_memories·fts_memories·edges·episodic·journal` ·
  cola + writer (único escritor, embeddings al insertar) · embeddings (embeddinggemma 768 vía Ollama, fallback
  fastembed; provider configurable `memory.embed_*` + `memory/reembed.py` con firma de modelo) · retriever
  (sqlite-vec + FTS5 → RRF k=60 → score α·rel+β·rec+γ·imp+δ·uso → **reranker** cross-encoder local `memory/rerank.py`
  → graph_expand) · grafo ·
  consolidador (sueño LIGERO: decay Ebbinghaus POR VENTANA + dedup + prune_invalid + eviction por peso, pinned
  intocable) · **`memory/rem.py`** (V2-056: sueño PROFUNDO «fase REM» diario — repara vectores `embed_pending` +
  dedup SEMÁNTICO por coseno + INSIGHTS por concepto [`slot=insight:<c>`, hook LLM inyectado desde
  `nucleo/memllm.py`, **`deepseek-v4-flash` vía AIMLAPI** desde 2026-08-09 — bench §12.4] + higiene con alerta;
  kill-switch `ZAELAR_REM`. ⚠️ Esta fase estuvo MUERTA semanas: `.format()` sobre un prompt con llaves literales
  lanzaba `KeyError` y el `except` lo volvía un warning — ver la decisión «Memoria central») · capa **episódica** (absorbió el
  antiguo `files/`: paste/drop → `memory/server_api.py` → `memory.write_episode`, binario + resumen buscable, carga
  lazy) · fachada + señal `memory.updated` por el bus. `memory/seed_from_hermes.py` = importador one-shot que siembra
  el perfil del operador desde `~/.hermes` si existe (best-effort, solo-lectura). **`memory/vault.py`** ★ (V2-060:
  BÓVEDA de secretos del operador CIFRADOS — cripto asimétrica sealed box vía PyNaCl + sobre passphrase Argon2id +
  passkeys WebAuthn PRF; tablas `vault_meta`/`vault_secrets`), **`memory/secrets.py`** (detección FAIL-CLOSED +
  redacción) y **`memory/vault_api.py`** (`/api/vault/*`, loopback) — ver la decisión clave «Bóveda de secretos».
  Diseño en `zaelar-memory.md`.
- `observability/` — **QUIÉN · CUÁNDO · en qué FLUJO** (V2-090). Completa el registro de eventos (que ya contaba
  QUÉ pasa) con los ejes para ANALIZARLO: `identity.py` (**`user_id`** estable por instalación —UUID4 aleatorio
  en `config/identity.json` gitignored, con **INIT EXPLÍCITO en el lifespan del server** desde 2026-08-16 (antes
  se generaba solo, la primera vez que CUALQUIER código llamara a `user_id()`; ahora queda creado y logueado en
  el arranque, igual de visible que el `ZAELAR_USER_ID` que una Machine de nube ya trae puesto) — en la nube
  MANDA ese `ZAELAR_USER_ID` del provisioner, `user_id()` lo prefiere sobre el fichero local— y **`session_id`**
  por SESIÓN DE TRABAJO del operador: arranca al conectar, se cierra con ⏻ o al cerrar la pestaña, y una
  reconexión NO la parte en dos) · `flows.py` (lectura por **CORRELATION ID**: flujos con duración real de punta
  a punta, familias, actores, tokens y errores; detalle cronológico; sesiones; cobertura) · `api.py`
  (`/api/observability/*`). **El correlation id NO es un id nuevo: es el `trace` de V2-044 PROMOVIDO** de campo
  del JSON a columna indexada (`events.corr_id`) — un segundo id paralelo se habría separado del primero en la
  primera costura cross-loop sin coser. Un flujo nuevo nace con cada petición del operador; lo que continúa un
  flujo vivo hereda el suyo. **A correction spoken while a task is still live MERGES into that task's `corr_id`
  instead of opening a new one** (2026-08-15): `send_to_worker`'s handler (`nucleo.py::_on_tool_call`) already
  resolves its target via `dispatch.resolve_sessions()`; when that resolves to exactly one live session, this
  turn adopts its `trace_id` (`dispatch.trace_of` + `trace.adopt`) instead of keeping the fresh one `trace.begin()`
  opened at turn start. With several live sessions and no unambiguous match, nothing merges — a stray extra flow
  beats guessing which task a correction belongs to. A flow's end is now also EXPLICIT (`kind="flow"`, emitted
  where the worker session that spawned it finishes), not just inferred from silence. **A single utterance split
  across several LiveKit turns also merges (2026-08-15):** LiveKit closes one turn per STT-final segment, so a
  long sentence spoken without pauses used to open a fresh trace per fragment — `_begin_or_adopt_trace()`
  (`nucleo.py`) checks the V2-096 accumulator's `pending()` instead: while a fragment chain is open, the next
  turn ADOPTS its trace rather than opening one, cleared once the chain resolves. Known limit, not solved here: if
  the accumulator judges a sentence complete (a closing period) and the operator keeps talking about the same
  thing right after, that reopens as a NEW chain/trace — a real improvement, not a guarantee of one flow per
  real-world task. **A pending confirmation's answer also merges into the turn that asked** (`widgets/
  confirm.py::request()` captures `trace.current()`, `_resolve_confirm()` adopts it before executing/cancelling)
  — the ask/answer/action of an irreversible confirm-gate now reads as one flow even across a barge-in-cancelled
  reply attempt in between. `flows()`'s SQL exposes `origin` (the `trace.begin(origin=...)` argument: `turno`/
  `kickoff`/`ui`/`cron`/`proactivo`/`cluster`/`probe`) and `title` (that root event's text) per flow — what the
  master's column-board (`cloud/backoffice`, private repo) uses to tell a real task apart from session
  initialization (kickoff greeting, canvas-restore reconciliation within the session's first ~10s) and to label
  each column/rail item with more than a bare corr_id. **A plain conversational flow now closes EXPLICITLY too**
  (2026-08-15): only a worker-spawned flow had an explicit close before this; the master could only guess
  liveness from recency, and guessed wrong the instant a turn finished (reported live: "restarted the system…
  still shows seven active flows"). `_run`'s success path (never the `CancelledError` branch — a barge-in
  cancellation may still get continued by the next fragment) calls `_maybe_close_flow()`, which closes the
  current trace UNLESS the V2-096 accumulator still expects more on it, a confirmation asked on it is still
  pending, or a worker is still running on it (`dispatch.has_live_trace`, the reverse of `trace_of`) — that
  worker owns the close instead. **A confirmation's "sí"/"no" is now resolved BEFORE any slow work, not only
  after** (2026-08-15): the old deterministic backstop (`classify_reply` + resolve) only ran after the model's
  full response streamed — a turn cancelled by barge-in before reaching it lost the answer in total silence,
  leaving the confirmation pending forever with the widget untouched (reproduced live: operator confirmed
  clearing the agenda by voice, the reply's turn got barge-in-cancelled, and the agenda never changed, with zero
  trace of it in the log). A clear yes/no is now resolved right after the hard-interrupt check, before the model
  is even called; ambiguous replies still fall through to the old late-stage backstop. **A widget can opt out of
  the visual Sí/No overlay** (`"confirm_ui": false` in its manifest, `nucleo.py::_confirm_ui_paints`; e.g.
  `widgets/agenda/manifest.json`, per an explicit operator request — "the agenda widget is voice-only"): the
  confirmation itself, and voice resolution, are completely unchanged — only the SSE emit that paints the card
  overlay is skipped. SOLO LECTURA: el único escritor de `events` sigue siendo
  el sink del bus. Fase LOCAL entregada; nube + privacidad en `INI-021` (raíz del workspace).
- `bus/` — **Sistema Nervioso**: pub/sub de señales in-process (asyncio, patrones fnmatch + `emit_sync`
  loop-agnóstico vía `call_soon_threadsafe` para entrega cross-loop job-thread↔uvicorn). `bus/log.py` = log durable
  de eventos en SQLite (`zaelar.db`, tabla `events`, WAL). `bus/sse.py` = puente SSE al frontend (`GET /events`).
  Transporte HÍBRIDO: llamadas directas en la ruta caliente de voz + eventos para lo async/fan-out. **Nada de
  Kafka/broker.**
- `frontend/` — interfaz como app de **módulos ES sin build**, migrable a Solid (core reactivo + services +
  components + widget desktop). Voz vía **cliente LiveKit** (`services/session-lk.js` + SDK vendorizado en
  `frontend/vendor/`). Ver `zaelar-modules.md §Frontend`. **SUPERFICIES NATIVAS del frontend = «widgets de
  SISTEMA», INTOCABLES** (V2-080): su LISTA CANÓNICA ÚNICA vive en **`frontend/app/core/system-surfaces.js`**
  (`SYSTEM_SURFACES` + `isSystemSurface()`) — panal de actividad, cámara/mic, orbe, TopBar, estado de conexión,
  chat (Chat/Procesos/Crons), panel de estado ◉, config ⚙, benchmarks, debug ◷, mapa de memoria 🧠, wizard 🧭,
  bóveda 🔐, banner de aviso y splash de arranque. `main.js` las MONTA desde esa lista (sin duplicar). El
  generador/`lifecycle` NUNCA las tocan (solo tocan `widgets/<id>/`). **Todo lo demás en pantalla son WIDGETS DE
  USUARIO** (catálogo `widgets/<id>/`, full-stack `manifest.json`+`data.py`+`widget.js`), variables y creados
  por/para el usuario **aunque se distribuyan de serie** — como los conectores. Añadir una superficie nativa nueva
  = añadirla a `system-surfaces.js`. **V2-082:** cada superficie dirigible por voz lleva `name` + `aliases` FIJOS
  (hardcodeados en el front, NO editables) — espejados en el backend `widgets/system_surfaces.py` (test de sincronía)
  para que el resolver de nombres las conozca. Cada tarjeta de widget de usuario pinta un HEADER genérico (en
  `desktop.js`, sin tocar su `widget.js`) con el NOMBRE + un ⚙ que despliega sus ALIAS editables.
- `server/` — FastAPI app + routers + entrypoint (`server/__main__.py`); corre el **agent worker de LiveKit
  EMBEBIDO** en el proceso (lifespan), y arranca en ese mismo lifespan el loop de `nucleo/`, el supervisor de
  widgets `backed` y el consumidor de la cola de memoria. Routers: `livekit_api` (token + config + swap de
  session.js), `voice_api`, `cron_api` (`/api/cron`), `wizard_api` (V2-040), `spotify_api` (V2-041), `config_api`
  (V2-043: `/api/config*` — el área de configuración full-screen), **`memory/vault_api`** (V2-060: `/api/vault/*` —
  bóveda de secretos, montado siempre), widgets, pages.
- `widgets/` — widgets full-stack (`data.py` + `widget.js` por carpeta), generador, catálogo, runtime.
  Dos *kinds* en `manifest.json`: `passive` (por defecto) y **`backed`**: un widget con proceso propio (`owner.py`)
  supervisado por `widgets/supervisor.py` (mailbox + reinicio con backoff + desactivar tras N fallos, aislado de la
  voz). Widgets backed = **`navegador`** (un navegador web real dentro de zaelar) y **`mensajeria`** (mensajería
  unificada WhatsApp+Telegram; su owner triaja en el propio widget con un modelo LOCAL, gated `"gate":"nucleo"`).
  **`widgets/background.py`** (V2-034) = planificador de **ejecución en BACKGROUND con ciclo**: un widget declara
  `"background": {"every": "1m"}` y sigue trabajando OFF-SCREEN en su periodo (mínimo 1s) — `data.py:tick(ctx)` de
  un passive corrido en un hilo, o un comando `tick` encolado a un owner backed — para refrescar datos y **volcar
  a memoria** lo que el operador pueda preguntar por voz (ver decisión). `widgets/actions.py` = semántica de
  acciones (V2-025); `widgets/refs.py` = resolución de referencias a items (V2-026).
- `config/` — settings runtime gestionados por la UI (gitignored): `settings.json` (⚙ STT/TTS/voz/idioma),
  `connectors.json` (flags+credenciales de conectores), `v2.json` (routing de modelos `fast`/`code_agent` +
  **`memory`** [reranker + embedding, V2-030] + `active_brain()`), `meshkore.json`. Cada uno con su módulo dueño
  (`settings.py`/`connectors.py`/`v2.py`) y **vista pública redactada** (secretos → `<clave>_set: bool`; cualquier
  clave que termine en `api_key` se redacta). `profiles.py`+`doctor.py` = perfiles coordinados + detector (wizard
  V2-040); `credentials.py` = único escritor del credential store. **`balances.py`** (V2-043) = saldo de APIs
  externas (proactivo donde se expone —ElevenLabs—, reactivo por error clasificado para el resto). El **área de
  configuración full-screen** (⚙, V2-043) se sirve por `server/config_api.py` (elige API/modelo por PIEZA) +
  `frontend/app/components/ConfigPanel.js`; sus alertas de saldo salen en el diálogo de estado (◉).
- `connectors/` — conectores externos; **`connectors/files/` = archivos en la NUBE** (Google Drive +
  OneDrive, V2-557: registro tipado de proveedores + PKCE compartido + un cliente por proveedor tras la
  **fachada agnóstica** `service.py`, que devuelve UNA forma normalizada — un tercer proveedor no toca el
  widget; doc `zaelar-cloud-files.md`); `connectors/meshkore/` = canal nativo de clusters (3er I/O junto a voz+chat),
  conducido por el **motor del FlashBrain en perfil UNTRUSTED** (V2-069: `brain.py` adapta el canal al motor →
  `nucleo/flash/cluster.py`, tools off + system identidad-safe) con **cápsula** de conversación (`capsule.py`);
  `connectors/architect/` = proveedor de código/proyectos sobre el
  daemon MeshKore compartido (tags `[[architect.*]]`, operator-only); `connectors/whatsapp/` = WhatsApp personal
  (bridge Baileys vendorizado); `connectors/telegram/` = Telegram personal (userbot Telethon); `connectors/email/` =
  **email personal** (V2-051, IMAP/SMTP **stdlib puro**, lógica vendorizada del adaptador de Hermes — leer+triar+
  **responder** por SMTP con threading; app-password + presets Gmail/Outlook/otro; el más limpio de los tres);
  `connectors/messaging/` = **capa compartida** de mensajería (ahora con OUTBOUND: cola `pending_reply` + `msg.reply`
  → tool `reply_message` con confirm-gate). Ver `zaelar-modules.md §Connectors`. Slots futuros: LinkedIn, X.
  **Contactos como memoria + envío-a-persona (mándale un mensaje a X) + conectores Apple/Google + red de agentes =
  iniciativa de DISEÑO `V2-052` (pendiente de OK del operador).**
- `tests/agent_headless/harness/` — harness de evaluación conversacional sintética + juez.
- `tests/voice/e2e/mic/` — self-test headless del transporte micrófono→STT por WebRTC.
- `tests/voice/e2e/agent/` — tester de voz (INI-013): 2º participante LiveKit que HABLA con zaelar y un JUEZ que evalúa lo que HACE.

`files/` quedó plegado en la capa episódica de `memory/` (shim de compatibilidad). Raíz (no-módulos): `README.md`,
`Makefile`, `requirements.txt` + `.venv/`, `Dockerfile`/`fly.toml`/`.dockerignore`, `scripts/` (tooling de
instalación por-OS), `CLAUDE.md`. **Logging → `.meshkore/logs/`** (no crear `logs/` en la raíz).

### Roadmap e iniciativas (`.meshkore/roadmap/`)

Las iniciativas activas están en `.meshkore/roadmap/initiatives/`. Anclar cada tarea a una iniciativa. El diseño del
cerebro «Colmena» vive en `.meshkore/roadmap/EPIC-v2-colmena.md`.

### Daemon (NO es por-proyecto)

El daemon de MeshKore es un **servicio único compartido** (hospedado en `daemon.meshkore.com`), que da
servicio a todos los proyectos del cluster. **Este repo NO arranca ni incluye un daemon propio.** La adopción
del estándar se hace apuntando el front del Architect a la URL de la carpeta `.meshkore/` de zaelar; el daemon
la lee, identifica el proyecto por `public/cluster.yaml` y lo onboarda (incluido el bloque `MESHKORE_PREAMBLE`).
No crear `.meshkore/daemon.py`, ni targets `make meshkore`, ni bindear el puerto 5570 desde aquí.

## Decisiones clave

> **Compaction policy (V2-601 T-18, 2026-09-06).** This log holds recent decisions VERBATIM and a one-line
> citation index for everything older. The full text of every archived entry lives, untouched and in its
> original order, in `.meshkore/docs/decisions-archive.md`; the dense per-decision source is each entry's
> initiative under `.meshkore/roadmap/initiatives/`. When closing work, keep writing full entries here — and
> when the size ratchet (`tests/infrastructure/unit/test_claude_md_ratchet.py`) trips, move the oldest
> full entries to the archive and leave their index line, exactly as this pass did. Never delete a citation:
> the closure trinquete requires every delivered initiative to stay cited in this file.

- **A NAME is a UI string, and the voice keeps answering to the one it shipped with (V2-694, 2026-09-14)**:
  the operator, on a session he had deliberately started in English — «el título de los widgets es en
  castellano… una vez está inicializada la sesión en inglés, se usa en inglés», and the rule that frames the
  whole batch: **«todos los nombres, etiquetas, títulos, botones… todo es configurable cuando se inicializa un
  idioma»**. **MEASURED before touching anything, because the first question was whether HE had broken it**:
  nothing had switched. `config/settings.json` held `stt_language: "en"`, every turn's prompt said «Responde
  ÚNICAMENTE en English», and `i18n.init.detect.should_detect()` is False the moment a language is persisted —
  so speaking Castilian could not have moved it and a reset only would with `wipe_profile`, which he had not
  ticked. **The Castilian was HARDCODED.** V2-613 built the seam (`ctx.t`/`ctx.lang`) and migrated two pilots;
  the other thirteen widgets carried their text inside `widget.js`, and every card TITLE came from
  `manifest.json`, which V2-082 had frozen on purpose because the voice resolver matches against it.
  - **That freeze is the interesting half.** The name is now `widgets.<id>.name` / `surfaces.<id>.name`, read by
    `widgets/registry.py::display_name`, so it follows the operator's language like every other label — and the
    manifest's own name stays as the FALLBACK (a generated widget has no bundle row and still needs a name) and
    **stays in `aliases`**. Translating it without keeping the original would have quietly retired half the
    vocabulary of every install that has ever spoken Castilian: a regression with no error message anywhere.
  - ⚠️ **`widgets/naming.py` (the worker's door) went through the registry and answered to the translated name
    from the first minute; `widgets/runtime.py::identify` (the VOICE) built its own lexical index straight off
    the manifests and did not.** Measured with the bundles in place and nothing else changed: «messages»,
    «downloads» and «browser» resolved to None for the voice while resolving correctly one module over — an
    English operator could READ «Messages» on the card and not be able to say it. Two doors into one namespace
    (V2-555), found only because the test was written against the real doors instead of against the registry.
  - **~480 strings across the catalog**, migrated as `tt("key", params, "<the literal>")` where the fallback is
    byte for byte what was hardcoded — so a widget rendered outside the engine behaves exactly as before and the
    change is reviewable line by line. ⚠️ **Ten module-level TABLES were the trap**: `const STATUS = {ok:
    "Hecho"}` is built at IMPORT time, before any `ctx` exists, so its text freezes in whatever language loaded
    first and survives every later switch; every one became a function resolved per paint. ⚠️ And **a whole class
    was invisible to the first scan** — sentences written as template literals, and labels living inside a
    `${…}` substitution (`${n === 1 ? "canción" : "canciones"}`) — so the scanner had to learn that a
    substitution is CODE, not template text, and then that a regex literal can contain backticks
    (`widgets/documento`'s `/`([^`]+)`/g` desynced it into reading every later comment as operator-facing text).
  - **The ratchet is the deliverable.** The old one recognised only a FULL key, so with fourteen widgets migrated
    it would still have been green having measured one — *a ratchet that cannot see the thing it ratchets reports
    safety*. It now derives each widget's prefix from its own helper, and refuses: a key missing from either
    bundle, an accented literal outside a translation call, and — **language-independently**, which is what made
    it bite — ANY literal assigned to `textContent`/`title`/`placeholder`/`alt`/`ariaLabel`. That last half was
    added because disarming `tt("seeds", …)` back to a bare `"Semillas"` left the accent check GREEN.
  - **Changing language is MANUAL and never spoken** (his rule: «hay que hacer todas las traducciones de todos
    los prompts, de todos los widgets… no es una cosa que vamos a permitir hacer con la voz»). No tool changes
    the language and none is added. ⚠️ Measured: the desktop ⚙ had **no language control at all** — the picker
    existed only in the first-run veil and the phone's sheet, so on this shell the answer to «I want it in
    English» was a factory reset. ⚙ → Apariencia carries it now, posting to `/api/i18n/choose/{code}` and never
    to the raw `stt_language` knob: that endpoint is what LOCKS the choice, generates the bundle for a language
    we do not ship, realigns the TTS voice and speaks the confirmation — writing the setting directly would
    leave a Swedish operator with a Swedish `stt_language` and an English interface. It asks **twice**.
  - `config.settings.update` is the ONE seam both doors cross, so that is where `i18n.runtime.invalidate()` and
    `registry.refresh_state()` live. On the client, `Desktop.relanguage()` re-rendered every widget's BODY since
    V2-613 and left the card HEADER alone — fine while the title was a constant, wrong the moment it became a
    translated string: it drops the registry and the compact-index caches and re-applies the names.
  - Nodes **4.11** (widened), **4.172** and **4.173** (RENDERED: a source scan proves the fetch line exists and
    proves nothing about whether the header changes); sixteen disarms, every mutation asserted, all red — ⚠️ and
    **four came back GREEN first, each accusing the test**: two properties were held by a second, independent
    guard (every shipped manifest already repeats its own name as its first alias; every surface's es/en word is
    already in the FIXED alias table), one measured a REIMPORT instead of the in-process cache the ⚙ actually
    hits, and one scanned raw source whose own COMMENT contained the words it was looking for (the V2-615 trap).
    The surface case could only be closed with a THIRD language, so the batch ships a generated-bundle test.
  - **NOT done, and named**: the per-widget `whenToUse` routing prose stays Castilian on purpose — it is an
    INTERNAL note the model reads and the prompt says so; and the catalog line still names a widget by its `id`
    rather than its label, which is defensible and would cost the shared per-turn budget (V2-526) to change.

- **A proxy in front of a hardened thing is a SECOND front door (V2-575 P1, 2026-09-14)**: the daemon had five
  guards and no way for a person to obtain it or point it at a folder. The engine now proxies it — a page over
  https cannot call plain http, a direct call needs CORS headers the daemon must never send, and the bearer
  token would have to reach JavaScript — and that proxy is the part worth writing down. It exposes `status`,
  `grant` and `revoke` and **no file route, ever**: proxying `files.read` would hand every page that can reach
  the engine the exact capability `daemon/security/guards.py` refuses, through our own credentials, and a
  ratchet fixes the route set so a future one needs a threat model rather than a test edit. Cross-origin is
  refused here too — without CORS a hostile page cannot READ the answer, but `grant` changes state, so fire and
  forget already puts a folder on somebody's allowlist. The guard reads `Sec-Fetch-Site` first and compares
  `Origin` against the request's OWN `Host`, never a configured hostname, because this engine is reached as
  localhost, as local.zaelar.com and as whatever a cloud account resolves to; the counterweight is in the same
  file, since our own page IS a browser. Three defects fell out of measuring rather than of reading: with no
  `daemon.json` the engine answered `reachable: true` because `/health` needs no token — a green icon over a
  daemon it cannot authenticate to; both CI runners uploaded `zaelar-daemon.pyz`, `manifest.json` and
  `SHA256SUMS` under those names into one flattened release, so one platform silently overwrote the other; and
  the first real Windows runner found `build.py` dying on `UnicodeEncodeError` printing `→` to a cp1252
  console **after every artifact was written** — the build worked, the script died on its own success line.
  The 🖥 icon is the one TopBar control not gated on `cloudProfile`: a cloud account is precisely the case
  where the user's own machine is unreachable, so hiding it hides it from the only people who cannot solve it
  another way — and that screen says outright that connecting a daemon to the cloud agent is still being
  built. Nodes **7.44** (offered and governed) and **7.41** (the cp1252 console). (2026-09-14; V2-575)

- **The errand FINISHES what it agreed — and a verifier reads ONE fact while an objective has several
  (V2-692, 2026-09-14)**: the operator reviewed his own test session and reported it whole — «he pedido que
  se organice una reunión… me ha pedido permiso para hacer el envío. Después el otro ha respondido, pero no
  ha seguido procesando… le he tenido que decir yo, acepta el mensaje. Y aún así no hemos terminado ni
  añadiendo el ítem a la agenda, ni tampoco creando el link de Google Meet.» Read from his own
  observability before touching anything (session `16770007`, flow `T9·08d2`, 209 events): **four defects
  stacked under one sentence, three of them silent by construction.**
  - **`bind()` refuses and NOBODY read the refusal.** A conversation belongs to one errand — right, and two
    objectives answering one person is how they get two different replies to one message. What was wrong is
    what the caller did with it: nothing. Yesterday's errand was still live (it had reached `agreed` and
    could never verify, see below), so it held his Telegram thread with a deadline sixteen hours past, and
    the errand born from his new order got **ZERO conversations** — a row that showed on the board as
    «esperando respuesta», rode the turn's context pack as an open gestión, and could not be woken by
    anything. His contact's reply then woke YESTERDAY's errand, against yesterday's objective. `claim()`
    takes the thread from a live incumbent — his newest word about this person is the current one — and the
    hand-over is TOLD; an errand that cannot take its conversation is closed on the spot rather than left
    to announce, in four hours, that nobody answered.
  - **`party.parse` has always returned an `agreed` block and NOTHING has ever read it.** The errand reached
    «hora acordada» and wrote nothing, anywhere. `errands/book.py` writes the meeting the ENGINE was told
    about, inside the mandate (`schedule` is a separate grant from `message`), and the Meet link Google
    mints as `conferenceData` (V2-685) is appended to the very reply that promises it — booking happens
    BEFORE the send, which is the whole point of the ordering. Meanwhile the worker was driving a browser
    into `accounts.google.com/signin`, twice, in two sessions.
  - **`verify.meeting_exists` filters on a `created` stamp the agenda has NEVER written**, so no errand in
    this house could close by being ACHIEVED — only by running out of time. Its own note records that the
    unit test missed it by writing the field BY HAND. `commit_meeting` stamps it now.
  - **His permission travels with his ORDER**: `send_to` stops being confirm-gated (the worker was gated
    FOUR times on one order and he had to answer «I don't want you to ask» to get his own errand moving);
    `reply` stays gated, because answering something that arrived on its own is nobody's order — his own
    rule, quoted. And `errands.shadow` ships FALSE: it shipped true so autonomy toward real people is not
    handed over on a green suite, and he has now read those rows and asked for the opposite. The bound does
    not move: an errand only ever writes to the ONE conversation it was born in.
  - **A gestión with a third party is HANDED OVER, never sat out.** Measured twice: the worker sent the
    message and then waited inside its own session — 25 `peek` calls, `sleep 150/240/300/420`, a `Monitor`
    loop the permission gate refused — ten minutes of paid session doing nothing, and then the session ended
    and the task ended with it. The durable mechanism existed since V2-683; nobody had told the worker. It
    also settles which door: an errand can only be born from `send_to`, so a follow-up with somebody who had
    already written to us could never become one — **what decides is not whether they wrote first, it is
    whether this message opens something that has to be followed.**
  - **A worker could not READ a widget that grows.** `read agenda` answered with **59 955 bytes**, 55 666 of
    them his whole calendar; the CLI persisted it and the worker was then refused the file twice («31 844
    tokens exceeds maximum allowed 25 000»), reaching 111 282 tokens of context in three minutes. Both
    worker doors hand back the digest the turn prompt has used since V2-576 — 975 bytes for that same
    calendar — plus what is inside and how big, so it can ask a declared action for a slice. Nothing is ever
    truncated: cut JSON reads as complete and is a different shape.
  - ⚠️ **THE BATCH SHIPPED THREE DEFECTS OF ITS OWN AND ITS LIVE RUN CAUGHT EVERY ONE**, all in the same
    family. (d) Lifting V2-683's «never promise a link» prohibition UNCONDITIONALLY, so with his calendar
    unlinked it told a real person «the Google Meet link will be sent with the invitation — it gets added
    automatically»: **a capability stated unconditionally is one the model promises unconditionally**, and
    the gap is paid by a stranger. What it may promise is read from the connector per wake, and fails
    CLOSED. (g) An anti-duplicate guard keyed on the SLOT and blind to the title — his calendar held five
    «Dentista» at 17:00, so it read «already booked», wrote nothing and **reported success**; the row an
    errand owns is the one IT wrote (`done_when.at`), a different slot MOVES the meeting, and an
    appointment that merely shares the hour belongs to somebody else's day. (h) And the verifier then closed
    it as «hecha y verificada» with the link debt outstanding — **closing RELEASES the conversation**, so
    the link could never be delivered.
  - **The class, worth more than the three cases: a verifier reads ONE fact and an objective can have
    SEVERAL**, and the error always falls the same way — it says done, and the operator finds out from the
    other person. Three times in one evening: a stamp nobody wrote, a neighbouring meeting in the same
    window, and a promise still unkept. «Acordar la videollamada Y MANDARLE el enlace» is one errand with
    two halves, and his condition reads literally — «la tarea no termina hasta que no está correctamente
    programada esa reunión» — where *programada* includes what was promised about it.
  - ⭐ **VERIFIED LIVE**: one order → worker → `send_to` with an objective → errand born and bound, **zero
    confirmations**; the engine RESTARTED mid-gestión and the errand came back exactly where it was; his
    reply at 20:27:03 woke it **eleven seconds later** and it decided, answered and booked on its own; and a
    second round moved the meeting from 16:00 to 17:00 instead of duplicating it. **NOT completed, and the
    reason is not code**: the Meet link needs the OAuth consent, a click in HIS browser on HIS account that
    the popup only survives inside — so the debt is recorded and the beat pays it the moment the link
    exists. The same click blocks deleting 23 test appointments: 22 live in his real Google Calendar with
    their own `googleId`, so a local-only delete would return on the next sync.
  - Nodes **3.47** (33 cases) and **3.48** (8). Twenty-eight disarms, every mutation asserted. Three came
    back green: two were harness artifacts (a `"confirm": true` inserted at the head of a JSON object is
    overridden by the real key later in it) and one accused the TEST — that property is held by the AGENDA's
    own `_is_same_meeting` (V2-208), not by this code, and the case now says so instead of taking credit.

- **A COMPOUND close does not swallow the rest of the sentence (V2-688, 2026-09-14)**: «close all, open
  agenda, connect to my google calendar» cleared the canvas and did nothing else — his question was the one
  anybody would ask, «why is this order not followed?». Read from his own observability before touching
  anything (flow `T10·c053`), and the WHOLE event chain of that turn is four lines: `✋ interrupción dura
  atendida · widget close · ⛔ vetaría close-drag · flow end`. **No tool, no model call, no reply.** Two
  thirds of one sentence discarded in silence — and the canvas DID clear, which looks enough like obedience
  to hide the two orders thrown away with it.
  - **The mechanism was right and the outcome wrong.** `attention.hard_interrupt()` exists because a close
    order once fell OUTSIDE the excerpt of a 14 000-char turn and simply never happened (T136); its
    guarantee — executed deterministically, before any model, always — is worth keeping and is not weakened
    here. What nobody had examined is the **`return` after it**: it treats «close» as the whole of what the
    operator said, which is true of «cierra todo» and false of every compound order. **Speech is full of
    compound orders** — that is how a person clears a desk before starting something.
  - **The close keeps its guarantee and the rest of the sentence keeps its turn.** ⚠️ The closing clause is
    **REMOVED** from what the model reads, not left in: handed «close all» against an already-empty canvas a
    model re-emits it (the context-bleed shape V2-635 catalogued across four classes), and that second close
    would land on whatever the very same sentence had just asked to open — turning one silent failure into
    an intermittent one, which is worse. `close_all_remainder()` is conservative by construction: courtesy
    («cierra todo, por favor»), timing («ya», «ahora mismo») and a single bare word all come back empty, and
    the caller then behaves exactly as before. **The comma is the only difference between its splitter and
    the one `_closes_the_whole_canvas` uses**, which stays comma-blind on purpose so an enumeration of
    things to close («cierra el vídeo, la música y todo lo demás») keeps reading as ONE closing clause.
  - The architecture ratchet went red (`nucleo.py` 3054 > 3043) and was paid by **EXTRACTING**, never by
    raising the ceiling: the whole hard-interrupt decision — worker vs music vs canvas, and whether closing
    was the entire request — moved to `nucleo/flash/hard_turn.py`, and nucleo.py ends at **3014**, below
    where the batch started. Wiring guards anchor on the module that OWNS the block (V2-555). Also dropped a
    dead re-export (`_action_is_negated`) that nothing in the repo reads and that had the ruff F401 gate red
    on that file before this batch.
  - **Deliberately NOT mirrored into the probe channel, and a test says so**: the probe never had this
    defect — it calls the model with the full text and only LABELS the action afterwards — so there is
    nothing to mirror, and stripping text before its model call would be a change with no defect behind it.
    V2-252's rule is that a behaviour fixed in one channel is fixed in both; **the channel that always
    worked is not the one to change**. Node **3.46** (20 cases); seven disarms, every mutation asserted, all
    red. ⚠️ **NOT verified live by voice** — the engine restarted onto it (`3.26+61100472`), but only the
    operator saying the sentence proves the whole path.

- **Both doors ask Google for the SAME return address (V2-687, 2026-09-14)**: the operator's FIRST real
  Google connect, and it died at the last step — «Access blocked: This app's request is invalid ·
  **Error 400: redirect_uri_mismatch**». Everything on this side was correct AND consistent, which is what
  made it hard to see: the client resolved (`source() == "shipped"`, project `studied-reason-508412-f7`,
  web client) with **no per-connector override set**, and the pending OAuth record proves the exact string
  we sent — `http://127.0.0.1:43917/api/calendar/callback`, verbatim what the engine printed and what he
  was told to register. Two further measurements framed it: the error is `redirect_uri_mismatch` and NOT
  `invalid_client`, so the client id was accepted; and the console's exported JSON carries **no
  `redirect_uris` key at all**, which a web client omits only when it has none registered.
  - **The defect is that TWO doors open this same consent and derived the address DIFFERENTLY.** ⚙ →
    Conectores → Calendario (`/api/calendar/connect`) reads the REQUEST headers — V2-603's fix, because a
    hardcoded loopback only works for a self-host opened on that machine — while the agenda card's own
    button went through `gcal.ui_action` → `service.connect_url(provider, tier)` with **no origin**, so it
    always fell back to the loopback default. Which URI Google had to match depended on which button he
    pressed, and this engine serves TWO origins (`127.0.0.1:43917` and `local.zaelar.com:44317`, the two
    listeners of the same app). **Registering the five the engine printed left the other five failing**,
    with an error that names neither door.
  - ⚠️ **The class is worth more than the case.** V2-603's origin fix was copied into this connector «from
    day one instead of being paid twice» — its own docstring says so — and it was copied into ONE of its
    two callers. **A fix that lives in a CALLER has to be re-applied by every caller that arrives later**,
    which is exactly V2-626's «a rule every caller has to remember is not a rule», one connector over.
  - Fixed by making the card send `location.origin` in the connect payload (absent — a voice-driven
    connect, a worker — it falls back to the loopback, the only honest answer when nobody is looking at a
    page), and by adding **`app.uris_to_register()`**, which is what the operator PASTES: every callback ×
    every origin this engine answers on, ports read from the same env names `server/__main__.py` honours.
    `redirect_uris(origin)` stays what the FLOW uses. **A list printed for one origin is right half the
    time**, and that is what made this read as «I did exactly what it said and it still failed». The
    README and the module docstring now name the error that actually happens and the right console box
    (*URI de redirección autorizados*, **not** *Orígenes autorizados de JavaScript*).
  - An origin in a payload is not a credential (V2-520) and cannot leak a code: Google only ever redirects
    to a URI the client has REGISTERED — the control this entire batch tripped over — and a malformed one
    falls back instead of travelling. Node **4.168**; five disarms, every mutation asserted, all red.
  - ⚠️ **The retry failed too, and agreeing was never going to be enough (V2-687b, same afternoon).** The
    engine probed Google's OWN authorize endpoint for every URI on the list — building the same URL the flow
    builds, following none of it, consenting nothing — and all five answered `redirect_uri_mismatch` while
    echoing the exact string we sent. So the client had **no redirect URI registered at all**, and **three
    defects were stacked under one error message** with only the first found. **(2) The list asked him to
    register five URIs Google will not accept.** `local.zaelar.com` is a DOMAIN — OURS, shipped as a DNS
    alias of 127.0.0.1 so a local engine can be opened over TLS — and Google exempts only the LOOPBACK
    address from domain ownership, so **no self-hoster can ever register it**. The remedy V2-687 reached for
    — print TEN instead of five — therefore made half the list unregistrable, which is worse than the defect
    it replaced. `app.normalize_origin()` collapses this engine's two local listeners onto loopback: same
    process, same token store, and a callback page that reads nothing from the origin's session, so which of
    the two Google returns to changes nothing the operator can observe. A genuinely remote origin is not one
    of `served_origins()` and passes through untouched, so V2-603 stays true and the list is five again.
    **(3) `CALLBACK_PATHS` named `/api/files/callback`, which this engine has NEVER served** — Drive answers
    on `/api/cloudfiles/callback`, and `/api/files/*` belongs to `memory_routes`, which `server/__init__.py`
    says in as many words. A wrong address on a list of five reads, to whoever pasted it, as «I did exactly
    what it said». The test derives the truth from the MOUNTED routers instead of trusting the tuple, which
    is the only one of the three a test could have caught the day it was written — and it declares the gap
    it exposes: **`/api/email/callback` has no router at all** (`server/email_api.py`, named by
    `connectors/email/oauth.py:7`, does not exist), so Gmail's OAuth door is dead and now says so.
  - **`app.check_registered()` — ask Google instead of guessing.** Registering a redirect URI is the one
    step of this setup that happens in somebody ELSE's console, and until today the only way to find out
    whether it had worked was to run a whole consent flow and read `Error 400` at the end of it. It answers
    **None, never False, when it cannot tell** — an offline machine must not be told its setup is broken,
    because «could not tell» and «not registered» send the operator to two different places. ⚠️ The general
    lesson, and the one worth more than this connector: **a list of addresses to register is only worth what
    it is DERIVED from** — hand-typed, it drifts from the routes in silence, and the drift only ever
    surfaces in the operator's browser, as HIS failure. Seven more disarms, every mutation asserted, all red.

- **The LAST METRE of a connector: the agenda owns its own, and a voice order ends in front of the BUTTON
  (V2-686, 2026-09-14)**: the operator tried to connect Google Calendar by voice, twice, minutes after
  V2-685 shipped the client, and lost both times — «he intentado conectar la agenda con Google Calendar
  pero el sistema no me ha entendido… necesito hacer ese test manual porque la conexión la tengo que hacer
  yo desde el browser con mi cuenta de Google». Read from his own observability before touching anything
  (session `a9fcd650`, engine `3.26+860dd7fb`):
  - **`T12·9e60` «open the google connector» → the model opened MESSAGING** and answered «the Google
    connector is right there with the login steps». It did not hallucinate: `widgets_n_selected: 15` of 15,
    so the whole catalog was in the prompt and selection filtered nothing — what decided it was that the
    only purpose line mentioning connecting was messaging's («…o conectar un canal», plus `gmail`,
    `conectar email` in its keywords), while the agenda's said nothing about connecting, nothing about
    Google and nothing about a calendar. **A connector adds ACTIONS and almost never the WORDS that lead to
    them**, and the routing line is the half nobody updates. Fixed by naming the service, the linking verb
    and **the frontier** («es la agenda, no mensajería») in `whenToUse` — 283 of the 300-char budget,
    asserted against `brief._purpose`, because what the cap trims is the END, which is exactly where the
    frontier clause lives (trap T4) — plus 21 keywords and 5 aliases **in both languages**: both lost turns
    were in ENGLISH against a widget whose vocabulary was Castilian except for «schedule» and «my day».
  - **`T14·76b6`, naming the widget, DID reach it — and nothing happened.** `widget_data agenda:connect`
    was allowed, executed, and returned a perfectly good consent URL; the screen did not move and the mouth
    said nothing (`completion_chars: 0`). The connector was never broken. **Two links cut the last metre,
    and neither is a bug that shows up in a log**: `widget_data_turn.py` keeps `{widget, act}` from a
    successful data-op and **throws the result away**, so no `url`/`hint` in a return value can ever reach
    the model; and even if it did, **the voice cannot finish an OAuth consent** — the popup only survives
    inside the click that opened it, which `widget.js` already documents and the calendar connector already paid for.
  - **So the voice does the half it CAN: it puts the button in front of him.** `gcal.push_connect_screen`
    leaves the card ON its connect step, published through `view_data` with the same token shape as the
    pushed view — a COUNTER (asking twice lands twice; a flag would stay true and move nothing) and an `at`
    that EXPIRES at 180 s (or tomorrow's first repaint ambushes him with a setup screen over the agenda he
    was reading). **The push happens BEFORE the connector is consulted**: if it depended on the URL coming
    out well, the case that needs a screen most — no OAuth app registered — would be the one without one.
    And the sentence is declared in the action's `desc`, which DOES travel in the prompt: call it, tell him
    to press «Conectar Google Calendar», never dictate the URL.
  - **The alta was not closed, and closing it found three live drifts**, each of which failed silently:
    `connectors/catalog/youtube.json` was still `planned` — parked in V2-603 F2 for ONE written reason, «no
    Google OAuth client», which V2-685 removed two days earlier — so the chat wall was offering him a **«Lo
    quiero»** button for a connector he already had (`oauth.authorize_url('youtube')` returns a valid URL);
    `google-calendar.json` declared id `google-calendar` while its live row is `google`, so
    `catalog.search()` could never rank his own calendar as connected; and `ChatWall.js`'s
    `CONN_FAMILY_ORDER` was missing `video` and `agenda`, live families since the YouTube account connector and the
    calendar one, so both rendered below Infraestructura in the «a family nobody expects» bucket. **If a manifest parks something
    behind a CONDITION, the condition goes in its notes and lifting it is the last step of whatever
    satisfies it.**
  - **The workflow now carries what this proved was missing**: six more wiring points (§4 is 14 now), the
    ROUTING half in §5, **§7-bis the LAST METRE** and **§7-ter declararlo HECHO**, four new traps — plus the
    two docs that did not exist: the connector **LIST**
    (`.meshkore/docs/modules/zaelar-connectors-inventory.md`, the operator's «añádelo a la carpeta MeshKore,
    a la lista de conectores») and the Google connector's module doc, which §8.1 required and V2-685 never
    wrote. Node **5.7** (+1 file) is the ratchet behind it: no live connector may sit on the wishlist, a
    `built` manifest with no live row must say why in writing, every live family has a name in BOTH bundles,
    a place in the chat wall's order and a section in the ⚙ panel, and no two rows share an id.
  - ⭐ **VERIFIED LIVE on his engine, and driving it found TWO MORE causes that no reading would have.**
    With the routing fixed, «conecta mi google calendar» and «connect my google calendar» reach
    `agenda:connect` (5 of 6 samples; the baseline reached it 0 times), and the action drives the real card:
    `POST /widgets/agenda/action` returns a consent URL **and** the live card comes back carrying
    `connect: {n: 1, …}`, which is the push. But the bare «open the google connector» kept opening
    Messaging, and the prompt said why: **`connectors/messaging/brief.py` claimed EVERY connection
    ceremony in the product** — «si quiere conectar/ver UNA APP, emite `[[show:mensajeria]]` … Guíale tú
    también de palabra ('te abro Mensajería, ahí tienes los pasos')», with the reply pre-written, which is
    almost verbatim what the model said. True when messaging was the only connector with a wizard; a defect
    once the engine grew five more and nobody narrowed the sentence. **A brief may claim its OWN family and
    no more.** And `connectors/google/brain.py` — mine, one day old — told the model it could offer to
    connect Google and never said THROUGH WHICH DOOR, so it picked the only widget whose text mentions
    connecting anything: the mechanism is a table now (`_DOORS`), and the offer SHRINKS as each door opens.
    ⚠️ **That same sentence was also wrong on its own terms**: «una sola vez sirve para Gmail, Calendar,
    Meet, Drive, Fotos y YouTube» is true of the CLIENT and false of the CONSENT — each connector runs its
    own flow, with its own scopes and its own token store, so linking the calendar grants nothing to Gmail,
    and a model that had just connected one door would have reported the other five as connected.
  - ⚠️ **And a lesson about HOW this was measured**: two rounds of prompt wording were added on the strength
    of ONE probe sample each, and both made it worse (`show_widget` with no action, then three turns calling
    nothing at all) before a third round showed the first «regression» had been a single unlucky draw on an
    UNCHANGED file. Reverted to the wording that measured best and sampled each phrase three times.
    **Tuning a prompt by single samples is not measurement**, and it was being done on the operator's live
    engine. Left as it is and reported: the bare «the google connector» still resolves to Gmail — defensible
    (Gmail IS a Google connector) and deliberately not forced, because forcing it breaks «conecta mi gmail».
  - Node **4.167**; fifteen disarms, every mutation asserted, all red — ⚠️ one came back GREEN and was a
    real gap: **nothing measured the scope of the messaging brief**, the very sentence that caused T12. ⚠️ **Two were harness artifacts** — a
    `-k "a or b"` split on whitespace produced «no tests ran», which exits non-zero and reads as red (the
    zsh trap, paid again) — and ⚠️ **one came back GREEN and accused the TEST**: the first two routing cases
    asserted `selection.candidates`' ranking, and with fifteen widgets **everything** is a candidate, so
    they measured nothing; rewritten against the artifact that actually failed, the row
    `brief.for_prompt` puts in the turn prompt. **Not fixed here and named**: the turn report still discards
    a successful data-op's result — making it reach the model is a change on the shared voice path and
    deserves its own batch.

- **ONE Google account, six doors — and Meet is an ARGUMENT, not a tool (V2-685, 2026-09-13)**: the
  operator, handing over the OAuth client he had just registered — «we need to create the google connector…
  we will use it for gmail. **change current to standardize**. use it for calendar and meet and for now i
  guess we do not have more widgets were applicable», then «add features to the system so brain workers etc,
  flashbrain, all can use it when need it». **MEASURED before writing a line**: six near-identical OAuth
  modules (1 325 lines), **five of them fronting Google**, each asking for the SAME client under a different
  name — `EMAIL_GMAIL_*`, `CALENDAR_GOOGLE_*`, `VIDEO_YOUTUBE_*`, `PHOTOS_GOOGLE_PHOTOS_*`, `FILES_GDRIVE_*`.
  He answers one and the other four stay dormant in silence. `builtin_client_id` had been declared and EMPTY
  since V2-603 and copied verbatim into the calendar connector the day it was built, both saying «EMPTY until Zaelar registers its own Google OAuth
  client». He registered it on 2026-09-12.
  - **`connectors/google/` holds the answer once, and is a LEAF**: nothing there imports another connector,
    because everything else imports it. `app.py` resolves the client — the operator's own (`GOOGLE_CLIENT_ID`)
    first, then the `client_secret_*.json` the console hands you, read **verbatim** out of
    `.meshkore/credentials/` so nothing is retyped into a source file and no second copy can drift; cached on
    (path, mtime), so a file dropped in while the engine runs is seen without a restart, and a value frozen at
    import would have left him restarting to be believed. It reports WHERE the client came from, never what it
    is. **Each connector's own name still wins**, which is what keeps the fair-code self-host story honest and
    what makes the change safe: Outlook, which authenticates against Microsoft, gets nothing — handing it a
    Google client would turn a dormant connector into a broken one, and that counterweight is the test that
    matters most here.
  - **`services.py` deliberately does NOT own the scopes of a connector that has its own registry.** Each
    already declares them next to the client that requests them, this package sits BELOW those connectors and
    cannot import them to check, and two copies of a scope list drift. It fills in `scopes` only for a service
    with no connector at all — which today means exactly one.
  - **Meet is that one, and it asks for NOTHING extra**: a Meet link is `conferenceData` on a calendar event,
    minted by the calendar scope the connector already holds. There IS a standalone Meet REST API behind
    `.../auth/meetings.space.created` and it is **named in `FUTURE_SCOPES` and not requested** — an unused
    sensitive scope buys nothing today and costs a harder Google verification for every user of the app.
    ⚠️ **`conferenceDataVersion=1` is the half that fails silently**: without that query parameter Google
    returns 200, creates the event, and DROPS the conference — no error, no link, and an agent that has just
    told the operator it made them a meeting room.
  - **The capability is an ARGUMENT of the tool the model already has**, and `brain.py` says so out loud. Meet
    is a verb this engine has never had, so a model asked for one has no prior behaviour to fall back on
    except inventing a `create_meet` tool or promising a link before Google minted it. Naming the capability
    alone is what makes a model improvise a verb — so the line names `meet: true` and states that no separate
    tool exists. Third payment of V2-603's receipt («four claims, zero connections»). **Workers needed no
    exception**: they reach it through `act widget_data`, already allowed and gated on the widget's own
    manifest, so `_PRESTABLE_TOOLS` — whose comment says it «grows only with an explicit designation, never by
    accident» — was left untouched.
  - ⚠️ **Three ratchets went red and two were paid by EXTRACTING**: `prompt.py` (846 > 834, 30 lazy imports >
    29) → `flash/connector_briefs.py`, ending at **789 and 26**, lower than before the batch started; the
    Google wiring guard re-anchored on the module that OWNS the block, per V2-555. The third was **not paid**:
    `widgets/agenda/data.py` sits EXACTLY on the 900-line newborn ceiling while another session edits it, so
    its one-line delegation (`gcal.apply_meet(meeting, payload)`) is deliberately left out — extracting from
    somebody else's in-flight file is worse than leaving one line, and a ratchet is never paid by a smaller
    diff. Its test is skipped and says exactly that.
  - ⚠️ **Eight tests in three other files went red, and all eight were MINE**: video, calendar and agenda each
    assumed no Google client could exist — video's `sandbox` fixture said so in its own docstring and simply
    had a third source it did not know about. **Pinned, never relaxed** (V2-606's lesson: a test that measures
    the machine it runs on), each with its counterweight asserting the new reality — including a FOURTH
    connector state the agenda had no sentence for: an app registered and awaiting consent is not «you have
    not linked it». And one test DOUBLE had a narrower signature than the real client (`post` with no
    `params`), so the new query parameter raised a TypeError that `insert_event`'s own except swallowed into
    `{"ok": False}`.
  - ⚠️ **The number collided.** This batch took V2-684 and the concurrent session already owned it; renumbered
    at closure, and the blind rename then clobbered **four foreign citations** in `tests/run_testmap.py`,
    restored by hand. Create the initiative file when the number is TAKEN.
  - Node **5.25** (27 cases, ten disarms, every mutation asserted, all red — one came back GREEN and accused
    the TEST: the case started from the already-trimmed state, so removing the guard popped a key that was not
    there). **NOT verified live, and it cannot be yet**: it is a **web** client, so Google refuses a redirect
    URI it has never seen — with `invalid_client`, at the END of a flow that looks healthy all the way up —
    and the five the engine serves (`app.redirect_uris()`) are not registered in the console. Nothing connects
    until the operator pastes them. **NOT committed**: `connectors/registry.py`, `connectors/calendar/`,
    `widgets/agenda/` and their tests all carry another session's uncommitted work, and a pathspec limits
    files, never hunks.

- **The test system learns the ERRAND, and a language leak becomes a failure (V2-684, 2026-09-13)**: the
  operator, handing over a second Telegram account of his own (`@cryptonite_fund`) to answer from — «así
  lo podrás probar contra una cuenta real» — and merging two testing plans into one batch, errand first.
  They ARE one plan: the errand's party turn is a language surface (`party.build_system` answers in the
  PARTY's language, not the operator's), which is the one case neither plan covered.
  - **The ARC, and why the pieces were not enough.** V2-683's 105 cases each move one piece with the
    neighbours stubbed; all of the errand's interesting behaviour is multi-turn, and the multi-turn shape
    had never run once. `tests/agent_headless/harness/errand_world.py` is ONE double, at the TRANSPORT —
    it hears `msg.send`, decides whether the message really went out, echoes the conversation it created,
    and can make the other person answer — with a clock the arc controls, so ten hours cost no seconds.
    Everything above it is product: the widget's `send_to`, the owner's flush WITH its secret scan, the
    watcher's three signals, the ledger, the wake, the parse, the verifier and the expiry sweep. Node
    **3.43** (19 cases): agreement closing against the AGENDA and not against the model, the answer ten
    hours later, «quiero hablar con Ricart» (blocks AND then stays quiet — the second half is the
    assertion), nobody answering, two exchanges as ONE conversation, a send that failed, a meeting he
    already had. Plus the half he said matters most, «sin necesidad de que lo tengamos que programar»: the
    same arc with NO playbook, with reunión→cena, and with `config/playbooks.json` beating genesis — with
    a ratchet that no playbook may name a person, a company or a site, which is what keeps a briefing from
    quietly becoming a script.
  - ⚠️ **The arc found a real defect: an ARMED errand would have answered NOBODY.** `wake._send` queues
    the composed reply in `pending_send`, and the only flush lived inside `_Owner.handle` — with no
    operator action on the messaging widget, nothing ever drained it. Invisible because the feature ships
    in SHADOW (nothing to flush) and because every unit test stopped at «it was queued». The owner's own
    beat drains it now; the flush stays where it is, because that is the one door where `memory/secrets.py`
    reads a text written by a MODEL for somebody outside.
  - **The shadow gate is a number now** (node **3.44**, read-only): every decision the errand logged, per
    errand, with what it WOULD have said — and the one question answerable mechanically, «how many would
    have written to a conversation that is not this errand's own». Zero is the gate. A log with no
    decisions says so instead of printing a reassuring zero over nothing. And node **3.45** is the only
    test in the house that writes to a PERSON: it arms the engine out of shadow for the length of the run
    and restores it in a `finally`, **refuses to start while any other errand is open** (the flag is
    global), and waits — saying what it is waiting for — through as many replies as the conversation takes.
  - **A language leak is a failure of the test that caused it.** `tests/lang.speaking(code)` does the
    THREE things a language change is (env + `actionmap.invalidate()` + `detect._should_cache`); five
    files each did a subset by hand and only one invalidated the pack, so a test that switched language
    read the previous language's table and passed describing the wrong one. The root conftest now fails
    whoever leaves `ZAELAR_LANGUAGE` changed — documented in prose since 2026-08-20 and never made red —
    and found two real leaks the day it was installed: one file POPPED the variable in its teardown
    (leaving every later test with no language at all) and two cases call `settings.update
    ({"stt_language": "de"})`, which writes the process env by design. Node **8.9**.
  - **The segmenter corpus stops mixing languages.** It was red at 54 % against a 70 % floor and all ten
    escaped fragments were English, while the segmenter has no branch for another language — so one
    blended number was pressing to LOWER the Castilian bar to accommodate English. Two buckets, two
    floors, a bucket too small to mean anything reported instead of asserted. ⚠️ Measured: the registry
    holds ZERO Castilian fragments today (the sessions rotated), so that side SKIPS rather than passing,
    and the test says which. ⚠️ Also measured, and the plan had it wrong: a session does NOT record its
    language — one event in 12 127 carries the field — so the label is lexical and says it is test-side.
  - Seven disarms, every mutation asserted, all red; two came back GREEN first and each accused the test
    (the failed-send guard is not what stops a birth — no echo is; and the flush's WIRING was measured by
    nobody, since the arcs drive it through the harness). `memory.errands_store` is blessed in the memory
    contract: the boundary test and the architecture ratchet pointed opposite ways in V2-683 and the
    extraction won — the blessing records that instead of leaving a red test with no written reason.
  - ⭐ **VERIFIED LIVE, and the live run found SIX more defects, none of them visible from the suite.**
    The operator answered from `@cryptonite_fund` and at 23:13:29 the errand answered him BY ITSELF —
    «Perfecto, mañana por la mañana. ¿Te viene bien a las 10:00?» — the first sentence this system has ever
    said to a person with nobody dictating it. What it cost, in the order it was found: (1) an errand
    CLOSED ITSELF in the same second over his real «Cinema with Mary», because `verify.meeting_exists`
    filtered on a `created` field the agenda never writes — **the earlier tests passed because they wrote
    that field BY HAND**; (2) an answer arriving with the ⏻ off was LOST rather than postponed, because
    `_fire_wakes` POPPED the wake six lines before `wake()` refused with «parado»; (3) the errand tests read
    his REAL `config/playbooks.json`, which the live node writes `shadow: false` into, so the shadow arcs
    ARMED themselves; (4) **an answer that arrived before a RESTART was lost for ever** — three messages
    landed at 22:28, the engine came back at 22:33, and the errand sat in `contacting` with `last_inbound`
    empty, because `_pending_wakes` is memory, the bus subscription is memory, and nothing ever asked the
    thread store what it was ALREADY HOLDING (`watch._reconcile` now compares each live errand against its
    own conversation: the bus becomes the FAST path instead of the only path, which also covers a ⏻ off for
    longer than one process and any dropped event); (5) **the model said NOTHING and the conversation
    died** — the party turn asked `deepseek-v4-pro`, a REASONER, for 700 tokens and got `reasoning_tokens:
    700` of 700, `finish_reason: length`, `content: ''`, which `wake()` filed as «ilegible» and answered
    with silence toward somebody who was waiting (the V2-658 class one layer over: `no_thinking`, a wider
    budget, ONE bounded retry — and the operator is told, because a turn that could not answer is
    indistinguishable from a gestión still in flight); (6) the dossier announced his OCCUPIED hours under
    the label «HUECOS LIBRES», so the next thing it would have done is offer «Cinema with Mary»'s slot to a
    stranger — **a label that contradicts its own value is worse than no line at all** — and the person was
    called «telegram», because the contact is filed by the handle he dictated while the conversation is
    keyed by the platform's numeric id.
  - ⚠️ **And the first real errand turned four UNRELATED tests red on a clean tree**:
    `context_packs.active_ids()` answered `['errands']` — his own gestión, in his own ledger — so the
    PHRASEBOOK cases failed, because the phrasebook correctly stands aside while a phase is guiding.
    Nothing was broken; the suite had started depending on whether he happened to have an errand open. The
    cause is this invariant's last unreached store, **`zaelar.db`** (the memory, the durable event log and
    the errand ledger), and the gap was already written down in `tests/browser/unit/agenda/conftest.py` —
    «nothing in the test conftests overrides `ZAELAR_DB`» — which is the same shape V2-673 paid for
    `config/v2.json`. The database moves for the whole session in the ROOT `conftest.py` now, beside the
    three that already do, with its row in `test_suite_isolation`; a runner pointing at its own corpus is
    honoured, because that is a test choosing its state. **NOT built**: the journey case and the language
    axis proper (T-B…T-G), named in the initiative. **Still not verified live**: the full CLOSE of an
    errand against a real agreement — the party turn holds no tools, so nothing turns «agreed» into an
    agenda row yet (V2-683 row 6, blocked on `connectors/calendar/`).

- **An errand with a THIRD PARTY outlives the turn — and it ships in SHADOW (V2-683, 2026-09-13)**: the
  operator's errand — «contacta con Iván Musikin y mantén una conversación con él para organizar una
  reunión esta tarde… y cuando él conteste, ahora o dentro de diez horas, sigue esa conversación» — plus
  the architectural half that outlives it: «que el sistema pueda soportar workflows de este tipo o de
  cualquier otra índole SIN necesidad de que lo tengamos que programar». **Measured before building
  anything: four kinds of «ongoing» existed and not one could hold it** — the TURN (seconds), the WORKER
  SESSION (`workers/session.py`: minutes, RAM, buried by `rehydrate.py` past `STALE_S`), the CRON (a prompt
  at a time, no state) and the HARNESS GOAL (`harness.py`: TTL 300 s, cap 8, RAM, verifies only whether a
  widget is empty). And three capabilities were missing outright: a contact had **no channels** (phone and
  email, no Telegram handle, no preferred one), **every outbound path required a conversation that already
  existed** (`_resolve_target` → `pending_reply` → each connector's drain), and nothing linked an inbound
  message to an errand WE started. So the work is a missing NOUN plus its resources, and deliberately NOT a
  workflow engine: no steps, no branches, no retries — that is the script the brain-worker doctrine
  forbids, and it is what would make «reservar una mesa» need a second engine next month.
  - **`nucleo/errands/` is a ROW, not a process**: it survives a restart because that is what a row does,
    and it is woken by the world instead of sitting in memory waiting. It is born from HIS OWN YES —
    `mensajeria.send_to` is confirm-gated and its question IS the mandate («Voy a escribir a Iván Musikin
    por Telegram: "…". Es para organizar una reunión esta tarde: si contesta, sigo yo la conversación por
    ahí y te aviso») — and, his own rule, **it closes itself**: the objective verifies, the deadline passes
    («en las próximas cuatro horas» is a GRAMMAR; a vague «esta tarde» falls back to a DECLARED default
    rather than a guessed date, the call `scheduler.parse_when` already makes), or he says so. A closed
    errand RELEASES its conversations, and `errand_threads`' primary key `(platform, chat_id)` makes «one
    errand per conversation» structural rather than remembered.
  - **The party turn holds NO TOOLS.** A stranger's words reach a model — that is what following a
    conversation means — and the model returns ONE JSON object the ENGINE executes. There is nothing for an
    injected instruction to call, structurally rather than by prompt wording. The profile is `cluster.py`'s
    UNTRUSTED one (V2-069) with exactly two differences, both written down: identity is disclosed BY MANDATE
    and only that much (the assistant's name, the operator's first name, that it writes on his behalf —
    that IS the errand), and the language follows the PARTY. `compose_state` is never read. The reply can
    only reach the conversation the errand already owns, held by two independent guards (a whitelist on the
    parse, and a send BUILT from the binding).
  - **SHADOW is what ships** (`errands.shadow`, genesis, default true): it decides and LOGS what it would
    say, and sends nothing. Autonomy that writes to real people in his name is handed over after he has read
    a few of those rows, not on the strength of a green suite. Fails closed, as do ⏻ (postponed, never lost)
    and an unreadable answer (half an action out of unparseable prose is worse than none: it reaches a
    person). Outbound text passes `memory/secrets.py` at the owner's flush and FAILS CLOSED — unlike a reply
    he dictated, this text was written by a model for a third party.
  - **Playbooks are DATA and a briefing** (`genesis.json`, overridable in `config/playbooks.json` — his
    «otro usuario podría querer Zoom», one file away): what «done» means, what must be known first, how the
    thing is done well, what ends it. Three properties keep it a shortcut and not a fence, each a test: an
    errand with NO playbook still runs, the operator's file wins, and nothing in it names a person, a company
    or a site — swap reunión→cena→taller and it stands.
  - **It closes on the product's own truth**: `verify.py` asks the agenda, ignores a meeting he ALREADY had
    (or last week's dentist closes today's errand), and answers None when it cannot read — which closes
    nothing, because a wrong «ya está» is the exact lie the V2-660 harness was built against.
  - ⚠️ **The ratchet caught a DESIGN mistake, not just a size**: the errand rows were being merged inside
    `dispatch.active_sessions()`, which feeds the stall detector, the susurro's dedup and the worker ledger
    — all three reasoning about a PROCESS, to which «waiting three hours for somebody to answer» reads as a
    stuck worker. Moved to the `/api/tasks` route (the operator's board); the brain has its own seam, the
    context pack. `dispatch.py` ended UNCHANGED and `memory/api.py` too (the facade went to
    `memory/errands_store.py`), both paid by extraction and never by a higher ceiling.
  - ⚠️ **Twenty green disarms across the batch, and they split three ways**: a guard that guarded NOTHING
    (deleted, V2-655's rule), tests that measured with values where the mutation changed nothing (a window
    equal to the default, a ceiling the grammar rejected, a numeric id where the point was a non-numeric
    one), and — three times — a property genuinely held by TWO independent guards, re-anchored on the
    load-bearing one, with the one that cannot be disarmed alone SAYING SO in the test instead of pretending.
    Sixty-three disarms in total, every mutation asserted, all red.
  - Nodes **4.96**, **4.166**, **5.24**, **3.41** and **3.42** (105 cases). ⚠️ **NOT verified live**: no
    real message has been sent by this path and no real person has answered one — which is what shadow mode
    is for. **NOT built**: the Meet link (`conferenceData.createRequest`, one small gap) waits on
    `connectors/calendar/` being committed by the session that owns it; and the messaging widget's prompt
    debt (a legacy 2 090-char `[[msg.*]]` protocol duplicating its 26 declared actions, and no
    `prompt_digest`) is named in the initiative and deliberately left alone: retiring the protocol and
    adding the digest are two halves of ONE swap on a live path, and that deserves its own batch.

- **A SET PHRASE is answered from a table, in any language — the phrasebook (V2-674, 2026-09-11)**: the
  operator, after starting a session in ENGLISH to check the product is language agnostic — «le digo hola y
  me dice un segundo o check-in, o sea, ¿qué vas a chequear si te acabo de decir hola?… ya lo pedí, una serie
  de frases hechas que estuvieran ya preseteadas en el idioma, en una hash table de saludos». **MEASURED in
  that session's own observability (sid fdd096a3 / daa7a385) before writing a line**: «Hello and good
  morning. How are you?» cost a **3 440 ms** model call covered by «Let me explain…»; «You were saying?» got
  «One sec, checking…» and then an **INVENTED errand** («there's a WhatsApp message from Jo that came in as
  an image»), assembled out of a memory pill; «Hey, mate. You there?» got «Let me check that for you…». None
  of the three is a request. **The mechanism already existed for a narrower case**: `presence.py` answers
  «¿sigues ahí?» from a pool, with no model and no tool. This is the same idea widened to the phrases that
  open, close and cushion a conversation — greeting, «¿qué tal?», «gracias», «adiós» — and one more that only
  exists as a pair («bien» means «I'm fine» ONLY when our own previous reply handed the question back;
  otherwise it is the answer to something WE asked, which is V2-665's defect with the roles reversed).
  **It is DATA and not a regex, and that is the whole reason it earns the words «language agnostic»**:
  `presence.py`'s regex is Spanish + English and structurally cannot grow to forty languages, so cues and
  replies hang off `LangSpec.smalltalk` (es/en, verified native) and `i18n/init/smalltalk.py` GENERATES a pack
  for any other language at onboarding, beside the alias pack that has been doing exactly this since V2-101.
  A language with neither answers `{}` — the lane declines and the model answers, as before. **Matching is
  deliberately strict**: the whole utterance must decompose into cues, generic forms of address and the
  language's own coordinating words («hello AND good morning» is two phrases with no punctuation between
  them, which is how he actually said it), and ONE unknown word hands the turn back untouched. The asymmetry
  is the point — answering «hola» with a model costs three seconds, and answering a real request with «¡Hola!
  Dime.» is a broken product — so the refusing cases carry most of the test weight. Replies come from a pool
  avoiding the last one used, per his «una especie de diálogo heurístico, un poco random»; and the
  `bounces`/`after_bounce` flags are OURS and never the translator's, because they encode a rule about the
  CONVERSATION and a pack that could set them would quietly change how the lane behaves. Two smaller findings
  from the same three sentences shipped with it: the presence knock now strips generic forms of address
  **wherever they appear** (the only word standing between «Hey, mate. You there?» and the lane that answers
  it was «mate»), and «you were saying» joins the social filler class so a question about the conversation
  stops arming a cover that promises to go and look at something. Node **3.37**; ten disarms, mutations
  asserted, all red. Ratchet paid by EXTRACTING: the probe's three deterministic lanes are one call now
  (`probe_actionmap.try_fast_lanes`, 1147 → 1138), and the three wiring guards that named `probe.py` name the
  CHANNEL instead, per V2-555.

- **A PHASE of the relationship has its own prompt, and it archives itself — context packs (V2-675,
  2026-09-11)**: the operator's second half of the same message — «una excepción al inicio en el que la
  conversación fuera guiada por el agente… ¿quién eres? ¿cómo te llamas? ¿dónde vives? ¿qué podría hacer por
  ti?», «tiene que conocerse a sí mismo y saber quién es y sus capacidades», and the architectural ask that
  outlives the feature: «este sistema de prompts que podamos inyectar en ciertas fases o en ciertos momentos
  o en ciertas situaciones es un sistema bastante potente que podría formar parte de nuestra arquitectura…
  de momento solo tendrá esta parte inicial», with the closing rule — «cuando ya hemos terminado con eso,
  esos prompts iniciales desaparecen y ya pasamos a la fase normal». **Three things already put text in the
  turn and none of them is this**: the resource layer is what the agent ALWAYS is (and is cached as the
  stable prefix, V2-536, which is precisely why a phase block may never live there — a cached block keeps
  being spoken after its phase is over); `_directive_block` is ONE style preference he gave this session;
  `live_state()` is what is true this second. A pack is the fourth thing, and the registry
  (`nucleo/context_packs/`) enforces what keeps it from becoming a permanent tax: it is re-judged EVERY turn
  from a cheap local read, an archived pack answers False for good, and **the catch is PER PACK** — one net
  around the whole section would let a single broken pack silently delete every other phase's contribution,
  producing a turn that looks exactly like the steady state. **The INTRODUCTION is the only pack today**, and
  it was measured first: the kickoff asked his name, he answered around it, and `operator_name` was still
  `None` three sessions later — there WAS no phase, so whether the two ever met depended on whether one
  greeting happened to land. The block says what to DO this turn and never what the agent IS, asks ONE thing
  at a time and drops it if he deflects, and **deliberately does not list the widgets**: the resource layer
  already carries the live catalog in the same prompt, and a second inventory written by hand is how two
  lists end up disagreeing (V2-594, V2-603). His «tampoco hace falta que se pase cuatro minutos hablando» is
  in there as a hard rule: two or three capabilities chosen from what he has already said about himself, then
  stop. **Closing it is the hard half**, and he asked for it to be ours and, where needed, a model's: three
  exits, cheapest first — DETERMINISTIC (we know his name, the one fact the phase exists to learn, and the
  memory writes it on its own, so the common case ends with no extra call at all), a JUDGE off the hot path
  and rationed (nothing is settled before four turns, then one call every four), and a CAP (an introduction
  still running after thirty turns is not introducing). **An unreachable judge leaves the phase OPEN** — a
  network blip must not silently skip the introduction — while unreadable settings mean NO phase, because a
  missing block costs a plainer first conversation and a block that cannot be turned off costs every turn
  forever. Watched from the bus (`turn.completed`), the Susurro/actionmap pattern: zero coupling with the
  voice provider, and it covers BOTH channels for free. The flag lives in `AGENT_KEYS`, so a factory reset
  correctly starts the relationship over. **And the phrasebook of V2-674 stands aside while a phase is
  guiding**: during the introduction «hola» is not small talk, it is the first move of a conversation that
  has somewhere to go — his own «excepción al inicio», and the reason the two batches are one. Node **3.38**;
  seventeen disarms, mutations asserted, all red — one came back GREEN and the TEST was wrong: it measured
  `compose()`'s outer net instead of the per-pack catch it claimed to be about, and now asserts that a
  healthy pack SURVIVES a broken neighbour. Ratchet paid by EXTRACTING the cron line to `live_blocks.py`
  (the browser/background-block precedent), and prompt.py's ceiling comes DOWN 854 → 834.

- **A config save is judged by what it LEAVES, and the suite stops writing the operator's routing (V2-673,
  2026-09-11)**: found on his LIVE engine while verifying something else — `config/v2.json` held
  `{"fast": {"provider": "aimlapi"}}` and nothing else, so the EFFECTIVE config was the broker as TITULAR of
  the voice brain (which the model table forbids outright) over a `model` and a `base_url` that were still
  DeepSeek's: one vendor's name printed over another's traffic, the V2-657 defect arriving by a new road.
  **Two faults, and the second is the one that matters.** (1) `config_api._model_mismatch` exists to stop
  exactly this and compared `patch["provider"]` against `patch["model"]` — a patch carrying ONLY a provider
  has no model IN IT to compare, and a partial write is the NORMAL shape of a config edit, so the guard was
  blind to the common case rather than to an exotic one. It reads the RESULT of the patch now, and also
  refuses a provider whose `base_url` was left behind. (2) The writer was
  `tests/infrastructure/unit/core/test_config_api_cloud_gate.py`, which POSTs a real save through the router
  and isolated NOTHING: every run of node 8.2 silently re-routed his brain, and had done since it was
  written — visible only because the new guard started refusing the incoherent result. Fixing that one file
  is not the fix: this is the THIRD time this class has been paid («a test never touches live artifacts»,
  «my suite reset its LIVE engine»), and each time the remedy was one file remembering. `config/v2.json` now
  moves to a temp path for the whole session in the ROOT `conftest.py`, beside `settings.json` and
  `widgets.store.DATA_DIR` which were already there — the routing store was simply the one this invariant
  had never reached — with its row in `test_suite_isolation`. Node **8.8**; four disarms, mutations
  asserted, all red. ⚠️ **A rule every test has to remember is not a rule**, and an unisolated test does not
  fail: it leaves something behind.

- **The DEPLOYMENT picks the profile — nobody is asked, and one default replaces two (V2-671,
  2026-09-11)**: the operator, shown the first-run wizard again after a factory reset — «el paso de si
  quiero una instalación local o remota es absurdo porque tú ya sabes si estás corriendo en el ordenador
  del cliente o la versión de la nube. Entonces esa pregunta va fuera» — and, about the damage it had
  already done, «ni siquiera es una opción en el reset que se altere la configuración del sistema».
  **MEASURED on his own install**: his engine came back on `qwen2.5:14b-instruct` over Ollama with
  `whisper_local` + `kokoro_local`, against the canonical table's `deepseek-v4-pro` + `deepgram` +
  `elevenlabs`. The reset did NOT do that, and the chain is the finding: V2-670 put `wizard_done` in
  `AGENT_KEYS` → the reset dropped it → `_first_run()` went True → `main.js` opened the wizard → it
  recommended `local` (correctly, by its own rules, on Apple Silicon with Ollama running) →
  `profiles.apply()` writes `settings.json` **and** `config/v2.json` as one coordinated lever. **The four
  install keys V2-670 deliberately preserved were preserved, and overwritten twenty seconds later**, along
  with the model routing the Reset dialog promises in writing is never touched — a hint that was therefore
  false, and is true again. Fixes: `_first_run()` returns False in BOTH deployments (a cloud account was
  already exempt, so the question only ever reached a self-hosted human — and asked them, in English,
  before they had chosen a language, to arbitrate between two provider stacks BY NAME; the panel stays
  reachable from 🧭, because wanting local models is legitimate and having it decided FOR you is not);
  `config/profiles.DEFAULT` becomes the canonical table's stack, ending the older fault underneath — **two
  defaults for one concept**, `profiles.py` saying `local` while `voice/engine/core/profile.py` said
  `remote`, whose `remote` row also named `voxtral` + `cartesia` against the table's `deepgram` +
  `elevenlabs` while NOTHING compared the two (that row is what a bare boot uses: every fresh install and
  every factory reset, so the drift shipped a voice stack nobody chose); `profiles.deployment()` reads
  WHERE the process runs from the provisioner's env var and is deliberately independent of WHICH providers
  the profile names — they share a word and are not the same question, and conflating them is what made the
  wizard's answer damaging rather than merely redundant; and `wizard_done` moves to `INSTALL_KEYS`, since
  it records something about the INSTALLATION and having it on the agent side is what let a reset arm the
  wizard. Node **8.5**, whose engine-row assertion is measured AGAINST `config/models.default.json` so a
  table change goes red instead of drifting; five disarms, mutations asserted, all red. The operator's own
  install was restored in the same pass (`settings.json` emptied, the wizard-written `fast`/`memory`
  sections dropped from `v2.json`) so the table governs again.

- **NOBODY SPEAKS before a language is chosen — the wordless picker, the voice that follows the language,
  and where the files live (V2-672, 2026-09-11)**: the operator on his fresh install — «me pide los
  idiomas, pero por detrás está hablando ya en un idioma por defecto… **no quiero que la gente hable hasta
  que no hayamos seleccionado el idioma**» — and «la voz que viene por defecto en español habla bien
  español, pero habla mal inglés… si hay alguien que habla chino o alemán o suajili tenemos que ponerle una
  voz que esté entrenada para esos idiomas». **Both were WRITTEN DECISIONS, not slips**: `agent.py` said
  the question «HAS to go out now, in English (the product default)» and the kickoff began `[FIRST RUN …
  SPEAK ENGLISH ONLY]`, so the one sentence a person could not understand was the one asking which language
  they understand; and `core/config.py` hardcoded `elevenlabs_voice_id` to a Castilian voice chosen by
  V2-035 when the product spoke one language. **MEASURED against the live API before a line was written**:
  `/v1/voices` returns the ACCOUNT's voices and **all 21 premade ones are `language: en`**, so that set
  structurally cannot answer «a voice trained for German»; `/v1/shared-voices?language=<code>` returns real
  NATIVE voices (es → latin american, peruvian; zh → beijing/taiwan mandarin) and honestly returns ZERO for
  Swahili; and a shared-library id works DIRECTLY in text-to-speech with no «add to my voices» step
  (verified with a nine-character synthesis) — without that last one this would have shipped a picker full
  of ids that 400. Also measured: the `.env` copy of the key on this machine answers **401** while the
  credential store's answers 200, so the new module asks the store first and says why. Built: **(1)** the
  first-run branch RETURNS — the session still starts (the mic must be live to hear a spoken answer) and
  says nothing, and the first thing anyone hears is `onboarding.confirmSpoken` in the language they just
  chose, which is also the greeting. **(2)** `i18n/catalog.py` + a rewritten picker that carries no word of
  ours: a speaking mark, then 40 rows of flag + the language's OWN native name, `en`/`es` pinned because
  those are the two the repo SHIPS; typing FILTERS the rows instead of submitting free text, because
  submitting needed a prompt telling you to write something in a language you may not read. **(3)**
  `voice/engine/speech/elevenlabs_voices.py` ranks natives first and KEEPS the multilingual ones last (a
  language with no native voice must still speak), and the ⚙'s list is per-language like Kokoro's. The
  realignment on a language change covered KOKORO only — which is why the cloud TTS never followed — and
  now asks **`voice_is_aligned(provider, voice, lang)`**, a different question from «is it in the list»,
  and the difference IS the defect: the ElevenLabs list deliberately keeps fallbacks, so a Castilian voice
  is in the English list and a membership check would have found it and changed nothing. **(4)** the folder
  step, self-host only and skippable, running DURING the generation (his own sequencing) with its words
  riding the same SSE event already translated: `library/paths.check_base()` is a SECOND door to
  `resolve()` with a different provenance — a person, on their own machine, once — so it accepts an
  absolute path, which `resolve()` never may, and pays for that with a validator that REFUSES instead of
  repairing (exists · directory · writable · never the filesystem root · never HOME itself · never a system
  directory · checked on the RESOLVED path). A cloud account is never asked: there the Volume IS the
  storage. **Two ratchets bit and both were right**: the energy sweep caught the new API calls (exempted —
  ElevenLabs bills per synthesised character and these two endpoints are metadata), and the dependency
  ratchet refused `i18n` reaching into the motor's voice catalog, so the alignment came out of `lock()` and
  lives only in `settings.update()`, the one seam every language writer already goes through. Nodes
  **8.6**, **8.7** and **4.162** (RENDERED); twenty-four disarms, mutations asserted, all red. ⚠️ **The
  rendered node caught a defect on its first run that no source read could**: the speaking mark was mounted
  with `innerHTML`, a prop `dom.js::h()` does not know, so it was set as a plain attribute and painted
  nothing. ⚠️ **And the path validator over-refused on macOS**: `/var` resolves to `/private/var` and the
  per-user temp directory lives under it, so the prefix ban refused an ordinary writable folder belonging
  to the person choosing — `/var` came out, because on Linux it is root-owned and the writability check was
  doing the work anyway. **NOT verified**: the native folder dialog headless (it cannot be), and the whole
  ceremony driven end to end by the operator.

- **A turn that calls a TOOL is covered at the SEAM (V2-669, 2026-09-11)**: the operator, after the engine
  moved onto the slower/better model — «si una pregunta como a qué hora tengo esta actividad en la agenda
  tarda 8 segundos en resolverse, necesitamos alguna frase o palabra de relleno… o incluso más rápido que
  dijera "dame unos segundos", porque si tenemos una locución demasiado larga alargaremos innecesariamente el
  tiempo de respuesta». **Measured in his own observability before building anything** (`deepseek-v4-pro`):
  the `read_widget` turn answering «¿a qué hora tengo la cita con Hacienda?» took **6 029 ms with
  `ttft_ms: 0`** — the first pass returned a TOOL CALL and no text, so the reply stream stayed empty for the
  whole turn — and across **7 real voice turns on a light route the turn ENDED 3.4-5.9 s AFTER the tool
  event**, while the lead-in filler had sounded 1.0-3.3 s BEFORE it. Its ~1 s of audio was long over. Nothing
  covered that stretch: both light-route branches went straight from the tool decision into the second pass,
  and the `emit()` beside them is observability, not a mouth. **The lead-in cannot fix this by construction**:
  it is chosen ~1.1 s in, before any model has spoken, so it can only ever be a blind thinking sound. The
  node now keeps racing the model's first chunk after the lead-in settles and covers a SECOND time when the
  provider publishes a work note at the seam (`filler_audio.note_work`, called from `read_widget`, `recall`
  and `web_search`). **The cover NAMES the source** — «Lo miro en Agenda…», «Lo busco en internet…» — which
  is the one thing the blind lead-in could not say, and is what keeps two covers from reading as the same
  wait said twice: the failure this codebase already met once (V2-189, session 2bdc67ee, «Déjame que mire…»
  then «Vale, dame un momento que lo miro.»). Guards, each disarmed: a second pass that answers inside
  `_WORK_GRACE_S` beats it and nothing is said; it never sounds within `_COVER_MIN_GAP_S` of the lead-in's
  FIRE (measured from the fire, because this node cannot know how long the TTS took); at most one per turn;
  `fillers: off` silences it; it is stripped from the forwarded transcript; and it updates anti-echo but
  **never `_last_reply`** — a cover carries no topic either, and feeding one to the directed-content judge is
  the 2026-08-17 bug. Pools are per language (`covers_widget`/`covers_search`/`covers_recall`, es+en) behind
  the same generated-pack seam the fillers use, so an onboarded language can eventually ship its own; a
  length ceiling is enforced in the test, because **a cover cannot be cut mid-sentence, so its own length IS
  latency** (his rule). **VOICE ONLY, and the module says why**: the text channel has no dead air to fill, so
  the parallel-implementation rule (V2-252) deliberately does not reach this one — written down instead of
  left as drift, with a guard that keeps `note_work` out of `probe.py`. Node **2.53**; eight disarms, each
  mutation asserted before measuring, all red. ⚠️ **Two of them were MINE and green at first**: one left the
  banned call alive inside the comment that replaced it, and one anchored on a line `pick_filler` carries
  BYTE-IDENTICALLY, so it mutated the wrong function (the V2-571 lesson). ⚠️ **And the harness left a
  mutation in the tree**: the mutation-landed assertion raised BEFORE the restore line, so a weakened
  `pick_filler` sat in the working tree after the sweep had already gone green — the restore is in a
  `finally` now. Also fixed here, and the same class: `test_filler_path_never_writes_last_reply` banned the
  string `_last_reply` in the whole file, so DOCUMENTING that rule in a comment turned it red (V2-615's trap);
  it reads comment-stripped code now and asserts BOTH mouths keep anti-echo. **Measured and NOT built,
  reported instead**: the second pass runs on the TURN's spec, so `deepseek-v4-pro` is paid twice per light
  route — 18 samples over the real agenda block put `deepseek-v4-flash` at **715-868 ms TTFT vs 805-949 ms**
  and **909-1 155 ms total vs 1 248-1 769 ms**, with **zero confabulation in 6/6 runs** of the two
  answer-is-absent cases (it states the absence AND names what IS there). The recorded reason pro holds the
  seat is a ROUTING bench («Pro routes 41/42, direct Flash 38/42»), and the second pass does no routing — but
  the allocation table is the operator's and `voice_brain` has no failover, so a split would add a second
  failure surface. His call.

- **A question about what a widget HOLDS is answered by the widget (V2-668, 2026-09-11)**: session 53de97d4,
  10:58:33 → 11:00:03. «¿a qué hora tengo la cita con Hacienda?» → «no la tengo con hora, solo que tienes que
  ir próximamente» — while the agenda held `11:30–12:30 · Cita Agencia Tributaria` in ONE line. Six turns
  later, after he opened the card BY HAND, the model said «hoy a las once y media» **calling no tool**: a
  widget's interior only ever reached the prompt while the card was OPEN (`widgets/brief.py`, `if wid in
  opened`), and NO tool read a closed one — `widget_data` EXECUTES a declared action, `recall` reads his
  long-term memory («no es para datos del mundo»), `web_search` reads the world. A question about his own
  widget's store had no route and was answered from a memory pill, a race the susurro itself filed
  (`[P1·memoria] La memoria durable se inyecta DESPUÉS de responder`). His verdict: «si yo le tengo que
  explicar cómo llegar a los datos, pierdo menos tiempo buscándolos yo». **`read_widget`
  (`nucleo/flash/widget_read.py`) is the fourth door**, `recall`'s sibling in shape — a LIGHT two-pass route
  resolved IN the turn, no card opened, no worker — reading through the seams the widgets already publish for
  the prompt (`refs.prompt_digest` → `coach_context()` → `refs.items_line`), so every widget that can be
  reasoned about while open can be asked about while closed; the second pass has the widget's content as its
  ONLY source and states an absence rather than filling it (V2-210). It lives in the `memory` family, which
  `tool_selection` never trims — that module's docstring already named this exact case («when is the vehicle
  inspection appointment?») and pointed it at `recall`, the wrong store. `web_search`, `widget_data` and
  `recall` now point at it for his own data. Both channels call the module (V2-252). Keyword routing was
  measured and rejected: «¿a qué hora tengo la cita?» hits the CLOCK's keywords, not the agenda's. The 23 100
  catalog ceiling — paid on every voice turn — was met by compacting nine descriptions, never raised. Node
  **2.52**.

- **An order NAMES its target, and a notice waits its turn (V2-666, 2026-09-11)**: the same session, three
  rails each correct in intent and wrong on one sentence. **(1)** «ponme un gráfico de la evolución del
  Bitcoin» → the model escalated, and the show guard STOLE it and opened YouTube with «Aquí lo tienes»:
  `runtime.identify` returned the only OPEN card «by context» (score 0.0, zero candidates) and the guard read
  that as a NAME — a blind open of whatever was on screen, the thing `identify`'s own docstring says it never
  does. `identify_named()` (alias/name only, context breaks ties, never a fallback) is what a SHOW asks now, in
  both channels; with no name and no antecedent the guard resolves to NOTHING and the escalation stands.
  **(2)** «Mírame, ábreme la agenda inmediatamente» opened the SEARCH card: the article «la» is a bare deictic
  token for `looks_like_bare_ref` (right about «cancélala»), so one article made the whole sentence
  «muéstramelo»-shaped, the noun he actually said was discarded, and the fallback «the previous route was a web
  search» chose for him. A sentence that NAMES its widget is never deictic — the name wins first. **(3)**
  «¿a qué hora tengo la cita con Hacienda?» arrived BEHIND three `[SISTEMA]` notes about a dead Bitcoin task
  (`text = "\n".join(notes) + "\n\n" + text`), two of them ordering «Díselo en ESTE turno», and the reply
  opened «Primero, Ricardo, te debo una cosa pendiente…». The operator's rule is the inverse and it is the
  rule of any assistant: the order is served first, the news waits until it is answered. `brain_notes.
  compose_turn` puts his words FIRST and the notes AFTER under a header that says when they may be spoken; the
  two writers now say «DESPUÉS de contestar». A model reads what comes first as the frame of its answer; the
  frame is his. Node **4.160**. Named, not done: the arbiter (V2-653) VETOED the blank `results` card that
  same turn (`show-drag`) and ALLOWED the YouTube blind open — still in shadow, and it cannot arbitrate the
  second class until it consults `identify_named`.

- **The generator's contract never contradicts its gate, and a red gate gets ONE repair (V2-667,
  2026-09-11)**: «ha intentado preparar un widget, ha fallado varias veces, cosa que me preocupa; es un
  widget muy sencillo, quizás ha fallado a la hora de obtener los datos». Not the data: two builds of a
  Bitcoin chart died 17 minutes apart, ~3 min and ~1 $ each, on the SAME error — `data.py imports non-stdlib
  'memory' (data.py must be stdlib-only)`. `generator.py::_CONTRACT` said both things in one block: the
  `data.py` bullet «STDLIB ONLY», the BACKGROUND bullet «`from memory import api as memory; memory.write(…)`».
  A price chart classifies itself as data that changes on its own → the agent followed the second line → the
  gate (the stricter one) killed the widget after the money was spent. `widgets/AGENTS.md:88` had carried the
  corrected form (`ctx.remember(...)` — «so data.py stays stdlib-only, no import memory») and
  `background.TickCtx` is the sanctioned door; the prompt was left behind by that refactor, and it hid because
  it fails late, expensively, and looks like the model's fault. Two changes: the contract agrees with the gate
  (`tick(ctx=None)`, memory through `ctx`, the prohibition spelled out), and **`_repair_once`** — a freshly
  built widget that fails the gate gets the gate's own error and one bounded edit in place before `_discard`;
  a second failure reports the NEW error, what stood after the repair. Create path only; modify has its
  rollback. Node **4.161**.

- **A SEARCH is not irreversible, a confirmation never recites our tool prose, and a bare name is not an
  errand (V2-665, 2026-09-11)**: the operator, with a screenshot — «sólo le he dicho que abra el widget de
  vídeo y que me ponga un vídeo y me ha abierto el chat en la columna de la izquierda, me ha soltado mensajes
  que creo que son de sistema en la interface del usuario, no ha puesto el vídeo… simplifiquemos todo esto y
  arreglémoslo de una vez». **Three symptoms, ONE cause.** At 10:07:07 the model called `widget_data(youtube,
  search)` and `actions.classify` answered CONFIRM, so the irreversible-action gate fired: V2-518 puts
  confirmations in the chat (the column that opened), the question was composed from the action's `desc` —
  text written FOR THE MODEL, which he read as «Ojo, esto es permanente: "BUSCAR vídeos para elegir: pinta
  hasta n resultados NUMERADOS en el INICIO del widget…"» — and the overlay covered the card. **The video had
  LOADED** (`videoId 16AhQaStWxg`, «Apolo 11: cómo fue la llegada del hombre a la Luna»), dimmed behind a
  modal he could not get past; it is visible in his own screenshot. Why CONFIRM: `_IRREVERSIBLE_RE` matched
  «manda» inside «…add_results los manda a la cola» — prose describing a SIBLING action, inside an action
  declared `view: true`, which writes nothing at all. **The catalog audit is the finding**: across 15 widgets
  the heuristic produced TWO hits, both false positives (`youtube:search`, `torrent:open` — both `view: true`,
  both on «manda»), and ZERO true positives; all 15 genuine confirmations carry an explicit flag. Three fixes,
  most general first: **(1) a `view` action can never be irreversible** — the flag means it only changes what
  is displayed and «writes nothing the operator would have to undo and nothing outside the app» (the generator
  contract, verbatim), so the two are mutually exclusive by definition and only the guess put them together;
  an explicit `confirm: true` still wins. **(2) The heuristic reads the action's OWN clause**, not the usage
  guidance after the first period — the same boundary `confirm_gate._human_confirm_question` already draws
  when it quotes a desc, applied one level earlier, to the DECISION instead of to the sentence. **(3) A
  confirmation carries the sentence he hears**: NINE of seventeen confirming actions had no `confirm_q`, so
  reciting tool prose was the NORMAL path, not the rare one — the seven still bare now have one, and
  `widgets/validator.py` refuses both a bare confirmation and the `view`+`confirm` contradiction, because a
  rule each widget author has to remember is not a rule. **And the trigger**: that search came off a bare
  «Johnny.» — the wake word alone, reaching the model with a memory pill about the video he had asked for the
  night before, so it answered «Voy a buscar el vídeo del Apolo 11» and acted; six seconds later a second bare
  «Johnny.» got «Dime, Ricardo.», which is the right answer. The most frequent utterance in wake-word mode was
  non-deterministic and half the time it invented an errand. `presence.is_summons` makes it its own class
  beside the presence knock (a leading interjection and a trailing courtesy allowed — they carry no request
  either; anything else is a real turn), answered from the same honest pools with no model and no tool, in
  BOTH channels (V2-252/V2-539). The engine's own susurro had filed it at 10:07:40: «[P2·routing] Una
  locución de wake-up suelta se convierte en consulta de widget y en promesa de acción». Node **4.159** (21
  cases, including the whole-catalog ratchet that keeps the heuristic from ever DECIDING again); five disarms,
  mutations asserted, all red — and the `confirm_q` disarm also turns `make test-widgets` red, which is the
  gate biting rather than a test agreeing with itself. Open and named in the initiative: the turn that loaded
  the video returned `completion_chars: 0` and a susurro repair spoke 23 s later over work that had already
  succeeded; the fragment accumulator DUPLICATED his sentence around the summons; and the shadow arbiter
  vetoed both the correct load and the spurious search, so it still cannot arbitrate this class.
  **V2-665b, same day, found by DRIVING the live engine rather than by reading**: «Johnny.» through the probe
  still reached the model, because `fast_lane.presence` and `presence.mirror` both resolved his name with
  `config.settings.get("assistant_name")` — **a key nobody writes**. A rename lands in MEMORY state and is
  pushed into `voice.attention` by `memory_cache`; the settings file has held `None` the whole time. So this
  is a defect OLDER than the batch that found it: the vocative strip that recognises «Johnny, ¿sigues ahí?»
  as a knock has been dead for a renamed assistant since V2-640 shipped, and the summons check would have
  been born dead the same way — **passing its own unit tests, because those handed the name in by hand**.
  `presence.assistant_names()` is the single source now and asks the authority (`attention.wakewords()`, the
  same list the gate itself consults: default + env + rename); both callers stop reading the settings file,
  and `is_presence_check` strips every name it should, longest first. The node grew an end-to-end drive of the
  REAL probe mirror, and its guard is anchored on the IMPORT rather than on the words — both files explain
  this defect in prose, and a scan its own explanation trips is a scan that gets weakened instead of believed.
  Sixth disarm red.

- **An order about DATA is not an order about the CANVAS — and «me vas a poner el vídeo» is an order
  (V2-664, 2026-09-11)**: the operator drove his own session and reported three things: the Apollo 11 video
  never played, «borra los datos de la agenda» **closed every widget he had open**, and twenty seconds later
  the YouTube card **reopened by itself, empty**. He then asked the question that shaped the batch — are the
  GUARDRAILS failing, or the errand harness we have just been adding? **Session eedf7f9b contains ZERO
  harness events**: no goal was born, no `false_claim` ran, nothing escalated. V2-660/661 did not fire once.
  All three are rails, each correct in intent and wrong on one sentence.
  **(1) The media grammar does not know how Spanish asks for a video.** «Bien, me vas a poner el vídeo del
  Apolo 11 llegando a la luna» → the model DID call `play_video(query="Apolo 11 llegando a la luna")` and
  `canvas_license.video_license` ate it as context-bleed: the pattern spells out the infinitive of every verb
  it knows (cargar, buscar, reproducir, abrir, cambiar, repetir) except the commonest one —
  `pon(?:me|te|le|lo|la|gas?|ed)?` **cannot reach «poner»**, because after «pon» come word characters and the
  `\b` fails. The periphrastic form («me vas a poner…», «¿puedes ponerme…?») is how a person actually asks,
  and it was the one shape the guard could not see; the turn ended promising «Y ahora te pongo el vídeo del
  Apolo 11» over a player that never loaded. Fixed by adding the infinitive/gerund/future stems (plus
  `mostrar`/`ensenar`, missing for the same reason); V2-635's participle rule is untouched. Second-order and
  worth recording: the veto marks the turn `deduped`, so the promise backstop stayed quiet over it too.
  **(2) A bare quantifier is not the canvas until it says so.** `hard_interrupt` fired close-ALL on *(a close
  verb ANYWHERE) AND (a quantifier ANYWHERE)* — his sentence carries «quita» in one clause and «todas esas
  entradas» fifteen words later in ANOTHER, so an order to delete ROWS INSIDE the agenda wiped the desktop,
  twice (the glued fragments re-fired it). The rule is now structural and needs no lexicon of intentions —
  grammar, never intent (V2-095): look at what the quantifier **governs**. Nothing («cierra todo»), a
  particle («ciéralo todo ya») or a card noun («todos los widgets») is the canvas; any other noun («todas
  esas entradas», «todos los datos») is a thing inside a widget. Implemented in BOTH copies, because the
  decision genuinely exists twice (`voice/attention.py::_quantifies_the_canvas` and the client fast lane's
  `quantifiesTheCanvas` — V2-252/V2-555, with a test reading both). V2-600's fullscreen veto and V2-584's
  stop-object rule are untouched.
  **(3) The fail-open release was driving the canvas.** V2-647 holds a spoken turn until the gate rules and
  fails open after `HOLD_MS`, on the stated rationale that *showing an ambient line is a nuisance, swallowing
  a real one is the bug*. Two things were wrong: **2.5 s is shorter than the verdict it waits for** (the
  accumulator holds an unfinished sentence for as long as he keeps talking — his verdict landed 2.86 s after
  the first held fragment, so the hold was in practice not holding), and **the release delivered BOTH
  halves**. At 09:40:24 it fired 0.36 s before the verdict while he was describing this very failure out loud
  («…que ha sido poner un vídeo…», every fragment correctly ruled AMBIENT) and the fast lane opened the card
  he had closed. The two halves are not equally reversible: `deliver(text, isFinal, judged)` now carries
  whether a verdict actually ruled directed, the CHAT still fails open, and the CANVAS never does.
  Nodes **3.36** and **4.158** (the client half drives the REAL `voiceCommands.js`), plus five new groups on
  4.145. **Six disarms, each mutation asserted before measuring, all red.** ⚠️ 4.158's own trap: the fast lane
  dedupes an identical action signature for 2.5 s, so two `closeAll` cases in a row measure the DEDUPE and not
  the rule. ⚠️ Renumbered at closure: the concurrent session had already PUSHED the two numbers below this
  one, and what is pushed wins — the initiative file is created when the number is TAKEN, not at the end. **NOT verified live**: needs an engine restart and a page reload. Open and named in the
  initiative: four duplicate «dentista» crons injected as four identical notes into one turn, and the product
  question of a reminder riding the turn it interrupts (V2-607's design, his call).

- **The window measures SILENCE, not speech — and a text the agent produces is FILED in the library
  (V2-661, 2026-09-11)**: «prioridad absoluta: le digo la palabra, hablo de forma continua sin pausas de 3 o
  5 segundos, y me desactiva el micro — se apaga el color del orbe y yo no he terminado la frase». Session
  1cdcb08e, 00:46: with the window open he spoke for **47 s** with no gap over 1.1 s — eleven VAD rising
  edges, the STT holding the sentence as «frase a medias», no verdict possible mid-sentence — and the whole
  sentence was judged AMBIENT at :52. V2-660 had made the window measure from the speech ONSET, but every
  rising edge re-stamped that onset, so the sentence was measured from its LAST breath, 33 s after the
  anchor: the fix for «judged at the end» had moved the reference to the wrong start. The ring died 5 s in,
  because its client timer only knows the last DIRECTED verdict. His rule (V2-655): three or four seconds
  **of silence**. Now an utterance is a CHAIN of VAD segments: `note_speech_onset` keeps the chain's first
  onset when a rising edge follows the falling edge (`note_speech_end`, new) by less than the window;
  `note_directed` moves the onset ONTO the anchor when a fragment's verdict lands while he is still talking;
  `_window_ref`/`window_open` answer `now` once his voice stopped and the silence outlasted the window; a
  180 s cap bounds a missed falling edge. Both VAD events carry `edge: on|off` and `sse.js` holds a LIT ring
  while his voice is active, re-arming a full window when it stops — never lighting one from off. **The
  file**: «¿has guardado la declaración en mis archivos?» → the worker fetched and verified the text and
  wrote a perfect `.md` into `widgets/_data/navegador/` — the browser task's directory, the only path it had
  ever been told — then saw the `archivos` shelf empty and spent three minutes trying to download a PDF.
  Resource, not reasoning: `library/index.save_text` (one safe leaf, `.md` when the name has no document
  extension, collisions suffixed), `archivos.save_document {name,text}` (lands the card on the shelf with the
  file selected, returns `where` + absolute `path`), `documento.save_to_library` (the text ON SCREEN becomes a
  file — one data-op, no worker), and `dispatch_prompts.library_block()` appended to every trusted worker
  prompt: the root, the shelves, the filing action, and the wrong place it actually wrote to. Nodes **3.34**
  and **4.154**; four disarms, mutations asserted, all red. A sibling session owns the other half of that
  night (`reveal_local_file`: a double-click must not download a second copy). ⚠️ The ring holding through a
  long sentence is NOT verified live yet.

- **The errand HARNESS closes the circle, and the window measures silence from speech ONSET (V2-660,
  2026-09-11)**: the operator's directive — «cuando obtiene permiso para realizar una acción falta terminar
  de cerrar el círculo… un arnés dinámico que comprueba que lo pedido se ha conseguido y solo entonces se
  informa». Session 0141a72a, two defects in one minute. **(1)** «Johnny.» opened a 5 s window; he began
  «Enséñame la declaración…» 2 s later and the STT finalized it 6 s later — judged at the END it fell
  outside the window and three directed turns became room noise. The window measures his SILENCE, which
  ends when he opens his mouth: `attention.note_speech_onset()` (VAD rising edge, `pipeline/agent.py`) and
  `_window_ref()` measure against the onset when it fell inside the standing window (a stale onset older
  than the anchor grants nothing). **(2)** After his «Adelante» the model said «aquí tienes el texto
  completo…» having run ONE web_search — `documento` open and EMPTY — and nothing compared the claim with
  the screen: `promise_backstop` reads promises, not completion claims; `_no_tool` was False because the
  search fired; the susurro caught it 40 s later. **`nucleo/harness.py`**: a ledger of GOALS `(kind,
  target, his words)` born from what the turn TOUCHED (every card shown, incl. the promise-backstop show),
  verified by readers of the product's own truth (the widget's `view_data()` `empty` flag + the open-cards
  state; a widget that does not declare emptiness → unverifiable, and the harness stays SILENT — a wrong
  «you did not deliver» over a delivered card is worse than none). Three seams: turn end in BOTH channels
  (`claims_done` over an unmet goal with no data-op this turn — the V2-603 fire-and-forget race is trusted
  — → the honest follow-up is spoken, V2-572 shape, and the errand escalates with the doc surface quoting
  his words); the prompt's live state (an open goal is a FACT with its RULE, V2-453); the loop heartbeat
  (met goals close with an event — no second mouth, the delivery announced itself). Typed by the WIDGET
  touched, never by an errand's words — the doctrine's word-swap test holds. F2-F4 named in the initiative:
  widget-declared verifiers (his CRITERIA, the language), worker goals closed by delivery events, bounded
  iteration, and the clarifying-question hinge (a «¿te refieres a X?» + yes should bind to the original
  request; `dispatch_confirm` parks only PERMISSION questions). Node **3.33** (18 cases); five disarms,
  mutations asserted, all red. ⚠️ NOT verified live end-to-end.

- **A widget_data cut by the TOKEN CAP escalates with the doc surface instead of apologizing (V2-658,
  2026-09-10)**: «le he dicho un documento y no lo ha hecho» — measured twice in consecutive sessions
  (the Declaration of Independence): the model opened an EMPTY `documento`, promised twice, finally
  pasted the FULL text inline into ONE `widget_data` → `finish_reason: length`, the action was
  discarded (V2-171's recording worked), and the turn fell to the mute backstop's «Perdona, ¿me lo
  repites?» over an errand it had in hand. Content that exceeds a voice turn is a WORKER's delivery
  (V2-644's doc surface), never an inline retry: `_drop_tool_call` records **`args_head`** (the head of
  what the model was writing — the operator's bare turn text at the incident was «Venga, estoy
  esperando.», useless as an errand), `oversized_widget_write()` names exactly the token-capped
  `widget_data` class (the other two drop classes are different faults, V2-566, and are NOT escalated),
  and both channels rescue: the voice provider escalates the request with `surface=documento` BEFORE
  the holding line so the turn speaks it, the probe synthesizes the same `escalate_to_slowbrain` before
  action classification. The `documento` manifest teaches the rule (costs prompt only with the card
  open — exactly the failing state). The same session live-verified V2-657: ~90 s of wedding room talk,
  zero responses. Node **3.32**; four disarms, mutations asserted, all red. ⚠️ NOT verified live
  end-to-end (needs a real worker run).

- **The conversation can DIE during table talk: the aside, the spoken shut-up, and the honest provider
  label (V2-657, 2026-09-10)**: the operator's dinner session (130418ed), read event by event. With a
  window open, every table utterance was admitted `active_window` (V2-531: inside a live window nobody
  judges), the model ANSWERED the room («Acostaros» → «Buenas noches, Ricardo»; «Luis, disfrutemos de
  las noticias…» → a clarifying question; «¿Mi copa de vino?» → a hallucinated denial), and both the
  admission (`note_directed`) and the answer's falling edge (V2-655) re-anchored the 5 s window — the
  conversation structurally could not die while anybody talked near the mic, until «¿Por qué sigues
  escuchando? Maldita sea, cállate. Apaga.» and the ⏻ by hand (killing a live worker with it). Three
  mechanisms: **(1) `[[aparte]]`** — the model's SANCTIONED silence for a turn clearly addressed to
  somebody else present (rule rides the wake-word block of `style_directive.prompt_lines`; ante la
  mínima duda, contesta): the channel marks the turn handled (never on TYPED, V2-646), skips the hollow
  repairs (a sanctioned silence is not a hole for V2-642's closer to fill), and
  **`attention.retract_last_directed()`** rolls back exactly that admission's window refresh — refusing
  once anything newer re-anchored, because deafness is the worse failure (V2-655); the window then
  expires from the operator's own last word. Probe mirrors the backstop skip. **(2) A spoken SHUT-UP
  order** («cállate», «silencio», «deja de escuchar»; per-sentence, vocative-stripped, interjections
  admitted — the session's literal «Maldita sea, cállate.») is an ATTENTION order resolved at the gate
  BEFORE any model: `attention.close_window()` (shared `_wipe_window()` with the V2-656 mode flip, same
  `orb:attention` emit) and the turn is swallowed — answering it would re-anchor the window it ordered
  shut. «apaga/apágate» deliberately stay out: they name the power or a device. **(3) The provider
  LABEL derives from the endpoint** (`model_spec._provider_label`; `ollama` honoured — it IS routing):
  that session's every brain event said `engine: aimlapi` while every request went to
  `api.deepseek.com`, and the stale label had been resurrected at 21:59 by the remote PROFILE, whose
  `fast` section still declared the broker under a rationale that stopped being true when the cloud
  moved to DeepSeek direct — profile aligned to the canonical table titular, with a test measuring it
  AGAINST the table. Node **3.31**; six disarms, mutations asserted, all red — one came back GREEN
  first because the wiring guard's anchor also matched the second occurrence of the same expression
  (the V2-571 lesson, paid again; re-anchored on the unique `or (` shape). ⚠️ NOT verified live —
  needs an engine restart. Open, named: a filler can still sound over an aside turn (the addressee is
  only known post-model until V2-651 F1), and «apaga» by voice reaches no power switch on purpose.

- **A bare boot loads the PRODUCT, a dead session is VISIBLE and recycles, the ◉ reads the speaker side,
  and no conversational pause exceeds 5s (V2-656, 2026-09-10)**: the operator's integrity review after an
  evening lost to a restart without `BRAIN=nucleo` — the profile default handed the AgentSession the raw
  broker plugin (no FlashBrain, no memory, no relay), the fundless provider 403'd every turn, LiveKit
  closed the session as unrecoverable at 38 s, and the ◉ said «Todo bien» while he talked to a grey orb.
  **(1)** Both profiles default `llm` to `nucleo` (`profile.py`) — baselines stay one env var away; booting
  the real product never again depends on remembering one. **(2)** A close-with-error records
  `health_state("voice","dead")`, alerts the timeline, and asks `homeostasis.request_recycle()` (new seam
  `_consume_recycle_request`: honoured next beat, survives the cooldown, never loops); the `/api/status`
  voice row goes RED and `StatusPanel.js` stops overwriting a server-side error with the browser's green —
  the browser's room stays connected when the server session dies, so it structurally cannot see this
  failure. **(3)** `voiceStatus` says the two silent «no me habla» causes (blocked playback, the 🔊 mute);
  `server/system_audio.py` reads the MACHINE's output (macOS osascript, cached): volume 0 / muted → warn,
  and an unmeasured OS gets NO row, never a fake green. A genuinely dead ElevenLabs key reddens the TTS
  row via the balance probe; a key that 401s only `user_read` records nothing — measured first: the
  operator's scoped key serves TTS fine. **(4)** The broker left every DEFAULT path (profile default gone;
  the stale `fast.provider` label removed from the operator's v2.json → the canonical table's DeepSeek
  titular governs). **(5)** Operator directive superseding 2026-09-09's ceiling: **no pause over 5 s** —
  `attention_window.MAX_S`=5 (the shape scale stays, every rung clamps), and `window_s()` clamps AFTER the
  env override in smart mode, because the ⚙ knob offered 15-120 s and an old stored value would have
  silently defeated the rule (options now 3/4/5). Livable because V2-655 anchors at the agent's LAST word.
  **(6)** A mode FLIP closes the standing window NOW (`attention.on_mode_change`, called from the single
  `settings.update()` seam only on a REAL change — a bulk save re-sending the same mode wipes nothing) and
  announces `orb:attention`, where `sse.js` now also darkens the ring: he measured 20+ s of orange after
  activating wake-word mode, riding out a window opened under the previous mode. Node **9.3** + additions
  to 9.1 and the attention suite; four disarms, mutations asserted, all red. ⚠️ NOT verified live: the
  3-second ring darken and a recycle after a real death.

- **IF IT TALKS TO YOU IT LISTENS TO YOU · the core is not modifiable · ⏻ stopped resumes nothing
  (V2-655, 2026-09-10)**: the operator, on the forensics of session 85eec898 — «arregla todo eso, no
  podemos permitir la sordera». Three defects, one shape: every piece does something correct and the
  SUM fails in silence.
  **A · THE DEAFNESS.** Sixteen of his turns in a row classified `🙉 ambiente`, «¿Qué te ha pasado?
  ¿Te has colgado?» and «Hola otra vez ×3» among them — 44% of that session. The window opened at
  16:31:55 sized 15 s and expired at 16:32:10 while the agent was still working; it then spoke for
  **90 seconds** and ended with «¿Sigo?», and the answer two seconds after its last word was room
  noise. Structural, not a classifier miss: `note_bot_speech` could only HOLD a window somebody else
  opened, so **the agent's own mouth could never grant attention** and the silence clock ran down
  during its own monologue — with the irony that a proactive delivery DOES reach `note_reply`, so one
  ending in `?` computed a 15 s `window_hint` for a window nobody opened. `attention.
  note_addressed_speech()` now ARMS the window before the agent speaks and the falling edge ANCHORS it
  at the LAST word (arming and not anchoring is the whole point: anchoring at the first word of a 90 s
  delivery IS the bug); `proactive.notify(opens_window=True)` by default, because that is what a
  proactive delivery IS. **The kickoff stays closed** — the written decision was always about the
  GREETING, and the guard was re-scoped to say that rather than weakened. `loop.py` stopped opening the
  window BEFORE its own 10-20 s of TTS. And **ambient sound does not touch the counters** (his rule,
  verbatim): `sse.js` did `else store.clearAttentionHit()`, so **a stray word from the room turned off
  his «te escucho» ring** while the engine's window was wide open — the client contradicting the engine
  about the one thing the ring reports; both verdicts carry `window_open` now, the ring darkens only
  when the engine says the window closed, and never re-arms a ring already lit. **Deliberately NOT
  done**: widening the gate (the 09:24 session has 603 discarded turns and ZERO directed, with nobody
  ever saying the name — that is V2-647 working), and any new signal (his call: ambient is ignored,
  full stop).
  **B · THE CORE IS NOT MODIFIABLE.** His directive: voice, chat or any interface with permissions may
  only modify WIDGETS. A message he pasted into the chat, written for a DEV agent, became an errand to
  a `claude_code` worker **in the same second** the model asked «¿Me pongo?»; the only thing that
  stopped it was the SPEND gate, and `danger.py` is money/commerce vocabulary with **not one word about
  touching the engine** — a coincidence, not a control. The protection that seemed to exist was
  accidental: the `architect` branch is also `kind="code"` WITHOUT being a widget task, and that one
  does not go through the confined generator — a CLI worker with `Write`+`Edit` and **the whole
  repository as cwd**, reachable by voice. `nucleo/protected_core.py`, two layers: MECHANISM
  (`writes_are_confined` — the question is the ERRAND, not the kind; only the widget generator and the
  cluster dev worker write, everything else gets a scratch cwd and no Write/Edit; fails CLOSED) and
  INTENT (`touches_the_engine` — grammar, never intent, exempted when the sentence names a widget,
  applied at the SINGLE gateway so the errand never comes to exist: no record, no sheet, no name; the
  refusal is spoken and lands on the timeline, because refusing in silence reads as a fault). **No
  `confirmed` escape hatch**: the spend gate is lifted by a yes, this one is not. ⚠️ Measured while
  writing it: the Spanish SUBJUNCTIVE slipped through — `modific\w*` does not match «modifiques»
  (modifi-QUE-s), so «quiero que modifiques el motor de voz» passed clean; prefixes cut before the
  alternation now. 10 vetoes + 12 legitimate errands, 0 failures both ways. The cluster `dev` channel
  stays outside on purpose and says so.
  **C · ⏻ STOPPED.** With `{"state":"stopped","src":"operator"}` persisted, boot resurrected a stale
  errand and spawned a GLM Brain Worker; `rehydrate.py` consulted the switch in NO line. The gate goes
  at the TOP, before `forget()` consumes the trail and `_bump()` burns a `RESUME_CAP` life — gating six
  seconds later at the dispatch door rejects correctly and **destroys the interrupted work in
  silence**, the very failure that module exists to prevent (*postpone, don't lose*, the rule
  `loop._fire_due` already applies to crons). `runstate.blocks_new_work()` is the ONE answer for the
  three spending doors and **fails CLOSED**: all three carried their own try/except and **all three
  failed OPEN**, so an unreadable switch meant «go ahead and spend» (the asymmetry with `stopped()` is
  deliberate and written down). Second door found and closed: `resume_interrupted_generations` relaunches
  a real `claude -p` and was gated by neither the switch nor the active brain.
  **D · A QUESTION IS NOT THEATRE.** `clarifying.asks_permission` is a NEW grammar and deliberately not
  the existing `asks_for_missing_detail`, which is about a missing DATUM and keeps courtesy OUT; the
  distinguishing feature is what the question is about — STARTING («¿me pongo?») versus REPORTING LATER
  («¿te aviso cuando lo tenga?»). The errand is PARKED in `dispatch_confirm`, which already collects the
  yes/no deterministically, tells the brain something is stopped so it does not narrate progress, and
  expires silence into «esa tarea NUNCA empezó» rather than into execution; the line says OFFERED, never
  IRREVERSIBLE. Fails CLOSED. ⚠️ A disarm came back GREEN and accused the CODE: the courtesy veto guarded
  NOTHING («te aviso» was never a permission phrase) and would have vetoed «¿te lo busco y te aviso
  cuando lo tenga?», which IS asking — **a guard that guards nothing is worse than none**, deleted.
  Nodes **3.27-3.30**, 16 disarms with each mutation asserted. The architecture ratchet went red three
  times and was paid by EXTRACTING (the attention gate → `attention_turn.py`, nucleo.py 3049→3033),
  never by raising a ceiling. ⚠️ **NOT verified live** — needs an engine restart.

- **THE MICROPHONE SWITCH has ONE door, and it is not the wake-word mode (V2-654, 2026-09-10)**: the
  operator, reading the forensics of session 85eec898 — «cuando yo desactivo el icono, ese estado es
  TOTAL … el estado se debe controlar en un solo sitio y controla todo el sistema. No puede fallar
  nunca.» He was right and it was worse than it looked: `store.micMuted` + `hb_mic_muted` had **SIX
  writers and four of them only painted an icon** — the boot probe on both shells, the ⏻ power button on
  both shells, the mobile dock, the server-stopped branch — because `applyMic()` was not on their path;
  and there was **no fourth thing to move at all**, since the engine had no notion of a microphone
  switch, so a correct client could not be checked and a wrong one could not be caught. Measured: the
  icon read CLOSED while the track published, the engine transcribed him for seven minutes and escalated
  an errand off what it heard. The mobile file's own comment already NAMED the failure («the phone would
  paint itself off with the mic open — the state that lies, again») and the line under it still only
  painted. Two secondary faults in the same path: `setMicrophoneEnabled` returns a PROMISE whose
  rejection a synchronous `catch` cannot see (a failed publish change was a silent divergence), and
  nothing re-asserted after a republished track. **`frontend/app/services/mic.js` is THE door**: one
  write moves the SIGNAL, the STORAGE, the live TRACK and the ENGINE (`POST /api/mic`), with the
  transport injected by whichever session engine is live and **registering APPLYING** (the reconnect
  hole). **`voice/mic_input.py` is THE holder**, and its `blocks_turn()` is consulted in the turn path
  ABOVE the attention gate: a closed mic reaches no model, no tool, no widget, no memory, no errand.
  Failure directions are deliberate and asymmetric — **muted is STICKY** (a client that mutes then dies
  leaves the engine muted, the safe side) and **the boot default is OPEN** (a stale client must never
  leave the agent deaf forever — deafness is the OTHER failure that same session paid for, 16 turns
  discarded in a row); the **session heartbeat re-asserts every ~4 s**, so a divergence in either
  direction self-corrects without anyone remembering to, and `muted` stays OPTIONAL on the beat so an
  older client beats as before. **NOT the attention mode, and neither may be written in terms of the
  other** (operator's clarification mid-build): the 🤖 wake-word mode is what makes a permanently open
  microphone livable — audio arrives, is transcribed, and `attention.py` decides turn by turn what was
  addressed to us — and **those rules are untouched**; a hard close is consulted first and **no wake word
  lifts it**, lifting the close **changes no attention state**, and a swallowed turn never reaches
  `note_directed()`. The one exemption is the TYPED turn, because muting in order to type IS the use
  case: consumed **one-shot** (`attention.consume_typed`, beside the window-based `was_typed` the mute
  backstop owns), never on a time window — with a window, typing and then speaking walks the spoken turn
  straight through the closed switch. It is deliberately **not a privacy boundary against the browser**:
  a live track still reaches STT and the transcript still lands in observability, because that transcript
  is the EVIDENCE of a divergence and hiding it is what made this cost seven minutes to see. Nodes
  **3.26** (engine) and **4.152** (the frontend RATCHET — nobody writes the mic state outside the door,
  nobody touches the track outside a session engine; the incident was not a broken function, it was six
  writers of one state, and *a rule each caller has to remember is not a rule*). Nine disarms, each
  mutation asserted, all red. The architecture ratchet went red mid-build and was paid by EXTRACTING the
  rule to `mic_input` rather than raising the ceiling. ⚠️ **NOT verified live** — needs an engine restart
  and a page reload.

- **The CANVAS ARBITER — one decision tree for every widget mutation, shadow first (V2-653 F0,
  2026-09-10)**: the operator's structural verdict after 30 days of widget incidents — «cada vez que
  hago una prueba me falla por un lado o por otro… un catálogo de <15 widgets: un sistema de puertas
  lógicas podría manejarlo; los usuarios van a forkear widgets, el sistema tiene que ser
  estructuralmente sólido; decisión piramidal, pocas opciones por nivel» — and this pass's own census
  agrees: ~8 doors mutate the canvas, ~13 guards veto a posteriori across ~10 modules and 2 channels,
  each correct and measured, and the SUM is a blacklist that never converges (every session finds the
  next gap) whose pieces now collide (the V2-652 silent tail = two correct guards interacting).
  `nucleo/canvas_arbiter.py` inverts the posture: every mutation is judged by ONE pyramidal tree
  needing TWO credentials — PROVENANCE (closed set: user/system/worker:tid/actionmap/flash/backstop;
  an unknown src or op inherits NOBODY's pass) and a LICENSE (the operator's words in THIS turn, a
  task that owns the surface, or his own hands). The proven guard modules are the tree's LEAVES
  (`canvas_license`, `close_guards`, manifest-driven `producers`/`actions.is_view`/`runtime.identify`),
  so a user-forked widget inherits the rails from its OWN manifest with zero code of ours.
  **F0 is SHADOW, deliberately** (the V2-651 pattern): `decide()` is enforced nowhere; ONE tap in
  `observer.emit` — the funnel every canvas command already travels as a `widget` event with `src`
  (V2-039), every turn as a `transcript`, every gate ruling as an `ambient` — assembles context and
  emits `kind="arbiter"` verdicts (allow/veto · rule · evidence; `_CAT` family `widget`; kill-switch
  `ZAELAR_ARBITER_SHADOW=0`; re-entrancy-guarded, fail-open). `data:*` order logs now CARRY their
  payload, so `payload-in-turn` is judged precisely. **The conformance suite is the month replayed**:
  V2-567 (a close order licenses no show), V2-605, V2-635 (insults close nothing; pausing is not
  fullscreen), V2-650 (a replayed play order is an order; the dentist duplicate stays dead), V2-650b
  (chatter reopens nothing), V2-652 (the drag turn), ambient credit, backstop duplication — node
  **3.25**, all green against `decide()` first try. Its own first run found `op=None` walking out as
  `lifecycle` (op vocabulary validated BEFORE the provenance ladder now), and a carrier disarm came
  back green TWICE (the tap test hands in its own dict; then the fix's regex died on the first paren
  and failed on GOOD code, masked by a pipe eating pytest's exit code — measure both directions, with
  pipefail). **Gate F0→F1, the operator's condition**: ZERO false vetoes over his real sessions,
  audited from the shadow verdicts. Then F1 arms data-ops at `widgets/server_api._dispatch` (verdict
  travels as a ticket via `provenance`), F2 funnels the ~15 scattered `emit("widget","show"/"close")`
  sites through `arbiter.command()`, F3 RETIRES each absorbed guard (dedupe cross-turn, `show_
  contradicts_the_order`, the probe's duplicated wiring) with its disarm inverted — the system ends
  with FEWER pieces. Census, tree diagram and full plan: the V2-653 initiative.

- **An internal message never reaches the operator's ears, a cover matches the order, and the agenda
  never invents an hour (V2-652, 2026-09-10)**: the operator's manual session (7f77e2cc, «pide cita
  previa en Hacienda»), read event by event — five defect classes, four closed here. **(1)** `add_meeting`'s
  retry instruction («vuelve a llamar a add_meeting con el título, el día (YYYY-MM-DD)…») was SPOKEN aloud
  and painted into the chat as zaelar's own words, twice: `data_ops.report_failure` (V2-603) voiced
  `message or error`, and `error` is often literally addressed to the MODEL. Now only `message` (the
  speakable sentence, the V2-463/V2-650b convention) is voiced; a bare `error` still corrects the model
  through the [SISTEMA] note but never becomes agent speech — and the agenda's empty-add refusal carries
  both keys. **(2)** «…Añade en la agenda mañana una cita» was covered with «Un momento, que lo busco…» and
  the complaint «Te he dicho que hagas una acción sobre la agenda» with «Déjame que lo mire…»:
  `filler_kind` now judges per SENTENCE with the leading vocative stripped (the order lives in the LAST
  sentence of a spoken turn), `_ACTION_VERB_RE` knows the data-write verbs (añade/apunta/anota/recuérdame…,
  es+en), `_SOCIAL_RE` knows complaint shapes, and an explicit imperative outranks the complaint beside it.
  **(3)** The «17:00» item he read as us copying his «reunión a las cinco» was `add_meeting`'s own
  `default="17:00"` over the promise backstop's hour-less write: a missing hour is a FACT — no hour → an
  all-day entry, and a timed add of the same day+title SETTLES that twin in place (one row, the dictated
  hour) instead of standing beside it («dos ítems»). **(4)** The errand escalated onto `lista` and the
  worker delivered a booking as a comparison sheet of non-options: the escalation `surface` gloss now
  teaches that a GESTIÓN (reservar, pedir cita, tramitar) is voz — delivered DONE, never a list — paid
  under the shared catalog ceiling by compacting the same tool. **(5a)** The worker typed the placeholder
  NIF «12345678Z» into Hacienda's REAL form twice and ground the census-validation modal for minutes: the
  web prompt's RECON/ASK discipline now says recon ENDS at a validated personal field — ask
  (`worker_bridge ask`) or deliver the blocker naming the datum, never retry with invented values. Nodes
  5.15 / 2.50-family files / 4.6 / 4.151; nine disarms, mutations asserted, all red — one came back GREEN
  first because its strip anchor matched an earlier «bucle» in the file and nothing had mutated (assert the
  mutation before measuring, paid again), and the V2-650 checkout-over-uncommitted-fix trap was paid once
  more before switching to commit-before-disarm. **Open, named in the initiative**: the SILENT TAIL (ten
  consecutive zero-char replies while the dedupe swallowed a context-bled add_meeting — a spoken DIRECTED
  deduped turn still counts «handled», V2-646's rule is typed-only), «Quítalo inmediatamente» never
  reaching `cancel_meeting`, Flash reframing a booking as research in the escalation brief, and showing
  the worker's browser for a voz-surface errand.

- **Knowing WHO is talking — the browser computes it, F0 measures in shadow (V2-651 F0, 2026-09-10)**:
  the operator's order — identify HIS voice and give it priority (which is also what lets Zaelar follow him
  over a TV: a TV voice is a human voice, only the voiceprint separates it), know that other people are
  present without profiling them, and NEVER let a third party's «yo soy Pedro» rename him or dirty his
  single profile. Architectural directive: **the browser carries the cost** — in cloud the backend is on the
  server and the browser on the client's laptop, so the fingerprint is computed CLIENT-SIDE and only a tiny
  label would cross the wire, never the audio-to-analyze (local self-host is one machine, so the split is
  free). This ships **F0 only: shadow measurement, ZERO behaviour change.** `frontend/app/lib/speaker-id.js`
  is a pure DSP core (autocorrelation pitch + spectral centroid + loudness, unit-tested with synthetic
  frames) plus a thin `SpeakerID` AnalyserNode adapter that self-segments (its own energy gate — the LiveKit
  engine gives the browser no VAD signal), auto-enrolls the operator's first speech segments, and classifies
  every later segment against a MAP of profiles (`classify`) — operator today, household voices tomorrow, an
  ONNX embedding (CAM++/onnxruntime-web) later behind the SAME interface, all without changing this file.
  `session-lk.js` runs it in a best-effort rAF started after `audio.initMic` and stopped in `stop()`, logging
  each verdict (label · score · operator score · pitch/centroid/rms) through the EXISTING `api.clientLog` seam
  into observability — nothing gated, no memory written, killable with `?nospk=1` / `zaelar_spk_shadow=0`.
  Its whole job is to produce the separability numbers on the operator's real mic/room BEFORE any later phase
  thresholds against it (measure, don't deduce). Node **4.150** (8 groups); five disarms verified red.
  **A review pass the same day found three real defects in this very build, all fixed here**: (1) the coarse
  vote is unusable as a measurement — `matchScore` is a 3-criteria vote, and measured across 60 distinct
  synthetic voices it returns exactly THREE distinct values, so every verdict now also carries `distancesTo`,
  a CONTINUOUS per-feature z-distance (that is what F1's threshold gets chosen from); (2) the agent's OWN TTS
  comes back through the mic and could be auto-enrolled AS the operator, poisoning the measurement — a
  `suppressed()` predicate wired to `store.botSpeaking()` now discards anything in flight and fingerprints
  nothing while zaelar talks; (3) TWO wiring assertions were weak in the same way — `_stopSpeakerShadow()`
  also matched the function DEFINITION, and the start-ordering check merely asserted two independent
  substrings existed, staying GREEN with the lines swapped — both re-anchored on the real call sites and
  re-disarmed. Measured cost: `pitchOf` is 0.91 ms/frame ⇒ ~27 ms/s ≈ **2.7% of one core**, only while speech
  is active.
  ⚠️ **NOT verified live**: the real mic tap and the fingerprint's accuracy in a room need the operator's
  engine — F0 exists precisely to gather that. Next, per the study: F1 identity shield (operator-voice-only
  writes to identity/state, closing the empty-profile and correction-bypass holes), F2 the «environment
  people» roster + a compact per-turn presence line the FlashBrain manages cheaply (no per-turn prompt/traffic
  cost when nobody else is there), F3 the opt-in hard voice-lock. **Mechanism, limits and how to read the
  shadow log: `.meshkore/docs/modules/zaelar-speaker-identity.md`** (the phase plan lives in the initiative,
  which is not published). One measured interaction named there and load-bearing for F1: `attention.py`'s
  active-conversation shortcut (V2-531) means that INSIDE a live window nothing is judged — with a TV on, room
  lines were logged `👂 dirigido a zaelar` and answered — so a speaker check must be consulted BEFORE that
  shortcut or a perfect voiceprint would change nothing.

- **A just-closed widget does not reopen on chatter, and a garbled list name resolves or refuses
  naming what exists (V2-650b, 2026-09-10)**: the operator's very next live minute (sid 3d394…), read
  event by event. «Johnny, cierra el widget de YouTube» worked exactly as designed (the V2-567 guard
  discarded the model's spurious show, the backstop closed) — and eight seconds later ROOM CHATTER
  («Avisando de… cuidado, que aquí está pasando algo») made the model re-emit that DISCARDED
  show_widget, and nothing blocked it: the card he had just closed reopened over nobody's order.
  V2-635 built licenses for close, video and fullscreen; **SHOW had none**. New
  `canvas_license.reopen_license` (narrow on purpose): only a widget the OPERATOR ordered closed in
  the last two minutes is gated, and it reopens on a conjugated media/show request or when his own
  words resolve to that widget through the V2-082 certainty resolver — never on chatter; a discarded
  drag counts as handled (`deduped`). Every close door records the close (`note_operator_close`: the
  tag funnel, the named-close backstop, the close-not-delete guard, the action map's fast lane), and
  both channels consult the license (probe mirrored, parallel-impl rule). In the same minute, «arranca
  la lista de Trublo» (the STT's rendering of «True Blue») was served TWICE by two mechanisms — the
  `play_music` tool played the SONG, then a re-emitted `play_playlist` data-op failed
  `playlist_not_found` on the garble and the correction path read the RAW CODE aloud
  («playlistnotfound») over music already playing. `play_playlist` now resolves a spoken garble by
  unique-winner similarity (≥0.6 with the runner-up under 0.5 — «Trublo»→«True Blue» measures 0.71
  against 0.27 for the next list; two near-matches stay a refusal, never a guess) and its refusal is a
  SENTENCE that names the existing lists (V2-463 — `report_failure` already speaks `message` when one
  exists). The provider ratchet (3043) was paid by extracting the whole show_widget resolution to
  `show_target.resolve_show` (guard-target passed IN — importing it there would add an upward
  dependency the V2-569 ratchet freezes); nucleo.py ended at 3036. Node **4.149** (+3 cases in
  4.148's musica file); four disarms, mutations asserted, all red — run AFTER committing the fix,
  which is the V2-531 lesson applied instead of re-paid. Detail: the V2-650 initiative.

- **A replayed play order is an order — and the playlist keeps the playback it started (V2-650,
  2026-09-10)**: the operator's morning session (aed0736c, the «True Blue» errand), read event by event.
  The worker did its job — refused the torrent as protected, confirmed the real album (Flash had escalated
  «"Blue" de Madonna (es un álbum de versiones de blues/jazz)», an invented gloss), built the 9-track list
  and verified it on screen. Then the music died twice, silently. **(1)**
  `widgets/musica/data.py::play_playlist` loaded its store snapshot, called the provider — which resolved
  track 1 and wrote `yt.videoId` + an 8-track queue into the store through its own load/save, exactly the
  read-modify-write contract the file's own header declares — and then persisted the STALE snapshot,
  erasing the playback it had just started: nothing sounded, the action reported `ok: True`, and the live
  store still held `yt: {}` as the evidence (the write landed 0.6 s after the action — too fast for the
  resolutions the clobber then discarded). The V2-611 class again: a stale snapshot is never written back
  over a store a collaborator writes to. A non-local first track now gets NO db (the connector owns the
  store during play/queue) and the final persist runs on a fresh load; a local first track keeps the old
  single-writer flow. **(2)** The operator then ordered the play THREE times («Vale, pues reproduce la
  lista», «Vamos, dale al play, a la primera canción») and the data-op dedupe guard (V2-038) ate every
  one as context-bleed: its only escape measures word overlap against the PAYLOAD, and no natural play
  order names `{"playlist": "true-blue"}` — one turn even ended with `completion_chars=0` over his
  explicit command. New `canvas_license.replay_license` (V2-635 doctrine — declared data + grammar, never
  intent): an identical re-emission passes the dedupe only when the action is one the widget DECLARES as
  starting production (`runtime.produce` — agenda-class ops declare none, so the founding dentist
  duplicate stays dead) AND the turn carries a conjugated media request. Verified against the session's
  own four turns: exactly the two real orders pass, the two drag turns stay deduped. Node **4.148**;
  three disarms, mutations asserted, all red. ⚠️ The V2-531 lesson was paid AGAIN mid-build: a
  `git checkout` after a disarm restored HEAD and silently wiped the uncommitted fix in all three files —
  re-apply the edit or commit BEFORE disarming, never checkout over uncommitted work. Open, named in the
  initiative: the same session's «¿Qué tiempo va a hacer hoy en Soria?» (and the complaint after it) was
  classified `llm_ambient` in `always` mode and never answered — an attention-gate classifier miss, not
  touched here; Flash's invented album gloss in the escalation brief and the errand title frozen on
  «Blue» after the worker confirmed «True Blue» (the V2-644 title class, for widget-surface errands).

- **A REPORT is delivered as a DOCUMENT — the `informe` surface (V2-644, 2026-09-09)**: the operator's
  order after the Juncal research (session adc8a7c7, read event by event before touching anything): a report
  errand must open «el visor simple» — a process tab while the work runs, then ONE white-paper document —
  never the results sheet, whose card list «queda un poco ridículo» for a report. What the forensics showed:
  STT heard «la empresa junca de ella Salvador SL» (= Juncadella Salvador SL, the operator's own surname),
  Flash guessed «Juncal de El Salvador» and the errand title froze on the guess even after the worker
  CONFIRMED the real name and NIF (21:14:30); the surface was `lista`, so the browser's page-extract pushed
  einforma's own trust badges («Cero CO2», «Confianza Online», «Tarifas») into Resultados as findings; the
  worker sent its web_search query under a key the bridge did not read, got a SILENT
  `{"results": [], "source": "none"}` twice, concluded «el puente no devuelve nada» and drove the browser
  for four minutes; and the report never landed anywhere (cancelled by a restart). Four changes:
  **(1)** a SIXTH surface value `informe` (`surfaces.DOC`, aliases informe/documento/report/dossier;
  offered in the escalation tool's enum — the shared catalog ceiling was paid by compacting, ending UNDER
  the old 23_100). Deliberately NOT in `SHEET`: every `opens_sheet` caller branches, so a report errand
  never rides the results-sheet path. **(2)** commission opens the `documento` widget bound to the task
  (`nucleo/docsheet.py`: doc_open/doc_retitle/doc_close — the sheet's own three gestures, sibling module),
  criteria seeding is guarded off, `sheet_for_delivery` skips doc-surface errands (the badge-junk path),
  and the worker prompt gains `DOC_SURFACE_BLOCK`: deliver via `documento` (4d), results is NOT open, first
  `show` early + `append` per section, say «Elaborando el informe…» before writing, and the document title
  carries the TRUE confirmed name — not the errand's phonetic guess. **(3)** the widget grows a live
  process view: `view_data().process` derived per read from the new `dispatch.task_progress(tid)`
  (`sheets.task_progress`, task-keyed sibling of `sheet_progress`), persisted at finish; Proceso|Documento
  tabs only when a process exists, and the document is PAPER — a white page whatever the host theme.
  **(4)** the `use_tool web_search` gate refuses an EMPTY query loudly naming the exact form, and accepts
  the sibling keys (`q`/`text`/`search`/`consulta`) a worker actually writes. Node **4.143** (17 headless +
  4 bridge + 6 rendered cases); seven disarms, mutations asserted, all red — TWO came back green first and
  the TESTS were wrong: nothing measured the finished-empty default tab (the alive safety net covered the
  mutation), and the bare harness defined no theme vars, so `var(--hb-bg,#fff)` resolved white and a
  regression to theme-following was invisible — the fixture now mounts a hostile dark host theme.
  ⚠️ NOT verified live end-to-end: a real informe errand needs a worker run; the engine restart +
  served-code checks are the shipped verification. Detail: the V2-644 initiative.

- **The orb answers ONE question, and a stopped mic is crossed out (V2-648, 2026-09-10)**: three things
  were painting on the same surface and nobody had reconciled them since the orb's colour became the
  LISTENING signal (2026-09-09). **(A)** The claim ignored the microphone: `_listeningNow()` read powerOff +
  attention mode, so a muted mic left the orb glowing «te escucho» over a shut input. The rule moved out of
  the draw loop into `services/listening.js` (dependency-free, so the test drives it and not a copy) and
  now reads `agentLive()` → mic → mode, in that order; an unreadable store answers NO, because a false grey
  is a nuisance and a false orange is the reported bug. **(B)** `canvas#orb.muted{opacity:.5;grayscale(.45)}`
  predated the signal and desaturated the orange into a dull brown whenever he silenced zaelar's voice —
  «el altavoz no tiene ningún efecto sobre el color del orbe». Rule and class deleted; what they carried
  MOVED to the 🔊 control beside it, which already paints itself crossed and grey. `frozen` stays. **(C)**
  Grey alone was saying «mic off», and grey is also what a disabled control looks like: `MIC_OFF` now adds a
  slash (the speaker's own off-face language), and the lit state gained a halo + heavier stroke so ON reads
  as LIT, without dimming OFF further — the muted mic must stay legible, its slash IS the message. The VU
  meter's RESTING floor went .72 → .88 in the same pass: a live, unmuted mic between words sat closer to a
  disabled control than to a lit one, which is why the icon he singled out was the one that read wrong. Nodes
  **4.146** (e2e: the slash measured by its RENDERED ink, both swap directions, ON-vs-OFF weight through the
  real cascade, and the orb's painting identical either side of a speaker click) and **4.147** (unit: the
  real `isListening`). Three disarms red. Detail: the V2-648 initiative.

- **The room is not the operator (V2-647, 2026-09-09)**: «todo lo que voy diciendo en mi conversación en la
  sala está siendo captado y transcrito en el chat». The GATE was never wrong — every line of that
  conversation was correctly judged `ambient` and answered with silence, and the grey orb correctly meant
  «hearing, not attending». The FRONTEND was wrong, twice: the gate's verdict travels as its own event and
  arrives just AFTER the transcript, so `sse.js` painted every user transcript into the wall and learned the
  verdict second — and never unlearned; and that same ungated transcript drove `handleWidgetVoice`, so room
  speech carrying «cierra» could close his widgets — V2-015's premise bypassed by a client-side shortcut
  older than it. `services/attention_hold.js` now HOLDS a spoken turn until the gate rules: directed →
  released whole (wall + canvas, `isFinal` intact), ambient → the turns that verdict COVERS are dropped,
  uncovered fragments keep waiting for their own ruling. It FAILS OPEN (no verdict in 2.5 s → release:
  showing an ambient line is a nuisance, swallowing a real one is the bug) and holds nothing in `always`
  mode; typed text bypasses it, directed by construction. Node **4.145**, six groups against the REAL module
  (not a copy of its logic), three disarms red. ⚠️ Two traps paid: `node --check` said OK on an sse.js with a
  stray `}` (the ES-module trap — the browser boot is the real gate and caught it), and `wallpaper_clear`
  wrote to the store with nothing to clear, which made a contract test that calls every declared action touch
  the suite's real settings file. Clearing nothing writes nothing.
- **A typed message is never lost (V2-646, 2026-09-09)**: two defects, one promise. **(A)** With ⏻ OFF the
  composer swallowed messages: `sendText` queues the text and calls `start()`, whose own gate against the
  server's truth refuses — so the queue never flushed, while the wall showed «sent» and `send()` had already
  cleared the box («la primera lo ha mandado al vacío… he tenido que escribir dos veces»). `canSend()` =
  `agentState() !== "off"` now gates the button (disabled + a dead style + a title saying why) AND `send()`
  itself, because Enter bypasses a button's `disabled`; `starting` stays open (there the queue does flush).
  **(B)** Measured 22:30:39: a TYPED «puedes ponermela en youtube o de alguna forma?» spent its 51 tokens on
  a `play_video` the canvas license vetoed as context-bleed, `deduped` marked the turn handled, and the mute
  backstop stayed quiet — `completion_chars: 0`, a written question answered with nothing. The V2-633/634
  silence exemptions are for AMBIENT room speech; a sentence somebody sat down and WROTE can never be that.
  New fact `attention.note_typed()/was_typed()` (stamped by the chat/paste handler beside `note_directed()`),
  and on a typed turn a vetoed/deduped action stops counting as «handled». V2-634's source guard was narrowed
  by exactly one state, with the reason in the assertion — a deduped duplicate still counts on SPOKEN turns.
  Node **4.144**; four disarms verified red. Left open on purpose: the license refused «ponermela» because the
  request is ANAPHORIC (it points at «la peli de minions» from earlier), which is a licensing-vocabulary
  decision, not a silence bug.
- **A cover never ends the turn, and covers describe MOTION (V2-642, 2026-09-09)**: session 651c25ac,
  20:51:49 — «¿Por qué la vista semanal no tiene una columna para cada día?» → «Déjame que mire…» → a reply
  with `completion_tokens=84` but `completion_chars=0` (the model spent the turn re-emitting a stale data-op
  the context-bleed guard rightly ignored) → silence forever. The operator's rule: «igual no tenía
  respuesta, pero igualmente hay que cerrar las conversaciones». Four changes. **(1)** third hollow-turn
  guard `a_cover_left_hanging` (mute completion after a sounded cover, or over an information question —
  but an uncovered mute STATEMENT stays legitimate silence, V2-633) + `mute_cover_repair` composes the
  missing answer; failing even that, `langs.pick_closer()` speaks the honest deterministic closer («pues
  ahora mismo no tengo una buena respuesta a eso») — the turn ALWAYS closes. **(2)** the three repairs
  (V2-572 bare ack · V-587 empty wait · this) consolidated in `second_pass.hollow_repairs` — ONE seam,
  called by the voice channel with `covered = filler fired after this turn's stream began` (monotonic
  stamp); the extraction also paid nucleo.py's ceiling (3024/3043). **(3)** the filler pools follow
  OpenAI's realtime prompting doctrine, which the operator pointed at: a cover DESCRIBES THE ACTION («Voy
  a mirarlo…», «Te lo compruebo…»), never a bare thinking sound — their explicit avoid-list («Hmm…», «Let
  me think…», «One moment while I process…») was literally our old pool, and a source-level test bans
  those exact phrases from returning. **(4)** a DANGLING fragment arms NO cover («Ahora quiero» got «A ver
  qué tenemos…» at 20:51:26 — half a sentence gets no promise; suppression needs POSITIVE evidence, an
  empty text still arms). Tests ride existing nodes 3.19 + the mouth file; three disarms verified red
  (the first mute-guard disarm came back GREEN — both branches caught the case — and was replaced by the
  real one: «empty reply never repairs», the pre-fix world).
- **The desktop wallpaper is a SPOKEN property (V2-641, 2026-09-09)**: the operator's spec — «igual que
  podemos con la voz colocar widgets o pasar el orbe a la barra, quiero poder poner una imagen de fondo…
  la buscaremos con el sistema y le diré usa la número 3». The flow: `show_images` finds photos (with
  «fondo» in the query, `image_turn._WALLPAPER_INTENT_RE` prefers ≥1600px files and sorts by area — there
  are 2900x1440 monitors behind this), the viewer shows them, and `imagenes`'s new `wallpaper` action
  (item resolved exactly like `select`; no item = the one on screen) persists it. Persistence is the
  V2-617 two-layer seam: `config/settings.py` (with `_sanitize_wallpaper` — the URL is echoed into a CSS
  `url("…")` on every client, so the sanitizer is a SECURITY seam: http(s) only, no quote/backslash/space,
  else {}), plus localStorage for instant paint; the live push rides the widget event channel
  (`emit("widget","wallpaper")` → sse.js → `theme.setWallpaper`, persist:false to avoid the echo loop).
  CSS: `body.hb-wallpaper .canvas` paints the photo under a `--canvas`-colored ::after scrim (.38) so
  widgets stay legible over any photo in either theme. The tool CATALOG deliberately carries no line —
  it sits 3 chars under its per-turn ceiling; the manifest brief (costs prompt only with the widget on
  screen, V2-526) teaches the action instead. Node **4.141** (e2e paints a fresh browser from the mocked
  account settings + sanitizer unit); disarm of the CSS rule verified red.
- **Covers that LISTEN, and the presence fast lane (V2-640, 2026-09-09)**: the 19:27 testing session
  (sid 1674ee35) became a «diálogo de besugos» measured turn by turn: every meta-question («¿qué quieres
  ver?», «¿a qué tengo que esperar?») armed a THINKING filler («Déjame ver…»), which read as an answer
  promising to look at something, which spawned the next meta-question — while the real replies (3-5 s
  TTFT on deepseek via aimlapi) died to barge-ins. Four changes: **(1)** `filler_kind` gains a SOCIAL
  class (`_SOCIAL_RE`: presence checks, greetings, questions about the conversation itself) with its own
  explanation-opener pool («Pues…», «Verás…») — a thinking sound may never again answer a question about
  us. **(2)** pools grew (20 neutral es / 9 action / 6 social, en likewise) and `pick_filler`'s
  anti-repetition is now a recent WINDOW (depth 4), not depth-1 — the operator heard «A ver…» twice in
  three turns. **(3)** the cover is chosen at ARM time and `filler_audio.arm(messages=…)` appends a
  [SISTEMA] note with the exact phrase to the turn's last user message (local list only — the V2-536
  stable prefix never changes), so the reply CONTINUES the muletilla instead of colliding with it; fire
  time speaks the promised phrase. **(4)** «¿sigues ahí?» never reaches a model: `nucleo/flash/presence.py`
  holds the ONE detector (whole-utterance, ≤7 words, vocative-stripped; a knock with cargo falls through),
  `fast_lane.presence` answers instantly from the idle/busy pools and the exchange still lands in the
  window + conv buffer (the V2-605 canned-line lesson), `probe.py` mirrors it via `_presence.mirror`
  (parallel impl). Plus the prompt now says the model's UI capabilities are EXACTLY the declared surface
  (canvas tags + widget actions) — the wallpaper turn showed it narrating past a capability that did not
  exist. Node **3.24**; two disarms (social branch, arm note) verified red.
- **The agent gets its OWN filesystem, and the torrent client becomes a SYSTEM tool (V2-638, 2026-09-09)**:
  the operator's reframing of V2-637, the day after it shipped. What a widget downloads is **not that
  widget's property**: a paper for `documento`, a track, a film — it all belongs in a tree the AGENT owns,
  structured, reachable by every widget, present by default on a cloud Machine. Nine requirements, and the
  design falls out of the first: **one root, a folder per kind, layout from GENESIS and overridable by him.**
  - **`library/`** (new module, declared in `cluster.yaml`): `paths.py` — the layout read from
    `nucleo/genesis.json` with per-install overrides in `<workspace>/config/library.json`, mtime-cached
    exactly like V2-633's style policy, plus `resolve()`, the SINGLE door. That door is a security seam, not
    a convenience: every path arriving here comes from a magnet payload, model output or a query string, so
    absolutes are REFUSED (never silently reinterpreted — stripping the leading slash maps `/etc/passwd` to
    a plausible in-library path and hides the caller's real intent), `..` is refused, and the check is made
    against the RESOLVED path, which is the only version that catches a symlink planted inside the library.
    A renamed folder is one segment, so a rename can never relocate the tree. `formats.py` separates what a
    file IS from whether the BROWSER can play it; `index.py` is the normalized record a widget consumes
    (`url`/`playable`/`kind`/`size`) and files a finished download onto its shelf; `server_api.py` serves
    `/api/library/*` including the ONE stream route both players share.
  - **The download policy is his**: by default only bring home what the page can play, with `keep` as the
    explicit escape for «lo quiero para el pendrive» — and an unplayable file is still offered through
    `/download`, because refusing without a way round is how a legitimate file looks broken. This corrected
    a REAL defect shipped the day before: V2-637 listed `.mkv`/`.avi` as playable video. No mainstream
    browser decodes either, so the client could pick a file it was structurally unable to show.
  - **The torrent client is now a system tool**: it writes ONLY into `library/downloads/` (his isolation
    rule) and never needs a path outside it — filing is our move, afterwards; `want` picks the shelf the
    caller came for, so the same client serves video, music and documents; a refusal NAMES the file it
    declined and offers the way round; and it has an operator SWITCH (`config/connectors.json`, default ON —
    it is the one connector that can saturate a line). **Second real defect found**: `connectors.enabled()`
    consulted the store and an env var but never the declared `_DEFAULTS`, so any connector shipped ON
    answered False on a fresh install. It hid because all four pre-existing connectors default to False.
  - **The video player stops being YouTube-only** (his requirement that the player hold the torrent tool
    directly — a film is watched there, so the download that produces it belongs to the same surface): a new
    `widgets/youtube/sources.py` owns where a row comes from — `youtube` → the embed, `local`/`torrent` → a
    plain `<video src>` against our own routes (the library one, or the piece-aware one while it still
    fills). Extracted rather than added because `data.py` sat EXACTLY on the 900-line newborn ceiling, so it
    ends net negative (899→896). The control funnel learned the second vocabulary: `post()` translates the
    IFrame API's verbs into media-element operations, so all five control sites work unchanged instead of
    growing a parallel copy. **Two latent defects closed BEFORE any non-YouTube row could exist**:
    `blocked_ids` keyed the blocklist on `videoId` and every such row carries `""` — one blocked local file
    would have put `""` in the set, which the queue filter reads as «matches everything», silently skipping
    every local item forever; and `swap_to` located the playing row by `videoId`, so two local rows both
    resolved to the first. A streaming row is also no longer given an invented `youtube.com/watch` URL.
  - **The music widget gets its third source** and, with it, MIXED playlists — needing **no new schema**:
    the track shape already carries `uri` and YouTube-audio already uses a scheme there (`yt:<id>`), so a
    local track is just `uri = "local:<rel>"` and playlists, Recent, Top and dedup keep working untouched.
    `local_audio.play` clears the `yt` block (the bar shows ONE thing) and bumps a `seq`, because asking for
    the same file twice must be two events and not one silent no-op. Two things deliberately NOT done
    because they fail silently: a local track is never queued into the connector (that queue holds query
    STRINGS it re-resolves, so a file would be dropped), and a filename with no « - » never invents an
    artist (a wrong credit propagates into Recent, Top and every playlist that holds the track).
  - Nodes **7.42** (19 cases), **4.139** (10 RENDERED + 14 unit) and **4.3** (+13); twelve disarms, every
    mutation asserted, all red. ⚠️ The V2-554 Dockerfile guard caught the missing `COPY library` before it
    could break a cloud boot — `server/__init__.py` imports it at module level. **NOT verified live**: the
    engine was not restarted, so none of the three surfaces has been driven by hand.
  - ⚠️ **Concurrency incident worth keeping**: three sessions were editing `tests/run_testmap.py`. To keep a
    peer's staged hunk out of my commit I rebuilt the file as HEAD + my hunk — and in that window the peer
    committed, so their node was lost and HEAD went red with two test files outside the map. Restored in
    `2b9ba75`. Rebuilding a shared file from HEAD to isolate one hunk is only safe if nobody commits in that
    window, which a session cannot know.

- **The agenda looks like a CALENDAR — the shapes everybody already knows (V2-643, 2026-09-09)**: the
  operator's redesign order with two screenshots of the week view. Measured before touching anything: the
  card declared NO `manifest.size`, so it opened at the default 400×340 tile — literally «se muestra muy
  pequeño, se cortan las palabras de abajo», the same class as V2-630 (musica) and V2-597 (youtube); the
  «week» was a list of the seven horizon days, one per row, with the per-day tabs (Hoy · Mañana · vie · sáb
  · dom · lun · mar) that are exactly the cramped buttons he was complaining about; and the calendar
  connectors were three 15px icons in the header that dropped an explanatory paragraph over the content —
  «los iconos son tan pequeños y están apelmazados que no se sabe qué significa ninguno» plus «un texto ahí
  que me parece absurdo como descripción». Now: a toolbar (brand · range · ‹ Hoy ›), a defined view band
  whose active view is an INVERTED chip (the V2-636 language), and the four classic views — **Día** (hour
  grid beside the coach rail this widget has always had), **Semana** (seven Mon–Sun COLUMNS over the grid,
  each day's items inside its own column, overlapping meetings packed SIDE BY SIDE because a calendar that
  hides an appointment is the worst thing this widget can do), **Mes** (navigable 7×N grid) and **Lista**
  (the Schedule view). His «varios colores, varias intensidades» is two axes, both DERIVED FROM DATA and
  never from sniffing a title (V2-095): the HUE comes from the dictated `category` or the planner's own
  block kind, the INTENSITY from how settled it is — a confirmed appointment is solid, one the other side
  has not answered is dashed (the convention every calendar already uses), a planner-placed task block is
  soft. Badges carry the rest of his spec: a bell when a reminder exists, 👥N for attendees. So the data
  model grew what a calendar entry actually is — `attendees` (names or a bare count: «somos cuatro» is four
  seats), `status`, `location`, `category`, `allDay` — with `update_meeting` as the single door for editing
  them (it touches ONLY the keys the payload names) and one default that matters: a meeting WITH people is
  born `pending` and one without is `confirmed`, because you invite people and then wait. ⚠️ Two bugs the
  tests caught, both mine: «sigue pendiente» read as CONFIRMED because «si» lives inside «sigue» (word
  boundaries now, and `_PENDING_RE` runs FIRST because «sin confirmar» contains the confirm stem — a disarm
  that stayed green proved nothing measured that negated case, which is what decides the order); and an
  all-day entry CRASHED the whole day plan, because `planner.plan_day` read `mt["startTime"]` on a meeting
  that by definition has none. The card FILLS its frame (`:has` on `.hb-scroll`, V2-636) with the grid
  scrolling inside, so nothing is clipped at any size; `manifest.size` 920×640. Node **4.142** (17 RENDERED
  cases — seven columns, a chip landing at its hour's pixel, two meetings not covering each other, the real
  card chrome for the clipping cases per the V2-608 fixture lesson), V2-540's render test rewritten to the
  new DOM with every behavioural claim intact, and the XSS fixture repointed at the surface that now
  renders. Ten disarms, mutations asserted, all red. ⚠️ Renumbered TWICE at closure (640 → 642 → 643): the
  concurrent session had already pushed V2-640/641/642 into this log — what is pushed wins, and the cheap
  thing to move is the batch that is not committed yet. Detail: the V2-643 initiative.

- **The agenda answers to the voice: the view alias, the missing vocabulary, the visible details, and the
  operator's language (V2-639, 2026-09-09)**: the operator's session, read event by event — he asked FOUR
  times for the month view and the widget landed on today every time, silently. The model had done its job
  (`show_day {view: 'month'}`) and `apply_action` only read `day`/`date`: the V2-341 class again — the
  model's natural alias must not cost the fact. `show_day` reads `day|date|view|mode|vista` now. Three
  intentions had NO vocabulary at all (the clear_all lesson): `move_meeting` (find like cancel_meeting,
  the end keeps the meeting's DURATION, and the reminder MOVES with it — an alarm for the old day fires a
  ghost, V2-473), `set_reminder` with a date and no title reaches EVERY meeting of that day («avisos para
  todas las citas del jueves» is one intention, not N turns), and `add_task` (a task is not a fake
  appointment with an invented hour; same no-inventing write discipline as add_meeting). The appointment's
  SUBSTANCE travels in `notes` now, and `prompt_digest()` (the V2-544/V2-576 seam) hands the brain the
  upcoming meetings — date · hour · title · reminder · notes — so «qué es ese punto del dentista» stops
  being a guess: `coach_context` only ever carried TODAY, so every meeting beyond it was invisible and the
  model narrated. `ref_index` exposes future meetings and the manifest declares `ref: "title"` on the three
  meeting actions (V2-595), so a spoken reference resolves. The whole surface is multilingual now:
  `_resolve_date`/`_resolve_time` hear English, the planner's INVENTED labels (Lunch/Break/overflow/
  avoidance) follow a `lang` argument — dictated titles pass through untouched, they are data — and
  `widget.js` dresses through `ctx.t`/`Intl.DateTimeFormat(ctx.lang)` (V2-613; `widgets.agenda.*` in both
  bundles, i18n manifest 5→6). Seed packs v7 carry the operator's literal live sentence («muéstrame la
  agenda con vista mensual») and the day/view grid into the deterministic lane. Node **4.140** (19 + 6
  RENDERED cases); six disarms, mutations asserted, all red. Detail: the V2-639 initiative.

- **A canvas mutation needs the operator's words — and a known order survives the wake word (V2-635,
  2026-09-09)**: one live session (34386d8f) measured four classes of the same failure, the model dragging
  its PREVIOUS tool call into a turn that licensed nothing: «Johnny pausa el vídeo» became fullscreen (the
  verbatim «pausa el video» seed missed because the phrase carried the agent's name — the map's exact
  whole-utterance lookup was dead in wake-word use), «minimiza el vídeo» became fullscreen TWICE (the
  toggle was the model's only route, and on a non-maximized card the toggle does the exact opposite),
  «Johnny eres tonto» and «¿Y por qué lo has quitado?» each CLOSED the widget nobody asked to close (the
  first emptied the loaded video, so «Continúa el vídeo» honestly died with «No hay ningún vídeo»), and
  «Muy bien, señora.» / «¿Pero por qué lo has cambiado otra vez?» each RELOADED the playing video. The
  remedy is grammar, never intent (V2-095), the stop_worker GUARD 2 posture: `nucleo/flash/
  canvas_license.py` (shared, BOTH channels) — `close_license` (looks_like_close: a model [[close]] or a
  widget_data «close» without a close verb in the turn is drag, discarded), `video_license` (conjugated
  request forms only — a participle narrates the past; «otro/otra» only NEXT TO a media noun, because
  «otra vez» in a complaint was the measured false positive; a short bare «Sí» keeps answering the
  model's own offer), and `fullscreen_license` (no screen-size words = drag, discarded; shrink words
  route to the new first-class `minimize` canvas order — executor + SSE + `desktop.shrink(id)`: exit
  fullscreen → restore maximize → rail chip — never the toggle backwards). A guarded discard counts as
  HANDLED (`deduped`), so the V2-633 silence never falls into the mute apology. And the fast lane retries
  its lookup with the leading VOCATIVE stripped (`attention.strip_leading_wakeword` +
  `actionmap.match_spoken`, both channels): only the known wake words come off — normalize.py's
  no-courtesy-stripping doctrine stands. Seed packs v6 add the session's missing phrases (minimiza /
  pantalla completa / cierra el vídeo, es+en). The provider ratchet was paid by extracting the play_video
  and fullscreen_widget branch BODIES into `video_turn.voice_execute` / `show_target.fullscreen_dispatch`
  (where the licenses live once for both channels). Node **3.23** (16 cases); eight disarms, mutations
  asserted, all red. Detail: the V2-635 initiative.

- **The video widget dresses like the product (V2-636, 2026-09-09)**: the operator's redesign order with
  his screenshot — he grew the card with the mouse and the control buttons were CLIPPED under its bottom
  edge; the tabs read as a second title line; title and date burned two rows; the controls were text
  buttons («no sé si es necesario el texto Play en un botón de play»). Now: the PLAYER tab is a flex
  column that FILLS the card (`:has` on the real card chrome — `.hb-scroll` overflow hidden, root
  height 100% — the frame takes every spare pixel and YouTube letterboxes inside the iframe, so the icon
  bar below is pinned and visible at ANY card size; every other tab keeps its scroll); the tab strip is a
  DEFINED band (bottom border, nowrap) behind a red brand mark, with the active tab an INVERTED chip
  (ink↔bg — the operator's «color de fondo y el texto invertido», which is also YouTube's own dark-mode
  chip); title left + channel·date right on ONE line (`.hb-yt-tline`); the controls are SVG icon buttons
  (⏮ ▶/⏸ ⏭ · vol−/vol+ · mute) in the music widget's `.hb-mus2-cbtn` language — local copies per V2-557 —
  with the main play/pause a red round toggle whose face says what a click will DO, and the volume
  readout as the bar's only text («70%», «—» muted); playing markers wear #f03; the voice hint only
  teaches over an EMPTY player. Node 4.4 (+1 file, 10 RENDERED cases — the clipping case mounts the REAL
  card structure per the V2-608 fixture lesson). Frontend-only: a page reload picks it up. Detail: the
  V2-636 initiative.

- **An embedded torrent client, so a magnet becomes a video playing INSIDE the agent (V2-637, 2026-09-09)**:
  the operator asked whether Zaelar could carry its own torrent client as an add-on — the mesh already has a
  search agent that returns a magnet, and he wanted the other half: find the movie AND play it in the agent,
  the same promise as the embedded browser, working on cloud and self-host, «part of our code package, nothing
  installed on the system». Measured before designing anything: `libtorrent` (the qBittorrent core) installs
  as a pure-Python wheel (2.1.1, py3.12) with zero system deps, and a public-domain magnet resolved its
  torrent metadata over the real network in ~4 s. So it ships in `requirements.txt` and the whole feature is
  in-package. `connectors/torrent/` mirrors the `connectors/video` family shape: `session.py` is the ONLY
  file that imports libtorrent (a LAZY process singleton — built on first use, never in the ASGI lifespan,
  which runs twice), `search.py` gets the magnet through `mesh_agents.serve` (free agents only, a 402 is a
  fact never paid, «nobody does this» is a spoken reason — the search itself is a network agent, not ours),
  `service.py` is the fail-safe facade whose `available()` is DERIVED from the wheel importing (V2-603 rule —
  a machine without it hides the connector, never shows-and-breaks), and `server_api.py` serves
  `/api/torrent/*`. The one hard part is streaming a file that is still DOWNLOADING: `FileResponse` stats once
  and is useless, so `stream` hand-rolls a `206` — parses `Range:`, reports `Content-Range` against the FULL
  size a `<video>` needs to seek, and streams through `session.iter_range`, which reads from DISK (a completed
  piece is checked and flushed there by default storage) after prioritizing (`set_piece_deadline`) and
  awaiting (`have_piece`) the pieces it is about to serve; sequential download + a per-file priority delivers
  the front first, so «play while it downloads» works. A chunk that never arrives raises and CLOSES the stream
  (a browser re-requests a Range better than it survives a hung socket). The `torrent` widget (`Descargas`)
  builds its `<video>` ONCE and only updates it on re-render (the V2-124/4.19 rule), showing the player only
  when `streamable` (metadata + first ~4 MB down), progress until then — its declared actions ARE the skills
  (V2-544), driven by the generic `widget_data` tool. **The FlashBrain model-tool wiring (a dedicated
  `stream_torrent` in the 5-file router core) was DEFERRED on purpose** — the V2-561 precedent: a
  self-contained feature does not also touch the sensitive, well-tested tool-routing core in the same commit;
  the agent already operates it through `widget_data` like `documento`/`archivos`. Node **5.22** (16 cases,
  three disarms verified red — the stream_url gate, the search-miss-must-not-download guard, the Range clamp);
  `make test-widgets` 15/15, connectors unit 299 green. Data lands under `widgets/_data/` (a declared
  workspace root). **NOT verified live end-to-end**: the metadata path is proven, the byte streaming of a real
  payload is not exercised in the suite (a unit test opens no session, reaches no network). Detail:
  `.meshkore/docs/modules/zaelar-torrent-addon.md`.

- **An unplayable video is swapped, not served — and the silent turn must not apologize (V2-634,
  2026-09-09)**: the operator, with LaLiga's «Video unavailable» on the card. We use the NATIVE YouTube
  IFrame embed, so embedding restrictions are per-video, set by the rights holder — the video plays on
  youtube.com and refuses every embed. The widget HAD reported it (`player_error`, one second after the
  load) and nothing consumed the report. His rule, now mechanism (`widgets/youtube/availability.py`,
  extracted paying the newborn ceiling — data.py sits at 900 exactly): a fatal code (101/150 embed
  disabled, 100 removed, 2/5 broken) puts the video on a BLOCKLIST no search or swap ever re-offers, and
  **provenance decides the rest** — a video WE resolved (query, search band, queue) is silently swapped
  for the next playable candidate (queue after pos → search band → the stored `last_query` re-resolved
  through the injected `_search_id`), while a link HE pasted gets the honest copyright message EVERY time
  («swapping what he explicitly asked for would be a different lie»). The onError report now names its
  `videoId`, so a late report for an already-replaced video never blames the successor. The card SAYS it
  (`.hb-yt-blockmsg`, via the V2-613 `ctx.t` seam, keys in both bundles, interpolated fallback) and the
  brain is told through `prompt_digest` (AVISO DEL REPRODUCTOR + the forbidden moves). **The same session
  also measured a one-hour-old V2-633 regression**: the model understood «ponme un vídeo de Ronaldinho»
  every time and called the tool every time — but with the ack gated, an acted-but-silent turn fell into
  the MUTE backstop and APOLOGIZED («se me ha ido» ×3) over turns that had worked, reading as
  not-understanding; and the context-bleed guard's correct swallows left those turns looking void. The
  backstop is gated on `_tool_handled` (hoisted above it) and a dedupe now marks the turn as handled.
  Node 4.4 (+11 cases) · 4.138 (+1 rendered) · 3.22 (+1); seven disarms red, one repeated against the
  MOVED code after the extraction. Detail: the V2-634 initiative.

- **The genesis rules govern the engine's OWN mouths — a short order runs in silence, and a spoken rule
  rules the very next turn (V2-633, 2026-09-09)**: the operator's session (6c715232) proved the style
  mechanism worked and still failed him: his rule («al recibir órdenes no responder nada») was captured and
  persisted by `set_style_directive` at 16:40:41 — and «Reproduce el vídeo» still got «Déjame ver…» +
  «Hecho.», twice, after the model had agreed. Cause: THREE mouths speak without the model and none
  consulted any rule — the fast lane's ack (V2-572, born from his own earlier opposite order), the
  never-mute backstops (the model OBEYED and said nothing; the engine injected «Hecho.» into its mouth),
  and the lead-in filler (whose `filler_kind` did not even know «reproduce» as an action verb). Now:
  `nucleo/genesis.json` ships the base rules (silent short orders; fillers "smart" — never covering a turn
  that is itself a short order), `nucleo/style_policy.py` layers per-install overrides written by the
  directive handler IN the same turn (`<workspace>/config/style.json`, mtime-cached read per use — a rule
  given by voice or chat governs the next utterance, and survives restarts; retraction restores genesis),
  and all three mouths consult it: the fast-lane ack is opt-in («confírmame las órdenes» brings it back),
  the data-op/show backstops gate on `_ack_allowed` (clarify/confirm stay never-mute — they are questions,
  not confirmations), and the filler checks `filler_allowed(kind)` at fire time. VOICE mouths only, stated
  in the module: chat keeps its text acks (an empty chat bubble looks broken; a written «Hecho.» interrupts
  nobody) — which is also why the probe's ack faces are untouched while a chat-given rule still moves the
  flags. `prompt_line()` teaches the MODEL's own mouth the same manners, only while the policy says silent.
  The missing seeds shipped too: «reproduce el video»/«dale al play»/… → youtube play (es+en, packs v5) —
  the session's exact phrase resolves in the deterministic lane now, like «pausa» always did. The ratchet
  fired twice and was paid by extracting `nucleo/flash/style_directive.py` — the WHOLE set_style_directive
  path for both channels (`handle`/`handle_probe`) plus `prompt_lines()` (wake-word + silent-orders: the
  tool's teaching and its handler in one place); wiring guards repointed to the CHANNEL (V2-555). Node
  **3.22** (15 cases, isolated workspace, two disarms red). Detail: the V2-633 initiative.

- **The video widget becomes a real player: tabs, a dashboard that carries the search, and the honest
  shelf of sources (V2-632, 2026-09-09)**: the operator's full redesign, triggered by his screenshot — the
  card opened EMPTY and small («reproduce un vídeo» opened the card before the video existed; V2-630's
  freeze pinned the footprint the missing manifest height produced). What was already built stayed the
  foundation (V2-366 queue · V2-597 account layer · V2-604 library); this pass reorganizes the SURFACE and
  the search's destination:
  · **Top TABS** (Inicio · Reproductor · Cola · Suscripciones · Listas) replace the home↔player toggle.
    `selectTab` is the ONE writer and clears the connectors screen — the V2-626 rule applied at birth
    instead of paid later (this widget's latent copy of that bug was already named in the V2-626 entry).
    A video ARRIVING on an empty card auto-jumps to Reproductor; a disarm proved the tab-close claim had
    to be measured ACROSS a re-render, not at the click (clearing pixels while `_screen` survives
    resurrects the shelf on the first SSE repaint).
  · **The SEARCH lands on the DASHBOARD, never in the queue** (`search_results` — numbered band, replaces
    the previous search; the queue only receives what he sends in): `play_result{item}` /
    `add_results{items:"1,3"|"all"}` / `clear_search` steer it, `prompt_digest()` (V2-576's seam) hands
    the numbered rows to the brain so «reproduce el tercero» resolves against what he SEES.
    `play_video(action=list)`'s whole chain updated (tool text · `video_turn` spoken face with real
    singular/plural · manifest `view:true` per V2-547's lesson) — the shared tool-catalog ceiling tripped
    at +60 chars and was paid by compacting the same description, never raised.
  · **Placeholder** on the player tab («Sin vídeo» title + the 16:9 frame kept and marked), queue rows
    with thumbnails, Suscripciones/Listas as real tabs over V2-604's data, and `follow_channel` with no
    name follows the CURRENT video's author (a required argument the sentence never fills, V2-609 class).
  · **The 🔌 SHELF** (messaging igrid language, local copy per V2-557): every video source with its truth —
    YouTube disabled naming INI-032's reason, Vimeo/Dailymotion/Twitch as shut doors from the V2-526
    catalog (`connector_shelf` composed server-side, fail-soft). A disabled box never fires a connect.
  · **Manifest sizes made honest** for the two width-only declarations the V2-630 freeze exposed:
    youtube 680×560, musica 468×540.
  · Data per the domain-stores doctrine (2026-09-09): everything in the widget's own store, ZERO rows into
    memory; the inferred channel preference is REM/heart's lane. Coordinated over the dev cluster with
    memoria-dev (heads-up + exact key inventory sent for the doctrine's Video section).
  Node **4.138** (9 rendered cases) + 4.4/4.52/4.53/4.116 files realigned to the new faces; golden
  re-recorded (40 keys); seven disarms, mutations asserted, all red after one test was hardened.
  ⚠️ Caught by SCREENSHOT, not by reading: the connmode CSS block sat BEFORE the per-tab rules and lost by
  order at equal specificity — the queue rendered underneath the shelf. Detail: the V2-632 initiative.

- **A card's size never follows its content (V2-630, 2026-09-09)**: the operator, with two screenshots of
  the same musica card at two widths — «el tamaño de los widgets debe ser fijo; si el texto no cabe, se
  acorta; el usuario decidirá si lo hace más grande o más pequeño». Mechanism: `.hb-win` has no width of its
  own (shrink-to-fit), musica declared no `manifest.size`, and the playback bar's nowrap title propagated
  its max-content width into the card — so the card's width was a function of the current song title. Fixed
  at CLASS level in the canvas: `desktop.js::_freezeSize` runs once per fresh card, right after
  `_applyPreferred`, and writes any still-auto dimension as explicit px (snapped, canvas-clamped, floored at
  the widget's `_minSize`; a minimized card and operator-set dimensions are untouched) — from then on
  content truncates or scrolls INSIDE the card, and only the operator's gestures and the canvas's own `_fit`
  change its size. Companions: musica declares `"size":{"w":468}` (deterministic first footprint — the
  freeze alone would pin whatever the current title happened to measure), and `/api/canvas/state`'s
  whitelist keeps `w`/`h` (the server fallback restore silently dropped the size half of «where he left
  it»). Node **4.137**, RENDERED with the real desktop.js and a CONTROL case proving an unfrozen card
  genuinely grows (without it the other cases measure air); two disarms red. Frontend-only: a page reload
  picks it up. Detail: the V2-630 initiative.

- **The free source CAN skip, and a narrated close is not an order (V2-631, 2026-09-09)**: the operator's
  session review (7be94951), each link verified in observability. (1) «Pasa a la siguiente canción» met
  `youtube_audio.py::next()` returning `unsupported` with a canned «Con esta fuente gratis no puedo saltar
  de canción» — spoken three times, twice right after AGREEING with him — while he skipped by hand through
  the very queue `on_ended()` already advances. `next()` now delegates to that same advance (empty queue =
  the honest refusal, naming the queue), `previous()` works off a new bounded `history` and requeues the
  current track at the front, the canned string is DELETED from both language tables, and the skip phrases
  are SEEDED in the action map (es+en) — the deterministic lane pause/resume already had. (2) The musica
  card closed itself TWICE — killing the audio, which lives inside it: `looks_like_close` matched «¿Van a
  cerrar anuncios?» (infinitive, third-person future) and «has cerrado el widget de música» (a complaint
  narrating the FIRST wrongful close) — the second one both fired the close backstop AND made
  `show_contradicts_the_order` discard the `show_widget` the model had correctly called to reopen it: one
  wrong True, three symptoms. Grammar, not intent: `_NARRATED_CLOSE_RE` STRIPS (never vetoes) participles
  after «haber»/«you've» and «va(n) a <infinitivo>» before testing — an imperative beside a narrated close
  still closes. The `action_map` was checked and NOT poisoned (zero learned rows). The ratchet fired on
  `router_guards.py` and was paid by extracting the whole close-order grammar to
  `nucleo/flash/close_guards.py` (AST-identical, re-exported). (3) The source catalog he asked for is the
  honest version: priority already existed (`music/registry._BUILTIN`: connected Spotify first,
  YouTube-audio always) — what was missing was VISIBILITY: `registry._music()` now lists youtube-audio as a
  live always-connected row, and the V2-526 shelf gains the music family (apple-music `planned` with its
  real gate; amazon-music/deezer/soundcloud/tidal/youtube-music `not-possible`, each naming why) — showing
  what we do NOT have on purpose, instead of narrating an Amazon integration that cannot exist. Nodes 5.11
  (+1 file) and the router/actionmap/music suites; six disarms red. NOT verified live (needs an engine
  restart). Detail: the V2-631 initiative.

- **The music widget brings real cover art, fast first, then enhancements (V2-629, 2026-09-09)**: the
  operator asked for a nicer design in "our line" of icons, real album/song art, and a player better than the
  competition — with a hard ordering constraint: music has to SOUND fast, art can arrive after, and whatever
  is fetched gets cached. Two speeds: (1) FREE and instant — a track played through YouTube-audio already has
  a resolved `videoId`, so `connectors/music/youtube_audio.py::_yt_thumb(id)` derives the video's own
  thumbnail URL with zero extra network call of ours; wired into every `Track(...)` and the persisted `yt`
  block. Same fix let `widgets/musica/data.py::_track_from_resolved` store what the PROVIDER resolved (real
  title/artist/art) into Recent/Top instead of the operator's raw spoken words, and `_clean_yt_title`/
  `_yt_display` strip upload boilerplate ("(Official Video)"…) and split an explicit "Artist - Title"
  delimiter for DISPLAY only — the stored title never changes. (2) SLOW and CACHED — a track never actually
  played (typed into a list, a legacy row) gets a lazy, once-per-song iTunes Search API lookup
  (`_enrich_art`/`_itunes_lookup`, free, no key), cached forever on a hit / 14 days on a miss, backfilling
  every occurrence of that song across Recent/Top/every playlist. The widget asks for it AFTER the row is
  already painted with its fallback (`widget.js::maybeEnrich`, deduped per page life, defensively tolerant of
  a `ctx.action` that returns anything other than a Promise) — never on the play path. `art_cache` rides
  along in `_compose` (which `_persist` also uses to write the disk file whole) but is stripped by
  `view_data()` before it crosses the wire, so the cache survives while the payload stays light. Every emoji
  control (⏮⏸▶⏭🔉🔊♥) became an inline SVG matching the app shell's own visual language (duplicated locally —
  `widget.js` cannot import app-shell code, V2-557's rule); the heart is a STATE indicator now
  (`data.fav_current`, filled when the playing track is already saved) and a dead cover URL degrades to the
  placeholder icon via `img.onerror` instead of a broken-image glyph.
  **A real bug the render tests caught, not reading**: `ICON_PLAY`/`ICON_PAUSE` were built as the outline
  base (`fill="none"`) plus an APPENDED `fill="currentColor"` on the same tag — the HTML parser keeps the
  FIRST duplicate attribute, so `fill` stayed `"none"` and the "solid" icons rendered as hairline outlines;
  invisible in a screenshot at icon size, caught only by asserting the resolved attribute. Fixed with a
  second, clean attribute set for solid icons, never an override on top of the outline one. Node 4.3
  (+1 file, 10 RENDERED cases + 4 connector-level), seven disarms, each mutation verified red. Two
  pre-existing tests needed fixing, not weakening: one asserted an empty call list that the new (correct)
  background enrichment now legitimately populates (filtered to exclude `enrich_art`); another's mock
  `ctx.action` returns `undefined`, so `maybeEnrich` was made defensive against any shape, matching the
  `try{...}catch(_){}` caution the same file already takes for `ended`. `make test-widgets` 14/14 (golden
  re-recorded — `fav_current` is a new key). **Coordination, per the operator's explicit split**: a message
  went to `memoria-dev` over the MeshKore dev cluster describing this build and asking about the in-progress
  memory upgrade, to align a FUTURE listening-preference ingestion path — no memory code was touched here;
  that is memory's call, briefed separately. Detail: the V2-629 initiative.

- **⏻ ON took two presses: two right fixes from the same day, racing (V2-627, 2026-09-09)**: the operator
  reported that the first press on a stopped agent «se sombrea un poco pero no arranca». His own observability
  had it — `orb:power on`, `agent:state starting`, `agent:state off`, all in the same second, and a SECOND
  `orb:power on` five seconds later (two consecutive `on` is the proof that `powerOff` had gone back to true).
  Cause: the 2026-08-31 pair. Orb.js was sequenced server-first (`runStart().then(session.start)`), and
  main.js gained an effect that revives the voice when `powerOff` drops from outside this tab — but
  `setPowerOff(false)` runs SYNCHRONOUSLY inside the click, so that effect started a session before
  `POST /api/run/start` was even sent; its ⏻ gate asked the server, was told STOPPED (true for a few more
  ms), aborted and set `powerOff` back to true, and the click's own `start()` then found `starting` still
  true and no-opped. The ordering fix was bypassed, not broken. Fix: a HANDOFF (`store.powerOnAt`) — while a
  ⏻ ON is in flight the click owns the startup and no other road may open a session; the guard lives INSIDE
  `ensureVoice`, so all three of its roads (boot, `pointerdown`, the effect) are covered at once, and the
  gate treats an in-flight ⏻ ON as history too. A TIMESTAMP with a 15 s expiry, never a boolean: a reply that
  never comes must not wedge the voice shut. Counterweight (a regression the fix could have introduced): EVERY
  press drops the handoff before branching and only ON takes it again — ON then OFF inside the window would
  otherwise have let the ON's still-scheduled `then(...)` bring the voice up over an agent just stopped. Two observability changes ship with it — every ⏻ press names
  itself and the state it was pressed in (`[zaelar] ⏻ ON — agent was off`, his request), and **the gate's
  abort stopped being silent** (`console.warn` + `voice:refused` on the server timeline): it is a legitimate
  outcome, but an invisible decision is the expensive kind. Node **4.136** — the handoff state machine is
  exercised by loading the REAL `core/store.js` in Chromium (it depends only on `reactive.js` and
  `localStorage`), the wiring is structural like its neighbour 4.91; six disarms red. Detail: the V2-627
  initiative.

- **Choosing a channel is ONE state transition, not a filter assignment (V2-626, 2026-09-09)**: the operator
  asked for his mail; the email dot lit and the WhatsApp connector screen stayed underneath it. `render()`
  applied a pushed view by assigning `_platFilter` alone, while the body is gated on
  `showChannels = !!_screen || …`, which returns EARLY — so the lens never rendered. The click path had no
  such bug: V2-610 had taught it, INLINE, to clear `_screen`/`_openMail`/`_confirmDisconnect`. That is the
  whole lesson — the behaviour lived in the CALLER, so each new caller had to remember it and the voice path
  never did. Now `selectPlatform(pl)` is the ONLY writer of `_platFilter` and owns the whole transition; the
  header dot, the title and the brain's pushed view all go through it. `connect_focus` resolves AFTER the
  pushed view on purpose: when one payload carries both, the SPECIFIC request (open this connector) survives.
  His framing is the rule to keep: *«toda esa mecánica del widget es mecánica… gestiones de estados. Por lo
  tanto, no puede ser que eso falle»* — and a rule every caller has to remember is not a rule.
  Node **4.135**, RENDERED (source cannot see it: the assignment is identical either way, only the screen on
  top differs), five disarms red. Two of them were green at first and the TEST was wrong, not the code: an
  open mail only yields visibly when the SAME channel is re-asked (otherwise the platform guard hides it),
  and a pending disconnect confirmation only renders back inside that connector's own screen.
  The class, checked in the siblings: `contactos` already clears its detail; `agenda` has no blocking screen;
  **`youtube` has the same latent defect** (`.hb-yt-connmode` hides the player/list/home, `_screen` is
  module-lived, nothing clears it) — unreachable today because INI-032 leaves `accounts_enabled` false, and
  named in the V2-626 initiative so reactivating accounts carries it. Detail: the V2-626 initiative.

- **Messaging pro: fetch on demand, per-platform view criteria, `peek` for analysis, and the autoresponder
  (V2-624, 2026-09-09)**: the operator's directive after driving the widget live (sid `952fcf2f`) and
  hitting two honest refusals — «todas las conversaciones con actividad en las últimas 72 horas» had no
  criterion anywhere, and «¿puedes ir al conector y chupar más mensajes?» had no door. His governing
  constraint: strictly incremental — «respeta lo que ya funciona y añade lo nuevo… no alterar los circuitos
  de memoria». Detail: the V2-624 initiative. Four additive capabilities, zero rewrites:
  - **`fetch_now {platform, since_hours}`** — a platform-wide pull through the connector, the same
    queue→bus round-trip shape as `load_more` (`msg.fetch` topic, per-platform `FetchInbox`). Telegram
    walks its own dialogs (a stale one is SKIPPED, never a reason to stop — Telegram floats PINNED dialogs
    to the head of the list, and an early exit on the first stale one answered 0 over a live account whose
    newest message was 12 minutes old; the walk is bounded by a 60-dialog cap instead, `3627978`. Broadcast
    channels excluded — a feed is not a conversation); email searches IMAP `SINCE` (day-granular — the service trims to the
    hour by each message's own timestamp). Everything lands in the CONVERSATIONS as read scrollback via
    the existing `connector.history` seam, never in triage: pulling the past must not interrupt anybody.
    **WhatsApp refuses honestly, naming what IS possible** (realtime + per-chat `load_more`) — its bridge
    has no bulk door, and offering one that cannot work is worse. `publish_history` gained optional
    `name`/`isGroup` so a thread BORN from a pull is labeled correctly (a group named after whichever
    member spoke first reads as a different conversation); a name a live message already wrote wins.
  - **`show_view {window_h}`** — the per-platform view CRITERION, persisted until changed (his words:
    criteria are per-platform state, not per-utterance; a plain `show_view` keeps it, `0` clears it). With
    one set, that platform's lens lists conversations from the THREAD store with movement in the window —
    «movimiento» includes what he read and what he sent — under a VISIBLE bar (label + ✕ + a «traer del
    conector» button exactly where the transport can serve it). Without one, the lens stays byte-for-byte
    the classic pending view. Activity rows carry no `n` on purpose (they open by identity,
    platform+chatId — a second numbering space colliding with the chat list's would open wrong chats).
  - **`peek {name|limit}`** — a conversation handed WHOLE to the brain (≤40 msgs, per-body and total
    budget, newest win), so the model summarizes/extracts IN the turn: «dame lo relevante del grupo del
    viaje», «la esencia de esos correos». Read-only by construction: the thread store IS the segregated
    data his storage doctrine describes; analysis is a READ of it, never an index into memory — the memory
    circuits (`kind='msg'` short-level ingestion, unchanged) were deliberately not touched.
  - **The autoresponder** — the «Phase 4» `connectors/whatsapp/client.py` has named since INI-014, now
    with its go-ahead. `set_autoresponder {platform|all, text, hours?}` (confirm-gated: it speaks for
    him), decision whole in `autorespond.py` (zero-import, the policy.py placement): NEVER a group, email
    only when `dirigido_a_mi`, hours window with wrap-around («22:00-08:00»), once per chat per 24 h
    against a DURABLE ledger (V2-607: an in-memory guard cannot dedupe a durable source). The send rides
    the EXISTING `msg.reply` seam — each connector's tested send path, echoed into the thread by the
    existing outbound-capture seams; the original item is NOT marked read: an automatic «estoy fuera» does
    not deal with the message. State is VISIBLE (settings panel chip + a brief line for the brain — an
    undeclared capability is one the model narrates, V2-540) and **survives a Reset** (`blank()` preserves
    `autoresponder`/`lens_criteria`: config is not «messages and queues»).
  - The architecture ratchet fired on `data.py` (1184 > 900) and was paid by EXTRACTING `views.py` (the
    read side: name resolution, thread/activity views, peek, previews, `_group_chats`) — one-directional
    seam, lazy back-imports, 892/313 after. ⚠️ One disarm came back GREEN on its first anchor: the
    mutation hit the `answer_action` PREVIEW instead of the `apply_action` branch — the same code shape
    exists twice (preview computes what the owner will persist), so a disarm must anchor on something
    unique to the function it claims to disarm (the V2-571 lesson, paid again).
  - Nodes **4.134** (4 files: criteria/fetch/peek/autoresponder + the RENDERED activity lens) and
    **5.20** (the two connector fetch drains, faked at the transport). Six disarms red. Sweeps:
    mensajería+connectors 445, infrastructure 648, `make test-widgets` 14/14.

- **A redundant media label, and a thread/mail screen stops stacking the dashboard header above its own
  (V2-622, 2026-09-08)**: two operator reports in the same message. (1) A voice-note bubble printed "🎵
  Audio" as a text line right above its own player — *"no hace falta poner 'audio', ya se ve no?"* (2) On a
  hard page refresh with a thread open, the FULL dashboard header (inbox count, every platform dot,
  connectors/settings/clear) rendered stacked above the thread's own header — *"ojo a como veo el widget al
  refrescar page."*
  - **`isBareMediaLabel(body)`** (new): a message whose body is empty or the literal `[<type> received]`
    placeholder carries no REAL caption — only what `displayBody()` invented to have something to print. The
    three call sites that render BOTH a text line and a `mediaBlock()` for the same item (`richList`,
    `messageRow`, `mailDetail`) now skip the text line once the real media block renders and the body is
    bare. A genuine caption typed alongside media is untouched — the placeholder regex requires the ENTIRE
    body to match, so a real sentence never gets swallowed.
  - **An open thread/mail is its own screen now, checked BEFORE the dashboard header is even built** — not
    after, with an early return. Both screens already carry a full header of their own (platform chip +
    contact/subject + "← Volver", since V2-620); the dashboard header sitting above it was never actually
    reachable from inside a thread (only `ctx.action("close")` clears `active_chat`, and none of the header's
    controls call it), so it was dead chrome, not a second control surface. Same precedence order as before
    (`showChannels` > `activeChat` > `openMail` > the list shapes) — only WHERE the check runs moved.
  - **Deliberately left alone**: the connectors/wizard screen has the identical stacking (its own
    `.chanhead` under the dashboard `hd`) but was not what was reported, and touching it risks the
    already-tested V2-561 wizard flow for no reported gain.
  - Node **4.132** (1 file, 2 new + 1 rewritten case). Two disarms verified red (the label-suppression guard,
    the early-return header-skip). `make test-widgets` stays green 14/14; full sweep
    `tests/browser/{unit,e2e}/mensajeria/`: 162 passed.
  - **Not yet verified live** — needs an engine restart, plus a reload for any already-open tab.

- **The system bar rotates to the BOTTOM, the orb swaps into its centre, and 🧠 moves upstairs (V2-623,
  2026-09-08)**: the operator's redesign — «move the left bar to bottom. orbe goes to center, left and right
  side contains the open widgets and the other icons»; «quita el icono de la memoria del orbe. ponlo arriba
  a la derecha»; and the follow-up that settled ⏻: «no sé si poner el icono de arrancar y parar en el centro
  del orbe» → YES, the orb IS the switch in bar mode — V2-124's mobile-dock pattern, now shared by both
  shells. `#wrail` = horizontal bottom band (`--wrail-h` replaces `--wrail-w`): chips left · orb centre ·
  tools right, version badge at the bar's left end, feedback launcher floated above it, the eye orb's
  resting place raised over the band. `store.orbDock` (persisted) + Orb.js's `applyOrbDock` REPARENT the one
  `#orb` canvas into the bar's slot and move the lid controls by `data-ctl` handles — mic·spk·cap | orb |
  chat·bot·swap, 3|3, buttons MOVED never rebuilt so handlers travel; "eye" re-appends all seven in
  canonical order (⏻ keeps the apex). The slot is a BUTTON whose ⏻ face and canvas alternate by VISIBILITY
  (the 4.19 lesson) and whose click forwards to the real `[data-ctl="pwr"]` — one owner of the power logic.
  Desktop: `railBand()` reserves the BOTTOM in `canvas()`, `minX()` is a 0 shim; V2-619's outside-the-rail
  grip offset retired WITH its trigger (the east grip returns to the wall's edge). `#activity` and the flash
  label survive bar mode on purpose — a transient notice must not die with the eye. Node **4.133** (7
  rendered cases), five disarms asserted and red (the bottom-band one caught by the mural's maximize check);
  the mural's five left-rail checks and V2-619's grip test rewritten to the new geometry; 130 widget-e2e +
  mural + infrastructure green. ⚠️ This batch first took the number V2-622 and the CONCURRENT session
  claimed it mid-build — renumbered at closure, and the blind rename clobbered ONE foreign citation in the
  testmap before being caught: reserve the number by creating the file when you TAKE it, and rename by hand.
  **Fix 2026-09-09**: the first `applyOrbDock` runs before the orb is mounted, `byCtl` queried only
  `document`, and `Element.append(null)` doesn't throw — it prints the LITERAL text "null" (seven of them
  beside the orb, found via an operator screenshot after two suites had passed). `byCtl` now falls back to
  the detached `wrapEl` and every lid move goes through a null-filtering `ctls()`; the swap test measures
  stray text in all four states (its 8th case), red before the fix.
  Open, named: captions hidden in bar mode; the slot's forwarding asserted structurally, not by a live
  power cycle.

- **The chat header names its tab, wide tabs keep their icons, and the ⧉ toggles BOTH ways (V2-621,
  2026-09-08)**: the operator's follow-up on V2-619's icon tabs — «nombre tab (fix min width) | 5 icons |
  2 icons at right», the same header in the floating box (whose lone × offered no way to BECOME a column),
  and «si se amplían los anchos se ve el icon y la desc al lado». Header now: `.cw-tabname` (the active
  tab's name, reactive, FIXED min-width so the icon strip holds still, hidden whenever the wall is not
  `cw-narrow`) | five icon tabs (wide mode keeps the icon BESIDE the label — the old `svg{display:none}`
  deleted, threshold 580→660 to pay for the ~24px each icon adds) | the ⧉ **mode toggle, visible in both
  shapes**: docked → float (unchanged), floating → `applyDock` on the last dock side; its face (⧉/◫ +
  title) is reactive through an `isDocked` SIGNAL written only by `setReserve` — `dockSide` is a plain
  variable a reactive binding would read exactly once, the V2-608 lesson applied instead of re-paid. New
  `chat.dock` key both bundles. Chat-wall suite grew to 17 (standing-name shown/retired, wide icon+label,
  box shows both buttons and the ⧉ docks it back); three disarms, mutations asserted, all red; version-bar,
  canvas-refit and the mural green after.

- **A screen change resets the scroller, "Volver" becomes a real button, each platform gets its own color,
  and a voice note can actually be dragged (V2-620, 2026-09-08)**: the operator's follow-up screenshot on
  V2-618 — opening a WhatsApp thread while the chat list behind it sat scrolled down left the thread's own
  "← Volver · contact" header rendered past the visible viewport on first paint (*"se ha metido como por
  debajo el header del otro"*), plus three redesign asks in the same message.
  - **The bug: `ctx.top()` existed and was never called, on ANY of this widget's screen swaps.** Its own
    comment already says "opening a record, changing tabs, returning to the list" — a chat list left
    scrolled down handed the fresh thread's shorter subtree a stale `scrollTop`, so its own header rendered
    scrolled past the viewport. His own scroll gesture only "fixed" it by forcing a reflow that happened to
    reveal it. Added to every real transition (open/close thread, open/close mail detail, the connectors
    toggle, a platform-lens click, a wizard open/step, the dashboard title) — verified against a SPY `ctx.top`
    in a rendered test, not a source read.
  - **"Volver" moves to the far right as a real bordered chip**, never a bare underlined link — the SAME
    visual language `.chanhead`'s own back link already used elsewhere in this widget, applied consistently
    instead of two languages for one affordance.
  - **Each platform keeps its own color now.** `PLAT.telegram.bg` and `PLAT.email.bg` both silently shared
    the SAME generic accent blue as everything else — indistinguishable at a glance, exactly what he
    noticed. Real hex for each (Telegram `#2AABEE`, email `#D8452D`, WhatsApp kept its `#16B8A6`) fixed the
    header dots and every chip avatar for free (`PLAT.bg` was already their one source), and a new
    `.thread.plat-<id>` class extends it to the outgoing bubble, the compose send button and its textarea's
    focus border. Literal hex, not a shared global theme var — deliberately never touching
    `frontend/app/core/palette.css`, mid-redesign in the same shared tree, uncommitted, the same day.
  - **The audio player actually scrubs now.** Native `<audio controls>` replaced by a custom play button +
    fixed-count (28) bar waveform + time label, still driven by the same hidden `<audio>` element.
    **The bars are decorative, not real amplitude — said plainly**: a real waveform needs the file's raw
    samples via `decodeAudioData`, which needs `fetch()`/`XMLHttpRequest` — both BANNED sinks in `widget.js`
    on purpose (the "no network from the client" boundary V2-557 drew, checked before writing a line). The
    `<audio>` element loads its own `src` through the browser's OWN media pipeline — the one legitimate way
    media reaches this widget. **Fixed width regardless of duration is structural, not tuned**: the bar
    COUNT is fixed, never derived from length, so a 1-minute and a 2-hour clip both render the same total
    width — his exact worry ("un audio de dos horas no va a caber el ancho") cannot happen by construction.
  - ⚠️ **A real defect, found only by driving actual playback**: the first test version mocked the asset
    route as a flat body-echo with no `Range`/`206` support — Chromium reported the clip's `seekable` as
    `[[0,0]]` FOREVER, even fully downloaded, and silently discarded every `currentTime =` assignment. The
    REAL route (`widgets/server_api.py`, Starlette's `FileResponse`) answers `Range:` with `206` on its own —
    the fix was in the TEST (a Range-aware mock matching what `FileResponse` actually does), not the product.
  - Node **4.131** (2 new files + 1 updated), three disarms verified red. Full sweep of
    `tests/browser/{unit,e2e}/mensajeria/`: 161 passed.
  - **Deliberately not done**: a true amplitude-accurate waveform (needs server-side peak extraction at
    ingest time — its own, larger initiative); per-platform theming anywhere outside the open thread itself.

- **Messaging reads like a chat, and the card chrome stops looking like two headers (V2-618, 2026-09-08)**:
  two operator reports in the same session. (1) A 1:1 WhatsApp thread repeated the contact's name on EVERY
  bubble, and his own replies had no left/right shape (*"solo necesito ver a la izquierda los mensajes de
  [él] y a la derecha los míos"*). (2) The card chrome: *"me disgusta profundamente el que parece que hay dos
  headers"* — a redundant grip button, a centered outer title, and the widget's own header undifferentiated
  from it.
  - **Bubbles, sender name shown only in a GROUP.** The 1:1 header already names the other party once, so
    repeating it per bubble was pure noise. The group flag had nowhere durable to live: `thread.py::_norm`
    never kept `isGroup` on a stored message, and `data.py` only re-attached it from a still-UNREAD item — a
    mostly-read group thread would silently look 1:1. Fixed by persisting `isGroup` on the **thread itself**
    (`thread.py::append`, set once, never cleared), never a per-message copy.
  - **The outbound-capture path was audited whole, not blindly patched.** His own reply not appearing sent me
    through the entire chain — the bridge already forwards `fromMe` messages, the connector already publishes
    them, the owner already writes them to the thread and clears pending items. Every seam checked out. The
    live store held **zero outbound messages, ever, across every thread** — consistent with either a real,
    narrow bug the source can't show or this path genuinely never having been exercised by an independent
    live reply since it shipped (V2-546's own verification used a scripted case). Neither draining the
    bridge's queue (destructive — steals the connector's own next poll) nor sending a real WhatsApp message as
    a test (externally visible, hard to reverse, against a real contact) were safe ways to force a
    reproduction. **Shipped instead**: two INFO log lines, one at each end of the same trace (the connector
    confirming the bridge handed over the message, the owner confirming it reached the store) — both ends
    were silent on success before. The next real occurrence is one grep away from diagnosable.
  - **Confirmed NOT the problem**: the SSE push mechanism. An open card already re-renders live on a backend
    store change (`sse.js`'s `data` handler → `desktop.refreshData`) — "más activo" was never a transport gap;
    if a message never appears, it never reached the store, which the new logging will now show.
  - **The redundant grip, retired.** `.hb-head` has been a full drag handle since V2-608 F6 — the code's own
    comment already said so — so the separate nine-dot `.hb-grip` button had nothing left to do. Removed
    system-wide (`desktop.js`): the button, its CSS, `NINE_DOTS`, its `DRAG_HANDLES` entry, every
    cinema/fullscreen/loading selector hiding it, the orphaned `desktop.move_tooltip` i18n key. `.hb-head`
    defaults to left-aligned now (previously centered, with a separate `.live` override that is simply the
    default everywhere now) — generic chrome, every widget's outer bar changes.
  - **The widget's own header, renamed and regrouped.** Inner title "Mensajería" (the catalog name, already
    said once by the outer bar) → **"Mensajes"**, the operator's own suggestion for what the screen actually
    is. The platform-icon row and the connectors/settings cluster are now two visually distinct groups
    (`.hdactions`, its own divider) instead of four icons sharing one gap.
  - Node **4.129** (2 new files, 7 cases). Two disarms verified red (thread-level `isGroup` persistence, the
    name-suppression rule). Full sweep across `tests/browser/`, `tests/connectors/unit/messaging/`, the
    roadmap/CLAUDE.md ratchets, and `make test-widgets` (14/14) all green.
  - **Deliberately NOT done**: the outbound-capture bug is instrumented, not fixed — no code path was found
    broken, and confirming or fixing it needs a real occurrence with the new logging live, which needs the
    operator's own phone. No timestamp dividers, read-receipt ticks, or avatars were asked for either.

- **A widget's root actually uses the width of the card it is given (V2-615, 2026-09-08)**: the operator,
  looking at mensajería's email detail — a long tracking URL wrapping across 4-5 lines while the 900px card
  around it sat mostly empty. *"Para este y TODOS los widgets deben ser auto-escalables."*
  - **Nine of fourteen system widgets** (`mensajeria`, `agenda`, `contactos`, `musica`, `clock`, `timer`,
    `search`, `imagenes`, `navegador`) hardcoded their root at `width:min(<N>px,<M>vw)` — a desktop-era cap
    `widgets/AGENTS.md` itself already half-retracted for mobile (V2-574) but never actually swept from
    desktop. `frontend/app/widgets/desktop.js` mounts a widget's root directly into a fully fluid,
    drag-resizable card, so the cap was 100% the widget's own CSS refusing space the operator handed it. Fixed
    to `width:100%;box-sizing:border-box` — the pattern `youtube`/`results`/`documento` already used.
  - **A second occurrence of the SAME pattern, different syntax, found only by RENDERING**: `navegador`'s
    per-task mini-browser card (`.hb-navt`, a SECOND root class) carried `width:560px;max-width:92vw` — a
    grep for the `min()` idiom alone would have missed it entirely.
  - **Taught forward**: `widgets/AGENTS.md` and `widgets/generator.py::_CONTRACT` both gained an explicit rule
    naming the root by its exact contract clause (`el.className` in `render(el,...)`), not just an implied
    "write it fluid." A new static gate (`widgets/validator.py`, sibling of V2-574's `min-width>360px` check)
    rejects both shapes going forward, threshold chosen by measuring the whole catalog first (every legitimate
    small element ≤320px, every real cap 440-920px).
  - ⚠️ **A false positive found before shipping**: the fix's own explanatory CSS comments (documenting the OLD
    capped value) contain the literal banned pattern as prose — the gate's first version scanned comments
    too, so the fix commit tripped its own rule. Fixed by stripping `/* ... */` before either width check runs.
  - ⚠️ **Two bugs in the new TEST harness itself, both caught before trusting it**: an `#id` selector on the
    mount point out-specificities any class rule the widget declares (the test could never fail regardless of
    the widget's CSS — the card's size now lives on a separate wrapper); and measuring
    `host.firstElementChild` (copied from the mobile phone-render script's DOM shape) instead of `host` itself
    picked up a shrink-to-fit flex ITEM's width on `clock`/`timer` (`align-items:center`) instead of the fluid
    root around it.
  - Node **4.128** (2 new files, content-independent by design — a widget's root class is set before any
    data-dependent branch, so even an EMPTY state exercises the rule). `make test-widgets` green 14/14 before
    AND after. Two disarms verified red. Full per-widget suites + the V2-574 phone-render script all green —
    no mobile regression from dropping the `vw` clamp term.
  - **Verified live** on `3.26+7c41646`: the engine restarted onto this build and the served
    `widgets/mensajeria/widget.js` carries `width:100%;box-sizing:border-box` on `.hb-msg`. An already-open
    browser tab needs a reload to pick up the new ES module (cached per page load, same as any widget update).

- **A Reset does not leave a CONNECTED mailbox mute (V2-614, 2026-09-08)**: the operator's screenshot — the
  mensajería widget open on "Nada que atender ahora ✓" right after asking to see his Gmail messages, and his
  framing that Reset must never disconnect a connector. Measured live before touching anything: Gmail **was**
  connected (`config/connectors.json`, `state.json` both said so) with **1081 real unread messages** — his
  fear (Reset disconnects the connector) was false, and the real failure is narrower and easier to miss.
  - **The bug: connected, polling, and permanently mute.** `connectors/email/service.py`'s `_seen`/`_published`
    (populated once at connect by `seed_from_mailbox`, V2-606, and again on every real delivery) are cleared
    ONLY by a full `stop()`. Reset (`widgets/reset.py` → `mensajeria/data.py::blank()`) wipes the widget's
    `items` AND its durable `taken` ledger (V2-607) — but that is WIDGET-side, and never touches a
    connector's own process state. So a message the connector already handed over once stays "already
    delivered" forever from ITS point of view, even after Reset erases every trace of it from the widget:
    `fetch_new(seen=_seen, ...)` skips it on every future poll. Measured: `taken` held zero `email:*` entries
    at all — consistent with an earlier backfill delivered once, then orphaned by a Reset.
  - **`reseed()`** (new) releases the most recent `BACKFILL`-sized (=30) currently-unread slice from
    `_seen`/`_published` — the SAME shape a fresh connect already produces (V2-606), so this cannot flood the
    widget with the whole backlog at once. `connectors/messaging/reseed.py::reseed_all()` fans out to every
    connector that has one (today: only email); `nucleo/reset.py::reset_all()` fires it fire-and-forget,
    wrapped in its own try/except, ONLY when mensajería actually had a store to blank.
  - **WhatsApp/Telegram checked and deliberately NOT touched**: both are live-push, drain-once architectures
    (a bridge queue drained server-side, a Telethon event fired once) with no durable "still unread on the
    server" reservoir to re-poll — clearing their dedup sets would be a no-op, since the message is gone from
    the transport, not merely masked by a Python set. Their own version of this problem (a Reset losing an
    undelivered message with no recovery path) is real and harder, and stays open, not silently forgotten.
  - **A second, separate cause in the same incident, NOT fixed here**: the model's tool call that turn was a
    bare `show_widget(mensajeria)`, never the second `widget_data(show_view, {platform:"email"})` call the
    manifest already declares and documents — a live routing/model-reasoning gap on one turn, not a missing
    mechanism.
  - **The dashboard default was checked and deliberately left alone**: the operator's own follow-up — for
    direct (non-group) chats, "unread" and "directed at me" are nearly the same set, so V2-607's `highlight:
    "direct"` default already covers most of what he described; not worth reopening yesterday's decision.
  - Node **5.19** (12 cases across three files), full regression sweep of the touched area green (154 passed).
  - **NOT verified live** — needs an engine restart. First check: with the real 1081-unread backlog still
    orphaned, press Reset and confirm a fresh backlog lands on the next poll tick with no manual restart.

- **The widget layer gets its i18n seam — `ctx.t`/`ctx.lang`, and two pilots prove it (V2-613,
  2026-09-07)**: closes the gap V2-603 named ("no `t()` seam exists in the widget layer at all") with the
  operator's own scope split — *"a user-customized widget is fine, it's made after the account already has a
  language; a SYSTEM widget has to adapt during the agent's initialization."*
  - **Two new `ctx` members, not a new import**: a widget cannot import `frontend/app/core/i18n.js` directly
    (it would break every bare-`http.server` render-test harness and couple every widget to an internal
    frontend path) — so `ctx.t(key, params?)` (a synchronous, in-memory lookup, passed straight through from
    the host's own `t()`) and `ctx.lang` (a GETTER, the raw active code) join `action`/`close`/`top`/`running`
    on BOTH hosts (`desktop.js` and the mobile `Deck.js`), with a new check in
    `test_mobile_host_contract.mjs` pinning that they stay declared on both — the exact "works on one host,
    silently no-ops on the phone" class that file already names for `scroll`.
  - **`t` for a custom string, `lang` for a locale SHAPE.** `clock` is the case `t()` cannot solve: English and
    Spanish don't just use different day/month WORDS, they put them in a different ORDER ("January 5, 2026" vs
    "5 de enero de 2026") — no template of translated words expresses that, so the two hardcoded Spanish
    `DAYS`/`MONTHS` arrays were deleted outright in favor of `Intl.DateTimeFormat(ctx.lang, {...})`. Verified
    live against a THIRD language this repo has never shipped a preset for (French: "Lundi | 7 septembre
    2026", correct order, zero bundle keys) — confirming the delegation genuinely generalizes past en/es.
    `timer` is the `ctx.t` pilot: ten literal Spanish strings moved to `widgets.timer.*` keys in both bundles —
    and its own dictated label ("pasta al dente") stays UNTRANSLATED on purpose, because product data typed by
    a person is not UI chrome.
  - **The re-render gap, closed.** A widget's `render()` only re-ran on ITS OWN data changing (SSE
    `widget/data`) — nothing re-invoked it on a LANGUAGE change, so a card left open across a switch showed
    stale chrome indefinitely. Both hosts now cache the widget's last-rendered data and gained `relanguage()`,
    fired from `createEffect(() => { t(""); host.relanguage(); })` in both `main.js` files — calling `t()`
    with a throwaway key is the whole mechanism: it unconditionally reads BOTH the language signal and the
    bundle-content signal before doing anything else, so this one line subscribes to exactly what should
    trigger a repaint, with no second dependency list to drift from `i18n.js`'s own internals. Safe by the
    EXISTING contract, not a new one: `widgets/AGENTS.md`'s "no polling" section already requires `render()`
    to be safe to call repeatedly with fresh data — this calls it repeatedly with the SAME data.
  - **The keys are added, never a bundle system**: widget strings live in the SAME `i18n/bundles/en.json`+
    `es.json` as everything else, under `widgets.<id>.*` — reuses the entire generate/parity/cache-version
    machinery for free. `MANIFEST_VERSION` 4→5.
  - **Taught forward**: `widgets/generator.py::_CONTRACT` (injected into every generation/modification prompt)
    and `widgets/AGENTS.md` now document both members as OPTIONAL and scoped to a SHIPPED widget — a one-off
    widget generated for this operator, after their language is known, needs neither.
  - Nodes 4.11 (+1 file: `test_widget_keys.py`, the widget-catalog sibling of the mobile shell's own
    "every `t()` key exists in both bundles" ratchet, plus its `t(...) || fallback` dead-code guard) and
    **4.127** (the two pilots, 11 RENDERED cases). Disarms verified red: the default-label fallback, the
    fallback-pattern guard, and the clock's `ctx.lang` wiring.
  - ⚠️ **The full regression sweep found a REAL breakage this caused, before it shipped**: the new `store.js`
    import 404'd inside `test_the_canvas_refits_when_the_chat_takes_a_column.py`'s route-mocked page (no static
    server behind it), whose hand-rolled import-stubber only knew about `desktop.js`'s FIRST import — 13 tests
    timed out at 30s each with nothing pointing at i18n. Isolated by stashing just the `desktop.js` edit and
    re-running (7s, all green) to confirm the cause before touching anything. Fixed by generalizing the stub
    and adding a self-check that fails in under a second, by name, if any import is ever left unstubbed again.
  - **VERIFIED LIVE end-to-end on the real engine (`3.26+00c62ee`)**: opened `timer` on the live canvas
    (Spanish, "TEMPORIZADOR"), called the SAME `POST /api/i18n/choose/{code}` the ⚙ panel uses to switch to
    English — the SAME open card, no reload, read "TIMER" — then switched back and it read "TEMPORIZADOR"
    again, restoring the operator's actual setting. Zero page errors.
  - **Deliberately not done**: migrating the other twelve system widgets (bounded, mechanical, per-widget
    follow-up — the mechanism and the ratchet are what make each one small); translating PRODUCT DATA inside a
    widget (message content, a dictated label) stays exactly as untouched as the language rules already
    require.

- **Chrome polish on the new skin: the composer writes, the tabs adapt, the rail never hides, and ONE grip
  moves the whole left assembly (V2-619, 2026-09-08)**: the operator's batch right after approving V2-617,
  six tasks over three components. **ChatWall**: composer at rows:3 + min-height + margins off the floor;
  each tab is icon+label and the wall's own ResizeObserver flips to ICON tabs below 580px — a clipped
  «Conect» never happens. ⚠️ The narrow flag is a SIGNAL read inside the class binding, never a classList
  write — the reactive binding rebuilds the whole className and wiped the imperative class: the V2-608
  dock-class trap, paid a THIRD time in the same file, caught by the rendered test before shipping.
  **WidgetRail**: never hides (empty canvas = empty chips + disabled tools) and never folds — the
  fold-to-a-sliver is deleted whole and the chevron toggles the CHAT COLUMN (`store.chatOpen`, reactive so
  the arrow always says what a click does); width is the `--wrail-w` token. **One grip**: the rail's width
  is FIXED, so the docked column's east strip sits just OUTSIDE the rail's edge (`-1*var(--wrail-w)-8px`,
  full height — its old `top:54px` dodge is obsolete out there) and the docked wall stops clipping
  overflow; dragging it resizes the chat while the rail travels with `#desk`: «arrastro todo».
  **FeedbackWidget**: one header band (title · underline tabs · ×), email on top, a body-size clearly-boxed
  textarea («Escribe aquí tu feedback…»), the checkbox without its explainer paragraph, a full-width send
  that SAYS «Enviar mi feedback», and the launcher drops the last pre-V2-617 gradient for the solid accent.
  Tests ride the mapped suites (chat-wall +3 · version-bar rewritten: a STALE `wrail.folded` key must not
  resurrect the fold, and the rail shows on an EMPTY canvas · mural +6, feedback layout rendered); six
  disarms, mutations asserted, all red. ⚠️ The mural's stacking check went red on a 1px COINCIDENCE, not a
  defect: V2-617's scale grew the orb cluster ~4px, its left edge landed exactly on column 1's tile
  boundary, and placement's touch-counts-as-overlap (correct, conservative) blocked the column — diagnosed
  by probing `_obstacles()` live after the first theory died against the measurement; the harness viewport
  moved off the boundary (1440×900). ⚠️ A sweep also showed 19 transient reds from another session
  mid-WRITE on mensajería's widget.js — non-reproducible, its 181 green on re-run.

- **The skin is DATA: design profiles in ⚙ Apariencia, custom knobs, and the graphite default (V2-617,
  2026-09-08)**: the operator's direction after approving the visual pitch — not one theme but a SYSTEM:
  selectable profiles where the LLM config lives, everything customizable (accent, type size, typeface),
  applied INTEGRALLY («no lo apliques en unas cajitas sí, en otras no») with user widgets adopting it by
  default. What sized the job: styles.css already made 402 token reads and every widget + both shells link
  ONE `core/palette.css` — so the whole ask is three data layers, not a rewrite.
  - **palette.css** ships the new default («grafito»: warm near-black, four real elevation levels,
    heliotrope accent, amber highlights-only, light re-derived as warm paper) plus new tokens: root size
    `--hb-fs-base`, the `--fs-*` scale, radii, and the desktop ground layers. **core/themes.js** is the
    profile catalog — `grafito` (an EMPTY override map: the stylesheet is the profile, one source of truth),
    `clasico` (the exact old navy, kept whole so nobody loses today's look), `ambar` — plus `customVars()`
    for the knobs. **services/theme.js** writes profile+custom as inline custom properties on `<html>`
    (inline beats the stylesheet → one swap repaints every token reader, generated widgets included), tracks
    applied keys so a profile never BLEEDS into the next, and persists two layers: localStorage (instant
    paint) and the ACCOUNT's copy in settings.json via /api/settings, which wins on the boot reconcile.
  - **The sanitizer is a security seam, not tidiness**: the stored theme dict is echoed into inline CSS on
    every client that loads the account, so `settings.py` shape-checks slug/hex/enum on write AND read —
    stored style injection is the attack.
  - **The desktop**: `html{font-size:var(--hb-fs-base)}` + all 174 `font-size` declarations converted to rem
    (scripted), so the S/M/L knob scales everything; token-driven ground (masked dot grid + accent halo);
    chat tabs at UI scale wearing the accent; the composer at body scale; the **widget rail's tools became
    21px silhouette SVGs in 44px targets** — the orb lid's language; his report on the 30px/11px text glyphs
    was «no logro entender ninguno». ⚠️ The bigger tabs overflowed the 420px docked header and buried the
    ⧉/× buttons — the V2-608 suite caught it (that exact unreachable-close test), fixed with
    `min-width:0` + own overflow scroll. The generator contract + widgets/AGENTS.md now bind NEW widgets to
    `var(--sans)` and rem, so the knobs reach them by default.
  - Node **4.130** (8 rendered cases mounting the REAL modules served from disk — the probe asserts the
    RESOLVED color of a token consumer, which catches an override key drifting from a token name — + 4
    backend). Six disarms, all red. ⚠️ Two test traps paid: Playwright consults routes LAST-registered-first
    (the catch-all swallowed /api/settings), and the first fixture hand-wrote the `html{font-size}` rule it
    existed to test — the real styles.css is linked now. Sweeps: tests/browser 1577 + mensajería 152, green.
  - **Open, named**: per-widget custom skins and desktop wallpaper images (user freedom on top of the
    system); the hand re-scale of legacy micro-type to the `--fs-*` steps; the 14 shipped widgets still
    hardcode their font stacks (new ones are bound; the sweep is its own pass).

- **The music widget goes pro — a shared artist is said ONCE, and the play button lives on the art
  (V2-612, 2026-09-07)**: operator's screenshot, a real playlist ("True Blue") where every row read
  literally "Madonna Papa Don't Preach" — the artist baked into `title` with no separator, `artist` empty on
  every row. Root cause: `add_to_playlist{query}` (V2-384's "one call is all the model gets") falls back to
  `title = query` when neither field is given explicitly, and a free-text search string has no reliable
  machine boundary between artist and song — nothing here has music metadata to resolve it from.
  - **`deriveArtistInfo(tracks)`** (`widgets/musica/widget.js`, RENDER-side only, data never touched): when
    every track in a playlist shares the same artist — either a proper `artist` field, uniformly, or (the
    legacy shape) the same leading word(s) in every `title` with something real left over after them — the
    artist is said ONCE in the header ("Madonna · 3 canciones") and dropped from every row. Mixed metadata
    quality or a genuinely mixed-artist playlist never triggers a guess: showing the data exactly as given
    beats inventing a wrong split with false confidence.
  - **The play button moved INSIDE the cover-art square** (`.hb-mus2-artwrap` + a circular fab anchored to
    its corner), per the operator's literal words — not below the header as a separate pill. Every track row
    (playlist, "Más escuchadas", "Recientes") now carries a `playing` state: a tint, an accent-colored
    title, and an animated three-bar equalizer replacing the track number — the visible "is this the one
    making sound" signal the operator asked for, everywhere a track can appear, not only the bottom bar
    (which grew the same badge). **Click SELECTS a row (visual only, no `ctx.action`); double-click PLAYS
    it** — a deliberate behavior change from single-click-plays, matching a desktop Spotify tracklist.
  - **Forward fix, not a repair of what's already stored**: `_track_from_payload` (`data.py`) now splits an
    EXPLICIT delimiter ("Artist - Title") into separate fields; plain concatenation with no delimiter is
    left untouched on purpose. `manifest.json` now tells the model explicitly to pass `artist` in its own
    field, never concatenated — teaching, not a hardcoded table.
  - ⚠️ **A real, pre-existing grammar bug surfaced by the new tests, unrelated to the ask**: `canción` +
    `"es"` produced "canciónes" (should drop the accent — "canciones") in both the list-card subtitle and
    the playlist header; fixed because the tests asserted the literal rendered string.
  - **i18n was raised mid-build by the operator** (this widget's UI is hardcoded Spanish, like every other
    widget) and deliberately NOT touched here: confirmed via grep and this file's own V2-603 entry below
    that the widget layer has zero `t()` seam anywhere, offered the operator a scoped choice, and the
    operator chose to keep música consistent with the rest of the catalog for now — the seam itself is a
    separate, real initiative (wiring `t()` into a bare-URL `import()`-ed module, its own render-test
    harness support, bundle keys), not a drop-in fix inside a visual redesign.
  - ⚠️ **Caught on the live visual check, not by reading**: a legacy merged-title row playing through a
    CONNECTED provider never lit up — the provider reports its own clean, real title ("Papa Don't Preach"),
    which never equals the stored merged one ("Madonna Papa Don't Preach"), so the ONE scenario the redesign
    exists to fix was exactly the one the naive equality missed. `nowPlayingMatches` now also accepts a
    SUFFIX match when the stored track has no separate artist field, requiring the leftover prefix to agree
    with the now-playing artist (when known) so two unrelated songs sharing an ending cannot false-positive.
  - Node 4.3 (+1 file, 17 RENDERED cases) + 3 data.py cases, six disarms verified red (artist derivation,
    the click/dblclick split, the playing-row marker in both the playlist and the home lists, the suffix
    match). `make test-widgets` stays green 14/14. **Verified live** on `3.26+60ce513`: rendered the exact
    reported shape (a "True Blue" playlist with merged Madonna titles) against the real widget.js — header
    says "Madonna · 5 canciones" once, rows read clean, the play button sits inside the cover art, and the
    playing row lights up green with the equalizer, matching the bottom bar.

- **Connecting an account is ONE step, and a failed data-op corrects the claim it already made (V2-603,
  2026-09-06)**: session `e1acdcca` — nine minutes trying to connect YouTube, three browser windows, and the
  account never connected. `video_oauth.json` did not exist and `/api/video/status` said
  `app_configured: false`, so **every path was closed before the first word** and nothing said so. Between
  11:19:19 and 11:20:47 the agent made **four claims of success and emitted one widget action**.
  - **The brain had the VERBS and never the STATE.** `widgets/brief.py` shipped `connect_account` /
    `open_connectors` every turn and never the fact that no app was registered. `_connector_briefs` injects
    live state for **messaging only** — and its own docstring records that it exists because the brain
    «invented "you have no important messages" while the widget was closed». Video is the third connector
    family and never got the equivalent. Given a verb and no fact, the model narrates.
  - **A failed data-op was DISCARDED.** `dispatch_tag` did `await brain_action(...)` and threw the value
    away, so `connect_account`'s exact reason («sin app OAuth registrada») existed in-process, reached
    observability as `widget/action_failed`, and reached nobody. Structural, not a slip: data-ops are
    fire-and-forget, so **the turn speaks first and the op resolves after** — when it fails the sentence is
    already wrong and nothing revisits it. Now `dispatch_and_report` announces it on the rails a finished
    worker already uses, deduped 90 s, with a note that FORBIDS the claim rather than merely reporting.
  - **A true sentence about the WRONG mechanism is the worst failure shape.** A worker drove the browser to
    `accounts.google.com/signin` in the Playwright profile and the agent reported «la sesión se guardó en el
    perfil del navegador» — true about that profile, and it produces no OAuth token. `brain_state` names
    that trap explicitly, because a model cannot be expected to know the difference.
  - **The redirect could only work on one machine**: hardcoded to `127.0.0.1:43917`, which on a managed
    deployment is the OPERATOR's own computer. It follows the request origin now (validated
    `scheme://host[:port]` — it is a header, so untrusted input landing in a URL we hand to Google) and
    **rides under the OAuth state**, because the exchange must return the redirect that was authorized.
  - **The wizard's first two steps were a Google Cloud project**, and step 2 was a dead end that told the
    operator to go find ⚙ → Conectores himself. A shipped `builtin_client_id` (EMPTY until the operator
    registers one — the connector still works, just the long way) makes it a single consent step; the
    operator's own client always wins, which is what keeps the fair-code self-host story honest. **No
    client_id field in the card**, deliberately: `widget.js` never touches the network (V2-557) and a
    data-op never carries a credential (V2-520) — the fix was never to move the field, it was to stop
    making him navigate. The callback refreshes the card itself, so the mandatory «Comprobar» is gone.
  - **No environment detection**, though the ask was framed that way: the consent tries a pop-up and
    degrades to a tappable link. One path that works self-hosted, in the cloud and on the PWA beats three
    that each need their own testing.
  - **«Perdona, ¿me lo repites?» ×4** — two faults in one string: it repeats (the sibling branch got
    anti-repetition in V2-189 after the identical measured symptom) and it **blames the operator's speech
    for a turn the model returned empty**. `mute_backstop` owns both branches so the two channels share the
    decision instead of mirroring it, rotates, and after every variant admits it is stuck.
  - **Routing**: `conecta` seeded `cluster` (MeshKore peers) and nothing else, so the most natural Spanish
    word for linking an account retrieved peer-to-peer tools. And the widget's routing line was rewritten
    **to fit** V2-547's 300-char budget — the first draft mentioned connecting only in its last sentence and
    the trim ate exactly the half that routes this errand.
  - Node **5.15** (22 cases, six disarms) + the V2-597 render tests updated to the new wizard (+3, two more
    disarms). ⚠️ **One disarm came back GREEN and accused the TEST**: it only hit `dispatch_tag`'s guard
    clause and never the real path. ⚠️ **And the first version polluted `sys.modules`** — `from voice import
    brain_notes` reads the PACKAGE attribute, so a fake under the module name is ignored once anything else
    imported the real one; it passed alone and failed in the full run. The architecture ratchet went red and
    was paid by **extracting**: `nucleo.py` 3068→**3038**, `probe.py` 1144→**1137**.
  - **NOT verified live** (needs a restart) and **the shipped client does not exist yet** — registering a
    Google OAuth app owned by Zaelar is a business action and belongs in the workspace root's private repo.
  - Left open and named: widget i18n (no `t()` seam exists in the widget layer at all — every widget's
    strings are hardcoded, mensajería's wizard included), and the double browser for one intent, which is
    V2-570's linear-gate family, not this one.

- **A connected mailbox that shows nothing, forever — the inbox was declared already-seen (V2-606,
  2026-09-07)**: the operator, with the widget open on «Email — Conectado. Tus mensajes llegan aquí
  automáticamente.» and an empty list: «the Gmail thing doesn't work, the messages are not shown». Measured
  against his real mailbox before touching anything: **1110 in INBOX, 1088 UNSEEN, 22 read**.
  - **`service._loop` seeded `_seen` with `mailbox.all_uids()`** — every UID in INBOX — under the comment «only
    triage email that arrives AFTER connecting». So all 1110 were declared already-seen on connect and the
    widget could never surface one of his 1088 unread. The connector was not broken: it authenticated, polled
    every 20 s and did exactly what it was told. And `_seen` lives in MEMORY and is cleared on stop, so every
    restart moved that line forward again — anything arriving while the engine was down went invisible too.
  - **The line is drawn where HE already draws it**: mail he has READ is dealt with and does not come back;
    mail he has NOT read is the thing he is asking to see. `mailbox.inbox_split()` (two IMAP searches, no flag
    written, no body fetched) + `seed_from_mailbox`.
  - **A triage surface is not a mailbox** — 1088 is not a list anybody reads, so only the most recent
    `BACKFILL` unread are handed over. **Which is exactly why the TOTAL is recorded and travels to the brain**:
    silently hiding the other 1058 is the failure being replaced. Before, `brief` said «Email: conectado.» and
    nothing else, so with a connected flag and an empty card the model had only one explanation available and
    invented it — «Es que no tienes mensajes nuevos sin leer, por eso sale vacío», over 1088. It was not lying;
    it was missing the fact. The line now carries the count and NAMES the forbidden sentence (V2-221).
  - **`-1` is not `0`**: «not measured» must never render as «you have none», which is the sentence this exists
    to make impossible. And the split fails soft in the SAFE direction — a connector that cannot tell read from
    unread keeps the old whole-inbox seeding rather than dumping a mailbox into a triage widget.
  - **VERIFIED LIVE**: the first email in the widget's history landed, and «¿cuántos correos sin leer tengo?» →
    «Tienes 1.088 correos sin leer en Gmail» naming the urgent one, while «demuéstrame que el conector funciona»
    → «El correo está conectado y funcionando: tienes 1.088 sin leer. El widget filtra y muestra los más
    recientes» (was: «Hecho.»).
  - Node **5.16**, six disarms. ⚠️ **Three came back GREEN**: the test RE-IMPLEMENTED the seeding instead of
    calling it — *a mirror proves the mirror works, not the product* — so `seed_from_mailbox` was extracted out
    of `_loop` (which connects to a real server, and is therefore untestable in place) and the IMAP half got its
    own fake. ⚠️ **And a stale `.pyc` survived a restore**: disarm 5's mutation (`n < 0`→`False`,
    `n == 0`→`n <= 0`) was byte-length IDENTICAL, and Python invalidates on (mtime, size), so a restore inside
    the same second reused the mutated bytecode and the clean tree stayed red. The disarm harness clears
    `__pycache__` every run now.
  - **Open and named**: the triage keeps **1 of 30** (measured three times — the rest are judged not «for you»),
    which is right for a notification surface and arguable for «show me my unread», and is a product decision;
    and **a VIEW data-op's RESULT is still discarded** — `show_view` returns its matches and the prompt orders
    «contesta con sus nombres», but `dispatch_and_report` is fire-and-forget, so V2-603 wired the FAILURE case
    and success-with-content still ends in the canned ack.

- **Storing is not notifying — nothing interrupts by default, and the summary is not the mailbox (V2-607,
  2026-09-07)**: the operator's direction, the same day, right on top of V2-606: the «notify me on a new
  message» flag must be **OFF by default** and live in the widget's state; each channel's section holds what
  arrived unread; and the **summary tab highlights only what meets his criterion — by default, what is
  addressed to him**. «We can even be reading the messages that are arriving.»
  - **The trap that made this more than a default change.** `notify.surface` decided BOTH what got STORED and
    what INTERRUPTED — one gate, two questions. Flipping the notification default to silence through it would
    have emptied the widget completely: the exact failure V2-606 had just fixed, arriving from the other side.
    So the four ingest paths (the v2 owner + the three direct-path connectors) now ask them in order: **what is
    NEW goes into its channel's section whatever the policy says**, and only then, **what may interrupt**.
  - **Two knobs where there was one**: `notify` (default `never`) and `highlight` (default `direct`). `highlight`
    has **no «never» level** — an empty main tab is a broken screen, not a policy. The historical predicate
    stays exactly reachable (`notify: important`), and `_matches` single-sources the ladder both read, because
    writing it twice is how the two would drift apart.
  - **A durable ledger, because the in-memory one could not keep the promise it made.** MEASURED on the live
    engine straight after V2-606: the same email (uid 219719, «Pago rechazado» from Amazon) announced **THREE
    times in fourteen minutes** — 12:29:39, 12:38:21, 12:43:17, one per restart, each on a different build.
    Nothing was malfunctioning: the mail is still UNREAD in Gmail, so every connect re-delivers it, correctly and
    forever, while the only thing remembering it was a `set()` built in `__init__`. That set even carried the
    comment «do not resurrect what the operator removed», which it could not keep for the same reason — he
    dismisses a message, the engine restarts, IMAP still calls it unread, and it walks back in. `store.taken_ids`
    / `new_among`, capped at 4000, oldest-first. **An in-memory guard cannot dedupe against a durable source.**
  - **The brain is told the split.** It holds every chat; his first tab does not. Two surfaces over one dataset
    that disagree is precisely how V2-606 produced «no tienes correos sin leer» over 1088 of them, so `brief`
    marks each chat with where he can see it, states the remainder, and names the forbidden sentence.
  - **`notify.surface` was DELETED**, not left with no callers: a dead function carrying the old coupling is how
    the coupling comes back.
  - **The fork that would have swallowed all of it.** `widgets/_user/mensajeria/` — a fork taken 2026-09-05 from
    engine 3.25 — **shadows the built-in** (`paths.roots()`, generated root first), and every file in it was
    **byte-identical to HEAD**; only `manifest.json` differed, by `origin` and `forked_from`. Zero user work, and
    it froze his messaging widget at 3.25: every fix shipped to `widgets/mensajeria/` from that day on would have
    reached nobody, silently. Removed (backup kept outside the repo). ⚠️ **A fork with no user content is not
    free — it is a shadow**, and the widget lifecycle should not leave one behind.
  - **VERIFIED LIVE** on his engine at `3.26+f04daa7`: all three channels effective at `notify: never,
    highlight: direct`; two further emails (Plaid, Amazon) taken in **silently** after the restart, recorded in
    the durable ledger, **zero notices emitted since the process came up**.
  - Node **5.17**, six verified disarms, all caught. ⚠️ **Found on the way**:
    `tests/browser/unit/mensajeria/test_notification_policy.py` isolated its store by patching
    `wstore._DATA_DIR` — an attribute that does not exist — behind a `hasattr` guard that made the whole fixture
    a **silent no-op**. What actually isolated the module was an accident of import order (`DATA_DIR` is computed
    at import time, so the first test froze it), and the cases leaked policy into each other. The leak was
    invisible because **the value that leaked equalled the default they asserted**; inverting the default is what
    made it show.
  - **Open and named**: whether the WhatsApp and Telegram bridges hand over UNREAD on connect the way email now
    does is **not measured** — nothing in their code paths pulls a backlog (WhatsApp's `history` branch is
    on-demand scrollback), and settling it needs a live re-link of both accounts, not a reading.

- **The desk shrank underneath the cards and nobody told them (V2-608, 2026-09-07)**: operator's screenshot —
  he dragged the chat wall to the left edge, it docked correctly into a full-height column, and **not one widget
  moved**. One card ended up behind the chat, the one on the right was cut off by the window edge and
  unreachable. «Todos tienen que estar dentro de ese espacio visible. Autofit + autoresize, respetando el
  mínimo de alto y ancho por widget.»
  - **Two coordinate systems that stopped agreeing.** `#desk` follows `--chatdock-l/r` in CSS, but the cards
    live on `.hb-stage`, which is `inset:0` — so they are placed in VIEWPORT coordinates and clamped against
    `innerWidth`/`innerHeight`, which stopped being the canvas the day the chat wall could take a column of it.
  - **The rectangle already existed, in exactly one place.** `arrange()` computed the dock-aware bounds INLINE,
    and was therefore the only gesture on the whole canvas that knew a chat column could be there. It is
    `canvas()` now and every clamp reads it: placement, drag, drag-resize, voice `resize`, `move`, `maximize`,
    `_applyPreferred`, the ResizeObserver guard, `compact` and `arrange`. (Same shape as
    *[[La propiedad de la puerta]]*: the good calculation was already being made, one caller away.)
  - **Three ways the canvas changes shape; only one said anything.** The rail announces `hb:rail-resized`, but
    its listener only ever shoved cards RIGHTWARDS — it never resized an oversized card and never pulled one
    back from the right edge. The chat dock announced **nothing**. A window resize was **not listened to
    anywhere**. All three run one autofit pass now, coalesced on a frame because a dock drag fires continuously.
  - **Autofit AND autoresize**: a card too wide for what is left is SHRUNK, never merely moved — down to that
    widget's own minimum (`manifest.min`, falling back to the 240×150 floor the drag handles already enforced),
    so a narrow canvas makes a card scroll instead of collapsing into a sliver. A maximized card is
    **re-maximized to the new canvas**, not clamped: it is deliberately canvas-sized, so clamping the old
    footprint would leave it hanging over the column it was told to avoid. **A card that is already legal is
    left exactly alone** — refitting is a repair, not a layout engine; a «tidy» that also undoes where he put
    things is a second bug.
  - **Two more defects, measured on the real page while testing this one**: (1) a **DOCKED wall did not come
    back docked** — `hb_chat_dock` was written on every dock and never read back on restore, so `floatGeo`
    (which `applyDock` does not clear) always won; measured: dock left, reload, returns at `left:18 w:320` with
    the key still holding `{side:"left",w:420}`. V2-550 fixed «it does not come back where it was» for the
    FLOATING wall; this was the same report for the docked one, which is the shape he actually uses. (2) **the
    reserved strip did not match the column it reserves** — `setReserve` measured `offsetWidth`, which is 0
    while the wall is unlaid-out (the restore path exactly), so it reserved the 340px default for a 420px column
    and left an 80px band of desk hidden under the chat.
  - ⚠️ **The first cut of this was a REGRESSION and he caught it the same day**: «simplemente le he dicho que
    abra el chat. No lo hemos pegado a la barra de la izquierda para que se haga una columna, y ha movido el
    resto de objetos a la derecha. Eso no había pasado nunca.» `canvas()` had inherited `arrange()`'s test —
    the wall's own bounding rect, comment and all («docked/floating on the LEFT»). For a deliberate «ordénalo
    todo» that is a nicety; for a refit that runs on EVERY canvas change it means merely OPENING the chat
    rebuilds the desktop. **The rule is his**: only a docked column shrinks the desk. It reads `--chatdock-l/r`
    now — published only for a wall that is open AND docked, and the exact values `#desk` is inset by — so the
    rectangle IS the desk and there is no second opinion to drift from it. A floating wall stays what it always
    was: an obstacle in `_obstacles()`. **Generalisable**: a calculation written for a DELIBERATE gesture is not
    automatically right for a CONTINUOUS one, and copying it is how a nicety becomes a defect.
  - ⚠️ **And the defect underneath his screenshot**, reproduced headless: the wall's `class` is a REACTIVE
    binding (`"chatwall tab-" + tab + (open ? " open" : "")`) that rewrites the WHOLE className, while
    `docked`/`dock-left` are set IMPERATIVELY by `applyDock`. Any tab or open change wiped them and left
    `dockSide` still set — so the wall rendered as a floating panel at `left:0` (`top:232 h:480`) **and still
    reserved a 420px column**, pushing the whole desk right for a column that was no longer there. Measured
    verbatim: classes `chatwall tab-chat open`, `--chatdock-l: 420px`. Pre-existing (a tab change while docked
    did it too); restoring the saved dock made it reachable on every load. **Two writers on one className, one
    reactive and one imperative, is the shape** — the reactive one must reproduce what the imperative one set.
  - ⚠️ **AND THE ROOT CAUSE WAS UNDERNEATH ALL OF IT** (F3, same day, four more reports): `#wstage` is a CHILD
    of `#desk`, and `#desk` carries `transform: translate3d(0,0,0)` — which makes it the **containing block for
    every `position:fixed` descendant**, `.hb-stage{inset:0}` included. So a card's `style.left` is measured from
    the DESK, and the stage slides on its own when a column insets `#desk`. Deliberate and documented since
    V2-062 (`main.js:33`): the orb and camera travel with the desk. **MEASURED**: a card at `style.left:100px`
    renders at viewport 115 undocked and at **535** with a 420px column, `style.left` untouched. Every clamp
    comparing `style.left` against a VIEWPORT number was wrong by exactly the column width — **and silently right
    whenever nothing was docked**, which is how it survived. It is also the other half of his report: `_wireDrag`
    took the grab offset from `getBoundingClientRect()` and wrote it into `style.left`, so the card jumped
    sideways the instant he grabbed it («la manita aparece desplazada 100 o 200 píxeles»). One `_toDesk()`
    conversion now feeds `canvas()`, `_obstacles()`, `_watchSize()`, the drag and the drag-resize.
  - ⚠️ **My fixture built `#wstage` as a SIBLING of `#desk`**, so `position:fixed` resolved against the window
    and the two coordinate systems coincided. Twelve green tests over a DOM the product does not have. **A
    harness whose DOM differs from the product's measures a different product** — when a UI fixture hand-writes
    the scaffold, copy the real rule verbatim, `transform` included.
  - **The orb** was already centred on the desk (`left:50%` resolves against `#desk`) — the first attempt added
    the dock offset and pushed it half a column off-centre, the same double-count again. What needed fixing is a
    DRAGGED orb: its inline `left` is a desk pixel valid for the old desk WIDTH, so it is remapped by the
    FRACTION of the band it sat at — «la misma posición relativa, en el nuevo tamaño de la zona visible».
  - **A docked column must always offer a way out.** It can be opened by the AGENT (a proactive push showing the
    cluster list), so it arrives docked without him docking it — and he had TWO independent reasons he could not
    close it: `--banner-h` was honoured by `.me` and `.tr` and **nothing else**, so the update banner buried the
    column's own header; and the column's east resize strip sat **on top of** the close button
    (`elementFromPoint` over the × returned `DIV.hb-rz hb-rz-e`). Plus a visible undock button that returns the
    floating chat panel — «se minimiza la barra y vuelve a aparecer el widget del chat».
  - **The whole header drags**, like any OS title bar, for every widget. `Desktop.DRAG_HANDLES` is the single
    declaration of what drags a card — read from the CARD, so a test can ask the product which parts are handles
    instead of choosing for it. Clicks survive on a 4px threshold, and the move/up listeners live on the
    **window**: on a 26px grip, handle-bound listeners stop firing the moment the pointer leaves it (measured:
    0px for a 120px drag), and capturing instead would retarget the click and kill the title button.
  - **F7 — the «Procesos» row's title mutated with every phase** (operator, same day): it began as «leyendo
    brickset.com…» and cycled through progress paragraphs until updates stopped. Two causes, one per layer: the
    store kept ONE `text` that four writers overwrote in turn, and **there is no `start` lifecycle event
    anywhere in the backend** — chips are BORN from their first `phase`, so the mutable activity text WAS the
    title; the one-time naming event («🏷️ encargo nombrado», V2-530), which carries exactly the settled name,
    was not even listened to in SSE. Now `title` (start seeds it, 🏷️ settles it, nothing else touches it) and
    `note` (phase/plan/progress) are separate fields; reconcile takes the server's `title` and real `age_s`,
    precedence settled-name → held-name → brief — **the mounted test caught the goal clobbering a settled name
    before it shipped**. Row = name · activity (2-line clamp) · «en curso · 1/5 · 20% · lleva 4 min · desde las
    19:42». Node **4.122**, seven disarms.
  - **F8 — a RESET sends the orb home** (operator, same day: «cuando se hace un reset, quiero que el orbe
    vuelva a su posición inicial»). Reset cleared canvas/log/chat and left a dragged orb where the drag put
    it — with `hb_pos_orb` restoring that spot on every future page load. `resetDraggable()`
    (lib/draggable.js) is makeDraggable's undo: forget the persisted key AND drop the inline styles, so
    `.orbwrap`'s own CSS centres it on the DESK again (with a docked column, the centre of the shrunk desk,
    not the window). Wired through the client-side deterministic reset path: `_clearCanvasAndLog()`
    announces `hb:canvas-reset`, Orb.js answers. Node **4.126**, four disarms, rendered with the real
    draggable.js and pointer gestures.
  - **F9 — the orb's drag was still in the WRONG coordinate space** (operator, 2026-09-08, next day: «cuando
    pincho en el orbe, el ratón se va… se desplaza unos 200 píxeles; la segunda vez el orbe se me ha movido
    fuera de la pantalla»). F3 fixed viewport-vs-desk for the CARDS (desktop.js); the orb/camera/status
    chrome drags through `makeDraggable` (lib/draggable.js), which still took the grab origin from
    `getBoundingClientRect()` (viewport) and wrote it into a `style.left` that resolves against `#desk` —
    so with a column docked every drag added the column width once: first click a ~200px jump, second
    off-screen, and a position persisted while docked came back shifted on every later load. Everything now
    converts through `containerBox(el)` — the element's REAL containing block, found by walking to the
    nearest transformed ancestor — so desk children drag in desk pixels, the clamp is the container's edge
    («the orb never leaves the visible desk»), the persisted position travels in container space, and
    elements mounted outside `#desk` (feedback button, floating chat) get the viewport box and are
    byte-for-byte unchanged. ⚠️ **The hard-drag test then caught a SECOND live defect**: the move/up
    listeners were handle-bound, so a fast drag whose first pointer sample already left the orb simply DIED
    — `styleLeft` empty, nothing persisted, the drag never happened. The F6 grip lesson, paid again in the
    OTHER drag path: per-drag window listeners now, no capture (a tap must keep firing the handle's click).
    Node 4.121 (+1 file, 5 rendered cases, real pointer gestures), four verified disarms.
  - Node **4.121**, twenty verified disarms, all caught. **RENDERED, not read**: a source test says the listener
    exists; only layout says the card ended up inside. ⚠️ The first version of the test built the Desktop with
    `Object.create(prototype)` to skip a constructor that ends in `restore()` (which talks to the server) — so
    the listeners never registered and the test measured nothing. Registering them in the test would have proved
    the test works, not the product, so the wiring came out as `_watchCanvas()`, the seam the constructor calls.
    Same move, same reason, as `seed_from_mailbox` in V2-606.

- **A card question the operator cannot answer is asked forever — and the captcha handoff nobody offered
  (V2-605, 2026-09-07)**: session `43b7bf79`, read turn by turn before touching anything. «Tienes 2 abiertas:
  ¿cuál te enseño, "t1" o "navegador"?» was spoken FIVE times in 93 seconds while he answered it («uno está
  vacío y el otro tiene la web del…»), rephrased it, protested and gave up — and his actual request, «ábreme el
  navegador para que te confirme el captcha», reached nothing.
  - **The sentence is not the model's.** It comes from `instances.resolve_show` and enters through
    `clarify["msg"]`, which **REPLACES** `spoken_text`. So when the model finally said the right thing at
    11:06:33 («The Fork nos ha bloqueado… confirmes tú el captcha»), the canned question was glued onto it
    instead of losing to it, and the `ROMPE EL BUCLE` nudge — which fired in four of those turns — was
    reprimanding the model for a sentence the model does not write.
  - **The question named IDS.** `_label` could only title a `results` sheet; every other piece fell through to
    the instance suffix and the base id — the dump the module's OWN docstring already forbade. A card is now
    named by WHAT IT SHOWS (`data.card_face`, implemented by the only two instantiating pieces), and a browser
    card **by its HOST**: found by a test of mine, «Reserva en los mejores restaurantes de España | TheFork»
    capped to a speakable length drops «TheFork» — a page title is marketing prose with the brand LAST.
  - **A BLANK card was a candidate**, and his reply is the specification. Showing only: `resolve_close` keeps
    asking, because there the blank one is the cheap mistake and the full one is somebody's work. Same input,
    opposite risk, opposite default.
  - **Asked ONCE.** With `last_spoken`, a repeat CHOOSES and says which — the V2-530 lesson one axis over: he
    had answered, with a description (`la que tiene la web`) the resolver had no way to express.
  - **`authenticate_web` was declared LOGIN-only** while being exactly the mechanism he asked for (it opens the
    REAL browser window on his machine). It was in the tool list of every one of those turns. *An undeclared
    capability is one the model NARRATES* (V2-540) — declared for half its job is the same failure. The wall
    note said «que entre él», which names an outcome, not a mechanism, and never named the SITE, so
    `web_auth.start("")` would have opened nothing by design. Both now carried.
  - ⚠️ **The thing it was NOT, and I nearly reported it.** The state block WAS in every prompt:
    `observer._prompt_excerpt` keeps head 6000 + tail 7000, the prompt grew 27k→38k at 11:02:43, and the block
    fell into the elided middle — **the exact trap that function's own docstring documents**. Measured instead
    of deduced, three steps from blaming healthy plumbing.
  - Ratchet paid by EXTRACTING: sheet naming → `results/sheet_names.py`, show-instance resolution →
    `flash/show_target.py` (which also single-sources what the two channels did twice). The tool-catalogue
    ceiling is SHARED and paid on every voice turn (V2-526): three drafts went up to 500 chars over and the
    DECLARATION was compressed, never the ceiling.
  - Nodes **4.118**/**4.119**, ten disarms, every mutation ASSERTED. ⚠️ **Three came back GREEN first time**:
    two were no-op mutations of mine (`"" or X` is `X`; and «captcha» survived in the example sentence), and one
    was a REAL gap — I claimed to have MOVED the sheet's naming into the widget and no test opened a sheet, so
    deleting it whole stayed green. *A move is only safe if the destination is measured.* And the extraction
    turned the older show-decision wiring guard RED because it was pinned to `probe.py`: repointed at the
    CHANNEL, per V2-555.
  - **FOUR doors show a card, and they only become visible ONE AT A TIME.** The tool path was fixed in both
    channels first; then driving the LIVE engine showed «Enséñame el navegador» never touches it. F2: the model
    called no tool and emitted no tag — a deterministic backstop produced the show with the base id, because in
    `_widget_fallback` the CLOSE branch has consulted the instance since V2-259 and the SHOW branch never did.
    F3, after F2 still did not narrow: the turn returned in under a second with no model call at all — it is
    the **ACTION MAP** (V2-539), since «Enséñame el navegador» is a SEEDED phrase (V2-567's grids). *The two
    doors fixed first are the SLOW ones; this is the lane a real operator actually hits.* One chokepoint
    (`instances.show_id`, narrow-only — these lanes are silent and cannot ask), not four patches, which is the
    doctrine written at the top of that same file for closing since V2-259. A test now COUNTS the doors.
  - ⚠️ **A measurement trap, paid twice**: `/api/flash/say` without `execute: true` DESCRIBES the action without
    running it, and `describe()` prints the STORED name — so the live check was reading the label, not the
    event. What counts is `widget/show` in observability.
  - **And the deepest one: our repeated sentence was DELETING his (F4).** Across the failing stretch the
    conversation window collapsed **10 → 8 → 6 → 4 → 2 messages in four turns**, so by the time he said «te he
    dicho que quiero un navegador en MI ordenador» the model was answering on two messages of history. His own
    diagnosis — «le falta lo que estamos haciendo en este momento» — was right. `dialog.prune_window` collapses
    near-identical ASSISTANT replies (correct, V2-032) and ALSO deleted the USER turn in front of the twin it
    removed, against what its own docstring has promised since the day it was written. Because the repeated
    sentence was OURS — a canned clarify he never provoked — **every repetition ate one of his**: four of his
    sentences went in and ONE came out, «¿no has entendido lo que te he dicho?», the least informative of the
    four. The mechanism that exists to stop degeneration was amplifying it, leaving the model less to escape
    with on every turn. What repeats is the reply; what he says never repeats and is exactly what is needed.
    Node **4.120**, two disarms.
  - **VERIFIED LIVE** on `3.26+69efaf4`: «ábreme el navegador para que te confirme el captcha» → `authenticate_web`
    (was `show_widget` + the question), and «enséñame el navegador» → `widget/show id=navegador::t1 src=actionmap`
    (was the bare, empty box). **NOT verified live**: the blank-card filter with a REAL worker-created browser
    task, which needs a live errand. **Open and named**: the GHOST CARD — the canvas began reporting a
    bare `navegador` with **no `widget/show` behind it**, the stray box the browser task registry's own
    comment already calls the «ghost card»; this makes it harmless to show, it does not remove it. Also open: `clarify` overriding a good reply in its 13
    other faces, 18 identical «Dentist» notices in one kickoff prompt, and a browser block that said «la web
    BLOQUEÓ» twelve lines above «YA HA ENCONTRADO ALGO».

- **Messaging navigation gets unstuck, and email defaults to a classic list (V2-610, 2026-09-07)**:
  diagnosed from the operator's own local session. Clicking a platform icon while Conectores was open never
  cleared `_screen`, so the click's own effect stayed hidden underneath it — «no se va la vista de
  conectores». The «Mensajería» title now returns to the unified dashboard from anywhere (his own words: it
  is «la única que voy a querer mirar en principio»). Email's default view stops being the same
  inline-clamp shape as a WhatsApp thread — asked, by voice, four times in one session, to compact it to
  «el asunto y la hora, como en cualquier cliente de correo electrónico», and no action existed to do it
  (`show_view` only ever moved the LENS, never the density). It ships as the hardcoded default now, never a
  toggle — his own words close that door: a fork can change it.
  - `_openMail` keys by the item's `messageId`, never its positional `n`: `n` is REASSIGNED on every save
    (`_renumber`), so a bare `n` pointer would resolve to whatever mail inherits that number next and
    silently show the WRONG one — caught by a test built around exactly that reuse before it shipped.
  - `messageActions()` extracted so the compact row and the new detail screen share one set of five buttons
    instead of drifting into two.
  - Node 4.122, 10 new + 8 updated cases, 8 verified disarms. **Found live, at closure**: the working tree
    also carried substantial UNRELATED uncommitted work (`desktop.js`, `ChatWall.js`, `Orb.js`, `styles.css`,
    i18n bundles, two chat-wall/canvas-refit e2e tests) that predates this change and was left untouched —
    it has its own currently-failing test. `git stash`/`pop` preserved it faithfully; committed only the
    four files this change actually touched, by explicit path.

- **Reply from the widget with review-first draft/send, and a real email signature (V2-611, 2026-09-07)**:
  three pieces the operator asked for together. **Redesign**: bigger, real-button header icons (26px→34px
  hit targets, hover backgrounds) and a border separating the header band from the content below —
  regression caught before shipping: the wider icons overflowed a 375px card, fixed with `flex-wrap` on the
  header row rather than shrinking the icons back down. **Compose bar**: `draft` writes the visible text
  without sending, `send_draft` sends exactly what the box shows — never a value cached from an earlier
  keystroke — reusing the EXISTING `pending_reply` drain untouched, so all three platforms send through the
  same path `reply` already used.
  - `_resolve_target`/`_enqueue_reply` are NEW, used only by draft/send_draft — `reply` keeps its ORIGINAL,
    separately-tested resolution (chat-list numbering when no thread is open) byte-for-byte, because the new
    actions' contract is deliberately different: the widget always hands over a concrete `n`+`messageId` for
    a single email, sidestepping the ambiguity `reply`'s legacy fallback has rather than trying to fix it
    for a caller it was never written for.
  - **Two real bugs, both found by tests before shipping.** `_resolve_target`'s n-lookup skipped
    `_renumber()` — `n` only exists once that runs (data.py:128), a raw stored item never carries one — so
    it would never have matched anything against REAL storage; only my own test fixtures, which pre-set `n`
    for readability, hid it. And `_enqueue_reply`'s "is this a live item to remove" check used
    `target.get("n")`, which is ALSO absent on `reply`'s own chat-grouping-resolved targets (they never go
    through `_renumber` either) — fixed by checking `messageId` instead, the one field every real item
    actually carries, ingested by every connector without exception.
  - **Signature, after checking rather than assuming.** No real Gmail signature to import — it lives behind
    the `gmail.settings.basic` OAuth scope, which this IMAP/SMTP connector doesn't request and structurally
    cannot use. No double-signature risk either — a raw SMTP send never goes through Gmail's own compose UI,
    so its auto-append never fires on anything sent this way. Appended exactly once, in `_drain_replies` —
    the one place a real send happens — read fresh from `config/connectors.py`, the SAME store the connect
    wizard already writes account credentials to; voice sets it line by line (`set_signature_line`).
  - `widgets/validator.py`: `mensajeria` added to `_STDLIB_EXEMPT` — reading the signature needs
    `connectors.email.config`, lazily, exactly like `youtube`'s own `_svc()` reaches its connector.
  - Nodes 4.124/4.125 + 5.18, 30 cases, 17 verified disarms. **Found at closure, not caused here**: another
    session's V2-608 F3–F7 work landed on `main` mid-build (its own commits, `3d74cd6`..`171d8b2`) — it
    correctly avoided this work's files, and its own initiative doc names this one back for the same reason.

- **«Sal de pantalla completa» needs no name — the canvas knew which card and never said so (V2-609,
  2026-09-07)**: session `4a492268`. «Sal de pantalla completa.» → «Hecho.» with **no tool call at all**;
  nine seconds later «Quita la pantalla completa del vídeo» exited correctly. Three things were true and
  only the third is a defect: `maximize()` IS a real toggle (so the second phrasing worked),
  `attention.mentions_fullscreen` correctly stopped the close-backstop from closing the whole widget
  (V2-600), and **`fullscreen_widget` REQUIRED `widget_id`** — described as «el widget a AMPLIAR», which is
  one-directional prose on a two-directional toggle — while the sentence names no widget. Inventing an id
  is forbidden (V2-026), so the model's only remaining moves were to call nothing or to confabulate, and it
  did both.
  - **The operator's reading was the correct one**: one card at full screen, almost nothing else open — the
    target was not ambiguous, it was *obvious*. And the canvas KNEW it: `card._restore` is the maximize
    marker, and the report that already travels on every `_persist()` carried `min` and not `max`. Same
    shape as V2-603's connector: **given a verb and no state, the model narrates.** A verb whose object the
    system can see and the model cannot is a verb the model declines to use.
  - **The fix went in the ARGUMENT, not the prose.** The verb mapped fine — the very next turn proves it —
    and the tool catalogue is paid on EVERY voice turn (INI-027) and had **three characters of headroom**.
    `widget_id` stops being required, its description says VACÍO = the one at full screen, and the catalogue
    came out **9 chars smaller** than before. Four seams: `desktop.js` reports `max`, `/api/canvas/state`
    keeps `state.maximized_widget`, `widgets/brief` marks that row, and `show_target.fullscreen_target`
    decides the target ONCE for both channels (the probe is a parallel impl by design — V2-252).
  - **The dangerous half, found by a disarm.** With NOTHING at full screen and ONE widget open — the
    operator's own most common canvas — `identify` happily resolved «sal de pantalla completa» to that
    widget, and `fullscreen_widget` is a TOGGLE: acting on it would have put the card INTO full screen, the
    exact opposite of the order. An empty argument now means «the one at full screen» and NOTHING else;
    with none, the honest result is nothing and the caller asks. ⚠️ My first version of that test opened
    TWO widgets, so the single-widget fallback walked straight through it — **the test has to stand in the
    operator's canvas, not in a convenient one**.
  - **Also true and NOT fixed here**: the «Hecho.» itself. `susurro/friction.py` detected it in the same
    second — «data-op fantasma (charló y dijo que actuaba sobre un widget, sin ejecutar la tool)» — and was
    **in cooldown, so nobody was told**. That detector is diagnostic, not corrective; a general "claimed
    done, called nothing" repair is its own batch and is named, not built.
  - **The number was already taken.** V2-605 belongs to the card-question initiative; `probe.py` carried its
    references before this work started. Renumbered to 609 at closure — and the rename then clobbered seven
    of those pre-existing references, which is the second half of the same trap: *reserve the number when
    you TAKE it, and rename by hand.*
  - Node **4.117** (16 cases, 12 verified disarms). **Verified live** on `3.26+3223c6a` in both directions.

- **The video widget OWNS its library; the connector only EXTENDS it (V2-604, 2026-09-07)**: operator's
  direction, verbatim in spirit — «it is more important to me that the video widget is responsible for
  storing the data. We don't want external dependencies. Our core, our engine, our memory, our widget are
  the ones who have control.» Followed channels, watch history, preferences/filters and saved lists moved
  into `widgets/youtube/library.py` and the widget's own store. **Every test in node 4.116 runs with the
  account connector ABSENT**, which is also its real state (V2-603 F2 hid it): nothing here may ask it
  anything or degrade without it.
  - **The history is ours BECAUSE WE PLAY THE VIDEO.** Recorded in the two places playback really starts
    and nowhere else, so `add`/`search` — which never autoplay (V2-366) — never enter it; a replay MOVES
    the row and bumps `plays`. It is not a copy of anything: the YouTube API's watch history has returned
    empty for every account since 2016, so this is the one video fact a connector could never hand us. The
    ownership argument and the capability argument point the same way, which is why the operator's instinct
    here was the stronger architecture and not merely the more independent one.
  - **A "minimum 720p" rule is only checkable at the PLAYER.** Measured, not assumed: the results page does
    not publish definition — of ~20 hits only 4K carries a badge at all — so `_search_many` can never
    enforce it. `widget.js` reports `availableQualityLevels` from the `infoDelivery` the player already
    sends (once per video; that stream fires several times a second and each report is a store write), and
    `player_quality` checks it. It **WARNS and never skips**: he asked for THIS video, and an explicit order
    outranks a standing filter — the same line `block_channel` draws for a pasted link. Levels that carry
    no information (`auto`/`default`) produce no verdict, because guessing from them would invent a
    complaint about a video that may be fine.
  - **A preference we cannot enforce is stored as a NOTE and says so.** Only `min_definition`, `captions`
    and `volume` are applied; anything else lands in `prefs_notes` with an answer that states plainly it
    will be honoured by judgement, not forced. Storing an unenforceable rule as though it were enforced is
    exactly the "true sentence about the wrong mechanism" V2-603 already paid for. `captions` re-asserts on
    every video; `volume` only when playback starts from nothing — a preference that undoes his last
    explicit order is not a preference, it is a bug with a settings screen.
  - **Two defects the tests caught, both mine.** (1) `_seed()` guarded only against sharing its LISTS, and
    its own docstring records the V2-366 bug that put that guard there; `prefs` arrived as the first DICT
    in the seed and went straight through, so a preference set in one session was still in the next
    widget's "empty" state. **A guard written against one container type is not a guard against aliasing.**
    (2) The preference VALUE was matched more strictly than the key — the table held `si`, the operator
    says `sí` — so the first sentence anyone would speak in Spanish was refused. Both were found by writing
    the test in his words rather than in the API's.
  - **The action gate now follows one level of delegation** (`widgets/validator.py`). It read `data.py`
    only, so V2-025's rule (a declared action needs a branch HERE) and the architecture ratchet (pay a
    growing file by EXTRACTING a module) pulled in opposite directions — leaving "keep the whole dispatch
    in one god file" as the only green option for every widget, forever. It still fails closed in both
    directions, and anything it cannot resolve statically is simply not counted.
  - Node **4.116** (29 cases, **13 verified disarms**). ⚠️ **One disarm came back GREEN**: removing the
    delegate-following from the gate changed nothing, because the test read the manifest directly instead
    of exercising the gate — a test that asserts the RESULT of a mechanism does not test the mechanism.
  - **Verified live** on `3.26+7b80c5b`: the library fields serve, the four preference paths answer, and
    the probe data was cleaned back out of the operator's real widget. ⚠️ **NOT verified live: the quality
    readback itself** — that the IFrame API emits `availableQualityLevels` inside `infoDelivery` needs a
    real browser with the agent running. The server side is covered; the wire is not.

### Archived decisions — index (full text: `.meshkore/docs/decisions-archive.md`)

- **The stop record declares its own lifespan (V2-568, 2026-09-03)** (2026-09-03; V2-567, V2-568)
- **A spoken correction reaches the SLOTLESS pill it corrects (V2-565, 2026-09-03)** (2026-09-03; V2-498, V2-536, V2-565)
- **A screen belongs to ONE connector, and a picker is a grid you can already see (V2-561, 2026-09-03)** (2026-09-03; V2-520, V2-526, V2-559, V2-561)
- **A fresh Volume has no directories, and a session born LAZILY told nobody (V2-562, 2026-09-03)** (2026-09-03; V2-102, V2-562)
- **The picture was never missing, only OUR COPY of it (V2-563, 2026-09-03)** (2026-09-03; V2-466, V2-563)
- **Google Photos via the PICKER, and a real gallery has to VIRTUALIZE its grid (V2-564, 2026-09-03)** (2026-09-03; V2-547, V2-564)
- **A follow-up is not a new errand, and an alias fragment is not a name (V2-566, 2026-09-03)** (2026-09-03; V2-565, V2-566)
- **One widget order, ONE mutation — and the boring ones never wait for a model (V2-567, 2026-09-03)** (2026-09-03; V2-210, V2-526, V2-539, V2-564, V2-567)
- **A DELIVERED hunt is not re-hunted in parallel — the linear gate (V2-570, 2026-09-03)** (2026-09-03; V2-095, V2-199, V2-222, V2-259, V2-453, V2-556, V2-566, V2-570)
- **ONE widget per errand — the browser lives INSIDE the sheet's process tab (V2-571, 2026-09-03)** (2026-09-03; V2-202, V2-434, V2-538, V2-539, V2-540, V2-562, V2-571)

- **El worker escribe lo natural y el CLI le cobraba el turno — tres formas más (V2-341, 2026-08-26)** (2026-08-26; V2-123, V2-248, V2-253, V2-306, V2-341)
- **Las dos puertas del motor le decían cosas opuestas al mismo worker (V2-350, 2026-08-26)** (2026-08-26; V2-350)
- **Un contratiempo también se cuenta: solo las buenas noticias llevaban un «cuéntalo» (V2-348, 2026-08-26)** (2026-08-26; V2-131, V2-133, V2-222, V2-276, V2-348)
- **Un nombre que comparten todas las filas no nombra a ninguna (V2-346, 2026-08-26)** (2026-08-26; V2-334, V2-345, V2-346, V2-347)
- **Una ruta que comparten decenas de anclas no es la ficha de nada (V2-334, 2026-08-26)** (2026-08-26; V2-320, V2-334)
- **Sin filas no se puede pedir que las cuente (V2-330, 2026-08-25)** (2026-08-25; V2-298, V2-330)
- **El informe dice qué nombró ZAELAR él mismo (V2-329, 2026-08-25)** (2026-08-25; V2-329)
- **Un SUPERÍNDICE no es parte del número (V2-326, 2026-08-25)** (2026-08-25; V2-326)
- **Pedir ayuda no es equivocarse (V2-325, 2026-08-25)** (2026-08-25; V2-325)
- **Cuando dos anclas apuntan al mismo anuncio, gana la que lo NOMBRA (V2-324, 2026-08-25)** (2026-08-25; V2-234, V2-324)
- **«Cero filas» no es «sin resultados» (V2-323, 2026-08-25)** (2026-08-25; V2-294, V2-323)
- **Verificar el ARREGLO no es verificar el CASO (V2-322, 2026-08-25)** (2026-08-25; V2-321, V2-322)
- **Una FECHA no es un teléfono, y la diferencia costaba la hoja entera (V2-321, 2026-08-25)** (2026-08-25; V2-321)
- **Las tools, de menos a más (2026-08-02, norma del operador)** (2026-08-02; no refs)
- **El FlashBrain se queda en DeepSeek V4 Flash — y la latencia NO es del prompt (2026-08-02)** (2026-08-02; no refs)
- **Dominios públicos → motor local (CERRADO 2026-07-22)** (2026-07-22; no refs)
- **Motor de voz = LiveKit Agents** (2026-07-29; INI-012)
- **Cerebro propio «Colmena» — FlashBrain ORQUESTADOR + workers Claude Code** (2026-07-13; V2-036)
- **Workers Claude Code = memoria serial + reporte por el bus + pool** (2026-07-16; V2-036)
- **Brain Workers INTERACTIVOS — sesiones vivas, bidireccionales y AGNÓSTICAS del motor** (2026-07-14; V2-029, V2-038, V2-063, V2-084)
- **UN BRAIN WORKER HACE CASI DE TODO — la seguridad es un FILTRO, no una lista corta de permisos** (2026-08-21; V2-117, V2-236)
- **Gate de ATENCIÓN — el micro abierto no actúa sobre voz ambiente** (2026-07-09; V2-015)
- **Latencia del turno — la memoria FUERA del camino caliente** (sin fecha; V2-011)
- **Circuito de CORTO PLAZO de interacción con el operador** (2026-07-14; V2-035)
- **El canvas es AUTORITATIVO — reconciliar al (re)conectar** (2026-07-14; V2-035)
- **ESTADO = contexto VARIABLE con UI vivo — el cerebro sabe lo que el operador tiene DELANTE** (sin fecha; V2-011)
- **RAILS — comportamientos comunes CONDUCIDOS** (sin fecha; V2-042, V2-047)
- **- **«Sistema arena» — rails/widgets/tools auto-generados, BRAIN RULES + USER RULES, genética (V2-046, DISEÑO** (2026-07-16; V2-042, V2-045, V2-046)
- **- **Bóveda de secretos del operador — cifrado E2E + passkeys (V2-060, CONSTRUIDO 2026-07-21, rama** (2026-07-21; V2-046, V2-060)
- **«Susurro» — auto-auditoría conversacional y mejora continua** (2026-08-09; V2-053, V2-061)
- **Acciones ENCADENADAS realidad↔widgets↔memoria + inteligencia asertiva de DOS velocidades** (2026-07-21; V2-061)
- **Búsqueda web = capacidad COMPARTIDA por los dos cerebros, model-agnóstica** (sin fecha; V2-011, V2-022, V2-024)
- **Prewarm del camino caliente en el ARRANQUE** (sin fecha; V2-024)
- **Prompt del FlashBrain = ESTADO compuesto + petición, ~30 líneas (no ~280)** (2026-07-11; V2-011, V2-027, V2-028, V2-029)
- **ORDEN DE PROVEEDORES — DeepSeek V4 DIRECTO primero, luego el broker, y solo al final OpenAI/Anthropic** (2026-08-19; no refs)
- **Cerebro de voz = NO-razonador** (sin fecha; no refs)
- **- **ORDEN DE PROVEEDOR — DeepSeek V4 DIRECTO primero, broker después, OpenAI/Anthropic el último (NORMA del** (2026-08-19; V2-097)
- **Routing de modelos — POR INVOCACIÓN** (2026-08-19; V2-034, V2-077, V2-097)
- **Memoria central** (2026-08-16; V2-013, V2-056)
- **Recuperación del recall LARGO = RERANKER model-agnostic, LOCAL por defecto** (2026-07-12; V2-030, V2-031)
- **Sistema Nervioso** (sin fecha; no refs)
- **Perfiles remote/local** (sin fecha; no refs)
- **Multidioma con catálogo alineado** (sin fecha; no refs)
- **UI multilingüe que se adapta a CUALQUIER idioma** (2026-08-09; V2-089)
- **La autodetección de idioma colgaba SOLO de la voz — un canal de texto se quedaba en inglés para siempre** (2026-08-20; V2-101, V2-170)
- **TTS local por hardware (Metal)** (sin fecha; no refs)
- **TTS cloud FIABLE — ElevenLabs** (2026-07-13; V2-035)
- **STT local por hardware** (2026-07-12; no refs)
- **Sistema de widgets** (sin fecha; V2-017, V2-025)
- **Nombres + alias de widgets con CERTEZA de enrutamiento** (2026-08-01; V2-082)
- **CHAT y VOZ, INDEPENDIENTES — el icono es el único dueño del silencio** (2026-08-02; V2-054, V2-088)
- **El icono del altavoz MANDA — un solo interruptor para la voz** (2026-08-01; V2-087)
- **La RED es NATIVA, y hay clusters PÚBLICOS** (2026-08-01; V2-082, V2-086)
- **Selección PROGRESIVA de capacidades — el prompt es O(K), no O(N)** (2026-08-02; V2-035, V2-078, V2-082, V2-085)
- **Acciones de widget = FRONTERA datos/código + gate de irreversibilidad (NO de escalado)** (2026-07-11; V2-025)
- **Data-ops por FUNCTION-CALLING + resolución de referencias a items** (2026-07-11; V2-025, V2-026)
- **Widgets en BACKGROUND — ejecución OFF-SCREEN con ciclo declarado** (2026-07-12; V2-034)
- **Ciclo de vida de widgets + memoria — CREAR/MODIFICAR = SlowBrain; BORRAR = FlashBrain con confirmación** (2026-07-09; V2-017)
- **Widgets "backed" + supervisor** (sin fecha; INI-016)
- **navegador — navegador web REAL + agente de tareas web** (sin fecha; INI-016)
- **navegador — TAREAS: una tarea = una tarjeta = una pestaña** (sin fecha; INI-016)
- **El navegador es el ÚLTIMO recurso: primero se le pregunta a la RED** (2026-08-19; V2-167, V2-169)
- **Un código de idioma inventado no falla: es un idioma** (2026-08-21; V2-171, V2-248, V2-249, V2-251)
- **Un informe de lo que ya pasó no es una orden** (2026-08-21; V2-039, V2-047, V2-259, V2-261)
- **Dos búsquedas son dos hojas, y estrenar deja de significar borrar** (2026-08-21; V2-242, V2-257, V2-259)
- **El navegador MUESTRA y la hoja GUARDA** (2026-08-21; V2-192, V2-200, V2-223, V2-240, V2-257)
- **Un formulario que calla no se distingue de uno que funciona** (2026-08-21; V2-124, V2-256)
- **Para vigilar el ARTEFACTO, el artefacto tiene que contener lo que se comprueba** (2026-08-21; V2-171, V2-195, V2-253, V2-254, V2-255)
- **La regla estaba escrita en TRES sitios y aplicada en UNO** (2026-08-21; V2-242, V2-252, V2-253, V2-254)
- **Unos argumentos ILEGIBLES no son una acción sin argumentos** (2026-08-21; V2-171, V2-253)
- **El canal de TEXTO no relevaba — y era la TERCERA vez que `probe.py` se separaba del provider de voz** (2026-08-21; V2-252)
- **Un solo reloj para el «hoy» que se le DICE al worker** (2026-08-21; V2-250)
- **La píldora que se auto-avala: un aviso PROGRAMADO existe de verdad, o no se dice** (2026-08-21; V2-219, V2-249)
- **Un `ref` caducado decía QUÉ pasaba y no CÓMO salir** (2026-08-21; V2-203, V2-212, V2-236, V2-241, V2-247, V2-248)
- **Traer el elemento a la vista es una CORTESÍA, no el clic** (2026-08-21; V2-236, V2-247)
- **Un escalón que se atasca SIEMPRE no se penalizaba nunca** (2026-08-21; V2-244, V2-246)
- **Callar un escalón es legítimo; callar QUE LO CALLAS, no** (2026-08-21; V2-244)
- **246 tests verdes que ninguna suite ejecutaba, y TRES formas de desaparecer** (2026-08-21; V2-098, V2-243, V2-245)
- **Un SALDO agotado no es una cuota, y quedarse sin proveedor no es un tropiezo** (2026-08-21; V2-098, V2-158, V2-243)
- **Una píldora de fondo no es un hecho sobre la persona** (2026-08-21; V2-242)
- **La puerta avisaba UNA vez y el worker chocó TRES** (2026-08-21; V2-211, V2-236, V2-241)
- **El extractor exigía PRECIO, así que un fontanero devolvía CERO filas** (2026-08-21; V2-236, V2-240)
- **Un RELEVO no es una muerte** (2026-08-21; V2-198, V2-222, V2-237, V2-238, V2-239)
- **Un `native_sid` que MATÓ a un worker no se vuelve a armar** (2026-08-21; V2-237, V2-239)
- **La búsqueda dio la respuesta perfecta y MURIÓ dentro del worker** (2026-08-21; V2-199, V2-223, V2-226, V2-236)
- **El extractor PARTÍA el precio y no cogía el nombre** (2026-08-21; V2-234, V2-235)
- **La nota llevaba delante el CROMO DE NAVEGACIÓN, y el turno describió eso** (2026-08-20; V2-223, V2-234)
- **UN ENCARGO, UNA SUPERFICIE: el panal de hexágonos se RETIRA** (2026-08-20; V2-233)
- **El contrato de pantalla estaba en verde y el operador seguía sin ver nada** (2026-08-20; V2-199, V2-227, V2-233)
- **La nota del hallazgo llevaba TRES órdenes, y el turno obedeció la del medio** (2026-08-20; V2-223, V2-224, V2-226)
- **Decirlo una vez no es olvidarlo** (2026-08-20; V2-189, V2-221, V2-224)
- **El compositor de investigación LEÍA la cadena de proveedores y nunca la ESCRIBÍA** (2026-08-25; V2-225)
- **El prompt se contradecía a sí mismo, y el turno elegía la mitad cierta** (2026-08-20; V2-199, V2-221, V2-222)
- **Lo que el navegador ENCUENTRA no llegaba a nadie** (2026-08-20; V2-215, V2-220, V2-223)
- **Una tarea de fondo MUERTA no es una pregunta pendiente** (2026-08-20; V2-185, V2-189, V2-193, V2-196, V2-198, V2-213, V2-220, V2-221)
- **El aviso proactivo existía y no tenía dónde llegar** (2026-08-20; V2-073, V2-214, V2-215, V2-220)
- **El worker dejaba de trabajar en la aridad de NUESTRO propio CLI** (2026-08-20; V2-117, V2-153, V2-219)
- **Un hecho recogido en TODAS partes y dicho en NINGUNA** (2026-08-20; V2-185, V2-193, V2-197, V2-202, V2-207, V2-211, V2-212, V2-215)
- **El aviso existía y su CONTENIDO estaba roto** (2026-08-20; V2-214)
- **DOS REGRESIONES MÍAS, medidas el mismo día y en el único caso 5/5 del tablero** (2026-08-20; V2-176, V2-202, V2-209, V2-210)
- **«Prueba otro sitio» sin decir CUÁL es un deseo, no una instrucción** (2026-08-20; V2-176, V2-185, V2-186, V2-213)
- **Un `usage` dice la FORMA, no el ERROR** (2026-08-20; V2-203, V2-212)
- **La puerta es NUESTRA: el worker se muere en ella y en silencio** (2026-08-20; V2-117, V2-202, V2-211)
- **Un dato del mundo, dicho con una cifra y sin consultar nada** (2026-08-20; V2-022, V2-135, V2-210)
- **Desde fuera del proceso, «el muro no se anotó» y «se anotó y el turno lo ignoró» se veían IDÉNTICOS** (2026-08-20; V2-176, V2-207)
- **La MISMA cita dos veces, ahora por la data-op del modelo** (2026-08-27; V2-194, V2-208)
- **«Aquí lo tienes» sobre una tarjeta vacía — y la frase es NUESTRA** (2026-08-20; V2-176, V2-209)
- **Le decíamos al worker que mirara una captura que no estaba en disco** (2026-08-20; V2-117, V2-203, V2-205)
- **El puente del payload contestaba con el OSError pelado, y el worker lo leía como un callejón sin salida** (2026-08-20; V2-117, V2-186, V2-203)
- **El confirm-gate paró un clic irreversible y no preguntó a NADIE** (2026-08-20; V2-126, V2-153, V2-202)
- **Una tarea de verificación se cuelga del CASO, no del arreglo** (2026-08-20; V2-133, V2-199, V2-200, V2-201)
- **Cada cara del bloque del navegador tiene que poder DISPARARSE** (2026-08-20; V2-176, V2-199, V2-200, V2-201)
- **El arreglo anterior no estaba roto: estaba MUERTO** (2026-08-20; V2-185, V2-192, V2-199, V2-200)
- **Un test que no recorre el camino real prueba que el código compila, no que funciona** (2026-08-20; V2-126, V2-190, V2-198, V2-199)
- **Una sesión de WORKER que acaba desaparecía del estado** (2026-08-20; V2-150, V2-197, V2-198)
- **Dos listas de estados que había que mantener sincronizadas — y `open` llevaba en el hueco desde siempre** (2026-08-20; V2-196, V2-197)
- **Una tarea CANCELADA no estaba ni viva ni terminada** (2026-08-20; V2-150, V2-176, V2-190, V2-195, V2-196)
- **La captura forense de un turno guardaba la persona y tiraba el ESTADO** (2026-08-20; V2-195)
- **La suite escribía en la agenda REAL del operador: 328 citas de prueba** (2026-08-20; V2-194)
- **La cita se apuntaba DOS veces** (sin fecha; V2-153, V2-186, V2-189, V2-194)
- **Con varias tareas vivas, el estado MANDABA entregar una y no decía cuál** (2026-08-20; V2-189, V2-192, V2-193)
- **REGRESIÓN PROPIA: pasé de demasiado optimista a demasiado pesimista** (2026-08-20; V2-185, V2-192)
- **«Sí, adelante» → «Hecho.» → «¿Ya está cancelada del todo?»** (2026-08-20; V2-176, V2-189)
- **Una tarea parada esperando a que el operador ENTRE decía «te dará el resultado sola»** (2026-08-20; INI-016, V2-167, V2-176, V2-185)
- **Un hecho que solo vive un turno es un hecho que la conversación pierde** (2026-08-20; V2-150, V2-171, V2-176, V2-190)
- **Una confirmación que CADUCA borraba el hecho de que existió** (2026-08-20; V2-138, V2-150, V2-190)
- **El relleno de espera decía CUATRO veces la misma frase, y no lo decía el modelo** (2026-08-20; V2-038, V2-133, V2-189)
- **El muro más silencioso: la página de error del PROPIO sitio** (2026-08-20; V2-187, V2-188)
- **Un hecho que no se puede decir en voz alta es un hecho que no llega** (2026-08-20; V2-145, V2-150, V2-185, V2-187)
- **El operador pidió el aviso en SUBJUNTIVO y el backstop no lo reconoció** (2026-08-20; V2-151, V2-167)
- **Una respuesta que aún PREGUNTA archivaba una cita hecha con su propia pregunta** (2026-08-20; V2-167)
- **El muro del cuerpo DISPARÓ, y el hecho se borró al re-enrutarse** (2026-08-20; V2-167, V2-176)
- **«¿Hay algo corriendo?» era la pregunta equivocada** (2026-08-20; V2-132, V2-176, V2-196)
- **Una búsqueda vacía y una búsqueda IMPOSIBLE eran el mismo dato** (2026-08-30; V2-176)
- **El traspaso de inicio de sesión no estaba cableado en el canal de TEXTO** (2026-08-20; V2-153, V2-176)
- **El día del aviso podía estar SOLO en la frase del operador** (2026-08-20; V2-121, V2-167)
- **Una fecha sola no es un compromiso** (2026-08-20; V2-167)
- **El muro y el atasco NUNCA llegaron al worker** (2026-08-20; V2-167, V2-186)
- **«No me habías pedido eso» era VERDAD** (2026-08-20; V2-176)
- **Un proveedor roto no se le decía a NADIE en el canal de texto** (2026-08-20; V2-176)
- **Un muro puede estar en el CUERPO de la página, con URL normal y status 200** (2026-08-20; V2-167)
- **El atasco llegaba al TURNO y no al WORKER** (2026-08-20; V2-167, V2-186)
- **- **Una salvedad no compite con una promesa: el estado PROMETÍA que la tarea iba a terminar sola, también** (2026-08-20; V2-152, V2-167, V2-185)
- **El turno que fija la FECHA no es el que dice el QUÉ** (2026-08-20; V2-075, V2-132, V2-151, V2-176)
- **El turno corría con un tope que NO cabía la tool más importante del sistema** (2026-08-20; V2-171)
- **Una ruta de FastAPI no sabe qué función viene detrás del decorador** (2026-08-19; V2-169)
- **navegador — AUTENTICACIÓN = abrir un navegador REAL** (2026-07-10; INI-016)
- **«Una sola mente» — el FlashBrain conduce TODA conversación** (2026-07-25; V2-069)
- **El SEGUNDO backend de Brain Worker: Codex — y su frontera de seguridad es DISTINTA** (2026-08-12; V2-010, V2-038)
- **El TERCER backend: Grok Build — y la elección de worker es una TERNA, no una casilla** (2026-08-13; no refs)
- **Los Brain Workers no dependen de UN proveedor — cadena + relevo automático** (2026-08-09; no refs)
- **Energy metering — cobertura real, no solo tabla de tarifas** (2026-08-16; INI-019, INI-020)
- **Control central de proveedores en el perfil cloud** (2026-08-05; INI-019)
- **«Homeostasis» — el LATIDO AUTÓNOMO del sistema** (2026-07-25; V2-070)
- **REHIDRATACIÓN — el trabajo que corta un reinicio se recoge, no desaparece** (2026-08-12; no refs)
- **El ESCRITORIO se rehidrata — y el `localStorage` es per-ORIGEN** (2026-08-12; no refs)
- **Canal nativo MeshKore** (2026-07-26; V2-069, V2-072, V2-075, V2-076)
- **Una tarea/flujo SOLO nace de CUATRO fuentes — el pulso NUNCA crea trabajo por tener un loop** (2026-08-16; no refs)
- **- **`voice.trace.active()` — un puntero EXPLÍCITO para eventos que el ContextVar nunca puede ver (2026-08-16,** (2026-08-16; no refs)
- **- **El gate de atención en modo `always` (el default, micro SIEMPRE abierto — permanente, NO es algo a reverti** (2026-08-17; V2-093, V2-097, V2-105, V2-109)
- **- **Fusionar dos flujos que resultan ser la MISMA tarea — la capacidad existe, el disparo automático NO (pass** (2026-08-16; V2-105)
- **El motor no arrancaba NUNCA en frío — deadlock de reentrancia en `memory/db.py::get_db()`** (2026-08-16; V2-105, V2-106)
- **Seguridad del canal de cluster** (2026-07-26; V2-021, V2-069, V2-071)
- **Reglas en TRES niveles + PACTO de conversación agente-agente** (2026-07-25; V2-046, V2-067, V2-071, V2-072)
- **Criterio de conversación por INTELIGENCIA — parar/ceder el turno cuando no fluye** (2026-07-26; V2-010, V2-073, V2-075)
- **Sello de VERSIÓN — saber qué código corre y qué versión generó cada línea** (2026-07-26; V2-074)
- **Proveedor Architect** (sin fecha; no refs)
- **Mensajería personal UNIFICADA con triaje** (sin fecha; V2-051, V2-052)
- **Configuración MANEJADA POR LA INTERFAZ — "instala una vez, todo lo demás desde la UI"** (sin fecha; V2-083)
- **Tema dark/light** (sin fecha; no refs)
- **- **Controles del orbe = «EL OJO» — 7 iconos como párpado superior + ECG como párpado inferior (el orbe = iris** (2026-07-22; V2-014, V2-016, V2-039)
- **LA PILA de Energy — el saldo se VE antes de agotarse** (2026-08-13; no refs)
- **Visor de memoria (🧠 «mapa de la memoria») — DOS VISTAS** (2026-07-10; V2-014)
- **ADMISIÓN — cuando el proceso NO es la frontera, sin sesión verificada no se sirve nada** (2026-08-13; no refs)
- **PARAR ES PARAR — el interruptor global vive en el SERVIDOR, y un widget DECLARA lo que produce** (2026-08-13; V2-039, V2-065, V2-092)
- **PARAR ES PARAR, de verdad: ni sesión fantasma con el agente parado, ni turno cortado a medias** (2026-08-15; V2-092)
- **La ESPERA se oye, y el veredicto de latencia ya puede culpar al proveedor** (sin fecha; V2-093)
- **RELEVO por latencia del cerebro de voz** (2026-08-14; V2-094, V2-097)
- **DeepSeek DIRECTO cura el TTFT, y por eso es RELEVO y no titular** (2026-08-17; V2-094, V2-097)
- **El turno se cierra cuando la frase ACABA, no cuando hay silencio** (2026-08-14; INI-012, V2-092, V2-095, V2-096, V2-102)
- **Una frase en DOS TIEMPOS es UNA petición — y el fragmento no genera nada** (2026-08-02; V2-095, V2-096)
- **SELECCIÓN PROGRESIVA de tools — el turno lleva su RUMBO, no el catálogo entero** (2026-08-02; V2-085, V2-096)
- **Architecture/modularization pass — real duplication killed, three god-files split, one deliberately NOT split** (2026-08-16; V2-095, V2-096, V2-098)
- **V2-098 follow-up: FlashBrain modularization, 9 splits executed** (2026-08-17; V2-076, V2-098, V2-108, V2-109, V2-112)
- **- **Floating feedback widget — a self-hosted engine's first outbound call, and the control-plane's first** (2026-08-16; INI-023, V2-100, V2-256)
- **First-run language onboarding — a blocking ceremony, and the alias-pack extension point finally built** (2026-08-16; V2-101)
- **Turn-completeness judge — real intelligence replaces "hold forever"** (2026-08-16; V2-095, V2-096, V2-097, V2-102)
- **RESET left stale rows on screen and never touched the chat wall** (2026-08-16; no refs)
- **Memory — write-path self-healing, and REM stops being purely additive** (2026-08-16; V2-103)
- **REM — gate de fidelidad antes de escribir/demotar un insight** (2026-08-16; V2-075, V2-103, V2-104)
- **Corpus longitudinal con contradicciones + REM real end-to-end (V2-107)** (2026-08-17; V2-107)
- **Susurro's friction window had no recency boundary — an 11-hour-old exchange got escalated as "now" (V2-108)** (2026-08-17; V2-108)
- **- **A worker-dispatched browser task's own trace was empty for its whole lifetime — TaskBrowser used ambient** (2026-08-17; V2-108)
- **La query de recall llevaba pegada la nota `[SISTEMA]` del turno — el modelo alucinó un familiar (V2-110)** (2026-08-17; V2-110)
- **- **Grafo multi-hop (PPR) + bi-temporal explícito — dos piezas de V2-111 §9, construidas por delante de las** (2026-08-17; V2-095, V2-102, V2-111)
- **- **An escalated flow closed itself seconds after opening — a structural race, not an occasional one (V2-113,** (2026-08-17; V2-113)
- **- **Lead-in filler leaked into the chat wall AFTER the real reply — now its own module, and structurally unabl** (2026-08-18; V2-096, V2-101, V2-102, V2-122)
- **- **Showing data is the generic sheet's job, not a reason to write a component — and a created widget was neve** (2026-08-18; V2-098, V2-115)
- **- **One sentence must be ONE flow — and flow continuity can no longer hang on getting completeness right; plus** (2026-08-18; V2-090, V2-095, V2-096, V2-097, V2-102, V2-116)
- **- **A worker started with the engine's own developer manual inside it, and its raw provider error was delivere** (2026-08-18; V2-105, V2-117)
- **- **The flow-merge TRIGGER, built at last — and neither of the two resolvers we already had could do it (V2-12** (2026-08-18; V2-029, V2-075, V2-090, V2-105, V2-113, V2-117, V2-123)
- **- **A SECOND SHELL over one engine — the mobile PWA, and the two contracts that made it cheap (V2-124, 2026-08** (2026-08-18; V2-088, V2-092, V2-124)
- **La memoria estaba sana; la deuda era ESTRUCTURAL — y tres imports inversos se BENDICEN, no se arreglan** (2026-08-23; V2-114, V2-117, V2-273)
- **Un recall que NO llega se veía igual que una memoria vacía** (2026-08-25; V2-031, V2-273, V2-311)
- **Un encargo viejo viajaba en CADA prompt como un hecho permanente de la persona** (2026-08-26; V2-254, V2-337)
- **La SONDA de backend esperaba como una llamada real: 20,3 s en el PRIMER acceso a memoria** (2026-08-26; V2-103, V2-311, V2-349)
- **El widget de YouTube tiene LISTA, y `add` NUNCA arranca la reproducción (V2-366, 2026-08-27)** (2026-08-27; V2-092, V2-366)
- **Buscar vídeos va al REPRODUCTOR, no a la hoja de resultados (V2-402, 2026-08-27)** (2026-08-27; V2-366, V2-380, V2-402)
- **- **El Brain Worker corre con lo que la NUBE puede contratar, y un escalón que no ve se declara ciego** (2026-08-27; V2-403)
- **El deck móvil se NAVEGA, y su restore alcanzó la paridad V2-351 (V2-474, 2026-08-29)** (2026-08-29; V2-351, V2-465, V2-474)
- **- **El arranque en frío enseñaba claves i18n crudas — y la leyenda buena llegaba sin que la viera nadie** (2026-08-29; V2-124, V2-481)
- **Cinco filas eran pocas, y decirle que hay más no es enseñárselas (V2-479, 2026-08-29)** (2026-08-29; V2-374, V2-479)
- **A terminal field cannot tell a process, and a zero must say why it is zero (V2-512, 2026-08-30)** (2026-08-30; V2-506, V2-512)
- **The instrument must not turn a coincidence into a cause (V2-506, 2026-08-30)** (2026-08-30; V2-506)
- **A retired provider may not be named by ANY ladder (V2-504, 2026-08-30)** (2026-08-30; V2-500, V2-504)
- **A lab measures the PRODUCT, not the machine it runs on (V2-502, 2026-08-30)** (2026-08-30; V2-500, V2-502)
- **- **The memory's semantic space comes from a CLOUD provider, and a paid call is metered (V2-501,** (2026-08-30; V2-103, V2-501)
- **El reparto de modelos vive en UNA tabla pública, y un solo failover por servicio (V2-500, 2026-08-30)** (2026-08-30; V2-500)
- **Z.AI es del BRAIN WORKER y de nadie más (V2-496, 2026-08-30 — deroga V2-462)** (2026-09-01; V2-462, V2-496)
- **- **El compositor del brief pedía «no razones» a un modelo que NO PUEDE dejar de hacerlo, y toda búsqueda** (2026-08-29; V2-225, V2-488)
- **- **La red MeshKore estaba construida, verificada en vivo y NUNCA se consultaba — dos causas apiladas y** (2026-08-29; V2-118, V2-167, V2-211, V2-486, V2-487)
- **Una frase deja DOS píldoras críticas, y el corte expulsaba un hecho de SEGURIDAD (V2-491, 2026-08-29)** (2026-08-29; V2-123, V2-490, V2-491)
- **- **DOS puertas por las que entra un vector de otro espacio, y ninguna fallaba con ruido (V2-484 y V2-485,** (2026-08-29; V2-482, V2-484, V2-485)
- **La voz de V2-497 estaba colgada DESPUÉS de la puerta que más se cierra (V2-503, 2026-08-30)** (2026-08-30; V2-311, V2-482, V2-484, V2-497, V2-503)
- **Un reparador INERTE parecía un reparador SIN TRABAJO (V2-497, 2026-08-29)** (2026-08-29; V2-311, V2-482, V2-485, V2-497)
- **Los GUSTOS son estado ACTIVO, y el slot obvio está medido como MUERTO (V2-498, 2026-08-29)** (2026-08-29; V2-337, V2-491, V2-497, V2-498)
- **- **Una limitación de INGESTIÓN dicha sin palabra de categoría también es crítica (V2-499, 2026-08-29,** (2026-08-29; V2-490, V2-491, V2-499)
- **Un vector de espacio AJENO no lo repara nadie, nunca (V2-482, 2026-08-29)** (2026-08-29; INI-026, V2-482)
- **La TERCERA puerta al scheduler no normalizaba (V2-480, 2026-08-29)** (2026-08-29; V2-151, V2-249, V2-480)
- **La puerta del backstop de entrega tampoco era la LONGITUD (V2-478, 2026-08-29)** (2026-08-29; V2-364, V2-371, V2-478)
- **Una garantía escrita en un solo idioma es un defecto para todos los demás (V2-475, 2026-08-29)** (2026-08-29; V2-475)
- **La entrega se NOMBRA y lo no verificable no se da por cumplido (V2-469, 2026-08-29)** (2026-08-29; V2-341, V2-469)
- **Un caso BLOQUEADO no es una avería, ni un turno que gastar cada vuelta (V2-448, 2026-08-28)** (2026-08-28; V2-260, V2-448)
- **Un solo formateador de fila (V2-455, 2026-08-28)** (2026-08-28; V2-240, V2-451, V2-455)
- **La sesión NUNCA pide la cámara — mic-only (V2-456, 2026-08-28)** (2026-08-28; V2-088, V2-456)
- **Cadena de buscadores de imágenes (V2-466, 2026-08-28)** (2026-08-28; V2-466)
- **El reproductor publica su lista y el visor tiene teclado (V2-465, 2026-08-28)** (2026-08-28; V2-026, V2-380, V2-465)
- **La ronda deja un VÍDEO — modo escaparate + grabador (V2-464, 2026-08-28)** (2026-08-28; V2-464)
- **La tarjeta se abre donde aterrizan los datos (V2-463, 2026-08-28)** (2026-08-28; V2-346, V2-463)
- **Z.AI: el plan primero, los créditos después (V2-462, 2026-08-28)** (2026-08-28; V2-458, V2-462)
- **Un MATIZ sobre una foto no es un encargo · y la conversación por API se VE (V2-461, 2026-08-28)** (2026-08-28; V2-032, V2-461)
- **Un agente del plató arranca con la sesión EN BLANCO (V2-460, 2026-08-28)** (2026-08-28; V2-460)
- **Tres agentes en esta máquina, tres puertos, y ninguno se mueve (V2-459, 2026-08-28)** (2026-08-28; V2-459)
- **Enseñar una foto es un turno de 3 s, no un encargo de 355 (V2-457, 2026-08-28)** (2026-08-28; V2-402, V2-457)
- **Un saldo agotado apaga a los escalones de su MISMA cuenta (V2-458, 2026-08-28)** (2026-08-28; V2-243, V2-252, V2-458)
- **La oferta de PARAR se hace una vez — el hecho se queda (V2-454, 2026-08-28)** (2026-08-28; V2-131, V2-224, V2-454)
- **El recall que NO llegó se cuenta — «preguntó lo que ya sabía» tiene DOS causas (V2-453, 2026-08-28)** (2026-08-28; V2-311, V2-432, V2-453)
- **- **El prompt está en castellano y el operador habla inglés: el modelo copiaba su idioma (V2-452,** (2026-08-28; V2-221, V2-452)
- **Las filas de la hoja viajan aunque NO haya navegador (V2-451, 2026-08-28)** (2026-08-28; V2-259, V2-432, V2-438, V2-441, V2-444, V2-451)
- **Un precio de mercado ANTES de entregar nada — y los TRES caminos de entrega (V2-450, 2026-08-28)** (2026-08-28; V2-223, V2-450)
- **La entrega multimedia no está en la hoja (V2-445, 2026-08-28)** (2026-08-28; V2-366, V2-402, V2-445)
- **El mismo defecto en el SEGUNDO bloque, y era el que disparaba (V2-444, 2026-08-28)** (2026-08-28; V2-222, V2-443, V2-444)
- **Sin filas, lo único que hay es la PALABRA del worker (V2-443, 2026-08-28)** (2026-08-28; V2-152, V2-238, V2-249, V2-330, V2-358, V2-440, V2-443)
- **Pedirlo dos veces no es hacerlo dos veces (V2-442, 2026-08-28)** (2026-08-28; V2-123, V2-442)
- **«Le pedimos lo imposible»: avisado de que había algo y servido con CERO filas (V2-441, 2026-08-28)** (2026-08-28; V2-330, V2-441)
- **El censo del INSTANTE separa dos causas que se veían idénticas (V2-440, 2026-08-28)** (2026-08-28; V2-330, V2-439, V2-440)
- **`results::X` y `X` son la MISMA hoja, y una volvía VACÍA (V2-439, 2026-08-28)** (2026-08-28; V2-242, V2-259, V2-439)
- **La cara dice que hay filas y la hoja no las da (V2-438, 2026-08-28)** (2026-08-28; V2-438)
- **Un elemento muerto dice qué hacer (V2-437, 2026-08-28)** (2026-08-28; V2-437)
- **Una memoria rechazada dice POR QUÉ (V2-436, 2026-08-28)** (2026-08-28; V2-344, V2-436)
- **El worker PUEDE escribir lo que le decimos que escriba (V2-435, 2026-08-28)** (2026-08-28; V2-435)
- **Un RELEVO no es un encargo nuevo, tampoco para quien LEE la hoja (V2-434, 2026-08-28)** (2026-08-28; V2-432, V2-434)
- **El puente del worker habla el vocabulario de widgets (V2-433, 2026-08-28)** (2026-08-28; V2-429, V2-433)
- **La hoja llena y el prompt diciendo que no (V2-432, 2026-08-28)** (2026-08-28; V2-352, V2-432)
- **Un «no» bien fundado es una ENTREGA (V2-431, 2026-08-28)** (2026-08-28; V2-431)
- **El precio que DICE es el que TIENE (V2-430, 2026-08-28)** (2026-08-28; V2-430)
- **Un comando rechazado dice qué se intentó (V2-429, 2026-08-28)** (2026-08-28; V2-424, V2-426, V2-429)
- **Un traceback se recorta por la COLA (V2-428, 2026-08-28)** (2026-08-28; V2-421, V2-425, V2-428)
- **La apertura del tester no puede recitar nuestra hoja (V2-427, 2026-08-28)** (2026-08-28; V2-427)
- **El `cd` bloqueado, y la premisa falsa que lo provoca (V2-426, 2026-08-28)** (2026-08-28; V2-426)
- **El error de payload dice QUÉ falló (V2-425, 2026-08-28)** (2026-08-28; V2-425)
- **El `&` solo también lo bloquea nuestro guarda, y no estaba en la regla (V2-424, 2026-08-28)** (2026-08-28; V2-412, V2-424)
- **Una fila INFRA dice CUÁL (V2-423, 2026-08-28)** (2026-08-28; V2-423)
- **La misma búsqueda dos veces no son dos búsquedas (V2-422, 2026-08-28)** (2026-08-28; V2-422)
- **Un payload que falta dice lo que SÍ hay (V2-421, 2026-08-28)** (2026-08-28; V2-421)
- **El denominador es lo que se le MOSTRÓ, no lo que hay en la hoja (V2-420, 2026-08-28)** (2026-08-28; V2-420)
- **Un worker MIRANDO EL MENÚ no es un worker estrellado (V2-418, 2026-08-28)** (2026-08-28; V2-418)
- **Una función que decide fechas leía DOS relojes (V2-419, 2026-08-28)** (2026-08-28; V2-419)
- **El plató no para: 24/7 con guardián (V2-417, 2026-08-28)** (2026-08-28; V2-417)
- **El marcador dice con qué CEREBRO se midió cada fila (V2-415, 2026-08-27)** (2026-08-27; V2-415)
- **Que nos BLOQUEEN no es que el mundo esté vacío (V2-414, 2026-08-27)** (2026-08-27; V2-414)
- **Una recarga es INVISIBLE desde el motor, así que se vuelve a probar (V2-413, 2026-08-27)** (2026-08-27; V2-243, V2-413)
- **La búsqueda mira desde donde vive la persona (V2-411, 2026-08-27)** (2026-08-27; V2-411)
- **El prompt del worker no enseña lo que nuestro guarda bloquea (V2-412, 2026-08-27)** (2026-08-27; V2-412)
- **El dedup decía que NO y no decía POR QUÉ (V2-507, 2026-08-30)** (2026-08-30; V2-507)
- **Un encargo CONFIRMADO conserva su hoja (V2-508, 2026-08-30)** (2026-08-30; V2-117, V2-128, V2-227, V2-238, V2-259, V2-507, V2-508, V2-509)
- **Lo que vuelve de una búsqueda es una PISTA, y la NOTA seguía ordenando entregarla (V2-510, 2026-08-30)** (2026-08-30; V2-222, V2-226, V2-234, V2-236, V2-479, V2-508, V2-510)
- **Lo que CUENTA lo que pasó no es lo que TRAE algo (V2-511, 2026-08-30)** (2026-08-30; V2-236, V2-240, V2-321, V2-364, V2-511)
- **The gate reads the ORDER, not the words (V2-509, 2026-08-30)** (2026-08-30; V2-128, V2-507, V2-508, V2-509)
- **A SHIPPED widget is forked, never edited in place — and never deleted from disk (V2-515, 2026-08-31)** (2026-08-31; V2-515, V2-518)
- **A catalog costs nothing until it is CONNECTED (V2-526, 2026-08-31 — DESIGN, no code yet)** (2026-08-31; V2-078, V2-083, V2-169, V2-520, V2-526)
- **- **Stopping is DISCARDING — abandon_work (V2-528, 2026-08-31; supersedes the 2026-07-10 freeze-to-resume** (2026-08-31; V2-214, V2-528)
- **- **A `[SISTEMA]` note is never the errand: the SECOND door, and a question is not a promise (V2-534,** (2026-09-01; V2-049, V2-095, V2-530, V2-534)
- **A NEGATED clause is not a promise (V2-534 follow-up, 2026-09-01)** (2026-09-01; V2-049, V2-095, V2-252, V2-534)
- **STABLE PREFIX FIRST — the prompt's block order is what the provider's cache can see (V2-536, 2026-09-01)** (2026-09-01; V2-097, V2-255, V2-533, V2-536)
- **The MURAL — placement that dodges the chat, the widget RAIL, and auto-arrange (V2-537, 2026-09-01)** (2026-09-01; V2-087, V2-464, V2-474, V2-537)
- **The rail is DOCKED, and a card gets the size its manifest declares (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **A sheet is for RESULTS, and an ITEM is a real candidate (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **Figures are made SPEAKABLE at the TTS node, and only there (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **An undeclared capability is one the model NARRATES — the agenda's view is an action (V2-540, 2026-09-01)** (2026-09-01; INI-027, V2-521, V2-540)
- **A canvas click has to land on the sheet the operator is LOOKING AT (V2-540, 2026-09-01)** (2026-09-01; V2-259, V2-540)
- **Who may interrupt is CONFIGURATION — per-connector notification policy (V2-532, 2026-09-01)** (2026-09-01; V2-520, V2-522, V2-527, V2-532)
- **- **The turn clock tells OUR share — pre-turn attribution + prefix-cache visibility + pooled judges (V2-533,** (2026-09-01; V2-533, V2-536)
- **- **Inside an active conversation, NOBODY judges — the attention gate went deaf mid-dialogue (V2-531,** (2026-09-01; V2-531)
- **An errand has a NAME, and it is not a slice of the conversation (V2-530, 2026-08-31)** (2026-08-31; V2-151, V2-199, V2-530)
- **The lead-in filler sounds BEFORE the reply — it IS the reply's first segment (V2-529, 2026-08-31)** (2026-08-31; V2-122, V2-529)
- **The proactive delivery QUEUE — one message at a time (V2-527, 2026-08-31)** (2026-08-31; INI-008, V2-047, V2-525, V2-527)
- **⏻ ON has to START it — the reload was the tell (V2-525, 2026-08-31)** (2026-08-31; V2-092, V2-525)
- **The BOUNDARIES of a work session (V2-524, 2026-08-31)** (2026-08-31; V2-524)
- **Messaging is a MAIN widget now — the operator's spec (V2-521/522/523, 2026-08-31)** (2026-08-31; V2-051, V2-520, V2-521, V2-522, V2-523)
- **Connecting a channel can be ASKED FOR (V2-520, 2026-08-31)** (2026-08-31; V2-051, V2-520)
- **The attachment can never swallow the message (V2-519, 2026-08-31)** (2026-08-31; V2-519)
- **The widget's CONFIG corner + confirmations live in the CHAT (V2-518, 2026-08-31)** (2026-08-31; V2-518)
- **CONTACTOS: un directorio para TODAS las identidades — y su vista contesta (V2-541, 2026-09-01)** (2026-09-01; V2-124, V2-208, V2-473, V2-523, V2-540, V2-541)
- **Borrar una superficie es MUDAR lo que llevaba, o es perderlo (V2-542, 2026-09-01)** (2026-09-01; V2-538, V2-542)
- **- **MENSAJERÍA: la vista es una acción que contesta, los medios se VEN, y las órdenes llegan a las apps** (2026-09-01; V2-520, V2-531, V2-541, V2-543)
- **- **The INSIDE of a widget belongs to widget_data — the prompt no longer contradicts the catalog (V2-544,** (2026-09-01; V2-222, V2-467, V2-539, V2-544)
- **- **What a pure show may RUN is decided by the ACTION, not by the words — and the lens phrases resolve before** (2026-09-01; V2-544, V2-545)
- **The messaging widget FOLLOWS the real apps instead of drifting from them (V2-546, 2026-09-01)** (2026-09-01; V2-546)
- **A KNOWN phrase skips the model — the ACTION MAP (V2-539, 2026-09-01)** (2026-09-01; V2-095, V2-539, V2-545)

#### Movidas el 2026-09-14
- **A voice fullscreen order must change the screen — requestFullscreen is gesture-gated and rejects in SILENCE (V2-583, 2026-09-05)** (2026-09-05; V2-583)
- **The video widget gets an ACCOUNT — the video connector family, and the interior anchors to the parent (V2-597, 2026-09-05)** (2026-09-05; V2-034, V2-557, V2-564, V2-597)
- **A fullscreen order is about a SCREEN STATE, never a close — and cinema goes above everything (V2-600, 2026-09-05)** (2026-09-05; V2-583, V2-600)
- **A stale connector error never greets a fresh open — and the state line OUTRANKS the window (V2-582, 2026-09-05)** (2026-09-05; V2-221, V2-567, V2-582)
- **The daemon is the piece that reads somebody's disk, so it gets an attacker with a name (V2-575 P0 security pass + P4, 2026-09-06)** (2026-09-06; V2-575, V2-601)
- **The controls exist; a ROBOT runs them now — the audit remediation tier (V2-601 T-01..T-14, 2026-09-05/06)** (2026-09-05; V2-090, V2-121, V2-348, V2-554, V2-555, V2-600, V2-601)
- **The A2A card names SKILLS, not a contact URL (V2-616, 2026-09-08)** (2026-09-08; V2-616)
- **An empty answer is not a served errand (V2-602, 2026-09-06)** (2026-09-06; V2-596, V2-602)
- **The engine is licensed: Sustainable Use License 1.0, fair-code (V2-601 T-03, 2026-09-06)** (2026-09-06; INI-027, V2-601)
- **This file compacts by ARCHIVING, never by deleting (V2-601 T-18, 2026-09-06)** (2026-09-06; V2-601)
- **A catch-all category must not outrank a specific match (V2-599, 2026-09-05)** (2026-09-05; V2-599)
- **A broken upstream is not a request for fields (V2-598, 2026-09-05)** (2026-09-05; V2-487, V2-598)
- **The workflow table: what serves this kind of errand (V2-594, 2026-09-05)** (2026-09-05; V2-487, V2-594)
- **A free tier arrives as one entry in a LIST (V2-593, 2026-09-05)** (2026-09-05; V2-593)
- **Zero agents beats a wrong one (V2-581, 2026-09-05)** (2026-09-05; V2-580, V2-581)
- **The answer says what the agent claims to be (V2-580, 2026-09-05)** (2026-09-05; V2-580)
- **A mesh agent can gate its skills behind a bearer of its own issue (V2-579, 2026-09-05)** (2026-09-05; V2-579, INI-030)
- **The phone is HEARD, and the dock is the operator's (V2-573, 2026-09-04)** (2026-09-04; V2-573)
- **The mouth matches the order (V2-572, 2026-09-03)** (2026-09-03; V2-210, V2-572)
- **Dependency directions are a ratchet, like sizes (V2-569, 2026-09-03)** (2026-09-03; V2-569)

#### Movidas el 2026-09-11
- **La agenda no inventa, y el aviso por defecto es SUYO (V2-473, 2026-08-29)** (2026-08-29; V2-222, V2-341, V2-473)
- **La acción que ES el propósito de un widget es la que se salta el censo (V2-547, 2026-09-02)** (2026-09-02; V2-545, V2-547)
- **El catálogo enrutaba con la frase cortada a mitad de palabra (V2-547, 2026-09-02)** (2026-09-02; V2-027, V2-526, V2-545, V2-547)
- **Un fallo de RECUPERACIÓN es invisible cuando sobrevive un vecino plausible (V2-548, 2026-09-02)** (2026-09-02; V2-457, V2-547, V2-548)
- **LA HOJA EN BLANCO: una sola cosa para leer, y el borde que la mantiene pequeña (V2-549, 2026-09-02)** (2026-09-02; V2-457, V2-463, V2-547, V2-549)
- **Lo que se perdía del chat no era la posición, era estar ABIERTO (V2-550, 2026-09-02)** (2026-09-02; V2-550)
- **Media tarjeta no es una tarjeta más pequeña (V2-551, 2026-09-02)** (2026-09-02; V2-551)
- **Un glifo que cambia de significado bajo la mano hay que leerlo antes de usarlo (V2-552, 2026-09-02)** (2026-09-02; V2-551, V2-552)
- **Un número de versión no sabe si el navegador tiene que recargar (V2-553, 2026-09-02)** (2026-09-02; V2-551, V2-553)
- **Un `COPY` no significa que el directorio viaje (V2-554, 2026-09-02)** (2026-09-02; V2-500, V2-554)
- **Mover código «byte por byte» cambia sus GLOBALS (V2-555, 2026-09-02)** (2026-09-02; V2-554, V2-555)
- **BUSCAR ANUNCIOS es UNA tool, y el MÓDULO decide si sirve el turno o escala (V2-556, 2026-09-02)** (2026-09-02; V2-117, V2-222, V2-510, V2-556)
- **ARCHIVOS EN LA NUBE: el tramo de permiso es el DISEÑO, y un permiso que no puede listar no es un disco vacío (V2-557, 2026-09-02)** (2026-09-02; V2-507, V2-520, V2-526, V2-540, V2-541, V2-545, V2-557)
- **A refusal has to name what you PASTED, and a retry has to move something (V2-559, 2026-09-03)** (2026-09-03; V2-559)

## Testing y rueda de mejora (INI-013)

zaelar se prueba **solo, sin micrófono humano**, con un agente tester independiente que HABLA con zaelar y un
JUEZ que evalúa lo que zaelar HACE (no lo que dice). **El PLAYBOOK autocontenido de "cómo se prueba" (trigger "lanza
un test del bot", Paso 0 de alineación, prioridades, evaluación, archivado) vive en
`.meshkore/docs/ops/zaelar-testing.md`**; el catálogo legible de escenarios en `tests/voice/e2e/agent/anexos/catalogo-escenarios.md`
y el histórico de informes por día en `tests/voice/e2e/agent/reports/<YYYYMMDD>-<desc>/`. Docs canónicas:
**«¿funciona todo bien?» → `./.venv/bin/python tests/run_testmap.py`**: el MAPA DE TESTS navegable — todo el testing
ordenado por **DOMINIO → CASO DE USO → CANAL** (9 dominios, nodos `N.M`), responde con el árbol numerado
"1.1 ✅, 1.2 ✅, 2.1 ✅…" y marca aparte los nodos VIVOS (exigen `make run`). Es la fuente de verdad de qué fichero
cubre cada caso; la narrativa/segunda-opinión (cobertura, huecos, duplicación) en `tests/TESTMAP.md`. Se extiende
1000→10000 por hojas (añadir ficheros a un nodo o un nodo nuevo), sin reescribir la espina. Docs canónicas:
`.meshkore/roadmap/initiatives/INI-013-voice-tester.md` (registro de pruebas + oleadas),
`.meshkore/docs/ops/zaelar-observability.md` (cómo depurar por logs), `.meshkore/docs/ops/zaelar-model-benchmarks.md`
(modelos/latencias). Cómo funciona:

> **TRES formas de testing** (el DETALLE completo — cómo lanzar, formatos, evaluación — vive en
> **`.meshkore/docs/ops/zaelar-testing.md`**, no aquí): (1) **MEMORIA** (`tests/memory/e2e/bot/`, taxonomía A–X);
> (2) **VOZ e2e** (INI-013, `tests/voice/e2e/agent/`) — realista, lento, con ruido de STT; (3) **canal de PRUEBA del FlashBrain por
> TEXTO** (V2-032, el más RÁPIDO, headless) — **úsalo siempre que toques cerebro rápido / conversación / prompt /
> memoria-estado / tools**: `make reset` → `make flash-serve` → `make flash T="…"` (ver el playbook para el resto).

Cómo funciona (canal de VOZ e2e, INI-013):

- **El tester** (`tests/voice/e2e/agent/`, `python -m tests.voice.e2e.agent.run`): se une a la MISMA sala LiveKit de zaelar como un **2º
  participante**, **habla por TTS** y **escucha+transcribe con Deepgram STT**. Un cerebro **DRIVE** (DeepSeek vía
  AIMLAPI) conduce el escenario/objetivo turno a turno. Uso: `./.venv/bin/python -m tests.voice.e2e.agent.run --scenario <id>` o
  `--goal "..." --turns N`, `--no-open` para no abrir navegador. **Requiere zaelar ya arrancado** (`make run`). Bucle
  nocturno: `tests/voice/e2e/agent/overnight.sh` + `tests/voice/e2e/agent/guard.sh`.
- **El juez** (`tests/voice/e2e/agent/judge/`, GLM-4.6 vía Z.AI, fallback DeepSeek): se suscribe a `GET /events` (el bus del
  observer) y evalúa el **comportamiento OBSERVABLE**: acciones de frontend (widgets `show`/`close`, navegador), tags
  del cerebro, escalados, latencias reales. Escribe un informe por sesión en `tests/runs/agent/report_*.md` (+ `.json`,
  versionados; los `.wav`/`.log` se ignoran).
- **El prompt de iteración — el loop autónomo** (`/loop 20m <prompt>`, skill `loop`): re-invoca SIEMPRE el mismo
  ciclo: **(1) guarda** (`curl /api/brain`; si no responde, `make run` y esperar) → **(2) prueba** la siguiente
  oleada → **(3) arregla** en código si hay hallazgo → **(4) re-verifica** (reinicia si tocó `.py`) → **(5)
  documenta** una entrada FECHADA nueva al final de INI-013 → **(6) repite**.
- **Cron test→fix (cada 15 min) — el PROCEDIMIENTO ESTÁNDAR** (`tests/voice/e2e/agent/cron_tick.sh`, doc en INI-013 §Cron test→fix
  loop): cada disparo prueba **UN caso de uso COMPLETO** (no saludos triviales) rotando por `tests/voice/e2e/agent/scenarios.py`
  (mensajería · widgets · navegador/moto · conectores · memoria · búsqueda V2-022 · agenda · idea compleja…), el
  JUEZ lo puntúa (`overall>=4` = PASS, `dispatch_dead`/null = INFRA), y el agente **arregla el código si falla**,
  reinicia si tocó `.py`, **re-corre ese mismo escenario** y documenta. `cron_tick.sh` asegura zaelar UP, SALTA si el
  operador está en vivo, rota con cursor y aplica watchdog. Se prueba contra la **cuenta viva del operador**
  (autorizado: admin/pruebas; añadir/quitar datos reales OK, NUNCA crear perfiles ni romper).
- **Oleadas de prueba (A-L)**, en INI-013: A=fiabilidad de escalada, B=directiva de estilo, C=memoria de arranque,
  D=widgets, E/F=WhatsApp/Telegram, G=paste/ficheros, H=multilenguaje, I=latencia, J=regresión, K=widgets nuevos,
  L=cron/proactividad.
- **Evaluación A FONDO de la MEMORIA** (bot dedicado `tests/memory/e2e/bot/`): taxonomía de **24 dimensiones (A–X)**
  anclada a los benchmarks del estado del arte (LongMemEval/LoCoMo/MemBench/MemoryAgentBench/MemConflict/BEAM/STALE/
  Mem2ActBench) — alimenta la memoria incremental por el CAMINO REAL (`_brain_view`, sin LLM en la lectura) + pytest
  de regresión + tester en vivo para lo que es del LLM. **Teoría canónica** en `zaelar-memory.md §Evaluación de la
  memoria`; **mapa/cobertura** en `TAXONOMY.md`; **control de calidad cada 50 casos** en `EXIGENCIA.md`; oleadas
  fechadas en INI-013. Fronteras abiertas (T175/T177/T178/T179/T181/T182/T183) y mejoras aplicadas en `V2-021`.
- **Entrada primaria de memoria para agentes**: ejecutar
  `./.venv/bin/python -m tests run memory --case memory::group::1.4::v4 --no-open`. Son 15 turnos naturales por el
  gateway real CORAZÓN con extracción, descarte, slots/correcciones y recall; el operador los ve en `127.0.0.1:8765`.
  Para aging/TTL/REM usar después `memory::group::1.4::timeline-6m` (966 pasos, 180 días, REM diario). Ninguna de
  estas pruebas toca la memoria real del operador; todo caso tardío reconstruye su prefijo causal en una BD aislada.
- **UN solo sistema de log** (`voice/observer.py::emit(kind,label,…)`): TODO evento —cerebro, widgets, transcripts,
  `state`, `vad`/barge-in, `metric` STT/TTS/turno, `error`— se registra ahí y sale por SSE `GET /events` +
  `.meshkore/logs/timeline-latest.jsonl` + `.meshkore/logs/sessions/<id>.jsonl` + el anillo de `/debug`. El motor de
  voz (`agent.py`) llama a `emit()` directamente; `voice/engine/pipeline/instrument.py` **ya no** registra eventos —
  solo el handshake de arranque (topic `vl2`, para el splash) y una grabación de mic OPCIONAL (`ZAELAR_RECORD_MIC`,
  def OFF). El juez consume `GET /events`. Detalle en `zaelar-observability.md`. **Anti-flood (2026-07-12):** las
  `VADMetrics` (y cualquier métrica sin latencias reales) NO se registran — se disparaban ~2/s de forma continua
  (más con ruido de fondo), sin dato útil, y cada evento hacía 2 escrituras de fichero SÍNCRONAS en el hilo de voz
  → floodeaban el SSE y sumaban latencia; se conservan STT/TTS/LLM/EOU con números. El puente `memory.updated`→SSE
  va **coalescado** (trailing-debounce 400ms, `ZAELAR_MEM_SSE_COALESCE_MS`): una ráfaga de mutaciones de un turno =
  UNA señal (el visor re-fetchea con debounce, no pierde reactividad). **Trazabilidad (V2-044,
  `voice/trace.py`):** cada estímulo (frase del operador voz/chat, kickoff, probe, cron, chispa, tap de UI, peer
  de cluster) nace con un **`trace` id** y TODA su cadena derivada (tools, tags, rails `span=rail:K`, workers
  `span=worker:N`, navegador `span=web:tN`, memoria) llega sellada — ContextVar por `create_task`/`to_thread` +
  costuras explícitas (payload de escalada→`SessionRecord.trace_id`, registro de tareas del navegador, run del
  rail). El visor ◷ pinta un chip por fila (click→filtra la cadena) y el botón **⛓** alterna a la vista
  **Trazas** (árbol frase→actor→eventos). Detalle en `zaelar-observability.md §Trazabilidad` + iniciativa V2-044.
  **Filtro del visor = las PIEZAS del sistema, con inventario CERRADO (2026-08-09):** las familias son
  **FlashBrain · Brain Workers · Memoria · Widgets · Sistema/Código · Pulso** (fuera «Principal», que era un cajón
  de sastre), y **TODO `kind` emitido pertenece a una** — lo garantiza un test que recorre el código y falla si
  alguien estrena un kind sin clasificarlo (`tests/infrastructure/unit/core/test_observer_categories.py`, nodo
  7.6); antes caían filas que ningún chip gobernaba. Regla: **la familia dice QUÉ pasó, el `span`/`trace` dice
  QUIÉN lo hizo** — la lectura de memoria de un worker es `memory`, no «worker»; para aislar por ACTOR está la
  vista Trazas. **UN SOLO eje de filtro, el `kind`** (panel plegable «Filtros (N)» con el mapa COMPLETO de lo
  filtrable —una fila por familia, su rótulo enciende/apaga la familia entera—, shift+click = solo ese) + cabecera
  FIJA de columnas. **El último evento va ARRIBA (2026-08-10, decisión del operador): la lista crece por PREPEND y
  el scroll es 100% manual** — eso RETIRA el «seguir el fondo» y toda su maquinaria (estado de seguimiento, ventana
  de gesto, rAF, indicador): un estado que puede mentir sobre lo que estás viendo se elimina, no se blinda (falló
  dos veces). Tabla completa en `zaelar-observability.md §El visor`. **Cada evento lleva
  además `corr` (el FLUJO), `sid` (sesión de trabajo) y `uid` (instalación)**, y `bus/log.py` los sube a COLUMNAS
  indexadas de `events` junto a `cat`/`kind`/`ms`/`model`/tokens → la observabilidad se CONSULTA por flujos en
  vez de escanearse. Ver el módulo `observability/` y la iniciativa V2-090.
- **Routing de modelos del tester**: DRIVE + juicio barato = **DeepSeek vía AIMLAPI**; juicio competente = **GLM-4.6
  vía Z.AI**. Claves en `.env` + `.meshkore/credentials/tester.env` (gitignored).
- **Docker SÍ se permite AQUÍ** (aislamiento, LiveKit dedicado del tester) — es la ÚNICA parte del proyecto donde
  Docker es aceptable; el CORE de zaelar NUNCA depende de Docker.
- **Limitaciones CONOCIDAS del arnés**: (a) `--goal` SIEMPRE usa canal VOZ; (b) el Deepgram STT del propio tester a
  veces garbla/mezcla idiomas o "oye" el audio de zaelar → ante señal sucia, mirar `timeline-latest.jsonl`.

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


#### Movidas el 2026-09-14 (V2-694)

- **Two screens, ONE widget (V2-574, 2026-09-04)** (2026-09-04; V2-574)
- **The voice SEES the open directory — a widget the operator is looking at publishes its truth (V2-576, 2026-09-04)** (2026-09-04; V2-311, V2-576)
- **A widget event reaches the pills it outdates — the lifecycle chain (V2-577, 2026-09-04)** (2026-09-04; V2-577)
- **The sleep circuit review — five silent integrity holes in the REM process (V2-578, 2026-09-05)** (2026-09-05; V2-578)