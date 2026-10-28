"""What the bridge adds to the state it returns: the wall the page is, the URL change an action made, and the
stall of a tab that stopped moving.
Moved out of `act_api.py`; every module name is read through the package (`_f.<name>`), so a patch on `act_api`
still governs every call.
"""

from widgets.navegador import act_api as _f


def _with_wall(snap: dict, task_id: str = "") -> dict:
    """Annotate a snapshot with `wall` when the page it landed on STOPPED us (anti-bot challenge, CAPTCHA, load
    error) — V2-167.

    The worker drives through this endpoint and its only view of the page is what comes back here, so a wall it
    cannot see is a wall it grinds against. Measured: a run spent three minutes re-photographing Booking's
    `chal_t=` challenge and another walked through Google's `/sorry/index`, and both reported no obstacle at all.
    The rule telling the worker what to do about a captcha already existed (`nucleo/dispatch_prompts.py`); what
    was missing was any way for it to know it was looking at one.
    """
    try:
        from widgets.navegador import tasks as _t
        reason = _t.wall_reason(str((snap or {}).get("url") or ""))
        # V2-470 — the wall the TASK already knows (status 403/429, body needles — computed at capture,
        # tasks.py) has to travel too: URL sniffing alone let round 11 of `cheapest-monitor__us` record
        # walls on four retailers while the act responses carried exactly ONE «MURO» line. The worker's
        # entire view of the page is this response; a wall it cannot see is a wall it grinds against.
        if not reason and task_id:
            reason = str((_t.get(task_id) or {}).get("wall") or "")
    except Exception:
        return snap
    if reason:
        snap = dict(snap or {})
        snap["wall"] = reason
        # V2-213 — «prueba otro sitio» without saying WHICH ONE is a wish, not an instruction. Measured: thirteen
        # minutes on the same host in `book-hotel-night-known__es`, and `restaurant-tonight-madrid` ending on a
        # DuckDuckGo results page. The genetic catalog knows the task's category and now also where to go when
        # the trusted site shuts the door; the host that just blocked us is EXCLUDED, because offering the site
        # where it is stuck reads as «insist».
        try:
            from nucleo.flash import site_catalog as _sc
            from widgets.navegador import tasks as _t2
            goal = str((_t2.get(task_id) or {}).get("goal") or "") if task_id else ""
            alts = _sc.alternatives_for(goal, _t.host_of(str(snap.get("url") or "")))
            if alts:
                snap["wall_alts"] = [{"name": n, "url": u} for n, u in alts[:3]]
        except Exception:
            pass
        # V2-470 — pivoting SITES has a limit the pivoter cannot see: when this task's wall history spans
        # TWO OR MORE hosts, the browser channel itself is being refused (fresh profile, anti-bot mood),
        # and «prueba otro sitio» becomes a treadmill. The streak is a fact of the task record; what to do
        # about it is printed by nav_cli, next to the wall it belongs to. One walled host stays a site
        # problem — the alternatives above are the right answer there.
        try:
            from widgets.navegador import tasks as _t3
            hist = (_t3.get(task_id) or {}).get("walls") or [] if task_id else []
            sites = sorted({str(w.get("site") or "") for w in hist if w.get("site")}
                           | ({_t.host_of(str(snap.get("url") or ""))} - {""}))
            if len(sites) >= 2:
                snap["wall_streak"] = {"n": max(len(hist), 2), "sites": sites}
        except Exception:
            pass
    return snap


def _query_of(url: str) -> dict:
    """The address PARAMETERS, verbatim. A listing encodes its filters there — any filters, not just one."""
    try:
        from urllib.parse import parse_qsl, urlsplit
        return {k: v for k, v in parse_qsl(urlsplit(str(url or "")).query, keep_blank_values=True)}
    except Exception:
        return {}


def _with_url_change(before: str, snap: dict) -> dict:
    """Tell the worker WHAT changed in the page address, not only what it is now.

    V2-293 — measured in the 13:42 batch, `search-buy-guitar__es`, with the model driving blind (the
    session-serving tier cannot read images, V2-289). The worker wanted a MAXIMUM price of €150: it clicked the
    filter, typed «150»… and the page went to `?min_sale_price=750`. MINIMUM price, and 750. The round ended with
    ZERO extractions, and nothing in the bridge response said that the filter had landed somewhere else: the full
    URL travels on one long line between the title and elements, and a new parameter inside it is not visible.

    What is added is the DELTA, the only thing the worker cannot infer: it has the current URL, but not the
    previous one. It is generic by construction — whatever parameters exist are compared without knowing their
    site or meaning; the same mechanism works for a price filter, a size filter, or a next page.

    Deliberately, this does NOT judge whether the change is what the worker wanted: that is the worker's job,
    since it knows what was requested. This reports what the page says about itself.
    """
    a, b = _f._query_of(before), _f._query_of(str((snap or {}).get("url") or ""))
    if not before or a == b:
        return snap
    bits = []
    for k, v in b.items():
        if k not in a:
            bits.append(f"{k}={v} (nuevo)")
        elif a[k] != v:
            bits.append(f"{k}: {a[k]} → {v}")
    for k in a:
        if k not in b:
            bits.append(f"{k} ya no está")
    if not bits:
        return snap
    snap = dict(snap or {})
    snap["url_change"] = "; ".join(bits[:6])
    return snap


def _with_stall(task_id: str, snap: dict) -> dict:
    """Tell the worker how long its own task has gone WITHOUT MOVING — the half of V2-167 that never reached it.

    The wall travels to the worker (above) and the stall did not, which left the two halves of the same fact in
    different places: the FlashBrain turn learned that a task had stopped moving, and the only party that could
    do anything about it did not.

    Measured on `find-theatre-tickets__es` (2026-08-20 01:01): the worker navigated seven times, landed on the
    right event page at 00:40:32, and then took FOURTEEN screenshot revisions of it without a single further
    navigation for roughly twenty minutes. It was not blocked and it was not idle — it was looking at the page
    over and over. Nothing in what came back from here said «you have been here a while», so from inside the
    loop every `look` was as good as the first. Same shape on `restaurant-tonight-madrid`: eleven minutes and
    ten captures of one page.

    Only reported past the same threshold the turn uses, so an ordinary page-by-page pass says nothing.
    """
    try:
        from widgets.navegador import tasks as _t
        stalled = int((_t.get(task_id) or {}).get("stalled_s") or 0) if hasattr(_t, "get") else 0
        if not stalled:
            for _p in _t.active_progress():
                if str(_p.get("id") or "") == str(task_id):
                    stalled = int(_p.get("stalled_s") or 0)
                    break
    except Exception:
        return snap
    if stalled >= _f._STALL_HINT_S and not (snap or {}).get("wall"):
        snap = dict(snap or {})
        snap["stalled_s"] = stalled
        snap["hint"] = (f"llevas {stalled // 60} min en esta página sin avanzar: o extraes ya lo que necesitas "
                        f"de lo que tienes delante, o pruebas otro sitio. Repetir `look` no la cambia.")
    return snap
