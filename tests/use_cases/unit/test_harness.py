"""Unit tests for the use-case harness's deterministic pieces (watchdog.parse, verify's extraction logic).
The harness drives an LLM and a live server, so it isn't itself deterministic — but its parsing/extraction
logic is, and is worth pinning down without a live zaelar or a real LLM call."""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import verify, watchdog


def test_watchdog_parse_valid_json():
    out = '{"health":"off_track","action":"nudge","nudge_text":"no dije ciudad","reason":"asumió Sevilla"}'
    v = watchdog.parse(out)
    assert v == {"health": "off_track", "action": "nudge", "nudge_text": "no dije ciudad",
                "reason": "asumió Sevilla"}


def test_watchdog_parse_fails_open_on_garbage():
    v = watchdog.parse("not json at all")
    assert v["health"] == "flowing"
    assert v["action"] == "continue"


def test_watchdog_parse_fails_open_on_invalid_vocabulary():
    v = watchdog.parse('{"health":"confused","action":"panic","reason":"?"}')
    assert v["health"] == "flowing"
    assert v["action"] == "continue"


def test_watchdog_parse_strips_markdown_fence():
    out = '```json\n{"health":"flowing","action":"continue","reason":"ok"}\n```'
    v = watchdog.parse(out)
    assert v["health"] == "flowing"


def test_families_in_extracts_distinct_categories():
    events = [{"cat": "worker"}, {"cat": "widget"}, {"cat": "worker"}, {"cat": None}, {}]
    assert verify.families_in(events) == {"worker", "widget"}


def test_find_navegador_task_id_from_flat_payload():
    events = [{"payload": {"id": "navegador::t42"}}]
    assert verify.find_navegador_task_id(events) == "t42"


def test_find_navegador_task_id_from_nested_extra():
    events = [{"payload": {"extra": {"id": "navegador::t7"}}}]
    assert verify.find_navegador_task_id(events) == "t7"


def test_find_navegador_task_id_from_json_string_payload():
    events = [{"payload": json.dumps({"id": "navegador::t9"})}]
    assert verify.find_navegador_task_id(events) == "t9"


def test_find_navegador_task_id_absent_when_no_match():
    events = [{"payload": {"id": "widget::agenda"}}, {"payload": {}}]
    assert verify.find_navegador_task_id(events) == ""


def test_mechanism_report_flags_missing_signals(monkeypatch):
    monkeypatch.setattr(verify, "poll_navegador_task", lambda *a, **k: {})
    events = [{"cat": "flash"}]
    report = verify.mechanism_report(events, ["worker", "widget"])
    assert report["families_observed"] == ["flash"]
    assert report["missing_signals"] == ["worker", "widget"]
    assert report["navegador_task_id"] == ""
