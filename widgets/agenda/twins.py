"""Is this the SAME appointment? — title identity and the twin settlement (V2-778 F1, 2026-10-01).

Moved out of `widgets/agenda/data.py` (934 lines, over the 900 a new file may reach): how two rows are judged the
same commitment (V2-473: the title once articles and the widget's own nouns are gone, a token subset at the same
instant) and how a second write of one appointment settles a repeat rule on the first (V2-773). Unchanged;
`data` imports every name back.
"""
from __future__ import annotations

import re

from . import edit, gcal
from .when import _strip_accents


# ── THE SAME COMMITMENT WRITTEN TWICE (V2-208) ────────────────────────────────────────────────────────────────
# Measured on `remember-and-remind-deadline` (2026-08-20 14:39), from the sandbox's own `state.json`:
#
#     meetings = [«renovar el seguro del coche» 2026-08-27, «Renovar el seguro del coche» 2026-08-27]
#
# Two rows for one obligation, differing by an article and a capital letter. V2-194 fixed this for the BACKSTOP
# (`router_guards.already_in_agenda`, which checks before dispatching) and the model's OWN data-op has no such
# guard: two turns, two `add_meeting`, nobody comparing. The guard belongs HERE, next to the write, so every
# writer present and future gets it — that is the same reasoning that put `already_in_agenda` next to its write
# rather than inside the pure decision.
#
# Why the TIME is part of the key and not just the day: two viewings of the same flat at 10:00 and 17:00 are two
# meetings, and a duplicate that is silently dropped is worse than a duplicate that is visible. So the rule is
# narrow ON PURPOSE — same day, same time, same title once articles/case/punctuation are gone. A legitimate
# repeat carries a different hour or a different title; what it never carries is the same three.
# …plus the widget's own category nouns (V2-473 round 5): «Cita dentista con los niños» and «Dentista con
# los niños» are the SAME commitment — the model re-titles on a retry and the dedup let both rows in, each
# spawning its default reminder. The category noun of the widget itself is title noise, not identity.
_ARTICLES = {"el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "de", "del", "the", "a", "an",
             "cita", "reunion", "reunión", "meeting", "appointment", "evento"}


def _title_key(title: str) -> str:
    """Comparable form of a meeting title: no accents, no case, no punctuation, no articles."""
    words = re.findall(r"\w+", _strip_accents(str(title or "")).lower())
    return " ".join(w for w in words if w not in _ARTICLES)


def _is_same_meeting(a: dict, b: dict) -> bool:
    """Same day, same start time and the same title once the noise is gone.

    V2-473 round 6: at the SAME instant, one title's meaningful tokens being a SUBSET of the other's is
    also the same commitment («Llevar a los niños al dentista» vs «Dentista niños» landed as two meetings
    with two reminders). Disjoint titles at the same hour stay two meetings — a double-booked hour is the
    user's business, not ours to merge."""
    if str(a.get("date") or "") != str(b.get("date") or ""):
        return False
    if str(a.get("startTime") or "") != str(b.get("startTime") or ""):
        return False
    if _titles_overlap(a.get("title"), b.get("title")):
        return True
    return _same_subject(a, b)


# ── ONE SLOT, ONE SUBJECT, TWO WORDINGS (V2-781, 2026-10-10) ──────────────────────────────────────────────────
# Measured on `demo-initialization__us`: «Veterinario de Pixel» and «Pixel — veterinarian», both 2026-11-20
# 16:00-17:00, each with its own notice. The INIT says the vet visit twice (the pet section, then the calendar
# section) and the model wrote the first one in Spanish in an English session. The token-subset rule above
# compares words exactly, so a translation is «disjoint» and a second row landed. Two narrow widenings, both at
# the SAME instant only:
#   · a COGNATE counts as the same word (veterinario/veterinarian, dentista/dentist, producto/product): every
#     meaningful word of the shorter title has an exact or cognate partner in the longer one;
#   · the same PROPER NOUN (capitalised, and not just because it opens the title) in both titles, when both rows
#     also give the same END — the full slot. Nobody keeps two different appointments about Pixel in one slot.
def _cognate(x: str, y: str) -> bool:
    if x == y:
        return True
    if min(len(x), len(y)) < 5:
        return False
    n = 0
    for cx, cy in zip(x, y):
        if cx != cy:
            break
        n += 1
    return n >= max(5, min(len(x), len(y)) - 3)


def _cognate_subset(ta, tb) -> bool:
    wa, wb = _title_key(ta).split(), _title_key(tb).split()
    if not wa or not wb:
        return False
    short, long_ = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return all(any(_cognate(w, v) for v in long_) for w in short)


def _capitalised(title, *, skip_first: bool = False) -> set:
    words = re.findall(r"\w+", str(title or ""))
    return {_strip_accents(w).lower() for i, w in enumerate(words)
            if (i > 0 or not skip_first) and len(w) >= 3 and w[0].isupper() and not w.isupper()
            and _strip_accents(w).lower() not in _ARTICLES}


def _same_subject(a: dict, b: dict) -> bool:
    """Same instant already checked by the caller: a cognate wording, or a shared proper noun over the same end."""
    ta, tb = a.get("title"), b.get("title")
    if _cognate_subset(ta, tb):
        return True
    ea, eb = str(a.get("endTime") or ""), str(b.get("endTime") or "")
    if not ea or ea != eb:
        return False
    # a NAME in at least one title (capitalised past its opening word) and capitalised in the other too
    return bool((_capitalised(ta, skip_first=True) & _capitalised(tb))
                | (_capitalised(tb, skip_first=True) & _capitalised(ta)))


def _settle_rule(db: dict, twin: dict, new: dict) -> bool:
    """A second write of the SAME appointment that carries a repeat rule the row lacks settles the rule on the
    row (V2-773, 2026-09-27). «Anna vacation, December 20 through January 4» reached the card twice from the
    demo's INIT list: first as one all-day entry, then — the repair pass, with the end date this time — as a
    daily span. The twin rule saw the same title on the same day and dropped the richer write, so her
    vacation was a single day on the calendar. A rule the row already has is never overwritten here: that is
    `update_meeting`'s call, with the operator's words behind it."""
    if not isinstance(new.get("repeat"), dict) or twin.get("repeat"):
        return False
    twin["repeat"] = dict(new["repeat"])
    gcal.patch_google(twin)
    edit.touch(db, twin)
    return True


def _titles_overlap(ta, tb) -> bool:
    """One title's meaningful tokens equal to or a subset of the other's — the V2-473 round-6 rule,
    extracted so the hour-less-twin settlement (V2-652) compares titles with the exact same judgment."""
    ka, kb = _title_key(ta), _title_key(tb)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    sa, sb = set(ka.split()), set(kb.split())
    return sa <= sb or sb <= sa


def same_series(new: dict, meetings: list) -> dict | None:
    """The live SERIES a new series re-adds, or None: same title and start hour, and its first day is already one
    of that series' sessions (V2-781 T520, 2026-10-04).

    Measured on `weekly-appointment-until-june__us`: «there's no class next Tuesday, take off just that day» →
    the model wrote the whole series again from the FOLLOWING Tuesday (`add_meeting {date: 2026-10-13, repeat:
    weekly, …}`) and said «Done»: 77 rows where there were 38, every Tuesday doubled, and the class he removed
    still there with its notice. A series that starts on one of its twin's own sessions adds nothing he asked
    for. A second series on OTHER days (piano on Thursdays too) does not start on one, and is left alone."""
    if not isinstance(new.get("repeat"), dict) or not new.get("date"):
        return None
    from .query import _on_day
    for m in meetings or []:
        if (isinstance(m.get("repeat"), dict) and str(m.get("startTime") or "") == str(new.get("startTime") or "")
                and _titles_overlap(m.get("title"), new.get("title")) and _on_day(m, str(new["date"]))):
            return m
    return None


def series_refusal(new: dict, meetings: list) -> dict | None:
    """`add_meeting`'s answer when the new series re-adds a live one (see `same_series`), or None."""
    m = same_series(new, meetings)
    if m is None:
        return None
    return {"ok": False, "code": "series_exists",
            "error": f"«{m.get('title')}» already repeats on these days from {m.get('date')} — this would write it "
                     f"twice. To drop ONE day: cancel_meeting {{title, date: that day}}; to end it from a day: "
                     f"cancel_meeting {{title, from}}; to change it: update_meeting."}
