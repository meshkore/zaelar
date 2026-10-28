---
title: Principles
updated: 2026-10-23
status: stable
---

# The base of the whole system — mechanisms, not rules

The founding statement, in short:

> We need a system that is not *trained by rote* but intelligent — one that knows what to do. Nobody can spell
> out every case one by one; that would be a pile of if-elses. The engine is an intelligent system connected to
> language models that can understand tasks, process them and make its own decisions. What it needs is not only
> that freedom but the mechanisms to understand, execute and verify, so that any kind of task is feasible for the
> agent. When something is unclear it asks the user; when the user is not there it decides, and what the user
> says becomes dynamic rules that adapt to each operator. We are building a SYSTEM, not a band of predefined
> rules or preset rails. The only things with rails are the widgets.

This is not a preference about style. It is the criterion that decides whether a change belongs in this
engine at all, and it outranks the convenience of any individual fix.

## The line that actually works

«No rules» is not the rule — the destructive-action contract is a rule, and it is what keeps a bulk delete
from ever reaching the operator's real calendar. The distinction that survives contact with the code is
**what the rule is about**:

| | Rail on CONSEQUENCES — a MECHANISM, keep it | Rail on JUDGEMENT — a LIMIT, remove it |
|---|---|---|
| What it constrains | what may irreversibly happen; what a door accepts; what a mandate allows | what to say, when something counts as X, how to behave |
| Effect on the model | none — it reasons freely and the engine bounds the outcome | it stops reasoning and follows the script |
| Examples here | `party.py` offers **no tools** at all; `contract.guard` refuses a destructive action with an empty selector; `book.unbook` can only unwrite the row that errand wrote; a mandate's `may` list | «no discutas»; «acúsale recibo en una frase»; «si te pide X responde Y»; a verb table that decides intent |

`nucleo/errands/party.py` is the template and should be read before designing anything in this class: the
highest-consequence mouth in the engine writes to real people on the operator's real accounts, and it is
made safe **structurally** — the model returns ONE JSON object and the ENGINE executes what the mandate
allows, so a stranger's sentence cannot reach a tool because no tool is offered. Freedom of reasoning,
zero freedom of consequence. Every rail worth having has that shape.

## The three duties this puts on any change

1. **Declare capabilities, never script behaviour.** An undeclared capability is one the model narrates
   instead of using; a capability it is told it lacks is one it talks the operator out of. So say what it MAY
   do, once — and stop there. Watch for rails on judgement smuggled in as help: a sentence telling a model
   «don't argue» or «acknowledge in one sentence» inside a fix that is otherwise a mechanism.
2. **When it is not clear: ask. When nobody answers: decide, and remember what was decided.** `ask_operator`
   is the asking half. The remembering half — turning his answer into a durable policy that the NEXT
   decision of the same class consults — is the part that makes the system adapt per operator instead of
   per release. See the extension point below: without it, a stated preference either stays in one
   conversation or gets frozen into a prompt.
3. **Widgets are the only place rails belong.** A widget has a declared shape: its `manifest.json` actions
   ARE its skills, its `data.py` owns its data, its store is its state. System widgets ship that shape
   predetermined and the operator may change it. Nothing else in the engine gets to be a rail — not the
   router, not the prompts, not the playbooks.

## Extension point: a per-operator policy store

The engine can ask (`ask_operator`, the confirm gates) and can remember facts (`memory/`, pills). The design
leaves room for the piece that joins them: a **per-operator policy store** that takes an answer the operator
gave to a question the system asked and makes it the default the same class of decision reads next time. It is
the natural next step of the philosophy above, and the right home for preferences that would otherwise be
turned into constants in prompts and code.

## Any user, any request, any language — the engine is generic, the personalisation sits beside it

> Multiple users will make multiple requests in multiple languages. The system must absorb any case; we never
> channel one in particular. (Operator, 2026-10-28.)

What this forbids and what it asks for, for any change that touches how a request is understood or carried out:

1. **No patch for the case in front of you.** A fix is only accepted when it is the mechanism for the whole CLASS
   of that case — change the widget, the wording, the language, the city: it must still hold. A rail is allowed
   only when it is **generic for a kind of act** (a canvas gesture, a data-op on any card, a stop, a confirmation)
   and helps cases nobody has written yet; never for one phrase, one widget or one user.
2. **The engine never knows the user; the adaptive layers do.** Everything that depends on WHO is speaking and HOW
   lives in data the engine reads, never in constants: the widget and action **aliases** (`widgets/registry`,
   the manifests), the **rules table** (`rules/`, scoped global → domain → widget → item), **memory** (his tastes,
   his places, his contacts) and the **per-operator policy store** above. «Find me a restaurant» searches his city
   because memory says where he is, not because the code names a city. A threshold or a window that turns out to
   depend on the speaker is a candidate for that layer, not for a constant — until then it is ONE value for
   everyone, with its reason written next to it.
3. **Thresholds, windows and vocabularies are mechanisms, not tunings.** When a verdict floor or a recency window
   decides a case, the change is to the RULE that reads it (which readers vote, in which order, what evidence
   outvotes what), stated once and tested with variants — not a number nudged until today's turn passes.
4. **Never bound future scalability to make today work.** A widget that only answers in one language, a door that
   lists the cards it knows, a verb table that routes: each of these works today and closes a door tomorrow. The
   question before merging is the one the Brain Worker doctrine asks: *does it work for a task nobody has
   written yet?*

## Fix the class, never the case

> No fixes whose purpose is to make individual tests pass. Improvements happen at the structural level, they fix
> the system, and the tests pass as a result. This is a global product that must be able to serve any request.

The tests and the judge are a SAMPLE of the requests the product will meet. Green on the sample is the
consequence of a sound system, never the target. So:

1. **Name the class before touching code.** «The sheet rejects LG rows» is a case; «the sheet's subject is read
   from capital letters» is the class. If you cannot name the class, you have not found the cause yet.
2. **Reach for structure in this order:** a verdict the turn already pays (Jev, the brief) → a datum someone
   declares (a manifest action, the research brief, the connector catalogue) → one door / one reader that every
   route crosses → and only then language data, in `i18n/`, for every language at once.
3. **The test proves the class, not the case:** it carries at least one variant the failing case did not — the
   other language, a reworded request, another domain, an input shape nobody recorded.
4. **Forbidden, whatever the deadline:** a regex or word list added so one case passes; a case id or a fixture's
   string in product code; weakening or rewriting an assertion to go green (an assertion changes only when the
   behaviour changed on purpose, and the commit says so); raising any ratchet ceiling.
5. **When the structural fix does not fit the batch,** the test stays red (or `xfail` with the class as its
   reason) and the class is recorded as open work. An honest red beats a patched green: a patched green hides the
   class from the next person and from the judge.

Enforced, not just written: `tests/infrastructure/unit/test_words_never_fix_a_case.py` (node 7.73) — the count
of `re.compile` calls and module-level word tables in product code may only fall.

## How to tell you are violating this

Before writing the change, ask the two questions the Brain Worker doctrine already asks
(`.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`), then a third:

- Change one word of the request — hotel→restaurante, Sevilla→Los Ángeles — **does it still stand?**
- Does it work for a task nobody has written yet?
- **Is what I am adding a sentence about how to behave?** If yes, it is a rail on judgement. Delete it and
  find the mechanism it was standing in for.
- **Would this change exist if that one test did not?** If no, it is a patch for the test.
