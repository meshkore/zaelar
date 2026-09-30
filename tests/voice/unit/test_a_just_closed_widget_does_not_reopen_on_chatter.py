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

from tests import voice_turn_source as _vts

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
    nucleo_src = _vts.read(ENGINE / "voice/engine/llm/providers/nucleo.py")
    assert nucleo_src.count("note_operator_close(") >= 3, \
        "the tag funnel, the close backstop and the close-not-delete guard must all record the close"
    exec_src = (ENGINE / "nucleo/actionmap/executor.py").read_text(encoding="utf-8")
    assert "note_operator_close(" in exec_src, "the fast lane's close is operator-ordered too"


def test_both_channels_consult_the_reopen_license():
    for rel in ("voice/engine/llm/providers/nucleo.py", "nucleo/flash/probe.py"):
        src = _vts.read(ENGINE / rel)
        assert re.search(r"reopen_license\(_rid, text", src), rel


def test_the_voice_guard_counts_the_turn_as_handled_not_void():
    src = _vts.read(ENGINE / "voice/engine/llm/providers/nucleo.py")
    m = re.search(r"reopen_license\(_rid, text.*?elif _rid:", src, re.S)
    assert m, "the guard block moved — re-anchor this test"
    assert 'deduped["v"] = True' in m.group(0), \
        "a discarded drag is handled (V2-635), never a void for the mute backstop"


# ── V2-773 (2026-09-27, demo V7): the VERDICT closes, the model shows — the show loses ────────────────────
def _brief_reading(verdicts: dict):
    """A fake `turn_brief.read`: (choice, {"used": True}) for the keys given, the fallback otherwise."""
    def _read(handle, key, fallback, *, min_confidence=None):
        if key in verdicts:
            return verdicts[key], {"used": True, "confidence": 0.97}
        return fallback, {"used": False}
    return _read


def test_a_show_of_the_card_the_verdict_closes_is_a_closing_turn(monkeypatch):
    """«Stop it and close the video widget»: canvas=close (1.00), screen_action=youtube:close (0.97); the player
    closed and the model still called show_widget(youtube). The text guard saw nothing; the verdict does."""
    from nucleo.flash import turn_brief as tb
    monkeypatch.setattr(tb, "read", _brief_reading({tb.CANVAS_KEY: "close", tb.TARGET_KEY: "youtube:close"}))
    assert lic.closing_turn(object(), "youtube") is True, "THE BUG: the card came straight back"
    assert lic.closing_turn(object(), "agenda") is False, "a close naming another card leaves this show alone"


def test_a_close_naming_nobody_shows_nothing_and_any_other_verdict_shows(monkeypatch):
    from nucleo.flash import turn_brief as tb
    monkeypatch.setattr(tb, "read", _brief_reading({tb.CANVAS_KEY: "close", tb.TARGET_KEY: "none"}))
    assert lic.closing_turn(object(), "youtube") is True
    monkeypatch.setattr(tb, "read", _brief_reading({tb.CANVAS_KEY: "show"}))
    assert lic.closing_turn(object(), "youtube") is False
    monkeypatch.setattr(tb, "read", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no brief")))
    assert lic.closing_turn(None, "youtube") is False, "no brief, no veto"


def test_the_show_branch_asks_the_verdict_next_to_the_text_guard():
    src = _vts.read(pathlib.Path("voice/engine/llm/providers/nucleo.py"))
    assert "if _router.show_contradicts_the_order(text) or _canvas_lic.closing_turn(_brief, _wid):" in src


def test_the_fast_lens_door_asks_the_verdict_too():
    """Demo E5 (2026-09-27): «Close my messages» — the card closed, the model ran `mensajeria:close` (a view-op)
    over the now-closed card, and the lens door brought it back as a «turn-order». A close never brings the card."""
    src = _vts.read(pathlib.Path("voice/engine/llm/providers/nucleo.py"))
    i = src.index("_fx.carries(wid, action_name, _fx.DATA_READ) and not _cvis.is_open(wid)")
    assert "not _canvas_lic.closing_turn(_brief, wid)" in src[i:i + 200]
