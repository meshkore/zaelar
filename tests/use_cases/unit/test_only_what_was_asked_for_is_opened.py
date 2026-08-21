"""A card nobody asked for is a defect, and the harness has to SEE it.

The operator caught it on screen (2026-08-21) and the automated walk had not: an empty «Navegador» card
sitting on top of the browser card that was actually working. Nothing ordered it open — the canvas reports
its open set, the server normalises `navegador::t2` down to `navegador` for the prompt, and the audit emit
of that new id travels on the same SSE bus the canvas takes orders from. The canvas obeys its own report.

These tests pin the READER, not the engine fix: `ghost_widgets` must recognise the signature, and — the
part that matters more — it must never claim a clean canvas when there was no canvas to look at.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.use_cases.e2e.agent import verify  # noqa: E402


def _snap(instances):
    """One `canvas (instancias)` event, in the shape the observability API really hands back: the fields
    land FLAT inside a JSON-string payload, not under an `extra` key (see `verify._fields`)."""
    import json
    return {"cat": "ui", "label": "canvas (instancias)",
            "payload": json.dumps({"label": "canvas (instancias)", "cat": "ui",
                                   "extra": {"instances": list(instances), "n": len(instances)}})}


def test_the_base_card_next_to_its_own_instance_is_a_ghost():
    r = verify.ghost_widgets([_snap(["navegador::t1"]), _snap(["navegador::t1", "navegador"])])
    assert r["observed"] is True
    assert [g["id"] for g in r["ghosts"]] == ["navegador"]
    assert r["ghosts"][0]["alongside"] == ["navegador::t1"]


def test_an_instance_alone_is_not_a_ghost():
    r = verify.ghost_widgets([_snap(["results", "navegador::t2"])])
    assert r["ghosts"] == [] and r["observed"] is True


def test_a_base_card_with_no_instance_of_it_is_not_a_ghost():
    """`results` open on its own is the normal case today and must not be reported: the defect is a base
    card DUPLICATING an instance of itself, not a base card existing."""
    r = verify.ghost_widgets([_snap(["results", "navegador::t2"]), _snap(["results", "agenda"])])
    assert r["ghosts"] == []


def test_no_canvas_attached_is_NOT_reported_as_clean():
    """The whole point. The echo needs a real frontend reporting its canvas, so an unattended round has no
    snapshot at all — which is why the walk went days without seeing this. `observed=False` keeps that
    distinction alive; a reader that returned «0 ghosts» here would be asserting a check it never ran."""
    r = verify.ghost_widgets([{"cat": "widget", "label": "show", "payload": '{"extra":{"id":"navegador::t1"}}'}])
    assert r["observed"] is False
    assert r["ghosts"] == [] and r["n_snapshots"] == 0


def test_the_reader_survives_the_shapes_the_api_really_returns():
    """Junk in the stream cannot take the reader down: a round that raises here loses its whole verdict."""
    r = verify.ghost_widgets([None, 42, {}, {"label": "canvas (instancias)"},
                              {"payload": "not json"}, _snap(["navegador::t1", "navegador"])])
    assert [g["id"] for g in r["ghosts"]] == ["navegador"]


def test_the_last_canvas_is_carried_so_the_report_can_show_it():
    r = verify.ghost_widgets([_snap(["results"]), _snap(["results", "navegador::t2", "navegador"])])
    assert r["last"] == ["results", "navegador::t2", "navegador"]
    assert r["max_cards"] == 3
