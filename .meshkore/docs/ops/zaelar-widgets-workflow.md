---
title: Zaelar Widgets Change Workflow
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# Widget system change workflow — "run the widgets workflow"

**Trigger:** when the operator says **"run the widgets workflow"** (or "review the widgets change", "close the
widgets change"), or when YOU have just touched something structural in the widget system and are about to call
it closed — run this checklist before saying you are done.

> **Not every change under `widgets/` triggers it.** A comment, an internal rename, a style tweak inside one
> widget that touches neither the contract nor the architecture → **this workflow is not needed**, carry on as
> usual. It is for **structural** changes: a new tag, a new `manifest.json` field, a storage change, a change in
> who may mutate what (SlowBrain/FlashBrain), a change in the refresh mechanism, a change in the validation gate,
> or a new widget "kind". See [[zaelar-modules]] §Widgets for the current state of the system, and
> [[zaelar-change-protocol]] / [[zaelar-docs-sync]] for the general protocols this one specialises for `widgets/`.

---

## 0. Does this workflow apply? (scope filter)

Ask yourself: does this change alter something **any widget, present or future, has to respect or can use**?
If the answer is yes to any of these, run the full workflow:

- The `manifest.json` / `data.py` / `widget.js` contract (a new field, a new convention, `actions`, `usage`,
  `confirm`/`irreversible` — an action's execution mode, `widgets/actions.py`; `background`+`tick(ctx)` —
  off-screen execution on a cycle, `widgets/background.py`; `ref_index` — refs to items, `widgets/refs.py`; `kind`).
- The tag protocol (`voice/tag_protocol.py`) — a new tag, a syntax change, a change in what is escaped/held back.
- Brain↔widget dispatch (`voice/engine/llm/providers/nucleo.py`, `nucleo/flash/router.py`, `nucleo/dispatch/`,
  `widgets/__init__.py`, `widgets/server_api.py`) — who may create/modify/delete/deliver/mutate data, and under
  which conditions.
- The storage model (`widgets/store.py`) — on-disk format, location, migration.
- The refresh mechanism (`frontend/app/widgets/desktop.js`, `frontend/app/services/sse.js`).
- The generator's validation gate (`widgets/generator.py`).
- The home of the system's public documentation (the public diagram `/technology/widgets`, outside this repo — a
  MANUAL step that no workflow syncs on its own; update it only when the change matters to an outside reader, not
  for every internal detail — plus `widgets/AGENTS.md` and `zaelar-modules.md §Widgets`).

If the change is only inside ONE widget (its `data.py`/`widget.js`/`notes.md`) and touches none of the above,
update THAT widget's `notes.md` (per-widget memory, see `widgets/AGENTS.md`) and stop there — nothing else in this
document is needed.

## 1. Impact map — "if you touched this, update that"

| You touched | Also update |
|---|---|
| A new tag or a syntax change (`tag_protocol.py`) | `widgets/brief.py` (`TAG_PROTOCOL`) · `nucleo/turn/prompt/` if the FlashBrain must know it or be blocked from it · `zaelar-modules.md §Widgets` · public diagram (`/technology`, outside this repo, + its `.ts`, only for a change that matters to an outside reader) |
| A new `manifest.json` field (e.g. `actions`, `safe`, `kind`) | `widgets/AGENTS.md` (the contract for hand editors) · `widgets/generator.py` → `_CONTRACT`/`_CREATE_PROMPT`/`_MODIFY_PROMPT` (the contract for the code agent) · `widgets/brief.py` if the brain must read it |
| The storage model (`widgets/store.py`) | a **lazy, automatic** migration, never a manual script nor data loss (same pattern as the `_v` schema migration) · `widgets/AGENTS.md` · the generator's `_CONTRACT` · doc + diagram |
| Brain↔widget governance (who mutates what) | `voice/engine/llm/providers/nucleo.py` + `nucleo/flash/router.py` (dispatch + the declaration of the tools `escalate_to_slowbrain`/`set_style_directive`) · `nucleo/dispatch/` (SlowBrain) · `nucleo/turn/prompt/` · `widgets/brief.py` · doc + diagram |
| The refresh mechanism (SSE/poll) | `desktop.js` · `sse.js` · `widgets/AGENTS.md` (the "no polling" rule) · doc + diagram |
| **Any VISIBLE string of a built-in widget** (label, title, button, empty state, `placeholder`, `title`) | `tt("key", params, "<the literal>")` in the `widget.js` + the row in `i18n/genesis/en/ui.json` **and** `es.json` · bump `MANIFEST_VERSION` if the SET of keys changes · the gate at node 4.11 requires it and fails the build |
| **The NAME of a widget or a surface** | `widgets.<id>.name` / `surfaces.<id>.name` in both bundles — NOT `manifest.json`, which stays as the fallback and as an alias so voice keeps answering to the factory word · `widgets/registry.py::display_name` is the only reader |
| The validation gate (`generator.py`) | run `make test-widgets` against ALL existing widgets before calling the change good |
| A new "kind" or structural capability (e.g. "backed" widgets) | the full design written in `zaelar-modules.md` BEFORE touching real code · a line in `.meshkore/docs/criteria.md` · do not build the generic mechanism without a real consumer that validates it |

## 2. Review the impact on the widgets that ALREADY exist

- If you touched something ALL widgets use (contract, store, validation gate): run `make test-widgets` and
  confirm zero failures before continuing. If something breaks, fix it — a structural change can never leave an
  existing widget broken.
- Decide, widget by widget, whether it should adopt the new capability (e.g. should `mensajeria` declare `"safe"`
  on some action now that the level exists?). They do not all have to migrate at once — but if you decide NOT to
  migrate one yet, note it in its `notes.md` so it is traceable and not re-argued from scratch next time.
- If you changed the on-disk format (`widgets/store.py`), verify the migration against REAL data from at least one
  existing widget (not only an empty test widget) before calling it good.

## 3. Document — the golden rule is ALWAYS three places, never two out of three

Same principle as `zaelar-docs-sync.md`: it appears in **context (`CLAUDE.md` / `criteria.md`) + canonical doc
(`zaelar-modules.md`) + the public diagram** (if the change matters to an outside reader). For widgets,
specifically:

- **`.meshkore/docs/modules/zaelar-modules.md` §Widgets** — the canonical source, the full detail. A big change may
  deserve its own subsection (like "Widget-apps ('backed' widgets)").
- **`.meshkore/docs/criteria.md`** — a CONCISE line if a rule changed, pointing at the detail above. Never
  duplicate the detail there: only the rule + where the rest lives.
- **The public diagram `/technology/widgets` (outside this repo) — THE DIAGRAM AND THE THEORY, BOTH.** It is easy
  to update only the prose of the `.astro` and forget the nodes in the `.ts` `build()`. Go through `build()`
  **node by node** — titles, sub-lines, and the arrow paths/labels that refer to what you changed — not only the
  prose above. If the change adds a new piece to the circuit (a folder, a tag, a governance level), that piece
  needs ITS OWN group/box in the SVG, not just a mention in prose. This is for OUTSIDE readers (trimmed on
  purpose, no internal file paths) — do not trigger it for every internal detail, only for topology/flow changes
  a self-hoster or visitor would see.
- If the tag vocabulary or the contract the brain sees changes: **`widgets/brief.py`** + the FlashBrain prompt
  (**`nucleo/turn/prompt/`**). The live persona/instructions are not an external file: they are injected on
  every connection from `memory/` + `nucleo/turn/prompt/`, so there is no personal copy to touch here.
- If the contract the code agent (Claude Code) sees changes: **`widgets/AGENTS.md`** + **`widgets/generator.py`**
  (`_CONTRACT`/`_CREATE_PROMPT`/`_MODIFY_PROMPT`).

## 4. Test — not just code review

- `make test` (imports/health) and `make test-widgets` (contract + golden + ES-module parse of EVERY widget) —
  both green before continuing.
- If the change touches brain↔widget dispatch/governance: test it **live** against the real system (not only by
  reading code) — e.g. by calling `nucleo.llm.fast_client.FastClient()` (FlashBrain) and `nucleo.dispatch`
  (SlowBrain) directly to confirm both speeds behave as expected with the new prompt/brief, and that
  `escalate_to_slowbrain` escalates what it should. Clean up any test data left in the real stores when you
  finish (never leave a "test meeting" in the operator's agenda).
- If you touched the public widgets diagram: build the site (it fails on type/syntax errors) and, if you touched
  the SVG geometry, check it by eye in the browser (no box spills out of its group, text fits the box height for
  its number of lines, no arrow label leaves the canvas) before deploying.

## 5. Restart (if needed)

- Did you touch any `.py`? → **yes**, the server must be restarted (no hot reload; `make run` = `BRAIN=nucleo`,
  the default brain — check `GET /api/brain` BEFORE killing the process, to relaunch exactly the same way). Never
  restart with someone in a live session or a task in flight (see `CLAUDE.md`).
- Did you only touch a widget (frontend `.js`/`.css`, or the public site's diagram)? → **no** engine restart
  needed — the frontend is served with `Cache-Control: no-store` (reloading the page is enough); the public site
  lives outside this repo.
- To restart: identify the process tree (`livekit-server` + `python -m server`, both children of
  `bash scripts/run-livekit.sh`), `SIGTERM` first; if it does not respond within a few seconds, `SIGKILL`. After a
  `SIGKILL`, check for orphaned processes left hanging from a child (e.g. the WhatsApp bridge on port 3111) — if
  they are not cleaned up, the next start collides with the busy port.
- Then verify: `GET /`, `GET /api/brain`, `GET /widgets` (correct catalogue, new fields present if you touched
  the manifest), and any endpoint specific to the change.

## 6. Commit / push

- Follow the commit/push policy in `CLAUDE.md` (pathspec commits, never someone else's uncommitted work).
- Group the touched files by category in the message (code · generator contract · canonical docs · public
  architecture) so the commit is traceable as the structural change it is.

## Summary for the operator (at the end)

When you finish this workflow, ALWAYS answer with:
- What changed, in 2-3 sentences (architecture/contract/governance — not a list of files).
- What you updated (short list: generator contract, brief, canonical docs, architecture diagram + theory).
- What you tested (`make test`/`test-widgets`, and if there was a live test, against what).
- Whether you restarted or not, and why.
- What is left open (a migration of a specific widget not done yet, something the operator has to redo by hand
  such as re-scanning a QR).
