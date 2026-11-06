"""THE BRAIN screen: one turn of one round through the turn pipeline — a FIXED picture of the stations
(zaelar-architecture.md §5i, §5h) and, for that turn, the ones the signal crossed lit in order with the state each
carried, read from the sandbox's `events` table by the turn's corr_id. The dark stations that SHOULD have fired are
the point: the model called an escalation and no Brain Worker was born → the router, the worker and the circuit
are dark with that reason, decided from the turn's own evidence (the model's tool calls, `turn_actions`), never
from prose.

What would rot: a station lit by an event that belongs to another station; a turn matched to the wrong flow; an
«expected» that fires on a plain chat turn; a sandbox DB opened for writing.
"""
from __future__ import annotations

from tests.platform import observatory_data as od
from tests.platform.tests.observatory_fixture import (  # noqa: F401 — fixtures
    SANDBOX, dashboard_sources, get, observatory, runs_root, write_round, write_sandbox,
)

ARCHITECTURE = od.ENGINE / ".meshkore" / "docs" / "architecture" / "zaelar-architecture.md"


def test_the_picture_is_fixed_and_follows_the_turn_pipeline_of_the_architecture() -> None:
    """Twelve stations, in pipeline order, each naming its module; the doc that defines the pipeline names those
    modules. Rename a stage in the architecture and this says which station fell out of the picture."""
    ids = [s["id"] for s in od.STATIONS]
    assert ids == ["gate", "brief", "memory", "prompt", "route", "model", "tools", "consent", "circuit", "worker", "notices", "mouth"]
    doc = ARCHITECTURE.read_text(encoding="utf-8") if ARCHITECTURE.exists() else ""
    if doc:
        for needle in ("pipeline_gate", "brief", "flow_of.route", "pipeline_stream", "consent", "circuit", "notices", "mouth"):
            assert needle in doc, f"the architecture no longer names {needle}; the station list must follow it"


def test_a_turn_lights_the_stations_it_crossed_in_order_with_the_state_each_carried(observatory) -> None:
    _, root, url = observatory
    write_round(root)
    write_sandbox(root)
    d = get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=0")
    assert d["readable"] and d["corr_id"] == "T1·64a8" and d["matched_by"] == "text"
    st = {s["id"]: s for s in d["stations"]}
    assert d["order"][:2] == ["gate", "consent"] and d["order"][-1] == "mouth"
    assert set(d["order"]) == {"gate", "consent", "prompt", "memory", "brief", "model", "tools", "mouth"}
    assert {kv["k"]: kv["v"] for kv in st["brief"]["state"]}["escalate_or_inline"] == "escalate -> USED (0.91)"
    model = {kv["k"]: kv["v"] for kv in st["model"]["state"]}
    assert model["model"].startswith("deepseek-flash") and model["finish"] == "tool_calls"
    assert "escalate_to_slowbrain" in model["tool call"]
    assert {kv["k"] for kv in st["consent"]["state"]} == {"door · tasks.intake"}
    assert any("results::abc-1" in kv["k"] for kv in st["tools"]["state"])
    assert st["mouth"]["state"][0]["v"] == "Voy a ello, te los busco ya."
    assert st["gate"]["first_ms"] == 0 and st["model"]["first_ms"] == 9100
    assert d["strip"][0]["corr_id"] == "T1·64a8" and d["strip"][1]["corr_id"] == "T2·4e4d"


def test_the_dark_stations_that_should_have_fired_are_named_with_their_reason(observatory) -> None:
    """Turn 0: the model CALLED `escalate_to_slowbrain` (its own tool call) and the harness read the turn as
    `escalate` — no router, no worker, no circuit event followed. Those three are dark AND expected, each with the
    check that expected it. Turn 1 is a plain answer: nothing is expected dark."""
    _, root, url = observatory
    write_round(root)
    write_sandbox(root)
    d = get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=0")
    dark = {s["id"]: s for s in d["stations"] if s["expected"]}
    assert set(dark) == {"route", "worker", "circuit"}, set(dark)
    assert not dark["worker"]["lit"] and any("no Brain Worker" in w for w in dark["worker"]["why"])
    assert any("escalate" in w for w in dark["route"]["why"])
    assert d["turn_action"]["action"] == "escalate"
    d1 = get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=1")
    assert d1["readable"] and not [s for s in d1["stations"] if s["expected"]]
    assert set(d1["order"]) == {"gate", "prompt", "brief", "model", "mouth"}


def test_a_turn_with_no_trace_or_no_db_is_said_not_painted(observatory) -> None:
    _, root, url = observatory
    write_round(root)
    write_sandbox(root)
    d2 = get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=2")
    assert d2["readable"] is False and d2["matched_by"] == "none" and "no root trace" in d2["why"]
    assert d2["heard"] == "Vale, gracias, con eso me apaño." and d2["said"] == ""
    assert get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=9")["readable"] is False
    import shutil
    shutil.rmtree(root / "use_cases" / "sandbox" / SANDBOX / "memory")
    od._CACHE.clear()
    d0 = get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=0")
    assert d0["readable"] is False and "no kept sandbox" in d0["why"]


def test_the_sandbox_db_is_opened_read_only_and_the_raw_flow_is_a_link_out(observatory) -> None:
    """The screen never writes the agent's DB and never repaints its trace: the raw flow is the engine's own
    observability API, linked when the sandbox is up."""
    _, root, url = observatory
    write_round(root)
    ws = write_sandbox(root)
    db = ws / "memory" / "_data" / "sandbox.db"
    before = db.stat().st_mtime_ns
    d = get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=0")
    assert db.stat().st_mtime_ns == before
    assert d["links"]["db"] == str(db)
    assert d["n_events"] == 11 and all(len(s["events"]) <= 8 for s in d["stations"])
    src = dashboard_sources()["brain.js"]
    assert "api/observability/flow" in src or "flow_api" in src
    for word in ("anthropic", "openai", "completions"):
        assert word not in src.lower()


def test_a_round_that_names_its_turns_is_opened_by_their_corr_id_not_by_their_text(observatory) -> None:
    """Since V2-856 the harness writes each turn's corr_id on its transcript rows: the screen opens the turn by that
    id even when the text would match nothing (the driver trimmed it), and the round's own workspace, not the
    newest one by time."""
    _, root, url = observatory
    p = write_round(root, emitted=True)
    write_sandbox(root)
    import json
    data = json.loads(p.read_text(encoding="utf-8"))
    data["results"][0]["run"]["transcript"][2]["text"] = "a line the trace never carried"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    d = get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=1")
    assert d["readable"] and d["corr_id"] == "T2·4e4d" and d["matched_by"] == "emitted"
    assert [s["matched_by"] for s in d["strip"]][:2] == ["emitted", "emitted"]


def test_a_round_whose_workspace_was_pruned_is_never_given_another_one(observatory, tmp_path) -> None:
    _, root, url = observatory
    p = write_round(root, emitted=True)
    write_sandbox(root, name="20261102-115000-es")     # a newer-by-time sandbox that is NOT the round's
    import json
    data = json.loads(p.read_text(encoding="utf-8"))
    data["results"][0]["run"]["workspace"] = str(tmp_path / "gone")
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    d = get(f"{url}/api/turn?file=report_20261102-120419.json&idx=0&turn=0")
    assert d["readable"] is False and "pruned" in d["why"]

