"""V2-628 F3 — `chat_digest`: «¿tengo que hacer alguna acción de este grupo?» is answered from the LIVING
per-chat state distilled in idle, not by making the operator read the thread. A chat with no digest yet is
said honestly and channels to `peek` — «no digest» must never be spoken as «nothing pending»."""
from __future__ import annotations

import json
import time

import pytest

from connectors.messaging import archive, digest
from widgets import store as wstore
from widgets.mensajeria import data


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    yield
    archive.reset()


def _seed_digests():
    now = time.time()
    archive.record("whatsapp", "g1", [
        {"messageId": f"m{i}", "from": "Marta", "body": f"pago de la excursión {i}", "ts": now - 3600 - i * 60}
        for i in range(3)], direction="in", chat_name="Familias 3ºB", is_group=True)
    archive.record("email", "school", [
        {"messageId": f"e{i}", "from": "CRA", "body": f"boletín {i}", "ts": now - 7200 - i * 60}
        for i in range(3)], direction="in", chat_name="CRA EL VALLE")

    def llm(system, user):
        if "Familias" in user:
            return json.dumps({"summary": "pago pendiente",
                               "open_actions": [{"what": "pagar la excursión", "due": "2026-09-11"}],
                               "deadlines": ["2026-09-11: pago"]})
        return json.dumps({"summary": "boletín informativo", "open_actions": [], "deadlines": []})

    digest.refresh_due(llm, now=now)


def test_a_named_group_answers_with_its_open_actions():
    _seed_digests()
    res = data.answer_action("chat_digest", {"chat": "familias"})["result"]
    assert res["count"] == 1
    d = res["digests"][0]
    assert d["chat"] == "Familias 3ºB" and d["open_actions"][0]["what"] == "pagar la excursión"
    assert "acciones abiertas" in res["detail"]


def test_no_chat_named_returns_only_chats_with_open_actions():
    _seed_digests()
    res = data.answer_action("chat_digest", {})["result"]
    assert [d["chat"] for d in res["digests"]] == ["Familias 3ºB"], \
        "the newsletter chat has nothing open and must not pad the pending list"


def test_a_chat_without_a_digest_channels_to_peek_instead_of_denying():
    res = data.answer_action("chat_digest", {"chat": "vecinos"})["result"]
    assert res["count"] == 0
    assert "peek" in res["detail"] and "no digas que no hay nada pendiente" in res["detail"]


def test_the_manifest_declares_it_answer_only_and_safe():
    import pathlib
    m = json.loads((pathlib.Path(data.__file__).parent / "manifest.json").read_text())
    assert "chat_digest" in m["actions"]
    assert m["actions"]["chat_digest"].get("safe") is True
    assert "abiertas" in m["actions"]["chat_digest"]["desc"].lower() or \
           "ABIERTAS" in m["actions"]["chat_digest"]["desc"]
