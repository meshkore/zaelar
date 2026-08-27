"""Un verbo que va a una URL, sin la URL, decía solo la FORMA — y el worker reincidía (V2-369).

Medido en `rental-car-automatic-airport__es` (2026-08-27, ronda del supervisor, 2/5). Siete errores de
contrato con nuestros propios puentes en los tres primeros minutos, y dentro de ellos la medida que decide
este arreglo:

    t=32,4 s   nav_cli navigate: error: the following arguments are required: url
    t=74,3 s   nav_cli navigate: error: the following arguments are required: url     ← el MISMO, 42 s después
    t=90,0 s   nav_cli visit:    error: the following arguments are required: url

En la MISMA sesión, `worker_bridge act` pelado —que SÍ lleva pista guiada— falló una vez y **no se repitió**.
Los que llevan pista se corrigen; los que solo reciben el `usage:` reinciden. `_hint_for` cubría `type_at`,
`scroll` y `click_at` (las tres confusiones de aridad que midió V2-341) y no cubría ninguno de los verbos que
van a una dirección.

Lo que costó: el encargo no llegó a un solo sitio de alquiler. Lo que acabó en la hoja fueron los ocho
títulos de la página de resultados del buscador, y el juez los contó como candidatos y acusó al turno de no
entregarlos — el instrumento acusando al producto de no ofrecer «Requerimientos y cualificaciones del
alquiler» como si fuera un coche.

Es el contrato del nodo 4.20 otra vez: lo que el puente SABE, lo dice, y un fallo dice además cómo se sale.
"""
import subprocess
import sys

import pytest

from nucleo.nav_cli import _hint_for


def _pista(verbo: str) -> str:
    return _hint_for(f"nav_cli {verbo}")


@pytest.mark.parametrize("verbo", ["navigate", "open", "goto", "visit"])
def test_todo_verbo_de_direccion_dice_como_salir(verbo):
    """`open` y `goto` son ALIAS de `navigate` — cubrir solo el nombre canónico deja dos puertas abiertas."""
    p = _pista(verbo)
    assert p, f"«{verbo}» va a una dirección y no dice nada"
    assert "https://" in p, "sin un ejemplo con esquema, «entera» es una palabra"
    assert "MISMO comando" in p


@pytest.mark.parametrize("verbo", ["navigate", "visit"])
def test_la_pista_NOMBRA_al_verbo_que_falló(verbo):
    """Una pista que habla de otro comando manda a escribir el que no era."""
    assert f"`{verbo} https://" in _pista(verbo)


def test_la_pista_PROHIBE_repetirlo_igual():
    """Los 42 segundos entre los dos `navigate` pelados son esto: la reacción natural ante un fallo es
    repetir, y aquí repetir no puede funcionar NUNCA."""
    assert "NO lo repitas igual" in _pista("navigate")


def test_no_se_le_invita_a_inventarse_una_direccion():
    """El fallo simétrico, y sería peor: un worker que se saca una URL de la cabeza navega a una página que
    no existe y lo cuenta como un paso dado (V2-253: actuar con un argumento inventado)."""
    assert "no adivines" in _pista("navigate")


@pytest.mark.parametrize("verbo", ["click", "type", "extract", "snapshot", "look"])
def test_un_verbo_que_NO_va_a_una_direccion_no_recibe_esta_pista(verbo):
    """Sensibilidad por el otro lado: una pista sobre direcciones colgada de `click` es ruido, y un worker
    aprende a saltarse las pistas que no vienen a cuento."""
    assert "LA DIRECCIÓN" not in _pista(verbo)


def test_las_pistas_de_V2_341_siguen_donde_estaban():
    """Este cambio AÑADE una rama; si se lleva por delante las que ya había, cambia un defecto por tres."""
    assert "COORDENADAS" in _pista("type_at")
    assert "PÍXELES" in _pista("scroll")
    assert "COORDENADAS" in _pista("click_at")


def test_el_CLI_REAL_la_imprime_y_ANTES_del_usage():
    """El camino de verdad, no el predicado: `_hint_for` puede ser perfecto y no estar enchufado. Y el orden
    importa — un worker lee de arriba abajo, así que la salida tiene que llegar antes del muro de sintaxis
    que ya está mirando (es el contrato de `bridge_usage.guided`)."""
    r = subprocess.run([sys.executable, "-m", "nucleo.nav_cli", "navigate"],
                       capture_output=True, text=True)
    assert r.returncode == 2
    err = r.stderr
    assert "LA DIRECCIÓN" in err, "la pista no llega al worker"
    assert err.index("LA DIRECCIÓN") < err.index("usage:"), "la salida llega después del muro"
