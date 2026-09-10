"""V2-650b — a widget the operator JUST closed does not reopen over chatter.

Measured live 2026-09-10 (sid 3d394…): «Johnny, cierra el widget de YouTube» closed it (the V2-567
guard discarded the model's spurious show, the backstop closed) — and eight seconds later room chatter
(«Avisando de… cuidado, que aquí está pasando algo») made the model re-emit that DISCARDED show_widget,
and nothing blocked it: the card reopened over nobody's order. V2-635 built licenses for close, video
and fullscreen; SHOW had none. The gate is narrow on purpose: it only guards a widget the operator
ordered closed in the last two minutes, and it opens again on a conjugated media/show request or when
his own words resolve to that widget — never on chatter.
"""
from __future__ import annotations

import pathlib
import re

from nucleo.flash import canvas_license as lic

ENGINE = pathlib.Path(__file__).resolve().parents[3]


def _fresh(monkeypatch):
    monkeypatch.setattr(lic, "_RECENT_CLOSES", {}, raising=True)


# ── 1 · the license, against the session's own sentences ─────────────────────────────────────────────────

def test_chatter_does_not_reopen_a_just_closed_widget(monkeypatch):
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    assert lic.reopen_license("youtube", "Avisando de de cuidado, que aquí está pasando algo.") is False


def test_a_real_request_reopens_it(monkeypatch):
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    for t in ("vuelve a abrir el youtube", "ponme otro vídeo de Ronaldinho", "muéstrame el youtube"):
        assert lic.reopen_license("youtube", t) is True, t


def test_naming_the_widget_alone_reopens_it_through_the_resolver(monkeypatch):
    """No conjugated verb, but his own words resolve to the widget with certainty (V2-082)."""
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    assert lic.reopen_license("youtube", "el youtube") is True


def test_a_widget_nobody_closed_is_untouched_by_the_gate(monkeypatch):
    _fresh(monkeypatch)
    assert lic.reopen_license("musica", "Avisando de de cuidado, que aquí está pasando algo.") is True


def test_the_window_expires(monkeypatch):
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    lic._RECENT_CLOSES["youtube"] -= lic._REOPEN_WINDOW_S + 1
    assert lic.reopen_license("youtube", "bla bla bla") is True


# ── 2 · every close door records, and both channels consult ──────────────────────────────────────────────

def test_every_close_door_notes_the_operator_close():
    nucleo_src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert nucleo_src.count("note_operator_close(") >= 3, \
        "the tag funnel, the close backstop and the close-not-delete guard must all record the close"
    exec_src = (ENGINE / "nucleo/actionmap/executor.py").read_text(encoding="utf-8")
    assert "note_operator_close(" in exec_src, "the fast lane's close is operator-ordered too"


def test_both_channels_consult_the_reopen_license():
    for rel in ("voice/engine/llm/providers/nucleo.py", "nucleo/flash/probe.py"):
        src = (ENGINE / rel).read_text(encoding="utf-8")
        assert re.search(r"reopen_license\(_rid, text", src), rel


def test_the_voice_guard_counts_the_turn_as_handled_not_void():
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    m = re.search(r"reopen_license\(_rid, text.*?elif _rid:", src, re.S)
    assert m, "the guard block moved — re-anchor this test"
    assert 'deduped["v"] = True' in m.group(0), \
        "a discarded drag is handled (V2-635), never a void for the mute backstop"
