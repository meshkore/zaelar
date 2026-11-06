"""nucleo/request/send_task_answer.py — his answer to a send task's question, and the answering turn's own call.

The other half of `nucleo/request/send_task` (split by concern, nucleo files stay small): `answered` fills the slot
the task asked for on the SAME row and runs it (a which-answer that still leaves the words lacking hands the row to a
Brain Worker that composes them); `take_call` lets the model's call on the answering turn fill the waiting row, so the
bound answer and the call are one answer, never two sends.
"""
from __future__ import annotations

import time

from nucleo.request import base, note
from nucleo.request.send_task import (AGENT, HIS, KIND, NONE, _emit, _end_state, _keep, _question, _schedule, _words_of,
                                      artefact, missing, sources)
from nucleo.request.send_task_run import _rec

#: Spoken answers to a send task's TEXT question that the model did not quote (`compose`): the worker composes them.
_COMPOSE: set = set()
#: How long a waiting send task stays the one a quoted line of his completes (`fill_from_quote`): the conversation.
RECENT_S = 600.0


def compose(ask_id: str) -> None:
    """His spoken answer to this send task's text question was not quoted by the model: a worker composes it."""
    if ask_id:
        _COMPOSE.add(str(ask_id))


def fill_from_quote(said: str, model_text: str, *, emit=None) -> str:
    """The turn's model QUOTED words of his and named the person of the latest send task waiting on its TEXT: those
    words are the text, that row runs (measured live: «dile: prueba siete…» was not bound — the model said «Sending
    "prueba siete, ignóralo" to Andrew now» and the verdict ran `dismiss`). Both are required — his quoted words AND
    the person the row waits to write to — so a quote about anything else completes nothing. The row's uid, or "".
    """
    try:
        from nucleo.acts.message_names import TOK, fold
        from nucleo.circuit import asker
        from nucleo.cli import worker_api
        from nucleo.request import inline_ask, send_task_words
        quoted = send_task_words.quoted_his(said, model_text)
        if not quoted:
            return ""
        named = set(TOK.findall(fold(send_task_words.without(model_text, quoted))))
        now = time.time()
        for a in sorted(worker_api.open_asks(), key=lambda a: -float(a.get("since") or 0)):
            art = asker.artefact(str(a["task_id"]))
            ret = art.get("retained") or {}
            if ret.get("kind") != KIND or str(ret.get("slot_name") or "") != "text":
                continue
            if now - float(art.get("created") or 0) > RECENT_S:
                break
            uid = str(a["task_id"])
            keep = artefact(uid)
            who = [str(v) for s, d in (keep.get("slots") or {}).items() if d.get("rule") == "his_words"
                   for v in [dict(keep.get("payload") or {}).get(str(d.get("key") or s))] if v]
            if not who or not any(set(TOK.findall(fold(w))) & named for w in who):
                break                              # the latest waiting send is not the one this line speaks of
            entry = dict(art)
            got = answered(uid, entry, quoted)
            _emit(emit, "📨 his quoted words complete the send that waited for them", quoted,
                  {"cat": "flash", "task_id": uid, "ask_id": a.get("ask_id"), "ran": bool(got.get("ok"))})
            return uid
    except Exception as e:  # noqa: BLE001
        note(e)
    return ""


def answered(uid: str, entry: dict, text: str, choice: int | None = None) -> dict:
    """His answer fills the slot this task asked for, on this same row, and the task goes on. A `no` to its consent
    cancels it; a yes clears what the door asked about and runs it."""
    from nucleo import circuit, consent
    from nucleo.request import inline_ask
    retained = entry.get("retained") or {}
    ask_id = str(entry.get("ask_id") or entry.get("corr_id") or "")
    if str(entry.get("consent") or "") == consent.ASK_CONSENT:
        from nucleo.cli.worker_api_answer import decision
        said = decision(str(entry.get("question") or ""), text, choice)
        if said is None:
            return {"ok": False, "row": uid, "unclear": True}
        if not inline_ask.take(ask_id):
            return {"ok": True, "row": uid, "already": True}
        if said != "yes":
            circuit.settle(row=uid, state="cancelled", outcome="he did not confirm it")
            return {"ok": False, "row": uid}
        from nucleo.workers import taint
        taint.cleared(_rec(uid, artefact(uid)))
        _schedule(uid)
        return {"ok": True, "row": uid}
    key, slot = str(retained.get("slot") or ""), str(retained.get("slot_name") or "")
    if ask_id in _COMPOSE and slot == "text":
        # a SPOKEN answer the model did not quote is not the text: an instruction («reply with what the hotel's mail
        # says») is composed by a Brain Worker on this row — never sent literally (measured live, 2026-11-06)
        _COMPOSE.discard(ask_id)
        if not inline_ask.take(ask_id):
            return {"ok": True, "row": uid, "already": True}
        return {"ok": True, "row": uid, "worker": _worker(uid, artefact(uid), ask_id, " ".join(str(text).split()))}
    cands = list(retained.get("candidates") or [])
    value = str(cands[int(choice)]) if choice is not None and 0 <= int(choice) < len(cands) else \
        " ".join(str(text or "").split())
    if not (key and value):
        return {"ok": False, "row": uid, "unclear": True}
    if not inline_ask.take(ask_id):
        return {"ok": True, "row": uid, "already": True}
    art = artefact(uid)
    art.setdefault("payload", {})[key] = value
    (art.setdefault("slots", {}).setdefault(slot or key, {"key": key, "rule": ""}))["source"] = HIS
    from nucleo import his_words
    his_words.note(value)                      # his answer is his naming of that value, for every door
    _keep(uid, art)
    _end_state(uid, str(art.get("widget") or ""), str(art.get("action") or ""), art.get("payload") or {},
               _words_of(uid))
    nxt, nkey = missing(art)
    if nxt:
        # He answered WHICH person and the words still lack: his sentence most likely carried them (the model never
        # extracted them). A question about what he said is not legitimate — a Brain Worker composes the words from
        # his request on THIS row (the person already his, the end state on the row) and sends through the exit door.
        return {"ok": True, "row": uid, "worker": _worker(uid, art, ask_id, value, choice=choice)}
    from nucleo.circuit import ledger
    ledger.resumed(uid)
    inline_ask.resuming(uid, {"widget": art.get("widget"), "action": art.get("action"), "candidates": []})
    _schedule(uid)
    return {"ok": True, "row": uid}


def _worker(uid: str, art: dict, ask_id: str, answer: str, *, choice: int | None = None) -> int:
    """A Brain Worker on this row (`message` playbook): the words to compose, the person and the end state kept."""
    from nucleo.circuit import ledger
    from nucleo.request.answered_task import PLAYBOOK
    row = ledger.get(uid) or {}
    request = _words_of(uid)
    said = f"{request} — {answer}" if request and answer else request or answer
    ledger.resumed(uid)
    dw = dict((_spec_of(uid) or {}).get("done_when") or {})
    ctx = {"src": "answer", "kind": "generic", "task_uid": uid, "answers": ask_id, "playbook": PLAYBOOK,
           "surface": "voz", "origin": str(row.get("origin") or "voz"), "heard": answer,
           **({"trace": str(row["trace_id"])} if row.get("trace_id") else {}),
           **({"done_when": dw if "any" in dw or "all" in dw else {"any": [dw]}} if dw else {}),
           **({"chosen": f"{ask_id}#{int(choice)}"} if choice is not None else {})}
    from nucleo.acts.errand import escalate_to_slowbrain
    tid = int(escalate_to_slowbrain(said, context=ctx) or 0)
    _emit(None, "↩ answer handed its task to a worker", said, {"cat": "flash", "task_id": uid, "ask_id": ask_id,
          "worker": tid, "playbook": PLAYBOOK})
    if not tid:
        from nucleo import circuit
        circuit.settle(row=uid, state="failed", outcome="the answered task could not be started")
    return tid


def _spec_of(uid: str) -> dict | None:
    from nucleo.circuit import spec
    return spec.of_task(uid)


def take_call(wid: str, action: str, payload: dict | None, said: str) -> str:
    """The same act Flash calls on a turn that answers this task's question (the model heard his answer and called
    the door with it): its slots fill the waiting row, nothing new opens. The row's uid, or "" when no send task
    waits on this card's act."""
    try:
        from nucleo.circuit import asker
        from nucleo.cli import worker_api
        from nucleo.request import inline_ask
        for a in worker_api.open_asks():
            art = asker.artefact(a["task_id"])
            ret = art.get("retained") or {}
            if ret.get("kind") != KIND or base(ret.get("widget")) != base(wid) or str(ret.get("action")) != action:
                continue
            uid = str(a["task_id"])
            keep = artefact(uid)
            said = f"{_words_of(uid)} {said}".strip()     # his words on this task: the request and this answer
            got = sources(wid, action, dict(payload or {}), said, reading=keep.get("reading"))
            slot = str(ret.get("slot_name") or ret.get("slot") or "")
            if got.get(slot, {}).get("source", NONE) == NONE:
                continue                        # the call does not fill what this task is waiting for
            if not inline_ask.take(str(a["ask_id"] or "")):
                return uid                      # his answer already ran this
            art.update(state="answered", answer=str(dict(payload or {}).get(ret.get("slot")) or ""),
                       answered_at=time.time())
            asker.keep(uid, art)
            merged = {**dict(keep.get("payload") or {}),
                      **{k: v for k, v in dict(payload or {}).items() if isinstance(v, str) and v.strip()}}
            keep.update(payload=merged, slots=sources(wid, action, merged, said, reading=keep.get("reading")))
            for s, d in keep["slots"].items():   # what he already gave this task stays his
                if d["source"] == AGENT and str((artefact(uid).get("slots") or {}).get(s, {}).get("source")) == HIS:
                    d["source"] = HIS
            _keep(uid, keep)
            _end_state(uid, wid, action, merged, said)
            if missing(keep)[0]:
                return uid
            from nucleo.circuit import ledger
            ledger.resumed(uid)
            inline_ask.resuming(uid, {"widget": wid, "action": action, "candidates": []})
            _schedule(uid)
            return uid
    except Exception as e:  # noqa: BLE001
        note(e)
    return ""
