"""The agenda's reference index speaks the agent's language (V2-778 F3-30, 2026-10-02).

Measured live on `agenda-everyday-edits__us` (sandbox, English agent): after an edit the turn said «Done. Right
now it holds: … «Abril's piano lesson (cita 2026-10-07 17:00 · todos los miércoles hasta el 2026-11-30)»». That
sentence is assembled from this index's HINTS (`widget_data_turn.named_ack`), and the hints were Spanish whatever
language the agent spoke: «cita», «proyecto», and the repeat rule described with `recur.describe`'s Spanish default.
"""
from __future__ import annotations

import re

import pytest

_SPANISH = re.compile(r"\b(cita|proyecto|todos|hasta|semanas|meses|días|fecha de fin)\b", re.I)


def _index(monkeypatch, code):
    from i18n import langs
    from widgets.agenda import data as AD, index as IX
    monkeypatch.setattr(langs, "current_language", lambda: langs.LANGUAGES[code])
    import datetime as _dt
    soon = _dt.date.today() + _dt.timedelta(days=5)        # relative: a fixture date never goes stale
    db = {"projects": [{"id": "p1", "name": "Website", "status": "active"}],
          "meetings": [{"title": "Piano lesson", "date": soon.isoformat(), "startTime": "17:00",
                        "repeat": {"freq": "weekly", "days": [soon.weekday()], "interval": 1,
                                   "until": (soon + _dt.timedelta(days=60)).isoformat()}}],
          "tasks": [], "lists": []}
    monkeypatch.setattr(AD, "load_db", lambda: db)
    return IX.ref_index()


def test_an_english_agent_gets_english_hints(monkeypatch):
    rows = _index(monkeypatch, "en")
    hints = " ".join(str(r.get("hint") or "") for r in rows)
    assert hints and not _SPANISH.search(hints), hints


def test_a_spanish_agent_keeps_its_own(monkeypatch):
    rows = _index(monkeypatch, "es")
    hints = " ".join(str(r.get("hint") or "") for r in rows)
    assert "cita" in hints and "todos los" in hints, hints
