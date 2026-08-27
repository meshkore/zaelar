"""Un hallazgo SIN ENCARGO no puede presentarse como si fuera del que se está atendiendo (V2-377).

Medido en `best-plumber-same-day__es` (2026-08-27, 2/5). Mientras el operador pedía un fontanero de urgencias
en Madrid, entraron por la puerta de hallazgos estas notas:

    [SISTEMA] El navegador ha SACADO esto de la página, trabajando en «la tarea del navegador»:
              Audi A3 2004 — 1500 € — https://es.wallapop.com/...
    [SISTEMA] El navegador ha SACADO esto de la página, trabajando en «la tarea del navegador»:
              SEAT Leon — € 15.000 — https://www.autoscout24.es/...

Eran de la búsqueda de COCHES anterior, cuya pestaña seguía viva sobre autoscout24 (el log lo enseña: «🧭
página · SEAT Leon … AutoScout24» en mitad de la ronda del fontanero). El turno los ofreció como fontaneros
DOS veces, y el operador contestó «Perdona, yo no he pedido coches ni de coña jajaja».

El juez lo archivó como que zaelar «ignora la línea del prompt» y «presentó coches como candidatos». No los
ignoraba: **le dimos coches etiquetados como hallazgos de su encargo**. La frase «la tarea del navegador» se
lee como LA tarea, la de ahora, y ahí está el daño — un relleno nuestro afirmando una pertenencia que nadie
comprobó. Tercera vez en la tanda que una frase enlatada nuestra es la que miente (V2-176 «Hecho.», V2-209
«Aquí lo tienes»).

Y NO se calla el hallazgo: puede ser justo lo que el operador pidió hace un rato, y tirarlo sería V2-223 otra
vez. Se dice el hecho y se nombra el hueco (V2-127/V2-133).
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


# ── la ronda medida ────────────────────────────────────────────────────────────────────────────────────────

def test_una_pestaña_SIN_encargo_ya_no_dice_que_es_la_tuya():
    tid = tasks.create("")                      # la pestaña huérfana de la ronda anterior
    n = _nota(tid)
    assert "la tarea del navegador" not in n, "la etiqueta que se leía como «lo tuyo»"
    assert "NO dice a qué encargo pertenece" in n


def test_y_PROHIBE_ofrecerlo_como_resultado_de_lo_pedido():
    """El daño no fue no saberlo: fue ofrecer un Audi a quien pedía un fontanero, dos veces."""
    n = _nota(tasks.create(""))
    assert "NO se lo ofrezcas como resultado de lo que ha pedido" in n
    assert "búsqueda ANTERIOR" in n


def test_el_HALLAZGO_no_se_tira():
    """V2-223: lo que el navegador encuentra tiene que llegar a alguien. Puede ser lo que pidió hace un rato."""
    n = _nota(tasks.create(""))
    assert "Audi A3 2004" in n and "1500 €" in n


def test_le_dice_QUE_hacer_en_los_dos_casos():
    """Un dato sin lectura se vuelve a leer como candidato (doctrina de V2-240/V2-360)."""
    n = _nota(tasks.create(""))
    assert "nómbralo diciendo de dónde sale" in n
    assert "cállatelo y sigue con lo suyo" in n


# ── lo que NO cambia ───────────────────────────────────────────────────────────────────────────────────────

def test_una_tarea_CON_encargo_conserva_su_nota_de_siempre():
    """La sensibilidad que importa: el camino bueno es el 99 % de las veces y no puede tocarse."""
    tid = tasks.create("Busca un fontanero de urgencias en Madrid centro")
    n = _nota(tid)
    assert "ha SACADO esto de la página, trabajando en «Busca un fontanero" in n
    assert "NO dice a qué encargo pertenece" not in n
    assert "NÓMBRALO EN ESTE TURNO" in n


def test_un_encargo_de_SOLO_espacios_cuenta_como_sin_encargo():
    """`or` no basta: una cadena de espacios es verdadera y produciría una etiqueta VACÍA entre comillas
    —«trabajando en «»»— que es aún menos informativa que la vieja.

    ⚠️ La primera versión pasaba `tasks.create("   ")` y el desarme salió VERDE: `create` ya recorta, así que
    por ese camino el espacio nunca llega. El caso pasaba por el aseo del vecino, no por el guarda que dice
    medir. Se escribe en el registro DIRECTAMENTE, que es lo que `_hand_over` lee — y lo que otro camino
    podría dejar ahí mañana."""
    tid = tasks.create("un encargo cualquiera")
    tasks._tasks[tid]["goal"] = "   "
    assert (tasks.get(tid) or {}).get("goal") == "   ", "premisa: el espacio tiene que llegar al lector"
    n = _nota(tid)
    assert "NO dice a qué encargo pertenece" in n


def test_sin_ninguna_fila_con_nombre_manda_la_rama_de_pagina_vacia():
    """Las tres ramas conviven; la de la página que no da nada (V2-234) sigue siendo la suya."""
    tid = tasks.create("Busca un fontanero de urgencias en Madrid centro")
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    act_api._hand_over(tid, [{"title": "", "price": "1 €", "url": "https://x.invalid/cat"}])
    n = " ".join(brain_notes.drain())
    assert "NO ha sacado ni un resultado con nombre" in n
