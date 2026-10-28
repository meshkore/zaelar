# Rules — one scoped table for every standing rule and preference

**The rule: a standing rule and a preference are the same thing. Each one is a ROW with a scope, read by a
deterministic cascade; the model shapes a new row once, when it is written, and never reads the table to decide
anything.** Code: `rules/` (initiative V2-806).

## Why one table

Before this, the same spoken sentence could land in up to three shapes — a style flag (`config/style.json`), a
consent class (`config/consent.json`) and a free-text line in the memory state (`state.rules` +
`state.rule_scopes`) — each written by its own regex, and the free text rode every prompt whether the turn
needed it or not. A widget kept its own preferences (`widgets/_data/youtube` `prefs`/`prefs_notes`), and the
autoresponder rewrote a consent class globally to turn itself on. Six stores, three classifiers, no listing.

## The row

| field | meaning |
|---|---|
| `id` | stable id. User rows: `r_<hex>`; defaults: `default:<key>@<scope>`; migrated rows: derived from their origin, so a re-run inserts nothing |
| `scope` | where it applies (grammar below) |
| `kind` | `gate` — applied by code, decides act/ask; `pref` — a value an owner reads, or a `note` the model reads |
| `key` | what it sets: `consent` (allow · ask · never), `ask_at` (a sensitivity level), a style knob, a widget preference, or `note` |
| `value` | JSON |
| `except` | narrower scopes the row does NOT cover |
| `source` | `default` (genesis / manifests) or `user` (his words, the Settings panel, a migrated override) |
| `text` | his own words, verbatim |
| `created_at`, `active`, `until` | `until` is an epoch; a row past it is read as inactive by the clock at read time — nothing sweeps it |

The table lives in the same SQLite file as memory (`ZAELAR_DB`), owned by `rules/` — memory neither reads nor
writes it.

## Scope grammar

A scope is a string; `/` separates levels inside a family and `*` matches any one segment.

```
global
<domain>                         messaging · calendar · payment · web · account · voice
<domain>/<channel>               messaging/email
<domain>/<channel|*>/<act>       messaging/email/send_new · messaging/*/send_new · payment/*/authorize
widget:<id>                      widget:youtube
widget:<id>/<action>             widget:youtube/play
item:<id>                        item:c17
```

The vocabulary is **read, not invented**:

- a consent class `<domain>.<act>` (genesis `consent.classes`, a manifest action's `consent_class`, a widget's
  `consent_scope` hook) maps to `<domain>/*/<act>`; refined by a channel (`<class>@<channel>`) it maps to
  `<domain>/<channel>/<act>`;
- channels are the connector catalog's built entries that declare a `consent_class`;
- widgets and actions are the installed manifests;
- `voice` is the agent's own mouth (how it speaks), the one domain that is not a consent class.

## The request's path, and the cascade

A request is understood before any rule is read: the decision model and the widget layer already name the
widget, the action, its consent class (refined by its channel) and, when there is one, the item. From that the
engine builds the request's **path** — its anchors, general to specific:

| level | anchor |
|---|---|
| 0 | `global` |
| 1 | `messaging` |
| 2 | `messaging/email` |
| 3 | `widget:mensajeria` |
| 4 | `messaging/email/send_new` · `widget:mensajeria/send_draft` |
| 5 | `item:<id>` |

A channel the call cannot name is `*` in the path, and a row for a named channel never matches it.

A row **covers** the request when its scope matches one of the anchors segment by segment (`*` in the row
matches anything) and none of its `except` scopes does. Selection is a prefix walk over strings — no model.

The covering rows are applied in order and, per key, **the last one wins**:

1. lower level first — the more specific row runs last;
2. at the same level, a row with fewer `*` is more specific;
3. at the same level and specificity, `user` runs after `default`;
4. then by `created_at`.

`note` rows do not override each other: every covering note is kept.

Specificity outranks the source, as decided: a broad row of his (`messaging`) does not beat a narrower factory
row (`messaging/*/send_new`). That is why a new rule is written at the narrowest DECLARED scope that matches what
he said (see «Writing a rule»): «ask before sending messages» is a row at the class's own scope, where it meets
the default and wins.

An exception is either a narrower row («email: allow» + «messaging/email/send_new@item:c17: ask») or the row's
own `except` list.

## Defaults are rows too

`source=default` rows are built from declared data at read time and never stored: genesis
`consent.classes` (one `consent` gate per class), genesis `consent.ask_at` (the global level), and genesis
`style` (the `voice` preferences). A user row at the same scope and key runs after its default and wins. A
default cannot be deleted; it can be overridden.

A widget action's declared sensitivity (`sensitivity`, `confirm`, `view`, the widget's `security`) is NOT a
row: it is a property of the action, read as the *level* the class rule is compared against.

## What the cascade decides, and what it cannot

`consent.decide` asks, in order:

1. a missing fact → ask for the fact;
2. more than one candidate → ask which;
3. the cascade's `consent` for this path: `never` → refuse, `ask` → ask;
4. **the radius**: an unbounded call, or one that touches more than one thing → ask;
5. `allow` (or his explicit order over a row he has seen) → act;
6. the action's level against the cascade's `ask_at` → ask or act.

Steps 1, 2 and 4 are **rails on the consequence**: they are code in `consent.decide`, outside the table, and no
row — not even a global `allow` — reaches them.

## Writing a rule

A new spoken rule is structured ONCE, when it is written: one structured model call (the same off-turn
seat the engine uses for small strict-JSON tasks, `nucleo/memory_agent/processor/llm.py`) is handed the sentence and the declared
vocabulary and answers `{op, scope, kind, key, value, except, until}`. The scope is validated against the
vocabulary; a scope nobody declared becomes the nearest declared ancestor. If no model answers, the sentence is
kept as a `note` at `global` — what every rule was before scopes existed. The agent repeats the stored row back
once, in plain words.

«Forget the rule about emails» is resolved the same way: the call names the scope, and the row is removed **by
id**. Two candidates are a question, never a guess.

`until` is optional («don't bother me today» → the end of today); there is no expiry by default.

## What reaches the model

- `gate` rows never enter the prompt: code applies them.
- `pref` rows whose key is read by code (style knobs, a widget's preferences) reach the model only through the
  line their owner already composes.
- `note` rows enter the prompt **only for the scopes in play in that turn**: `global` and `voice` on the voice
  surface; a widget's notes when that widget is on screen, named in the turn or recently used. The worker's
  dossier carries `global` and widget notes, never `voice`.

There is no always-on block of «the newest N rules».

## Listing and editing

He never sees a scope, a key or an id: he says his rules and the system files them. The same rows are the list —
by voice («what rules do I have?») and in ⚙ Settings → Rules — always in his words: a row is his own sentence (a
row he never worded is named by what it sets), and its place is named from declared data in his language
(`rules/labels.py`: «In general», «Email · send new messages», «YouTube»), grouped the same way on screen and
aloud. Ids and scopes are the handles the panel and `/api/rules` use underneath; only the model's own permission
line keeps the technical scope. A default shows as a default; editing it writes a user row at the same scope.
