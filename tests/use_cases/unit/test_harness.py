"""Unit tests for the use-case harness's deterministic pieces (watchdog.parse, verify's extraction logic).
The harness drives an LLM and a live server, so it isn't itself deterministic — but its parsing/extraction
logic is, and is worth pinning down without a live zaelar or a real LLM call."""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import driver, scenarios, verify, watchdog


def _scenario():
    return scenarios.UseCaseScenario(
        id="unit-test", locale="es", tier=1, persona_brief="da igual", opening_line="hola",
        success_checks="da igual")


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


def test_driver_does_not_close_on_a_closing_word_that_is_still_a_question(monkeypatch):
    """Live bug (cheapest-monitor, 2026-08-17): 'Vale, perfecto. ¿Ya tienes algo?' ended the conversation
    after 2 turns — 'perfecto' matched the closing heuristic even though the driver was still actively
    waiting on an answer. A real goodbye never ends in a question."""
    monkeypatch.setattr(driver.llm, "call", lambda *a, **k: "Vale, perfecto. ¿Ya tienes algo?")
    d = driver.Driver(_scenario())
    d.opening()
    d.hears("Sigo con ello, dame un momento.")
    d.reply()
    assert d.done is False


def test_driver_closes_on_a_genuine_goodbye(monkeypatch):
    monkeypatch.setattr(driver.llm, "call", lambda *a, **k: "Perfecto, muchas gracias.")
    d = driver.Driver(_scenario())
    d.opening()
    d.hears("Ya está reservado.")
    d.reply()
    assert d.done is True


def test_driver_closes_on_a_bare_final_gracias(monkeypatch):
    monkeypatch.setattr(driver.llm, "call", lambda *a, **k: "Vale, genial, gracias.")
    d = driver.Driver(_scenario())
    d.opening()
    d.hears("Hecho.")
    d.reply()
    assert d.done is True


def test_driver_does_not_close_on_a_bare_perfecto_with_no_farewell(monkeypatch):
    """Live bug (search-buy-used-car, 2026-08-17): 'Perfecto, quedo a la espera.' ended a run at 3 turns —
    'perfecto' is an ordinary Spanish acknowledgment, not a goodbye, unless paired with an actual sign-off."""
    monkeypatch.setattr(driver.llm, "call", lambda *a, **k: "Perfecto, quedo a la espera.")
    d = driver.Driver(_scenario())
    d.opening()
    d.hears("Sigo con ello, dame un momento.")
    d.reply()
    assert d.done is False


def test_driver_does_not_close_on_gracias_in_the_middle_of_a_sentence(monkeypatch):
    monkeypatch.setattr(driver.llm, "call", lambda *a, **k: "Vale, gracias por avisar, sigo esperando entonces.")
    d = driver.Driver(_scenario())
    d.opening()
    d.hears("Sigo con ello.")
    d.reply()
    assert d.done is False


def test_watchdog_prompt_carries_the_mechanism_hint_when_given():
    """Live bug (search-buy-used-car, 2026-08-17): the watchdog abandoned a scenario after just 3 turns —
    'zaelar keeps saying it's still searching' — while the mechanism report (checked after the fact) showed
    a real navegador task genuinely navigating (status=working, a real Wallapop search URL). A real
    vision-based browser search legitimately takes minutes; the watchdog needs the same system-truth
    grounding the final verdict already gets, not just the conversational transcript."""
    msgs = watchdog.build_messages(_scenario(), [{"who": "tester", "text": "hola"}],
                                   mechanism_hint="status=working, shot_rev=7, url=https://example.com")
    user_content = msgs[1]["content"]
    assert "status=working" in user_content
    assert "MECANISMO EN VIVO" in user_content


def test_watchdog_prompt_omits_mechanism_block_when_no_hint():
    msgs = watchdog.build_messages(_scenario(), [{"who": "tester", "text": "hola"}])
    assert "[MECANISMO EN VIVO]" not in msgs[1]["content"]


def test_live_navegador_snapshot_fails_open_to_empty_string(monkeypatch):
    monkeypatch.setattr(verify.probe_client, "current_session_id", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert verify.live_navegador_snapshot(0.0) == ""


def test_live_navegador_snapshot_empty_when_no_navegador_task(monkeypatch):
    monkeypatch.setattr(verify.probe_client, "current_session_id", lambda: "sid1")
    monkeypatch.setattr(verify.probe_client, "session_events", lambda *a, **k: [])
    assert verify.live_navegador_snapshot(0.0) == ""


def test_live_navegador_snapshot_reports_status_and_shot_rev(monkeypatch):
    monkeypatch.setattr(verify.probe_client, "current_session_id", lambda: "sid1")
    monkeypatch.setattr(verify.probe_client, "session_events",
                        lambda *a, **k: [{"payload": {"id": "navegador::t9"}, "ts_ms": 1}])
    monkeypatch.setattr(verify.probe_client, "navegador_task",
                        lambda tid: {"status": "working", "shot_rev": 3, "url": "https://x.test"})
    snap = verify.live_navegador_snapshot(0.0)
    assert "status=working" in snap
    assert "shot_rev=3" in snap
    assert "https://x.test" in snap
