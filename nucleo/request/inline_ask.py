"""nucleo/request/inline_ask.py — an inline act a door answered with a consent ASK makes ITS row wait (V2-851 §3/§3a).

Before: «send a message to Raquel» with two Raquels ran inline in the turn, the door refused with its question, the
turn's mouth said it — and the row ended `failed`. Nothing durable was asked, no `ask_id` could be answered by screen,
and his next words only worked if the model happened to call the door again.

Now a refusal that IS a consent ASK — the door names the candidates (`candidates` + the payload `slot` they fill:
ASK_WHICH) or the facts it lacks (`needs`: ASK_FACT), or says `consent: ask_consent` — goes through THE asker
(`nucleo/circuit/asker`) exactly as a worker's question does: the row waits for his answer with its `ask_id`, the act
is retained on the row's `ask` artefact ({widget, action, payload, slot, candidates}), and the `ask` event puts the
question on screen. The row is never settled `failed` for it.

The answer (screen route, or the brief's binding verdict on a later turn) resumes THAT row: the retained act re-runs
through the same door with the answer bound into its slot (`rerun`) — never a new row, never a model run. Which
candidate he named is the binding verdict's choice over the declared candidates (`worker_api_bind`); his words are
never matched here. The door's echo then settles the row through `circuit.settle`, as any inline act's.
"""
from __future__ import annotations

import time

from loguru import logger

#: How long a re-run's slot value is remembered, so the same act the model ALSO calls on the answer turn is not sent
#: twice (the answer already sent it). Not a matcher: the key is the declared slot value, exact.
RECENT_S = 120.0
_RECENT: dict = {}


def _note(e: BaseException) -> None:
    import sys
    logger.debug(f"inline_ask: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


def _base(wid: str) -> str:
    return str(wid or "").split("::", 1)[0]


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


def held(row: str, wid: str, action: str, payload: dict | None, res, *, question: str = "") -> str:
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
        q = (question or refusal_line.speakable(_base(wid), res) or str(res.get("message") or "")).strip()
        entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": row, "task_id": "", "inline": True, "action": action,
                 "question": q, "answer": "", "result": None, "session": session,
                 "consent": v["verdict"], "candidates": v["candidates"], "options": v["candidates"],
                 "said": True,                   # the turn's own mouth said it: the pulse never relays it again
                 "retained": {"widget": wid, "action": action, "payload": dict(payload or {}), "slot": v["slot"],
                              "candidates": v["candidates"]}}
        ledger.store().task_patch(row, session_id=session)
        return asker.ask(row, entry)
    except Exception as e:  # noqa: BLE001 — a question that could not be made durable leaves the refusal as it was
        _note(e)
        return ""


def _remember(wid: str, action: str, slot: str, value: str, uid: str) -> None:
    now = time.time()
    for k in [k for k, (_u, t) in _RECENT.items() if now - t > RECENT_S]:
        _RECENT.pop(k, None)
    _RECENT[(_base(wid), action, slot, " ".join(str(value or "").split()).casefold())] = (uid, now)


def _recent(wid: str, action: str, payload: dict | None) -> str:
    now = time.time()
    for (w, a, slot, value), (uid, t) in list(_RECENT.items()):
        if (w, a) == (_base(wid), action) and now - t <= RECENT_S and value and value == " ".join(
                str((payload or {}).get(slot) or "").split()).casefold():
            return uid
    return ""


def claim(wid: str, action: str, payload: dict | None) -> tuple[str, bool]:
    """The same act called again naming one of a waiting row's DECLARED candidates is his answer reaching the door:
    `(row, False)` — it runs on THAT row, never a new one. `(row, True)` when an answer already sent exactly this
    within `RECENT_S` (the model re-calling the act the answer re-ran). `("", False)` otherwise."""
    try:
        from nucleo.circuit import asker, ledger
        from nucleo.cli import worker_api
        for a in worker_api.open_asks():
            art = asker.artefact(a["task_id"])
            ret = art.get("retained") or {}
            if not art.get("inline") or _base(ret.get("widget")) != _base(wid) or ret.get("action") != action:
                continue
            got = " ".join(str((payload or {}).get(ret.get("slot") or "") or "").split()).casefold()
            if got and got in {str(c).casefold() for c in ret.get("candidates") or []}:
                art.update(state="answered", answer=got, answered_at=time.time())
                asker.keep(a["task_id"], art)
                ledger.resumed(a["task_id"])
                _remember(wid, action, str(ret.get("slot") or ""), got, a["task_id"])
                return a["task_id"], False
        dup = _recent(wid, action, payload)
        if dup:
            return dup, True
    except Exception as e:  # noqa: BLE001
        _note(e)
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
    wid, action = str(retained.get("widget") or ""), str(retained.get("action") or "")
    if entry.get("consent") == "ask_consent":
        from nucleo.cli.worker_api_answer import _says_yes
        payload = dict(retained.get("payload") or {}) if _says_yes(str(entry.get("question") or ""), text) else None
        if payload is None:
            from nucleo import circuit
            circuit.settle(row=uid, state="cancelled", outcome="he did not confirm it")
            return None
    else:
        payload = bound(retained, text, choice)
    if not (wid and action) or payload is None:
        return None
    ledger.resumed(uid)
    slot = str(retained.get("slot") or "")
    _remember(wid, action, slot, str(payload.get(slot) or "") if slot else "", uid)
    row = ledger.get(uid) or {}
    from nucleo.flash import data_ops
    return await data_ops.dispatch_and_report(wid, action, payload, row=uid,
                                              text=str(row.get("goal") or row.get("title") or ""))
