# An appointment somebody ELSE asked for — the proposal path

**Module:** `nucleo/errands/proposals.py` · **Surface:** the agenda widget's proposals band ·
**Related:** `zaelar-google-connector.md` (how the appointment is finally written), `zaelar-cluster-channel.md`
(where a peer's identity comes from, and what it is worth)

---

## What this is for

Most appointments arrive from Google Calendar, already made. This path is the other case: somebody *asks* for
one — through a messaging channel such as Telegram or WhatsApp — and the operator has to decide.

The spec in one sentence: the agent organizes the appointment with whoever asked, tells the operator «this
person asked for an appointment, we can do it on this day, everything is arranged», and once the operator
says yes the calendar entries are created and the requester is told it was accepted.

**Email is deliberately out of scope.** A Gmail invitation already lands in Google Calendar on its own, so
treating it as a proposal would produce the same appointment twice.

---

## How it hooks into the errand flow

An inbound message can already become a calendar entry: `nucleo/errands/wake.py` negotiates with the other
party and calls `nucleo/errands/book.py::book()`. The proposal path is the branch where the errand has no
mandate to schedule (`may_schedule()` is False): instead of silently returning, `book()` parks the agreed slot
as a proposal for the operator.

**Refusing to WRITE to his calendar is right. Refusing to ASK is not.** That `else` is the whole feature, and
it is why every messaging channel inherits the behaviour with no code of its own.

```
inbound message → errands/wake → party turn → decision{agreed}
                                                    │
                            may_schedule?  ── yes ──┴──→ book.book()  → calendar row
                                           ── no  ─────→ proposals.park()
                                                              │
                                              operator's YES  ├──→ book.book()  → calendar row
                                              operator's NO   └──→ errands.close(declined)
```

## Where a parked proposal lives, and why not in a table of its own

**On the errand row.** The errand is already durable, already expires, already appears on the operator's
board — and, the part that decides it, already holds the **binding to the conversation the proposal arrived
on**, which is the address the answer has to travel back to. A parallel store would have to re-derive all
four, and would be a second thing to keep in sync.

Mechanically: `state = "proposed"` and the slot under `done_when.proposal`. No schema migration — both are
existing columns.

⚠️ **A proposal blocks verification.** `verify.meeting_exists` returns False while `done_when.proposal` is
set, for the same reason `link_owed` does: nothing is in the calendar yet, so an unrelated meeting sharing
that window must not close the errand — and closing it would **release the conversation**, leaving the person
who asked with an answer nobody is going to send.

## The authorization criterion — and why «always manual» is not provisional

The obvious guard is that nobody can push an appointment into the operator's calendar without his
permission. An allowlist of authorized contacts looks like the answer, but **a list like that would be worse
than none**, and the reason is concrete rather than cautious:

- a cluster peer's `handle` is **self-declared**. `connectors/meshkore/security.py::neutralize_identity`
  sanitizes the string; it does not prove it. A cryptographic identity exists only for **us**
  (`connectors/meshkore/identity.py::did_key`).
- the allowlist that does exist is **per cluster, not per person** (`connectors/meshkore/store.get_perms`),
  and `perms.escalate_context` hardcodes `"trusted": False` — a cluster escalation never inherits operator
  trust.

So an allowlist keyed on a name anybody can claim would *look* like a control while being none. Therefore:

1. **the name of whoever proposed is a LABEL SHOWN TO THE OPERATOR, never an authorization;**
2. **every proposal needs his explicit yes** — acceptance is always manual;
3. **his yes IS the grant.** `proposals.accept()` adds `schedule` to the errand's own mandate and then calls
   `book.book()` unchanged — nothing here re-implements booking, so the path that writes a calendar row stays
   the single one that has always written it;
4. **text that came from outside stays DATA.** It keeps passing through `security.fence_untrusted`; nothing
   in this path interprets a proposal as an instruction.

The design leaves a seam for auto-accept, to be used only once a peer identity is something that can be
verified cryptographically.

## How the operator hears about it, and answers

- **Notice:** a task matter on the errand's row (`nucleo/events/task_event.told(…, ask=True)`): the row waits for his
  answer with the question, and the out-of-turn mouth says it once with the task's identity. It names who, when, what for — and says outright that **it is not in the calendar
  yet**, which is the claim that would otherwise be made by omission.
- **Card:** the agenda paints a proposals band above the calendar, deliberately **not** styled like an
  appointment — a row that looks like an entry is already making the claim. Two buttons, «Aceptar» and
  «Rechazar». The answer is a plain yes or no; there is no «propose another time».
- **Voice:** the declared actions `accept_proposal` / `decline_proposal` (`widgets/agenda/manifest.json`),
  so «acepta esa cita» works. `errand_id` is optional — with one proposal pending, there is nothing to
  disambiguate.

## Extension points

- **Proposals from a cluster peer.** `connectors/meshkore/bridge.py::_CLUSTER_TURN_ALLOWED` admits
  `cluster.send` / `cluster.done` / `cluster.pact`; a `cluster.propose` verb would let a peer-originated turn
  reach this path, gated by its own per-cluster permission in `store.set_perms`.
- **Telling the requester.** Accepting releases the errand to carry on, and the errand answers through the
  thread it is bound to; nothing is sent from `proposals.py` itself.

## Tests

- `tests/agent_headless/unit/test_a_proposal_waits_for_the_operators_yes.py` — testmap node **3.50**
- `tests/browser/unit/agenda/test_an_appointment_says_who_convened_it.py` — testmap node **4.175** (the band,
  rendered)
