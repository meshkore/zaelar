---
title: Action Map
category: modules
updated: 2026-09-02
owner: ricart
status: current
---

# The action map — a KNOWN phrase skips the model

`nucleo/actionmap/` is a deterministic layer that sits **in front of the FlashBrain**. One finalized
utterance is normalized and looked up, verbatim, in a per-language table of verified command phrases. A hit
executes a direct action in **silence**, in well under a millisecond; everything else falls through to the
model, untouched.

It covers direct canvas and panel actions, declared view actions on widgets, verb × object grids and
upgradable language packs. See [Extension points](#extension-points) for where the design leaves room to grow.

## Why it exists

Many times a day an operator says «limpia la pantalla», «abre el WhatsApp», «cierra la agenda». Without the map,
every one of those is a full model turn: a network round-trip, tokens spent, and a non-zero chance that a small
model narrates the action instead of calling the tool.

A short command whose meaning has already been verified does not need to be understood again.

## The doctrine boundary — this is NOT intent classification

The house rule stands («no hardcoded, understand»): we do not write verb tables and we do not teach the
brain to guess. The map does not violate it because of what it is *not* allowed to do:

- it matches the **whole utterance**, normalized, and nothing else — no keyword spotting, no fuzzy distance, no
  stemming, no stopword removal;
- it **never splits** a sentence. «Ponte a buscar un restaurante y abre el WhatsApp» has no entry and goes to
  the model whole. Two actions in one sentence is exactly the case a lookup table cannot judge;
- **when in doubt, the model.** Every failure path — unknown phrase, unresolvable target, undeclared data-op,
  no running loop, a broken index, a disabled row — falls through. `execute()` returning `False` is a routing
  decision, never an error;
- its certainty comes from the **provenance of the entry** (shipped, or defined by the operator), never from
  string similarity.

The unit of matching is *a short phrase bounded by silence*. A chain of commands — «abre el WhatsApp… ahora el
Telegram… enséñame el correo» — is N utterances, therefore N lookups and zero model calls, which is precisely
the workload that motivated the module.

## Architecture

### Where it hooks in — BOTH channels

| Channel | File | Position |
|---|---|---|
| voice and text (one pipeline) | the fast lane (`voice/engine/llm/providers/fast_lane.py`), called from `nucleo/turn/pipeline_gate.py` | after the hard-interrupt/gate region, before the fragment accumulator |

Both go through the one shared module; neither reimplements it. The voice hook is additionally guarded against
a **pending fragment chain** (`brain._acc.fragments`): mid-accumulation the utterance is not yet a whole
utterance, so the map must not claim it.

Wiring a mechanism into only one channel is an easy mistake to make, so the testmap node carries an explicit
guard asserting both call sites exist. The probe also **runs** the action rather than merely reporting it: once
the map can drive a widget's data, a headless report alone would let a test pass without the data ever moving.

### The data

`action_map` in `zaelar.db` (`memory/schema.py::ACTION_MAP`):

```
id · lang · phrase · action(JSON) · source · status · hits · agree · disagree · created_at · last_hit_at
UNIQUE(lang, phrase)   index (lang, status)
```

All access goes through the **`memory/api.py` facade** (`action_map_active`, `action_map_add`,
`action_map_retarget_seed`, `action_map_seed_version`, `action_map_set_seed_version`, `action_map_hit`):
production code outside `memory/` may not touch memory internals, and the boundary guard enforces it.

`source` and `status` carry the two things that make the table safe to ship into: where a row came from, and
whether the operator has vetoed it.

**One install, one language.** The language is fixed at onboarding, and the runtime index holds only the active
one — `store.index()` is a plain `dict[phrase] → entry`, rebuilt lazily on first use, on a language change and
on writes. A miss costs one dict lookup.

### Normalization

`normalize.py`: lowercase → NFKD accent strip → punctuation to spaces → whitespace collapse. Deliberately
nothing else. Stemming or stopword removal would start making different sentences equal, which is the
classifier this module refuses to be.

### The closed allowlist

`executor.py` is the single place that says what a table row may run:

| `do` | required | notes |
|---|---|---|
| `show_widget` / `close_widget` / `fullscreen` | `widget` | |
| `close_all` | — | |
| `move` | `widget`, `where` | `left · right · center · top · bottom` |
| `show_panel` | `tab` | `chat · procesos · crons · clusters`; optional `action: open\|close` |
| `widget_data` | `widget`, `action` | only ops the widget declares **FAST**, checked at execute time |

Everything runs through the **same emit funnels the model's own output uses** — the `widget` / `panel` observer
events the frontend already consumes — never a parallel executor. The vocabulary is idempotent or reversible by
construction; nothing destructive, content-carrying or credential-adjacent is representable, whatever a row
says. `validate()` refuses a bad action **at import time, loudly** (an `alert` event): a module whose seeds
silently failed to load is a module born dead.

Named multi-step **workflows are deliberately not an action kind** — they belong to the errand circuit, see
[Extension points](#extension-points).

Two details that are easy to get wrong and are pinned by tests:

- **the phrase travels on every event**, including `close` / `move` / `fullscreen`: when the wrong widget opens,
  the first question is always *what text produced this?*;
- **a VIEW op brings the card up as well.** `widgets/actions.py::is_view` is a second axis, orthogonal to
  FAST/CONFIRM/ESCALATE, and opt-in per action — nothing is inferred from the name, because the same `open` is
  display-only in `mensajeria` and a real-world side effect in `navegador`. «Ábreme el WhatsApp» is one order
  with two halves: the card in front, that lens selected. The loop is acquired **before** any emit, so
  a run without one falls through whole instead of half-executed.

### Target resolution

Through `widgets.runtime.identify` — the one resolver the rest of the brain uses — with **no fuzzy
fallback**. An entry whose widget cannot be resolved with certainty does not execute; the turn goes to the
model.

### Seeding: the Genesis pack, and how it upgrades

`i18n/genesis/<lang>/actionmap.json` ships with the repo and is imported lazily the first time that language is
indexed — the `widgets/agenda/seed.json` convention.

A pack carries `entries` (literal phrase → action) and `grids`. A **grid** is a verb × object table for one
family of orders — `{abre|ábreme|muéstrame|…} × {el WhatsApp|el Telegram|el correo|…}` — expanded at import
into ordinary exact-match rows. It is *bookkeeping, not understanding*: nothing at match time gets smarter, the
table simply stops being written by hand. It exists because those families are exactly where a small model is
unreliable and where the phrasings are many and boring.

The pack is versioned and imports **once per pack version**, not once per install, so an improved pack reaches
every existing engine on upgrade instead of only fresh installs. On an upgrade new phrases
are inserted and a phrase that is still an **untouched shipped row** is retargeted; a row the operator disabled,
or one the map learned, is never moved (`INSERT OR IGNORE` + `source='seed' AND status='active'` on the
retarget). **A veto survives every release.**

### Kill switch

`ZAELAR_ACTIONMAP=0` (checked **first** and **off-only**, so a broken config store cannot force the module on),
then `config/v2.py` `actionmap.enabled`. The precedence trap is the documented one: a stored value beats the env
fallback, which is why the env check is explicit and first.

## Observability — which layer acted

Every surface must be able to tell a map turn from a model turn, so the origin is a **field, not an
inference**:

- `kind="actionmap"`, family `flash` (`voice/observer.py::_CAT`), two labels: `⚡ action map: direct action (no
  model)` and `🕵️ map candidate…`;
- every map event carries `engine: "actionmap"` and `origin: "actionmap"`, plus `action`, `entry`, `source`,
  `match_ms` and the phrase; a model turn stamps `origin: "flash"`. **Counting turns by origin is a field, not
  a guess from the label.**
- `match_ms` is folded into `pre_ms` as `amap_ms`, the existing per-segment latency convention
  (`nucleo/flash/turn_perf.py`);
- the local viewer (◷) prints `ActionMap` in the LAYER column, which reads `engine` — that is why the field is
  stamped, not decoration.

**`watch.py` measures the other half of the question — what the map is MISSING.** A bus subscriber on
`turn.completed` (zero coupling with the voice provider). When the model resolves a turn
with a single canvas action, nothing heavier behind it and almost nothing to say, that turn is emitted as a
**map candidate**, marked with whether the phrase is already in the table — an entry that exists but did not
fire is a different problem from a missing entry, and conflating the two is how a table looks healthy while
never being used. It observes only: it writes no rows and promotes nothing.

> ⚠️ `turn_detail` is one seam but the two channels write **different decision shapes** — voice writes flags
> (`widget_acted`, `shown_ids`, …), the probe writes a collapsed `{action, tool_calls, tags, reply}`. A reader
> that knows one shape is blind to a whole channel and **silently returns nothing**. `watch.py` branches on a
> sentinel key and is tested against both.

## Tests

Node **2.41** of the testmap (`tests/agent_headless/unit/actionmap/`) — hits and misses, the closed
allowlist, the loud seed refusal, the one-install-one-language rule, both kill switches, the candidate logic for
both decision shapes and the wiring guard on both channels. Node **2.7** covers the auditor knowing which layer
acted, node **2.1** the interaction with the show/`widget_data` guard.

## Extension points

The design leaves room for:

- **Conversational definition** — a router tool that creates, retargets or disables entries by conversation,
  with passive candidate capture in shadow mode and promotion/demotion driven by `agree` / `disagree` counters
  (the columns already exist in the table).
- **Generated language packs** — `i18n/generated/<code>.actions.json` alongside the shipped Genesis packs.
- **More declared view ops** — any connector widget can declare view actions the same way messaging does.
- **Workflows** — named chains («resérvame mesa hoy») fire the normal errand circuit, never a recorded macro, so
  they live outside this module.

Today the table grows with each release. The auditor can name a map fault and `watch.py` can point at what
should probably be an entry, so any runtime promotion starts from observed evidence instead of intuition.
