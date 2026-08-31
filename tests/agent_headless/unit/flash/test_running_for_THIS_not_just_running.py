"""“Is anything running?” was the wrong question: the deciding one is “is anything running FOR THIS?” (V2-176).

The promise-without-action backstop (V2-132) is gated by “nothing alive,” and its reasoning is correct but
INCOMPLETE: with a task in progress, “I’m still working on it” is honest and re-escalating would do the work twice—but
only if the live task is about what was requested.

Measured twice, in two different cases and from both sides:

  · `book-hotel-night-known__es` (2026-08-20 10:26), `mecanismo 1`, y el mecanismo dice
    `status=cancelled url=https://www.ticketmaster.es/`:

        TESTER  Resérvame una noche en el Hotel Palacio de la Merced para el 30 de agosto.
        ZAELAR  ¿para una o dos personas, y habitación doble o individual?
        TESTER  Una, solo yo. Y la habitación estándar, me da igual.
        ZAELAR  Me pongo con ello, tardo un poco.
        ...
        ZAELAR  Sigo sin novedades: la reserva sigue en marcha

    Nothing escalated because a worker for the PREVIOUS errand (the theater) was still alive. Four turns of “the reservation
    is still in progress” about an already-cancelled Ticketmaster task. The judge: “critical domain divergence.”
  · `restaurant-tonight-madrid` (2026-08-19): the same pattern from the other side—the question was about Casa Lucio and the
    answer was about El Rey León.
"""
from __future__ import annotations

import pytest

from nucleo.flash import router_guards as g

HOTEL = "Resérvame una noche en el Hotel Palacio de la Merced para el 30 de agosto. — Una, solo yo."
TEATRO = "conseguir dos entradas para el musical de El Rey León en Madrid el sábado"


def test_an_unrelated_errand_does_not_count_as_running_for_this():
    assert g.nothing_running_for(HOTEL, [TEATRO]) is True


def test_but_the_same_errand_does():
    """The half that protects what the gate protected: re-escalating here would do the work twice."""
    assert g.nothing_running_for(HOTEL, ["reservar noche en el Hotel Palacio de la Merced"]) is False


def test_with_nothing_running_it_is_trivially_true():
    assert g.nothing_running_for(HOTEL, []) is True


def test_one_matching_errand_among_several_is_enough_to_hold():
    assert g.nothing_running_for(HOTEL, [TEATRO, "reservar el hotel palacio"]) is False


# ── conservative IN THE DIRECTION THE GATE PROTECTED ────────────────────────────────────────────────────────
# The two errors do not cost the same: running an errand twice is a defect the operator PAYS for; being told
# “I’m still working on it” about someone else’s errand is one they cannot even see. So when in doubt, as before.
def test_a_goal_too_thin_to_judge_keeps_the_old_conduct():
    for thin in ("eso", "lo de antes", "", "sí"):
        assert g.nothing_running_for(thin, [TEATRO]) is False, thin


def test_an_unreadable_running_goal_is_assumed_to_be_this_one():
    assert g.nothing_running_for(HOTEL, [""]) is False
    assert g.nothing_running_for(HOTEL, [None]) is False


def test_a_function_word_in_common_is_not_a_topic_in_common():
    """The bug in the first attempt at this predicate: “Hotel Palacio … FOR August 30” and
    “tickets FOR El Rey León” overlapped on “for,” and a preposition was enough to make two completely unrelated
    errands appear to be the same. Attached punctuation did the same (“agosto.” ≠ “agosto”)."""
    assert "para" not in g._topic_words(HOTEL)
    assert "agosto" in g._topic_words(HOTEL), "la puntuación se está quedando pegada a la palabra"
    assert not (g._topic_words(HOTEL) & g._topic_words(TEATRO))


def test_a_date_in_common_is_not_a_topic_in_common():
    """Two errands for the same Saturday are not the same errand."""
    assert g.nothing_running_for("reservar mesa el sábado en Casa Lucio",
                                 ["conseguir entradas el sábado para el Rey León"]) is True


# ── and it is wired into BOTH channels ───────────────────────────────────────────────────────────────────────
def test_both_channels_ask_the_new_question():
    """Source guard. This predicate is useless in only one channel: voice and text have the same
    duplicated gate, and this batch has already found two dead fixes caused by wiring only one side."""
    import inspect

    from nucleo.flash import probe
    from voice.engine.llm.providers import nucleo as voice_nucleo

    for mod, name in ((probe, "probe.py"), (voice_nucleo, "el provider de voz")):
        src = inspect.getsource(mod)
        assert "nothing_running_for" in src, f"{name} sigue preguntando solo «¿hay algo corriendo?»"


def test_the_text_channel_can_read_WHAT_is_running():
    """`has_active()` says WHETHER anything is running; to compare, we need to know WHAT. And if the registry cannot be read,
    the empty list plus the conservative predicate preserve the previous behavior."""
    from nucleo.flash import probe
    assert isinstance(probe._running_goals(), list)


def test_the_predicate_is_reachable_from_the_router_facade():
    """Voice calls through `_router.`; without the re-export, that channel's wiring would fail at runtime
    and only on the turn that matters."""
    from nucleo.flash import router
    assert router.nothing_running_for is g.nothing_running_for
