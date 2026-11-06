"""The Observatory's HOME is a dashboard, not a catalog tree (operator, 2026-11-06): who is testing right now, how
every set went last time, the scoreboard, the sandboxes — read from the files the runners leave, nothing launched.

Ratchets, not descriptions: each pins a reading that would rot silently. A progress that counts events instead of
tests reads «7473 / 1»; a trend that forgets the previous sweep says nothing; a sandbox whose port is guessed from
its folder name points at the wrong agent; a launch button on a spectator surface is a second way to start a run
nobody is reading the exit code of.
"""
from __future__ import annotations

import time

from tests.platform import ports
from tests.platform.tests.observatory_fixture import (  # noqa: F401 — fixtures
    T0, SANDBOX, dashboard_sources, get, get_text, observatory, runs_root, sweep_result, write_ledger, write_round,
    write_run, write_sandbox, write_watchdog,
)


def test_running_now_reads_progress_and_the_case_in_flight_from_the_live_runs_only(observatory) -> None:
    """One row per LIVE run, with the denominator from `test.discovered`, the count from `test.finished`, the case
    in flight from the last `test.started` and the reds by name. A stale run (events stopped) and a finished one
    are not «running now», whatever `run.json` says."""
    _, root, url = observatory
    now = time.time()
    write_run(root, "20261106-100000-browser-aaaaaa", status="running", actor="agent-a", suite="browser", lines=[
        {"type": "test.discovered", "ts": now, "test_id": "t1", "index": 1, "total": 3},
        {"type": "test.discovered", "ts": now, "test_id": "t2", "index": 2, "total": 3},
        {"type": "test.discovered", "ts": now, "test_id": "t3", "index": 3, "total": 3},
        {"type": "collection.finished", "ts": now, "total": 3},
        {"type": "test.started", "ts": now, "test_id": "t1", "label": "one"},
        {"type": "test.finished", "ts": now, "test_id": "t1", "label": "one", "status": "passed"},
        {"type": "test.started", "ts": now, "test_id": "t2", "label": "two"},
        {"type": "test.finished", "ts": now, "test_id": "t2", "label": "two", "status": "failed"},
        {"type": "test.started", "ts": now, "test_id": "t3", "label": "three"},
        {"type": "step.started", "ts": now, "test_id": "t3", "step": "turns", "label": "conversación con el agente"},
        {"type": "interaction.input", "ts": now, "test_id": "t3", "who": "tester", "turn": 1, "input": {"text": "hola"}},
    ])
    write_run(root, "20261106-090000-voice-bbbbbb", status="running", actor="agent-b", suite="voice", age_s=3600)
    write_run(root, "20261106-080000-memory-cccccc", status="passed", actor="agent-b", suite="memory")

    rows = get(f"{url}/api/running")["running"]
    assert [r["actor"] for r in rows] == ["agent-a"]
    row = rows[0]
    assert (row["total"], row["done"], row["passed"], row["failed"]) == (3, 2, 1, 1)
    assert row["current"]["label"] == "three" and row["current"]["step"] == "conversación con el agente"
    assert row["current"]["turn"] == 1
    assert row["reds"] == ["two"]


def test_sandboxes_are_read_from_the_kept_workspaces_with_the_locale_s_fixed_port(observatory) -> None:
    """A workspace is `<stamp>-<lang>`; the port comes from `tests/platform/ports.py`, never from the folder — one
    fixed port per locale is the registry's whole point. `en` is the US set. A folder with only `config/` never
    booted and must say so (`has_db: false`), not read as a kept round."""
    _, root, url = observatory
    write_sandbox(root, "20261104-131310-es")
    write_sandbox(root, "20261104-131309-en", with_db=False)
    rows = {r["name"]: r for r in get(f"{url}/api/sandboxes")["sandboxes"]}
    es, us = rows["20261104-131310-es"], rows["20261104-131309-en"]
    assert es["locale"] == "es" and es["port"] == ports.sandbox_port("es") and es["has_db"] is True
    assert us["locale"] == "us" and us["port"] == ports.sandbox_port("us") and us["has_db"] is False
    assert isinstance(es["alive"], bool) and es["kind"] == "sandbox"
    assert es["stamp"] == time.mktime(time.strptime("20261104131310", "%Y%m%d%H%M%S"))


def test_last_result_per_set_names_the_reds_and_compares_with_the_previous_run(observatory) -> None:
    """The unit sweep from `watchdog-*.json` (newest, with the reds by node and the trend against the sweep before),
    the use cases per locale from the round files (states counted, the FAILs linked to their round)."""
    _, root, url = observatory
    write_watchdog(root, "20261105-200000", [sweep_result("tests/voice/unit", passed=100)])
    write_watchdog(root, "20261105-225701", [
        sweep_result("tests/voice/unit", passed=99, failed=1, verdict="failed",
                     failures=["tests/voice/unit/test_attention.py::test_mode_default_is_always"]),
        sweep_result("tests/memory/unit", passed=40)])
    write_round(root)
    write_ledger(root)
    d = get(f"{url}/api/results")
    unit = d["unit"]
    assert unit["last"]["file"] == "watchdog-20261105-225701.json" and unit["last"]["verdict"] == "failed"
    assert unit["last"]["counts"] == {"passed": 139, "failed": 1}
    assert unit["last"]["reds"] == ["tests/voice/unit/test_attention.py::test_mode_default_is_always"]
    assert unit["trend"]["reds"] == 1 and unit["prev"]["file"] == "watchdog-20261105-200000.json"
    assert "by_target" not in unit, "the home payload must stay small — the per-folder map is the sets screen's"
    es = d["use_cases"]["es"]
    assert es["source"] == "reports" and es["states"] == {"FAIL": 1}
    assert es["reds"][0]["scenario"] == "search-monitors-under-400" and es["reds"][0]["file"] == "report_20261102-120419.json"
    # no US round FILE on disk: the card falls back to the LEDGER (the verdicts outlive the pruned files) and says so
    assert d["use_cases"]["us"]["source"] == "ledger" and d["use_cases"]["us"]["states"] == {"PASS": 1}
    assert d["scoreboard"]["n"] == 2 and d["scoreboard"]["by_state"] == {"FAIL": 1, "PASS": 1}


def test_the_scoreboard_reads_the_ledger_beside_the_runs_root(observatory) -> None:
    """`status.json` is gitignored: a server started from a worktree against the main checkout's runs must read the
    main checkout's ledger, found beside the runs root — not an empty file in its own tree."""
    _, root, url = observatory
    write_ledger(root)
    sb = get(f"{url}/api/scoreboard")
    assert sb["n"] == 2
    cells = {(c["tier"], c["locale"]): c for c in sb["cells"]}
    assert cells[(2, "es")]["FAIL"] == 1 and cells[(2, "us")]["PASS"] == 1
    row = sb["rows"]["search-monitors-under-400"]
    assert row["kk"]["n"] == 2 and row["kk"]["settled"] == "UNSETTLED"      # two rounds agree, K is three


def test_nothing_on_any_screen_launches_a_run() -> None:
    """V2-709, extended to the ES modules: no launch endpoint is called, nothing POSTs, no play button — the
    agents drive the tests. The old test reads `index.html` only; the screens now live in modules too."""
    for name, src in dashboard_sources().items():
        assert '"/api/run"' not in src, name
        assert 'method: "POST"' not in src and "method:'POST'" not in src, name
        assert 'class="go"' not in src, name
    index = dashboard_sources()["index.html"]
    for module in ("home.js", "sets.js", "judge.js", "brain.js", "board.js"):
        assert f"./dashboard/{module}" in index, f"the shell does not load {module}"


def test_the_shell_serves_only_its_own_modules_and_files_under_the_runs_root(observatory) -> None:
    """Two static doors were added: `/dashboard/<module>` and `/runs/<file>`. Each is a name or a path INSIDE one
    folder; a traversal reads nothing (the same guard `?run=` keeps)."""
    _, root, url = observatory
    write_watchdog(root, "20261105-225701", [sweep_result("tests/voice/unit")])
    assert "export" in get_text(f"{url}/dashboard/lib.js")
    assert get(f"{url}/runs/watchdog-20261105-225701.json")["totals"]["passed"] == 10
    import urllib.error
    for hostile in ("/dashboard/../server.py", "/dashboard/..%2Fserver.py", "/runs/../../etc/passwd", "/runs/%2e%2e/x"):
        try:
            get_text(url + hostile)
        except urllib.error.HTTPError as err:
            assert err.code == 404, hostile
        else:
            raise AssertionError(f"served {hostile}")
