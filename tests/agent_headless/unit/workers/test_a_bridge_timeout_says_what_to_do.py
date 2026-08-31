"""`ERROR: timed out` said WHAT happened and nothing about what to do — and the worker got stuck there (V2-274).

Measured in `search-secondhand-monitor__es` (2026-08-24 00:56), with the round returning ZERO results after
reaching the correct page:

    navegador  🧭 navegador ⚠️ error   Exit code 1 ERROR: timed out      (+266,9 s)
    navegador  🧭 navegador ⚠️ error   Exit code 1 ERROR: timed out      (+358,7 s)

`str(socket.timeout())` is literally those two words. `_act` wrapped them in `{"ok": False, "error":
str(e)}` and `_print_state` printed them as-is, so the ONLY thing the worker knew on this side was that something
had failed. Same family as V2-186 (the wall and the jam recorded but never printed), V2-203 (the bare OSError
from the payload bridge), V2-212 (`usage` without stating the error), and V2-248 (the expired `ref`), and the same
contract as node 4.20: **what the bridge knows, it SAYS, and a failure also says how to get out of it.**

What makes this case different from its siblings is that the natural reaction is the ONLY one that cannot work.
A timeout here is our wait period expiring, not the action being cancelled: the tab may still be
working. Repeating the command queues a second action on top of a busy browser — and the worker has no
way to infer that, because «timed out» does not say whose deadline expired.
"""
from nucleo import nav_cli


def test_un_timeout_dice_que_la_accion_puede_seguir_viva():
    out = nav_cli._transport_error(TimeoutError("timed out"), "extract")
    assert "NO quiere decir" in out and "seguir corriendo" in out, (
        "sin esto, «timed out» se lee como «no se hizo», que es la lectura que lleva a repetir")


def test_y_PROHIBE_repetir_nombrando_la_salida():
    out = nav_cli._transport_error(TimeoutError("timed out"), "extract")
    assert "NO la repitas" in out, "la reacción natural es repetir, y es la única que no puede funcionar"
    assert "look" in out, "una prohibición sin salida deja al worker igual de parado"


def test_nombra_el_comando_que_se_quedo_colgado():
    """With several actions in flight, «something did not respond» does not tell it which one to resume."""
    assert "«navigate»" in nav_cli._transport_error(TimeoutError("timed out"), "navigate")
    assert "«click_at»" in nav_cli._transport_error(TimeoutError("timed out"), "click_at")


def test_el_plazo_QUE_SE_DICE_es_el_que_de_verdad_se_espera():
    """A notice that names a number must read it from where it is applied: two literals drift and lie."""
    out = nav_cli._transport_error(TimeoutError("timed out"), "extract")
    assert f"{nav_cli._ACT_TIMEOUT_S}s" in out
    src = __import__("inspect").getsource(nav_cli._act)
    assert "timeout=_ACT_TIMEOUT_S" in src, "el urlopen volvió a llevar el número a mano"


def test_el_motor_INALCANZABLE_no_se_confunde_con_una_espera():
    """These are two different places to send the worker: one waits, the other delivers and says so."""
    out = nav_cli._transport_error(ConnectionRefusedError("[Errno 61] Connection refused"), "look")
    assert "no puedo hablar con el motor" in out
    assert "entrega lo que ya tengas" in out
    assert "look" not in out, "mandarle a mirar cuando nadie contesta es mandarle a un bucle"


def test_un_fallo_QUE_NO_CONOCEMOS_conserva_su_texto():
    """Inventing a diagnosis for the unforeseen is how a clue stops being information (V2-248)."""
    assert nav_cli._transport_error(ValueError("algo que no habíamos visto"), "click") == (
        "algo que no habíamos visto")


def test_la_pista_LLEGA_a_la_pantalla_del_worker():
    """The half that no measurement sees: `_print_state` is the only place through which the worker looks.

    V2-186 was paid for entirely because of this — two fixes that traveled over HTTP and died one line away from their reader.
    """
    printed = []
    _real = print

    import builtins
    builtins.print = lambda *a, **k: printed.append(" ".join(str(x) for x in a))
    try:
        nav_cli._print_state({"ok": False, "error": nav_cli._transport_error(TimeoutError("timed out"), "extract")})
    finally:
        builtins.print = _real
    joined = "\n".join(printed)
    assert "NO la repitas" in joined and "look" in joined
