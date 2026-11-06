"""THE JUDGE VIEWER reads one use-case round as a verdict with its evidence — the hand-off card a developer needs,
the mechanism as a checklist, the conversation with the markers — from the round .json `report.py` writes and
the sandbox the round kept. Nothing is inferred by a model here: a missing signal is a row of the report, a false
claim is the turn `verify.market_claims_before_delivery` measured, the blocker is the judge's own line.

What would rot: a check that reads «ok» when the field it claims to read is absent; a finding the judge pinned to
a turn painted beside the wrong turn; a round handle that walks out of the runs folder.
"""
from __future__ import annotations

from tests.platform.tests.observatory_fixture import (  # noqa: F401 — fixtures
    SANDBOX, dashboard_sources, get, observatory, runs_root, write_ledger, write_round, write_sandbox,
)


def test_the_hand_off_card_carries_the_blocker_the_state_the_repro_and_the_sandbox(observatory) -> None:
    _, root, url = observatory
    write_round(root)
    write_ledger(root)
    write_sandbox(root)
    d = get(f"{url}/api/round?file=report_20261102-120419.json&idx=0")
    assert d["readable"] and d["scenario"] == "search-monitors-under-400" and d["locale"] == "es"
    assert d["blocker"].startswith("No listo para producción")
    assert d["state"] == "FAIL" and d["overall"] == 2 and d["scores"]["mecanismo"] == 1
    assert d["reproduce"] == "python -m tests.use_cases.e2e.agent.run --scenario search-monitors-under-400 --sandbox"
    assert d["code"]["sha"] == "41908d5cb" and d["machine"]["gpu_models"][0]["name"].startswith("local-model")
    assert d["sandbox"]["name"] == SANDBOX and d["sandbox"]["matched_by"] == "time" and d["sandbox"]["has_db"]
    assert d["sandbox"]["engine_url"].startswith("http://127.0.0.1:")
    assert d["settle"]["n"] == 2 and d["settle"]["settled"] == "UNSETTLED" and d["settle"]["ledger_sha"] == "41908d5cb"
    assert d["links"]["report_json"] == "use_cases/report_20261102-120419.json"
    assert d["links"]["report_md"] == "use_cases/report_20261102-120419.md"
    assert d["missing"], "what an older round does not carry is said on the screen, never painted as a hole"


def test_the_checklist_reads_each_expected_signal_with_what_was_measured_and_where(observatory) -> None:
    """One row per expected signal and per measured fact, each naming the field of the round .json that proves it.
    The fixture's round: the worker never ran (bad), the sheet opened and stayed empty (bad), the second reply
    named prices with no rows behind them (bad), the widget signal fired (ok), the language is the case's (ok)."""
    _, root, url = observatory
    write_round(root)
    checks = {c["id"]: c for c in get(f"{url}/api/round?file=report_20261102-120419.json&idx=0")["checks"]}
    assert checks["signal:worker"]["status"] == "bad" and checks["signal:worker"]["measured"] == "MISSING"
    assert checks["signal:widget"]["status"] == "ok"
    assert checks["sheet"]["status"] == "bad" and "none named" in checks["sheet"]["measured"]
    assert checks["timing"]["status"] == "bad" and "NEVER" in checks["timing"]["measured"]
    assert checks["claims"]["status"] == "bad" and "turn(s) 1" in checks["claims"]["measured"]
    assert checks["lang"]["status"] == "ok" and checks["lang"]["expected"] == "es"
    assert checks["audit"]["status"] == "ok"
    for c in checks.values():
        assert c["where"].startswith("mechanism_report."), c


def test_the_conversation_carries_the_markers_and_the_judge_s_notes_on_the_turns_they_cite(observatory) -> None:
    """Turns are numbered from 0 as the judge cites them (`zaelar@turn1`). The unbacked claim lands on turn 1, the
    judge's [alta] finding beside it; the mute turn is turn 2 and it is the first; the «mecanismo» finding has no
    turn and stays unanchored instead of landing somewhere."""
    _, root, url = observatory
    write_round(root)
    d = get(f"{url}/api/round?file=report_20261102-120419.json&idx=0")
    assert d["n_turns"] == 3 and d["first_claim"] == 1 and d["first_mute"] == 2
    zaelar = [t for t in d["turns"] if t["who"] == "zaelar"]
    assert [m["kind"] for m in zaelar[1]["markers"]] == ["claim"]
    assert [n["turno"] for n in zaelar[1]["notes"]] == ["zaelar@turn1"]
    assert [m["kind"] for m in zaelar[2]["markers"]] == ["mute"]
    assert zaelar[0]["action"] == "escalate" and zaelar[0]["asked"] == ["escalate_to_slowbrain"]
    assert zaelar[0]["widget_ops"] == ["results.show"]
    assert [f["turno"] for f in d["findings_unanchored"]] == ["mecanismo"]
    assert d["watchdog"][0]["action"] == "nudge"


def test_an_unjudged_round_is_readable_and_says_so(observatory) -> None:
    _, root, url = observatory
    write_round(root, judged=False)
    d = get(f"{url}/api/round?file=search-monitors-under-400-20261102-120419.json&idx=0")
    assert d["readable"] and d["pending"] is True and d["state"] == "PENDING" and d["blocker"] == ""
    assert d["checks"], "the mechanism is measured before the judge speaks — it is readable without a verdict"
    rounds = get(f"{url}/api/rounds")["rounds"]
    assert rounds[0]["pending"] is True and rounds[0]["dir"] == "pending"


def test_a_round_handle_is_a_basename_and_never_walks_out_of_the_runs_folder(observatory) -> None:
    _, root, url = observatory
    write_round(root)
    for hostile in ("../report_x.json", "..%2F..%2Fetc%2Fpasswd", "/etc/passwd", ".hidden.json", "report.txt"):
        d = get(f"{url}/api/round?file={hostile}&idx=0")
        assert d["readable"] is False, hostile
    assert get(f"{url}/api/round?file=report_20261102-120419.json&idx=7")["readable"] is False


def test_the_viewer_calls_no_model_and_links_out_for_the_raw_trace() -> None:
    """The brief's rule: no model calls here, ever; the raw trace lives in the agent's ◷ viewer."""
    src = dashboard_sources()["judge.js"]
    for word in ("anthropic", "openai", "deepseek", "completions", "/v1/messages"):
        assert word not in src.lower(), word
    assert "flow_api" in src and "the agent's viewer" in src and "report .md" in src
    assert "/api/round?" in src and "events.jsonl" not in src



def test_a_round_that_names_its_workspace_and_turns_says_so(observatory) -> None:
    """The emitted round (V2-856): the sandbox is the one it names, each turn carries its corr_id, and the two emits
    leave the screen's `missing` list."""
    _, root, url = observatory
    write_round(root, emitted=True)
    write_sandbox(root)
    d = get(f"{url}/api/round?file=report_20261102-120419.json&idx=0")
    assert d["sandbox"]["name"] == SANDBOX and d["sandbox"]["matched_by"] == "emitted"
    assert [t.get("corr_id") for t in d["turns"][:4]] == ["T1·64a8", "T1·64a8", "T2·4e4d", "T2·4e4d"]
    assert not any("workspace" in m or "corr_id" in m for m in d["missing"])
    assert [m for m in d["missing"] if "por_criterio" in m or "signal_evidence" in m] == d["missing"]


def test_each_score_carries_the_turns_that_decided_it(observatory) -> None:
    """`por_criterio` (V2-856): the judge names, per dimension, the turns behind the score and one line of why; the
    viewer puts that line on those turns. A round judged before the field shows its scores with no turns."""
    import json
    _, root, url = observatory
    p = write_round(root)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["results"][0]["verdict"]["por_criterio"] = {"resultado": {"turnos": ["zaelar@turn1"], "nota": "never delivered"}}
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    d = get(f"{url}/api/round?file=report_20261102-120419.json&idx=0")
    assert d["criteria"]["resultado"]["turns"] == [1] and d["criteria"]["resultado"]["note"] == "never delivered"
    assert all(c["turns"] == [] for k, c in d["criteria"].items() if k != "resultado")
    on_turn_1 = [n for t in d["turns"] if t["turn"] == 1 and t["who"] != "tester" for n in t.get("notes", [])]
    assert any(n["gravedad"] == "criterio" and "never delivered" in n["problema"] for n in on_turn_1)


def test_a_named_workspace_outside_the_runs_root_is_still_the_round_s_own(observatory, tmp_path) -> None:
    """A lab of another checkout lives outside this runs root: the round names it, so it is opened, never swapped."""
    import json
    _, root, url = observatory
    p = write_round(root, emitted=True)
    ws = tmp_path / "elsewhere" / "20261106-090000-us"
    (ws / "memory" / "_data").mkdir(parents=True)
    (ws / "memory" / "_data" / "sandbox.db").write_bytes(b"")
    write_sandbox(root)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["results"][0]["run"]["workspace"] = str(ws)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    d = get(f"{url}/api/round?file=report_20261102-120419.json&idx=0")
    assert d["sandbox"]["path"] == str(ws) and d["sandbox"]["matched_by"] == "emitted" and d["sandbox"]["has_db"]

