"""`ERROR: timed out` decía QUÉ pasó y nada de qué hacer — y el worker se quedó ahí (V2-274).

Medido en `search-secondhand-monitor__es` (2026-08-24 00:56), con la ronda entregando CERO resultados después
de haber llegado a la página correcta:

    navegador  🧭 navegador ⚠️ error   Exit code 1 ERROR: timed out      (+266,9 s)
    navegador  🧭 navegador ⚠️ error   Exit code 1 ERROR: timed out      (+358,7 s)

`str(socket.timeout())` son literalmente esas dos palabras. `_act` las envolvía en `{"ok": False, "error":
str(e)}` y `_print_state` las imprimía tal cual, así que lo ÚNICO que el worker sabía de este lado era que algo
había fallado. Misma familia que V2-186 (el muro y el atasco anotados y nunca impresos), V2-203 (el OSError
pelado del puente de payload), V2-212 (`usage` sin decir el error) y V2-248 (el `ref` caducado), y el mismo
contrato del nodo 4.20: **lo que el puente sabe, lo DICE, y un fallo dice además cómo se sale de él.**

Lo que hace este caso distinto de sus hermanos es que la reacción natural es la ÚNICA que no puede funcionar.
Un timeout aquí es nuestro plazo de espera agotándose, no la acción cancelándose: la pestaña puede seguir
trabajando. Repetir el comando encola una segunda acción encima de un navegador ocupado — y el worker no tiene
forma de deducirlo, porque «timed out» no dice de quién es el plazo.
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
    """Con varias acciones en vuelo, «algo no contestó» no le dice cuál reanudar."""
    assert "«navigate»" in nav_cli._transport_error(TimeoutError("timed out"), "navigate")
    assert "«click_at»" in nav_cli._transport_error(TimeoutError("timed out"), "click_at")


def test_el_plazo_QUE_SE_DICE_es_el_que_de_verdad_se_espera():
    """Un aviso que nombra un número tiene que leerlo de donde se aplica: dos literales derivan y miente."""
    out = nav_cli._transport_error(TimeoutError("timed out"), "extract")
    assert f"{nav_cli._ACT_TIMEOUT_S}s" in out
    src = __import__("inspect").getsource(nav_cli._act)
    assert "timeout=_ACT_TIMEOUT_S" in src, "el urlopen volvió a llevar el número a mano"


def test_el_motor_INALCANZABLE_no_se_confunde_con_una_espera():
    """Son dos sitios distintos a los que mandar al worker: uno espera, el otro entrega y lo dice."""
    out = nav_cli._transport_error(ConnectionRefusedError("[Errno 61] Connection refused"), "look")
    assert "no puedo hablar con el motor" in out
    assert "entrega lo que ya tengas" in out
    assert "look" not in out, "mandarle a mirar cuando nadie contesta es mandarle a un bucle"


def test_un_fallo_QUE_NO_CONOCEMOS_conserva_su_texto():
    """Inventar un diagnóstico para lo no previsto es cómo una pista deja de ser información (V2-248)."""
    assert nav_cli._transport_error(ValueError("algo que no habíamos visto"), "click") == (
        "algo que no habíamos visto")


def test_la_pista_LLEGA_a_la_pantalla_del_worker():
    """La mitad que ninguna medición ve: `_print_state` es el único sitio por el que el worker mira.

    V2-186 se pagó entera por esto — dos arreglos que viajaban por HTTP y morían a una línea de su lector.
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
