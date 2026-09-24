<!--
Canonical workflow for adding a NATIVE UI surface — a panel, a tab of the chat wall, a system overlay — end to
end. Written 2026-09-24 from the V2-761 build (the wall's «Apps» tab), which is the reference implementation
every step here points at. Sibling of `zaelar-new-widget-or-connector-workflow.md`: that one is for pieces the
catalogue carries; this one is for the body of the interface itself.
-->

# A new native surface (panel, wall tab, system overlay) — the full workflow

**Trigger:** *«añade una pestaña de…»*, *«quiero un panel nuevo para…»*, *«pasa el workflow de superficie
nativa»*, or any change that adds something to `frontend/app/core/system-surfaces.js`.

A native surface is **not a widget**: it is not in the catalogue, the operator cannot delete it, and the
generator never touches it. It still has to be reachable by hand AND by voice, in every language the
interface speaks, at every width the wall can take. The rule that governs this document is the same as the
widget one: **a surface wired in all but one of its points does not fail loudly — it comes out EMPTY, or
UNREACHABLE**, and an unreachable surface gets diagnosed as «the model did not understand».

## 0. Which workflow?

| If you are… | Follow |
|---|---|
| adding a native surface / a tab of the wall / a system overlay | **this document** |
| adding a widget or a connector | `zaelar-new-widget-or-connector-workflow.md` |
| changing the widget SYSTEM (manifest contract, dispatch, storage) | `zaelar-widgets-workflow.md` |

## 1. Three decisions before any code

1. **A tab of an existing surface, or a surface of its own?** A list the operator browses belongs in the
   wall (Chat · Procesos · Clusters · Conectores · Apps). A tab costs no z-index, no mount point and no new
   close gesture. A surface of its own needs all three.
2. **Where does its data come from?** Prefer an endpoint that already exists — V2-761 needed none:
   `/widgets/registry` already carried `origin` and `forked`. A new endpoint is a new place to go stale.
3. **What does a click do?** It goes through a door that already exists (`hb:open-card` for a card,
   `store.setConfigOpen` for settings). A second way of doing the same thing is a second thing to keep
   in sync.

## 2. The wiring — the list of places that fail SILENTLY

| # | Touch | If you forget it |
|---|---|---|
| 1 | `frontend/app/components/<Surface>.js` — the tab body, its `TAB_LABEL` entry, the button, the refresh-on-enter branch | the tab exists and shows stale or no data |
| 2 | `frontend/app/styles.css` — the `.chatwall.tab-<id> .<panel>{display:flex}` rule, and the panel in the hide-all list | the panel is built and never painted |
| 3 | `frontend/app/core/store.js` — `_TABS` (and any sub-tab signal / aliases) | `setChatTab("<id>")` silently falls back to Chat |
| 4 | `frontend/app/lib/icons.js` — an icon that does not collide with another surface's meaning | two icons read as the same action (V2-761: dots, because the rail's arrange buttons are squares) |
| 5 | the wall's width thresholds (`TABS_NARROW_BELOW`, `TABS_TIGHT_BELOW`) — **measure every tab's box at 260-800px** | a tab sits behind the strip's hidden scrollbar (measured: it already happened with four tabs) |
| 6 | `i18n/bundles/en.json` **and** `es.json` — every label, empty state and tooltip, plus `surfaces.<id>.name` | `t()` returns the KEY, which is truthy — the raw key is painted |
| 7 | `frontend/app/core/system-surfaces.js` — the entry with `name` + `aliases` (`phase: "tab"` when it is not mounted on its own) | the voice cannot name it |
| 8 | `widgets/system_surfaces.py` — the backend mirror (the sync test fails if you skip it) | the resolver does not know it |
| 9 | `voice/engine/llm/providers/nucleo.py` **and** `nucleo/flash/probe.py` — a `show_widget` that names the surface must route to it, not ask «which widget?» | the model picks `show_widget` and the turn ends in a clarifying question |
| 10 | `nucleo/flash/panel_canon.py` — the `show_panel` argument → tab id | the model's argument lands on the default tab |
| 11 | `nucleo/flash/router_catalog.py` — the `show_panel` description names it (**paid for by compressing, never by raising a ceiling**: `test_router.py` + `test_the_prompt_prose_only_shrinks.py`) | the model has no reason to call the tool for it |
| 12 | `nucleo/actionmap/executor.py::_PANEL_TABS` + `nucleo/actionmap/seeds/{es,en}.json` with the pack `version` **bumped** | whole-utterance orders fall through to the model — and new phrases in an old version reach no existing install |
| 13 | `tests/run_testmap.py` — the rendered test and the voice test, each with its node | the tests exist and nobody runs them |

## 3. Aliases: measure the NEIGHBOURHOOD, not the phrase

The name resolver fuzzes **single-word** aliases (`widgets/runtime._alias_score`, cutoff 0.84). A bare
single word that is a near miss of another piece's word steals it. Measured in V2-761: a bare «aplicaciones»
would have caught «abre la APLICACIÓN de música» and opened the list instead of the music card. So:

- prefer multi-word aliases wherever a single word has a near neighbour («las aplicaciones», «mis apps»);
- before committing, run `runtime.identify()` over the phrases that must reach the surface **and** over the
  neighbours that must not move («la aplicación de música», the video card's own «vuelve al catálogo»,
  «abre whatsapp»), and pin both lists in the test;
- the word «widget» (singular) scopes the resolver to USER widgets on purpose (`_WIDGET_WORD_RE`); a plural
  «widgets» does not trigger it, which is what lets «la lista de widgets» name a system surface.

## 4. Tests — two, both seen red

1. **Rendered** (Chromium, the real component + store + stylesheet, the data endpoint routed): the button
   exists, its icon, the panel paints, the rows are the right ones, a click reaches the door, and **every tab
   is reachable at every width**. Register the catch-all route FIRST — Playwright gives the last matching
   route priority, and a catch-all registered after the i18n route swallows the bundle.
2. **Voice** (unit): the three doors (action map, `show_panel`, `show_widget` → surface) and the neighbours.

Stash the product files and watch both go red before trusting them.

## 5. Close

The decision in `.meshkore/docs/decisions.md`, the initiative, the module log — the usual closure.
