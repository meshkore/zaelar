"""An empty page WITH prior delivery is not “the search is finding nothing” (V2-370).

Measured in `search-buy-bicycle__es` (2026-08-27) — and what makes it serious is that it was the BEST round in days:
result 4, mechanism 4, two real bikes delivered (Trek 6500 SLR at €290, Specialized at €290, both
size M and below the cap). The last turn ended like this:

    «La página esa no está trayendo lo que pediste, así que la dejo.»

The judge filed it [high] as a false claim, and it is. But **the model did not say it: we did.**
The note that drives `_hand_over` when a page returns not even one named row says, literally, “that page is not
providing what was requested,” and the turn repeated it almost word for word.

Read that turn’s prompt before accusing anyone: it contained all FIVE rows with names and prices and the instruction
to count them. It was not disobedience — it was choosing between two true facts, and the one carrying an imperative was the note’s.
It is V2-222 all over again: two records describing ONE errand, and the prompt with no branch for the
middle case.

The note was written for an IN-PROGRESS search, where saying “this site provides nothing; I’m switching” is exactly
right (V2-234). Triggered at the end, after something has been delivered, that same sentence becomes the verdict
on the entire errand and erases a result that does exist. What changes is not the FACT —the page still provides
nothing, and omitting that would leave the turn unable to explain why nothing new is arriving— but its SCOPE.
"""
import pytest

from voice import brain_notes
from widgets.navegador import act_api, tasks
from widgets.results import data as SHEET

# The page that provides nothing: navigation links from the website itself, without a single title.
CROMO = [
    {"title": "", "price": "300EUR", "url": "https://tienda.invalid/bicicletas/hasta-300"},
    {"title": "", "price": "", "url": "https://tienda.invalid/ayuda/envios"},
]
# What had ALREADY been delivered, exactly as it appeared in the round.
ENTREGADO = [
    {"title": "Bicicleta montaña Trek 6500 SLR mejorada Talla M", "price": "290 €",
     "url": "https://tienda.invalid/anuncio/trek"},
    {"title": "Bicicleta de Montaña Specialized", "price": "290 €",
     "url": "https://tienda.invalid/anuncio/specialized"},
]


@pytest.fixture
def task():
    tid = tasks.create("Busca una bicicleta de montaña de segunda mano en buen estado, talla M",
                       sheet="v370-hoja")
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    yield tid
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()


def _nota(tid) -> str:
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    act_api._hand_over(tid, CROMO)
    notas = brain_notes.drain()
    assert notas, "sin nota no hay nada que medir"
    return " ".join(notas)


def _sembrar_hoja(items):
    SHEET.apply_action("present", {"sheet": "v370-hoja", "title": "Resultados", "items": items})


# ── con entrega detrás: el alcance es la PÁGINA ────────────────────────────────────────────────────────────

def test_la_ronda_medida_ya_no_licencia_el_veredicto_falso(task):
    """The phrase STILL appears, and it has to appear: it is NAMED in order to prohibit it. A “don’t say that” without
    saying what “that” is gives the model nothing to compare against (V2-221). What is checked is that it arrives
    as a prohibition and not as an instruction, so the distance between “NEVER” and the phrase is the data."""
    _sembrar_hoja(ENTREGADO)
    n = _nota(task)
    assert "no está dando lo que pidió" not in n, "la ORDEN vieja no puede seguir ahí"
    i_nunca, i_frase = n.find("NUNCA"), n.find("no está trayendo lo que pediste")
    assert i_nunca >= 0 and i_frase > i_nunca, "la frase tiene que venir DETRÁS del NUNCA que la prohíbe"
    assert "ni que lo dejas" in n


def test_el_HECHO_de_la_pagina_se_sigue_contando(task):
    """Keeping quiet about the empty page would be the opposite failure: the turn would be unable to explain why
    nothing new is arriving, which is exactly what the operator is waiting to hear."""
    _sembrar_hoja(ENTREGADO)
    n = _nota(task)
    assert "no ha salido ningún resultado con nombre" in n
    assert "enlaces de navegación" in n


def test_dice_que_la_busqueda_NO_ha_terminado(task):
    _sembrar_hoja(ENTREGADO)
    n = _nota(task)
    assert "NO el final de la búsqueda" in n
    assert "YA tiene resultados" in n


# ── sin nada entregado: la redacción de siempre, INTACTA ───────────────────────────────────────────────────

def test_con_la_hoja_VACIA_la_nota_no_cambia(task):
    """The safeguard that supports the fix. Without prior delivery, “that page is not providing what was requested”
    is TRUE and useful — this is V2-234, and losing it would trade one defect for another: the turn would once again serve
    navigation links as though they were findings."""
    _sembrar_hoja([])
    n = _nota(task)
    assert "esa página no está dando lo que pidió" in n
    assert "NO el final de la búsqueda" not in n


def test_una_fila_SIN_NOMBRE_no_cuenta_como_entrega(task, monkeypatch):
    """A row without a title has no thing identity (V2-234), so it cannot support “I have already given you
    something”: if it counted, merely having navigation links in the sheet would be enough to silence the warning.

    ⚠️ This case was first written by seeding the sheet with a row without a title, and dismantling it exposed the issue: removing
    the name filter did NOT make it fail. The reason is that the sheet itself already discards untitled rows
    when writing them (`apply_action("present")` throws them away), so through that path the case could never reach the
    branch it claims to measure. It is measured where the filter lives, against the data the sheet RETURNS. The check
    is still worthwhile —it is defense in depth around a reader that does not control its source— but the
    test has to tell the truth about what it iterates over."""
    import widgets.results.data as _rd
    monkeypatch.setattr(_rd, "view_data",
                        lambda *a, **k: {"items": [{"title": "  ", "price": "10 €"}]})
    assert act_api._sheet_already_named(task) is False


def test_una_pagina_QUE_SI_DA_sigue_por_su_rama(task):
    """The third branch is untouched: with named rows, the V2-223 finding note takes precedence."""
    _sembrar_hoja(ENTREGADO)
    act_api._HANDED.pop(task, None)
    brain_notes.drain()
    act_api._hand_over(task, ENTREGADO)
    n = " ".join(brain_notes.drain())
    assert "ha SACADO esto de la página" in n
    assert "NO el final de la búsqueda" not in n


# ── el lector ──────────────────────────────────────────────────────────────────────────────────────────────

def test_sin_poder_leer_la_hoja_se_cae_a_la_redaccion_de_siempre(task, monkeypatch):
    """A conservative direction, and a reasoned one: without prior delivery the old wording is CORRECT, and this case only
    exists when there is prior delivery. The reverse —keeping the empty page quiet just in case—would break the common case."""
    import widgets.results.data as _rd
    monkeypatch.setattr(_rd, "view_data", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hoja rota")))
    assert act_api._sheet_already_named(task) is False


def test_una_tarea_SIN_hoja_propia_no_hereda_la_entrega_de_otro_encargo():
    """La hoja PELADA es compartida (V2-259), así que leerla aquí dejaría que lo entregado por OTRO encargo
    callara el aviso de éste. Lo cazó un test que ya existía —la hoja pelada acumula filas dentro de la misma
    suite— y es el mismo defecto en producción, solo que ahí no se ve: `_sheet_of` cae a "" fail-soft."""
    tid = tasks.create("una tarea sin encargo detrás")     # without `sheet=`
    _sembrar_hoja(ENTREGADO)                               # another sheet, with delivery in it
    SHEET.apply_action("append", {"sheet": "", "items": ENTREGADO})   # and the BARE one, too
    try:
        assert act_api._sheet_already_named(tid) is False
    finally:
        act_api._HANDED.pop(tid, None)
        brain_notes.drain()


def test_el_lector_mira_la_HOJA_del_encargo_y_no_el_registro_de_la_tarea(task):
    """The same choice as V2-299 and for the same reason: `has_results` exists only if someone called
    `set_results`, and there the line came to say “WITHOUT bringing anything” with 21 rows in the sheet."""
    _sembrar_hoja(ENTREGADO)
    assert act_api._sheet_already_named(task) is True
    assert not (tasks.get(task) or {}).get("results"), "la premisa: el registro está vacío y la hoja no"
