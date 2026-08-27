"""La cara cortaba en cinco y se callaba, así que para el turno esas cinco ERAN la hoja (V2-374).

Segunda mitad de V2-234, que la nota del navegador aplica desde entonces («y N filas más de la misma página»)
y esta superficie nunca tuvo.

Medido en `search-buy-camera__es` (2026-08-27, 2/5). La hoja tenía **CATORCE** candidatos con nombre —Canon
EOS 4000D, Nikon D3500, D5300, Canon 7D, EOS 1200D, Nikon D50, D800— y las cinco que llegaron al último turno,
leídas de su prompt, fueron:

    «Cámara profesional Canon EOS 550D — 200 €»; «Funda Hama para cámara réflex — 9 €»;
    «Mochila para cámara réflex — 25 €»; «Arnés para cámara — 15 €»; «Funda Kata e-702 — 25 €»

Cuatro de cinco eran ACCESORIOS. Zaelar cerró la conversación ofreciendo la funda de 9 € y la mochila de 25 €
a quien pedía una réflex por menos de 400, y el watchdog lo había cantado en vivo: «Esos son accesorios, no
cámaras».

**No hay nada que reordenar, y conviene decirlo porque era mi primera hipótesis y era falsa**: reproducido
contra el pipeline real (`dedupe_by_url` → `by_identity` → `by_amount`), el orden que llega es el del DOM,
fielmente — fue Wallapop quien puso una funda la segunda. Tampoco eran dos hojas distintas, que fue la
segunda hipótesis: las dos superficies leen la misma.

Lo que faltaba era decir que había más. Con nueve filas escondidas y sin saberlo, «di solo lo que RESPONDE a
lo que pidió» es una instrucción que el prompt hace difícil de cumplir — el modelo no puede elegir entre lo
que no ve (V2-330).
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
    """Contar el resto no puede costar ni una de las que sí se listan."""
    filas = LB._sheet_top_rows(hoja(CAMARAS), 5)
    assert filas[0] == "«Cámara profesional Canon EOS 550D — 200 €»"
    assert sum(1 for f in filas if f.startswith("«")) == 5


def test_con_la_hoja_JUSTA_no_se_dice_nada(hoja):
    """Sensibilidad: cinco de cinco no esconde nada, y una coletilla que sale siempre deja de ser señal."""
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
    """Una fila sin título no tiene identidad de cosa (V2-234), así que contarla inflaría el número y le haría
    creer que le escondemos hallazgos que no existen."""
    items = CAMARAS[:5] + [{"title": "", "price": "1 €"}, {"title": "  ", "price": "2 €"}]
    filas = LB._sheet_top_rows(hoja(items), 5)
    assert len(filas) == 5, filas


def test_la_linea_NO_afirma_la_pantalla(hoja):
    """V2-278: nunca decir dónde vive. Dice que están en la HOJA —una escritura que ya ocurrió, igual que las
    otras cinco— y nunca «en pantalla»."""
    filas = LB._sheet_top_rows(hoja(CAMARAS), 5)
    assert "en pantalla" not in filas[-1]


def test_el_tope_de_UNO_tambien_cuenta(hoja):
    filas = LB._sheet_top_rows(hoja(CAMARAS), 1)
    assert len(filas) == 2 and "13 candidato(s) más" in filas[-1]


def test_sin_hoja_no_hay_filas_ni_coletilla():
    tid = T.create("un encargo sin hoja detrás")
    assert LB._sheet_top_rows(tid, 5) == []
    T._tasks.clear()
