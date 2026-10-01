"""What leaves the machine, or lands in a file beside the timeline, is scrubbed first (V2-778 F4-37, 2026-10-01).

Two places carried the operator's words and the engine's prompt verbatim. The feedback button attaches the
session's newest events to a report — including the `system` category, whose forensic turn capture holds the
whole composed prompt (memory, state, his contacts) — and sends them to us. And the full prompt capture
(`.meshkore/logs/prompts/<session>.jsonl`, ~40 KB a turn) was written unredacted, under the repo root whatever the
workspace, with no size bound, and ON in a hosted account. Now: the evidence drops `system` events and every
string goes through one scrubber (personal secrets + token shapes); the capture is scrubbed, lives under the
workspace, stops at a size cap, and is OFF in a hosted account unless `ZAELAR_LOG_PROMPTS=1` says otherwise.
"""
from __future__ import annotations

import json

_SECRET = "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_PASSWORD = "mi contraseña de netflix es Hunter2!xyz"


def _event(cat, label, payload):
    return {"id": 1, "ts_ms": 0, "topic": "observer", "corr_id": "", "session_id": "s1", "user_id": "u", "cat": cat,
            "kind": "brain", "label": label, "span": "", "ms": None, "model": "", "tokens_in": 0, "tokens_out": 0,
            "ver": "", "payload": json.dumps(payload, ensure_ascii=False)}


def test_the_feedback_evidence_drops_system_events_and_scrubs_the_rest(monkeypatch):
    from observability import flows
    from server import feedback_api as fb
    events = [_event("system", "🧾 turno (prompt+ventana+tools+decisión)", {"system_prompt": "MEMORY: his wife's name"}),
              _event("brain", f"key {_SECRET}", {"text": _PASSWORD, "token": "x"}),
              _event("ui", "ok", {"text": "nada que tapar"})]
    monkeypatch.setattr(flows, "session", lambda sid: {"session_id": sid})
    monkeypatch.setattr(flows, "events", lambda **k: list(events))
    out = fb._build_evidence("s1")
    blob = json.dumps(out, ensure_ascii=False)
    assert all(e.get("cat") != "system" for e in out["events"]), "the forensic prompt capture never leaves"
    assert _SECRET not in blob and "Hunter2!xyz" not in blob, blob
    assert "nada que tapar" in blob, "what has nothing to hide still travels"


def test_the_prompt_capture_is_scrubbed_and_lives_under_the_workspace(tmp_path, monkeypatch):
    from voice import observer
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("ZAELAR_LOG_DIR", raising=False)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    observer._full_prompt_record(f"system with {_SECRET}", [{"role": "user", "content": _PASSWORD}], "hola", {})
    files = list(tmp_path.rglob("*.jsonl"))
    assert files, "the capture must land under the workspace, not under the repo"
    text = files[0].read_text(encoding="utf-8")
    assert _SECRET not in text and "Hunter2!xyz" not in text, text


def test_the_prompt_capture_stops_at_its_size_cap(tmp_path, monkeypatch):
    from voice import observer
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("ZAELAR_LOG_DIR", raising=False)
    monkeypatch.setattr(observer, "PROMPTS_MAX_BYTES", 2_000)
    for _ in range(20):
        observer._full_prompt_record("x" * 500, [], "hola", {})
    size = sum(f.stat().st_size for f in tmp_path.rglob("*.jsonl"))
    assert size <= 2_000 + 1_000, size


def test_the_prompt_capture_is_off_in_a_hosted_account_unless_asked(tmp_path, monkeypatch):
    from voice import observer
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("ZAELAR_LOG_DIR", raising=False)
    monkeypatch.setenv("ZAELAR_USER_ID", "cloud-user-1")
    monkeypatch.delenv("ZAELAR_LOG_PROMPTS", raising=False)
    from nucleo import cloud_account
    assert cloud_account.is_cloud_account(), "fixture: this is a hosted account"
    assert observer.prompt_capture_on() is False
    monkeypatch.setenv("ZAELAR_LOG_PROMPTS", "1")
    assert observer.prompt_capture_on() is True, "the deployment can still ask for it"
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("ZAELAR_LOG_PROMPTS", raising=False)
    assert observer.prompt_capture_on() is True, "self-host keeps today's default"


def test_in_a_hosted_account_the_capture_file_is_not_written(tmp_path, monkeypatch):
    from voice import observer
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("ZAELAR_LOG_DIR", raising=False)
    monkeypatch.setenv("ZAELAR_USER_ID", "cloud-user-1")
    monkeypatch.delenv("ZAELAR_LOG_PROMPTS", raising=False)
    observer._full_prompt_record("system", [], "hola", {})
    assert not list(tmp_path.rglob("*.jsonl")), "a hosted account writes no prompt capture by default"
