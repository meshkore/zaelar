"""The writer resolved the sheet through two paths and the reader through one (V2-352).

Measured live on 2026-08-26, `search-buy-used-car` is around 12. The run came out **1/5**, and its #1 blocker was
“zaelar had real results in front of it for more than 4 minutes and repeatedly said there was nothing”: the
operator asked five times “do you have anything yet?” and received five negative answers while the sheet
accumulated TWELVE cars with a name, price, and link (Mercedes A-Class, Chrysler Sebring, Alfa Tonale, Golf Variant, BMW 520d…).

It was not the model. The DETERMINISTIC guard that exists precisely for this —`delivery.sheet_delivery_backstop`, V2-305—
fired its silence event NINE times, and V2-336 (which made the silence visible through its entries) left the
reason written in the event itself:

    38,0s  rows=0  goal=''   |   325,5s  rows=0  goal=''      ← all nine identical

`rows=0` with twelve rows in the sheet. They never reached the backstop.

THE ASYMMETRY. A task’s sheet is resolved from the browser tab, and there are TWO paths:

  · the tab’s SEAL (`tasks.get(tid)["sheet"]`) — durable, survives the worker (V2-281), but **is written
    only once, in `create()`**: if the record did not yet have a sealed sheet at that moment, it remains
    empty FOREVER (the comment in `tasks.create` itself says so);
  · the live-session REGISTRY (`dispatch.sheet_for_nav_task`) — can answer while the worker is alive.

The WRITER (`act_api._sheet_for`, which feeds `_hand_over`) uses both: seal, and if it is empty, registry.
That is why the twelve rows landed correctly in `results::9a37af-1`. The READERS —`_sheet_has_rows`, the
“HAS RESULTS” face, and `_sheet_top_rows`, which feeds the backstop— stopped at the first one:

    sheet = tasks.get(tid)["sheet"]
    if not sheet:
        return []          # ← blind

It writes correctly and reads incorrectly: the same pattern as V2-350 (two gates, different answers for the same
worker) and V2-348 (a branch missing on only one side). And the GHOST card that the harness reports in both runs is
the other symptom of the same zero: `tasks.create` warns that an unresolved sheet sends findings to the bare
`results` box, “the one that belongs to nobody”.

THE ORDER DOES NOT CHANGE, and that is deliberate: the seal comes first, because it is the only thing still there
when the worker is replaced or dies (V2-281). The registry is BACKUP, exactly as in the writer — no more, no less.
"""
import pytest

from nucleo.flash import live_blocks as LB

FILAS = [{"title": "MERCEDES-BENZ Clase A 200 d", "price": "39.900 €"},
         {"title": "CHRYSLER Sebring 200C 2.0CRD Limited", "price": "2.500 €"},
         {"title": "VOLKSWAGEN Golf Variant 2.0TDI Life 85kW", "price": "11.900 €"}]


@pytest.fixture
def plató(monkeypatch):
    """A tab, a sheet with rows, and a control for saying whether the tab has a seal or not.

    The ATTRIBUTES of the real modules are patched, never `sys.modules`: the readers execute
    `from widgets.navegador import tasks` INSIDE the function, and that reads the attribute from the already imported
    package, so replacing the `sys.modules` entry works only if nothing imported it beforehand — green in isolation and
    red with the full suite, which is how this was caught here.
    """
    from nucleo import dispatch as _disp
    from widgets.navegador import tasks as _t
    from widgets.results import data as _sd
    estado = {"sello": "", "registro": ""}
    monkeypatch.setattr(_t, "get", lambda tid: {"sheet": estado["sello"]} if tid == "t1" else None)
    monkeypatch.setattr(_t, "active_summaries",
                        lambda limit=3: [("t1", "Búscame un coche de segunda mano diésel por menos de 12.000 €")])
    monkeypatch.setattr(_sd, "view_data",
                        lambda sheet, *a, **k: {"items": FILAS} if sheet == "results::9a37af-1" else {"items": []})
    monkeypatch.setattr(_disp, "sheet_for_nav_task", lambda tid: estado["registro"])
    return estado


def test_con_sello_se_lee_por_el_sello(plató):
    """The usual path, unchanged: the seal takes precedence and the registry is not even queried (V2-281)."""
    plató["sello"] = "results::9a37af-1"
    plató["registro"] = "results::OTRA-COSA"
    assert LB._sheet_top_rows("t1", 3)
    assert "Clase A" in LB._sheet_top_rows("t1", 3)[0]
    assert LB._sheet_has_rows("t1") is True


def test_SIN_sello_el_lector_pregunta_al_registro_como_hace_el_escritor(plató):
    """The measured defect: the tab was created before its registry had a sheet, so the seal remained
    empty forever. The writer succeeds through the backup; the reader remained blind."""
    plató["sello"] = ""
    plató["registro"] = "results::9a37af-1"
    filas = LB._sheet_top_rows("t1", 3)
    assert filas, "rows=0 con doce coches en la hoja: es el silencio de las nueve veces"
    assert "Clase A" in filas[0]
    assert LB._sheet_has_rows("t1") is True


def test_y_entonces_el_backstop_de_entrega_SI_ve_las_filas(plató):
    """The full consequence, at the point where it was measured: `any_live_task_rows` is what the backstop consumes."""
    plató["sello"] = ""
    plató["registro"] = "results::9a37af-1"
    goal, filas = LB.any_live_task_rows(3)
    assert len(filas) == 3, "esto es el `rows=0` del evento de silencio, que salió nueve veces"
    assert "coche de segunda mano" in goal, "sin el encargo, el backstop no puede juzgar frescura"


def test_sin_sello_y_sin_registro_no_se_inventa_nada(plató):
    """The conservative side: two exhausted paths means “there is no sheet”, not just any sheet. Falling back to the bare
    `results` box would announce the rows from another task."""
    plató["sello"] = ""
    plató["registro"] = ""
    assert LB._sheet_top_rows("t1", 3) == []
    assert LB._sheet_has_rows("t1") is False
    assert LB.any_live_task_rows(3) == ("", [])


def test_una_hoja_que_existe_pero_esta_VACIA_no_es_un_hallazgo(plató):
    """Resolving the address is not the same as having rows: a newly opened sheet resolves correctly and contains nothing."""
    plató["sello"] = "results::recien-abierta"
    plató["registro"] = ""
    assert LB._sheet_top_rows("t1", 3) == []
    assert LB._sheet_has_rows("t1") is False
