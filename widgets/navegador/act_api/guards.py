"""What the bridge adds to the state it returns: the wall the page is, the URL change an action made, and the
stall of a tab that stopped moving. Names are read through the package (`_f.<name>`).
"""

from widgets.navegador import act_api as _f


def _with_wall(snap: dict, task_id: str = "") -> dict:
    """Annotate a snapshot with `wall` when the page STOPPED us (anti-bot challenge, CAPTCHA, load error) —
    V2-167. This response is the worker's only view of the page: a wall it cannot see is a wall it grinds against.
    """
    try:
        from widgets.navegador import tasks as _t
        reason = _t.wall_reason(str((snap or {}).get("url") or ""))
        # V2-470 — the wall the TASK already knows (status 403/429, body needles computed at capture) travels
        # too: URL sniffing alone misses most walls.
        if not reason and task_id:
            reason = str((_t.get(task_id) or {}).get("wall") or "")
    except Exception:
        return snap
    if reason:
        snap = dict(snap or {})
        snap["wall"] = reason
        # V2-213 — «try another site» must name WHICH: the site catalog offers alternatives for the task's
        # category, EXCLUDING the host that just blocked us (offering it again reads as «insist»).
        try:
            from nucleo.flash import site_catalog as _sc
            from widgets.navegador import tasks as _t2
            goal = str((_t2.get(task_id) or {}).get("goal") or "") if task_id else ""
            alts = _sc.alternatives_for(goal, _t.host_of(str(snap.get("url") or "")))
            if alts:
                snap["wall_alts"] = [{"name": n, "url": u} for n, u in alts[:3]]
        except Exception:
            pass
        # V2-470 — walls on TWO OR MORE hosts mean the browser channel itself is refused, and pivoting sites is a
        # treadmill: report the streak (cli.nav prints what to do). One walled host stays a site problem.
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
    """Tell the worker WHAT changed in the page address, not only what it is now (V2-293): the delta of the query
    parameters is the one thing it cannot infer (it has no previous URL). Generic — parameters are compared
    without knowing their site or meaning — and it does NOT judge whether the change is what the worker wanted.
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
    """Tell the worker how long its own task has gone WITHOUT MOVING (the half of V2-167 that never reached it):
    from inside the loop every repeated `look` seems as good as the first. Reported only past the same threshold
    the FlashBrain turn uses, so an ordinary page-by-page pass says nothing.
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
