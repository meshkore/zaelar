"""nucleo/nav_cli.py — lo que el puente ANOTA para el worker tiene que IMPRIMIRSE (V2-167 · V2-186).

Dos arreglos viajaron por HTTP y murieron a una línea de su lector:

  · **V2-167** puso `wall` en cada respuesta de `/api/navegador/act` — la página nos PARÓ (anti-bot, CAPTCHA,
    error de carga, «Access Denied» en el cuerpo). Se puso ahí precisamente para que el WORKER pudiera actuar.
  · **V2-186** puso `hint`/`stalled_s` — esta página no se mueve desde hace minutos.

Y `_print_state`, que es la ÚNICA vista que el worker tiene de la página (el prompt del worker web solo le da
`nucleo.nav_cli`), imprimía `msg`, URL, TÍTULO, VISTA y ELEMENTOS. Ni uno de los dos campos. Medido en cuatro
rondas: catorce capturas de la misma página en veinte minutos, una corrida entera contra el muro de Booking, y
una tarea en `done` mientras el operador oía «aún no ha dado señal».

La lección, que es la del fichero entero: **anotar una respuesta no sirve de nada si nadie la imprime.** Por eso
el último test no comprueba un campo concreto sino el contrato: lo que el puente añade para el worker, el CLI lo
dice.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout

from nucleo import nav_cli


def _printed(res: dict) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        nav_cli._print_state(res)
    return buf.getvalue()


def test_the_wall_reaches_the_worker():
    out = _printed({"ok": True, "url": "https://www.entradas.com/teatro-musical/el-rey-leon-t3328",
                    "title": "Access Denied",
                    "wall": "el sitio bloqueó el acceso (te tomó por un robot)",
                    "elements": "[1] botón Buscar"})
    assert "el sitio bloqueó el acceso" in out


def test_and_it_says_what_to_do_instead_of_only_naming_it():
    """Un muro sin salida es un dato; con salida es una instrucción. El worker está en un bucle, así que lo que
    necesita es la alternativa, no el diagnóstico."""
    out = _printed({"ok": True, "url": "https://x.test/", "title": "t",
                    "wall": "el sitio pidió verificación anti-robot"})
    assert "otro sitio" in out.lower()


def test_the_stall_hint_reaches_the_worker():
    out = _printed({"ok": True, "url": "https://www.thefork.es/restaurant/casa-lucio-madrid/r146247",
                    "title": "Casa Lucio", "stalled_s": 300,
                    "hint": "llevas 5 min en esta página sin avanzar: o extraes ya lo que necesitas de lo que "
                            "tienes delante, o pruebas otro sitio. Repetir `look` no la cambia."})
    assert "5 min en esta página sin avanzar" in out


def test_the_wall_is_said_BEFORE_the_page_it_is_about():
    """El worker lee de arriba abajo y decide. Un muro anunciado después de los elementos interactivos es una
    invitación a seguir clicando."""
    out = _printed({"ok": True, "url": "https://x.test/", "title": "Access Denied",
                    "wall": "el sitio bloqueó el acceso (te tomó por un robot)",
                    "elements": "[1] botón Buscar"})
    assert out.index("bloqueó el acceso") < out.index("URL:") < out.index("ELEMENTOS")


def test_an_ordinary_page_says_neither(bare=None):
    """La otra mitad: sin esto, «avisar del muro» y «avisar siempre» pasan el mismo test."""
    out = _printed({"ok": True, "url": "https://www.thefork.es/restaurant/casa-lucio-madrid/r146247",
                    "title": "Casa Lucio", "elements": "[1] Reservar"})
    assert "MURO" not in out and "AVISO" not in out


def test_everything_the_bridge_ANNOTATES_for_the_worker_gets_printed():
    """EL CONTRATO, y la guarda contra repetir el fallo: cada campo que `act_api` añade pensando en el worker
    tiene que salir por aquí. Añadir el campo y no imprimirlo no falla con ruido — falla en silencio, y ya ha
    costado dos arreglos muertos."""
    import inspect

    from widgets.navegador import act_api

    annotated = set()
    for fn in (act_api._with_wall, act_api._with_stall):
        for line in inspect.getsource(fn).splitlines():
            line = line.strip()
            if line.startswith("snap[") and "]" in line and "=" in line:
                annotated.add(line.split("[", 1)[1].split("]", 1)[0].strip().strip("\"'"))
    assert annotated, "no se pudo leer qué anota el puente: ¿cambió la forma de las anotaciones?"

    # Un campo puede llegar al worker de dos maneras: IMPRESO tal cual, o RENDERIZADO por otro que sí se
    # imprime. `stalled_s` es el número y `hint` es la frase que lo dice con palabras («llevas 5 min…»), así que
    # su lector es `hint` — y `hint` tiene su propio test arriba. Esto no es una excepción a dedo: es el
    # invariante escrito bien. Lo que no se admite es un campo sin ninguna de las dos cosas.
    RENDERED_BY = {"stalled_s": "hint"}

    printer = inspect.getsource(nav_cli._print_state)

    def _reaches_the_worker(key: str) -> bool:
        for candidate in (key, RENDERED_BY.get(key, "")):
            if candidate and (f'"{candidate}"' in printer or f"'{candidate}'" in printer):
                return True
        return False

    missing = sorted(k for k in annotated if not _reaches_the_worker(k))
    assert not missing, (
        f"el puente anota {missing} para el worker y el CLI no lo imprime ni lo renderiza. Un campo que nadie "
        f"lee es un arreglo muerto: imprímelo en `_print_state`, decláralo en RENDERED_BY apuntando al campo "
        f"que sí lo dice, o quítalo de `act_api`.")


# ── V2-212: un `usage` dice la FORMA, no el ERROR ─────────────────────────────────────────────────────────────
# Medido en `book-hotel-night-known__es` (2026-08-20 15:29):
#     Exit code 2 usage: nav_cli type_at [-h] [--submit] x y text
#     nav_cli type_at: error: argument y: invalid int value: 'Hotel Palacio de la Merced Burgos reservas 3'
# `type` toma un [ref] y `type_at` toma COORDENADAS: el worker usó la aridad de uno con el nombre del otro. El
# mensaje de argparse dice qué falló y nada de qué hacer — la misma clase de fallo mudo que el `informe.json`.
def _nav_cli_stderr(argv):
    import contextlib
    import io

    from nucleo import nav_cli
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        try:
            nav_cli.main(argv)
        except SystemExit:
            pass
    return buf.getvalue()


def test_type_at_con_el_texto_en_la_coordenada_explica_la_confusion():
    err = _nav_cli_stderr(["type_at", "3", "Hotel Palacio de la Merced Burgos reservas", "x"])
    assert "COORDENADAS" in err
    assert "`type <ref>" in err          # nombra el comando que SÍ era
    assert "usage:" in err               # y no se pierde la forma


def test_click_at_tambien_lo_explica():
    err = _nav_cli_stderr(["click_at", "boton de buscar"])
    assert "COORDENADAS" in err and "`click <ref>`" in err


def test_un_comando_bien_escrito_no_recibe_ninguna_pista():
    """Sensibilidad: la pista es para el error, no para el uso normal. Si saliera siempre, sería ruido en cada
    llamada y el worker aprendería a ignorarla."""
    err = _nav_cli_stderr(["navigate"])          # falta el argumento: error, pero de OTRO comando
    assert "COORDENADAS" not in err
