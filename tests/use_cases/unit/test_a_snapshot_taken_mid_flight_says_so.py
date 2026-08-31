"""The report is composed with work STILL ALIVE, and nothing said so (V2-397).

Measured across the 215 archived reports that include `quiescence`:

    settled: True   84
    settled: False 131      ← 61 %, con la espera agotada en el tope (mediana 60,2 s)

and of those 131, **130** with the note «N worker(s) sin final al agotarse la espera: hay trabajo vivo». That is,
in six out of ten rounds the report was composed while a worker was still working — still needing to
write its findings, its sheet, and its widgets.

Two defects, only one underlying issue:

1. **THE ORDER.** `wait_for_quiescence` exists precisely for this, and its own docstring says so: «so the
   mechanism is read after the round, not during it». But in `run.py` it was called AFTER
   `mechanism_report`, so it protected the final columns (`worker_health`, `proactive_notes`,
   `search_returns`) but did not protect the CORE — the event flow from which `families_observed`,
   `widget_ops`, `sheet_instances`, `dropped_actions`, and the entire audit originate.

2. **THE WORDS.** `quiescence` did not appear even once in `judge.py`. The judge read «la hoja está vacía»,
   «ningún widget escribió» and scored it as a product failure, unaware that it was being shown a
   snapshot taken halfway through the work.

It is not INFRA and cannot be: canceling six out of ten rounds would leave the board unmeasured and hide
real defects behind it. It is a WARNING, and the warning has to reach the person doing the scoring.
"""
import ast
from pathlib import Path

from tests.use_cases.e2e.agent import judge as J, verify as V


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


def _run_src() -> str:
    return Path("tests/use_cases/e2e/agent/run.py").read_text()


# ── 1. the order ───────────────────────────────────────────────────────────────────────────────────────────

def _linea_de(nombre: str) -> int:
    """First line of `_run_scenario` where `nombre` is CALLED (AST, not `in src`: the name also appears
    in comments, and the guard must measure the property, not presence — V2-396 learned this the hard way)."""
    tree = ast.parse(_run_src())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_run_scenario")
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) == nombre:
            return n.lineno
    raise AssertionError(f"«{nombre}» no se llama en _run_scenario")


def test_se_espera_al_silencio_ANTES_de_leer_el_tronco():
    assert _linea_de("wait_for_quiescence") < _linea_de("session_events"), (
        "el flujo de eventos se lee antes de esperar a que el motor calle: la auditoría entera sale "
        "de una foto sacada a media faena")


def test_y_ANTES_de_componer_el_informe():
    assert _linea_de("wait_for_quiescence") < _linea_de("mechanism_report")


# ── 2. the words ───────────────────────────────────────────────────────────────────────────────────────────

def test_una_ronda_con_trabajo_VIVO_se_le_dice_al_juez():
    txt = _texto(J.mechanism_facts({"quiescence": {
        "settled": False, "waited_s": 60.2, "pending_workers": 2,
        "note": "2 worker(s) sin final al agotarse la espera: hay trabajo vivo"}}))
    assert "A MEDIA FAENA" in txt
    assert "2 worker" in txt
    assert "no prueba" in txt


def test_una_ronda_que_SI_calló_no_dice_nada():
    """Sensitivity: a warning that always appears stops being a warning."""
    txt = _texto(J.mechanism_facts({"quiescence": {"settled": True, "waited_s": 6.0, "events": 300}}))
    assert "A MEDIA FAENA" not in txt


def test_sin_el_dato_tampoco_se_inventa():
    assert "A MEDIA FAENA" not in _texto(J.mechanism_facts({"results_sheet": {"n_named": 3}}))


# ── the phrase lives in verify, so it can be asserted without grep ─────────────────────────────────────────

def test_la_frase_es_una_funcion_y_no_una_condicion_suelta():
    assert V.measured_in_flight({"quiescence": {"settled": False, "pending_workers": 1,
                                                "waited_s": 60.2}})
    assert V.measured_in_flight({"quiescence": {"settled": True}}) == ""
    assert V.measured_in_flight({}) == ""


def test_el_motor_que_seguia_escribiendo_SIN_workers_tambien_cuenta():
    """The minority case (1 of 131) is something else: nobody alive, yet the store kept writing. It is still
    reported — what invalidates the snapshot is that it was taken in motion, not who was moving it."""
    frase = V.measured_in_flight({"quiescence": {"settled": False, "pending_workers": 0, "waited_s": 60.1}})
    assert frase and "seguía escribiendo" in frase


# ── the round is not canceled ─────────────────────────────────────────────────────────────────────────────

def test_NO_es_INFRA():
    """131 of 215 rounds have this form: canceling them would leave the board unmeasured and hide real
    defects behind it. The warning informs the person doing the scoring; it does not remove the score."""
    src = _run_src()
    assert "crashed = verifymod.measured_in_flight" not in src
