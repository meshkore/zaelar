"""nucleo/request/answered_task.py — an answered question about an act that LEAVES is an identified task (V2-851 §2b, F2e).

Measured after F2d: the answer resumed its request by running ONE new Flash text turn «request — answer» on the row,
and in 6 of 14 of those turns the model said «sending it now» and called nothing — the row stayed running until a
sweep failed it. §2b: Flash decides, asks until the task is clear, and only an IDENTIFIED task goes to a worker,
with its playbook and what it needs; latency of 15 s or more is accepted, speed is never bought with a shortcut.

So the answer no longer re-runs a model turn. It starts a Brain Worker through the one errand portal
(`acts/errand.escalate_to_slowbrain`) ON THE SAME ROW (`task_uid`: the row becomes the worker's, no new row), with:

  · the brief — his request, his answer, the candidate the binding verdict chose (`<ask_id>#<n>`), said as one line;
  · the playbook `message` (on the row's `playbook` column and in the escalation's context);
  · `done_when` — the world's echo of the leaving act, rendered from the card's own declared templates over the
    person he chose (`spec.render`). With nobody chosen there is nothing exact to render, and the errand's birth
    asks for its end state once, as every errand without one (`spec.born`).

The worker acts through the bridge's message door, asks `verify`, and `circuit.settle` closes the row on the echo —
the worker never closes. One answer starts at most one worker (`inline_ask.take`, the once-per-`ask_id` lock).

What stays deterministic stays deterministic: a door's kept act whose answer is a plain pick among its declared
candidates (or a yes to its consent) re-runs through the same door with no model at all (`inline_ask.rerun`).
"""
from __future__ import annotations

import json

from nucleo.request import acts_of, base, note

#: The playbook an answered leaving act follows (V2-851 §6; the composer is `nucleo/workers/prompts/playbook.py`).
PLAYBOOK = "message"


def deterministic(entry: dict, choice: int | None) -> bool:
    """Can the kept act re-run with his answer and no model? A yes to its consent, or a pick among the candidates
    the door itself declared — anything else (a fact to compose, a free answer) needs the worker."""
    retained = entry.get("retained") or {}
    if retained.get("kind") == "utterance":
        return False                                  # our own question kept no act: there is nothing to re-run
    if str(entry.get("consent") or "") == "ask_consent":
        return True
    cands = list(retained.get("candidates") or [])
    return choice is not None and 0 <= int(choice) < len(cands)


def start(uid: str, entry: dict, text: str, choice: int | None = None) -> int:
    """Hand row `uid`, whose leaving act waited on his answer, to a Brain Worker on that same row. The worker's task
    id, or 0 when nothing started (this answer already took its act, or the portal refused it)."""
    from nucleo.circuit import ledger
    from nucleo.request import inline_ask
    retained = entry.get("retained") or {}
    ask_id = str(entry.get("ask_id") or entry.get("corr_id") or "")
    row = ledger.get(uid) or {}
    request = " ".join(str(retained.get("text") or row.get("goal") or row.get("title") or "").split())
    cands = list(retained.get("candidates") or [])
    who = str(cands[int(choice)]) if choice is not None and 0 <= int(choice) < len(cands) else ""
    answer = " ".join(str(who or text or "").split())
    said = f"{request} — {answer}" if request and answer else ""      # his request said again with his answer
    if not (uid and said) or not inline_ask.take(ask_id):
        return 0
    from nucleo import his_words
    his_words.note(who or text)               # the candidate he picked (screen or voice) is HIS naming of that person
    ledger.resumed(uid)
    inline_ask.resuming(uid, retained)        # the same act called elsewhere meanwhile is this answer's: never twice
    # `done_when`: the leaving act's end state for `who` — every declared template of the kept act(s) that renders over
    # the kept payload with `who` in the person's slot, as ONE `any`. Nothing when nothing renders (nobody chosen: no
    # guess).
    clauses, seen = [], set()
    if who:
        from nucleo.acts import message
        from nucleo.circuit import spec, verify
        from widgets import effects
        wid = str(retained.get("widget") or "")
        slot = str(retained.get("slot") or "")
        payload = dict(retained.get("payload") or {})
        for k in ((slot,) if slot else message.RECIPIENT_KEYS):
            payload[k] = who
        for act in acts_of(retained):
            if not effects.leaves(base(wid), act):
                continue
            try:
                mode, got = verify._clauses(spec.render(wid, act, payload) or {})
            except Exception as e:  # noqa: BLE001
                note(e)
                continue
            if mode == "all" and len(got) > 1:
                continue                              # a conjunction cannot be one branch of an `any`
            for c in got:
                key = json.dumps(c, sort_keys=True, default=str)
                if key not in seen:
                    seen.add(key)
                    clauses.append(c)
    dw = {"any": clauses} if clauses else {}
    try:
        ledger.store().task_patch(uid, playbook=PLAYBOOK)
    except Exception as e:  # noqa: BLE001
        note(e)
    ctx = {"src": "answer", "kind": "generic", "task_uid": uid, "answers": ask_id, "playbook": PLAYBOOK,
           "surface": "voz", "origin": str(row.get("origin") or "voz"), "heard": " ".join(str(text or "").split()),
           **({"trace": str(row["trace_id"])} if row.get("trace_id") else {}),
           **({"done_when": dw} if dw else {}),
           **({"chosen": f"{ask_id}#{int(choice)}"} if who else {})}
    from nucleo.acts.errand import escalate_to_slowbrain
    tid = int(escalate_to_slowbrain(said, context=ctx) or 0)
    try:
        from voice.observer import emit
        emit("brain", "↩ answer handed its task to a worker", text=said[:300], role="system",
             extra={"cat": "flash", "task_id": uid, "ask_id": ask_id, "worker": tid, "playbook": PLAYBOOK,
                    "done_when": bool(dw), **({"chosen": ctx["chosen"]} if who else {})})
    except Exception as e:  # noqa: BLE001
        note(e)
    if not tid:
        from nucleo import circuit
        circuit.settle(row=uid, state="failed", outcome="the answered task could not be started")
    return tid
