"""When the errand sheet is not resolved, the prompt is composed as if there were nothing.

And that is the failure measured in V2-432: of the **48** rounds whose sheet eventually had rows with names, **45**
had turns in which the live block told the model that the task was still stuck — **257 turns**. The
model answered “nothing new” and the judge penalized it for denying what was in front of it.

The failure makes no noise: `_sheet_of_tab` returns `""`, `_sheet_has_rows` returns `False`, the results
face does not light up, and the result is indistinguishable from there truly being nothing. Without a line that
says so, the failure can only be inferred by cross-referencing when the sheet was filled with the text of each
prompt — which is what had to be done to find it.

It is emitted in `_sheet_of_tab` and not in each caller because BOTH resolution paths end there.
"""
from __future__ import annotations

import pytest

from nucleo.flash import errand_sheet as ES


@pytest.fixture
def _emitido(monkeypatch):
    vistos: list[dict] = []
    import voice.observer as OBS
    monkeypatch.setattr(OBS, "emit",
                        lambda kind, label, text="", role="", extra=None: vistos.append(
                            {"label": label, "extra": dict(extra or {})}))
    return vistos


def _sin_resolver(monkeypatch):
    """Neither a tab marker nor a session record: the exact signature of the failure."""
    import widgets.navegador.tasks as _t
    import nucleo.dispatch as _d
    monkeypatch.setattr(_t, "get", lambda *_a, **_k: {})
    monkeypatch.setattr(_d, "sheet_for_nav_task", lambda *_a, **_k: "")


def test_una_hoja_sin_resolver_lo_DICE(monkeypatch, _emitido):
    _sin_resolver(monkeypatch)
    assert ES._sheet_of_tab("6175ca-1") == ""
    assert _emitido and "SIN RESOLVER" in _emitido[0]["label"]
    assert _emitido[0]["extra"]["nav_task"] == "6175ca-1", "sin el id no se puede ir a mirar cuál era"


def test_una_hoja_que_SÍ_resuelve_no_dice_nada(monkeypatch, _emitido):
    """The sensitivity counterpart: a line emitted during every prompt composition is pure noise, and the live block
    is composed on every turn."""
    import widgets.navegador.tasks as _t
    monkeypatch.setattr(_t, "get", lambda *_a, **_k: {"sheet": "results::6175ca-1"})
    assert ES._sheet_of_tab("6175ca-1") == "results::6175ca-1"
    assert _emitido == []


def test_el_REGISTRO_como_respaldo_tampoco_avisa(monkeypatch, _emitido):
    """The second path is just as valid as the first: warning there would label working behavior as a failure."""
    import widgets.navegador.tasks as _t
    import nucleo.dispatch as _d
    monkeypatch.setattr(_t, "get", lambda *_a, **_k: {})
    monkeypatch.setattr(_d, "sheet_for_nav_task", lambda *_a, **_k: "results::6175ca-1")
    assert ES._sheet_of_tab("6175ca-1") == "results::6175ca-1"
    assert _emitido == []


def test_instrumentar_NO_puede_tumbar_el_prompt(monkeypatch):
    """The live block is composed on every turn: an exception here would leave the operator without the entire turn."""
    _sin_resolver(monkeypatch)
    import voice.observer as OBS
    monkeypatch.setattr(OBS, "emit", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ES._sheet_of_tab("6175ca-1") == ""


def test_live_blocks_sigue_usando_LA_MISMA_funcion():
    """The extraction cannot have left two copies: that is the debt this repo paid four times in one
    week, and here it would mean that the warning exists in one place while the prompt is composed with the other."""
    from nucleo.flash import live_blocks as LB
    assert LB._sheet_of_tab is ES._sheet_of_tab


# ── And the other half: RESOLVED, but not the one containing the rows ─────────────────────────────────────
def test_una_hoja_resuelta_y_VACIA_tambien_lo_dice(monkeypatch, _emitido):
    """Failing to resolve was already counted. Resolving to the WRONG box looked exactly like getting it right —
    and that was the case for `search-buy-guitar__es` (2026-08-28): `unresolved_errand_sheets.n` came out **0**, meaning
    it resolved, and yet there were six turns in which the model was not told it had anything, with fifteen
    candidates in the sheet. Without this line, the diagnosis remains “it resolved correctly and something happens afterward.”"""
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(LB, "boxes_of_tab", lambda *_a, **_k: ["results"])
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: {"items": []})
    assert LB._sheet_has_rows("6175ca-1") is False
    assert _emitido and "RESUELTA PERO VACÍA" in _emitido[0]["label"]
    assert _emitido[0]["extra"]["hoja"] == "results", "sin decir CUÁL caja miró no se puede comparar"


def test_una_hoja_resuelta_CON_filas_no_dice_nada(monkeypatch, _emitido):
    """The sensitivity counterpart: this is the healthy path and it is traversed on every turn."""
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(LB, "boxes_of_tab", lambda *_a, **_k: ["results::6175ca-1"])
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: {"items": [{"title": "Yamaha F370BL"}]})
    assert LB._sheet_has_rows("6175ca-1") is True
    assert _emitido == []


def test_una_lectura_que_REVIENTA_tampoco_se_calla(monkeypatch, _emitido):
    """The third silent path, and the one that remained. Measured on 2026-08-28 in `weekend-motor-events__es`: four
    blind turns with the TWO previous signals at zero — it neither failed to resolve nor found the empty box—, so
    the only possibility left was for the read to blow up and the `except` to swallow it.

    A failure that swallows itself is worse than a noisy one: it leaves the prompt saying there is nothing and
    the investigator with nothing to read.
    """
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(LB, "boxes_of_tab", lambda *_a, **_k: ["results::6175ca-1"])
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: (_ for _ in ()).throw(KeyError("items")))
    assert LB._sheet_has_rows("6175ca-1") is False
    assert _emitido and "ILEGIBLE" in _emitido[0]["label"]
    assert "KeyError" in _emitido[0]["extra"]["error"], "sin el error no hay nada que investigar"


def test_la_cara_dice_que_hay_filas_y_la_hoja_no_las_da(monkeypatch, _emitido):
    """The fourth path, and the only one that remained SILENT.

    The results face lights up with `_p["has_results"]` **OR** `_found_candidates`, and the `or` short-circuits:
    if the first is true, `_sheet_has_rows` is not called and its three warnings do not exist.
    Then `_sheet_top_rows` resolves on its own, finds no box with rows, and the turn comes out saying
    “it has already found something, but its names have not yet been written” — with the names written.

    Measured in `reorder-prescription__us` (2026-08-28): three turns at 32, 72, and 111 seconds AFTER the
    sheet had six pharmacies with names and addresses, told that there was something there and with zero rows. The model
    named zero of six, and the judge called it “a severe failure to provide that data.”
    """
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(LB, "boxes_of_tab", lambda *_a, **_k: ["results::d787b2-1"])
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: {"items": []})
    assert LB._sheet_top_rows("d787b2-1") == []
    # the warning lives in `errand_sheet` (its home: it concerns the errand sheet), and `live_blocks` calls it
    assert _emitido and "no las da" in _emitido[0]["label"]
    assert "d787b2-1" in _emitido[0]["extra"]["cajas"], "sin las cajas no se puede comparar con dónde están"


def test_y_cuando_SÍ_las_da_no_dice_nada(monkeypatch, _emitido):
    """The sensitivity counterpart: this is the healthy path and it is traversed on every turn with results."""
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(LB, "boxes_of_tab", lambda *_a, **_k: ["results::d787b2-1"])
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: {"items": [{"title": "CVS · 701 Van Ness Ave"}]})
    filas = LB._sheet_top_rows("d787b2-1")
    assert filas and "CVS" in filas[0]
    assert _emitido == []
