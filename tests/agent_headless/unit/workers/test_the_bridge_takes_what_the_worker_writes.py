"""V2-219 — the worker died in OUR OWN CLI's arity, twice, in cases with nothing to do with each other.

Measured 2026-08-20 by the use-case harness:

  `hotel-under-15-days`   Exit code 2 usage: worker_bridge [-h] {ask,wait,act,say} … the following arguments
                          are required
  `hotel-under-15-days`   Exit code 2 nav_cli scroll: error: argument dy: invalid int value: 'down'
  (the Bilbao round)      the same `scroll down`, three more times

Consequence in the same round: `n_search_events: 0`. Not one search in the whole run — the worker died in its
own arguments before reaching the web, and the turn went on saying it was working.

Two different faults with one shape. `scroll down` is the CLI being wrong: every other tool a worker has ever
driven takes a direction there, its own manual says `scroll 800` so it KNOWS the syntax and does not use it,
and it wrote the natural thing four times across two unrelated cases. `worker_bridge act` with no payload is
the worker being wrong, and there the fix is not to accept it but to say how it is written — the same contract
as node 4.20: what the bridge knows, it says, and a failure also says how to get out of it.

That second half matters most HERE of all the bridges: `worker_bridge` is how a worker ASKS for a search, so
dying in its arguments leaves it blind for the rest of the task.
"""
import subprocess
import sys

import pytest

from nucleo import nav_cli, worker_bridge


# ── the CLI was wrong: a direction is a legitimate way to write it ────────────────────────────────────────────
@pytest.mark.parametrize("word,sign", [("down", 1), ("abajo", 1), ("up", -1), ("arriba", -1)])
def test_the_measured_word_is_accepted(word, sign):
    px = nav_cli._scroll_amount(word)
    assert px * sign > 0, f"«{word}» debería moverse en ese sentido"
    assert abs(px) == nav_cli._SCROLL_STEP


def test_a_number_still_means_exactly_that_number():
    """Sensitivity: accepting the word must not turn the pixel argument into an approximation. A worker that
    measured a distance on the capture and asks for 240 gets 240."""
    assert nav_cli._scroll_amount("240") == 240
    assert nav_cli._scroll_amount("-1500") == -1500


def test_nonsense_still_fails_AND_says_both_ways_to_write_it():
    """Widening the input must not become «accept anything»: an unreadable value is still an error. What
    changes is that the error carries the two forms instead of `invalid int value`."""
    import argparse
    with pytest.raises(argparse.ArgumentTypeError) as e:
        nav_cli._scroll_amount("perro")
    msg = str(e.value)
    assert "scroll 800" in msg and "scroll down" in msg


def test_the_whole_command_runs_end_to_end():
    """`_scroll_amount` being right is not the same as it being WIRED: the parser has to use it as the type.
    Run the real CLI — with no server it fails on the connection, never on the argument."""
    out = subprocess.run([sys.executable, "-m", "nucleo.nav_cli", "scroll", "down"],
                         capture_output=True, text=True, timeout=60)
    assert "invalid int value" not in (out.stdout + out.stderr)


# ── the worker was wrong: the failure says how it is written ─────────────────────────────────────────────────
def test_act_names_the_search_call_verbatim():
    """The commonest use and the one that was lost: the hint carries a line the worker can copy, not a
    description of a line."""
    h = worker_bridge._hint_for("worker_bridge act")
    assert "use_tool" in h and '"tool":"web_search"' in h


@pytest.mark.parametrize("sub", ["ask", "say", "wait"])
def test_every_subcommand_has_its_own_way_out(sub):
    h = worker_bridge._hint_for(f"worker_bridge {sub}")
    assert h.strip(), sub
    assert sub in h


def test_an_unknown_prog_still_says_something_useful():
    """Fail-open on the hint itself: a subcommand added tomorrow gets the general rule instead of silence."""
    h = worker_bridge._hint_for("worker_bridge algo-nuevo")
    assert "ask" in h and "act" in h


def test_the_bridge_prints_the_hint_when_the_argument_is_missing():
    """The measured failure, end to end. Asserted on the real process because the whole point is what reaches
    the worker's stderr — a hint that exists and is not printed is V2-186 again."""
    out = subprocess.run([sys.executable, "-m", "nucleo.worker_bridge", "act"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 2
    err = out.stderr
    assert "the following arguments are required" in err      # the complaint is KEPT
    assert "use_tool" in err                                   # …and now it says what to do
    assert "usage:" in err                                     # …and the form is still there


def test_the_hint_lands_BETWEEN_the_complaint_and_the_usage():
    """A worker reads top-down: the way out has to arrive before the wall of syntax it is already staring at."""
    out = subprocess.run([sys.executable, "-m", "nucleo.worker_bridge", "act"],
                         capture_output=True, text=True, timeout=60)
    err = out.stderr
    assert err.index("required") < err.index("use_tool") < err.index("usage:")


# ── V2-306: `open`/`goto` son ALIAS de navigate — y el equivocado era el CLI, no el worker (la regla de
# V2-219). Medido en `find-best-hotel-city__es` (2026-08-25 02:22): DOS workers seguidos escribieron
# `nav_cli open <url>` — el verbo natural, y el que nuestra propia receta enseña en prosa («para ABRIR una
# página usa…»)— y quemaron sus turnos en «invalid choice: 'open'» mientras la ronda acababa con la hoja
# vacía. Un alias conserva la semántica idéntica; una pista sobre el error seguiría costando la llamada.

@pytest.mark.parametrize("alias", ["open", "goto"])
def test_open_and_goto_navigate_exactly_like_navigate(alias, monkeypatch):
    calls = []
    monkeypatch.setattr(nav_cli, "_act", lambda cmd, args: calls.append((cmd, args)) or {"ok": True, "msg": ""})
    monkeypatch.setattr(nav_cli, "_print_state", lambda r: None)
    nav_cli.main([alias, "https://es.wallapop.com"])
    assert calls == [("navigate", {"url": "https://es.wallapop.com"})], \
        "el alias tiene que llegar al MISMO handler — un alias que parsea y no despacha es el peor de los dos"


# ── V2-341: dos formas MÁS que el CLI rechazaba y el worker escribe solo. Medido sobre TODOS los logs de
# sesión del plató — 41 errores de contrato con `nav_cli`, de los que 18 son el `open` que V2-306 ya cerró,
# 5 una URL suelta sin verbo y 5 un `type_at` con la aridad de `type`. En la ronda del coche
# (`search-buy-used-car`, 2026-08-26) cinco errores encadenados dejaron la hoja a CERO mientras el turno
# contaba que seguía navegando. Misma regla que V2-306 y V2-219: cuando el uso natural es inequívoco, el
# equivocado es el CLI.

@pytest.mark.parametrize("url", ["https://es.wallapop.com/coches", "http://coches.net"])
def test_a_bare_url_can_only_mean_navigate(url, monkeypatch):
    calls = []
    monkeypatch.setattr(nav_cli, "_act", lambda cmd, args: calls.append((cmd, args)) or {"ok": True, "msg": ""})
    monkeypatch.setattr(nav_cli, "_print_state", lambda r: None)
    nav_cli.main([url])
    assert calls == [("navigate", {"url": url})], \
        "una cadena que empieza por http(s) no es ningún otro verbo del catálogo"


def test_type_at_with_a_ref_and_a_text_is_the_plain_type(monkeypatch):
    """`type` va con [ref] del snapshot y `type_at` con COORDENADAS de la captura: el fallo natural entre dos
    comandos hermanos. Medido cinco veces, una de ellas con el texto de búsqueda entero metido donde va la `y`
    («invalid int value: 'diésel menos 100000km madrid'»)."""
    calls = []
    monkeypatch.setattr(nav_cli, "_act", lambda cmd, args: calls.append((cmd, args)) or {"ok": True, "msg": ""})
    monkeypatch.setattr(nav_cli, "_print_state", lambda r: None)
    nav_cli.main(["type_at", "26", "diésel menos 100000km madrid"])
    assert calls == [("type", {"ref": 26, "text": "diésel menos 100000km madrid", "submit": False})]


def test_a_real_type_at_with_coordinates_is_left_alone(monkeypatch):
    """SENSIBILIDAD: el camino de VISIÓN no se toca. Sin esto, «acepta la aridad de type» y «rompe type_at»
    pasarían el mismo test."""
    calls = []
    monkeypatch.setattr(nav_cli, "_act", lambda cmd, args: calls.append((cmd, args)) or {"ok": True, "msg": ""})
    monkeypatch.setattr(nav_cli, "_print_state", lambda r: None)
    nav_cli.main(["type_at", "410", "260", "hola"])
    assert calls == [("type_at", {"x": 410, "y": 260, "text": "hola", "submit": False})]


def test_a_half_written_type_at_still_fails_instead_of_being_guessed(monkeypatch):
    """SENSIBILIDAD la otra dirección: `type_at 410 260` (falta el texto) son coordenadas legítimas a medias.
    Convertirlo en un `type` escribiría «260» en el elemento 410 — actuar sobre una página real con un
    argumento inventado, que es justo lo que V2-253 cerró en el otro extremo. Que lo diga argparse."""
    monkeypatch.setattr(nav_cli, "_act", lambda cmd, args: pytest.fail("no debería despachar nada"))
    with pytest.raises(SystemExit):
        nav_cli.main(["type_at", "410", "260"])


def test_the_verb_is_read_from_the_right_position_when_argv_is_none(monkeypatch):
    """GUARDA DEL ÍNDICE, y no es hipotética: la primera versión de este arreglo leía `argv[1]`.
    `main(argv=None)` deja que argparse lea `sys.argv[1:]`, así que el VERBO está en la posición 0 — pero
    todos los tests de arriba pasan una lista, donde `argv[1]` es el primer ARGUMENTO. O sea que el fallo
    salía verde en la suite entera y reventaba con TypeError en cada invocación real del worker."""
    calls = []
    monkeypatch.setattr(nav_cli, "_act", lambda cmd, args: calls.append((cmd, args)) or {"ok": True, "msg": ""})
    monkeypatch.setattr(nav_cli, "_print_state", lambda r: None)
    monkeypatch.setattr(sys, "argv", ["nav_cli", "https://coches.net"])
    nav_cli.main()
    assert calls == [("navigate", {"url": "https://coches.net"})]


@pytest.mark.parametrize("verb,extra", [("click", []), ("type", ["hola"])])
def test_a_ref_with_the_brackets_we_print_is_still_a_ref(verb, extra, monkeypatch):
    """La más nuestra de las tres formas: `dom.py` pinta cada elemento como `[2] button "Buscar"` y el
    encabezado de `_print_state` dice «usa el número [ref] con click/type». Copiar LITERALMENTE lo que le
    enseñamos devolvía «invalid int value: '[2]'» y le costaba el turno."""
    calls = []
    monkeypatch.setattr(nav_cli, "_act", lambda cmd, args: calls.append((cmd, args)) or {"ok": True, "msg": ""})
    monkeypatch.setattr(nav_cli, "_print_state", lambda r: None)
    nav_cli.main([verb, "[2]", *extra])
    assert calls and calls[0][1]["ref"] == 2


def test_a_ref_that_is_not_a_number_still_fails(monkeypatch):
    """SENSIBILIDAD: quitar corchetes no puede volverse «acepta cualquier cosa como ref». Un ref inventado
    haría clic en el elemento equivocado de una página real — el fallo que V2-248 y V2-253 ya pagaron."""
    monkeypatch.setattr(nav_cli, "_act", lambda cmd, args: pytest.fail("no debería despachar nada"))
    with pytest.raises(SystemExit):
        nav_cli.main(["click", "[el botón de buscar]"])
