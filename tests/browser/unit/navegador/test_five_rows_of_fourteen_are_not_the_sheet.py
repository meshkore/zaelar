"""The face cut off at five and said nothing, so for the turn those five WERE the sheet (V2-374).

Second half of V2-234, which the browser note has applied ever since (“and N more rows from the same page”)
and this surface never had.

Measured in `search-buy-camera__es` (2026-08-27, 2/5). The sheet had **FOURTEEN** named candidates —Canon
EOS 4000D, Nikon D3500, D5300, Canon 7D, EOS 1200D, Nikon D50, D800— y las cinco que llegaron al último turno,
read from its prompt, were:

    “Canon EOS 550D professional camera — 200 €”; “Hama case for SLR camera — 9 €”;
    “SLR camera backpack — 25 €”; “Camera harness — 15 €”; “Kata e-702 case — 25 €”

Four of the five were ACCESSORIES. Zaelar ended the conversation by offering the €9 case and the €25 backpack
to someone asking for an SLR for less than 400, and the watchdog had called it out live: “Those are accessories, not
cameras”.

**There is nothing to reorder, and it is worth saying so because it was my first hypothesis and it was false**: replayed
against the real pipeline (`dedupe_by_url` → `by_identity` → `by_amount`), the order that arrives is the DOM order,
faithfully — Wallapop was the one that put a case second. Nor were they two different sheets, which was the
second hypothesis: both surfaces read the same one.

What was missing was saying that there were more. With nine rows hidden and without knowing it, “give only what
ANSWERS what was asked for” is an instruction that the prompt makes difficult to follow — the model cannot choose among what
it cannot see (V2-330).
"""
import pytest

from nucleo.flash import live_blocks as LB
from widgets.navegador import tasks as T
from widgets.results import data as SHEET

CAMARAS = [
    {"title": "Cámara profesional Canon EOS 550D", "price": "200 €"},
    {"title": "Funda Hama para cámara réflex", "price": "9 €"},
    {"title": "Mochila para cámara réflex", "price": "25 €"},
    {"title": "Arnés para cámara", "price": "15 €"},
    {"title": "Funda Kata e-702 para cámara", "price": "25 €"},
    {"title": "Canon EOS 4000D + kit", "price": "230 €"},
    {"title": "Nikon D3500 Kit", "price": "320 €"},
    {"title": "Nikon D5300 Reflex", "price": "280 €"},
    {"title": "Canon 7D", "price": "350 €"},
    {"title": "Canon EOS 1200D + kit", "price": "180 €"},
    {"title": "Nikon D50 Plata", "price": "70 €"},
    {"title": "Nikon D800", "price": "390 €"},
    {"title": "Canon EOS 4000D + kit", "price": "225 €"},
    {"title": "Nikon D5100 Reflex", "price": "150 €"},
]


@pytest.fixture
def hoja():
    def _poner(items, sheet="v374-hoja"):
        tid = T.create("una cámara réflex de segunda mano por menos de 400", sheet=sheet)
        SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados", "items": items})
        return tid
    yield _poner
    T._tasks.clear()


def test_la_ronda_medida_ya_DICE_que_hay_nueve_mas(hoja):
    filas = LB._sheet_top_rows(hoja(CAMARAS), 5)
    assert len(filas) == 6, "cinco candidatos y la línea que cuenta el resto"
    assert "9 candidato(s) más" in filas[-1]


def test_las_cinco_filas_SIGUEN_saliendo_enteras(hoja):
    """Counting the remainder must not cost even one of the rows that are actually listed."""
    filas = LB._sheet_top_rows(hoja(CAMARAS), 5)
    assert filas[0] == "«Cámara profesional Canon EOS 550D — 200 €»"
    assert sum(1 for f in filas if f.startswith("«")) == 5


def test_con_la_hoja_JUSTA_no_se_dice_nada(hoja):
    """Sensitivity: five out of five hides nothing, and a suffix that always appears ceases to be a signal."""
    filas = LB._sheet_top_rows(hoja(CAMARAS[:5]), 5)
    assert len(filas) == 5
    assert not any("más" in f for f in filas)


def test_con_MENOS_filas_que_el_tope_tampoco(hoja):
    filas = LB._sheet_top_rows(hoja(CAMARAS[:2]), 5)
    assert len(filas) == 2


def test_una_sola_escondida_se_dice_igual(hoja):
    filas = LB._sheet_top_rows(hoja(CAMARAS[:6]), 5)
    assert "1 candidato(s) más" in filas[-1]


def test_las_filas_SIN_NOMBRE_no_se_cuentan_como_candidatos(hoja):
    """A row without a title has no thing identity (V2-234), so counting it would inflate the number and make it
    believe that we are hiding findings that do not exist."""
    items = CAMARAS[:5] + [{"title": "", "price": "1 €"}, {"title": "  ", "price": "2 €"}]
    filas = LB._sheet_top_rows(hoja(items), 5)
    assert len(filas) == 5, filas


def test_la_linea_NO_afirma_la_pantalla(hoja):
    """V2-278: never say where it lives. It says that they are in the SHEET —a write that already happened, just like the
    other five— and never “on screen”."""
    filas = LB._sheet_top_rows(hoja(CAMARAS), 5)
    assert "en pantalla" not in filas[-1]


def test_el_tope_de_UNO_tambien_cuenta(hoja):
    filas = LB._sheet_top_rows(hoja(CAMARAS), 1)
    assert len(filas) == 2 and "13 candidato(s) más" in filas[-1]


def test_sin_hoja_no_hay_filas_ni_coletilla():
    tid = T.create("un encargo sin hoja detrás")
    assert LB._sheet_top_rows(tid, 5) == []
    T._tasks.clear()
