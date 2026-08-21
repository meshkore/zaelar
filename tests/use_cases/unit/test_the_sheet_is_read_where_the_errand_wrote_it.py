"""A reader pointed at the wrong box does not fail — it invents facts.

Measured on `two-searches-two-sheets` (2026-08-21), the first round after V2-259 landed: the errand wrote to
`results::1` / `results::2` and `results_sheet()` read the bare `results`, which by then was a DIFFERENT box
holding fifteen leftover rows of hotels and cars from earlier rounds. The judge read that and concluded the
agent "claims to have found plumbers with no mechanism backing it" — a finding that looks exactly as credible
as a real one, filed against an agent that had done nothing wrong.

The ids come from `sheet_instances`, so the two readers cannot point at different boxes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.use_cases.e2e.agent import verify  # noqa: E402


def _fake(monkeypatch, boxes: dict):
    """`boxes` maps the QUERY SUFFIX to the payload — the shape the widget route really takes."""
    seen: list[tuple[str, str]] = []

    def _read(wid, q=""):
        seen.append((wid, q))
        return boxes.get(q)

    monkeypatch.setattr(verify.probe_client, "widget_data", _read)
    return seen


def test_each_instance_is_read_with_its_own_suffix(monkeypatch):
    seen = _fake(monkeypatch, {"1": {"items": [{"title": "Fontanero A"}], "title": "fontanero"},
                               "2": {"items": [{"title": "Coche B"}], "title": "coche"}})
    r = verify.results_sheet(["results::1", "results::2"])
    assert seen == [("results", "1"), ("results", "2")]
    assert r["n_items"] == 2 and r["n_named"] == 2
    assert [b["id"] for b in r["per_box"]] == ["results::1", "results::2"]


def test_the_bare_box_is_NOT_read_when_instances_exist(monkeypatch):
    """The whole point. The bare box survives across rounds and is nobody's errand after V2-259 — reading it
    alongside the instances would fold somebody else's leftovers into this errand's count."""
    seen = _fake(monkeypatch, {"1": {"items": [{"title": "Fontanero A"}]},
                               "": {"items": [{"title": "Hotel de otra ronda"}] * 15}})
    r = verify.results_sheet(["results::1"])
    assert ("results", "") not in seen
    assert r["n_items"] == 1 and "Hotel de otra ronda" not in (r["titles"] or [])


def test_with_no_instances_it_falls_back_to_the_bare_box(monkeypatch):
    """An engine from before V2-259, or a round where no sheet was opened: then the bare box IS the only one,
    and refusing to read it would report an empty sheet that is not empty."""
    seen = _fake(monkeypatch, {"": {"items": [{"title": "Algo"}]}})
    r = verify.results_sheet(None)
    assert seen == [("results", "")]
    assert r["read"] is True and r["n_items"] == 1


def test_a_non_results_instance_id_is_ignored(monkeypatch):
    """`sheet_instances` only ever yields results boxes, but this reader must not turn into a generic widget
    reader by accident: a `navegador::t3` in that list would make it read the browser card as a sheet."""
    seen = _fake(monkeypatch, {"": {"items": []}})
    verify.results_sheet(["navegador::t3"])
    assert seen == [("results", "")]


def test_unreadable_is_not_empty(monkeypatch):
    """`read: False` and `n_items: 0` mean different things and always have: an unread sheet is not an empty
    one, and 0 must never stand for "nobody looked"."""
    _fake(monkeypatch, {})
    r = verify.results_sheet(["results::1"])
    assert r["read"] is False and r["n_items"] == 0


def test_the_two_readers_cannot_point_at_different_boxes():
    """Guard on the wiring, which is the half a behavioural test cannot see: `mechanism_report` must take the
    ids from `sheet_instances` rather than calling `results_sheet()` bare. That is what keeps "which boxes
    were opened" and "what is in them" answering about the SAME boxes."""
    import inspect
    src = inspect.getsource(verify.mechanism_report)
    assert "results_sheet(" in src
    line = next(l for l in src.splitlines() if '"results_sheet"' in l)
    assert "sheet_instances(" in line, f"results_sheet no recibe los ids de sheet_instances: {line.strip()}"
