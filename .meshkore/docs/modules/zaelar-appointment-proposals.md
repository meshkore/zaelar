# An appointment somebody ELSE asked for — the proposal path (V2-697)

**Module:** `nucleo/errands/proposals.py` · **Surface:** the agenda widget's proposals band ·
**Related:** `zaelar-google-connector.md` (how the appointment is finally written), `zaelar-cluster-channel.md`
(where a peer's identity comes from, and what it is worth)

---

## What this is for

Most appointments arrive from Google Calendar, already made. This path is the other case: somebody *asks* for
one — through Telegram or WhatsApp today, through another agent on the MeshKore cluster soon — and the
operator has to decide.

His framing, which is also the spec:

> «cuando llegue una propuesta a través del cluster o de un mensaje o de donde sea se le puede comentar al
> operador en plan: tal persona nos ha pedido una cita, le hemos dicho que puede ser tal día, lo hemos
> organizado todo; y cuando esté todo, el operador simplemente confirmará que sí y se crearán esas entradas
> en los calendarios y se le confirmará al iniciador que todo eso ha sido aceptado.»

**Email is deliberately out of scope.** A Gmail invitation already lands in Google Calendar on its own, so
treating it as a proposal would produce the same appointment twice.

---

## The one-line change that made it work

An inbound message *already* became a calendar entry before this: `nucleo/errands/wake.py` negotiates with the
other party and calls `nucleo/errands/book.py::book()`. What was missing was the branch where the errand has
no mandate to schedule — `may_schedule()` returned False and `book()` **returned**. The other person had said
yes, the engine held the slot, and nobody was told.

**Refusing to WRITE to his calendar is right. Refusing to ASK is not.** That `else` is the whole feature, and
it is why Telegram and WhatsApp inherit the behaviour with no code of their own.

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

The operator asked for the obvious guard: *«obviamente tienen que tener permiso del operador, cualquiera no
nos puede enchufar una cita a través del cluster»*, and floated an allowlist of authorized contacts. **A list
like that would be worse than none today**, and the reason is measurable rather than cautious:

- a cluster peer's `handle` is **self-declared**. `connectors/meshkore/security.py::neutralize_identity`
  sanitizes the string; it does not prove it. A cryptographic identity exists only for **us**
  (`connectors/meshkore/identity.py::did_key`).
- the allowlist that does exist is **per cluster, not per person** (`connectors/meshkore/store.get_perms`),
  and `perms.escalate_context` hardcodes `"trusted": False` — a cluster escalation never inherits operator
  trust.

So an allowlist keyed on a name anybody can claim would *look* like a control while being none. Therefore:

1. **the name of whoever proposed is a LABEL SHOWN TO THE OPERATOR, never an authorization;**
2. **every proposal needs his explicit yes** — his own scoping: «de momento podemos dejar que el sistema
   siempre necesite aceptaciones manuales»;
3. **his yes IS the grant.** `proposals.accept()` adds `schedule` to the errand's own mandate and then calls
   `book.book()` unchanged — nothing here re-implements booking, so the path that writes a calendar row stays
   the single one that has always written it;
4. **text that came from outside stays DATA.** It keeps passing through `security.fence_untrusted`; nothing
   in this path interprets a proposal as an instruction.

The seam for auto-accept is left; the auto-accept is **not built**. It should not be until a peer identity is
something we can verify.

## How the operator hears about it, and answers

- **Notice:** one `[SISTEMA]` note through `voice/brain_notes.push`, keyed `proposal:<errand_id>` so it can be
  retracted once answered. It names who, when, what for — and says outright that **it is not in the calendar
  yet**, which is the claim that would otherwise be made by omission.
- **Card:** the agenda paints a proposals band above the calendar, deliberately **not** styled like an
  appointment — a row that looks like an entry is already making the claim. Two buttons, «Aceptar» and
  «Rechazar». There is **no «propose another time»**, by his own scoping: *«yo por ahora no haría la
  funcionalidad de proponer otra hora, pero sí diría si sí o si no.»*
- **Voice:** the declared actions `accept_proposal` / `decline_proposal` (`widgets/agenda/manifest.json`),
  so «acepta esa cita» works. `errand_id` is optional — with one proposal pending, there is nothing to
  disambiguate.

## What is NOT built

- **`cluster.propose`.** `connectors/meshkore/bridge.py::_CLUSTER_TURN_ALLOWED` still admits only
  `cluster.send` / `cluster.done` / `cluster.pact`, so a peer-originated turn has no verb that reaches this
  path. Adding it needs its own per-cluster permission in `store.set_perms`. Until then the proposal path is
  reachable from messaging only.
- **Telling the requester.** Accepting releases the errand to carry on and the errand answers through the
  thread it is bound to; nothing is sent from `proposals.py` itself.
- **Live verification.** No real proposal has travelled this path end to end yet.

## Tests

- `tests/agent_headless/unit/test_a_proposal_waits_for_the_operators_yes.py` — testmap node **3.50**
- `tests/browser/unit/agenda/test_an_appointment_says_who_convened_it.py` — testmap node **4.175** (the band,
  rendered)
