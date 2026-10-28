"""No canvas event vanishes while the canvas leaves fold into the door (V2-826 §2b, refactor2710-04).

Every literal (kind, label) the canvas door, its arbiter, the turn it reads and the canvas leaves emit is frozen here;
a show or close a caller hands to `nucleo.acts.canvas.apply("<op>", …)` counts as the ("widget", "<op>") the door emits
for it. A pair may move between these files or into the door, never vanish; one retired on purpose leaves this set in
the same commit, with the reason. Measured 2026-10-28 on the branch after T-02 (every writer crosses the door).
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
FILES = ["nucleo/acts/canvas.py", "nucleo/acts/canvas_arbiter.py", "nucleo/acts/canvas_turn.py", "nucleo/acts/close_target.py", "nucleo/acts/named_target.py",
         "nucleo/canvas_focus.py", "nucleo/canvas_closes.py", "nucleo/surfaces.py"] + [
    f"nucleo/flash/{m}.py" for m in ("agenda_close_is_a_cancel", "bulk_close", "canvas_claim", "canvas_license",
                                     "canvas_visibility", "card_close", "card_commission", "card_receipt",
                                     "close_answer", "close_guards", "show_guard", "show_target", "surface_ack")]

FROZEN = {
('brain', '⚠️ commission call failed — the errand stays as it was'),
    ('brain', '⛶ fullscreen_widget → canvas'),
    ('brain', '✍️ se redacta en una sola petición en vez de un worker'),
    ('brain', '❓ close of a piece with several cards open — asking which'),
    ('brain', '❓ una pregunta no escribe — la reparación no crea ni cambia nada'),
    ('brain', '⤡ fullscreen_widget(off) → salir de pantalla completa'),
    ('brain', '⤡ salida de pantalla completa COMPLETADA — el modelo lo dijo y no llamó a nada'),
    ('brain', '⤵️ fullscreen_widget con orden de ENCOGER → canvas minimize'),
    ('brain', '🎯 acción declarada en vez de un worker (la tarjeta del catálogo)'),
    ('brain', '🎯 el veredicto completa al modelo (sin tool) — arrange'),
    ('brain', '🎯 la herramienta del turno en vez de un worker (la tarjeta del catálogo)'),
    ('brain', '🎯 la tarjeta responde lo que el modelo iba a buscar en la web'),
    ('brain', '🎯 lectura de la tarjeta en vez de un worker'),
    ('brain', '🔁 abrió la tarjeta y prometió más — la llamada, en una segunda pasada'),
    ('brain', '🔁 la segunda pasada no dio llamada'),
    ('brain', '🗓️ close of the agenda over a removal of one of its rows — cancelled instead'),
    ('brain', '🙈 close by backstop — his answer to our «which one should I close?»'),
    ('brain', '🚫 second pass refused: a web address nobody said'),
    ('brain', '🛡️ fullscreen_widget ignorado — el turno no habla de tamaño de pantalla (context-bleed)'),
    ('brain', '🧭 card declined: his words name another errand'),
    ('brain', '🧭 catálogo tardío (la pantalla dijo «none»)'),
    ('brain', '🧷 bulk close: sparing would close nothing — everything closes'),
    ('brain', '🧷 bulk close: the card in use stays'),
    ('widget', 'arrange'),
    ('widget', 'close'),
    ('widget', 'gate_shadow'),
    ('widget', 'show'),
    ('widget', '🚫 presentación suprimida'),
}


def _pairs(sources: dict[str, str]) -> set:
    pairs = set()
    for rel, text in sources.items():
        for n in ast.walk(ast.parse(text)):
            if not isinstance(n, ast.Call) or not n.args or not isinstance(n.args[0], ast.Constant):
                continue
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if name == "apply" and rel != "nucleo/acts/canvas.py":
                pairs.add(("widget", n.args[0].value))
            elif name in ("emit", "_emit", "_say") and len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                pairs.add((n.args[0].value, n.args[1].value))
    return pairs


def _now() -> set:
    return _pairs({f: (ENGINE / f).read_text(encoding="utf-8") for f in FILES if (ENGINE / f).exists()})


def test_no_frozen_canvas_event_vanishes():
    gone = sorted(FROZEN - _now(), key=str)
    assert not gone, f"a canvas event stopped being emitted: {gone}"


def test_disarm_a_dropped_event_is_named():
    pairs = _pairs({"nucleo/x.py": 'from nucleo.acts import canvas\ncanvas.apply("close", "agenda", src="flash")\n'})
    assert pairs == {("widget", "close")}
    assert ("widget", "close") in FROZEN and ("widget", "close") not in (_now() - {("widget", "close")})
