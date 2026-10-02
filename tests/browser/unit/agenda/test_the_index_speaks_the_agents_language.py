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


# ── the same class in every widget whose hints are read back (one helper: `widgets/hint_lang.py`) ──────────

@pytest.fixture
def english(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.LANGUAGES["en"])


def test_a_playlist_counts_songs_in_english(english, monkeypatch):
    from widgets.musica import data as MD
    monkeypatch.setattr(MD, "_load_db", lambda: {"playlists": [{"id": "p", "name": "Gym", "tracks": [{}, {}]}]})
    assert MD.ref_index()[0]["hint"] == "2 songs"


def test_a_download_and_the_catalogue_say_so_in_english(english, monkeypatch):
    from widgets.archivos import torrents as T
    monkeypatch.setattr(T, "state", lambda db: {"catalog": {"releases": [{"title": "A film"}]}})
    monkeypatch.setattr(T, "live_rows", lambda db: [{"id": "t1", "title": "A song", "group": "seed"}])
    hints = [r["hint"] for r in T.refs({})]
    assert hints == ["catalogue", "seeding"], hints


def test_a_contact_group_counts_members_in_english(english, monkeypatch):
    from widgets.contactos import data as CD
    monkeypatch.setattr(CD, "load_db", lambda: {})
    monkeypatch.setattr(CD, "visible", lambda db: [{"id": "g", "name": "Family", "kind": "group",
                                                    "platform": "whatsapp", "members": [1, 2, 3]}])
    assert CD.ref_index()[0]["hint"] == "whatsapp · 3 members"
