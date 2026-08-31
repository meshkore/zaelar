"""A San Francisco case is not measured on the Madrid set.

`--lab es` on a `__us` case does NOT fail: it measures. And what it measures is Marc, from Madrid, handling a
San Francisco assignment in Spanish inside an English brief. A tester that contradicts itself does not measure the
product; it measures the harness—and the round comes out GREEN for infrastructure, so the result enters the scoreboard
as though it were a verdict about the product. Same family as the 19 US scenarios that on 2026-08-27
responded with Spanish reality, and invisible from the outside for the same reason.

The defect lived in two places and is ONE:
  · the supervisor—the loop that is going to run for 24 consecutive hours—called `una_ronda(esc)` without a set, so
    the default `es` remained in effect for EVERYTHING, including `__us` cases.
  · `run.py` did not prevent it, so fixing only the supervisor leaves the same error possible with a manual `--lab`.

The refusal is intentionally fail-closed: a measurement with the wrong person is worse than no measurement, because
one that does not exist cannot fool anyone.
"""
from __future__ import annotations

from dataclasses import dataclass

from tests.use_cases.e2e.agent import supervisor as S
from tests.use_cases.e2e.agent.run import wrong_lab_refusal


@dataclass
class _Caso:
    id: str
    locale: str


def test_el_sufijo_del_id_dice_el_plato():
    assert S.plato_de("cheapest-monitor__us") == "us"
    assert S.plato_de("cheapest-monitor__es") == "es"
    assert S.plato_de("hotel-under-15-days") == "es", "sin sufijo, el plató de siempre"


def test_el_supervisor_lo_pasa_de_verdad(monkeypatch):
    """It is not enough for the function to exist: `main()` had to stop calling it without a set."""
    vistos: list[tuple[str, str]] = []

    def _falsa_ronda(esc, lab="es"):
        vistos.append((esc, lab))
        if len(vistos) >= 2:
            raise KeyboardInterrupt          # stops the supervisor's infinite loop
        return {}

    monkeypatch.setattr(S, "rotacion", lambda: ["cheapest-monitor__us", "hotel-under-15-days"])
    monkeypatch.setattr(S, "una_ronda", _falsa_ronda)
    monkeypatch.setattr(S.time, "sleep", lambda *_: None)
    monkeypatch.setattr(S, "_recargar_si_cambie", lambda *_: None)
    try:
        S.main()
    except KeyboardInterrupt:
        pass
    assert vistos == [("cheapest-monitor__us", "us"), ("hotel-under-15-days", "es")]


def test_el_plato_equivocado_se_niega():
    msg = wrong_lab_refusal("es", [_Caso("cheapest-monitor__us", "us")])
    assert msg and "cheapest-monitor__us" in msg and "--lab es" in msg


def test_el_plato_correcto_pasa():
    """The sensitivity half: without this, “rejects the mismatch” and “rejects everything” pass alike."""
    assert wrong_lab_refusal("us", [_Caso("cheapest-monitor__us", "us")]) == ""
    assert wrong_lab_refusal("es", [_Caso("hotel-under-15-days", "es")]) == ""


def test_una_tanda_mixta_se_niega_entera_y_los_nombra():
    """The real rotation case: the list contains both kinds and we need to see WHICH ones are extraneous."""
    casos = [_Caso("a__us", "us"), _Caso("b", "es"), _Caso("c__us", "us")]
    msg = wrong_lab_refusal("es", casos)
    assert "a__us" in msg and "c__us" in msg and "2 caso" in msg
    assert " b," not in msg and "b." not in msg, "the one that fits is not accused"


def test_un_sandbox_no_tiene_persona_y_no_es_asunto_de_esto():
    """Without `--lab` there is no persistent agent or profile to contradict: the refusal does not apply."""
    assert wrong_lab_refusal("", [_Caso("cheapest-monitor__us", "us")]) == ""


# ── Make both sets advance, not just one (2026-08-28) ──────────────────────────────────────────────────
def test_los_dos_platos_se_alternan_dentro_de_cada_grupo():
    """The operator asked to measure US **and** ES. The rotation priority (“broken first”) is what matters and is not
    changed; what was failing is that within each group the order came from the scoreboard dictionary and the
    `__us` cases remained in a block—measured: the first US case was in **position 21** of 132, about two
    hours and forty-five minutes into the set. A loop that runs all night without touching half the list is not measuring
    that half, even if it has it written down."""
    got = S.intercala(["a__es", "b__es", "c__es", "x__us", "y__us"])
    assert got == ["a__es", "x__us", "b__es", "y__us", "c__es"]


def test_el_mas_largo_termina_de_tirar_solo():
    assert S.intercala(["a__es", "b__es", "c__es"]) == ["a__es", "b__es", "c__es"]
    assert S.intercala(["x__us", "y__us"]) == ["x__us", "y__us"]
    assert S.intercala([]) == []


def test_se_alterna_pero_NO_se_baraja():
    """Shuffling would make two consecutive passes impossible to compare, and the rotation is precisely what makes them
    comparable. The relative order within each set must remain intact."""
    ids = [f"{c}__es" for c in "abcde"] + [f"{c}__us" for c in "vwxyz"]
    got = S.intercala(ids)
    assert [x for x in got if x.endswith("__es")] == [f"{c}__es" for c in "abcde"]
    assert [x for x in got if x.endswith("__us")] == [f"{c}__us" for c in "vwxyz"]
    assert sorted(got) == sorted(ids), "no se pierde ni se duplica ningún caso"


def test_la_prioridad_sigue_mandando_DENTRO_de_cada_plato():
    """Rewritten 2026-08-28, NOT reversed. The property—the priority takes precedence—is the same; what changed is
    where it means something.

    Previously, each group was interleaved (`intercala(rotos) + intercala(nunca) + intercala(buenos)`), and
    measured over the first four hours of the 24/7 run this produced **25 ES rounds versus 7 US**: ES has more broken
    cases, so after exhausting the US cases in the “broken” group, thirteen consecutive ES cases remained before reaching the
    “never measured” group, where the 52 untouched US cases live.

    Now each set carries its complete queue (broken → never → good) and they alternate turn by turn. What is
    sacrificed is having a broken case from one set come before a never-measured case from the OTHER—a comparison that
    means nothing, because two products are being measured in parallel, not one list.
    """
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text(encoding="utf-8")
    assert "return intercala(cola_es + cola_us)" in src
    assert src.index("rotos + nunca + buenos") < src.index("return intercala(cola_es + cola_us)")


def test_cada_plato_lleva_su_PROPIA_cola_de_prioridad():
    """Interleaving within each group was not enough, as the figures showed: **25 ES rounds versus 7 US** in the
    first four hours of the 24/7 set.

    The cause: ES has many more broken cases, so after exhausting the US cases in the “broken” group, thirteen consecutive ES
    cases remained BEFORE the “never measured” group began—the one where the 52 US cases no one had touched live. The
    priority was respected and the operator still had no US data.

    Now each set goes through broken → never → good independently and they alternate turn by turn: the priority
    remains intact WITHIN each locale, which is where it means something.
    """
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text(encoding="utf-8")
    assert "cola_es = [x for x in rotos + nunca + buenos if not x.endswith" in src
    assert "return intercala(cola_es + cola_us)" in src


def test_un_ROTO_de_su_plato_sigue_yendo_antes_que_un_BUENO_del_mismo():
    """The priority is not sacrificed for alternation: having a broken case from one set come before a
    never-measured case from the OTHER is sacrificed, since that comparison means nothing."""
    got = S.intercala(["roto__es", "nunca__es", "bueno__es", "roto__us", "nunca__us"])
    solo_es = [x for x in got if not x.endswith("__us")]
    assert solo_es == ["roto__es", "nunca__es", "bueno__es"]
    solo_us = [x for x in got if x.endswith("__us")]
    assert solo_us == ["roto__us", "nunca__us"]
