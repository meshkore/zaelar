# The decision model — one bounded-choice primitive, and where it may sit

> **What this is.** A small, non-generative model (TypeSafe System One, «Jev») that answers ENUMERATED
> questions with a calibrated confidence. It picks among options it is handed. It writes no text, it
> knows nothing it was not given, and nothing it answers executes anything.
>
> **Where the detail lives.** `nucleo/jev.py` (the only module that talks to it) and
> `nucleo/turn/brief.py` (the turn's questions). This document is the ANATOMY: the contract,
> who may call it, from where, and the rules that do not move.

## Why it exists

Some decisions in a turn are genuinely hard for a small fast model and trivial for a specialist:
*is this an errand worth a Brain Worker, or chatter? does this sentence license opening a card? with
three cards open, which one is «close that» about?* Those are **bounded choices**: the options exist,
they are declared, and what is needed is a pick among them — not prose, not a plan.

Paying a reasoning round trip for a bounded choice is the waste this exists to remove. Paying a
classifier round trip for something a local lookup answers in milliseconds is the waste it could
CREATE, which is why placement is half of this document.

## THE RULE OF PLACEMENT

> **It serves what is decided AFTER the model. What is decided before it is not its business.**

Anchors of a turn, in the order they happen from the turn's admission:

1. the prompt is assembled (a local step, milliseconds);
2. the tool catalogue is settled;
3. **a verdict lands**;
4. the model's first token arrives;
5. the reply is complete.

A brief fired when the turn is admitted reaches a POST-model reader with time to spare, and can never
reach a PRE-model one without making the model wait. That is not a tuning parameter: it is the reason
«put the classifier in front of the model» is the opposite design, not a smaller one.

**And the cost is the ROUND TRIP, not the questions**: one question, several heterogeneous ones, or a
hundred candidates cost about the same single trip. Everything a turn needs therefore goes in ONE call.

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

If all of them collapsed into `[]`, a shortlist nobody had looked at would be indistinguishable from
one the chooser had narrowed.

## Who may call it, and from where

| Caller | Door | Note |
|---|---|---|
| the voice turn | `turn_brief.ask_for_turn` at the ADMITTED sentence | one brief per turn; readers `peek` |
| the cover phrase | the same brief (`request_type`) | no second socket for the same words |
| memory / task recall | `select_many_status` | narrows with a lexical index FIRST |
| a Brain Worker | `worker_bridge decide @file.json` → `/api/worker/act` | ONE allowed action, behind the task token |
| the probe / text channel | `choose_sync`, `classify_sync` | blocking, and has no event loop to freeze |

A worker is a subprocess: it reaches the engine only through that endpoint, which already carries
the authentication, the policy and the piggyback. The payload goes by FILE, like every other payload
on that bridge — the engine's own permission gate rejects an argument containing braces and quotes.

## The turn's brief

One call, fired at the admitted sentence, carrying every question read after the model:

| Key | Question |
|---|---|
| `canvas` | show / close / neither — a backstop for a tag the grammar missed |
| `request_type` | what KIND of turn, which picks the cover phrase's pool |
| `escalate_or_inline` | does this need a background worker? |
| `screen_action` | which declared action of which OPEN CARD, keyed by instance |
| `catalog_widget` | (when nothing is open) which widget of the catalogue is NAMED |

The last two are never asked together: with cards open, the ACTION is what disambiguates far more
sharply than «which widget» over descriptions. The widget falls out of the action.

**The criteria text is the product surface of these decisions.** Targeting built from «Name» + aliases
+ the widget's `desc` is clearly sharper than from the `desc` alone. The words a widget answers to are
the widget's own declaration, not a table in the engine.

⚠️ **Only the part of a declaration that ARRIVES can decide anything.** `screen_action` truncates each
action's `desc` at `turn_brief.MAX_DESC_CHARS` (200). A description written past that bound reaches the
question beheaded, with nothing saying so — and the clause that gets cut is usually the one that made
the action routable (for example the clause that lets «vuelve al catálogo» reach `youtube:show_tab`).
Raising the bound does not end the class: a declaration has to FIT the channel that decides with it.
A ratchet (node 2.74) keeps the number of over-length descriptions from growing. **When an action is
never chosen, read what the question actually said about it before blaming the model.**

⚠️ **Touching one description changes its NEIGHBOURS, so measure the neighbourhood.** Fattening the
winner of one phrase can starve the action next to it: adding «para el vídeo de verdad» to `close` can
stop «Vale, para el vídeo» from being a pause; adding «vuelve al inicio del vídeo» to `restart` can turn
«inicio del widget de vídeo» into a rewind. The minimum measurement is every phrase belonging to the
actions that share vocabulary, before and after — never only the phrase being chased. And a HOMOGRAPH
is closed by NAMING it, not by listing more synonyms: «para» is also a preposition, so «Vale, para el
vídeo.» can read as «OK, for the video.» — a description that says «here «para» is the verb, not the
preposition» resolves it within the same 200 characters.

⚠️ **An UNSURE answer has no opinion; an ABSENT one still fails closed.** The gate that lets the verdict
complete an empty turn must not read «unsure» the same as «no answer»: otherwise a torn reader (say,
`request_type` split between answer and comment) vetoes a near-certain one (`screen_action =
youtube:pause` with high confidence), and an order like «Para el vídeo» goes unexecuted.

So it is a REFUSAL list (`direct_action.NOT_AIMED_AT_THE_SCREEN`), and the reason is that the SCREEN
question already answers `none` with high confidence for ambient remarks, so the two guards agree exactly
where it matters:

    «¿el siguiente es de la NASA?»   question  · screen_action none
    «ese vídeo es antiguo»           comment   · screen_action none
    «hoy juega el Barça»             comment   · screen_action none
    «Bórrame los tres últimos…»      order     · screen_action remove

⚠️ **A POLITE ORDER is shaped like a question, so `question` cannot be on that list.** «¿Puedes
enseñarme el catálogo?» is `request_type = question` and `screen_action = youtube:show_tab`; in Spanish
that IS how orders are given. Every GENUINE question answers `none` on the screen question, so a
`question` entry could never save a turn — while `complete` only fires where the screen question is
CONFIDENT about a concrete action, which is exactly where such an entry would do damage. A weaker reader
must never veto a stronger one.

    «¿Puedes, por favor, reproducir el vídeo número dos?»  play_result   ← an order
    «¿Me pones el siguiente?»                              next          ← an order
    «¿Puedes parar el vídeo?»                              pause         ← an order
    «¿el siguiente es de la NASA?»                         none
    «¿cuántos vídeos hay en la cola?»                      none
    «¿de qué año es este documental?»                      none
    «¿quién sale en el vídeo?»                             none
    «¿tú crees que llegaron a la luna de verdad?»          none

**The standing test for any entry on that list**: name a turn it would SAVE that the screen question
does not already answer `none`. If there is none, the entry can only ever be wrong.

⚠️ **A text guard may compose with the verdict, never contradict it.** `direct_action.
a_fragment_moves_nothing` is the shape that is allowed: it refuses a turn that is ONLY A NUMBER
(«sesenta y nueve.», the tail of a sentence the acoustic layer closed early, which would otherwise be
executed as `set_volume 69`) — but only when the verdict ANSWERED and named nothing, and only reusing
`escalation_guard.is_a_fragment` rather than a reader of its own. Absent, failed or disabled brief →
it stands down entirely. Its narrowing to numbers is deliberate: without it the guard would reach
«páusalo» and «páralo», which `too_thin_to_commission` also calls fragments (its `_ALSO_A_VERB` hatch
matches «para» and the enclitic is a different token), and those are among the commonest orders.

⚠️ **Measure against the candidate set of the turn you are repairing.** The screen question is
enumerated PER CALL from what was open and possible at that moment, so a set borrowed from another
session is a different question. «Bórrame los tres últimos de la cola» against a set without `remove`
(an empty queue, so `_possible_now` dropped it) picks `clear_list`; against the set of the actual turn
it picks `remove`. The candidate list is in the `probabilities` of that turn's brief event — take it
from there, never from a neighbouring session.

## The rules that do not move

1. **`nucleo/jev.py` is the only module that talks to it.** One endpoint, one key, one timeout.
2. **Every answer is enumerated per call from DECLARED capabilities** — manifest actions of what is
   open, the escalate pair, the catalogue. Never free text, never a table of domain verbs of ours.
3. **Nothing it says executes anything on its own.** A confident verdict maps onto a path that already
   exists and is already gated (`action_mode_now`, `contract.guard`, the consent flow). It may COMPLETE
   a turn — fire a declared action of an open card through that same gate — but only where the model
   left the turn empty or its own call could not resolve, and never over a valid call: the verdict
   completes the model, it does not overrule it (`direct_action.complete`). The two readers are right in
   different places, so each fills the other's gaps.
4. **Every call leaves one event, and every READ leaves one too** — with `call_id`, the turn, and
   whether the verdict was used or why it was not.
5. **`ZAELAR_JEV=0`** — and a missing key, an open breaker, a slow or unsure call — is the engine
   exactly as it is without the decision model.
6. **Nobody waits.** Readers `peek`, never `wait`. Many directed turns end in barge-in before they
   finish, so a reader that blocked would be paying for turns that no longer exist.
7. **No router in front of it and no reasoner deciding whether to ask it.** Methods are exposed from
   evidence and capabilities, the decision model ranks them, the existing gate validates the effect.

## Bounds

`MAX_QUESTIONS` (120) and `MAX_STATE_CHARS` (60 000) are checked where the only wire call lives, and
a caller past them gets an error rather than a silently truncated verdict set. Background callers
share a small semaphore; the voice brief does not take it, because making the hot path queue behind
a worker's sweep is the one way this module could make a turn slower. A worker's deadline is clamped
by us: it has no latency budget of its own but it does have a Bash timeout.

A circuit breaker opens after three consecutive failures for a minute, so a provider outage costs
nothing per turn instead of a thread and a full timeout for a verdict that is not coming.

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
discarded and costs nothing; a WRONG verdict above it is acted on. A bench that only counts hits can
report a high accuracy while hiding a phrase that is consistently missed at middling confidence.

⚠️ **A test that builds the handle by hand proves the MAPPING, never the WIRING.** If every test
constructs the verdict itself, nothing proves the real entry point ever makes a call — and a `None` that
means both «switched off» and «broken» lets a broken integration pass. The wiring class above
(`calls == 1` through the real door) exists for exactly that reason.
