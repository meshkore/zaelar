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
    """INVERTIDO por V2-360, y se conserva aquí para que el cambio de decisión quede donde estaba la anterior.

    Decía: «una fila sin precio sale solo con su nombre — inventar una puntuación « — » alrededor de nada se
    leería como un dato ausente mal dicho». La primera mitad sigue siendo cierta (la fila NO se descarta: sin
    precio también es un hallazgo); la segunda resultó ser justo al revés.

    Medido en `compare-insurance-quotes__es` (2026-08-27): de cuatro filas solo una traía importe, y el turno
    ofreció las otras tres como presupuestos comparables —«estas tres primeras ya te sirven»—. Con el título a
    secas, la falta de precio solo se puede deducir del SILENCIO, y un modelo pequeño no la deduce: la rellena.
    Decirlo cuesta una palabra, que es el remedio de V2-127 y V2-133."""
    tid = T.create("Busca una guitarra", sheet="v298-2")
    _sheet_with("v298-2", [{"title": "Guitarra Acústica Crafter FX 550 EQ"}])
    assert LB._sheet_top_rows(tid) == ["«Guitarra Acústica Crafter FX 550 EQ — SIN PRECIO»"]
    # …y lo que NO cambió: la fila sigue estando. Descartarla escondería un hallazgo real.


def test_acotado_a_cinco_esto_va_a_un_prompt_no_a_una_pantalla():
    tid = T.create("Busca monitores", sheet="v298-3")
    _sheet_with("v298-3", [{"title": f"Monitor candidato {i}", "price": "60 €"} for i in range(12)])
    assert len(LB._sheet_top_rows(tid)) == 5


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


# ── V2-360: y la AUSENCIA de importe también se dice ────────────────────────────────────────────────────
#
# Medido en `compare-insurance-quotes__es` (2026-08-27, ronda del supervisor, 2/5). De las cuatro filas de la
# hoja **solo una traía importe**, y el turno anunció:
#
#     «Direct Seguros, Allianz Direct, Génesis, MAPFRE y Pelayo… estas tres primeras ya te sirven»
#
# El juez, [alta]: «solo Direct tenía precio y las demás no tenían ni precio ni cobertura. Presentó como
# candidatos comparables lo que eran nombres sin datos».
#
# La cara YA ordenaba lo correcto —«si pregunta por un dato que estas líneas no traen, di que aún no ha
# llegado»— pero eso cubre la rama en que el operador PREGUNTA, y aquí el modelo lo ofreció sin que nadie
# preguntara. Y sobre todo: una fila sin importe se renderizaba como un título A SECAS, así que el modelo
# tenía que deducir la falta del SILENCIO.
#
# Nombrar el hueco cuesta una palabra y cierra la sustitución — es el mismo remedio que V2-127 («AUSENCIA de
# ubicación, dicha con todas las letras») y V2-133 («SIN paso reportado aún»). Un teléfono cuenta como dato
# accionable, misma regla que `by_amount`: un resultado es un nombre y una forma de actuar sobre él, nunca un
# precio (V2-240).

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
    """V2-240: un resultado es un nombre y una forma de actuar sobre él, nunca un precio. Marcar «SIN PRECIO»
    un fontanero con teléfono sería llamar hueco a lo que sí se puede usar."""
    out = _rows(monkeypatch, [{"title": "Fontaneros 24H Madrid", "price": "", "tel": "612345678"}])
    assert out == ["«Fontaneros 24H Madrid — 612345678»"]


def test_la_mezcla_de_la_ronda_medida(monkeypatch):
    """Una con precio y tres sin él: exactamente lo que el turno presentó como comparable."""
    out = _rows(monkeypatch, [{"title": "Direct Seguros", "price": "152 €"},
                              {"title": "Allianz Direct", "price": ""},
                              {"title": "Génesis", "price": ""},
                              {"title": "MAPFRE", "price": ""}])
    assert out[0].endswith("152 €»")
    assert sum(1 for r in out if "SIN PRECIO" in r) == 3


def test_la_cara_dice_QUE_HACER_con_una_linea_sin_precio(monkeypatch):
    """El dato solo, sin la lectura, se vuelve a leer como candidato. La regla va DENTRO del mismo bloque de
    filas que ya ordena «di solo lo que RESPONDE a lo que pidió» (V2-348: la bifurcación va dentro)."""
    from pathlib import Path
    src = Path("nucleo/flash/live_blocks.py").read_text()
    assert "marcada SIN PRECIO no es una opción" in src
    assert "ofrezcas como candidata" in " ".join(src.split())
