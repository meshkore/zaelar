"""Containment: even if the driver slips out of character, the JUDGE must not charge that line to zaelar.

Face 5 (`test_driver_flip_by_vocative.py`) prevents the flip; this covers the case where it slips through anyway. And slip through they did:
in round 6 of `cheapest-monitor` (2026-08-23), the generic harness warning that already existed—“the model
acting as the user slipped out of character N times”—was in front of the judge and was not enough. The judge read the
TESTER's line in an assistant's voice and charged it as `zaelar@turn7`, one of the round's three [high]-priority
blockers, with the full quote. The `TESTER`/`ZAELAR` labels in the transcript were also in front of it, and the
content overpowered them.

That is why the rule stops talking about the role and instead names the TEXT: the specific, quoted line, with the
prohibition attached. A judge that charges it anyway is contradicting a literal quote, not drawing the wrong inference.
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
    # This is exactly what was charged in round 6: quoting it in a finding.
    assert "hallazgo" in low


def test_sin_flip_el_juez_no_ve_ninguna_advertencia_de_este_tipo():
    """A warning that always appears is noise, and worse: it trains the judge to ignore it when it matters.

    The report is deliberately POPULATED. The first version of this test passed `{}` and was green for the
    wrong reason: `mechanism_facts` returns early with “there is no mechanism report” and never reaches the block
    that was meant to be checked. The teardown caught it—forcing the warning to always appear did not turn anything red—which is
    exactly what the teardown is for."""
    facts = mechanism_facts({"families_observed": ["worker", "widget"], "expected_signals": ["worker"]})
    assert "Familias del sistema" in facts, "el informe se cortó arriba: el test no llega a lo que mide"
    assert "LAS ESCRIBIÓ EL ARNÉS" not in facts


def test_varias_lineas_salen_TODAS(monkeypatch):
    facts = mechanism_facts({"role_flip_lines": [{"turn": 3, "text": "Ya está listo, Marc."},
                                                 {"turn": 7, "text": _LINE}]})
    assert "turno 3" in facts and "turno 7" in facts
    assert "2 turno(s)" in facts
