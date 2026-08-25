"""V2-325 — pedirle ayuda a un puente del worker no es equivocarse, y `widget_cli` lo trataba como error.

MEDIDO en los logs de sesión del plató (2026-08-25, vuelta completa):

    332 sesiones de worker · 81 usan `nav_cli` · 5 llegan a `widget_cli` · de esas 5, TRES mueren en Exit code 2

Y el paso que las mata es el PRIMERO. Del log de una de ellas, literal:

    [161] · paso ⚠️ error    Exit code 2 comando desconocido: --help
    [163] · paso ⚠️ error    Exit code 2 <manual de uso>

El worker escribe `widget_cli --help` —lo que hace cualquiera con una herramienta nueva—, recibe «comando
desconocido» con código 2, prueba otra cosa, vuelve a fallar y abandona. Su hermano `nav_cli` contesta `--help`
con exit 0 porque usa argparse, y es justamente el puente que sí se usa (81 de 332).

POR QUÉ IMPORTA MÁS DE LO QUE PARECE: `widget_cli` es la única forma que tiene un worker de poner en la hoja lo
que aprende ABRIENDO fichas. Sin ella, la hoja solo se llena con lo que el extractor automático saca de un
listado. Medido en la ronda del seguro (20:22-20:32): el juez ve 8 opciones reunidas, la hoja recibe 2, y el
prompt del cerebro llevó las MISMAS dos filas nueve turnos seguidos.

⚠️ LO QUE ESTE ARREGLO NO PRUEBA: que los workers vayan a usar la hoja ahora. Prueba que se les quitó una
fricción medida en el primer gesto. Lo otro se mide DESPUÉS, en el caso — que es la regla que costó cuatro
arreglos aprender hoy (ver `CLAUDE.md`, V2-322).
"""
import subprocess
import sys

import pytest

_CLI = [sys.executable, "-m", "nucleo.widget_cli"]


def _correr(*args):
    p = subprocess.run(_CLI + list(args), capture_output=True, text=True, timeout=30)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


@pytest.mark.parametrize("verbo", ["--help", "-h", "help", "ayuda", "--ayuda", "-?", "/?"])
def test_pedir_ayuda_SALE_BIEN(verbo):
    """Cero, no dos. El código es la mitad del mensaje: un modelo que ve `Exit code 2` concluye que se equivocó
    de herramienta, no que le acaban de contestar."""
    rc, out = _correr(verbo)
    assert rc == 0, f"`{verbo}` salió con {rc}"
    assert "widget_cli" in out and "read" in out


def test_y_TRAE_el_manual_no_solo_un_codigo():
    rc, out = _correr("--help")
    assert rc == 0
    for pista in ("read", "data", "show", "close", "@"):
        assert pista in out, f"el manual no menciona «{pista}»"


def test_un_verbo_QUE_NO_EXISTE_sigue_fallando():
    """La sensibilidad: si esto pasa a 0, el puente deja de avisar de un error real y el worker cree que su
    llamada funcionó — que es peor que el defecto que arregla V2-325."""
    rc, _ = _correr("inventado")
    assert rc == 2


def test_pero_el_error_DICE_qué_verbos_hay():
    """Misma cortesía que `nav_cli._hint_for`: un error que no enseña el camino cuesta otra vuelta entera."""
    _, out = _correr("inventado")
    for verbo in ("read", "data", "show", "close"):
        assert verbo in out, f"el error no nombra «{verbo}»"
    assert "--help" in out


def test_sin_argumentos_sigue_siendo_un_error_de_uso():
    """Convención, y deliberado: invocar sin nada NO es preguntar. `cmd` a secas → uso + 2, como en todo el
    ecosistema; `cmd --help` → ayuda + 0. Cambiar el primero sería inventarse una convención propia."""
    rc, out = _correr()
    assert rc == 2
    assert "widget_cli" in out


def test_el_HERMANO_que_sí_se_usa_se_comporta_igual():
    """`nav_cli` es la referencia, no una idea mía: 81 de 332 sesiones lo usan y contesta `--help` con 0. Este
    test ata los dos puentes para que no vuelvan a divergir en la puerta de entrada."""
    p = subprocess.run([sys.executable, "-m", "nucleo.nav_cli", "--help"],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0
