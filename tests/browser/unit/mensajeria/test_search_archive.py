"""V2-628 F1 — `search_archive`: a question about PAST messages channels to the permanent archive, never to
memory recall. The inbox, the threads and the msg pills all EXPIRE by design; the archive is the one copy
that does not, so «when did the school write?» and «did I ever answer it?» have somewhere to be answered
from — with the honest boundary that the log only covers what arrived after its activation.
"""
from __future__ import annotations

import time

import pytest

from connectors.messaging import archive
from widgets import store as wstore
from widgets.mensajeria import data


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    yield
    archive.reset()


def _seed_school_month():
    now = time.time()
    archive.record("email", "school", [
        {"messageId": "e1", "from": "CRA EL VALLE", "body": "menú del comedor de octubre", "ts": now - 20 * 86400},
        {"messageId": "e2", "from": "CRA EL VALLE", "body": "reunión de padres el jueves", "ts": now - 2 * 86400},
    ], direction="in", chat_name="CRA EL VALLE")
    archive.record("email", "school", [
        {"messageId": "o1", "body": "asistiré a la reunión", "ts": now - 1 * 86400},
    ], direction="out", chat_name="CRA EL VALLE")
    return now


def test_who_wrote_this_month_is_answered_with_names_and_dates():
    _seed_school_month()
    r = data.answer_action("search_archive", {"sender": "valle", "since_days": 30})
    res = r["result"]
    assert res["count"] == 2, "both school messages of the window, and only the inbound ones carry the sender"
    assert all(m["from"] == "CRA EL VALLE" for m in res["matches"])
    assert all(len(m["when"]) == 16 for m in res["matches"]), "each match carries its date for the answer"
    assert "ARCHIVO" in res["detail"]


def test_did_we_answer_it_is_a_direction_query():
    _seed_school_month()
    r = data.answer_action("search_archive", {"chat": "valle", "direction": "out"})
    res = r["result"]
    assert res["count"] == 1 and res["matches"][0]["from"] == "yo"
    assert "reunión" in res["matches"][0]["body"]


def test_did_we_answer_it_is_a_join_that_names_the_date():
    _seed_school_month()
    res = data.answer_action("search_archive", {"q": "comedor", "check_reply": True})["result"]
    assert res["reply"] is not None, "an outgoing message in the same chat after the hit IS the answer"
    assert len(res["reply"]["when"]) == 16 and "asistiré" in res["reply"]["body"]
    assert "SÍ se contestó" in res["detail"] and res["reply"]["when"] in res["detail"]


def test_an_unanswered_message_is_stated_not_invented():
    _seed_school_month()
    now = time.time()
    archive.record("whatsapp", "g1", [
        {"messageId": "w1", "from": "Marta", "body": "hay que pagar la excursión", "ts": now - 3 * 86400},
    ], direction="in", chat_name="Familias 3ºB", is_group=True)
    res = data.answer_action("search_archive", {"q": "excursión", "check_reply": True})["result"]
    assert res["reply"] is None
    assert "NO consta ninguna respuesta" in res["detail"], "absence is declared, never a guessed yes"


def test_the_window_filters_and_text_walks_the_index():
    _seed_school_month()
    recent = data.answer_action("search_archive", {"sender": "valle", "since_days": 7})["result"]
    assert [m["body"] for m in recent["matches"]] == ["reunión de padres el jueves"]
    by_text = data.answer_action("search_archive", {"q": "comedor"})["result"]
    assert by_text["count"] == 1 and "comedor" in by_text["matches"][0]["body"]


def test_an_empty_archive_states_its_boundary_instead_of_denying_the_past():
    r = data.answer_action("search_archive", {"sender": "valle"})
    res = r["result"]
    assert res["count"] == 0 and res["archive_since"] is None
    assert "no indexa el pasado" in res["detail"], "the model must say the log has no coverage, not «it never happened»"


def test_a_miss_names_the_coverage_start():
    _seed_school_month()
    res = data.answer_action("search_archive", {"sender": "nadie-con-este-nombre"})["result"]
    assert res["count"] == 0 and res["archive_since"] is not None
    assert res["archive_since"] in res["detail"]


def test_no_criterion_is_a_refusal_that_names_the_arguments():
    r = data.answer_action("search_archive", {})
    assert r["ok"] is False and "since_days" in r["error"]


def test_the_manifest_declares_it_and_the_routing_line_fits():
    import json
    import pathlib
    m = json.loads((pathlib.Path(data.__file__).parent / "manifest.json").read_text())
    assert "search_archive" in m["actions"], "an undeclared capability is one the model narrates (V2-540)"
    assert m["actions"]["search_archive"].get("safe") is True
    assert "PASADOS" in m["actions"]["search_archive"]["desc"]
    assert "archivo" in m["whenToUse"] and len(m["whenToUse"]) <= 300, "the routing line is written to FIT (V2-549)"
