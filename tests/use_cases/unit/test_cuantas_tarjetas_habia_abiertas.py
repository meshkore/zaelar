"""How many cards were on the canvas at each turn — the OTHER concurrency (V2-739).

`task_registry.max_concurrent` counts background errands. It says nothing about what the operator is
LOOKING at, and that is what he talks about by allusion: «bájale el volumen a ese», «cierra el de abajo»,
«ahora el otro». A scenario that opens three cards and operates them one by one is measuring ROUTING, and
without a live reading of the open set the judge can only believe the transcript — which is the thing under
test. A judge handed a conclusion it cannot check against anything distrusts the conclusion (measured three
rounds running on `play-music-and-build-playlist`).

Driven against the REAL reader, with the event shape the canvas really emits (`cat="widget"`, `label` ∈
{show, close}, instance in `id` as `"<widget>::<algo>"`).
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify

TRANSCRIPT = [
    {"who": "user", "at": 0.0}, {"who": "zaelar", "at": 1.0},
    {"who": "user", "at": 10.0}, {"who": "zaelar", "at": 11.0},
    {"who": "user", "at": 20.0},
]


def _ev(sec: float, label: str, wid: str = "") -> dict:
    return {"cat": "widget", "label": label, "id": wid, "t_ms": sec * 1000.0}


def test_each_turn_carries_the_cards_that_were_open_in_it():
    out = verify.open_widgets_by_turn(
        [_ev(1.0, "show", "youtube"), _ev(11.0, "show", "musica"), _ev(21.0, "show", "agenda")],
        TRANSCRIPT)
    assert out["by_turn"] == {"t0": ["youtube"], "t1": ["musica", "youtube"],
                              "t2": ["agenda", "musica", "youtube"]}
    assert out["max_open"] == 3
    assert out["kinds"] == ["agenda", "musica", "youtube"]


def test_an_instance_is_the_same_CARD_as_its_base():
    """`youtube::t2` and `youtube` are one kind of card. Counting them as two would report a canvas with
    three cards on it as if it had five — `sheets_opened` is the reader for the opposite question."""
    out = verify.open_widgets_by_turn(
        [_ev(1.0, "show", "youtube"), _ev(2.0, "show", "youtube::t2")], TRANSCRIPT)
    assert out["by_turn"]["t0"] == ["youtube"]
    assert out["max_open"] == 1


def test_a_close_takes_one_card_and_a_bare_close_takes_them_all():
    out = verify.open_widgets_by_turn(
        [_ev(1.0, "show", "youtube"), _ev(2.0, "show", "musica"), _ev(11.0, "close", "musica")],
        TRANSCRIPT)
    assert out["by_turn"] == {"t0": ["musica", "youtube"], "t1": ["youtube"], "t2": ["youtube"]}
    out = verify.open_widgets_by_turn(
        [_ev(1.0, "show", "youtube"), _ev(2.0, "show", "musica"), _ev(11.0, "close")], TRANSCRIPT)
    assert out["by_turn"]["t1"] == []
    assert out["max_open"] == 2, "the peak is what the run REACHED, not what survived to the end"


def test_the_peak_survives_a_card_that_was_closed_again():
    """The number the judge needs is «were they ever up together», not «are they up now». A run that opens
    three and closes two before the last turn still proved the canvas held three."""
    out = verify.open_widgets_by_turn(
        [_ev(1.0, "show", "youtube"), _ev(1.5, "show", "musica"), _ev(2.0, "show", "agenda"),
         _ev(11.0, "close", "agenda"), _ev(11.5, "close", "musica")], TRANSCRIPT)
    assert out["max_open"] == 3
    assert out["by_turn"]["t2"] == ["youtube"]


def test_no_operator_turn_means_nothing_to_bucket_INTO():
    assert verify.open_widgets_by_turn([_ev(1.0, "show", "youtube")], []) == {}
    assert verify.open_widgets_by_turn([_ev(1.0, "show", "youtube")],
                                       [{"who": "zaelar", "at": 0.0}]) == {}


def test_the_operators_own_click_counts_too():
    """The canvas reports what the OPERATOR opened by hand with `src="user"` (V2-039). The command path
    drops that echo on purpose — a report of what already happened is not an order — but for «what was on
    screen» it is the best evidence there is, and filtering it would make his own click invisible."""
    e = _ev(1.0, "show", "navegador"); e["src"] = "user"
    out = verify.open_widgets_by_turn([e], TRANSCRIPT)
    assert out["by_turn"]["t0"] == ["navegador"], "a card he opened himself is still a card he can talk about"
