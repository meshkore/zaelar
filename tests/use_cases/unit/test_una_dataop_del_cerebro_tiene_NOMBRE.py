"""V2-390 — from the outside, all of the brain's data-ops looked the same.

The UI path (the operator touches a button) ALREADY emitted `widget/action` with the action name inside. The
BRAIN path did not: only the anonymous `widget/data` that triggers `store.save` came out, so an
`add_to_playlist` and a `set_volume` were the same event.

Measured in `play-music-and-build-playlist` (2026-08-27 13:29). Checked by hand against the live studio, with the
round just completed:

    yt        → {"videoId": "0iLF_rtUbq0", "title": "Música relajante para trabajar…", "paused": false}
    playlists → [{"id": "curro", "name": "Curro", "tracks": []}]

In other words: the music WAS PLAYING and the «Curro» playlist EXISTED. The verdict was **1/5, «hallucination of
success»**, and its textual reason: *«the mechanism proves (without `create_playlist`, without audio evidence)
that neither thing happened»*, citing «only generic data operations». The instrument blaming the product again,
and with the lowest possible score on two dimensions.

Two halves, because either one alone fixes nothing: the engine NAMES the op, and the harness READS it by name.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.use_cases.e2e.agent import verify as V


def _ev(label, wid, action=None, cat="widget"):
    e = {"cat": cat, "label": label, "id": wid}
    if action is not None:
        e["action"] = action
    return e


# ── the harness READS it by name ───────────────────────────────────────────────────────────────────────────────

def test_una_op_con_nombre_se_cuenta_por_su_NOMBRE():
    ops = V.widget_ops([_ev("action", "musica", "add_to_playlist")])
    assert ops == {"musica": {"add_to_playlist": 1}}


def test_dos_ops_DISTINTAS_no_se_confunden():
    """The heart of it: counting them by label produced `{action: 2}`, which is tantamount to saying nothing."""
    ops = V.widget_ops([_ev("action", "musica", "add_to_playlist"),
                        _ev("action", "musica", "set_volume")])
    assert ops == {"musica": {"add_to_playlist": 1, "set_volume": 1}}


def test_una_op_que_FALLO_se_cuenta_APARTE():
    """The widget refusing and the change taking effect are opposite facts."""
    ops = V.widget_ops([_ev("action", "musica", "add_to_playlist"),
                        _ev("action_failed", "musica", "add_to_playlist")])
    assert ops == {"musica": {"add_to_playlist": 1, "add_to_playlist✗": 1}}


def test_una_op_SIN_nombre_lo_DICE():
    """A silent gap is filled in; it must be named (V2-127/V2-133)."""
    assert V.widget_ops([_ev("action", "musica")]) == {"musica": {"(op sin nombre)": 1}}


def test_los_eventos_de_SIEMPRE_siguen_contandose_igual():
    """The other direction: `data`/`show`/`close` cannot change shape, because the rest of the report depends on it."""
    ops = V.widget_ops([_ev("data", "musica"), _ev("show", "youtube"), _ev("close", "youtube")])
    assert ops == {"musica": {"data": 1}, "youtube": {"show": 1, "close": 1}}


def test_la_instancia_se_sigue_colapsando_al_widget():
    assert V.widget_ops([_ev("action", "navegador::t2", "open")]) == {"navegador": {"open": 1}}


# ── the engine NAMES it ───────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def emisiones(monkeypatch):
    """Captures what the engine emits when executing a brain data-op."""
    vistos = []
    import voice.observer as _obs
    monkeypatch.setattr(_obs, "emit",
                        lambda kind, label, text="", role="", extra=None:
                        vistos.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    return vistos


def _corre(monkeypatch, resultado):
    import widgets.server_api as SA

    async def _disp(wid, action, payload):
        return resultado
    monkeypatch.setattr(SA, "_dispatch", _disp)
    return asyncio.run(SA.brain_action("musica", "add_to_playlist", {"playlist": "Curro"}))


def test_el_cerebro_NOMBRA_la_op_que_lanza(monkeypatch, emisiones):
    """The safeguard that would have been enough: the UI path already did this, but the brain path did not."""
    _corre(monkeypatch, {"ok": True, "playlist": "curro"})
    con_nombre = [e for e in emisiones if e["label"] == "action"]
    assert len(con_nombre) == 1
    assert con_nombre[0]["action"] == "add_to_playlist" and con_nombre[0]["id"] == "musica"


def test_una_op_que_el_widget_RECHAZA_emite_su_propio_evento(monkeypatch, emisiones):
    """«Nothing is playing» is a fact the judge needs; folding it into the success event is how a
    «Done.» that is not true survives."""
    _corre(monkeypatch, {"ok": False, "error": "nothing_playing", "message": "No suena nada ahora."})
    fallos = [e for e in emisiones if e["label"] == "action_failed"]
    assert len(fallos) == 1
    assert fallos[0]["error"] == "nothing_playing" and fallos[0]["is_error"] is True
    assert "No suena nada" in fallos[0]["text"]


def test_una_op_que_SALE_BIEN_no_emite_fallo(monkeypatch, emisiones):
    """The branch on the other side: always marking failure would make the event useless."""
    _corre(monkeypatch, {"ok": True})
    assert not [e for e in emisiones if e["label"] == "action_failed"]


def test_el_is_error_viaja_DENTRO_de_extra():
    """`emit` does not accept `is_error` as a kwarg, and extras are flattened into the event. With the standalone
    kwarg, a TypeError is raised and swallowed by the surrounding `except`: the failure event would NEVER be
    emitted. Committed while writing this, which is why the safeguard exists."""
    import inspect

    import voice.observer as _obs
    assert "is_error" not in inspect.signature(_obs.emit).parameters
