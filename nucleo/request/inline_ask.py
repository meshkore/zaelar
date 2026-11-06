"""nucleo/request/inline_ask.py — an inline act a door answered with a consent ASK makes ITS row wait (V2-851 §3/§3a).

Before: «send a message to Raquel» with two Raquels ran inline in the turn, the door refused with its question, the
turn's mouth said it — and the row ended `failed`. Nothing durable was asked, no `ask_id` could be answered by screen,
and his next words only worked if the model happened to call the door again.

Now a refusal that IS a consent ASK — the door names the candidates (`candidates` + the payload `slot` they fill:
ASK_WHICH) or the facts it lacks (`needs`: ASK_FACT), or says `consent: ask_consent` — goes through THE asker
(`nucleo/circuit/asker`) exactly as a worker's question does: the row waits for his answer with its `ask_id`, the act
is retained on the row's `ask` artefact ({widget, action, payload, slot, candidates}), and the `ask` event puts the
question on screen. The row is never settled `failed` for it.

The answer (screen route, or the brief's binding verdict on a later turn) resumes THAT row: when it is a plain pick
among the door's declared candidates (or a yes to its consent) the retained act re-runs through the same door with the
answer bound into its slot (`rerun`) — never a new row, never a model run. An answer about an act that LEAVES which
needs composing goes to a Brain Worker on the same row instead (`nucleo/request/answered_task`, V2-851 F2e). Which
candidate he named is the binding verdict's choice over the declared candidates (`worker_api_bind`); his words are
never matched here. The door's echo then settles the row through `circuit.settle`, as any inline act's.
"""
from __future__ import annotations

import threading
import time

from nucleo.request import acts_of, base, note

#: How long a re-run's slot value is remembered, so the same act the model ALSO calls on the answer turn is not sent
#: twice (the answer already sent it). Not a matcher: the key is the declared slot value, exact.
RECENT_S = 120.0
_RECENT: dict = {}
#: The questions an act already TOOK: one answer runs its act once, whoever triggers it (the model re-calling the act,
#: the binding verdict's re-run, a screen answer). Identity = the `ask_id`; checked and set under one lock, so two
#: triggers racing on the same answer cannot both pass (measured: a model call whose slot arrived under a synonym key
#: ran on a NEW row, then the verdict re-ran the retained act — two sends to the same person 12 ms apart).
_TAKEN: dict = {}
_LOCK = threading.Lock()
#: Rows an answer is resuming (`answered_task.start`): {row: (widget, actions, candidates, at)}. The
#: answering turn's model calling the same act is that same answer — never a second send.
_RESUMING: dict = {}


def verdict_of(res) -> dict | None:
    """The consent ASK a door's refusal carries, or None when it is a plain refusal. The door measured the candidates
    and the missing facts; the ONE rule (`consent.decide`) says which question that is."""
    from nucleo import consent
    if not isinstance(res, dict) or res.get("ok") is not False:
        return None
    cands = [str(c) for c in (res.get("candidates") or []) if str(c or "").strip()]
    needs = [str(n) for n in (res.get("needs") or []) if str(n or "").strip()]
    v = str(res.get("consent") or "")
    if not v:
        if not (cands or needs):
            return None
        v = consent.decide(level="routine", missing=needs, candidates=cands, licensed=True)["verdict"]
    if v not in (consent.ASK_FACT, consent.ASK_WHICH, consent.ASK_CONSENT):
        return None
    slot = str(res.get("slot") or (needs[0] if needs else ""))
    if v != consent.ASK_CONSENT and not slot:
        return None                          # an answer with nowhere to go cannot resume the act
    return {"verdict": v, "slot": slot, "candidates": cands if v == consent.ASK_WHICH else []}


def held(row: str, wid: str, action: str, payload: dict | None, res, *, question: str = "", options=None) -> str:
    """The door asked: row `row` waits on its question. Returns the `ask_id`, or "" when the refusal is no ASK."""
    v = verdict_of(res)
    if not row or v is None:
        return ""
    try:
        from nucleo.circuit import asker, ledger
        from nucleo.flash import refusal_line
        from nucleo.runtime_ids import next_seq
        from observability import identity
        ask_id = f"{row}-q{next_seq('inline.ask')}"
        session = identity.session_id()          # the conversation that asked: its answer resumes this row
        q = (question or refusal_line.speakable(base(wid), res) or str(res.get("message") or "")).strip()
        entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": row, "task_id": "", "inline": True, "action": action,
                 "question": q, "answer": "", "result": None, "session": session,
                 "consent": v["verdict"], "candidates": list(options or v["candidates"]),
                 "options": list(options or v["candidates"]),
                 "said": True,                   # the turn's own mouth said it: the pulse never relays it again
                 "retained": {"widget": wid, "action": action, "payload": dict(payload or {}), "slot": v["slot"],
                              "candidates": v["candidates"]}}
        ledger.store().task_patch(row, session_id=session)
        return asker.ask(row, entry)
    except Exception as e:  # noqa: BLE001 — a question that could not be made durable leaves the refusal as it was
        note(e)
        return ""


def take(ask_id: str) -> bool:
    """True exactly once per `ask_id`: the one act of that answer may leave. False for every later trigger."""
    if not ask_id:
        return True
    now = time.time()
    with _LOCK:
        for k in [k for k, t in _TAKEN.items() if now - t > RECENT_S * 10]:
            _TAKEN.pop(k, None)
        if ask_id in _TAKEN:
            return False
        _TAKEN[ask_id] = now
        return True


def reached(wid: str, action: str, res, uid: str) -> None:
    """Record whom the door's act reached, so a waiting row's re-run bound to that same declared candidate within
    `RECENT_S` is the same act, never a second one (exact identity of the door's resolution, never a match of words)."""
    # Who an act that left actually reached, as the door resolved it (`result.to` / `to`): none when it did not leave.
    if not isinstance(res, dict) or res.get("ok") is not True or res.get("already"):
        return
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    who = " ".join(str(inner.get("to") or res.get("to") or "").split())
    if who:
        _remember(wid, action, "\x00reached", who, uid)


def _remember(wid: str, action: str, slot: str, value: str, uid: str) -> None:
    now = time.time()
    for k in [k for k, (_u, t) in _RECENT.items() if now - t > RECENT_S]:
        _RECENT.pop(k, None)
    _RECENT[(base(wid), action, slot, " ".join(str(value or "").split()).casefold())] = (uid, now)


def _recent(wid: str, action: str, payload: dict | None, slot: str = "") -> str:
    """The row whose act already carried this exact slot value — or, for `slot`, already REACHED that value."""
    now = time.time()
    for (w, a, key, value), (uid, t) in list(_RECENT.items()):
        if (w, a) != (base(wid), action) or now - t > RECENT_S or not value:
            continue
        want = " ".join(str((payload or {}).get(slot if key == "\x00reached" else key) or "").split()).casefold()
        if key == "\x00reached" and not slot:
            continue
        if value == want:
            return uid
    return ""


def _named(payload: dict | None, retained: dict) -> str:
    """The declared candidate this call names in the retained slot — or, with no slot (a question Flash asked
    itself), in any of the call's values. Exact identity with a candidate, never a reading of words."""
    cands = {" ".join(str(c).split()).casefold() for c in retained.get("candidates") or []}
    slot = str(retained.get("slot") or "")
    values = [(payload or {}).get(slot)] if slot else list((payload or {}).values())
    for v in values:
        got = " ".join(str(v or "").split()).casefold() if isinstance(v, str) else ""
        if got and got in cands:
            return got
    return ""


def resuming(uid: str, retained: dict) -> None:
    """An answer resumes row `uid` with a new turn: the same act called elsewhere meanwhile is that answer's."""
    now = time.time()
    for k in [k for k, v in _RESUMING.items() if now - v[3] > RECENT_S]:
        _RESUMING.pop(k, None)
    _RESUMING[uid] = (base(retained.get("widget")), acts_of(retained), list(retained.get("candidates") or []), now)


def claim(wid: str, action: str, payload: dict | None) -> tuple[str, bool]:
    """The same act called again naming one of a waiting row's DECLARED candidates is his answer reaching the door:
    `(row, False)` — it runs on THAT row, never a new one. `(row, True)` when an answer already sent exactly this
    within `RECENT_S` (the model re-calling the act the answer re-ran). `("", False)` otherwise."""
    try:
        # The payload as the door will read it: the manifest's own keys (`widgets.contract.fold_aliases`). The model
        # may name the slot under a synonym (`name` for `contact`); reading the raw key missed his answer.
        from widgets import contract
        payload = contract.fold_aliases(base(wid), action, dict(payload or {}))
    except Exception as e:  # noqa: BLE001
        note(e)
        payload = dict(payload or {})
    try:
        # The row an answer is already resuming with this act (same card, a declared act, a declared candidate when
        # the question named some), within `RECENT_S`: an answer already resumes this request with its own turn.
        now = time.time()
        for uid, (w, acts, cands, at) in list(_RESUMING.items()):
            if now - at <= RECENT_S and w == base(wid) and action in acts and (
                    not cands or _named(payload, {"candidates": cands})):
                return uid, True
        from nucleo.circuit import asker, ledger
        from nucleo.cli import worker_api
        for a in worker_api.open_asks():
            art = asker.artefact(a["task_id"])
            ret = art.get("retained") or {}
            if not art.get("inline") or base(ret.get("widget")) != base(wid) or action not in acts_of(ret):
                continue
            got = _named(payload, ret)
            if got:
                if not take(a["ask_id"]):
                    return a["task_id"], True     # another trigger already ran this answer's act
                art.update(state="answered", answer=got, answered_at=time.time())
                asker.keep(a["task_id"], art)
                ledger.resumed(a["task_id"])
                _remember(wid, action, str(ret.get("slot") or ""), got, a["task_id"])
                return a["task_id"], False
        dup = _recent(wid, action, payload)
        if dup:
            return dup, True
    except Exception as e:  # noqa: BLE001
        note(e)
    return "", False


def bound(retained: dict, text: str, choice: int | None) -> dict | None:
    """The retained payload with his answer in its slot: the candidate the verdict chose, else his text (a fact, or
    the screen's option). None when there is nothing to bind."""
    slot = str(retained.get("slot") or "")
    cands = list(retained.get("candidates") or [])
    payload = dict(retained.get("payload") or {})
    if not slot:
        return payload                           # ASK_CONSENT: the act as it was, on his yes
    if choice is not None and 0 <= int(choice) < len(cands):
        payload[slot] = cands[int(choice)]
    elif str(text or "").strip():
        payload[slot] = " ".join(str(text).split())
    else:
        return None
    return payload


async def rerun(uid: str, entry: dict, text: str, choice: int | None = None):
    """Resume inline row `uid`: the retained act through the same door with the answer bound. The door's echo settles
    the row through `circuit.settle`; a door that asks again makes the SAME row wait on a new question."""
    from nucleo.circuit import ledger
    retained = entry.get("retained") or {}
    if retained.get("kind") == "matter":         # a task matter's question (V2-857 P0-2): his answer is on the row
        if take(str(entry.get("ask_id") or "")):
            ledger.resumed(uid)                  # the turn that bound it reads the answer off the row and acts
        return {"ok": True, "row": uid, "answered": True}
    if retained.get("kind") == "start":          # a parked errand's question (V2-857 P0-1): its yes relaunches it
        from nucleo.dispatch import confirm as _dc
        return _dc.rerun_start(uid, entry, text)
    from nucleo.request import consent_ask as _ca
    if retained.get("kind") in _ca.ACTS:         # a card's delete/restore, a cluster connect or send (phase 3)
        if not take(str(entry.get("ask_id") or "")):
            return None
        if choice is not None:
            yes = int(choice) == 0
        else:
            from nucleo.cli.worker_api_answer import _says_yes
            yes = _says_yes(str(entry.get("question") or ""), text)
        from nucleo import circuit
        if not yes:
            circuit.settle(row=uid, state="cancelled", outcome="he did not confirm it")
            return {"ok": False, "row": uid}
        ledger.resumed(uid)
        res = await _ca.ACTS[str(retained["kind"])](retained)
        ok = bool(isinstance(res, dict) and res.get("ok", True))
        circuit.settle(row=uid, state="done" if ok else "failed",
                       outcome=f"{retained['kind']} {'ran' if ok else 'failed'} on his yes")
        return {"ok": ok, "row": uid, "result": res}
    from nucleo.request import answered_task
    try:   # is this kept question about an act that leaves the machine? Read off the card's declared effects
        from widgets import effects
        card = base(retained.get("widget"))
        leaves = bool(card) and any(effects.leaves(card, a) for a in acts_of(retained))
    except Exception as e:  # noqa: BLE001
        note(e)
        leaves = False
    if leaves and not answered_task.deterministic(entry, choice):
        # F2e — an answer that needs composing (our own question, a fact, a free answer) about an act that LEAVES is
        # an identified task: a worker takes it on this row. A plain pick or a yes re-runs the kept act below.
        return {"ok": True, "worker": answered_task.start(uid, entry, text, choice), "row": uid}
    wid, action = str(retained.get("widget") or ""), str(retained.get("action") or "")
    if not take(str(entry.get("ask_id") or entry.get("corr_id") or "")):
        return None                              # this answer's act already ran (the model's own call took it)
    if entry.get("consent") == "ask_consent":
        # his answer is the candidate the brief (or the screen) chose — `#0` yes, `#1` no; only with no choice at
        # all are his words read by the confirmation recogniser
        if choice is not None:
            yes = int(choice) == 0
        else:
            from nucleo.cli.worker_api_answer import _says_yes
            yes = _says_yes(str(entry.get("question") or ""), text)
        payload = dict(retained.get("payload") or {}) if yes else None
        if payload is None:
            from nucleo import circuit
            circuit.settle(row=uid, state="cancelled", outcome="he did not confirm it")
            return None
    else:
        payload = bound(retained, text, choice)
    if not (wid and action) or payload is None:
        return None
    slot = str(retained.get("slot") or "")
    if slot and (dup := _recent(wid, action, payload, slot)) and dup != uid:
        # The same turn's own act already REACHED exactly this candidate on another row: one answer, one act.
        from nucleo import circuit
        circuit.settle(row=uid, state="done", outcome=f"the same act already left on row {dup}")
        return {"ok": True, "already": True, "row": dup}
    ledger.resumed(uid)
    _remember(wid, action, slot, str(payload.get(slot) or "") if slot else "", uid)
    row = ledger.get(uid) or {}
    from nucleo.flash import data_ops
    return await data_ops.dispatch_and_report(wid, action, payload, row=uid,
                                              text=str(row.get("goal") or row.get("title") or ""))
