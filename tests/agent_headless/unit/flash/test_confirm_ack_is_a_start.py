"""Un «sí» a la puerta de confirmación ARRANCA la tarea; no la termina (V2-176 frente 1).

Medido en `cancel-subscription-before-charge__es` (2026-08-20 01:21), y el daño está en las palabras del
propio operador dos líneas después:

    TESTER  Sí, adelante. Y avísame cuando tengas que entrar yo.
    ZAELAR  Hecho.
    TESTER  ¿Ya está cancelada del todo? No me has pedido que entre al login, ¿seguro que no te falta algo?

Entendió «Hecho.» como hecho, que es lo que significa. El juez lo marcó grave («falsa confirmación de
ejecución») — y no lo dijo el modelo: `probe.py` mapeaba `confirm_task` al MISMO ack que una data-op
(`data_ack` = «Hecho.»), o sea el ack de TERMINADO sobre algo que acababa de empezar.

Cómo se llegó aquí, porque importa: el frente 1 del paraguas suponía que la frontera estaba en el prompt
(«estoy accediendo a tu cuenta» vs «voy a intentar acceder»). Midiendo las 78 respuestas archivadas del arnés,
la hipótesis no se sostiene: solo **10 AFIRMAN** un hecho frente a **41 que expresan intención** —el modelo
casi siempre acierta— y las **tres** afirmaciones en corridas donde el mecanismo no registró NADA (0 URL, 0
capturas, 0 búsquedas) son todas la misma palabra: «Hecho.». La frontera no estaba en el prompt; estaba en
nuestras propias frases.
"""
from __future__ import annotations

import inspect

from voice.engine.core import langs


def _probe_ack_source() -> str:
    from nucleo.flash import probe

    return inspect.getsource(probe.run_turn)


def test_a_YES_does_not_get_the_done_ack():
    """La aserción concreta: `confirm_task` ya no comparte rama con `widget_data`."""
    src = _probe_ack_source()
    assert 'if action == "confirm_task":' in src
    assert 'if action in ("widget_data", "confirm_task"):' not in src


def test_a_yes_acknowledges_a_START_with_the_holding_line():
    src = _probe_ack_source()
    i = src.index('if action == "confirm_task":')
    branch = src[i:src.index("elif action in (", i)]      # SOLO la rama del sí, no la siguiente
    assert "holding_line(" in branch          # «Vale, dame un momento que lo miro.» — que es la verdad
    # la ASIGNACIÓN, no la mención: el porqué del cambio se explica en un comentario de esa misma rama, y
    # buscar el token suelto convertiría el comentario en el fallo
    assert "spoken = _lg.data_ack" not in branch


def test_but_a_NO_still_gets_it_because_a_NO_really_did_resolve():
    """La otra mitad, y es la que impide que esto se convierta en «nunca digas hecho»: «no, déjalo» SÍ resuelve
    algo de verdad — la tarea queda descartada— y ahí «Hecho.» es cierto."""
    src = _probe_ack_source()
    assert '"confirm_task_no"' in src
    i = src.index('elif action in ("widget_data", "confirm_task_no"):')
    assert "data_ack" in src[i:i + 900]


def test_and_the_yes_no_split_happens_where_the_reply_is_classified():
    """La propiedad: el nombre de acción lo decide el SÍ/NO del operador, nunca el éxito del re-lanzamiento.

    F1 (2026-08-24) movió la clasificación a `nucleo/turn/confirm_gates.py` (la precedencia de las tres puertas
    se decide una vez, nodo 2.29), así que el sitio donde se parte ya no es este fichero: el probe recibe
    `_ans.yes` —que ES la respuesta clasificada; para la puerta de tarea, `resolve_confirm` devuelve `ok` igual
    al veredicto del operador— y solo le pone nombre. La primera versión de este guarda casaba el literal viejo
    y se puso rojo sobre el arreglo, no sobre el defecto."""
    src = _probe_ack_source()
    assert '"confirm_task" if _ans.yes else "confirm_task_no"' in src
    from nucleo.turn import confirm_gates as _g
    import inspect as _i
    assert "classify_reply" in _i.getsource(_g._task_gate), \
        "la clasificación del sí/no ya no vive en la puerta de tarea: ¿quién decide ahora el veredicto?"


def test_the_holding_line_never_asserts_completion():
    """Lo que hace que este cambio sea un arreglo y no un cambio de sitio del mismo problema."""
    for code in ("es", "en"):
        for line in langs.LANGUAGES[code].holding_lines:
            low = line.lower()
            assert "hecho" not in low and "done" not in low
            assert "ya está" not in low


def test_the_voice_provider_does_NOT_have_this_bug():
    """Comprobado antes de tocar nada, para no «arreglar» un canal que no fallaba: en el provider el ack corto
    se gatea con `data_done`, que solo lo pone el despacho REAL de una data-op — resolver una confirmación pone
    `acted["widget"]` y no eso. Es un fallo del canal de TEXTO, que es donde corre el arnés."""
    from voice.engine.llm.providers import nucleo as _provider

    src = inspect.getsource(_provider)
    i = src.index('if data_done["v"] and not spoken_text')
    assert "data_acks" in src[i:i + 600]
    assert "confirm" not in src[i:i + 600].lower()
