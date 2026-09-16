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


# ── cancelling ONE appointment (V2-705) ──────────────────────────────────────────────────────────────────
def _matches(db: dict, payload: dict) -> list[dict]:
    """The meetings the spoken reference names: the title matched TOLERANTLY through the one shared matcher
    (`widgets/textmatch`, V2-705) — so «renovar seguro coche» finds «Renovar el seguro del coche» and a
    dropped letter is forgiven, the same intelligence contacts and messages get — plus the date when he
    gave one. A meeting whose title is an accent-folded SUPERSTRING of the reference still counts (his words
    are usually shorter than the calendar's), and above that, the tolerant score catches the rest."""
    from . import data as _data
    from .. import textmatch

    ref = str(payload.get("title") or "").strip()
    if not ref:
        return []
    fref = textmatch.fold(ref)
    raw_date = str(payload.get("date") or "")
    date = _data._resolve_date(raw_date) if raw_date else ""
    out = []
    for m in db.get("meetings", []):
        if date and m.get("date") != date:
            continue
        ftitle = textmatch.fold(m.get("title") or "")
        if not ftitle:
            continue
        # A folded substring (his phrasing is usually a slice of the real title) OR a tolerant score over the
        # floor (a typo, a C for a K). Substring stays because a 3-word slice of a 6-word title can fall under
        # the score floor on length alone, and a slice is a deliberate, precise reference.
        if fref in ftitle or textmatch.score(ref, m.get("title") or "") >= 0.72:
            out.append(m)
    return out


def dup_key(m: dict) -> tuple[str, str, str]:
    """WHAT MAKES TWO ROWS THE SAME APPOINTMENT: title, day, hour. One function, because two callers decide
    opposite things from it — `cancel_meeting` calls a group ONE appointment (so it takes every copy and
    never asks «which of the eleven?») and `dedupe_meetings` keeps one member of the group. If they ever
    grouped differently, one of them would be deleting a row the other calls distinct."""
    return (str(m.get("title") or "").strip().lower(), str(m.get("date") or ""),
            str(m.get("startTime") or ""))


def dedupe_meetings(db: dict, payload: dict) -> tuple[dict, list[dict]]:
    """KEEP ONE of each identical group and remove the copies. The action «simplify to one» needed (V2-710).

    Measured 2026-09-16, session `7a22136c`:

        he      «Okay. I see two. Items today at the same time.»
        zaelar  «You're right — two entries at 11:30 today… duplicates of the same appointment. Would you
                 like me to remove one of them?»
        he      «Yes, please. Simplify to one.»
        engine  BOTH gone
        he      «I said simplify to one, not delete both… the smart move would have been deleting one of
                 those. But you just did delete the two of them.»

    Nothing misread him. `cancel_meeting` removes every identical copy ON PURPOSE — eleven copies of one
    «Dentist» are a sync artifact, not eleven appointments, and asking «which of the eleven?» would be the
    absurd question. The model had no other action to reach for, so it reached for that one. The gap was in
    the VOCABULARY, not in the resolution: there was no way to say «leave one».

    `title`/`date` NARROW which groups are touched; with neither, every duplicate group in the calendar is
    collapsed. A group is identical title + day + hour — the same key `cancel_meeting` calls one
    appointment, so the two functions cannot disagree about what a duplicate is.
    """
    groups: dict[tuple, list[dict]] = {}
    pool = _matches(db, payload) if str(payload.get("title") or "").strip() else list(db.get("meetings", []))
    if not pool:
        return {"ok": False, "error": "not_found", "detail": "no appointment matches that"}, []
    from . import data as _data
    raw_date = str(payload.get("date") or "")
    date = _data._resolve_date(raw_date) if raw_date else ""
    for m in pool:
        if date and str(m.get("date") or "") != date:
            continue
        groups.setdefault(dup_key(m), []).append(m)
    extra = [m for rows in groups.values() for m in rows[1:]]
    if not extra:
        return {"ok": True, "removed": 0, "kept": len(groups),
                "detail": "no duplicates to collapse — nothing was touched"}, []
    gone, stuck = [], []
    for m in extra:                                        # the same order as `cancel_meeting`: Google first
        if gcal.delete_google(m):
            _data._cancel_reminder(m)
            gone.append(m)
        else:
            stuck.append(m)
    # BY IDENTITY, never by value: identical copies are EQUAL dicts, so `m not in gone` removes the one
    # this action exists to keep. (`cancel_meeting` can use `in` because it wants every copy gone.)
    _gone_ids = {id(m) for m in gone}
    db["meetings"] = [m for m in db.get("meetings", []) if id(m) not in _gone_ids]
    res = {"ok": True, "removed": len(gone), "kept": len(groups),
           "titles": sorted({str(m.get("title") or "") for m in gone})[:6]}
    if stuck:
        res["failed"] = [m.get("title") for m in stuck]
    return res, stuck


def cancel_meeting(db: dict, payload: dict) -> tuple[dict, list[dict]]:
    """Cancel the ONE appointment the payload names, IN PLACE, and answer `(result, stuck)`.

    Three refusals, each a sentence the model can act on, none of them a deletion:
      · no title → `selector_missing` (the contract upstream already refuses it; belt and braces here,
        because this function is also a library call);
      · nothing matches → `not_found`, with the upcoming titles so he can name one;
      · the title matches several DIFFERENT appointments (distinct date or hour) and he gave no date →
        `ambiguous`, listing them. Identical duplicates of one appointment (same title, day and hour —
        the calendar held 11 copies of «Dentist» on 16/09) are ONE appointment and go together: «remove
        the dentist» means all its copies, never «which of the eleven?».
    A row Google refuses to delete STAYS (the `clear_range` lesson: 42 reported gone, four still there).
    """
    from . import data as _data

    if not str(payload.get("title") or "").strip():
        return {"ok": False, "error": "selector_missing",
                "detail": "cancel_meeting needs `title` — an empty selector never means «every meeting»"}, []
    hits = _matches(db, payload)
    if not hits:
        soon = [f"«{m.get('title')}» {m.get('date', '')} {m.get('startTime', '')}".strip()
                for m in sorted(db.get("meetings", []), key=lambda m: (str(m.get("date") or ""), str(m.get("startTime") or "")))
                if str(m.get("date") or "") >= _data._today()][:8]
        return {"ok": False, "error": "not_found",
                "detail": "no appointment matches that title" + (f" (upcoming: {'; '.join(soon)})" if soon else "")}, []
    distinct = {dup_key(m) for m in hits}          # the SAME grouping `dedupe_meetings` keeps one of
    if len(distinct) > 1 and not str(payload.get("date") or "").strip():
        rows = sorted(distinct, key=lambda k: (k[1], k[2]))
        return {"ok": False, "error": "ambiguous",
                "options": [f"«{t}» {d} {h}".strip() for t, d, h in rows][:8],
                "detail": "that title matches several different appointments — say which day (or hour)"}, []
    gone, stuck = [], []
    for m in hits:
        if gcal.delete_google(m):
            _data._cancel_reminder(m)
            gone.append(m)
        else:
            stuck.append(m)
    db["meetings"] = [m for m in db.get("meetings", []) if m not in gone]
    res = {"ok": True, "removed": len(gone), "title": str((gone or hits)[0].get("title") or ""),
           "date": str((gone or hits)[0].get("date") or "")}
    if stuck:
        res["failed"] = [m.get("title") for m in stuck]
    return res, stuck
