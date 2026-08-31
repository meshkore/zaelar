"""V2-392 — «suena algo de verdad» could not be verified from the report.

`widget_ops` says what was TOUCHED. That is not the same as whether something actually happened, and in media
cases the distinction is the entire criterion: «SUENA ALGO DE VERDAD» is literally the first half of
`play-music-and-build-playlist`.

Measured on 2026-08-27 at 14:02, manually checked against the studio with the round just completed:

    yt        → {"videoId": "263Vb6xiifo", "title": "MUSICA ZEN ULTRA RELAJANTE…", "paused": false}
    playlists → [{"name": "Curro", "tracks": [{"title": "MUSICA ZEN ULTRA RELAJANTE…"}]}]

It was playing, and the list had that same song INSIDE it: both halves of the case were fulfilled. Verdict: **3/5**,
«the assistant lies when claiming that it is playing music without the necessary technical confirmation (zero
evidence)». The product had done it, and nothing could say so.

The engine ALREADY knew —`widgets/producers.py` evaluates `active_when` against the widget's `view_data()`— and
what was missing was the ability to ASK it from outside the process. It is queried, not inferred: reimplementing
`active_when` in the harness would be a second truth, capable of diverging precisely from the one the product uses.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tests.use_cases.e2e.agent import probe_client as PC
from tests.use_cases.e2e.agent import verify as V


def _cuerpo(resp) -> dict:
    return json.loads(bytes(resp.body).decode("utf-8"))


# ── the engine answers ───────────────────────────────────────────────────────────────────────────────────────

def test_el_endpoint_devuelve_lo_que_dice_el_MOTOR(monkeypatch):
    import widgets.producers as P
    import widgets.server_api as SA

    async def _producing(*, channel=None):
        return ["musica"]
    monkeypatch.setattr(P, "producing", _producing)
    assert _cuerpo(asyncio.run(SA.producing_endpoint())) == {"producing": ["musica"]}


def test_si_el_motor_no_sabe_responder_NO_revienta(monkeypatch):
    """This is diagnostic data: bringing down one report read would cost the entire round."""
    import widgets.producers as P
    import widgets.server_api as SA

    async def _boom(*, channel=None):
        raise RuntimeError("el registro no está listo")
    monkeypatch.setattr(P, "producing", _boom)
    cuerpo = _cuerpo(asyncio.run(SA.producing_endpoint()))
    assert cuerpo["producing"] == [] and "no está listo" in cuerpo["error"]


# ── the harness reads it ──────────────────────────────────────────────────────────────────────────────────────

def test_el_cliente_lee_la_lista(monkeypatch):
    monkeypatch.setattr(PC, "_get", lambda path, timeout=15.0: {"producing": ["musica", "youtube"]})
    assert PC.widgets_producing() == ["musica", "youtube"]


def test_el_cliente_pregunta_a_la_RUTA_correcta(monkeypatch):
    visto = {}
    monkeypatch.setattr(PC, "_get", lambda path, timeout=15.0: visto.setdefault("path", path) and {})
    PC.widgets_producing()
    assert visto["path"] == "/widgets/producing"


def test_un_motor_mudo_dice_NO_PUDE_PREGUNTAR_y_no_lanza(monkeypatch):
    """Rewritten by V2-396, not reverted. What it protected —that a silent engine does NOT crash the round— remains
    intact; what it returned was the defect: `[]` is the branch that this same file taught the judge to read
    as «nothing was playing», so an unreachable engine accused the product of not playing anything."""
    def _boom(path, timeout=15.0):
        raise OSError("conexión rechazada")
    monkeypatch.setattr(PC, "_get", _boom)
    assert PC.widgets_producing() is None       # and above all: it does not throw


def test_una_respuesta_SIN_el_campo_no_inventa_nada(monkeypatch):
    """Likewise: `{"error": "404"}` is a FAILED read, not a silent engine."""
    monkeypatch.setattr(PC, "_get", lambda path, timeout=15.0: {"error": "404"})
    assert PC.widgets_producing() is None


# ── the direction of the data is STATED (V2-401) ──────────────────────────────────────────────────────────────

def test_el_juez_sabe_que_producing_es_el_estado_DECLARADO():
    """The operator's capture (2026-08-27): «This video is unavailable» on screen with the declared state
    saying `paused: false`. The data is asymmetric — declared «nothing playing» is reliable, declared «playing»
    can fail in the browser — and the judge has to know the direction so as not to score with it backwards."""
    from tests.use_cases.e2e.agent import judge as J
    txt = J.mechanism_facts({"widgets_producing": []})
    txt = txt if isinstance(txt, str) else "\n".join(txt)
    assert "DECLARADO" in txt
    assert "sí es fiable" in txt


# ── and it reaches the report ─────────────────────────────────────────────────────────────────────────────────

def test_el_informe_de_mecanismo_LLEVA_lo_que_suena(monkeypatch):
    """The guard that would have been enough: the criterion required `yt.videoId`, and the report contained none of it."""
    monkeypatch.setattr(V.probe_client, "widgets_producing", lambda: ["musica"])
    mech = V.mechanism_report([], [])
    assert mech["widgets_producing"] == ["musica"]


def test_el_arnes_NO_reimplementa_active_when():
    """The engine is QUERIED. A copy of `active_when` here is a second truth that can diverge from the one the
    product uses — and the one that decides what appears on screen is the product's.

    ⚠️ About the CODE, not the comment: the first version matched the bare string and came out RED because
    the `widgets_producing` docstring itself explains why it is NOT reimplemented. A guard that reads the
    explanation instead of the code is the same failure already paid for with `extract=None` in V2-380, in reverse.
    """
    import ast
    for f in ("tests/use_cases/e2e/agent/verify.py", "tests/use_cases/e2e/agent/probe_client.py"):
        arbol = ast.parse(Path(f).read_text(encoding="utf-8"))
        # A literal `"active_when"` in the harness can only be the beginning of a copy of the rule; the
        # docstring that EXPLAINS why it is not copied is prose and does not count (ast.Constant does not see a
        # standalone module/function docstring as this literal, because it is compared for exact equality).
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and nodo.value == "active_when":
                assert False, f"{f} nombra `active_when` como dato: se PREGUNTA al motor, no se copia"
