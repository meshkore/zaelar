#
# sweep.py — CLEARING A WINDOW OF THE CALENDAR, KEEPING WHAT HE NAMES (V2-693).
#
# The sibling `clear_all` learned on 2026-08-14 that an intention with no action behind it cannot be gotten
# right by the model. This is the same lesson one size down, measured on 2026-09-14 in his own words:
# «limpia todo los items de esta semana, menos lo de mañana a las 15h y el inicio de instituto de lunes».
#
# The only bulk tool was `clear_all`, whose scope is EVERYTHING and forever, so the model reached for it and
# then described a selective deletion it could not perform — and had the confirmation been answered yes, the
# two appointments he asked to KEEP would have gone too, along with every future one. «Menos estos» is not a
# nuance of «todo»: it is a different action.
#
# It lives in its own module because `data.py` sits on the 900-line ceiling and a ratchet is paid by
# EXTRACTING, never by raising the number. The back-imports are lazy and one-directional: `data.py` calls in
# here, nothing here is imported at `data.py`'s module level.
#
from __future__ import annotations

from . import gcal


def keep_list(payload: dict) -> list[dict]:
    """What the operator asked to KEEP, as rows of `{title?, date?, time?}`.

    Three shapes reach here and all three are how a person says it: a plain string («el zerohash»), a list of
    strings, or rows carrying a date and an hour («mañana a las 15h»). Anything unreadable is DROPPED rather
    than guessed — a keeper we cannot read must never silently become a deletion."""
    from . import data as _data

    raw = payload.get("keep")
    if raw is None:
        raw = payload.get("except")
    if raw is None:
        return []
    rows = raw if isinstance(raw, (list, tuple)) else [raw]
    out = []
    for r in rows:
        if isinstance(r, str) and r.strip():
            out.append({"title": r.strip()})
        elif isinstance(r, dict):
            row = {}
            if str(r.get("title") or "").strip():
                row["title"] = str(r["title"]).strip()
            if str(r.get("date") or "").strip():
                row["date"] = _data._resolve_date(str(r["date"]))
            t = str(r.get("time") or r.get("startTime") or "").strip()
            if t:
                row["time"] = t
            if row:
                out.append(row)
    return out


def kept(m: dict, keep: list[dict]) -> bool:
    """Does this appointment match ANY keeper? A keeper with several fields must match all of the ones it
    names — «mañana a las 15h» is a date AND an hour, and matching on the date alone would keep the rest of
    that day."""
    from . import data as _data

    for k in keep or []:
        if "date" in k and str(m.get("date") or "") != k["date"]:
            continue
        if "time" in k and str(m.get("startTime") or "") != k["time"]:
            continue
        if "title" in k and not _data._titles_overlap(k["title"], m.get("title")):
            # `_titles_overlap` and NOT plain containment: it is this widget's OWN judgement (V2-473 round 6,
            # reused by the twin settlement), it drops the filler words a person says, and it is what makes
            # «el zerohash» find «Gavin/Ricart zerohash blockchain intro». A containment test fails on that
            # exact sentence, which is the one he actually said.
            continue
        return True
    return False


def window(payload: dict) -> tuple[str, str]:
    """The closed date window the sweep applies to. With no end, the window is the single day he named; an
    inverted pair is swapped rather than refused, because «del viernes al lunes» is a window either way."""
    from . import data as _data

    lo = _data._resolve_date(str(payload.get("from") or payload.get("start") or ""))
    hi = _data._resolve_date(str(payload.get("to") or payload.get("end") or "")) if (
        payload.get("to") or payload.get("end")) else lo
    return (hi, lo) if hi < lo else (lo, hi)


def clear_range(db: dict, payload: dict) -> tuple[dict, list[dict]]:
    """Run the sweep over `db` IN PLACE and answer `(result, stuck)`.

    A row Google REFUSED to delete STAYS. Dropping it locally anyway would report a deletion the cloud never
    made, and the next sync pulls it straight back — which is exactly what happened the first time this ran
    against his real calendar: 42 reported gone, four still there."""
    from . import data as _data

    lo, hi = window(payload)
    keep = keep_list(payload)
    doomed = [m for m in db.get("meetings", [])
              if lo <= str(m.get("date") or "") <= hi and not kept(m, keep)]
    gone, stuck = [], []
    for m in doomed:
        if gcal.delete_google(m):
            _data._cancel_reminder(m)
            gone.append(m)
        else:
            stuck.append(m)
    db["meetings"] = [m for m in db.get("meetings", []) if m not in gone]
    for b in list(db.get("blocks", [])):
        if lo <= str(b.get("date") or "") <= hi:
            db["blocks"].remove(b)
    res = {"removed": len(gone), "from": lo, "to": hi,
           "kept": [m.get("title") for m in db.get("meetings", [])
                    if lo <= str(m.get("date") or "") <= hi and kept(m, keep)]}
    if stuck:
        # NAMED, not counted: «no pude con 4» is a number he can do nothing with.
        res["failed"] = [m.get("title") for m in stuck]
    return res, stuck
