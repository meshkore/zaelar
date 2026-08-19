"""El relleno de espera no puede decir CUATRO veces la misma frase (V2-189).

`data_acks` tiene este tratamiento desde V2-038, porque dos «Hecho.» seguidos disparaban el detector de
bucles. Al relleno de espera —que se dice mucho más a menudo— nunca se le aplicó. Medido en dos casos
distintos de la misma noche:

  · `cheapest-monitor` (2026-08-20 01:21) — «Vale, dame un momento que lo miro.» CUATRO veces, palabra por
    palabra, con el operador contestando «vale, quedo atento» / «vale, sin prisa» cada vez. overall 1/5,
    eficiencia 1.
  · `restaurant-tonight-madrid` (01:01) — cinco turnos de lo mismo. El juez: «ineficiencia comunicativa
    severa», gravedad alta.

Y no lo dice el modelo: la frase la pone el backstop de nunca-mudo, por nosotros, cuando el turno vuelve sin
contenido propio. Quitarlo es peor (V2-092/V2-122: un turno mudo es el fallo más grave), así que lo que había
que arreglar es que **no se repita** y que, pasada la segunda espera, lleve el único hecho honesto disponible
—cuánto lleva— con una salida. Nunca un PASO: esa es la línea que trazó V2-133.
"""
from __future__ import annotations

import pytest

from nucleo.flash import router_guards as g
from voice.engine.core import langs


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(g, "_longest_pending_min", lambda: 7)
    yield


def _converse(lang, turns: int) -> list[str]:
    window, said = [], []
    for _ in range(turns):
        line = g.holding_line(window, lang)
        said.append(line)
        window += [{"role": "user", "content": "vale, quedo atento"},
                   {"role": "assistant", "content": line}]
    return said


@pytest.mark.parametrize("code", ["es", "en"])
def test_four_waits_are_never_the_same_sentence_four_times(code):
    said = _converse(langs.LANGUAGES[code], 4)
    assert len(set(said)) == 4, f"se repitió: {said}"


@pytest.mark.parametrize("code", ["es", "en"])
def test_and_never_twice_IN_A_ROW(code):
    """La forma que de verdad se nota. Rotar y aun así repetir la de justo antes no arregla nada."""
    said = _converse(langs.LANGUAGES[code], 8)
    assert all(a != b for a, b in zip(said, said[1:])), said


def test_past_the_second_wait_it_says_how_long_and_offers_a_way_out():
    said = _converse(langs.LANGUAGES["es"], 3)
    assert "7 min" in said[2]
    assert "?" in said[2]                       # una salida, no otra vuelta de proceso


def test_but_it_never_states_a_STEP():
    """La línea de V2-133: el relleno puede decir que sigue, y cuánto lleva; jamás EN QUÉ PUNTO va. Ocho de
    doce casos de aquella tanda fallaron por una fase inventada con la forma exacta de un paso de worker."""
    said = _converse(langs.LANGUAGES["es"], 6)
    prohibidas = ("login", "rellenando", "consultando", "en la página", "formulario", "fase")
    for line in said:
        assert not any(p in line.lower() for p in prohibidas), line


def test_with_no_task_to_time_it_still_never_repeats(monkeypatch):
    """El hecho puede no estar disponible (no se puede leer el despacho). Eso degrada la ESCALADA, no la
    no-repetición: seguir diciendo lo mismo cuatro veces sería el mismo defecto con otra excusa."""
    monkeypatch.setattr(g, "_longest_pending_min", lambda: 0)
    said = _converse(langs.LANGUAGES["es"], 3)
    assert all(a != b for a, b in zip(said, said[1:])), said


def test_the_chooser_is_wired_into_BOTH_channels():
    """`probe.py` y el provider de voz son implementaciones paralelas del mismo turno, y el provider solo
    distinguía la PRIMERA espera de las demás: de la tercera en adelante todas eran idénticas."""
    import inspect

    from nucleo.flash import probe as _probe
    from voice.engine.llm.providers import nucleo as _provider
    assert "holding_line(" in inspect.getsource(_probe.run_turn)
    assert "holding_line(" in inspect.getsource(_provider)
