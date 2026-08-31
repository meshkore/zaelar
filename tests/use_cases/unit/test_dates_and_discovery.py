"""Future-date ratchet + contract for discovery cases.

Operator rule (2026-08-19): dates in a use case are ALWAYS relative to today. This test exists because the defect
is not visible when reading: the catalog asked for «flights for the May holiday weekend» and «the birthday is on
March 14» with the clock in AUGUST — cases impossible by construction that the dashboard counted as agent
failures. An absolute date expires on its own and silently poisons the measurement, so the prohibition belongs in
a test.
"""
from __future__ import annotations

import datetime as dt
import re

from tests.use_cases.e2e.agent import dates as DT, discovery as DISC, scenarios as SC

_MESES = ("enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|"
          "january|february|march|april|may|june|july|august|september|october|november|december")
# «14 de marzo», «September 20th», «puente de mayo»: a NAMED month in the SOURCE text is the forbidden pattern.
_ABS = re.compile(rf"\b(?:\d{{1,2}}\s+de\s+(?:{_MESES})|(?:{_MESES})\s+\d{{1,2}}|puente de (?:{_MESES}))\b",
                  re.I)


def _sources() -> dict[str, str]:
    """The SOURCE text, not the resolved text: after `resolve()`, every date is a named and legitimate month."""
    import inspect

    from tests.use_cases import cases_data
    out = {}
    for mod in (SC, DISC, cases_data):
        out[mod.__name__] = inspect.getsource(mod)
    from tests.use_cases.e2e.agent import derived
    out["derived"] = inspect.getsource(derived)
    return out


def test_ningun_caso_lleva_una_fecha_absoluta_escrita_a_mano():
    bad = []
    for name, src in _sources().items():
        for line in src.splitlines():
            if line.lstrip().startswith("#") or "dates.py" in line:
                continue
            m = _ABS.search(line)
            if m:
                bad.append(f"{name}: …{m.group(0)}… → usa un token de dates.py")
    assert not bad, ("fechas absolutas en casos de uso (caducan solas y vuelven el caso imposible):\n  "
                     + "\n  ".join(bad))


def test_los_tokens_de_fecha_se_resuelven_en_todo_escenario():
    left = []
    for s in SC.all_scenarios():
        for field in (s.opening_line, s.persona_brief, s.success_checks, *(s.memory_seed or [])):
            for tok in re.findall(r"\{[A-Z_]+\}", field or ""):
                left.append(f"{s.id}: {tok}")
    assert not left, f"tokens sin resolver: {left}"


def test_toda_fecha_resuelta_cae_en_el_futuro():
    """The proposed weekend can never be in the past — not even a Saturday shifted to Sunday."""
    for ref, expect_sat in ((dt.date(2026, 8, 19), dt.date(2026, 8, 22)),   # miércoles
                            (dt.date(2026, 8, 22), dt.date(2026, 8, 22)),   # sábado: hoy vale
                            (dt.date(2026, 8, 23), dt.date(2026, 8, 22))):  # domingo: el finde es el de hoy
        sat, sun = DT.next_weekend(ref)
        assert sat == expect_sat and sun == sat + dt.timedelta(days=1), (ref, sat, sun)
        assert sun >= ref, f"el domingo propuesto ({sun}) es anterior a hoy ({ref})"
    assert DT.days_ahead(21) > DT.today()
    assert DT.days_ahead(0) > DT.today(), "days_ahead(0) tiene que empujar al futuro, no devolver hoy"


def test_los_casos_de_descubrimiento_traen_su_contrato_completo():
    """Each discovery case SEEDS memory and declares how to verify that it landed.

    Without `seed_probe_query`, the seeding cannot be verified, and without verification the case would measure
    the memory distiller while reporting an agent failure — the error these cases exist to prevent.
    """
    assert DISC.SCENARIOS, "no hay casos de descubrimiento"
    for s in DISC.SCENARIOS:
        assert s.memory_seed, f"{s.id} no siembra memoria"
        assert s.seed_probe_query, f"{s.id} no dice cómo comprobar la siembra"
        # `worker`/`widget`, NOT «Brain Workers»/«Widgets»: what is compared against the mechanism report
        # is the event's RAW `cat`, not the label a human reads in the viewer. These two asserts named the
        # label, so they CONFIRMED the bug instead of catching it — test and code written at the same time
        # from the same mistaken belief. The ratchet that does catch it (`test_segments.py`) reads the
        # families from `voice.observer._CAT` instead of repeating what I believed.
        assert "worker" in s.expected_signals, f"{s.id} debería exigir un worker real"
        assert "widget" in s.expected_signals, f"{s.id} debería exigir el widget de resultados"
        low = s.success_checks.lower()
        assert "widget nuevo" in low or "new widget" in low, (
            f"{s.id}: el criterio no dice que crear un widget nuevo es un fallo (V2-115)")
    assert {s.locale for s in DISC.SCENARIOS} == {"es", "us"}, "la familia tiene que cubrir ES y EN"


def test_un_pass_no_puede_tapar_un_mecanismo_roto():
    """High overall score + mechanism 1–2 = FAIL, not PASS.

    REAL case that motivated it (2026-08-19, `reorder-prescription__es`): impeccable behavior —5 in naturalness,
    adaptation, and outcome—with **mechanism 1**, and the judge writing «critical desynchronization: reports
    'working' status with zero background activity». The aggregate threshold marked it as PASSED and discarded
    that finding. The harness's foundational rule is that mechanism takes precedence over text; this applies it to
    the marker.
    """
    from tests.use_cases.e2e.agent import status as S

    base = {"run": {}, "verdict": {"veredicto": "ok"}}
    roto = {**base, "verdict": {"veredicto": "ok", "scores": {"naturalidad": 5, "resultado": 5, "mecanismo": 1}}}
    sano = {**base, "verdict": {"veredicto": "ok", "scores": {"naturalidad": 5, "resultado": 5, "mecanismo": 4}}}
    assert S._state(4, roto) == "FAIL", "un mecanismo roto no puede salir en verde"
    assert S._state(4, sano) == "PASS"
    assert S._state(5, {**base, "verdict": {"veredicto": "ok", "scores": {"mecanismo": 2}}}) == "FAIL"
    # Without a mechanism score (purely conversational cases), the threshold still governs: the guard cannot
    # turn "not measured" into "broken".
    assert S._state(4, {**base, "verdict": {"veredicto": "ok", "scores": {"naturalidad": 4}}}) == "PASS"
    # And INFRA remains INFRA, never FAIL — that was already the rule and must not be broken by this change.
    assert S._state(None, base) == "INFRA"
