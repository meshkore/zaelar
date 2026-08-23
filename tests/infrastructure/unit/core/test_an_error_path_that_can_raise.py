"""Un manejador de error que puede reventar no es un manejador de error (2026-08-23).

Lo reportó el arnés con la ronda que le mató: `cheapest-monitor` murió en el turno 10 con un HTTP 500, y el log
del motor traía `IndexError: list index out of range` desde

    _err = str(e).splitlines()[0][:200]

`"".splitlines()` es `[]`, así que CUALQUIER excepción sin mensaje —`TimeoutError()`, `CancelledError()`, un
`RuntimeError('')` pelado— hace que la línea reviente ella sola.

Lo que lo convierte en grave es DÓNDE estaba: las quince copias vivían dentro de un `except`, y la de `probe.py`
es el manejador que clasifica el fallo de proveedor y decide el RELEVO de cadena. Un proveedor cayendo en
silencio se llevaba por delante al manejador del fallo — el turno devolvía 500 y **el relevo no ocurría nunca**.
La red de seguridad se rompía justo cuando hacía falta, y el síntoma señalaba a otra cosa.
"""
import ast
import asyncio
import pathlib
import re

from nucleo.errors import brief

# parents[4], no [3]: este fichero vive un nivel más hondo que `test_architecture_ratchet.py`. Con [3] el
# barrido apuntaba a `tests/`, así que se auto-denunciaba con su propio docstring y no encontraba el motor.
ENGINE = pathlib.Path(__file__).resolve().parents[4]


def test_the_three_shapes_that_used_to_crash():
    """Los tres reproducidos antes de escribir nada. Ninguno lanza, y ninguno devuelve vacío: un log que dice
    «TimeoutError» sirve; uno en blanco es justo lo que la línea original intentaba evitar producir."""
    for exc in (TimeoutError(), asyncio.CancelledError(), RuntimeError("")):
        got = brief(exc)
        assert got == type(exc).__name__, got


def test_a_normal_message_keeps_its_first_line_and_its_cap():
    assert brief(ValueError("boom\nsegunda línea que no interesa")) == "boom"
    assert len(brief(ValueError("x" * 500))) == 200
    assert len(brief(ValueError("x" * 500), 50)) == 50


def test_a_str_that_itself_raises_does_not_take_the_handler_down():
    """Raro y real: errores envueltos de C con un `__str__` que revienta. Si `brief` lanzara ahí, habríamos
    cambiado un modo de fallo por otro con el mismo efecto."""
    class _Nasty(Exception):
        def __str__(self):
            raise RuntimeError("simulado")

    assert brief(_Nasty()) == "_Nasty"


def test_no_production_handler_slices_splitlines_without_a_guard():
    """El guarda de la CLASE. Quince copias de una línea son quince ocasiones de arreglar catorce.

    Se permite la forma cuando está GUARDADA por un ternario que exige texto (es el caso de `music_flow.py`) o
    cuando la lectura viene de un valor ya comprobado — por eso se mira si en la MISMA línea hay una condición,
    en vez de prohibir el patrón a ciegas y obligar a rodearlo."""
    ofensores = []
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE).as_posix()
        # `tools/` queda fuera: son scripts de desarrollo que se lanzan a mano, no manejadores del motor vivo,
        # que es de lo que va este guarda. Comprobado que su único caso ES seguro — la lectura va detrás de un
        # `if text and …` en la línea anterior — así que no se está tapando nada, se está acotando el sujeto.
        if any(x in rel.split("/") for x in (".venv", "tests", "tools", "__pycache__")) \
                or rel == "nucleo/errors.py":
            continue
        try:
            src = p.read_text()
        except Exception:
            continue
        for n, line in enumerate(src.splitlines(), 1):
            if "splitlines()[0]" not in line:
                continue
            if " if " in line:            # ternario que exige contenido — guardado
                continue
            ofensores.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert not ofensores, ("un manejador vuelve a cortar `splitlines()[0]` sin guarda — usa "
                           "`nucleo.errors.brief(e)`:\n  " + "\n  ".join(ofensores))


def test_the_handler_that_decides_the_relay_uses_it():
    """El sitio concreto que tumbó la ronda: si vuelve a construir su mensaje a mano, el relevo se vuelve a
    romper cuando un proveedor cae en silencio."""
    src = (ENGINE / "nucleo" / "flash" / "probe.py").read_text()
    bloque = src[src.index("provider_failure"):][:1200] if "provider_failure" in src else ""
    assert bloque, "desapareció el manejador de fallo de proveedor del probe"
    fuente = src[:src.index("provider_failure")]
    assert "_brief(" in fuente or "_brief(" in bloque, "el manejador del relevo dejó de usar el helper"
    assert not re.search(r"str\(\w+\)\.splitlines\(\)\[0\]", src), "volvió la forma que revienta"
