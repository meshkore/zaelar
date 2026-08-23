"""Contención: aunque el conductor se salga del papel, el JUEZ no puede fichar esa línea contra zaelar.

La cara 5 (`test_driver_flip_by_vocative.py`) evita el flip; esto cubre el que se escape igual. Y se escapan:
en la ronda 6 de `cheapest-monitor` (2026-08-23) el aviso genérico de arnés que ya existía —«el modelo que
hace de usuario se salió de su papel N veces»— estaba delante del juez y no bastó. El juez leyó la línea
del TESTER con voz de asistente y la fichó como `zaelar@turn7`, uno de los tres bloqueadores [alta] de la
ronda, con la cita entera. Las etiquetas `TESTER`/`ZAELAR` del transcript también estaban delante, y el
contenido pudo con ellas.

Por eso la regla deja de hablar del papel y pasa a nombrar el TEXTO: la línea concreta, citada, con la
prohibición pegada. Un juez que la fiche igual está contradiciendo una cita literal, no infiriendo mal.
"""
from tests.use_cases.e2e.agent.judge import mechanism_facts

_LINE = ("Sí, Marc, le he mirado las reseñas y están muy bien en general. La gente destaca sobre todo la "
         "nitidez del 4K, aunque algunos mencionan que los altavoces son justitos.")


def test_the_flipped_line_reaches_the_judge_QUOTED_and_not_just_counted():
    facts = mechanism_facts({"role_flip_lines": [{"turn": 7, "text": _LINE}]})
    assert "reseñas" in facts, "el juez no ve el TEXTO: un aviso que no cita no distingue qué línea era"
    assert "turno 7" in facts


def test_the_prohibition_is_explicit_about_no_atribuirla_a_zaelar():
    facts = mechanism_facts({"role_flip_lines": [{"turn": 7, "text": _LINE}]})
    low = facts.lower()
    assert "prohibido" in low
    assert "zaelar" in low
    # Lo que se fichó en la ronda 6 fue exactamente esto: citarla en un hallazgo.
    assert "hallazgo" in low


def test_sin_flip_el_juez_no_ve_ninguna_advertencia_de_este_tipo():
    """Un aviso que sale siempre es ruido, y peor: entrena al juez a ignorarlo cuando importe.

    El informe va POBLADO a propósito. La primera versión de este test pasaba `{}` y era verde por el motivo
    equivocado: `mechanism_facts` corta arriba con «no hay informe de mecanismo» y no llega nunca al bloque
    que se quería comprobar. Lo cazó el desarme —forzar el aviso a salir siempre no puso rojo nada—, que es
    justo para lo que está el desarme."""
    facts = mechanism_facts({"families_observed": ["worker", "widget"], "expected_signals": ["worker"]})
    assert "Familias del sistema" in facts, "el informe se cortó arriba: el test no llega a lo que mide"
    assert "LAS ESCRIBIÓ EL ARNÉS" not in facts


def test_varias_lineas_salen_TODAS(monkeypatch):
    facts = mechanism_facts({"role_flip_lines": [{"turn": 3, "text": "Ya está listo, Marc."},
                                                 {"turn": 7, "text": _LINE}]})
    assert "turno 3" in facts and "turno 7" in facts
    assert "2 turno(s)" in facts
