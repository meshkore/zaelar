"""The per-chat digest (V2-628 F3): one LIVING state per chat, distilled from the archive in idle.

The promise it keeps: «do I need to do anything from <group>?» is answerable without reading 200 messages.
The discipline it keeps: a chat is only distilled when it has NEW archive rows and has SETTLED, the state is
UPSERTED (never accumulated), a mute model leaves the previous digest standing, and the pass is injectable —
the domain module never imports a brain (the rem.py hook pattern, wired by nucleo/loop).
"""
import json
import re
import time

import pytest

from connectors.messaging import archive, digest

NOW = None  # each test computes its own


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "_db_path", lambda: str(tmp_path / "archive.db"))
    archive.reset()
    yield
    archive.reset()


def _seed_chat(hours_quiet=1.0, n=4, chat_id="g1", name="Familias 3ºB", tag="m"):
    now = time.time()
    last = now - hours_quiet * 3600
    msgs = [{"messageId": f"{tag}{i}", "from": "Marta",
             "body": f"hay que pagar la excursión antes del viernes ({i})",
             "ts": last - (n - 1 - i) * 60} for i in range(n)]
    archive.record("whatsapp", chat_id, msgs, direction="in", chat_name=name, is_group=True)
    return now


def _llm_ok(system, user):
    return json.dumps({"summary": "pending excursion payment",
                       "open_actions": [{"what": "pagar la excursión", "due": "2026-09-11"}],
                       "deadlines": ["viernes 2026-09-11: pago de la excursión"]})


def test_a_settled_chat_with_new_messages_gets_one_upserted_digest():
    now = _seed_chat()
    rep = digest.refresh_due(_llm_ok, now=now)
    assert rep["digested"] == 1
    d = digest.get("whatsapp", "g1")
    assert d and d["digest"]["open_actions"][0]["what"] == "pagar la excursión"
    # A second pass with no new messages costs nothing: due gating, not a timer.
    calls = []
    rep2 = digest.refresh_due(lambda s, u: calls.append(1) or _llm_ok(s, u), now=now + 3600)
    assert rep2["considered"] == 0 and not calls


def test_a_chat_still_moving_is_not_distilled_mid_flight():
    now = _seed_chat(hours_quiet=0.1)
    rep = digest.refresh_due(_llm_ok, now=now)
    assert rep["considered"] == 0 and digest.get("whatsapp", "g1") is None


def test_a_mute_model_leaves_the_previous_digest_standing():
    now = _seed_chat()
    digest.refresh_due(_llm_ok, now=now)
    _seed_chat(hours_quiet=0.9, n=2, chat_id="g1", tag="x")  # new rows, still settled
    rep = digest.refresh_due(lambda s, u: None, now=time.time())
    assert rep["failed"] >= 1
    d = digest.get("whatsapp", "g1")
    assert d and d["digest"]["open_actions"], "a failed pass must never hole out the standing state"


def test_find_only_open_is_the_anything_pending_question():
    now = _seed_chat()
    archive.record("email", "school", [
        {"messageId": f"e{i}", "from": "CRA", "body": f"boletín {i}", "ts": now - 7200 - i * 60}
        for i in range(3)], direction="in", chat_name="CRA EL VALLE")

    def llm(system, user):
        if "CRA EL VALLE" in user:
            return json.dumps({"summary": "newsletter", "open_actions": [], "deadlines": []})
        return _llm_ok(system, user)

    rep = digest.refresh_due(llm, now=now)
    assert rep["digested"] == 2
    pending = digest.find(only_open=True)
    assert [d["chat_name"] for d in pending] == ["Familias 3ºB"]
    assert len(digest.find()) == 2


def test_the_kill_switch_stops_the_pass_whole(monkeypatch):
    now = _seed_chat()
    monkeypatch.setenv("ZAELAR_CHAT_DIGEST", "0")
    calls = []
    rep = digest.refresh_due(lambda s, u: calls.append(1), now=now)
    assert rep == {"considered": 0, "digested": 0, "failed": 0} and not calls


def test_prose_around_the_json_is_tolerated_and_garbage_is_a_miss():
    good = digest._parse("Sure! Here it is:\n```json\n" + _llm_ok(None, None) + "\n```")
    assert good and good["open_actions"]
    assert digest._parse("I could not read the conversation.") is None


def test_the_loop_injects_the_heart_hook_into_the_pass():
    """The wiring guard (comment-stripped, per the V2-573 lesson): nucleo/loop must call
    digest.refresh_due with a memllm-backed hook — a pass nobody schedules is a module born dead."""
    import pathlib
    src = pathlib.Path("nucleo/loop.py").read_text()
    src = re.sub(r"#[^\n]*", "", src)
    assert "from connectors.messaging import digest" in src
    assert "refresh_due" in src and "chat_sync" in src
