<!--
Canonical workflow for SHIPPING A NEW WIDGET and/or A NEW CONNECTOR, end to end.
The cloud-files family (Google Drive + OneDrive + the `archivos` explorer) is the reference implementation
every step here points at. Each trap listed in §11 costs more than the step that prevents it.
-->

# New widget / new connector — the complete workflow

**Trigger:** *"add a connector for X"*, *"build a widget for Y"*, *"run the new-widget workflow"*.

What follows is EVERY action, in order, for a new piece to end up built, wired, tested, documented and in
context. The rule behind it: **a piece that is not wired at ALL of its points does not fail loudly — it comes
out EMPTY**, and an empty surface gets diagnosed as something else. That is why half of this document is a list
of places to touch, not code to write.

## 0. Which workflow is this? (scope filter)

| If you are going to… | Follow |
|---|---|
| **create a NEW piece** (widget, connector, or both) | **this document** |
| change the widget SYSTEM (manifest contract, dispatch, storage, gate) | `zaelar-widgets-workflow.md` |
| add a NATIVE surface (panel, wall tab, system overlay) | `zaelar-native-surface-workflow.md` |
| change an existing widget, inside its own folder | its `notes.md` and nothing else |
| close any batch that changes behaviour | `.meshkore/docs/conventions/closure-protocol.md` |

---

## 1. Before writing a line — five decisions

Answer them in writing in the piece's design notes. All five have a default answer, and the default is almost
always right; what is expensive is not having made them.

**1.1 Widget, connector, or both?** A CONNECTOR talks to the outside world and has no screen. A WIDGET is a
surface and should not know whom it talks to. If you need both, separate them from minute one with a
**provider-agnostic facade** that returns ONE normalized shape (`connectors/files/service.py` is the model). The
proof the boundary is in the right place: *adding a second provider touches the registry and one client module,
and ZERO lines of the widget*.

**1.2 Does the FlashBrain need a new tool? Almost always NO.** The tool catalog travels WHOLE on every turn,
including the one that says "hi", and it has a ceiling enforced by a test. **A widget's declared actions ARE its
skills** — the FlashBrain runs them through the generic `widget_data` tool that already exists, and a catalog
entry costs ONE line of prompt, not a tool slot. A new tool is only justified when the capability **has no
widget** (`web_search`, `recall`). If you add one, you must trim another: the ceiling lives in
`tests/agent_headless/unit/flash/test_router.py`.

**1.3 Does it run in the BACKGROUND?** (This must be decided, not omitted.) Does its data change on its own, off
screen, in a way the operator might ask about by voice without opening the card? A mailbox, a feed, the weather →
**yes**: declare `"background": {"every": "…"}` and write `tick(ctx)`, flushing to memory through `ctx`. An
explorer, a search box, a chart → **no**, and write down why (for `archivos`: polling someone's cloud spends API
quota to answer a question nobody asked).

**1.4 Does it PRODUCE something?** Does it keep doing something when the operator stops looking — audio, video,
recording, a live process? If so, declare `runtime{output, produce[], suspend, active_when}` or your widget will
keep playing with the agent STOPPED. If not, declare nothing: *received* media (a photo, a QR code) is passive
content, not production.

**1.5 How does it live on SEVERAL SCREENS?** (Required in the manifest since V2-792.) The same agent is open on
the operator's computer and phone at once, with one conversation. `"screens": "shared"` — a reflection of data (a
calendar, a list, contacts, a map, results): it may be open on every screen, a request opens it on the screen that
asked, the others get an «open here» chip, and every copy shows the same data live. `"screens": "single"` — it
takes the device's sound or picture (a video, music, a recording): it lives on ONE screen, and asking for it from
another screen MOVES it (the screen that had it stops and closes its copy); orders about it (pause, volume) still
reach it wherever it plays. `runtime.output` ⇒ `"single"`, and the gate rejects the contradiction. The host does the
moving (`voice/screens.py` + `frontend/app/services/screens.js`), so the widget's code never looks at other screens.
Policy and its one rule: `widgets/screen_policy.py`; node 4.269 fails a built-in widget that does not declare it.
**It is tested before the widget is declared done** — automatic (`python -m tests.widget_harness --two-screens <id>`, two
real browsers; node 4.270 over the whole catalogue) and manual by the operator with a real computer and phone
(`python -m tests.widget_harness --manual <id>`): `.meshkore/docs/ops/zaelar-two-screen-test.md`.

---

## 2. The connector — the files and their order

Built **bottom up**, and each layer is tested before writing the one above it.

```
connectors/<family>/
├─ providers.py    ①  the typed REGISTRY: one entry per provider with endpoints, scopes and capabilities
├─ oauth.py        ②  the flow (if it uses OAuth) — a thin module over connectors/oauth_base.py
├─ <provider>.py   ③  one client per provider: speaks HTTP, returns the NORMALIZED SHAPE, nothing else
├─ service.py      ④  the AGNOSTIC facade — the only thing the rest of the system sees
├─ server_api.py   ⑤  the control plane (`/api/<something>/*`): status · connect · callback · disconnect
└─ __init__.py
```

- **① `providers.py`** — everything that distinguishes one provider from another goes here as DATA, never as
  scattered `if`s. If a provider has permission tiers with different consequences, **that is a field**, not a
  constant (in the cloud-files family the tier decides whether the tree can be listed at all). `public_list()`
  returns the redacted view for the frontend: labels and notes, **never endpoints or credentials**.
- **② `oauth.py` is CONFIGURATION over `connectors/oauth_base.py`.** The flow — PKCE, the pending states and
  their expiry, the exchange, the refresh, the return address derived from the operator's origin — lives ONCE in
  the base, so that every connector gets the same correct behaviour (the consent always returns to the
  operator's own origin, a forged origin never reaches the redirect URL, every pending consent expires). A new
  connector's `oauth.py` declares `STORE`, `ENV_PREFIX`, `CALLBACK_PATH`, `_DEFAULT_REDIRECT`,
  `_GOOGLE_PROVIDERS` and `_pv`, and its public functions are one-line calls passing the module itself
  (`connectors/photos/oauth.py` is the smallest reference; `connectors/email/oauth.py` shows a connector whose
  providers and accounts are shaped differently — `_auth_spec`, `_oauth_capable`, accounts keyed by address).
  Each connector keeps its OWN store file, callback route and credential names: nothing is shared but code.
  The base reads everything through the connector's module at call time, so a connector overrides a piece by
  defining it. `tests/connectors/unit/test_every_account_connector_runs_the_same_oauth_flow.py` (node 5.62)
  runs the same flow against every connector — add yours to its `CONNECTORS` list. Spotify
  (`connectors/spotify/auth.py`: one account, one pending consent, no provider table) has a different shape and
  is deliberately kept on its own flow.
- **② `oauth.py`, storage** — PKCE S256 from `connectors/oauth_pkce.py`; tokens through `SecureJsonStore`
  (atomic write + chmod 600) in `.meshkore/credentials/<x>.json`, **gitignored**. Store **which permission was
  granted** next to the token: the callback only carries `code` and `state`, so whatever the operator chose has
  to travel inside the `state`. A `refresh` that returns no `refresh_token` **keeps the previous one**, or the
  operator gets disconnected hours later.
- **③ the clients** — they return the SAME keys. A test enforces it; without it the facade is an illusion.
  Escape whatever the operator types before putting it into the provider's query language.
- **④ `service.py`** — **always fail-safe**: `{"ok": False, "error": "…"}`, never an exception upwards. A
  provider that is down degrades to a card that says so; it never takes a voice turn down with it. And
  **distinguish what is not an error**: if a legitimate answer produces the same emptiness as a failure, return
  `ok` **with a `reason`** — see §11-T1, the most expensive trap in this family.
- **⑤ `server_api.py`** — **check the prefix is free before choosing it**
  (`grep -rn '"/api/<something>' server/ connectors/`). FastAPI resolves two routers on one prefix by mount
  order, silently.

---

## 3. The widget — the files and their order

```
widgets/<id>/
├─ manifest.json   identity, declared actions, aliases, size
├─ data.py         view_data · apply_action · ref_index · prompt_digest
├─ widget.js       render(el, data, ctx)
├─ notes.md        the decision log of THIS widget (read it before touching it, write it afterwards)
├─ golden.json     recorded by the harness itself — delete it if you change the shape of view_data on purpose
└─ __init__.py     empty
```

- **`view_data(q)` is the HOT path**: it runs on every render AND again on every SSE push. It serves the
  CACHE. No network in there. Every call to the outside world lives in `apply_action`, which runs once per
  operator intent.
- **`apply_action` is a TABLE.** One `_a_<name>(action, p)` function per action, a module-level
  `ACTIONS = {"name": fn}` literal in `data.py`, and `apply_action` is the lookup — the gate reads the table's
  keys, and anything it cannot read fail-opens. The full rule and the reference are in `widgets/AGENTS.md`
  (`widgets/musica/` is the worked example).
- **`apply_action` RETURNS what it finds.** An action that only repaints leaves the turn with nothing to say:
  "do I have a contract with Axa?" is a QUESTION. Return `matches` and the turn can name them.
- **An action error TEACHES the shape of the retry** — which field is missing, which actions exist — and names
  the way out. A "no" that does not say how to get out reads as a breakdown.
- **`ref_index()`** if any action points at an item by id: the model NEVER invents ids. Give a DIFFERENT `field`
  per item class, or "open the budget" will walk into the folder named like the file.
- **`prompt_digest()`** if, with the card open, it makes sense to answer about its content without a round trip.
  Bound it and **say it is bounded** ("and 12 more"): a truncated listing that does not say so reads as the total.

---

## 4. The wiring — the list of places that fail EMPTY

**This is the section that saves the most time.** None of these points raises an error when forgotten; all of
them produce an empty surface or an invisible capability.

| # | Touch | If you forget it |
|---|---|---|
| 1 | `connectors/registry.py` → add `_<family>()` **and put it in `descriptors()`** | the connector does not exist for ⚙ or for anyone |
| 2 | `server/__init__.py` → import + **the `routers` list** | the control plane answers 404 and it looks like a network bug |
| 3 | `widgets/registry.py::_BUILTINS` | the widget is marked "yours" instead of "built-in" |
| 4 | `ConfigPanel.js` → the connector card **and the `fams` list** | the cards exist and NOBODY renders them |
| 5 | `frontend/app/services/api.js` | the panel's button has nobody to call |
| 6 | `i18n/genesis/en/ui.json` **and** `es.json` | `t()` returns the KEY, which is truthy: `config.cx.fam_files` shows up on screen |
| 7 | `widgets/validator.py::_STDLIB_EXEMPT` if `data.py` imports a connector | `make test-widgets` red for everybody |
| 8 | `tests/run_testmap.py` | the tests exist and **nobody runs them** |
| 9 | `connectors/catalog/<id>.json` with `state: "built"` | the connector does not show up in capability search, and if it was `planned` it keeps being offered as pending |
| 10 | `ChatWall.js::CONN_FAMILY_ORDER` if the FAMILY is new | the family falls into the "alphabetical at the end" drawer and the connector is painted under Infrastructure |
| 11 | `chat.connFamily.<fam>` in `en.json` **and** `es.json` | `t()` returns the KEY: `chat.connFamily.agenda` appears as a section title |
| 12 | `nucleo/flash/connector_briefs.py` | the brain has the VERB but not the STATE — and narrates instead of acting |
| 13 | `.meshkore/credentials/README.md` | nobody knows which variable to fill in, or where the credentials file goes |
| 14 | `.meshkore/docs/modules/zaelar-connectors-inventory.md` | the list stops telling the truth the same day |
| 15 | **`widgets.<id>.name` in `en.json` AND `es.json`** | the card is titled from `manifest.json`, i.e. in whatever language you wrote it, for everyone |
| 16 | **`tt("key", params, "<the literal>")` on EVERY visible string in `widget.js`**, with its row in both bundles | a session in English reads your buttons in Spanish — and the gate (node 4.11) rejects it |

> Points 9-14 have a ratchet: `tests/connectors/unit/catalog/test_a_built_connector_is_never_on_the_wishlist.py`
> (node 5.7) checks 9, 10 and 11 against the live registry, plus "no `built` without a live row" and "no
> duplicate id".
>
> Points 15-16 also have a ratchet, and this one DOES fail the build:
> `tests/browser/unit/i18n/test_widget_keys.py` (node 4.11) rejects a key missing from either bundle, an
> unwrapped accented literal, and — independently of language — **any** literal assigned to
> `textContent`/`title`/`placeholder`/`alt`/`ariaLabel`.
> ⚠️ The trap you cannot see by reading: **a module-level TABLE of labels** (`const STATUS = {ok:"Done"}`) is
> built at IMPORT time, before any `ctx` exists, so it freezes the language forever. Make it a function and
> resolve it on every paint.

**Golden rule of wiring:** every time a layer READS a field, check that the layer that writes it sends it. The
classic shape: the widget's panel reads `tiers`, the ⚙ card reads `tiers`, and the registry does not send them.
The check takes ten seconds: `grep -n "<field>"` in the producer and in the consumer.

---

## 5. The FlashBrain's skills — how the capability is declared

All of this lives in `manifest.json`, and all of this is what the model sees.

- **`actions`**: one entry per action, **not one more and not one fewer** than `apply_action` handles. The
  validation gate REJECTS either mismatch. An undeclared action is INVISIBLE even if it works; a declared one
  that nobody handles is a dead entry.
- **`"view": true`** on every action that only changes what is seen. It is what lets "open my Drive" *list*
  instead of just raising the card. ⚠️ **When marking them, the first question is not which ones are lenses but
  WHICH ONE ANSWERS THE SENTENCE THE WIDGET EXISTS FOR** — that is exactly the one an opt-in pass skips, and
  skipping it leaves the card open and empty.
- **`"confirm": true`** only if truly irreversible (pay, send, publish, delete). Reversible actions go bare.
- **`usage`**: how to drive the widget — which action for which intent. It goes into the prompt; keep it short.
- **`whenToUse`**: the ROUTING line. **It has a budget: 300 characters** (`widgets/brief._PURPOSE_CAP`), and
  what gets cut is the end, which is where the BOUNDARY clause sits. Write it to FIT and check it with a test
  against `brief._purpose`, not by eye.
- **`keywords` / `aliases`**: precise and non-overlapping. The harness warns about collisions; validation
  rejects a manifest whose keywords ALL belong to other widgets.

⚠️ **A CONNECTOR HAS TWO HALVES, AND THE SECOND ONE IS THE EASY ONE TO FORGET: the ACTIONS and the WORDS that
lead to them.** A new connector adds `connect`/`disconnect` to a widget and rarely touches its `whenToUse` —
which is the ROUTING line, the one the model reads to choose a widget. If, among all the widgets in the prompt,
the only one whose line talks about connecting is a different one (say, messaging: "…or connect a channel"),
then "open the google connector" routes there, even though the calendar widget is the one that owns the Google
Calendar connector. The model routes with what it has.

The rule, then:

1. The routing line **NAMES the service and the linking verb**, and when another widget already claims similar
   words, **it states the boundary** ("it is the calendar, not messaging, that owns the X connector").
2. And it has to **FIT**: the budget is 300 characters and what gets cut is the end, which is exactly where the
   boundary was just written. Check it against `brief._purpose`, not by eye (trap T4).
3. `keywords` grow **in BOTH languages** — «conectar calendario» AND "connect calendar". Routing in one language
   against a widget whose words are all in the other one fails. And they are ADDED: an English word never
   replaces its Spanish equivalent.
- **`worker_guide`** if a Brain Worker is meant to deliver here: tell it the TWO steps (write the JSON to a
  relative file with Write, then `python -m nucleo.cli.widget data <id> <action> @file`). Pasting JSON on the
  command line is blocked by the quotes and by the shell guard.

---

## 6. The boundaries you do not cross

1. **Voice carries INTENT, never a credential.** No action `payload` carries `client_secret`, `token` or
   `password`. Registering the app is done ONCE in ⚙ → Connectors. Put it under test: voice reaches exactly those
   payloads.
2. **`widget.js` does not touch the network.** No `fetch`, no WebSocket, no dynamic `import()`. If something
   external has to be started (an OAuth consent), a **declared action** does it and returns the URL, and the card
   opens it. Open the window SYNCHRONOUSLY in the click and fill its `location` afterwards, or the browser blocks it.
3. **All external text is UNTRUSTED**: `textContent` and `createElement`, never `innerHTML`. A file called
   `<img onerror=…>` is a legal name on every provider.
4. **Widgets do not talk to each other.** Return the data and let the BRAIN decide. Never import another widget
   from yours.
5. **`data.py` is stdlib.** If your widget IS a connector and there is no stdlib equivalent, it goes into the
   curated `_STDLIB_EXEMPT` list **with its reason written down**, and keeps the import DEFERRED inside the
   functions so that importing the module — and therefore the catalog, and therefore every prompt — does not pay
   for `httpx`.
6. **Each widget writes only under `widgets/_data/<its-id>/`.** Never outside.
7. **Public/private boundary**: `engine/` is PUBLIC. Describe the MECHANISM here; deployment-specific policy is
   out of scope for this repo.

---

## 7. The tests — the complete set

There are **five classes**, and the fourth is the one most often missing.

| class | where | what it proves |
|---|---|---|
| **connector** | `tests/connectors/unit/<family>/` | the REASONING around the HTTP: states that look alike, provider failures, normalization |
| **widget contract** | `tests/browser/unit/<id>/` | declared==handled · `view` · no credentials in payloads · `whenToUse` fits · `view_data` does not touch the network |
| **rendering** | `tests/browser/e2e/widgets/test_<id>_render.py` | what no reading of the source can give you (see below) |
| **LIVE** | the same directory, node `live: True` | the real round trip against the operator's account |
| **two screens** | automatic: node 4.270 (the whole catalogue, nothing to write) + `tests.widget_harness --two-screens <id>`; manual: `tests.widget_harness --manual <id>` | the widget does what its `"screens"` says with the agent open on a computer AND a phone — `.meshkore/docs/ops/zaelar-two-screen-test.md` |

**Rendering is not decoration.** `t()` returns the KEY when a translation is missing, and the key is truthy; a
DOM handle written as `cond ? a : b` leaves a detached canvas with no error at all; a notice can exist in the DOM
with ZERO height. No source test sees any of that. And if your widget paints external text, **render a hostile
name and assert that no element was born**.

**The LIVE test** — when the piece needs a real account:
- It goes in a **`"live": True`** node, which `deterministic_paths()` excludes: it does not run in CI and does not
  turn red on a machine without an account.
- **It SKIPS with the exact steps to enable it.** *Pending* is a legitimate state; passing on empty and being
  mistaken for coverage is not.
- **It never asserts or prints the operator's content.** This repo is public. Assert SHAPE and INVARIANTS, never
  what the person has.
- Even if it cannot be executed, **the circuit is built in full**: the day a credential exists, nothing has to be
  written.

**Disarms are mandatory.** For every decision, break the code and check the test turns RED — and **ASSERT that
the mutation was applied** before measuring: a green disarm is a badly applied mutation until proven otherwise.
Count how many tests ran; in zsh an unquoted parameter is not word-split, and `pytest $T` with two paths inside
runs *"no tests ran"* while looking green.

**Register the files in `tests/run_testmap.py`.** A new file needs its line **even if the directory is already
covered**: the map lists explicit paths, it does not glob. Check afterwards:

```bash
./.venv/bin/python -c "from tests.platform import catalog; p=set(catalog.deterministic_paths('all')); \
  print('unit', '<unit path>' in p); print('live excluded', '<live path>' not in p)"
```

---

## 7-bis. The LAST MILE — the operator has to be able to CONNECT it

A connector that is built, wired and green is still useless until the operator gives consent. The agent cannot
do that part, and the design has to say so instead of pretending otherwise.

- **Consent is ALWAYS a CLICK of theirs.** `window.open()` only survives inside the gesture that opens it; a
  window opened after an `await` is blocked by every browser **silently**. That is why the card opens the popup
  SYNCHRONOUSLY in the click and fills its `location` afterwards.
- **By voice, the action does the half it can: it leaves the card ON the step with the button.** Returning the
  URL does not help: `nucleo/flash/widget_data_turn.py` keeps `{widget, act}` and **drops the action's result**,
  so nothing you return reaches the model or the operator. The nudge travels through `view_data()` with the token
  shape the pushed view already uses — a COUNTER (asking twice lands twice) and an `at` that EXPIRES (tomorrow's
  repaint does not open a setup screen on top of them).
- **The screen moves even when the connector REFUSES.** If the nudge depended on the URL coming out right, the
  case that most needs a screen — no OAuth app registered — would be exactly the one without it.
- **The sentence is declared by the MANIFEST, not by the result.** Since the result is dropped, the only way the
  voice knows what to say is the action's `desc`, which does travel in the prompt: call it, tell them to press the
  button, and **never dictate the URL**.
- **A "web" OAuth client requires the return URIs registered BEFOREHAND**, or Google answers `invalid_client` at
  the END of a flow that looks healthy. Print the exact list and put it in the credentials README.

## 7-ter. Declaring it DONE — the five places where a connector stops being pending

This is what gets skipped once the technical part works and it feels finished.

1. **`connectors/catalog/<id>.json` → `state: "built"`.** If it was `planned`, this is what **removes it from the
   pending connectors**: the chat wall paints the wishlist (`planned` + `not-possible`) with an "I want it"
   button, so a live connector still marked `planned` offers the operator something they already have. **If a
   manifest parks something behind a CONDITION, the condition is written in its `notes`, and lifting it is the
   last step of whatever fulfils it.**
2. **Manifest id = the id of its live row.** `catalog.search()` ranks "connected" by comparing ids against the
   registry; with a different id — even a nicer one — search will never know it is linked.
3. **The registry row and its family**, with the family wired at points 10 and 11 of §4.
4. **The list**: a row in `.meshkore/docs/modules/zaelar-connectors-inventory.md`, with its widget and its doc.
5. **The brain**: its state in `connector_briefs.py`, and — if it introduces a capability the model has never
   seen — **the sentence that NAMES its mechanism**. A capability named without its mechanism gets improvised: the
   model invents a tool that does not exist.

## 8. The documentation — every place, never most of them

1. **Module doc** — `engine/.meshkore/docs/modules/zaelar-<piece>.md`: anatomy, contract, the decisions with
   their why. Public → mechanism only.
2. **`.meshkore/docs/criteria.md`** — one line, with its test node, if a rule the engine obeys changed.
3. **The widget's `notes.md`**, which is what stops the next session from undoing a decision already taken.
4. **The LIST** (`.meshkore/docs/modules/zaelar-connectors-inventory.md`): what is read to know what exists.
5. If the piece has a part that is not the engine's, only the mechanism goes here.

---

## 9. Commit and push — with several agents on the same tree

The tree is shared by several sessions and **the git index is SHARED**.

```bash
git status --short                       # whose is each change?
git diff --cached --name-only            # if it lists someone else's files, someone filled the index
git diff <file>                          # a pathspec limits FILES, not HUNKS
git add <new paths> && git commit -m "…" -- <paths>    # ⚠️ IN ONE COMMAND
git push origin main
```

- **A bare `git commit` commits the WHOLE INDEX.** Always use `git commit -m "…" -- <paths>`.
- ⚠️ **NEW files need `git add`, and that `add` opens a window** in which a bare `git commit` from ANOTHER session
  takes them into its own commit. Do `add` and `commit` **in the same command** and leave nothing staged in
  between.
- Options go BEFORE `--`; after `--` everything is a path.
- If it is already pushed and the attribution came out wrong: **`main` is not rewritten**. The code is not lost;
  tell the peer and move on.
- **Commit early**, even before testing. Losing code is not reversible.

---

## 10. Live verification

A green test is not a working product.

```bash
./zaelar status                          # is HEAD running?
./zaelar restart                         # NEVER with live voice or with a battery measuring
```

- Check routes with a **real request** (`TestClient` or `curl`), not by reading `app.routes`: in this FastAPI
  version included routers are stored wrapped and **it looks like there are no routes** (§11-T5).
- Open the card and LOOK at it.
- Write down what was **not verified live**. It is the honest half of the report.

---

## 11. The traps

| | Trap | What it costs |
|---|---|---|
| **T1** | A legitimate state that produces the SAME emptiness as a failure | "your Drive is empty" to someone whose Drive is full, and the defect gets diagnosed as a broken connector. **Return `ok` + `reason`.** |
| **T2** | A consumer reads a field its producer does not send | The surface comes out empty, with no error. `grep` the field on both sides. |
| **T3** | Adding the card and forgetting the ⚙ family list | The card exists and nobody renders it |
| **T4** | `whenToUse` > 300 chars | The BOUNDARY clause is cut and routing is lost exactly where it matters |
| **T5** | Verifying mounting by reading `app.routes` | Gives `[]` with the routes perfectly mounted → you "fix" something that works |
| **T6** | A test that scans the source and matches its own COMMENTS | Permanently red on a file that documents the rule. Assert the PATTERN (`.innerHTML =`), not the word |
| **T7** | A test double that is too generous | A fake `breadcrumb` that returns 2 levels for everything makes a "go up from level 1" test assert the wrong parent |
| **T8** | `git add` on a shared tree | Another session takes your files into ITS commit |
| **T9** | New test file without a testmap line | Green and **nobody runs it** |
| **T10** | Choosing an `/api/` prefix already in use | Two routers, one wins by mount order, silently |
| **T11** | Adding the ACTIONS and not the WORDS (`whenToUse`/`keywords`) | The model routes to the neighbouring widget that does say "connect", and its answer sounds perfectly reasonable |
| **T12** | Returning the consent URL expecting it to reach the model | The turn report drops the result: the action runs, the screen does not move and the voice stays silent |
| **T13** | Leaving a working connector as `planned` | The chat wall offers "I want it" for something the operator already has |
| **T14** | A catalog id different from the id of its live row | `search()` never ranks it as connected, and nothing fails |

---

## 12. The checklist (copy and paste when closing)

```
CONNECTOR
[ ] providers.py: providers are DATA; differences are fields
[ ] oauth.py: shared PKCE · tokens in the credential store (600, gitignored) · the permission travels with the token
[ ] oauth.py is a thin module over connectors/oauth_base.py, and the connector is in node 5.62's CONNECTORS
[ ] one client per provider → SAME normalized shape (with a test)
[ ] service.py: fail-safe · what-is-not-an-error returns ok+reason
[ ] server_api.py: /api prefix free (checked with grep)

WIDGET
[ ] manifest: actions == apply_action · view on the one that ANSWERS · confirm only if irreversible
[ ] whenToUse fits in 300 (test against brief._purpose) · usage · aliases · keywords without total collision
[ ] cheap view_data (no network) · apply_action returns what it finds · errors that teach the shape
[ ] apply_action is an ACTIONS = {name: fn} table, one function per action
[ ] ref_index if there are ids · prompt_digest if relevant (bounded, and saying so)
[ ] background: decided and written down · runtime{} if it produces
[ ] screens: "shared" or "single" declared (single if it takes the device's sound/picture)
[ ] two screens: `tests.widget_harness --two-screens <id>` green · the operator's manual pass (`--manual <id>`) done, written in notes.md
[ ] widget.js: no fetch · no innerHTML · textContent · classes with their own prefix · theme via --hb-*

WIRING  (the 16 points of §4, one by one)
[ ] connector registry + descriptors()   [ ] server routers      [ ] _BUILTINS
[ ] ConfigPanel card + fams              [ ] api.js              [ ] i18n en+es
[ ] _STDLIB_EXEMPT if relevant           [ ] run_testmap.py
[ ] catalog/<id>.json state:"built", id == id of the live row
[ ] CONN_FAMILY_ORDER + chat.connFamily.<fam> in both bundles (if the family is new)
[ ] connector_briefs.py (the STATE, not just the verb)   [ ] credentials/README.md

ROUTING  (§5 — the half that gets forgotten)
[ ] whenToUse names the service AND the linking verb, with its boundary, and FITS in 300
[ ] keywords/aliases in BOTH languages, added (never replaced)

LAST MILE  (§7-bis)
[ ] consent is the operator's click · popup opened INSIDE the click
[ ] by voice: the card stays ON the button's step (token with counter + expiry)
[ ] the screen moves even if the connector refuses
[ ] the action's desc carries the sentence · and forbids dictating the URL
[ ] return URIs registered (web client) and printed in the README

TESTS
[ ] connector · contract · RENDERING · live (live:True, skips with instructions)
[ ] disarms with the mutation ASSERTED, and how many tests ran
[ ] make test-widgets green · the new node in deterministic_paths, the live one out

DOCS
[ ] module doc   [ ] criteria.md (if a rule changed)   [ ] notes.md
[ ] row in zaelar-connectors-inventory.md
[ ] mechanism only here

CLOSE
[ ] add+commit in ONE command, with pathspec · push
[ ] verified live, and written down what could NOT be verified
```
