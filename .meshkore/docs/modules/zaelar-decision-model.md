# The decision model — one bounded-choice primitive, and where it may sit

> **What this is.** A small, non-generative model (TypeSafe System One, «Jev») that answers ENUMERATED
> questions with a calibrated confidence. It picks among options it is handed. It writes no text, it
> knows nothing it was not given, and nothing it answers executes anything.
>
> **Where the detail lives.** `nucleo/jev.py` (the only module that talks to it) and
> `nucleo/flash/turn_brief.py` (the turn's questions). This document is the ANATOMY: the contract,
> who may call it, from where, and the rules that do not move.

## Why it exists

Some decisions in a turn are genuinely hard for a small fast model and trivial for a specialist:
*is this an errand worth a Brain Worker, or chatter? does this sentence license opening a card? with
three cards open, which one is «close that» about?* Those are **bounded choices**: the options exist,
they are declared, and what is needed is a pick among them — not prose, not a plan.

Paying a reasoning round trip for a bounded choice is the waste this exists to remove. Paying an
800 ms classifier round trip for something a local lookup answers in 3 ms is the waste it can
CREATE, which is why placement is half of this document.

## THE RULE OF PLACEMENT (V2-726, measured)

> **It serves what is decided AFTER the model. What is decided before it is not its business.**

| Anchor, from the turn's admission | p50 |
|---|---|
| prompt assembled | 3 ms |
| tool catalogue settled | 381 ms |
| a verdict lands | 785 ms |
| model's first token | 1 919 ms |
| reply complete | 4 192 ms |

A brief fired when the turn is admitted reaches a POST-model reader with seconds to spare, and can
never reach a PRE-model one without making the model wait. That is not a tuning parameter: it is the
reason «put the classifier in front of the model» is the opposite design, not a smaller one.

**And the cost is the ROUND TRIP, not the questions**: 1 question 800 ms, 4 heterogeneous 708-826 ms,
100 candidates 1 041 ms. Everything a turn needs therefore goes in ONE call.

## The two shapes, and the one contract

| Call | Shape | Used by |
|---|---|---|
| `ask_many` / `choose_many_sync` | N different questions, one trip | the turn brief |
| `select_many_status` | N candidates scored against ONE criterion | task recall |
| `decide` | ONE choice among N declared candidates, with a status | workers, and anything new |

`decide(purpose, evidence, candidates, …) -> Decision`:

```
{status, chosen: [id], confidence: {id: float}, latency_ms, call_id, provenance}
```

**The eight statuses exist because emptiness is ambiguous.** Three are ANSWERS the caller should act
on and five are ABSENCES it should route around:

| Answer | Means |
|---|---|
| `selected` | one candidate, at or above the confidence gate |
| `no_match` | it looked and none of them is what was asked |
| `abstained` | it looked and declined — `none`, or below the gate |

| Absence | Means |
|---|---|
| `unavailable` | network, timeout, open circuit breaker: nobody chose |
| `disabled` | switched off or no key: nobody chose |
| `empty` | nothing was handed to it to choose between |
| `expired` | the deadline passed, queue time included |
| `too_big` | more candidates or evidence than the bounds allow, refused before the wire |

Before this contract, all of them were `[]`, and a shortlist nobody had looked at was being
presented as one the chooser had narrowed.

## Who may call it, and from where

| Caller | Door | Note |
|---|---|---|
| the voice turn | `turn_brief.ask_for_turn` at the ADMITTED sentence | one brief per turn; readers `peek` |
| the cover phrase | the same brief (`request_type`) | it used to open a second socket for the same words |
| memory / task recall | `select_many_status` | narrows with a lexical index FIRST (INI-027 §7) |
| a Brain Worker | `worker_bridge decide @file.json` → `/api/worker/act` | ONE allowed action, behind the task token |
| the probe / text channel | `choose_sync`, `classify_sync` | blocking, and has no event loop to freeze |

A worker is a subprocess: it reaches the engine only through that endpoint, which already carries
the authentication, the policy and the piggyback. The payload goes by FILE, like every other payload
on that bridge — our own permission gate rejects an argument containing braces and quotes.

## The turn's brief

One call, fired at the admitted sentence, carrying every question read after the model:

| Key | Question |
|---|---|
| `canvas` | show / close / neither — a backstop for a tag the grammar missed |
| `request_type` | what KIND of turn, which picks the cover phrase's pool |
| `escalate_or_inline` | does this need a background worker? |
| `screen_action` | which declared action of which OPEN CARD, keyed by instance |
| `catalog_widget` | (when nothing is open) which widget of the catalogue is NAMED |

The last two are never asked together: with cards open, the ACTION is what disambiguates (0.94
against 0.26 for «which widget» over descriptions). The widget falls out of the action.

**The criteria text is the product surface of these decisions.** Built from a widget's `desc` alone
the targeting scored 6/9; from «Name» + aliases + the same desc, 8/9. The words a widget answers to
are the widget's own declaration, not a table in the engine.

⚠️ **And only the part of a declaration that ARRIVES can decide anything** (V2-753). `screen_action`
truncates each action's `desc` at `turn_brief.MAX_DESC_CHARS`, and while that bound was 90 it cut
`youtube:show_tab` mid-word — throwing away the clause V2-742 had written into the manifest so that
«vuelve al catálogo» would be routable at all. Measured against the real API: `none` 0.77 at 90
chars, `youtube:show_tab` **0.96** at 200, with `pause` 1.00, `next` 0.94 and `search` 0.99 unmoved
and no latency change (47 candidates, 4.7 KB → 5.8 KB, ~850 ms both). **When an action is never
chosen, read what the question actually said about it before blaming the model.**

⚠️ **Raising the bound did not end that class — writing past it is the same defect** (V2-755). The
`youtube:show_tab` description written the day the bound moved to 200 is **485 characters**, so «al
inicio del widget de vídeo» never arrived and the phrase came back `restart` 0.69 in the next live
session; rewritten to 199 it measures `show_tab` **0.94**. Across this house **48 of 220** declared
actions were over the bound, reaching the question beheaded with nothing saying so; 45 remain, as
declared debt with a ratchet (node 2.74). A declaration has to FIT the channel that decides with it.

⚠️ **Touching one description changes its NEIGHBOURS, so measure the neighbourhood** (V2-755). Three
times running, fattening the winner of one phrase starved the action next to it, and the symptom
surfaced two days later in another session: «PARA el vídeo de verdad» added to `close` made «Vale,
para el vídeo» stop being a pause (`none` 0.65, said twice); «vuelve al inicio DEL VÍDEO» added to
`restart` made «inicio del widget de vídeo» a rewind (0.99). The minimum measurement is every phrase
belonging to the actions that share vocabulary, before and after — never only the phrase being chased.
And a HOMOGRAPH is closed by NAMING it, not by listing more synonyms: «para» is also a preposition,
so «Vale, para el vídeo.» reads as «OK, for the video.» — quoting his wordings scored `none` 0.47,
adding «ahí «para» es el verbo, no la preposición» scored `pause` **0.98**, in the same 200 characters.

⚠️ **An UNSURE answer has no opinion; an ABSENT one still fails closed** (V2-756). The gate that lets
the verdict complete an empty turn used to require a confident `order`/`answer` on `request_type`, and
read «unsure» the same as «no answer» — so a torn reader vetoed a near-certain one: «Para el vídeo»
measured `screen_action = youtube:pause` **0.95** with `request_type` split between answer 0.49 and
comment 0.39, nothing fired, and the operator said «He dicho que pares el vídeo. Que no me has oído.»

It is a REFUSAL list now (`direct_action.NOT_AIMED_AT_THE_SCREEN`), and the reason is measured: the
SCREEN question already answers `none` at **0.87-0.99** for every ambient remark tested, so the two
guards agree exactly where it matters and only the request-type one was ever wrong.

    «¿el siguiente es de la NASA?»   question 1.00  · screen_action none 0.95
    «ese vídeo es antiguo»           comment  0.82  · screen_action none 0.96
    «hoy juega el Barça»             comment  1.00  · screen_action none 0.87
    «Bórrame los tres últimos…»      order    1.00  · screen_action remove 0.98

⚠️ **Measure against the candidate set of the turn you are repairing** (V2-756). The screen question is
enumerated PER CALL from what was open and possible at that moment, so a set borrowed from another
session is a different question. «Bórrame los tres últimos de la cola» measured `clear_list` 0.59
against a set that had no `remove` in it (the queue was empty then, so `_possible_now` had dropped it)
and `remove` **0.98** against the set of the turn that actually failed. The candidate list is in the
`probabilities` of that turn's brief event — take it from there, never from a neighbouring session.

## The rules that do not move

1. **`nucleo/jev.py` is the only module that talks to it.** One endpoint, one key, one timeout.
2. **Every answer is enumerated per call from DECLARED capabilities** — manifest actions of what is
   open, the escalate pair, the catalogue. Never free text, never a table of domain verbs of ours.
3. **Nothing it says executes anything on its own.** A confident verdict maps onto a path that already
   exists and is already gated (`action_mode_now`, `contract.guard`, the consent flow). Since V2-754 it
   may COMPLETE a turn — fire a declared action of an open card through that same gate — but only where
   the model left the turn empty or its own call could not resolve, and never over a valid call: the
   verdict completes the model, it does not overrule it (`direct_action.complete`). Measured reason: in
   one session each reader was right exactly where the other was wrong.
4. **Every call leaves one event, and every READ leaves one too** — with `call_id`, the turn, and
   whether the verdict was used or why it was not.
5. **`ZAELAR_JEV=0`** — and a missing key, an open breaker, a slow or unsure call — is the engine
   exactly as it was before any of this.
6. **Nobody waits.** Readers `peek`, never `wait`. 56 of 87 real directed turns die to barge-in
   before they finish, so a reader that blocked would be paying for turns that no longer exist.
7. **No router in front of it and no reasoner deciding whether to ask it.** Methods are exposed from
   evidence and capabilities, the decision model ranks them, the existing gate validates the effect.

## Bounds

`MAX_QUESTIONS` (120) and `MAX_STATE_CHARS` (60 000) are checked where the only wire call lives, and
a caller past them gets an error rather than a silently truncated verdict set. Background callers
share a small semaphore; the voice brief does not take it, because making the hot path queue behind
a worker's sweep is the one way this module could make a turn slower. A worker's deadline is clamped
by us: it has no latency budget of its own but it does have a Bash timeout.

A circuit breaker opens after three consecutive failures for a minute — a provider outage used to
cost a thread and a full timeout on every turn, forever, for a verdict that was never coming.

## How it is tested

| Class | Fakes | Answers |
|---|---|---|
| **wiring** | the transport | does the real door reach the wire? `calls == 1` |
| **parity** | the transport | are off / slow / unsure identical to no-model-at-all? |
| **efficiency** | nothing | trips per turn, bytes offered, zero blocking callers |
| **effectiveness** | nothing — the REAL API | accuracy, confidence, latency, and wrong-and-confident |

Only the last one spends money, and it is opt-in (`ZAELAR_JEV_BENCH=1`), never writes the operator's
timeline, and archives the criteria wording it measured — two runs are comparable only if they asked
the same question.

**The metric that governs is wrong-and-confident, not accuracy.** A verdict below the gate is
discarded and costs nothing; a WRONG verdict above it is acted on. «Ábreme el vídeo» once scored 0/8
at 0.52-0.61, and a bench counting hits would have reported 89% and hidden exactly that.

⚠️ **A test that builds the handle by hand proves the MAPPING, never the WIRING.** One integration
shipped in an initiative marked done and never made a single call in its life: its tests all
constructed the verdict themselves, and the one case that touched the real entry point asserted
`is None` — which is what the bug returned. The same `None` meant «switched off» and «broken».
