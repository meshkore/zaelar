"""The TEST SETS screen browses the three layers (V2-856) — unit · module benches · use cases — and keeps the spine
language → family → theme. Three readings that would rot:

  · a unit folder's «last sweep» must be found whether the watchdog swept the FOLDER or, with `--impacted`, only
    some FILES in it — the targets in `watchdog-*.json` are either;
  · the bench table on screen is the table in `tests/README.md` §Module benches — pinned, or the README and the
    screen drift apart with nobody noticing;
  · a use case's verdict comes from the ledger row of ITS locale, and the two locales are different sets.
"""
from __future__ import annotations

import re

from tests.platform import observatory_data as od
from tests.platform.tests.observatory_fixture import (  # noqa: F401 — fixtures
    ENGINE, get, observatory, runs_root, sweep_result, write_ledger, write_round, write_watchdog,
)


def test_a_folder_s_last_sweep_is_found_by_folder_or_by_the_files_inside_it(observatory) -> None:
    _, root, url = observatory
    write_watchdog(root, "20261105-200000", [sweep_result("tests/voice/unit", passed=100, seconds=30)])
    write_watchdog(root, "20261105-225701", [
        sweep_result("tests/voice/unit/test_attention.py", passed=5, failed=1, verdict="failed", seconds=2,
                     failures=["tests/voice/unit/test_attention.py::test_mode_default_is_always"]),
        sweep_result("tests/memory", passed=40, seconds=20)])
    areas = {a["id"]: a for a in get(f"{url}/api/sets/unit")["areas"]}
    voice = next(f for f in areas["voice"]["folders"] if f["folder"] == "tests/voice/unit")
    # the NEWEST sweep that covered the folder — by one file — wins over the older whole-folder sweep
    assert voice["sweep"]["file"] == "watchdog-20261105-225701.json"
    assert voice["sweep"]["verdict"] == "failed" and voice["sweep"]["scope"] == "1 file(s)"
    assert voice["red_files"] == ["tests/voice/unit/test_attention.py"]
    mem = next(f for f in areas["memory"]["folders"] if f["folder"] == "tests/memory/unit")
    assert mem["sweep"]["scope"] == "parent" and mem["sweep"]["verdict"] == "ok"
    never = [f for a in areas.values() for f in a["folders"] if not f["sweep"]]
    assert never, "a folder no sweep covered must say so, not look green"
    assert all(f["suites"] for a in areas.values() for f in a["folders"]), "every folder names the suite(s) it serves"


def test_the_bench_table_is_the_readme_s_table() -> None:
    """Every module row of `tests/README.md` §Module benches is in `observatory_data.BENCHES`, by its module name,
    and nothing on screen claims a bench the README does not list (a run file pattern is screen-only detail)."""
    readme = (ENGINE / "tests" / "README.md").read_text(encoding="utf-8")
    section = readme.split("### Module benches", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| module") and not line.startswith("|---")]
    modules_in_readme = {re.sub(r"\s+", " ", line.split("|")[1].strip()) for line in rows}
    assert modules_in_readme, "the README lost its bench table"
    on_screen = {b["module"] for b in od.BENCHES}
    missing = modules_in_readme - on_screen
    assert not missing, f"benches in tests/README.md the screen does not list: {missing}"
    extra = on_screen - modules_in_readme
    assert extra <= {"turn brief (Jev)"}, f"benches on screen the README does not list: {extra}"


def test_a_bench_s_last_run_file_gives_its_numbers_and_trend(observatory) -> None:
    _, root, url = observatory
    import json
    (root / "scrape-bench-20261104-134843.json").write_text(json.dumps({"at": "2026-11-04 13:48", "rows": [
        {"site": "wallapop", "met": False, "n": 0, "floor": 20}, {"site": "coches.net", "met": True, "n": 33, "floor": 25}]}))
    (root / "scrape-bench-20261104-160430.json").write_text(json.dumps({"at": "2026-11-04 16:04", "rows": [
        {"site": "wallapop", "met": True, "n": 21, "floor": 20}, {"site": "coches.net", "met": True, "n": 33, "floor": 25}]}))
    b = next(x for x in get(f"{url}/api/sets/benches")["benches"] if x["id"] == "scrape")
    assert b["runs_on_disk"] == 2 and b["last"]["met"] == 2 and b["last"]["sites"] == 2
    assert b["trend"]["headline"] == 1
    assert b["last"]["file"] == "scrape-bench-20261104-160430.json"
    memory = next(x for x in get(f"{url}/api/sets/benches")["benches"] if x["id"] == "memory")
    assert memory["last"] is None and memory["runs_on_disk"] == 0     # no file: said, never faked


def test_use_cases_join_the_catalog_with_the_ledger_row_of_their_own_locale(observatory) -> None:
    """The catalog row (what we promise) carries the ledger verdict (how it went) of ITS locale: the ES row of a
    case and the US row of the same case are two different measurements. A catalog id with no ledger row has
    `verdict: null` — «never measured» is information."""
    _, root, url = observatory
    from tests.use_cases.cases_data import CASES
    es_case = next(c for c in CASES if c.locale == "es")
    write_ledger(root, es_case.id)
    d = get(f"{url}/api/sets/usecases")
    rows = [c for g in d["groups"] for c in g["cases"]]
    mine = {c["locale"]: c for c in rows if c["id"].endswith("::" + es_case.id)}
    assert mine["es"]["verdict"]["state"] == "FAIL" and mine["es"]["verdict"]["kk"]["n"] == 2
    if "us" in mine:
        assert mine["us"]["verdict"]["state"] == "PASS"
    assert sum(1 for c in rows if c["verdict"] is None) >= len(rows) - 2
    assert {c["locale"] for c in rows} <= {"es", "us"} and d["n"] == len(CASES)
    assert [t["id"] for t in d["themes"]], "the theme order is the rail's order"
