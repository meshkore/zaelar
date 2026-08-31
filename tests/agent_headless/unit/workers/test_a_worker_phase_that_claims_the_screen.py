"""“10 proposals in the results sheet” with the sheet EMPTY, and no marker at all (V2-358).

Measured in `search-buy-used-car` (2026-08-27 08:03, supervisor round, 1/5). At 60.9 s the
Process ring displayed this line, alongside others verified as “9 results on the page” and in the same type:

    Preparando entrega: 10 propuestas en la hoja de resultados

The sheet finished the round with **0 rows** (mechanism report: “0 candidate(s) with names out of 0 row(s)”). The
operator reads that, looks at the empty sheet, and both things cannot be true — and the one they believe is the one
written in system type.

It is the same disease as V2-357 (invented names), one layer further down: **something shaped like a fact that is
not one**. And the answer is the one V2-345 already gave for narration: **do not discard it, MARK it**. The worker
ASSERTS things — this house paid for one of its assertions to be taken as a verified fact (V2-249, “SCHEDULED
Reminder” without being able to schedule anything) — and in this ring its prose coexists with what we have actually
verified, so it must be distinguishable at a glance.

THE CUT IS NARROW in both directions, and both matter: it is marked only if the step NAMES THE SCREEN
**and** the sheet is empty. A mechanical step (“entering coches.net”) is left alone — marking them all would be noise
and would end with nobody looking at the marker — and if the sheet DOES have rows, the assertion is TRUE and is left alone too.

The list of forms is short and comes from OUR vocabulary — what the product calls its own sheet — not from an
external site. Here we do know exactly what it is called, which is precisely the opposite of the `dom.py` case,
where a list of texts would be doomed because tomorrow it would be another store.
"""
import pytest

from nucleo.flash import live_blocks as LB

HOJA = "results::19e54a-1"
CLAIM = "Preparando entrega: 10 propuestas en la hoja de resultados"


@pytest.fixture
def hoja(monkeypatch):
    """A control for specifying what is in the sheet."""
    from widgets.results import data as _sd
    estado = {"items": []}
    monkeypatch.setattr(_sd, "view_data", lambda sheet, *a, **k: {"items": estado["items"]})
    return estado


def test_la_linea_medida_se_marca(hoja):
    """The exact case: it asserts ten proposals about an empty sheet."""
    assert LB.worker_phase_is_a_claim(CLAIM, HOJA) is True


def test_con_la_hoja_LLENA_la_afirmacion_es_cierta_y_no_se_toca(hoja):
    """The side that matters: marking something true teaches the operator to ignore the marker."""
    hoja["items"] = [{"title": "VOLKSWAGEN Golf Variant 2.0TDI", "price": "11.900 €"}]
    assert LB.worker_phase_is_a_claim(CLAIM, HOJA) is False


def test_un_paso_MECANICO_no_se_marca_nunca(hoja):
    """It does not mention the screen, so it asserts nothing the operator can disprove."""
    for p in ("entrando en coches.net", "recorriendo la página", "9 resultados en la página",
              "conduciendo el navegador"):
        assert LB.worker_phase_is_a_claim(p, HOJA) is False, p


def test_filas_SIN_nombre_no_respaldan_nada(hoja):
    """A sheet with hollow rows is empty for these purposes: the same rule as `by_identity` — a row without a
    name is chrome, not a result."""
    hoja["items"] = [{"title": "", "price": "€ 10.475"}, {"title": "   ", "price": "€ 9.900"}]
    assert LB.worker_phase_is_a_claim(CLAIM, HOJA) is True


def test_sin_hoja_resuelta_NO_se_marca(hoja):
    """Marking because we cannot read would be making a blind accusation, and silence leaves the ring as it was."""
    assert LB.worker_phase_is_a_claim(CLAIM, "") is False


def test_las_otras_formas_de_nombrar_la_pantalla(hoja):
    for p in ("ya lo tienes en pantalla", "tres opciones en la hoja", "10 rows on screen"):
        assert LB.worker_phase_is_a_claim(p, HOJA) is True, p


def test_una_fase_vacia_no_es_una_afirmacion(hoja):
    assert LB.worker_phase_is_a_claim("", HOJA) is False


def test_el_anillo_lo_CABLEA_y_marca_con_el_mismo_simbolo():
    """Wiring guard over the source without comments: a decision without a caller is the fix that does not
    exist. And the symbol is the SAME as V2-345 — if the worker's narration is marked “💬” and its phase were
    marked differently, the operator would have to learn two conventions for the same fact."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/sheets.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    i = src.index("def record_phase")
    # Up to the NEXT function, not a window of N characters: this function's docstring is long and a fixed cut
    # left the call out — the guard failed with the wiring in place.
    _fin = src.find("\ndef ", i + 10)
    cuerpo = src[i:] if _fin < 0 else src[i:_fin]
    assert "worker_phase_is_a_claim(" in cuerpo, "nobody calls the detector: the marker can never appear"
    assert '"💬 "' in cuerpo, "the marker must be the same as the narration's (V2-345)"
