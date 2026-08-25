"""V2-330 — sin filas escritas, la cara NO puede ordenar que las cuente: era un imperativo imposible.

El bloque decía «CUÉNTALE en este turno LO QUE ENCAJE, con nombre y precio», y las filas (`_rows_bit`) solo se
añaden cuando la hoja YA tiene alguna con nombre. Sin ellas, el turno recibía una orden que no podía cumplir, y
el modelo contestaba lo único honesto que le quedaba: «te aviso en cuanto tenga algo».

MEDIDO sobre los turnos del plató (2026-08-25, de 21:00 en adelante), contando solo aquellos en los que esta
cara dispara:

    SIN filas en el prompt : 14 turnos · 79 % responden con espera
    CON filas en el prompt : 45 turnos · 42 % responden con espera

El 79 % no era desobediencia: era la única salida que le dejábamos. Y así se leía desde fuera — cinco de los
diez casos con mecanismo ≥4 y resultado ≤3 traían este veredicto, y el de `search-buy-camera__es` cita la
instrucción por su nombre:

    «el modelo ignora que la tarea ya tiene resultados (instrucción 'CUÉNTALE') y miente diciendo que sigue
     buscando»

Es exactamente la trampa que el docstring de `_sheet_top_rows` nombra desde V2-298 — «una instrucción que el
prompt hace imposible de cumplir no es una instrucción; es una trampa para el modelo Y para quien lea el
transcript»— y la escribimos nosotros.

⚠️ El 42 % restante (con filas delante y aun así esperando) es OTRO defecto, y no lo toca este cambio.
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


def _estado(goal, sheet, items):
    tid = T.create(goal, sheet=sheet)
    T.set_status(tid, "working")
    T.set_results(tid, {"conclusion": "", "items": [{"title": "algo"}]})   # la tarea SÍ encontró
    if items:
        SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados", "items": items})
    return "\n".join(LB.navegador_lines())


def test_sin_filas_NO_se_le_ordena_recitar():
    st = _estado("Busca una guitarra acústica", "v330-1", [])
    assert "CUÉNTALE en este turno LO QUE ENCAJE" not in st, (
        "se le pide con nombre y precio algo que el prompt no le da")


def test_sin_filas_se_le_dice_la_VERDAD_de_lo_que_hay():
    """Ni «no ha encontrado nada» (falso) ni un recital imposible: está produciendo y los nombres no están."""
    st = _estado("Busca una guitarra acústica", "v330-2", [])
    assert "YA HA ENCONTRADO algo" in st
    assert "sus nombres AÚN NO están escritos" in st


def test_y_la_frase_FALSA_queda_prohibida_por_su_nombre():
    """«Sigue sin resultados» es lo que decía el modelo, y es lo contrario de lo que pasa."""
    st = _estado("Busca una guitarra acústica", "v330-3", [])
    assert "no ha encontrado nada" in st and "es falso" in st


def test_no_se_le_deja_INVENTARSE_un_nombre():
    """El riesgo del arreglo por el otro lado: si se le dice «cuéntale que va bien» sin más, rellena el hueco."""
    st = _estado("Busca una guitarra acústica", "v330-4", [])
    assert "sin inventarte" in st


def test_CON_filas_el_imperativo_de_siempre_sigue_intacto():
    """La sensibilidad que importa: este cambio NO puede quitarle la orden de contar cuando sí tiene qué."""
    st = _estado("Busca una guitarra acústica", "v330-5",
                 [{"title": "Guitarra Acústica Fender CD-60", "price": "120 €"}])
    assert "CUÉNTALE en este turno LO QUE ENCAJE" in st
    assert "LO QUE YA HA ENTREGADO" in st
    assert "Fender CD-60 — 120 €" in st
    assert "sus nombres AÚN NO están escritos" not in st


def test_las_dos_ramas_son_EXCLUYENTES():
    """Una tarea no puede recibir las dos órdenes a la vez: sería la contradicción que V2-318 quitó."""
    con = _estado("Busca un monitor", "v330-6", [{"title": "Monitor MSI 27", "price": "100 €"}])
    sin = _estado("Busca otra cosa", "v330-7", [])
    assert ("CUÉNTALE en este turno LO QUE ENCAJE" in con) != ("CUÉNTALE en este turno LO QUE ENCAJE" in sin)
