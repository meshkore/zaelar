"""V2-469 · the canned search line says a count and must name that many — or say how many more.

Measured in `find-videos-on-a-topic-no-ai-slop` (2026-08-28 22:31): “I’ve put 5 videos in the list:
“a” · “b” · “c”… tell me which one I should play” — a count of 5, three names, and a bare ellipsis. The user answered,
reasonably: «me has dicho 5 pero solo veo 3 enlaces». A count that doesn't match what's shown reads as a
delivery that lost items; «y 2 más» turns the same truncation into a fact.
"""
import pytest

from nucleo.flash import video_turn as VT


@pytest.fixture(autouse=True)
def _es(monkeypatch):
    monkeypatch.setattr(VT, "_lang", lambda: "es")


def _spoken(added):
    return VT.spoken_for({"executed": "play_video", "accion": "list", "ok": True, "added": added}, "Hecho.")


def test_five_added_names_three_and_says_two_more():
    s = _spoken(["A", "B", "C", "D", "E"])
    assert "5 vídeos" in s and "«C»" in s and "y 2 más" in s
    assert "…" not in s


def test_three_added_names_all_three_with_no_remainder():
    s = _spoken(["A", "B", "C"])
    assert "«A»" in s and "«C»" in s
    assert "más" not in s


def test_four_added_says_one_more_in_singular():
    assert "y 1 más" in _spoken(["A", "B", "C", "D"])


def test_the_english_engine_says_it_in_english(monkeypatch):
    monkeypatch.setattr(VT, "_lang", lambda: "en")
    s = _spoken(["A", "B", "C", "D", "E"])
    assert "and 2 more" in s and "…" not in s


# ── the model spoke a promise while its own search already delivered (V2-469, round 8) ───────────────────
def test_a_spoken_promise_gets_the_delivery_appended():
    """Round 8, turn 0: the model said “I’m going to search for real videos…” while execute() had already put 5
    titled hits in the list — the user had to ASK for the titles, and next turn the model DENIED having
    searched (“they were already there in your list”). A list-search that added items names them in the same turn:
    if the model already spoke, the outcome is appended."""
    parte = {"executed": "play_video", "accion": "list", "ok": True, "added": ["A", "B", "C", "D", "E"]}
    out = VT.ensure_delivery_named("Voy a buscar vídeos reales y de personas de verdad.", parte)
    assert out.startswith("Voy a buscar vídeos reales")
    assert "5 vídeos" in out and "«A»" in out and "y 2 más" in out


def test_a_failed_search_appends_the_honest_outcome_too():
    """The promise must not stand alone over nothing: «no he podido buscarlos» rides along."""
    parte = {"executed": "play_video", "accion": "list", "ok": False, "message": "no encontré vídeos de eso."}
    out = VT.ensure_delivery_named("Voy a buscar ahora mismo.", parte)
    assert "No he podido buscarlos" in out


def test_a_non_list_turn_is_left_alone():
    parte = {"executed": "play_video", "accion": "play", "ok": True, "title": "X"}
    assert VT.ensure_delivery_named("Te lo pongo.", parte) == "Te lo pongo."


def test_an_empty_spoken_returns_the_canned_line_alone():
    parte = {"executed": "play_video", "accion": "list", "ok": True, "added": ["A"]}
    out = VT.ensure_delivery_named("", parte)
    assert out.startswith("Te he puesto 1")


def test_the_probe_actually_wires_the_augmentation():
    """Wiring guard (V2-199's lesson): the four tests above pass whole with the probe's call deleted —
    a decision nobody calls delivers nothing."""
    from pathlib import Path
    src = Path("nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "ensure_delivery_named" in src
