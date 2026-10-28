---
title: Zaelar — How a research task is DIRECTED (brief, funnel, composite proposals)
category: architecture
updated: 2026-10-23
owner: ricart
status: current
---

# Directing a research task

> NARRATIVE doc. It complements `zaelar-architecture.md` (which piece is what) by answering a different question:
> **if the operator asks for «the best holidays» and expects something a professional would sign off on, what has
> to happen between the sentence and the screen, in what order, and why in that order.**

## 0. Why the research layer exists

> «Opening a website, setting the filters, pressing the button and returning the first three results is
> something anyone can do.»

Driving a real browser, reading, extracting and verifying are resources the Brain Worker already has. What turns
them into research is **direction**: how wide to search and against which yardstick to judge. Without it, a
worker receiving free prose tends to settle for the minimum criterion that satisfies the literal sentence — a
shortcut such as «conclude with the 2-3 that fit best» is right for «get me the price of X» and wrong for «choose
the best».

Delivery needs its own shape too: a travel proposal **is not a list of hotels**. It is a package (this hotel +
that ferry + such a restaurant) that is compared and chosen as a whole. A flat results surface — 1 card = 1 thing
— can only hold a package dissolved in prose, which is exactly what prevents comparing it. So results can be
composite.

## 1. The three pieces

| Piece | File | What it solves |
|---|---|---|
| **Research director** | `nucleo/workers/brief.py` | Turns the raw request into a BRIEF: what disqualifies, what scores, what an expert would add, how wide to search, how quality is judged, what shape the delivery takes. |
| **Composite proposals + detail page** | `widgets/results/` | A result can be made of PIECES (`parts`), carry hard, queryable data (`facts`) and real photos (`images`); and the sheet has a DETAIL view of one item. |
| **The brain sees the screen** | `widgets/refs.py::prompt_digest` | Generic hook: a widget publishes a summary of its content and the FlashBrain carries it in the prompt → it can ANSWER about what is on screen, not just name it. |

## 2. The order, and why

```
operator's sentence
      │
      ▼
FlashBrain (nucleo/flash/) ── answers NOW («got it, starting the search») ── milliseconds, VOICE path
      │  escalate_to_slowbrain(request)
      ▼
ASYNC PRE-FLIGHT  ← here, and only here, there is time to THINK
  nucleo/dispatch/::_compose_brief
      │  · is it a research task? (the model decides, not a verb table)
      │  · was there a previous round with this goal? → expand() instead of recomposing
      ▼
  nucleo/workers/brief.py::compose  → structured BRIEF (30 s ceiling, fail-open)
      │  research.save(task_id)  +  research.remember_round(goal_key)
      ▼
worker prompt = literal request + BRIEF (to_prompt_block)
      │
      ▼
Brain Worker (Claude Code + real Chromium)
      │  funnel: gather ≥N → filter hard → score soft → VERIFY finalists
      │  hbnote plan/progress/phase   → the operator watches it advance
      │  hbnote considered N --kept M → the selection stays AUDITABLE
      │  widget_cli data results append → the sheet fills LIVE, proposal by proposal
      ▼
widgets/results  ── comparable list ──▶ (voice: «details of number 1») ──▶ full record
      │
      ▼
refs.prompt_digest → the FlashBrain knows what is on screen → answers «does it have wifi?» without searching again
```

**Why the brief is composed in the PRE-FLIGHT and not in the voice turn.** Separating hard from soft criteria,
deducing what will be needed but was not asked for, fixing the breadth and the yardstick is reasoning work. The
voice FlashBrain must answer in milliseconds: there is no room for it there. The escalation, on the other hand,
is already asynchronous and the operator knows it takes time — it is the one point in the system where there is
time to think before starting to work.

**Why the brief goes AFTER the literal request in the prompt.** It is the direction on *how* to do it well, and
it reads better once *what* is being asked is known. Without a brief (a concrete action: cancel an appointment)
the block does not appear and the worker runs exactly as it would otherwise.

## 3. The funnel — the piece that really changes the result

```
1) GATHER  ≥ min_candidates real candidates — BEFORE discarding any
2) FILTER  by the HARD criteria (failing one = out, no exceptions)
3) SCORE   the survivors with the SOFT criteria + the enrichments
4) VERIFY IN DEPTH only the finalists, against the YARDSTICK ← this is where the effort goes
5) DELIVER the n_final best, with their verified data
```

`min_candidates` has a **floor of 25** in code (`_MIN_CANDIDATES_FLOOR`). It exists because a model left to
choose the number tends to ask for «10 candidates» — a shallow search under another name. Choosing «the best»
among 8 is not choosing, it is settling. Models often ask for more on their own; the floor is there for when
they do not.

The **angles** matter as much as the number: through a single path (one aggregator) you always see the same
subset, so 40 candidates from a single source are 40 false candidates.

## 4. What «generic» means here, and why this is not a hotel finder

Nothing in `research.py` knows about hotels, ferries or prices. The composer asks: *what would an expert in THIS
domain add, how wide does the search need to be, how is quality judged?* — and that question has the same shape
for a quantum-physics thesis (how many papers before concluding? what makes a source solid?), for research to
write a book, or for choosing a library. **The brief itself names the domain**; the STRUCTURE of directing a
research task is the same. A test guards it: if the system prompt specialises in one domain, or the vocabulary
of a specific use case appears in it, the test fails.

The same holds on the screen side: `parts` are ROLES («Accommodation», «Transport», «Source», «Chapter»,
«Server»), not fields of a trip.

## 5. Rounds: «those won't do, keep looking»

The operator's second sentence **never mentions the first one**. That is why continuity is matched by GOAL
SIGNATURE (content-word overlap ≥0.5, the same threshold as web-task resumption), not by exact text or task id:

- `remember_round(goal_key, brief)` at launch → a bounded registry (40 live, 6 h TTL).
- `previous_round(goal_key)` when a new request arrives → if it matches, `expand()`: **round+1, breadth doubled,
  criteria intact**, and the reason for the rejection inside the brief.

Reopening the criteria would start ANOTHER search; doubling the breadth continues THIS one, so «search more»
never returns what the operator just rejected.

**Deliberate decision:** asking for the same thing twice within the TTL is treated as a continuation, not a new
search. Asking twice means the first answer did not serve.

## 6. Auditability: `considered`

`hbnote considered <N> --kept <M>` → `dispatch.session_considered` → `SessionRecord.considered/kept` →
`active_sessions()` / `pending_summaries()` → the FlashBrain prompt and `/api/tasks`.

Without this datum, «here are the 3 best» is **indistinguishable** from «here are the first 3», and neither the
operator nor the brain can judge whether to keep going. `-1` means NOT APPLICABLE (a task that is not research
has not «considered 0 candidates»).

## 7. What it does NOT do, on purpose

- **It commits to nothing.** The worker is forbidden to book, buy, pay, hire or send on the operator's behalf,
  even when it finds the perfect option: «search» must never turn into «find and BOOK» — irreversible money for a
  word nobody said. Double net: the director cannot add actions that were not requested, and the block the worker
  reads repeats it. (Third, pre-existing net: the confirm-gate for irreversible actions in `nucleo/danger.py`.)
- **It does not block on a minor datum.** If something is missing to be able to search, it ASSUMES a reasonable
  value and records it in `assumed` — and the worker must mention it on delivery. Filling a missing datum is fine;
  hiding that you filled it is not.
- **It does not claim what it did not verify.** A proposal with an unconfirmed datum that is FLAGGED is fine; one
  with an invented datum is not.

## 8. Kill switch and fail-open

`§research.enabled` (UI) + `ZAELAR_RESEARCH=0` (env), the same pattern as the Susurro. And fail-open **on every
path**: with no provider, on error, or past the 30 s ceiling, the worker runs WITHOUT a brief — but **with a
warning in the log**. A silent fail-open here would hide that every search had gone back to being shallow.

In the test session the kill switch is off (`conftest.py`): «find a flat» is a research task, so dispatch would
otherwise call the real model from tests that have nothing to do with research.

## 9. Implementation notes

- **Widgets update live independently of the voice session.** The event channel (`openSSE`) is opened by
  `main.js` at startup and lives as long as the application, so an open card keeps refreshing with the
  microphone off or the voice stopped (⏻). *Related trap:* with the LiveKit engine, `session-lk.js` is served AT
  the URL of `session.js` — editing `session.js` alone changes nothing at runtime (the test checks both files).
- **Provider errors are classified, not swallowed.** `_raise_with_body` is awaited in the provider call, so a
  429 is classified as a quota error and triggers the provider relay instead of surfacing later as a parse error.
- **Roles are short labels.** They are painted in a badge; the prompt asks for them short and a cap guarantees
  it, cutting at a WORD boundary (never mid-word).

## 10. References

- `nucleo/workers/brief.py` — the director (compose/parse/expand/to_prompt_block/rounds).
- `nucleo/dispatch/::_compose_brief`, `_build_prompt`, `_web_prompt`, `session_considered`.
- `widgets/results/{data,widget}.js|py` + `manifest.json` — composite schema, `facts`/`images`, `detail`/`list`.
- `widgets/refs.py::prompt_digest` + `widgets/brief.py` — the generic «what is on screen» hook.
- `config/v2.py §research` — model and kill switch.
- Tests: `tests/agent_headless/unit/test_research.py`, `tests/agent_headless/unit/test_dispatch.py`,
  `tests/browser/unit/widgets/test_results_presentation.py`,
  `tests/browser/unit/widgets/test_live_updates_independent_of_voice.py`.

## 11. Verifying end to end

The deterministic tests above cover the brief, the funnel parameters, rounds, `considered`, the kill switch and
fail-open; the browser tests cover the composite sheet, the detail view and live updates. The full chain — a
Brain Worker executing a brief against real websites and filling the sheet — is exercised by voice or chat from a
browser session, because the request is born in the agent process where the escalation listener runs. Milestones
to watch in the observability column: `task/plan` → `task/progress` → `widget/data` (the sheet filling) →
`task/considered`. The worker's bridges (`hbnote`, `widget_cli`) authenticate with a per-task token held in the
server's registry, so a worker must be launched by the server to report and paint.
