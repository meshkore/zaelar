"""The SHARED results sheet belongs to one errand at a time: a browser push that names its errand but no sheet takes
the shared sheet over instead of appending onto another errand's rows (V2-831 T-01, node 4.323).

2026-10-28: a streaming-offer errand's browser findings were pushed with no sheet and appended under six school-
canteen rows an earlier web search had left on the shared sheet. `intake.push(errand=…)` is the seam; the producers
that know the errand (`nucleo/dispatch/prepare.py`, `widgets/navegador/owner_actions.py`) pass it.
"""
from __future__ import annotations

from widgets.results import data as sheet, intake

OLD = [{"title": "Comedores Escolares - Educacyl", "url": "https://www.educa.jcyl.es/"}]
NEW = [{"title": "SkyShowtime", "price": "6,99€", "url": "https://www.skyshowtime.com/es"}]


def _titles():
    return [it["title"] for it in sheet.view_data("")["items"]]


def test_an_errand_push_replaces_rows_it_does_not_own_and_then_accumulates_its_own():
    sheet.apply_action("present", {"items": OLD, "sources": [{"name": "web search"}]})
    assert intake.push(NEW, errand="task-7") == 1
    assert _titles() == ["SkyShowtime"]
    assert [s["name"] for s in sheet.view_data("")["sources"]] == [], "the old errand's sources went with its rows"
    intake.push([{"title": "Max", "price": "9,99 €", "url": "https://max.com"}], errand="task-7")
    assert _titles() == ["SkyShowtime", "Max"]
    intake.push([{"title": "Filmin", "url": "https://filmin.es"}], errand="task-8")
    assert _titles() == ["Filmin"]


def test_a_push_with_no_errand_still_accumulates_and_an_errand_sheet_is_untouched():
    sheet.apply_action("present", {"items": OLD})
    intake.push(NEW)                                                 # the operator browsing by hand
    assert _titles() == [OLD[0]["title"], "SkyShowtime"]
    sheet.apply_action("present", {"sheet": "own-1", "items": OLD})
    intake.push(NEW, sheet="own-1", errand="task-9")
    assert [it["title"] for it in sheet.view_data("own-1")["items"]] == [OLD[0]["title"], "SkyShowtime"]


def test_a_present_keeps_the_owner():
    intake.push(NEW, errand="task-3")
    sheet.apply_action("present", {"items": NEW + [{"title": "Max", "url": "https://max.com"}]})
    intake.push([{"title": "Filmin", "url": "https://filmin.es"}], errand="task-3")
    assert _titles() == ["SkyShowtime", "Max", "Filmin"]


# ── V2-831 audit A6: the owner is stated by EVERY producer, not remembered by two of four ─────────────────────────────
def test_a_workers_search_takes_the_shared_sheet_for_its_errand_too():
    """The worker's web-search path (`findings.hand_search_rows`) pushed with no errand: its rows appended under
    another errand's. Now it names its errand like the browser producers."""
    from types import SimpleNamespace

    from nucleo.workers import findings
    sheet.apply_action("present", {"items": OLD})
    rec = SimpleNamespace(task_id="w-12", sheet="")
    res = {"query": "flats to rent in Valencia", "source": "web",
           "results": [{"title": "Piso en Ruzafa", "url": "https://example.com/ruzafa", "snippet": "3 hab"}]}
    assert findings.hand_search_rows(rec, res) >= 1
    assert OLD[0]["title"] not in _titles() and "Piso en Ruzafa" in _titles()


def test_every_producer_states_the_sheet_and_the_errand():
    """A door whose ownership depends on a keyword each caller must remember is not a door: every product call to
    `intake.push` states `sheet=` AND `errand=` (`errand=""` is the explicit «a browser he drives by hand»)."""
    import ast
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=root, capture_output=True, text=True).stdout.split()
    calls, missing = 0, []
    for rel in files:
        if rel.startswith("tests/") or "/tests/" in rel or rel == "widgets/results/intake.py":
            continue
        src = (root / rel).read_text(encoding="utf-8")
        if "push(" not in src or "intake" not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            f = getattr(node, "func", None)
            if isinstance(node, ast.Call) and isinstance(f, ast.Attribute) and f.attr == "push" \
                    and isinstance(f.value, ast.Name) and f.value.id.lstrip("_") == "intake":
                calls += 1
                kws = {k.arg for k in node.keywords}
                if not {"sheet", "errand"} <= kws:
                    missing.append(f"{rel}:{node.lineno}")
    assert calls >= 4, f"the producers were not found ({calls}) — the guard is looking at the wrong thing"
    assert not missing, f"a producer leaves the sheet's owner to chance: {missing}"
