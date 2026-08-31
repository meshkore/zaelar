"""The «YA HA ENCONTRADO» face must CARRY the rows it orders the turn to tell (V2-298).

Measured on `search-buy-guitar__es` (2026-08-24, round 21, judge verdict [alta]): the sheet held 27 named
candidates — Fender CD-60 at 120 €, Gibson Hummingbird, Crafter FX 550 — for 250 seconds before the last
turn, and the model answered «déjame ver si la ficha da la zona» when the operator pressed for them. The
judge's line: «El usuario no puede elegir lo que no ve.»

The model was not being lazy. The face's imperative said «CUÉNTASELO — QUÉ ha encontrado, con nombre y
precio» while the block carried only the COUNT («V2-278: cuántos, nunca DÓNDE» — a rule about not claiming
the SCREEN that had quietly swallowed the CONTENT too). The rows had reached the brain exactly once, as a
one-turn note four turns earlier; notes do not persist, so by the time the operator asked, the prompt held
an order the model could not follow. An instruction the prompt makes impossible is not an instruction.

The fix: the face reads the errand's sheet — durable, written by `intake.push` on every extraction, owned by
nobody's memory — and puts the top NAMED rows in the block itself. WHAT was found, never WHERE it lives:
V2-278's boundary (never claim «en pantalla» / «en la hoja») stays exactly where it was.
"""
import pytest

from nucleo.flash import live_blocks as LB
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    yield
    T._tasks.clear()


def _sheet_with(sheet: str, items: list[dict]):
    SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados", "items": items})


# ---------------------------------------------------------------- the helper, against a real sheet

def test_las_filas_salen_con_nombre_y_precio():
    tid = T.create("Busca una guitarra acústica", sheet="v298-1")
    _sheet_with("v298-1", [{"title": "Guitarra Acústica Fender CD-60", "price": "120 €"},
                           {"title": "Gibson Hummingbird Faded", "price": "150 €"}])
    rows = LB._sheet_top_rows(tid)
    assert rows == ["«Guitarra Acústica Fender CD-60 — 120 €»", "«Gibson Hummingbird Faded — 150 €»"]


def test_una_fila_sin_precio_DICE_que_no_lo_tiene():
    """REVERSED by V2-360, and preserved here so that the decision change remains where the previous one was.

    It said: «una fila sin precio sale solo con su nombre — inventar una puntuación « — » alrededor de nada se
    leería como un dato ausente mal dicho». The first half remains true (the row is NOT discarded: without a
    price it is still a finding); the second turned out to be exactly backwards.

    Measured in `compare-insurance-quotes__es` (2026-08-27): only one of four rows had an amount, and the turn
    offered the other three as comparable quotes —«estas tres primeras ya te sirven»—. With only the title,
    the lack of a price can only be inferred from SILENCE, and a small model does not infer it: it fills it in.
    Saying it costs one word, which is the remedy from V2-127 and V2-133."""
    tid = T.create("Busca una guitarra", sheet="v298-2")
    _sheet_with("v298-2", [{"title": "Guitarra Acústica Crafter FX 550 EQ"}])
    assert LB._sheet_top_rows(tid) == ["«Guitarra Acústica Crafter FX 550 EQ — SIN PRECIO»"]
    # …and what did NOT change: the row is still present. Discarding it would hide a real finding.


def test_acotado_por_TAMANO_esto_va_a_un_prompt_no_a_una_pantalla():
    """V2-479 — the cap changes from FIVE to TWELVE, and the real bound is no longer a count.

    Five was conservative and cost two measured rounds: `search-buy-camera__es` with fourteen candidates (four
    of the five shown were accessories, V2-374) and `find-best-hotel-city__us` round 6 with twelve hotels, two
    below the operator's cap, showing the faces — the turn concluded «all well above your $150» about a set it
    had not seen in full. The latter is decisive: **V2-374 already warned about the hidden ones and reached the
    same conclusion**, meaning that telling it there are more is not showing them.

    The line that counts the remainder STAYS — cutting off and staying silent is V2-374's defect — and the SIZE
    ceiling (`_SHEET_ROWS_BUDGET`) is the real bound: a cap by units places no limit on very long titles.
    """
    tid = T.create("Busca monitores", sheet="v298-3")
    _sheet_with("v298-3", [{"title": f"Monitor candidato {i}", "price": "60 €"} for i in range(20)])
    filas = LB._sheet_top_rows(tid)
    cuerpo = [f for f in filas if f.startswith("«")]
    assert len(cuerpo) == 12, f"se mostraron {len(cuerpo)}: el tope no es el de V2-479"
    assert "8 candidato(s) más" in filas[-1]
    assert sum(len(f) for f in cuerpo) <= LB._SHEET_ROWS_BUDGET, "el bloque se pasó de su techo de tamaño"


def test_sin_hoja_no_hay_filas_y_no_hay_error():
    tid = T.create("Busca algo sin encargo detrás")     # no sheet stamped
    assert LB._sheet_top_rows(tid) == []


def test_un_titulo_largo_se_recorta_no_revienta_el_bloque():
    tid = T.create("Busca", sheet="v298-4")
    _sheet_with("v298-4", [{"title": "G" * 300, "price": "1 €"}])
    (row,) = LB._sheet_top_rows(tid)
    assert len(row) < 120


# ---------------------------------------------------------------- the wiring: the block the turn reads

def test_la_cara_LLEVA_las_filas_no_solo_la_orden_de_contarlas():
    """The round-21 defect verbatim: the imperative without the content. If this goes red the face is back
    to ordering the model to say what the prompt does not give it."""
    tid = T.create("Busca una guitarra acústica de segunda mano", sheet="v298-5")
    T.set_status(tid, "working")
    _sheet_with("v298-5", [{"title": "Guitarra Acústica Fender CD-60", "price": "120 €"}])
    state = "\n".join(LB.navegador_lines())
    assert "CUÉNTALE en este turno LO QUE ENCAJE" in state
    assert "LO QUE YA HA ENTREGADO" in state
    assert "Guitarra Acústica Fender CD-60 — 120 €" in state
    assert "déjame mirar" in state          # the canned escape it exists to forbid, named in the block


def test_con_amplitud_reportada_pero_hoja_vacia_la_cara_sale_SIN_filas():
    """Sensitivity the honest way round: `kept` says the worker FOUND, the sheet says what was WRITTEN.
    With breadth but no rows yet, inventing a «LO QUE YA HA ENTREGADO» list would be the V2-278 false claim
    again — the face must fire (there IS something to tell) but carry no rows it does not have."""
    from nucleo import dispatch as D

    class _Rec:
        status = "working"
        kept = 3
        nav_task = None

    tid = T.create("Busca un monitor", sheet="v298-6")
    T.set_status(tid, "working")
    rec = _Rec()
    rec.nav_task = tid
    D._SESSIONS["v298-fake"] = rec
    try:
        state = "\n".join(LB.navegador_lines())
        assert "YA HA ENCONTRADO" in state
        assert "LO QUE YA HA ENTREGADO" not in state
    finally:
        D._SESSIONS.pop("v298-fake", None)


def test_la_frontera_de_V278_sigue_la_cara_no_afirma_la_pantalla():
    """The rows say WHAT, never WHERE: the ban on claiming «en pantalla» must survive this change."""
    tid = T.create("Busca una guitarra", sheet="v298-7")
    T.set_status(tid, "working")
    _sheet_with("v298-7", [{"title": "Guitarra Acústica Fender CD-60", "price": "120 €"}])
    state = "\n".join(LB.navegador_lines())
    assert "NO digas que «lo tiene en pantalla»" in state


# ── V2-360: and the ABSENCE of an amount is also stated ─────────────────────────────────────────────────
#
# Measured in `compare-insurance-quotes__es` (2026-08-27, supervisor round, 2/5). Of the sheet's four rows,
# **only one had an amount**, and the turn announced:
#
#     «Direct Seguros, Allianz Direct, Génesis, MAPFRE y Pelayo… estas tres primeras ya te sirven»
#
# The judge, [alta]: «solo Direct tenía precio y las demás no tenían ni precio ni cobertura. Presentó como
# candidatos comparables lo que eran nombres sin datos».
#
# The face ALREADY ordered the correct behavior —«si pregunta por un dato que estas líneas no traen, di que aún no ha
# llegado»— but that covers the branch where the operator ASKS, whereas here the model offered it without anyone
# asking. Above all, a row without an amount was rendered as a title ALONE, so the model had to infer the lack from
# SILENCE.
#
# Naming the gap costs one word and closes the substitution — it is the same remedy as V2-127 («AUSENCIA de
# ubicación, dicha con todas las letras») and V2-133 («SIN paso reportado aún»). A phone number counts as actionable
# data, the same rule as `by_amount`: a result is a name and a way to act on it, never a price (V2-240).

def _rows(monkeypatch, items):
    from nucleo.flash import live_blocks as LB
    from widgets.navegador import tasks as _t
    from widgets.results import data as _sd
    monkeypatch.setattr(_t, "get", lambda tid: {"sheet": "results::c4202d-1"})
    monkeypatch.setattr(_sd, "view_data", lambda sheet, *a, **k: {"items": items})
    return LB._sheet_top_rows("t1", 5)


def test_una_fila_sin_importe_lo_DICE(monkeypatch):
    out = _rows(monkeypatch, [{"title": "Allianz Direct", "price": ""}])
    assert out == ["«Allianz Direct — SIN PRECIO»"], "el silencio obliga al modelo a deducir la falta"


def test_una_fila_CON_importe_no_cambia(monkeypatch):
    out = _rows(monkeypatch, [{"title": "Direct Seguros", "price": "152 €"}])
    assert out == ["«Direct Seguros — 152 €»"]


def test_un_TELEFONO_cuenta_como_dato_accionable(monkeypatch):
    """V2-240: a result is a name and a way to act on it, never a price. Marking a plumber with a phone number
    «SIN PRECIO» would call empty something that can in fact be used."""
    out = _rows(monkeypatch, [{"title": "Fontaneros 24H Madrid", "price": "", "tel": "612345678"}])
    assert out == ["«Fontaneros 24H Madrid — 612345678»"]


def test_la_mezcla_de_la_ronda_medida(monkeypatch):
    """One with a price and three without: exactly what the turn presented as comparable."""
    out = _rows(monkeypatch, [{"title": "Direct Seguros", "price": "152 €"},
                              {"title": "Allianz Direct", "price": ""},
                              {"title": "Génesis", "price": ""},
                              {"title": "MAPFRE", "price": ""}])
    assert out[0].endswith("152 €»")
    assert sum(1 for r in out if "SIN PRECIO" in r) == 3


def test_la_cara_dice_QUE_HACER_con_una_linea_sin_precio(monkeypatch):
    """The data alone, without the interpretation, is read again as a candidate. The rule goes INSIDE the same
    row block that already orders «di solo lo que RESPONDE a lo que pidió» (V2-348: the branch goes inside)."""
    from pathlib import Path
    src = Path("nucleo/flash/live_blocks.py").read_text()
    assert "marcada SIN PRECIO no es una opción" in src
    assert "ofrezcas como candidata" in " ".join(src.split())
