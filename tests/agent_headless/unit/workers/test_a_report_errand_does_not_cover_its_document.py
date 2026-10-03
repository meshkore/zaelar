"""A report errand's first write to `results` mints its sheet without putting it over the document (demo pass 79).

F1 «write me a one page summary of the bitcoin whitepaper, in a document» (surface `informe`): the worker registered
its `sources` on `results`, `worker_api._own_sheet` opened the errand's sheet AND showed it, and F2 found the results
sheet on top of the summary. V2-644 already says a report errand never gets a results sheet auto-opened under it.
"""
from __future__ import annotations

import pytest

from nucleo import worker_api
from nucleo.workers.session import SessionRecord


@pytest.fixture
def shown(monkeypatch):
    seen: list[dict] = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label="", **kw: seen.append({"kind": kind, "label": label, **kw}))
    return seen


def _shows(seen):
    return [e for e in seen if e["kind"] == "widget" and e["label"] == "show"]


def test_a_report_errand_mints_its_sheet_without_showing_it(shown):
    rec = SessionRecord(task_id="901", goal="one page summary of the bitcoin whitepaper", surface="informe")
    sid = worker_api._own_sheet(rec)
    assert sid, "the box exists, so the rows it writes are not lost"
    assert _shows(shown) == [], "no results sheet over the document"


def test_a_list_errand_still_shows_its_sheet_on_first_write(shown):
    rec = SessionRecord(task_id="902", goal="three 27-inch 4K monitors under $400", surface="lista")
    assert worker_api._own_sheet(rec)
    assert len(_shows(shown)) == 1
