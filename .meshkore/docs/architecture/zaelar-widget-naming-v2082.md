# Widget names + aliases — routing with certainty

## 0. The principle

A widget opens **only when its name or one of its aliases is said.** Matching never falls back to «the most
similar widget»: a lexical matcher that also scores overlap with `description`/`whenToUse` can let a widget win
without its name being spoken, which is exactly the class of confusion this design removes.

- Every widget has a **canonical NAME** (shown in its header) + a **list of ALIASES**.
- **If you do not say the name or an alias, the widget does NOT open.**
- `chat` → always the main chat (a system surface). `messaging / WhatsApp / Telegram / X / Twitter / email` → the
  `mensajeria` widget. No ambiguity.
- A configuration control in the header of EVERY widget shows its aliases, **editable by the user by voice and by
  text** («add the alias WhatsApp to the messaging widget» is interpreted by the FlashBrain, with no code
  regeneration).
- A **state catalog** lists every widget with its aliases.
- The concepts stay **clean and unmixed**: widget vs system surface vs tool vs action/data-op vs embedding.

## 1. Conceptual model (single source, no mixing)

| Concept | What it is | Where it lives (source of truth) | Has name+aliases? |
|---|---|---|---|
| **Widget** | Canvas UI, full-stack | folder `widgets/<id>/` (manifest+widget.js+data.py) | **YES** |
| **System surface** | Native, untouchable piece (mic/cam, orb, chat, debug, config…) | `frontend/app/core/system-surfaces.js` + backend mirror | **YES** |
| **Tool** | OpenAI-style function the FlashBrain invokes | `nucleo/flash/router.py::TOOLS` | NO — not a user-facing identity |
| **Action / data-op** | Declared capability of ONE widget (the closest thing to a "skill") | `manifest.json["actions"]` + `data.py::apply_action` | NO — belongs to the widget |
| **Embedding** | Semantic vector | `memory/` exclusively | NO — widgets have no vector |

**"Skill" is not a concept in the code.** The functional word "skill" ≡ a widget's `actions`. `CLAUDE.md` and
`zaelar-architecture.md` describe it the same way so the concepts stay separate.

## 2. Data model: `name` + `aliases[]`

### 2.1 Widgets (manifest.json)

The canonical identity contract:

- **`name`** (string): the human canonical name = what the header shows and the first spoken term. Defaults to
  `title` if missing.
- **`aliases`** (string[]): alternative spoken names, **editable by the user**. This is the list shown in the
  header's config dropdown.

`keywords[]` is read only as a seed: on first load of a widget without `aliases[]`, `aliases` are **seeded** from
`keywords` (deduplicated, normalised). `aliases[]` is the ONLY identity field that is written, so there is **one
identity list**, not two.

### 2.2 System surfaces (system-surfaces.js + backend mirror)

Every `SYSTEM_SURFACES` entry carries `name` + `aliases[]`. Examples:
- `chat`: name "Chat", aliases `["chat","muro","muro de texto","escribirte","háblame por texto"]`.
- `config`: name "Configuración", aliases `["config","ajustes","preferencias","settings"]`.
- `debug`: name "Debug", aliases `["debug","depuración","logs","trazas"]`.
- `orb`, `camera`, etc. likewise.

**The source of truth for system aliases is the FRONTEND** (`system-surfaces.js`), hardcoded and **NOT
user-editable**: the frontend is "the body" and its genetics are programmed. Since the resolver lives in the
backend (`runtime`), a **backend mirror** (`widgets/system_surfaces.py`) is kept in sync by a test that fails if
they diverge. The resolver therefore unifies user widgets + system surfaces in a single namespace; `chat`
(system) and `mensajeria` (user) coexist → disambiguation is guaranteed.

### 2.3 State catalog (a projection, NOT a second source of truth)

A **projected read-model**, `widgets/registry.py::registry()`, returns for each entry:

```
{ "id", "name", "aliases": [...], "surface": "user" | "system" }
```

A compact version is projected into `memory/state.py` under `state["widget_registry"]` (read-only visibility,
regenerated, never hand-edited) and exposed at `GET /widgets/registry`. The **source of truth remains the
manifest** (user) and `system-surfaces` (system); the state is only the visible mirror.

## 3. Resolution engine: by name, with certainty

### 3.0 The word "widget" (and a system name) is a namespace SELECTOR

Before scoring, the sentence itself narrows the search space:

- If the sentence contains **"widget"** (or its synonyms `_WIDGET_SYN`: panel/gadget/board/counter/…), the user
  means a **piece built by them** → it resolves ONLY against **user widgets**. «open the messaging widget» can
  never land on a system surface.
- If the sentence names a **system object** («the chat», «the cron list», «the task list», «config», «debug») →
  system surface. The system has its pieces, but **they are not widgets**.
- If the sentence **says neither "widget" nor a system object** («open the messages») → it resolves by
  keyword/alias against BOTH spaces; the prompt carries the widget list to match with certainty; with no clear
  match → ask (§3.1, step 4).

### 3.1 Resolution hierarchy

`widgets/runtime.py::identify` follows this hierarchy (for widgets + system surfaces):

1. **Match by NAME/ALIAS** — the only opening signal. Accents and case are normalised. Voice typos are tolerated
   with difflib **ONLY over name/alias tokens** (never over the description). A full alias phrase aligned on word
   boundaries = strong match.
2. **`description`/`whenToUse` never open anything.** They can feed the prompt brief, but they are NOT a match
   signal. This removes the whole class of "opened because it looked thematically similar".
3. **Tie-break by context**: on a real alias tie, priority is **open > recent**; if it is still ambiguous →
   `ambiguous=True`.
4. **No name/alias match → it does NOT open.** It returns `None`. The caller treats `None` as normal conversation
   → the FlashBrain **asks with a natural, varied sentence** that fits the moment («sorry, I can't find that
   widget — which one do you mean?»); it **never** auto-opens the "most similar" one or uses a canned string.

Result: a show/open happens **only** when a registered name/alias is spoken. Collisions are impossible by design
(see §6, the alias uniqueness guard).

It applies on BOTH routes, kept in parity: the real provider `voice/engine/llm/providers/nucleo.py` (`_identify`,
`show_widget` handler) and the probe channel `nucleo/flash/probe.py` (`_identify_ctx`, show branch).

## 4. Editing aliases by voice and by text (a tool, no code regeneration)

Rewriting a manifest through `generator.modify_widget` (a full agent rewrite of the widget) is far too heavy for
"add an alias", so aliases have a deterministic path:

- **Tool** in `router.TOOLS`: `manage_widget_alias(widget_id, alias, op="add"|"remove")` with a description rich
  in synonyms («add/remove/set/delete an alias/name/nickname to/from a widget»). Situational gating
  `has_widgets`. Wired into `decide()` (kind `ALIAS`, medium priority) + handlers in `nucleo.py` and `probe.py`.
- **Surgical manifest write**: `widgets/aliases.py::add/remove` rewrites ONLY `manifest["aliases"]` atomically
  (tmp+rename), validates collisions (§6), calls `runtime.invalidate()` and emits SSE `kind:"widget",
  action:"alias"` so the frontend refreshes.
- The FlashBrain's own resolver interprets the order: «add the alias WhatsApp to the messaging widget» →
  `manage_widget_alias("mensajeria","WhatsApp","add")`. It works the same by voice or by text (same tool).
- **REST endpoints** for editing from the header (text/click): `POST /widgets/{id}/aliases`,
  `DELETE /widgets/{id}/aliases/{alias}`. Same `widgets/aliases.py` underneath.

System surfaces: their aliases are **fixed** (defined in `system-surfaces.js`); the config dropdown shows them
read-only, because they are part of the untouchable native contract.

## 5. Frontend: header with name + alias dropdown

The chrome of every widget is drawn by the common wrapper `frontend/app/widgets/desktop.js`, in that single place
(no individual `widget.js` is involved):

- **Name**: shows `_meta[id].name || title` — the name by which the widget is recognised.
- **Config icon (⚙)**: opens a host-level overlay (the `.hb-confirm` pattern in `desktop.js`) listing the aliases
  with:
  - add alias (text input → `POST /widgets/{id}/aliases`),
  - remove alias (× per chip → `DELETE …`),
  - read-only for system surfaces.
- CSS lives in `desktop.js::injectStyles()` (where all the chrome lives). The grip drag ignores clicks on these
  buttons (as the ChatWall ignores `.cw-x`/`.cw-tab`).
- **Reactivity**: a `widgetRegistry` store signal (filled from `GET /widgets/registry`) keeps the header's
  name/aliases live when they change by voice; the SSE `action:"alias"` refreshes the signal.

The visual shape of the header bars is specified in `.meshkore/docs/conventions/zaelar-widget-header-standard.md`.

## 6. Uniqueness and integrity (the guard that gives certainty)

- **An alias collision between widgets = rejection.** The shared validator
  `widgets/aliases.py::check_collision(id, alias, registry)` ensures an alias cannot belong to two entries
  (widget or surface). When adding by voice/text, a colliding alias is not added and Zaelar says so («that name
  is already used by X»).
- **A collision with a system surface** is rejected too (a widget cannot be aliased as "chat").
- The widget generator requires `name` + at least 1 alias and validates collisions on creation (`_validate`).

## 7. Migrating existing widgets

`widgets/migrate_aliases.py` (idempotent, run once; removed in refactor2710-12 once every widget had migrated): for each real widget → set `name` = `title`, `aliases` =
dedup(`keywords`), and report collisions for manual resolution. Widgets generated by tests are not migrated.

Key curation: `mensajeria.aliases` includes `whatsapp, wasap, telegram, x, twitter, correo, email, mail`; and
`chat` (system) shares none of them.

## 8. Testing

- `tests/browser/unit/widgets/test_resolver_certainty.py`: (a) a sentence with no registered name/alias → `None`
  (no hijack); (b) exact alias → that widget; (c) voice typo on an alias («wasap») → mensajeria; (d) chat vs
  mensajeria disambiguated; (e) open > recent tie-break.
- `tests/browser/unit/widgets/test_aliases.py`: add/remove, collision rejected, collision with a system surface
  rejected, cache invalidation.
- `test_router.py`: the `manage_widget_alias` tool is in the expected set.
- Provider/probe parity: an "aliases" scenario in `tests/voice/e2e/agent/scenarios.py` + «open by name/alias».

## 9. Design decisions

- **`keywords` ≡ `aliases`**: one identity list. `keywords` is read only as a migration seed.
- **System-surface aliases are FIXED**: hardcoded in the frontend (`system-surfaces.js`), not editable, shown
  read-only.
- **When nothing matches, ASK**: the FlashBrain answers with a natural, varied sentence that fits the moment;
  it never opens the closest match or uses a canned string. This is the basis of the certainty.
- **The word "widget" narrows the space** (§3.0): "widget" → user widgets only; a system object's name → system
  surface; neither → keyword against both + ask when there is no clear match.
