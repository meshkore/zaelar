"""F1 — precedence among the THREE confirmation gates, decided in one place.

Where it comes from: while looking for mirrors, it was measured that the VOICE channel resolved the TASK gate and the BROWSER gate
with the SAME guard (`if not had_pending_confirm and not worker_acted["v"]`, twice). `had_pending_confirm`
is the WIDGET gate, so nothing recorded that the task gate had just been resolved: with an irreversible task
stopped and a browser click waiting, ONE spoken «yes» authorized BOTH. The comment in that same block
said «only if the yes has not already resolved something else», and that is what made nobody look — an invariant
written in prose with no test behind it. The `probe` had it right, meaning the mirror drifted.

Two of the three gates trigger something irreversible (paying, buying, canceling). A response counted twice
authorizes a payment that nobody authorized, so this is not a matter of style.
"""
from __future__ import annotations

import pytest

from nucleo.turn import confirm_gates as gates


def _puerta(abierta: bool, devuelve, registro: list, nombre: str):
    """A spy gate: records whether it is QUERIED and whether it is told to resolve."""
    def _is_open():
        registro.append(f"{nombre}:preguntada")
        return abierta

    def _resolve(text):
        registro.append(f"{nombre}:resuelta")
        return devuelve
    return (_is_open, _resolve)


# ── what the defect allowed through ───────────────────────────────────────────────────────────────────────────

def test_un_si_con_DOS_puertas_abiertas_resuelve_UNA():
    """The measured case. Without this, a «yes» relaunches the irreversible task AND releases the browser click."""
    visto = []
    r = gates.resolve("sí",
                      task=_puerta(True, {"ok": True}, visto, "task"),
                      browser=_puerta(True, {"ok": True, "task_id": "t9"}, visto, "browser"))
    assert r.gate == "task" and r.yes is True
    assert "browser:resuelta" not in visto, \
        "la segunda puerta recibió el mismo «sí»: un pago y un clic autorizados con una sola palabra"


def test_la_puerta_que_no_contesta_ni_se_entera():
    """It is not enough to ignore its response: it must not even be QUERIED. Several of these gates consume the
    state when resolving it, so calling them «just to see» already spends it."""
    visto = []
    gates.resolve("sí",
                  task=_puerta(True, {"ok": True}, visto, "task"),
                  browser=_puerta(True, {"ok": True}, visto, "browser"))
    assert not [x for x in visto if x.startswith("browser")], f"se tocó la puerta de después: {visto}"


# ── the order, and ensuring it is order rather than luck ────────────────────────────────────────────────────

def test_el_widget_va_ANTES_que_la_tarea():
    """The widget comes first because it is what was discussed with the model in the live state of THIS turn
    (`confirm.pending_line`), so it is what the operator was most likely answering."""
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


# ── ambiguity is not authorization ──────────────────────────────────────────────────────────────────────────

def test_una_respuesta_que_no_es_si_ni_no_NO_cae_a_la_siguiente_puerta():
    """«¿y cuánto cuestan?» with an open confirmation is not a yes. Above all, it must not slip through as a
    response to the gate behind it, where an ambiguous word would become an authorization."""
    visto = []
    r = gates.resolve("¿y cuánto cuestan?",
                      task=_puerta(True, None, visto, "task"),
                      browser=_puerta(True, {"ok": True}, visto, "browser"))
    assert not r, "una respuesta ilegible acabó autorizando algo"
    assert "browser:resuelta" not in visto


# ── a failure in one gate must not take down the turn ────────────────────────────────────────────────────────

def test_una_puerta_que_revienta_se_salta_y_las_demas_siguen():
    """Losing a confirmation is bad; having an exception in the browser gate take down the turn that was
    resolving a payment is worse."""
    def _revienta():
        raise RuntimeError("boom")

    visto = []
    r = gates.resolve("sí",
                      widget=(_revienta, lambda t: "yes"),
                      task=_puerta(True, {"ok": True}, visto, "task"))
    assert r.gate == "task"


# ── each gate says «yes» in its own way, and ONE place knows that ────────────────────────────────────────────

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


# ── the WIRING: make the channels USE it, which is half of what broke ───────────────────────────────────────
#
# The test above checks the RULE. The failure was not in the rule — it did not exist — but in each channel
# writing its own, so a guard that only checked the module would pass despite the original defect. This is checked
# by AST rather than text: counting a string also counts prose that discusses it, and this file is full
# of prose that names it.

def _llamadas(path, dentro_de=None):
    """Function names called inside `dentro_de`."""
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
    """THE invariant, now true BY CONSTRUCTION rather than because the caller remembers.

    It took some effort to find a way to check it. The first version of the guard counted standalone calls to
    `answer_from_turn` in the voice channel — and stayed GREEN when the original defect was reintroduced, because the
    defect does not call that function by name: it calls the adapter. Counting calls described my fix, not
    the required property.

    The property is that one call queries the gates IN ORDER and stops at the first one that responds. Here
    it is checked on `resolve_all`, which is the gate used by the channels: with task and browser open, the
    browser is not even queried.
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
    # F1 (2026-08-24): the probe was the two sibling copies of the voice ones — voice drifted, probe did not, and
    # even so both are being removed: two correct implementations today are tomorrow's drift with the parity note
    # covering it. From here, BOTH channels go through the same call.
    ("nucleo/flash/probe.py", "run_turn"),
])
def test_ningun_canal_se_escribe_su_propia_precedencia(ruta, funcion):
    """WIRING guard using AST (not text: counting a string also counts prose that names it, and this
    file is full of prose that names it). Two ways to return to the defect, both forbidden: stop using
    the shared gate, or call a specific gate independently alongside it."""
    llamadas = _llamadas(ruta, funcion)
    assert "resolve_all" in llamadas, \
        f"{ruta} dejó de usar la puerta compartida: la precedencia vuelve a ser suya y vuelve a poder derivar"
    assert llamadas.count("answer_from_turn") == 0, f"{ruta}: llamada suelta a la puerta del NAVEGADOR"
    assert llamadas.count("resolve_confirm") == 0, f"{ruta}: llamada suelta a la puerta de TAREA"
