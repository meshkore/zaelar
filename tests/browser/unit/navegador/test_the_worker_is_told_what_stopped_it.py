"""nucleo/nav_cli.py — what the bridge ANNOTATES for the worker must be PRINTED (V2-167 · V2-186).

Two fixes traveled over HTTP and died one line short of their reader:

  · **V2-167** put `wall` in every response from `/api/navegador/act` — the page STOPPED us (anti-bot, CAPTCHA,
    loading error, «Access Denied» in the body). It was put there precisely so the WORKER could act.
  · **V2-186** put `hint`/`stalled_s` there — this page has not moved for minutes.

And `_print_state`, which is the ONLY view the worker has of the page (the web worker's prompt only gives it
`nucleo.nav_cli`), printed `msg`, URL, TITLE, VIEW, and ELEMENTS. Neither of the two fields. Measured over four
rounds: fourteen captures of the same page in twenty minutes, a full run against Booking's wall, and
a task in `done` while the operator heard «it still hasn't signaled».

The lesson, which is the lesson of the entire file: **annotating a response is useless if nobody prints it.** That is why
the last test checks the contract rather than a specific field: whatever the bridge adds for the worker, the CLI
says it.
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
    """A wall with no way out is data; with a way out it is an instruction. The worker is in a loop, so what it
    needs is the alternative, not the diagnosis."""
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
    """The worker reads from top to bottom and decides. A wall announced after the interactive elements is an
    invitation to keep clicking."""
    out = _printed({"ok": True, "url": "https://x.test/", "title": "Access Denied",
                    "wall": "el sitio bloqueó el acceso (te tomó por un robot)",
                    "elements": "[1] botón Buscar"})
    assert out.index("bloqueó el acceso") < out.index("URL:") < out.index("ELEMENTOS")


def test_an_ordinary_page_says_neither(bare=None):
    """The other half: without this, «warn about the wall» and «always warn» pass the same test."""
    out = _printed({"ok": True, "url": "https://www.thefork.es/restaurant/casa-lucio-madrid/r146247",
                    "title": "Casa Lucio", "elements": "[1] Reservar"})
    assert "MURO" not in out and "AVISO" not in out


def test_everything_the_bridge_ANNOTATES_for_the_worker_gets_printed():
    """THE CONTRACT, and the safeguard against repeating the failure: every field that `act_api` adds with the worker
    in mind has to come out here. Adding the field without printing it does not fail noisily — it fails silently, and it has already
    cost two dead fixes."""
    import inspect

    from widgets.navegador import act_api

    annotated = set()
    for fn in (act_api._with_wall, act_api._with_stall):
        for line in inspect.getsource(fn).splitlines():
            line = line.strip()
            if line.startswith("snap[") and "]" in line and "=" in line:
                annotated.add(line.split("[", 1)[1].split("]", 1)[0].strip().strip("\"'"))
    assert annotated, "no se pudo leer qué anota el puente: ¿cambió la forma de las anotaciones?"

    # A field can reach the worker in two ways: PRINTED as-is, or RENDERED by another field that is
    # printed. `stalled_s` is the number and `hint` is the phrase that expresses it in words («llevas 5 min…»), so
    # its reader is `hint` — and `hint` has its own test above. This is not a hand-picked exception: it is the
    # invariant written out correctly. What is not allowed is a field with neither of the two.
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


# ── V2-212: a `usage` states the FORM, not the ERROR ──────────────────────────────────────────────────────────
# Measured in `book-hotel-night-known__es` (2026-08-20 15:29):
#     Exit code 2 usage: nav_cli type_at [-h] [--submit] x y text
#     nav_cli type_at: error: argument y: invalid int value: 'Hotel Palacio de la Merced Burgos reservas 3'
# `type` takes a [ref] and `type_at` takes COORDINATES: the worker used one command's arity with the other command's name. The
# argparse message says what failed and nothing about what to do — the same kind of silent failure as `informe.json`.
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
    assert "`type <ref>" in err          # names the command that it actually was
    assert "usage:" in err               # and the form is not lost


def test_click_at_tambien_lo_explica():
    err = _nav_cli_stderr(["click_at", "boton de buscar"])
    assert "COORDENADAS" in err and "`click <ref>`" in err


def test_un_comando_bien_escrito_no_recibe_ninguna_pista():
    """Sensitivity: the hint is for the error, not for normal usage. If it appeared every time, it would be noise on every
    call and the worker would learn to ignore it."""
    err = _nav_cli_stderr(["navigate"])          # the argument is missing: an error, but from ANOTHER command
    assert "COORDENADAS" not in err
