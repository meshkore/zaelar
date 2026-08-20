"""«¿Hay algo corriendo?» era la pregunta equivocada: la que decide es «¿hay algo corriendo PARA ESTO?» (V2-176).

El backstop de promesa-sin-acción (V2-132) está gateado por «nada vivo», y su razonamiento es correcto e
INCOMPLETO: con una tarea en marcha, «sigo con ello» es honesto y re-escalar haría el trabajo dos veces — pero
solo si la tarea viva es de lo que se ha pedido.

Medido dos veces, en dos casos distintos y desde los dos lados:

  · `book-hotel-night-known__es` (2026-08-20 10:26), `mecanismo 1`, y el mecanismo dice
    `status=cancelled url=https://www.ticketmaster.es/`:

        TESTER  Resérvame una noche en el Hotel Palacio de la Merced para el 30 de agosto.
        ZAELAR  ¿para una o dos personas, y habitación doble o individual?
        TESTER  Una, solo yo. Y la habitación estándar, me da igual.
        ZAELAR  Me pongo con ello, tardo un poco.
        ...
        ZAELAR  Sigo sin novedades: la reserva sigue en marcha

    Nada escaló, porque seguía vivo un worker del encargo ANTERIOR (el teatro). Cuatro turnos de «la reserva
    sigue en marcha» sobre una tarea de Ticketmaster ya cancelada. El juez: «divergencia crítica de dominio».
  · `restaurant-tonight-madrid` (2026-08-19): la misma forma por el otro lado — se preguntó por Casa Lucio y se
    contestó sobre El Rey León.
"""
from __future__ import annotations

import pytest

from nucleo.flash import router_guards as g

HOTEL = "Resérvame una noche en el Hotel Palacio de la Merced para el 30 de agosto. — Una, solo yo."
TEATRO = "conseguir dos entradas para el musical de El Rey León en Madrid el sábado"


def test_an_unrelated_errand_does_not_count_as_running_for_this():
    assert g.nothing_running_for(HOTEL, [TEATRO]) is True


def test_but_the_same_errand_does():
    """La mitad que protege lo que la puerta protegía: re-escalar aquí haría el trabajo dos veces."""
    assert g.nothing_running_for(HOTEL, ["reservar noche en el Hotel Palacio de la Merced"]) is False


def test_with_nothing_running_it_is_trivially_true():
    assert g.nothing_running_for(HOTEL, []) is True


def test_one_matching_errand_among_several_is_enough_to_hold():
    assert g.nothing_running_for(HOTEL, [TEATRO, "reservar el hotel palacio"]) is False


# ── conservador EN LA DIRECCIÓN QUE LA PUERTA PROTEGÍA ──────────────────────────────────────────────────────
# Los dos errores no cuestan lo mismo: correr un encargo dos veces es un defecto que el operador PAGA; que le
# digan «sigo con ello» sobre el encargo de otro es uno que no puede ni ver. Así que ante la duda, como antes.
def test_a_goal_too_thin_to_judge_keeps_the_old_conduct():
    for thin in ("eso", "lo de antes", "", "sí"):
        assert g.nothing_running_for(thin, [TEATRO]) is False, thin


def test_an_unreadable_running_goal_is_assumed_to_be_this_one():
    assert g.nothing_running_for(HOTEL, [""]) is False
    assert g.nothing_running_for(HOTEL, [None]) is False


def test_a_function_word_in_common_is_not_a_topic_in_common():
    """El fallo que tuvo el primer intento de este predicado: «Hotel Palacio … PARA el 30 de agosto» y
    «entradas PARA El Rey León» solapaban en «para», y una preposición bastaba para que dos encargos sin nada
    que ver parecieran el mismo. La puntuación pegada hacía lo propio («agosto.» ≠ «agosto»)."""
    assert "para" not in g._topic_words(HOTEL)
    assert "agosto" in g._topic_words(HOTEL), "la puntuación se está quedando pegada a la palabra"
    assert not (g._topic_words(HOTEL) & g._topic_words(TEATRO))


def test_a_date_in_common_is_not_a_topic_in_common():
    """Dos encargos del mismo sábado no son el mismo encargo."""
    assert g.nothing_running_for("reservar mesa el sábado en Casa Lucio",
                                 ["conseguir entradas el sábado para el Rey León"]) is True


# ── y está cableado en LOS DOS canales ──────────────────────────────────────────────────────────────────────
def test_both_channels_ask_the_new_question():
    """Guarda de fuente. Este predicado no sirve de nada en un solo canal: la voz y el texto tienen la misma
    puerta duplicada, y esta tanda ya encontró dos arreglos muertos por cablear solo un lado."""
    import inspect

    from nucleo.flash import probe
    from voice.engine.llm.providers import nucleo as voice_nucleo

    for mod, name in ((probe, "probe.py"), (voice_nucleo, "el provider de voz")):
        src = inspect.getsource(mod)
        assert "nothing_running_for" in src, f"{name} sigue preguntando solo «¿hay algo corriendo?»"


def test_the_text_channel_can_read_WHAT_is_running():
    """`has_active()` dice SI hay algo; para comparar hace falta saber QUÉ. Y si el registro no se puede leer,
    la lista vacía más el predicado conservador dejan la conducta de antes."""
    from nucleo.flash import probe
    assert isinstance(probe._running_goals(), list)


def test_the_predicate_is_reachable_from_the_router_facade():
    """La voz llama por `_router.`; sin el re-export, el cableado de ese canal reventaría en tiempo de ejecución
    y solo en el turno que importa."""
    from nucleo.flash import router
    assert router.nothing_running_for is g.nothing_running_for
