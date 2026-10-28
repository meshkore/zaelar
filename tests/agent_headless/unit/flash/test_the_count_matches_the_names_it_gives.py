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
    assert "5 resultados" in s and "«C»" in s and "y 2 más" in s and "Inicio" in s
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
