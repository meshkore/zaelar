"""The Observatory's HOME is numbers only (operator, 2026-11-06): three boxes — unit, benches, use cases ES|US by
theme — and one line of notice when somebody is testing, which opens the live screen. The tables (scoreboard,
sandboxes, rounds) have tabs of their own; the live run has a route of its own.

The numbers are computed by the server (`observatory_data.home`), never by the page, and each one has a
denominator that would rot silently if invented: the use-case total is the CATALOG's `completable` segment (not
the ledger's row count, not one evening's batch), the state of a case is its ACCUMULATED ledger row (the last
batch's report said «INFRA 13 of 13» the night the engine was down — that is the bug this screen replaces), a bench
with no run file or no criterion says so instead of wearing a colour.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from tests.platform.tests.observatory_fixture import (  # noqa: F401 — fixtures
    dashboard_sources, get, observatory, runs_root, sweep_result, write_run, write_watchdog,
)
from tests.use_cases import themes
from tests.use_cases.catalog import case_groups
from tests.use_cases.e2e.agent import segments


def _catalog() -> dict[str, set[str]]:
    """bare id → the locales the catalog declares it in."""
    out: dict[str, set[str]] = {}
    for g in case_groups():
        for c in g["cases"]:
            out.setdefault(c["id"].split("::")[-1], set()).add(c.get("locale") or "")
    return out


def _ledger(root: Path, rows: dict[str, str]) -> Path:
    """`status.json` beside the runs root with one row per `<scenario>: <state>`."""
    p = root.parent / "use_cases" / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"updated": "2026-11-06 17:00", "scenarios": {
        sid: {"last_run": "2026-11-06 16:00", "overall": 4 if st == "PASS" else 2, "state": st, "tier": 1,
              "scores": {}, "verdict": "", "code": {"sha": "0000000", "n_dirty": 0}, "rounds": []}
        for sid, st in rows.items()}}), encoding="utf-8")
    return p


def test_use_case_numbers_count_the_completable_catalog_against_the_accumulated_ledger_per_language_and_theme(observatory) -> None:
    """The denominator is the catalog's `completable` segment per language; the numerators are ledger states; a
    case with no row is `never`; the credentials and capability cases are counted APART; a ledger row for a case
    the catalog no longer has counts nothing; the theme rows sum to the language total (no case lost)."""
    _, root, url = observatory
    cat = _catalog()
    completable = {b for b, locs in cat.items() if segments.is_completable(b)}
    both = sorted(b for b in completable if cat[b] == {"es", "us"})
    a, b = both[0], both[1]
    cred = next(x for x, locs in cat.items() if segments.group_of(x) == segments.CREDENTIALS and "es" in locs)
    _ledger(root, {f"{a}__es": "PASS", f"{a}__us": "FAIL", b: "INFRA",            # `b` bare = an old ES row
                   f"{cred}__es": "PASS",                                           # not completable: apart
                   "a-case-the-catalog-forgot__es": "PASS"})                         # not in the catalog: nothing
    u = get(f"{url}/api/home")["use_cases"]
    es, us = u["locales"]["es"], u["locales"]["us"]
    n_es = sum(1 for x in completable if "es" in cat[x])
    n_us = sum(1 for x in completable if "us" in cat[x])
    assert (es["total"], es["PASS"], es["FAIL"], es["INFRA"], es["never"]) == (n_es, 1, 0, 1, n_es - 2)
    assert (us["total"], us["PASS"], us["FAIL"], us["INFRA"], us["never"]) == (n_us, 0, 1, 0, n_us - 1)
    assert es["excluded"]["credentials"] == sum(1 for x, l in cat.items() if segments.group_of(x) == segments.CREDENTIALS and "es" in l)
    assert es["excluded"]["capability"] == sum(1 for x, l in cat.items() if segments.group_of(x) == segments.CAPABILITY and "es" in l)
    assert u["segment"] == segments.COMPLETABLE and u["updated"] == "2026-11-06 17:00"
    rows = {t["id"]: t for t in u["themes"]}
    assert 5 <= len(rows) <= 15, "a list the operator can read: between five and fifteen themes"
    assert list(rows) == [t["id"] for t in themes.THEMES if t["id"] in rows], "the table's order, not the dict's"
    assert sum(t["es"]["total"] for t in rows.values()) == n_es and sum(t["us"]["total"] for t in rows.values()) == n_us
    assert rows[themes.theme_of(a)]["es"]["PASS"] >= 1 and rows[themes.theme_of(a)]["us"]["FAIL"] >= 1
    assert rows[themes.theme_of(b)]["es"]["INFRA"] >= 1
    assert "otros" not in rows, "an unclassified case is a catalog defect the use-case ratchet fails on, not a row here"


def test_unit_numbers_are_the_last_sweep_s_totals_with_the_hung_counted_apart(observatory) -> None:
    _, root, url = observatory
    write_watchdog(root, "20261105-200000", [sweep_result("tests/voice/unit", passed=100)])
    write_watchdog(root, "20261105-225701", [
        sweep_result("tests/voice/unit", passed=99, failed=1, verdict="failed", failures=["tests/voice/unit/test_a.py::test_x"]),
        sweep_result("tests/memory/unit", passed=40, verdict="hung", hung_at="tests/memory/unit/test_b.py::test_y")])
    u = get(f"{url}/api/home")["unit"]
    assert u["last"]["file"] == "watchdog-20261105-225701.json" and u["last"]["verdict"] == "hung"
    assert (u["total"], u["passed"], u["failed"], u["hung"], u["reds"]) == (140, 139, 1, 1, 1)


def test_bench_numbers_say_no_run_or_no_threshold_rather_than_invent_a_colour(observatory) -> None:
    """A bench is green or red only by the criterion its own file carries (every site over its floor, every step
    ok); a score with no threshold (search) is `no_threshold`; a bench that leaves no file is `no_run`."""
    _, root, url = observatory
    b = get(f"{url}/api/home")["benches"]
    assert b["n"] == len(get(f"{url}/api/sets/benches")["benches"]) and b["with_run"] == 0 and b["no_run"] == b["n"]
    (root / "scrape-bench-20261104-160430.json").write_text(json.dumps({"at": "x", "rows": [
        {"site": "idealista", "met": True, "n": 12, "floor": 10}, {"site": "wallapop", "met": False, "n": 3, "floor": 10}]}))
    (root / "connectors-bench-20261106-135840.json").write_text(json.dumps({"at": "x", "sent": False, "rows": [
        {"platform": "email", "step": "fetch", "ok": True}, {"platform": "telegram", "step": "fetch", "ok": True}]}))
    (root / "search-bench-20261104-081142.json").write_text(json.dumps({"at": "x", "rows": [], "summary": {"gemini": {"score": 0.8}}}))
    b = get(f"{url}/api/home")["benches"]
    by = {r["id"]: r["verdict"] for r in b["rows"]}
    assert by["scrape"] == "red" and by["connectors"] == "green" and by["search"] == "no_threshold" and by["memory"] == "no_run"
    assert (b["with_run"], b["green"], b["red"], b["no_threshold"], b["no_run"]) == (3, 1, 1, 1, b["n"] - 3)


def test_the_home_paints_numbers_only_and_the_live_run_is_its_own_route(observatory) -> None:
    """The page: the home module reads `/api/home` and none of the tables' endpoints; its only link into a run is the
    notice to `#/live`; the bar has at most four tabs; `#/live` and `#/run/<id>` mount the live screen. The server:
    `/api/home` carries the live agents so the notice needs no second call."""
    src = dashboard_sources()
    home = src["home.js"]
    assert '"/api/home"' in home
    for table in ("/api/sandboxes", "/api/scoreboard", "/api/rounds", "/api/results", "/api/running", "/api/sets/"):
        assert table not in home, f"the home paints {table}: that is a tab's job, not the home's"
    assert 'href="#/live"' in home and "runcard" not in home, "the home has a notice line, not the run cards"
    index = src["index.html"]
    tabs = re.findall(r'data-route="([a-z]+)"', index)
    assert 3 <= len(tabs) <= 4, tabs
    assert 'head === "live"' in index and "function mountLive" in index
    assert 'else if (head === "run") unmount = mountLive(view, parts[1] || "");' in index
    assert 'head === "scoreboard"' in index and 'head === "sandboxes"' in index
    assert "mountScoreboard" in src["board.js"] and "mountSandboxes" in src["board.js"]

    _, root, url = observatory
    write_run(root, "20261106-100000-browser-aaaaaa", status="running", actor="agent-a", suite="browser", lines=[
        {"type": "test.discovered", "ts": time.time(), "test_id": "t1", "index": 1, "total": 1},
        {"type": "test.started", "ts": time.time(), "test_id": "t1", "label": "one"}])
    d = get(f"{url}/api/home")
    assert set(d) >= {"unit", "benches", "use_cases", "live"}
    assert [r["actor"] for r in d["live"]] == ["agent-a"] and d["live"][0]["run_id"] == "20261106-100000-browser-aaaaaa"
