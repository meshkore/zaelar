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
    """Reescrito 2026-08-28 (V2-443), NO volteado. La propiedad es la misma —sin filas se le dice la verdad de
    lo que hay, ni un recital imposible ni una negativa— y lo que cambió es CUÁL es esa verdad.

    V2-330 la escribió como «YA HA ENCONTRADO algo», y sin filas eso solo se puede leer de `kept`: la cuenta
    que el propio worker reporta. Medido en `find-theatre-tickets__us` (2026-08-28), esa afirmación fue FALSA
    once veces en una ronda — `worker_outcome.found: []`, la hoja vacía en todas partes. La afirmación se
    marca ahora como lo que es (suya, sin comprobar) y el hecho nuestro —no ha llegado ni una fila— se dice
    en firme.
    """
    st = _estado("Busca una guitarra acústica", "v330-2", [])
    assert "DICE QUE YA TIENE CANDIDATOS" in st and "no la hemos comprobado" in st
    assert "NO ha llegado ni una fila" in st


def test_se_separa_NO_HA_LLEGADO_de_NO_HA_ENCONTRADO():
    """Reescrito 2026-08-28 (V2-443), NO volteado — y ésta es la reescritura que más importa entender.

    V2-330 prohibió «no ha encontrado nada» porque con el worker produciendo es lo contrario de lo que pasa, y
    eso sigue siendo cierto: el mundo puede estar lleno y nosotros no saberlo. Lo que la prohibición se llevaba
    por delante era la frase VERDADERA y útil —«todavía no ha llegado nada»—, que habla de la ENTREGA y es un
    hecho nuestro. Sin ella, la única salida que le quedaba al turno era afirmar que ya estaba sacando cosas.

    Así que no se levanta la prohibición: se parte en dos, que es lo que le permite al operador decidir si
    espera o cambia de sitio.
    """
    st = _estado("Busca una guitarra acústica", "v330-3", [])
    assert "«NO HA ENCONTRADO nada»" in st and "NO LO SABES" in st
    assert "«TODAVÍA NO HA LLEGADO nada» es cierto y puedes decirlo" in st


def test_no_se_le_deja_INVENTARSE_un_nombre():
    """El riesgo del arreglo por el otro lado: si se le dice «cuéntale que va bien» sin más, rellena el hueco."""
    st = _estado("Busca una guitarra acústica", "v330-4", [])
    assert "NO te inventes nombres" in st


def test_CON_filas_el_imperativo_de_siempre_sigue_intacto():
    """La sensibilidad que importa: este cambio NO puede quitarle la orden de contar cuando sí tiene qué."""
    st = _estado("Busca una guitarra acústica", "v330-5",
                 [{"title": "Guitarra Acústica Fender CD-60", "price": "120 €"}])
    assert "CUÉNTALE en este turno LO QUE ENCAJE" in st
    assert "LO QUE YA HA ENTREGADO" in st
    assert "Fender CD-60 — 120 €" in st
    assert "DICE QUE YA TIENE CANDIDATOS" not in st


def test_las_dos_ramas_son_EXCLUYENTES():
    """Una tarea no puede recibir las dos órdenes a la vez: sería la contradicción que V2-318 quitó."""
    con = _estado("Busca un monitor", "v330-6", [{"title": "Monitor MSI 27", "price": "100 €"}])
    sin = _estado("Busca otra cosa", "v330-7", [])
    assert ("CUÉNTALE en este turno LO QUE ENCAJE" in con) != ("CUÉNTALE en este turno LO QUE ENCAJE" in sin)
