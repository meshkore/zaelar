"""Who owns each surface on his screen — measured in SHADOW (V2-844 F0). Nothing here changes behaviour.

The class V2-844 names: two decisions — «is this sentence new work or content for an open errand?» and «who may
touch this surface?» — are taken in many places, at different moments, with nobody owning the result. Before any
of that moves, this module records, as `owner` events, what the doors do today against what ONE owner per surface
would allow:

  · `show` / `write` — every show at the canvas door and every write of a turn into a sheet, with its would-be
    owner (`errand:<uid>` when an errand's row owns the instance, else the first actor that opened it) and its actor;
  · `non_owner_show` / `non_owner_write` — the actor is not the owner of an errand's surface;
  · `duplicate_open` — a new sheet opened for a request another open sheet already serves (the dedup's yardstick);
  · `orphan` — a sheet left waiting with no errand behind it, or a duplicate that had to be closed;
  · `discarded_launch` — a turn that was discarded unanswered still showed, wrote or launched work;
  · `fragment_goal` — an errand born with a fragment of its turn's joined request as its whole goal;
  · `door_disagree` — the flow door and the dispatcher's dedup answered differently for the same turn.

Violations carry `allow: False` and a `rule` (the class), so the shadow reader (`/api/observability/shadow?kind=owner`)
counts them per class like the arbiter's verdicts. Every entry point is best-effort and never raises: a measurement
must never touch the turn it measures. The registries are bounded RAM; a restart starts a new baseline.
"""
from __future__ import annotations

import time

from loguru import logger

from nucleo.acts.card_owner import errand as _errand, errand_of_rec as _errand_of_rec, is_live as _is_live

#: How long a turn is remembered as discarded / joined / judged by the flow door. A turn's side effects land within
#: seconds of it (the measured late write came 2.7 s after the discard); a minute covers a slow fast pass.
_TURN_TTL_S = 120.0
#: How many open surfaces are tracked at once: more than any screen holds, bounded so a long session cannot grow it.
_MAX = 256

_CLAIMS: dict[str, dict] = {}        # wid -> {owner, request, at}
_LAUNCHED: dict[str, list] = {}      # trace -> what it showed, wrote or launched (read when the discard comes later)
_FLOW_SAID: dict[str, str] = {}      # trace -> the flow door's answer ("" = new flow)


def _bound(d: dict) -> None:
    while len(d) > _MAX:
        d.pop(next(iter(d)))


def _fresh(d: dict, trace: str):
    v = d.get(trace)
    if isinstance(v, tuple) and time.time() - v[0] > _TURN_TTL_S:
        d.pop(trace, None)
        return None
    return v[1] if isinstance(v, tuple) else v


def _trace() -> str:
    try:
        from voice import trace as _t
        return _t.current()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"surface_owner: no trace readable — {type(e).__name__}: {e}")
        return ""


def _emit(cls: str, *, violation: bool, text: str = "", emit=None, **extra) -> None:
    try:
        if emit is None:
            from voice.observer import emit
        label = ("⚠️ owner: " if violation else "owner: ") + cls.replace("_", " ")
        emit("owner", label, role="system", text=text[:200],
             extra={"v": "V2-844", "shadow": True, "rule": cls, "allow": not violation, **extra})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"surface_owner: {cls} not recorded — {type(e).__name__}: {e}")


# ── who is acting, who owns ────────────────────────────────────────────────────────────────────────────────

def _errand_of_task(ref: str) -> str:
    """The errand a worker's ref names — its live record's row when registered, else the row its number composes (a
    worker shows its sheet before the dispatcher registers its record)."""
    try:
        from nucleo import dispatch as _d
        rec = _d.get_record(ref)
        return _errand_of_rec(rec) if rec is not None else _errand(ref)
    except Exception:  # noqa: BLE001
        return _errand(ref)


def actor_of(src: str) -> str:
    """The actor a canvas `src` names: `errand:<uid>`, `turn:<trace>`, `operator`, or "" (lifecycle — nobody acting)."""
    base, _, ref = str(src or "").partition(":")
    base = base.strip().lower()
    if base == "recall" and "::" in ref:
        sid = _sheet_of(ref)          # the errand this turn reopened IS the card's: named by its sheet, never by the card id
        return (owner_of_sheet(sid) or f"errand:{sid}") if sid else _errand_of_task(ref)
    if base in ("worker", "wall", "recall") and ref:
        return _errand_of_task(ref)
    if base == "sheet" and ref:
        return owner_of_sheet(ref) or f"turn:{_trace()}"
    if base == "turn":
        return f"turn:{ref}"
    if base == "user":
        return "operator"           # a permission, never an owner: his hands are always allowed
    if base in ("system", "client", "interrupt"):
        return ""
    return f"turn:{_trace()}"       # the model, the backstop, the action map: the turn that is running


def owner_of_sheet(sid: str) -> str:
    """The errand whose row owns sheet `sid` — live, parked or durable — else "". A row and its sheet share one name
    (`sheets.sheet_id_for` / `ledger.task_uid`), so a row whose sheet opened late still owns it."""
    sid = str(sid or "").strip()
    if not sid:
        return ""
    try:
        from nucleo import dispatch as _d
        for r in list(_d._SESSIONS.values()):
            uid = str(getattr(r, "uid", "") or "")
            if sid in (str(getattr(r, "sheet", "") or ""), uid):
                return _errand_of_rec(r)
        from nucleo.dispatch import confirm as _dc
        for tid, p in list((getattr(_dc, "_PENDING_CONFIRM", None) or {}).items()):
            if str(p.get("sheet") or "") == sid:
                return _errand(tid)
        from nucleo.circuit import ledger as _ledger
        if _ledger.get(sid):
            return f"errand:{sid}"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"surface_owner: owner of {sid} unreadable — {type(e).__name__}: {e}")
    return ""


def _sheet_of(wid: str) -> str:
    kind, _, inst = str(wid or "").partition("::")
    return inst if kind == "results" else ""


def _owner(wid: str, actor: str) -> str:
    return owner_of_sheet(_sheet_of(wid)) or (_CLAIMS.get(wid) or {}).get("owner") or actor


# ── the observations ─────────────────────────────────────────────────────────────────────────────────────

def _against_discard(actor: str, what: str, wid: str, emit=None) -> None:
    t = actor.split(":", 1)[1] if actor.startswith("turn:") else ""
    if not t:
        return
    from nucleo.turn import turn_marks
    if turn_marks.was_discarded(t):
        _emit("discarded_launch", violation=True, text=f"{what} {wid}", emit=emit, trace=t, what=what, id=wid)
    else:
        _LAUNCHED.setdefault(t, []).append((time.time(), what, wid))
        _bound(_LAUNCHED)


def _claim(wid: str, owner: str, request: str, emit=None) -> None:
    """First sight of `wid`: record its owner and, for a sheet, whether another open sheet serves the same request."""
    if wid in _CLAIMS:
        if request and not _CLAIMS[wid].get("request"):
            _CLAIMS[wid]["request"] = request
        return
    _CLAIMS[wid] = {"owner": owner, "request": request, "at": time.time()}
    _bound(_CLAIMS)
    if request and _sheet_of(wid):
        from nucleo.turn.errands_of_a_turn import same_errand
        twin = next((w for w, c in list(_CLAIMS.items()) if w != wid and _sheet_of(w) and c.get("request")
                     and same_errand(request, c["request"])), "")
        if twin:
            _emit("duplicate_open", violation=True, text=request, emit=emit, id=wid, twin=twin, owner=owner,
                  twin_owner=_CLAIMS[twin]["owner"])


def on_show(wid: str, src: str, *, emit=None) -> None:
    """A show the canvas door let through. Never raises."""
    try:
        actor = actor_of(src)
        if not wid or not actor:
            return
        _take_over(wid, actor)
        owner = _owner(wid, actor)
        _claim(wid, owner, "", emit)
        _judge("show", wid, actor, owner, src, emit)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"surface_owner: show of {wid} not measured — {type(e).__name__}: {e}")


def _take_over(wid: str, actor: str) -> None:
    """A new task of the same widget takes the card over: a claim held by an errand that is no longer live is
    released, so the next errand that shows it owns it (never counted as a non-owner show)."""
    held = (_CLAIMS.get(wid) or {}).get("owner") or ""
    if (held.startswith("errand:") and actor.startswith("errand:") and held != actor
            and not _sheet_of(wid) and not _is_live(held)):
        _CLAIMS.pop(wid, None)


def on_close(wid: str) -> None:
    _CLAIMS.pop(str(wid or ""), None)


def observe(op: str, wid: str, src: str) -> None:
    """The canvas door's one call: a show is measured, a close forgets its claim. Its rows go to the observer, never
    into the caller's own stream: a measurement must not become the last thing a door said."""
    on_show(wid, src) if op == "show" else (op == "close" and on_close(wid))


def on_write(sheet: str, request: str, *, emit=None) -> None:
    """A turn's fast pass wrote rows into `sheet`. `request` is what the door read; the turn's joined request, when
    its cut turn was folded in, is what the duplicate check compares. Never raises."""
    try:
        from widgets.results import data as _sheet
        wid, actor = _sheet.instance_id(sheet), f"turn:{_trace()}"
        owner = _owner(wid, actor)
        _claim(wid, owner, joined(_trace()) or request, emit)
        _judge("write", wid, actor, owner, "", emit)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"surface_owner: write of {sheet} not measured — {type(e).__name__}: {e}")


def _judge(op: str, wid: str, actor: str, owner: str, src: str, emit) -> None:
    errand_surface = owner.startswith("errand:")
    # the same rule the arbiter applies (V2-852 T11): only a LIVE owner is wronged — an ended one's card is taken over
    bad = errand_surface and actor != "operator" and actor != owner and _is_live(owner)
    _emit(f"non_owner_{op}" if bad else op, violation=bad, text=wid, emit=emit, id=wid, owner=owner, actor=actor,
          **({"src": src} if src else {}))
    _against_discard(actor, op, wid, emit)


def orphan(sheet: str, why: str, *, emit=None) -> None:
    """A sheet left with nobody behind it (`waiting`) or born a duplicate and closed (`closed`)."""
    _emit("orphan", violation=True, text=f"{sheet} · {why}", emit=emit, sheet=sheet, why=why)


def turn_discarded(trace: str = "") -> None:
    """The turn was discarded unanswered. What it already launched is reported now; what it launches later, then."""
    t = str(trace or _trace())
    if not t:
        return
    from nucleo.turn import turn_marks
    turn_marks.discarded(t)          # the behaviour reads it there (V2-844 F2); this module only measures
    for _at, what, wid in _LAUNCHED.pop(t, []):
        _emit("discarded_launch", violation=True, text=f"{what} {wid}", trace=t, what=what, id=wid, order="before")


def joined(trace: str) -> str:
    from nucleo.turn import turn_marks
    return turn_marks.cut_of(trace)[0]


def errand_born(tid, request: str, ctx: dict | None) -> None:
    """An escalation was queued: a launch of its turn, and is its goal only a fragment of the turn's request?"""
    try:
        t = str((ctx or {}).get("trace") or _trace())
        _against_discard(f"turn:{t}" if t else "", "launch", str(tid), None)
        whole = joined(t)
        if whole:
            from nucleo import matching
            mine, all_ = matching.content_words(request), matching.content_words(whole)
            if all_ and mine < all_:
                _emit("fragment_goal", violation=True, text=request, id=str(tid), joined=whole[:200], trace=t)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"surface_owner: errand {tid} not measured — {type(e).__name__}: {e}")


def flow_said(text: str, flow: str) -> None:
    """The flow door's answer for this turn ("" = a new flow)."""
    t = _trace()
    if t:
        _FLOW_SAID[t] = (time.time(), str(flow or ""))
        _bound(_FLOW_SAID)


def dispatcher_said(ctx: dict | None, request: str, into: str, by: str) -> None:
    """The dispatcher's dedup for an escalation of a turn the flow door judged: do the two doors agree?"""
    try:
        t = str((ctx or {}).get("trace") or "")
        said = _fresh(_FLOW_SAID, t) if t else None
        if said is None or bool((ctx or {}).get("confirmed")) or str(said).startswith("delivered:"):
            return      # a confirmed relaunch IS its errand; a delivered pass is continuity's, not the dedup's
        if str(said).removeprefix("esc:") == str(into or "").removeprefix("esc:"):
            return
        _emit("door_disagree", violation=True, text=request, trace=t, flow_of=said, dispatcher=str(into or ""), by=by)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"surface_owner: disagreement not measured — {type(e).__name__}: {e}")
