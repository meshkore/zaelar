"""The judge does not compare 13-digit epochs: the harness already gives them to it as relative values (V2-365).

Measured in `find-direct-flight-budget__es` (2026-08-27, round 15). The judge filed this test as the session's MOST
SERIOUS conduct failure —[high], “it had concrete data in front of it and did not provide it”:

    “first_result_ms 1787816928677 vs turn at 1787816914617” → “the sheet had already had rows for ~30 s”

928677 is GREATER than 914617. The rows arrived **14 seconds AFTER** the turn being accused. Sign
reversed and magnitude doubled. And that turn's prompt block, read later in the session log, contained
no rows: there was nothing to deliver.

The prose prohibition had already been written since V2-300 —“DO NOT use `first_result_ms` to accuse it of withholding”—
and it did not help, because the number was still in the JSON right below it. A guard that prohibits using data that remains
in front of the model competes with the data; the one that works is not putting it there.

What the fix does is the same thing V2-300 did with `delivery_lag_s`: the harness does the calculation, and
it can do it exactly. All instants against the SAME zero, so the judge can continue matching a row to a
turn —that question is legitimate and is exactly the one we need to be able to answer— without being able
to get the sign wrong while doing so.
"""
import json

from tests.use_cases.e2e.agent.judge import _clocks_relative


# The two numbers from the round, exactly as they appeared in the report.
TURNO = 1787816914617.7258
FILAS = 1787816928677.772


def test_la_ronda_medida_ya_no_se_puede_leer_al_reves():
    mech = {"prompt_context": [{"at_ms": TURNO, "turn": 8}],
            "sheet_timing": {"first_result_ms": FILAS}}
    out = _clocks_relative(mech)
    turno = out["prompt_context"][0]["at_s"]
    filas = out["sheet_timing"]["first_result_s"]
    assert filas > turno, "las filas llegaron DESPUÉS del turno; ése es el hecho que se leyó al revés"
    assert round(filas - turno, 1) == 14.1, "y la distancia es de 14 s, no de los ~30 que escribió el juez"


def test_el_cero_es_el_primer_instante_medido():
    """Against the same zero, otherwise they are not comparable to each other, which is exactly what needed fixing."""
    out = _clocks_relative({"a_ms": TURNO, "b_ms": FILAS})
    assert out == {"a_s": 0.0, "b_s": 14.1}


def test_ningun_epoch_crudo_sobrevive_al_json_del_juez():
    """The real guard: if someone adds a new clock tomorrow, this test catches it without being changed."""
    mech = {"sheet_timing": {"first_result_ms": FILAS, "sheet_ms": TURNO},
            "prompt_context": [{"at_ms": TURNO}, {"at_ms": FILAS}],
            "hondo": {"lista": [{"mas_hondo": {"cuando_ms": FILAS}}]}}
    blob = json.dumps(_clocks_relative(mech))
    assert "17878169" not in blob, "un epoch crudo llegó al juez"
    assert "_ms" not in blob


def test_una_DURACION_no_se_toca():
    """`first_output_ms` is ELAPSED milliseconds, not an instant. Making it relative would turn it into a
    time of day and would invent a fact—the symmetric error being fixed."""
    out = _clocks_relative({"at_ms": TURNO, "first_output_ms": 820, "latencia_ms": 0})
    assert out["first_output_ms"] == 820
    assert out["latencia_ms"] == 0
    assert out["at_s"] == 0.0


def test_sin_ningun_reloj_el_informe_pasa_intacto():
    mech = {"workers": {"spawned": 1}, "notas": ["sin relojes"]}
    assert _clocks_relative(mech) is mech


def test_el_informe_ORIGINAL_no_se_toca():
    """`mechanism_facts()` and the report on disk continue reading the epochs: making them relative is ONLY for the
    JSON the judge sees. Mutating the original would change the data for everyone who comes afterward."""
    mech = {"sheet_timing": {"first_result_ms": FILAS}}
    _clocks_relative(mech)
    assert mech == {"sheet_timing": {"first_result_ms": FILAS}}


def test_el_JSON_del_juez_sale_relativizado_y_lo_dice():
    """The wiring: the classic failure is for the function to exist but not be connected. And the judge has to KNOW
    that they are seconds, or it will read a 14.1 as a truncated epoch."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/judge.py").read_text()
    assert "json.dumps(_clocks_relative(mech)" in src
    assert "SEGUNDOS desde el primer instante medido" in src
    assert "json.dumps(mech, ensure_ascii=False, indent=2)" not in src, "quedó un volcado crudo"
