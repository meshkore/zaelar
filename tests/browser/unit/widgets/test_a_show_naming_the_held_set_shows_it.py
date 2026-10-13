"""A picture-less `imagenes:show` that NAMES the set on screen is that set (`show-real-photo-of-a-new-car__es`).

2026-10-14: six Ferrari Amalfi photos were on screen; «¿Me las enseñas?» → the promise repair called
`imagenes:show {query: "Ferrari Amalfi", source: "google"}` with no items, and the viewer refused it twice with
«no llegó ninguna imagen». `widgets/imagenes/held.py` answers it with the held set; a show naming something else,
or naming nothing, is still refused (demo pass 82: a Ferrari asked over a viewer of nebulae).
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def data(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.imagenes import data as d
    d.apply_action("clear")
    return d


def _amalfi(d):
    rows = [{"url": f"https://cdn.example.com/{i}.jpg", "title": f"Ferrari Amalfi {i}"} for i in range(6)]
    assert d.apply_action("show", {"items": rows, "query": "Ferrari Amalfi nuevo modelo", "source": "yandex"})["ok"]


def test_a_show_naming_the_held_subject_is_answered_by_the_set(data):
    _amalfi(data)
    r = data.apply_action("show", {"query": "Ferrari Amalfi", "source": "google"})
    assert r["ok"] is True and r["n"] == 6 and r.get("already_shown")
    assert data.view_data()["n"] == 6 and data.view_data()["source"] == "yandex", "the held set is left as it was"


def test_accents_and_case_do_not_split_a_subject(data):
    _amalfi(data)
    assert data.apply_action("show", {"title": "FERRARI amalfí"})["ok"] is True


def test_another_subject_or_no_subject_is_still_refused(data):
    _amalfi(data)
    for p in ({"query": "Ferrari Roma"}, {"query": "Ferrari Amalfi rojo"}, {}, {"items": "enséñamelo igual"}):
        r = data.apply_action("show", p)
        assert r["ok"] is False, p
    assert data.view_data()["n"] == 6, "a refusal never blanks the set on screen"


def test_an_empty_viewer_is_refused_whatever_the_query(data):
    assert data.apply_action("show", {"query": "Ferrari Amalfi"})["ok"] is False
