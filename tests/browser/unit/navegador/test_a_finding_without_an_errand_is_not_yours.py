"""A finding WITHOUT AN ERRAND cannot be presented as though it belonged to the one being handled (V2-377).

Measured in `best-plumber-same-day__es` (2026-08-27, 2/5). While the operator was asking for an emergency plumber
in Madrid, these notes came in through the findings channel:

    [SISTEMA] El navegador ha SACADO esto de la página, trabajando en «la tarea del navegador»:
              Audi A3 2004 — 1500 € — https://es.wallapop.com/...
    [SISTEMA] El navegador ha SACADO esto de la página, trabajando en «la tarea del navegador»:
              SEAT Leon — € 15.000 — https://www.autoscout24.es/...

They came from the previous CAR search, whose tab was still active on autoscout24 (the log shows it: «🧭
page · SEAT Leon … AutoScout24» in the middle of the plumber round). The turn offered them as plumbers
TWICE, and the operator replied «Sorry, I didn't ask for cars at all haha».

The judge filed it as zaelar «ignores the prompt line» and «presented cars as candidates». It was not ignoring
them: **we gave it cars labeled as findings from its errand**. The phrase «the browser task» is read as THE task,
the current one, and that is where the harm lies — boilerplate from us asserting a belonging that nobody checked.
Third time in the batch that one of our canned phrases is the thing that lies (V2-176 «Done.», V2-209
«Here you go»).

And the finding is NOT silenced: it may be exactly what the operator asked for a little while ago, and throwing it
away would be V2-223 all over again. State the fact and name the gap (V2-127/V2-133).
"""
import pytest

from voice import brain_notes
from widgets.navegador import act_api, tasks

COCHES = [
    {"title": "Audi A3 2004", "price": "1500 €", "url": "https://es.wallapop.com/item/audi-a3"},
    {"title": "SEAT Leon", "price": "15.000 €", "url": "https://www.autoscout24.es/anuncios/seat-leon"},
]


@pytest.fixture(autouse=True)
def _limpio():
    brain_notes.drain()
    yield
    tasks._tasks.clear()
    brain_notes.drain()


def _nota(tid) -> str:
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    act_api._hand_over(tid, COCHES)
    notas = brain_notes.drain()
    assert notas, "sin nota no hay nada que medir"
    return " ".join(notas)


# ── the measured round ──────────────────────────────────────────────────────────────────────────────────────

def test_una_pestaña_SIN_encargo_ya_no_dice_que_es_la_tuya():
    tid = tasks.create("")                      # the orphaned tab from the previous round
    n = _nota(tid)
    assert "la tarea del navegador" not in n, "la etiqueta que se leía como «lo tuyo»"
    assert "NO dice a qué encargo pertenece" in n


def test_y_PROHIBE_ofrecerlo_como_resultado_de_lo_pedido():
    """The harm was not failing to know it: it was offering an Audi twice to someone asking for a plumber."""
    n = _nota(tasks.create(""))
    assert "NO se lo ofrezcas como resultado de lo que ha pedido" in n
    assert "búsqueda ANTERIOR" in n


def test_el_HALLAZGO_no_se_tira():
    """V2-223: what the browser finds has to reach someone. It may be what they asked for a little while ago."""
    n = _nota(tasks.create(""))
    assert "Audi A3 2004" in n and "1500 €" in n


def test_le_dice_QUE_hacer_en_los_dos_casos():
    """A piece of data without context gets read again as a candidate (the doctrine of V2-240/V2-360)."""
    n = _nota(tasks.create(""))
    assert "nómbralo diciendo de dónde sale" in n
    assert "cállatelo y sigue con lo suyo" in n


# ── what does NOT change ───────────────────────────────────────────────────────────────────────────────────

def test_una_tarea_CON_encargo_conserva_su_nota_de_siempre():
    """The sensitivity that matters: the good path is the case 99% of the time and cannot be touched."""
    tid = tasks.create("Busca un fontanero de urgencias en Madrid centro")
    n = _nota(tid)
    assert "ha SACADO esto de la página, trabajando en «Busca un fontanero" in n
    assert "NO dice a qué encargo pertenece" not in n
    assert "NÓMBRALO EN ESTE TURNO" in n


def test_un_encargo_de_SOLO_espacios_cuenta_como_sin_encargo():
    """`or` is not enough: a string of spaces is truthy and would produce an EMPTY label in quotation marks
    —«working on «»»— which is even less informative than the old one.

    ⚠️ The first version passed `tasks.create("   ")` and the teardown came out GREEN: `create` already trims, so
    the space never arrives by that route. The case went through the neighbor's cleanup, not the guard that claims
    to measure. Write DIRECTLY to the record, which is what `_hand_over` reads — and what another route could leave
    there tomorrow."""
    tid = tasks.create("un encargo cualquiera")
    tasks._tasks[tid]["goal"] = "   "
    assert (tasks.get(tid) or {}).get("goal") == "   ", "premisa: el espacio tiene que llegar al lector"
    n = _nota(tid)
    assert "NO dice a qué encargo pertenece" in n


def test_sin_ninguna_fila_con_nombre_manda_la_rama_de_pagina_vacia():
    """The three branches coexist; the one for a page that gives nothing (V2-234) remains its own."""
    tid = tasks.create("Busca un fontanero de urgencias en Madrid centro")
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    act_api._hand_over(tid, [{"title": "", "price": "1 €", "url": "https://x.invalid/cat"}])
    n = " ".join(brain_notes.drain())
    assert "NO ha sacado ni un resultado con nombre" in n
