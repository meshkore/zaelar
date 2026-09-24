"""V2-759 — leaving full screen is its OWN order, and a claim of having left is made true.

Session `ee542271`, 2026-09-24, on the image viewer:

    OPERADOR  Y puedes poner el widget en pantalla completa?   → fullscreen_widget → maximize ✓
    OPERADOR  Y sal de pantalla completa.
    ZAELAR    Ya está, fuera de pantalla completa.             ← NOTHING called (susurro: «data-op fantasma»)
    OPERADOR  No, sigues estando en pantalla completa, no veo el orbe, no veo la barra inferior,
              → fullscreen_widget → exits — but only because the frontend TOGGLES
    OPERADOR  Me preocupa que te pida una acción, me digas que ya está hecha, cuando realmente no has hecho
              absolutamente nada. Y luego, además, que lo pida una segunda vez y sí seas capaz de hacerla.

The same failure as V2-609 (2026-09-07), whose fix — an optional `widget_id` and the canvas telling the model
which card is maximized — did not hold. Two structural causes, both fixed here:

  · THE TOOL WAS A TOGGLE. Leaving meant calling the tool that enters. And his complaint got the ENTER
    licence (`fullscreen`): it only left because the card happened to be full screen — on a normal card the
    same sentence would have blown it up. The direction is now an argument (`mode`), required, and the
    desktop's operations are idempotent in both directions.
  · NOTHING MADE THE CLAIM TRUE. When the model calls nothing on a turn the existing licence already reads as
    leaving, and a card IS covering the screen (the canvas's own report, not a reading), the exit is
    completed. The consequence is bounded: that card goes back where it was, nothing else moves.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[3]


def _tool():
    from nucleo.flash import router
    return next(t for t in router.TOOLS if t["function"]["name"] == "fullscreen_widget")["function"]


def _emits():
    rows = []

    def emit(kind, label, **kw):
        rows.append((kind, label, kw))
    return rows, emit


def _dispatch(args, text, monkeypatch, target="imagenes"):
    from nucleo.flash import show_target as st
    monkeypatch.setattr(st, "fullscreen_target", lambda rid, t: target)
    rows, emit = _emits()
    tags, deduped = [], {"v": False}
    st.fullscreen_dispatch(args, text, lambda a, e: tags.append((a, e)), emit, deduped)
    return tags, deduped


def _state(monkeypatch, maximized=""):
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": ["imagenes"], "maximized_widget": maximized})


# ── A · THE TOOL SAYS WHICH WAY ──────────────────────────────────────────────────────────────────────────────
def test_the_tool_takes_a_direction_and_requires_it():
    """Required because — unlike `widget_id` in V2-609 — it can always be filled: every sentence either puts
    full screen on or takes it off."""
    f = _tool()
    mode = f["parameters"]["properties"].get("mode") or {}
    assert mode.get("enum") == ["on", "off"], f"`mode` must be on|off: {mode}"
    assert "mode" in f["parameters"].get("required", []), "a direction the model may omit is the toggle again"
    assert "SALIR" in mode.get("description", "") and "sal" in mode.get("description", ""), \
        "the exit has to be NAMED in the argument the model fills"


def test_the_tool_no_longer_calls_itself_a_toggle():
    assert "interruptor" not in _tool()["description"].lower(), \
        "the description still teaches the model that leaving means calling the enter tool again"


def test_the_leaving_order_still_needs_no_name():
    """V2-609 stays: «sal de pantalla completa» names no card."""
    f = _tool()
    assert "widget_id" not in f["parameters"].get("required", [])
    assert "VACÍO" in f["parameters"]["properties"]["widget_id"]["description"]


# ── B · THE DISPATCH FOLLOWS THE DIRECTION ───────────────────────────────────────────────────────────────────
def test_off_leaves_with_an_explicit_direction(monkeypatch):
    tags, _ = _dispatch({"mode": "off"}, "Y sal de pantalla completa.", monkeypatch)
    assert tags == [("fullscreen", {"id": "imagenes", "on": False})], tags


def test_off_leaves_even_when_no_card_resolves(monkeypatch):
    """An empty id is «whichever card covers the screen» — the desktop knows it; the order has no object."""
    tags, _ = _dispatch({"mode": "off"}, "Y sal de pantalla completa.", monkeypatch, target="")
    assert tags == [("fullscreen", {"id": "", "on": False})], tags


def test_his_complaint_with_off_leaves_instead_of_toggling(monkeypatch):
    """«No, sigues estando en pantalla completa…» gets the ENTER licence. With the direction explicit, what the
    model says wins, and on a card that is not full screen the desktop's exit touches nothing."""
    tags, _ = _dispatch({"mode": "off"},
                        "No, sigues estando en pantalla completa, no veo el orbe, no veo la barra inferior,",
                        monkeypatch)
    assert tags == [("fullscreen", {"id": "imagenes", "on": False})], tags


def test_on_enters_idempotently(monkeypatch):
    tags, _ = _dispatch({"mode": "on"}, "pon el visor a pantalla completa", monkeypatch)
    assert tags == [("show", {"id": "imagenes"}), ("fullscreen", {"id": "imagenes", "on": True})], tags


def test_an_undirected_call_keeps_its_old_meaning(monkeypatch):
    """Every older call shape behaves exactly as before — toggle included."""
    tags, _ = _dispatch({}, "pon el visor a pantalla completa", monkeypatch)
    assert tags == [("show", {"id": "imagenes"}), ("fullscreen", {"id": "imagenes"})], tags


@pytest.mark.parametrize("mode", ["on", "off", ""])
def test_a_turn_that_says_nothing_about_screen_size_is_still_drag(monkeypatch, mode):
    """The licence stays, in both directions: «pausa el vídeo» must not throw him out of the film either."""
    tags, deduped = _dispatch({"mode": mode} if mode else {}, "Johnny pausa el vídeo.", monkeypatch)
    assert tags == [] and deduped["v"] is True, tags


# ── C · A CLAIM OF HAVING LEFT IS MADE TRUE ──────────────────────────────────────────────────────────────────
def test_the_measured_turn_is_completed(monkeypatch):
    """«Y sal de pantalla completa.», nothing called, the viewer covering the screen."""
    from nucleo.flash import show_target as st
    _state(monkeypatch, maximized="imagenes")
    assert st.fullscreen_exit_due("Y sal de pantalla completa.", fired=False) == "imagenes"


def test_it_is_never_completed_twice(monkeypatch):
    from nucleo.flash import show_target as st
    _state(monkeypatch, maximized="imagenes")
    assert st.fullscreen_exit_due("Y sal de pantalla completa.", fired=True) == "", \
        "the model DID call the tool: completing on top of it would act twice"


def test_nothing_is_completed_when_nothing_covers_the_screen(monkeypatch):
    """The screen fact is what bounds it: with no card full screen there is nothing to bring back."""
    from nucleo.flash import show_target as st
    _state(monkeypatch, maximized="")
    assert st.fullscreen_exit_due("Y sal de pantalla completa.", fired=False) == ""


@pytest.mark.parametrize("text", [
    "pon el visor a pantalla completa",                # entering — never completed as leaving
    "No, sigues estando en pantalla completa, no veo el orbe",   # ambiguous: the model decides that one
    "pausa el vídeo",                                  # not about screen size at all
    "qué tiempo hace mañana",
])
def test_only_what_the_existing_licence_already_reads_as_leaving(monkeypatch, text):
    """No new words: the completion rides the licence that was already there (`minimize`)."""
    from nucleo.flash import show_target as st
    _state(monkeypatch, maximized="imagenes")
    assert st.fullscreen_exit_due(text, fired=False) == "", text


def test_the_completion_leaves_and_says_so(monkeypatch):
    from nucleo.flash import show_target as st
    _state(monkeypatch, maximized="imagenes")
    rows, emit = _emits()
    tags = []
    acted = st.fullscreen_exit_backstop("Y sal de pantalla completa.", fired=False,
                                        tag_emit=lambda a, e: tags.append((a, e)), emit=emit)
    assert acted is True
    assert tags == [("fullscreen", {"id": "imagenes", "on": False})], tags
    assert any(r[0] == "brain" and "COMPLETADA" in r[1] for r in rows), \
        "a completed claim must leave a line in the timeline — otherwise the next «why did it leave?» has no answer"


def test_the_voice_turn_runs_the_completion_before_the_close_backstop_and_marks_it():
    """Order matters: a turn about leaving full screen must never be read below as an order to close the
    whole widget (the V2-600 incident)."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    i = src.index("_show_target.fullscreen_exit_backstop(")
    j = src.index('if (not acted.get("closed")) and _canvas_lic.close_license(text, brief=_brief)')
    assert i < j, "the completion runs AFTER the close backstop — a leave order could be read as a close"
    body = src[i:j]
    assert 'fired="fullscreen_widget" in _tool_fired' in body, "it does not know whether the model already acted"
    assert '_tool_fired.add("fullscreen_widget")' in body, \
        "it does not mark the turn as handled — the close backstop below could still fire"
    assert "_bnotes.operator_half(text)" in body, "it reads the composed turn instead of HIS words (V2-678)"


def test_the_text_channel_reads_the_same_decision():
    """V2-252 — one decision, both channels."""
    src = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "fullscreen_exit_due as _fullscreen_exit_due" in src
    assert "_fullscreen_exit_due(text, fired=False)" in src
    assert 'action = f"canvas:unfullscreen:{_fx}"' in src
    assert 'action = f"canvas:unfullscreen:{_frid}"' in src, "an explicit `off` is not mirrored in the text channel"


# ── D · THE EVENT CARRIES THE DIRECTION TO THE SCREEN ───────────────────────────────────────────────────────
def test_the_frontend_passes_the_direction_and_allows_an_unnamed_exit():
    src = (ENGINE / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if 'd.label === "fullscreen"' in l)
    assert "d.on === false" in line, "an exit with no id is dropped before it reaches the desktop"
    call = src[src.index(line):src.index(line) + 400]
    assert re.search(r'desktop\.fullscreen\(d\.id \|\| "", d\.on === true \? true : \(d\.on === false \? false : undefined\)\)',
                     call), "the direction does not reach `Desktop.fullscreen(id, on)`"
