"""F1 — la precedencia entre las TRES puertas de confirmación, decidida en un solo sitio.

De dónde sale: buscando espejos se midió que el canal de VOZ resolvía la puerta de TAREA y la del NAVEGADOR
con el MISMO guarda (`if not had_pending_confirm and not worker_acted["v"]`, dos veces). `had_pending_confirm`
es la puerta de WIDGET, así que nada registraba que la de tarea acabara de resolverse: con una tarea irreversible
parada y un clic del navegador esperando, UN «sí» hablado autorizaba LAS DOS. El comentario de ese mismo bloque
afirmaba «solo si el sí no ha resuelto ya otra cosa», y eso es lo que hizo que nadie mirara — un invariante
escrito en prosa y ni un test detrás. El `probe` lo tenía bien, o sea que el espejo derivó.

Dos de las tres puertas arman algo irreversible (pagar, comprar, cancelar). Una respuesta contada dos veces
autoriza un pago que nadie autorizó, así que esto no es una preferencia de estilo.
"""
from __future__ import annotations

import pytest

from nucleo.turn import confirm_gates as gates


def _puerta(abierta: bool, devuelve, registro: list, nombre: str):
    """Una puerta espía: apunta si le PREGUNTAN y si le mandan resolver."""
    def _is_open():
        registro.append(f"{nombre}:preguntada")
        return abierta

    def _resolve(text):
        registro.append(f"{nombre}:resuelta")
        return devuelve
    return (_is_open, _resolve)


# ── lo que el defecto dejaba pasar ───────────────────────────────────────────────────────────────────────────

def test_un_si_con_DOS_puertas_abiertas_resuelve_UNA():
    """El caso medido. Sin esto, un «sí» relanza la tarea irreversible Y suelta el clic del navegador."""
    visto = []
    r = gates.resolve("sí",
                      task=_puerta(True, {"ok": True}, visto, "task"),
                      browser=_puerta(True, {"ok": True, "task_id": "t9"}, visto, "browser"))
    assert r.gate == "task" and r.yes is True
    assert "browser:resuelta" not in visto, \
        "la segunda puerta recibió el mismo «sí»: un pago y un clic autorizados con una sola palabra"


def test_la_puerta_que_no_contesta_ni_se_entera():
    """No basta con ignorar su respuesta: no se la puede ni PREGUNTAR. Varias de estas puertas consumen el
    estado al resolverlo, así que llamarlas «solo para ver» ya lo gasta."""
    visto = []
    gates.resolve("sí",
                  task=_puerta(True, {"ok": True}, visto, "task"),
                  browser=_puerta(True, {"ok": True}, visto, "browser"))
    assert not [x for x in visto if x.startswith("browser")], f"se tocó la puerta de después: {visto}"


# ── el orden, y que sea el orden y no la suerte ──────────────────────────────────────────────────────────────

def test_el_widget_va_ANTES_que_la_tarea():
    """El widget primero porque es de lo que se le habló al modelo en el estado vivo de ESTE turno
    (`confirm.pending_line`), así que es lo que el operador estaba contestando con más probabilidad."""
    visto = []
    r = gates.resolve("sí",
                      widget=_puerta(True, "yes", visto, "widget"),
                      task=_puerta(True, {"ok": True}, visto, "task"))
    assert r.gate == "widget"
    assert "task:resuelta" not in visto


def test_una_puerta_CERRADA_deja_pasar_a_la_siguiente():
    visto = []
    r = gates.resolve("sí",
                      widget=_puerta(False, "yes", visto, "widget"),
                      task=_puerta(True, {"ok": True}, visto, "task"))
    assert r.gate == "task"


def test_sin_ninguna_abierta_no_resuelve_nada():
    r = gates.resolve("sí", widget=_puerta(False, "yes", [], "w"), task=_puerta(False, None, [], "t"))
    assert not r and r.gate == ""


# ── lo ambiguo no es una autorización ────────────────────────────────────────────────────────────────────────

def test_una_respuesta_que_no_es_si_ni_no_NO_cae_a_la_siguiente_puerta():
    """«¿y cuánto cuestan?» con una confirmación abierta no es un sí. Y sobre todo: no puede colarse como
    respuesta a la puerta de detrás, que es donde una palabra ambigua se convertiría en una autorización."""
    visto = []
    r = gates.resolve("¿y cuánto cuestan?",
                      task=_puerta(True, None, visto, "task"),
                      browser=_puerta(True, {"ok": True}, visto, "browser"))
    assert not r, "una respuesta ilegible acabó autorizando algo"
    assert "browser:resuelta" not in visto


# ── un fallo en una puerta no se lleva el turno por delante ──────────────────────────────────────────────────

def test_una_puerta_que_revienta_se_salta_y_las_demas_siguen():
    """Perder una confirmación es malo; que una excepción en la puerta del navegador tumbe el turno que estaba
    resolviendo un pago es peor."""
    def _revienta():
        raise RuntimeError("boom")

    visto = []
    r = gates.resolve("sí",
                      widget=(_revienta, lambda t: "yes"),
                      task=_puerta(True, {"ok": True}, visto, "task"))
    assert r.gate == "task"


# ── cada puerta dice «sí» a su manera, y eso lo sabe UN solo sitio ────────────────────────────────────────────

@pytest.mark.parametrize("devuelve, esperado", [
    ({"ok": True}, True), ({"ok": False}, False),      # dispatch / navegador
    ("yes", True), ("no", False),                      # widgets.confirm
])
def test_el_si_de_cada_puerta_se_lee_igual(devuelve, esperado):
    r = gates.resolve("da igual", task=_puerta(True, devuelve, [], "task"))
    assert r.gate == "task" and r.yes is esperado


def test_un_NO_tambien_consume_la_respuesta():
    """Un «no» resuelve tanto como un «sí»: la puerta se cierra y la de detrás tampoco lo recibe. Si no, un
    «no» a la tarea se leería como un «no» al clic, y son dos decisiones distintas."""
    visto = []
    r = gates.resolve("no", task=_puerta(True, {"ok": False}, visto, "task"),
                      browser=_puerta(True, {"ok": True}, visto, "browser"))
    assert r.gate == "task" and r.yes is False
    assert "browser:resuelta" not in visto


# ── el CABLEADO: que los canales lo USEN, que es la mitad que se rompió ──────────────────────────────────────
#
# El test de arriba prueba la REGLA. La avería no estaba en la regla —no existía— sino en que cada canal se
# escribía la suya, así que un guarda que solo mire el módulo daría verde sobre el defecto original. Se comprueba
# por AST y no por texto: contar una cadena cuenta también la prosa que habla de ella, y este fichero está lleno
# de prosa que la nombra.

def _llamadas(path, dentro_de=None):
    """Nombres de función llamados dentro de `dentro_de`."""
    import ast
    árbol = ast.parse(open(path, encoding="utf8").read())
    if dentro_de:
        árbol = next((n for n in ast.walk(árbol)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == dentro_de), None)
        assert árbol is not None, f"no encuentro `{dentro_de}` en {path}"
    out = []
    for n in ast.walk(árbol):
        if isinstance(n, ast.Call):
            f = n.func
            out.append(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return out


def test_resolve_all_decide_TODAS_las_puertas_en_UNA_llamada():
    """EL invariante, y ahora es cierto POR CONSTRUCCIÓN en vez de por que el llamante se acuerde.

    Costó dar con la forma de comprobarlo. La primera versión del guarda contaba llamadas sueltas a
    `answer_from_turn` en el canal de voz — y se quedó VERDE al reintroducir el defecto original, porque el
    defecto no llama a esa función por su nombre: llama al adaptador. Contar llamadas describía mi arreglo, no
    la propiedad que hacía falta.

    La propiedad es que una sola llamada consulte las puertas EN ORDEN y pare en la primera que conteste. Aquí
    se comprueba sobre `resolve_all`, que es la puerta que usan los canales: con tarea y navegador abiertos, el
    navegador no llega ni a que le pregunten.
    """
    import nucleo.turn.confirm_gates as g

    tocadas = []
    def _falsa(nombre, devuelve):
        def _open():
            tocadas.append(f"{nombre}:preguntada"); return True
        def _do(_t):
            tocadas.append(f"{nombre}:resuelta"); return devuelve
        return (_open, _do)

    import pytest as _p
    mp = _p.MonkeyPatch()
    try:
        mp.setattr(g, "_task_gate", lambda: _falsa("task", {"ok": True}))
        mp.setattr(g, "_browser_gate", lambda: _falsa("browser", {"ok": True, "task_id": "t9"}))
        r = g.resolve_all("sí")
    finally:
        mp.undo()

    assert r.gate == "task" and r.yes is True
    assert not [x for x in tocadas if x.startswith("browser")], (
        "la puerta del navegador vio el mismo «sí» que ya había gastado la de tarea — una tarea irreversible y "
        f"un clic autorizados con una sola palabra. Puertas tocadas: {tocadas}")


import pytest as _pt


@_pt.mark.parametrize("ruta, funcion", [
    ("voice/engine/llm/providers/nucleo.py", "_run_inner"),
    # F1 (2026-08-24): el probe era las dos copias hermanas de las de la voz — la voz derivó, el probe no, y
    # aun así las dos se retiran: dos implementaciones correctas hoy son la deriva de mañana con la nota de
    # paridad encima tapándola. Desde aquí los DOS canales pasan por la misma llamada.
    ("nucleo/flash/probe.py", "run_turn"),
])
def test_ningun_canal_se_escribe_su_propia_precedencia(ruta, funcion):
    """Guarda de CABLEADO por AST (no por texto: contar una cadena cuenta también la prosa que la nombra, y este
    fichero está lleno de prosa que la nombra). Dos formas de volver al defecto, las dos vetadas: dejar de usar
    la puerta compartida, o llamar a una puerta concreta por libre al lado."""
    llamadas = _llamadas(ruta, funcion)
    assert "resolve_all" in llamadas, \
        f"{ruta} dejó de usar la puerta compartida: la precedencia vuelve a ser suya y vuelve a poder derivar"
    assert llamadas.count("answer_from_turn") == 0, f"{ruta}: llamada suelta a la puerta del NAVEGADOR"
    assert llamadas.count("resolve_confirm") == 0, f"{ruta}: llamada suelta a la puerta de TAREA"
