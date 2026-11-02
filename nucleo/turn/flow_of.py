"""Which open flow does a request belong to? — the one answer every door that CREATES work asks first (V2-784 F2).

The product's promise is that each request lands in its flow. Until now that was decided after the fact: the
dispatcher's dedup folded a duplicate escalation into a live worker (`dispatch_listener`), continuity inherited
an ended errand's sheet (`errand_continuity`) — both AFTER the turn had already opened a sheet. Measured on the
operator's demo pass (2026-10-21 19:23): a fragment launched a hunt, the full sentence launched a second one,
the dedup folded the second worker into the first and left the second sheet open with nobody behind it.

This is the same question asked BEFORE anything is opened, over every open flow at once — live workers, errands
parked on a question to him, escalations and fast passes in flight (`named_errand.known`, which reads
`errand_pool` and `launches`), and fast passes that just delivered. Not just the last trace: a question about the
weather in between does not hide the monitor hunt.

Two judges, the house ones, in order: the dedup's containment yardstick (`errands_of_a_turn.same_errand`,
microseconds — the fragment-inside-the-sentence case), then the model judge the dispatcher already uses
(`dedup.about_a_live_errand`) for a refinement that shares few words with its errand («under 350»). Fail-open in
the same direction as the dispatcher: an unreadable judge answers «no flow», and the door opens a new one.
"""
from __future__ import annotations

import asyncio

from loguru import logger

#: The model judge runs INSIDE a turn here (the dispatcher's copy runs after it), so it gets a turn-sized budget;
#: past it the answer is «no flow» — the dispatcher's dedup still stands behind, as an alarm (V2-784 F4).
JUDGE_S = 3.0


def candidates() -> list[dict]:
    """Every open flow a request can belong to. Same entry shape as `named_errand.known()`, plus `delivered`."""
    from nucleo.turn import named_errand as _ne
    out = list(_ne.known(with_finished=True))      # V2-844 F2: a just-ended errand is a flow a correction reopens
    try:
        from nucleo.turn.errands_of_a_turn import same_errand
        from nucleo.workers import ended as _ended
        for d in _ended.recent_listing_deliveries():
            goal = str(d.get("goal") or "")
            if goal and d.get("sheet") and not any(same_errand(goal, str(e.get("request") or "")) for e in out):
                out.append({"id": f"delivered:{d.get('id')}", "request": goal, "sheet": str(d["sheet"]),
                            "delivered": True, "parked": False})
    except Exception as e:  # noqa: BLE001 — a reader never breaks a turn
        logger.debug(f"flow_of: deliveries unreadable — {type(e).__name__}: {e}")
    return [c for c in out if str(c.get("request") or "").strip()]


def _settled_elsewhere(flow: dict) -> bool:
    """A flow a request can only be FOLDED into (parked on his yes, finished, delivered) — never joined live."""
    return bool(flow.get("parked") or flow.get("ended") or flow.get("delivered"))


def kind(flow: dict) -> str:
    """How a request JOINS this flow: «worker» (inject), «sheet» (re-run into its sheet), or «none»."""
    fid = str(flow.get("id") or "")
    if not flow.get("parked") and not flow.get("starting") and not flow.get("delivered") and ":" not in fid:
        return "worker"
    return "sheet" if str(flow.get("sheet") or "").strip() else "none"


def lexical(text: str, pool: list[dict]) -> dict | None:
    from nucleo.turn.errands_of_a_turn import same_errand
    hits = [c for c in pool if same_errand(text, str(c.get("request") or ""))]
    return hits[0] if hits else None


async def flow_of(text: str, *, emit=None) -> dict | None:
    """The open flow `text` belongs to, or None (a new flow). Never raises; costs nothing with no flow open."""
    text = str(text or "").strip()
    pool = candidates() if text else []
    if not pool:
        text and __import__("nucleo.acts.surface_owner", fromlist=["x"]).flow_said(text, "")   # V2-844 F0
        return None
    hit, by = lexical(text, pool), "containment"
    if hit is None or _settled_elsewhere(hit):
        # V2-844 F2 (M2): words alike only PROPOSE a parked or a finished errand — folding a request into one of those
        # (absorb, reopen) is decided by the model judge, so «a hotel in Paris» never reopens the finished Rome one.
        try:
            from nucleo.request import append as _dedup
            tid = await asyncio.wait_for(asyncio.to_thread(
                _dedup.about_a_live_errand, text, [(str(c["id"]), str(c["request"])) for c in pool]), JUDGE_S)
        except Exception as e:  # noqa: BLE001 — fail-open: no flow, the door opens a new one
            logger.warning(f"flow_of: the judge failed, treating as a new flow — {type(e).__name__}: {e}")
            tid = ""
        hit, by = next((c for c in pool if str(c["id"]) == tid), None), "model"
    from nucleo.acts import surface_owner as _own
    _own.flow_said(text, str((hit or {}).get("id") or ""))   # V2-844 F0: compared with the dispatcher's answer
    if hit is not None and emit is not None:
        emit("flow", "🧵 la petición es de un flujo abierto", role="system", text=f"{text[:100]} → {hit['request'][:100]}",
             extra={"cat": "flash", "flow": hit.get("id"), "sheet": hit.get("sheet", ""), "by": by,
                    "join": kind(hit)})
    return hit


async def join(text: str) -> dict:
    """The listing door's use of the route (`flow_door.join`, where the consequences live)."""
    from nucleo.turn import flow_door
    return await flow_door.join(text)


def late_fold(target: str, ctx: dict) -> str:
    """The dispatcher folded an escalation into live errand `target` AFTER the turn acted (V2-784 F3/F4).

    That fold is a backstop now: with `flow_of` asked first it should not fire, so it is an ALARM with its
    evidence, not a silent merge. And it no longer leaks: the escalation's own sheet, when it is not the
    target's, is closed instead of left on screen with nobody writing into it (the 19:23 «Searching in depth…»
    card). Returns the sheet it closed, "" when none. Never raises."""
    own = str((ctx or {}).get("sheet") or "").strip()
    try:
        from nucleo import dispatch as _d
        rec = _d.get_record(target)
        theirs = str(_d.sheet_of(rec) or "") if rec is not None else ""
    except Exception as e:  # noqa: BLE001
        logger.warning(f"flow_of: late fold into {target} — target unreadable: {e}")
        theirs = ""
    orphan = own if own and own != theirs else ""
    orphan and __import__("nucleo.acts.surface_owner", fromlist=["x"]).orphan(orphan, "closed")   # V2-844 F0
    __import__("nucleo.turn.flow_door", fromlist=["x"]).backstop(target, ctx, "live", orphan=orphan)
    try:
        if orphan:
            from widgets.results import data as _sheet
            from nucleo.acts import canvas
            canvas.apply("close", _sheet.instance_id(orphan), src="system:flow_of")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"flow_of: could not report/close the late fold into {target}: {e}")
    return orphan


# ── V2-844 F2 · THE door: one route per turn, decided before the first side effect ─────────────────────────────
# V2-784 made `flow_of` «the one door» and gave it one caller. Every door that starts work or opens an errand surface
# now asks `route` (the turn's, begun in parallel with its model call) — the escalation portal, the listing door, the
# part-by-part relay — and the dispatcher's dedup stays behind it as a backstop that folds AND warns.
CONVERSATION, NEW, LIST = "conversation", "new", "list"
INJECT, ABSORB, REOPEN, JOIN = "inject", "absorb", "reopen", "join"
_TURN: dict = {}          # trace -> the route task begun for that turn
_NOT_MINE: list = []      # (words, flow id) a worker handed back: never folded there again (V2-784 F5)


def joins_as(flow: dict, brief=None) -> str:
    """How a request JOINS a flow it belongs to: a live worker takes it (`inject`, or the turn's paid stop verdict —
    `stop`, `steer`, `replace`), a parked errand absorbs it, an ended or delivered one reopens into its sheet, an
    escalation or pass still starting is joined in its sheet."""
    if flow.get("parked"):
        return ABSORB
    if flow.get("ended") or flow.get("delivered"):
        return REOPEN
    if kind(flow) == "worker":
        from nucleo.request import stop as _stop
        v = _stop.verdict(brief) if brief is not None else None
        return v if v in (_stop.STOP, _stop.STEER, _stop.REPLACE) else INJECT
    return JOIN


def chat(brief) -> bool:
    """Does the turn's PAID verdict read it, sure, as chat or a greeting (`request_type`)? Never on its own a reason
    to drop a request: only when no flow claims its words either (`route`)."""
    try:
        from nucleo.turn import brief as _tb, verdicts as _v
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "", min_confidence=_v.VETO) if brief is not None else ("", None)
        return bool(info) and kind in ("comment", "greeting")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"flow_of: the turn's kind unreadable — {e!r}")
        return False


def no_content(words: str) -> bool:
    from nucleo import matching
    return not matching.content_words(words)


def _of(flow: dict, words: str, brief) -> dict:
    from nucleo import sheets as _sheets
    return {"as": joins_as(flow, brief), "flow": str(flow["id"]), "sheet": _sheets.sheet_of_flow(flow), "words": words,
            "_flow": flow}


def _now(r: dict, brief) -> dict:
    """A route read again with the verdict as it stands NOW: a stop or a steer may have landed after it was begun."""
    return {**r, "as": joins_as(r["_flow"], brief)} if r.get("_flow") else r


def not_mine(words: str, flow: str) -> None:
    """A worker handed `words` back: they were not its errand. They never fold into it again."""
    _NOT_MINE.append((" ".join(str(words or "").split()).lower(), str(flow)))
    del _NOT_MINE[:-64]


def _was_handed_back(words: str, flow: dict) -> bool:
    from nucleo.turn.errands_of_a_turn import same_errand
    return any(f == str(flow.get("id")) and same_errand(w, words) for w, f in _NOT_MINE)


async def route(text: str, *, brief=None, emit=None) -> dict:
    """THE decision for a turn's request: `{as: conversation}` (nothing to commission: no content of its own, or chat
    that no open flow claims — «Okay.» after a request is no errand's content),
    `{as: list, parts: [...]}` (one sentence about several errands, part by part), `{as: inject|absorb|reopen|join|stop|
    steer|replace, flow, sheet}` (it belongs to an open flow), or `{as: new}`. `text` is read as the turn's WHOLE
    request (`errand.whole_request`). Never raises: an unreadable route is `new` and the dispatcher's backstop stands."""
    try:
        from nucleo.acts.errand import whole_request
        from nucleo.turn import brief as _tb
        brief = brief if brief is not None else _tb.of_this_turn()
        whole = whole_request(text)
        if no_content(whole):
            return {"as": CONVERSATION, "text": whole}
        pool = candidates()
        from nucleo.turn import split_by_errand as _sbe
        ps = _sbe.parts(whole, pool) if pool else []
        if len({str(p["errand"].get("id")) for p in ps}) > 1:
            return {"as": LIST, "text": whole, "parts": [_of(p["errand"], p["words"], brief) for p in ps]}
        flow = await flow_of(whole, emit=emit)
        if flow is None or _was_handed_back(whole, flow):
            return {"as": CONVERSATION if chat(brief) else NEW, "text": whole}   # chat no flow claims: nothing to commission
        return {**_of(flow, whole, brief), "text": whole}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"flow_of: route unreadable, a new flow — {type(e).__name__}: {e}")
        return {"as": NEW, "text": str(text or "")}


def begin(text: str, brief=None) -> None:
    """Start this turn's route NOW, beside its model call; the doors await it only before their first side effect."""
    try:
        from voice import trace as _trace
        t = _trace.current()
        if t and str(text or "").strip():
            _TURN[t] = asyncio.get_running_loop().create_task(route(text, brief=brief), name=f"flow-of-{t}")
            while len(_TURN) > 32:
                _TURN.pop(next(iter(_TURN)))
    except Exception as e:  # noqa: BLE001 — no loop or no trace: the door routes when it is reached
        logger.debug(f"flow_of: route not begun — {type(e).__name__}: {e}")


async def settled() -> dict | None:
    """This turn's route, awaited (within the judge's budget); None when the turn began none."""
    from voice import trace as _trace
    task = _TURN.get(_trace.current() or "")
    if task is None:
        return None
    try:
        return await asyncio.wait_for(asyncio.shield(task), JUDGE_S + 0.5)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"flow_of: the turn's route did not settle — {type(e).__name__}: {e}")
        return None


def _flat(text: str) -> str:
    from nucleo import matching
    return " ".join(matching.norm_text(text).split())


def for_request(req: str, brief=None, *, part: bool = False) -> dict:
    """The route of ONE request at a door that cannot await (the escalation portal). This turn's settled route when it
    is about these words: in a `list`, the part whose words ARE these (identity, never likeness); for one request of
    several (`part`), only the route of exactly its words. Else the lexical half alone — which may join a live or a
    starting flow, and only PROPOSES a parked or finished one: without the judge, that is a new errand and the
    dispatcher's backstop stands behind it."""
    from voice import trace as _trace
    from nucleo.acts.errand import whole_request
    from nucleo.turn.errands_of_a_turn import same_errand
    words = whole_request(req, part=part)
    if no_content(words):
        return {"as": CONVERSATION, "text": words}
    task = _TURN.get(_trace.current() or "")
    r = task.result() if task is not None and task.done() and not task.cancelled() and not task.exception() else None
    if r is not None:
        if r["as"] == LIST:
            mine = next((p for p in r["parts"] if _flat(p["words"]) == _flat(words)), None)
            if mine is not None:
                return {**_now(mine, brief), "text": words}
        elif _flat(r.get("text") or "") == _flat(words) or (not part and same_errand(words, r.get("text") or "")):
            return {**_now(r, brief), "text": words}
    hit = lexical(words, candidates())
    if hit is None or _was_handed_back(words, hit) or _settled_elsewhere(hit):
        return {"as": NEW, "text": words}
    return {**_of(hit, words, brief), "text": words}
