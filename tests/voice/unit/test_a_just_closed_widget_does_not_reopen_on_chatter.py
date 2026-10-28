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

from nucleo.acts import canvas as _door



from nucleo.flash import canvas_license as lic



def _fresh(monkeypatch):
    monkeypatch.setattr(lic, "_RECENT_CLOSES", {}, raising=True)


# ── 1 · the license, against the session's own sentences ─────────────────────────────────────────────────

def test_chatter_does_not_reopen_a_just_closed_widget(monkeypatch):
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    assert _door.reopen_ordered("youtube", "Avisando de de cuidado, que aquí está pasando algo.") is False


def test_a_real_request_reopens_it(monkeypatch):
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    for t in ("vuelve a abrir el youtube", "ponme otro vídeo de Ronaldinho", "muéstrame el youtube"):
        assert _door.reopen_ordered("youtube", t) is True, t


def test_naming_the_widget_alone_reopens_it_through_the_resolver(monkeypatch):
    """No conjugated verb, but his own words resolve to the widget with certainty (V2-082)."""
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    assert _door.reopen_ordered("youtube", "el youtube") is True


def test_a_widget_nobody_closed_is_untouched_by_the_gate(monkeypatch):
    _fresh(monkeypatch)
    assert _door.reopen_ordered("musica", "Avisando de de cuidado, que aquí está pasando algo.") is True


def test_the_window_expires(monkeypatch):
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    lic._RECENT_CLOSES["youtube"] -= lic._REOPEN_WINDOW_S + 1
    assert _door.reopen_ordered("youtube", "bla bla bla") is True


# ── 2 · every close door records, and the turn consults ──────────────────────────────────────────────────

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
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", _brief_reading({tb.CANVAS_KEY: "close", tb.TARGET_KEY: "youtube:close"}))
    assert _door.show_under_close(brief=object(), wid="youtube", words=False) is True, "THE BUG: the card came straight back"
    assert _door.show_under_close(brief=object(), wid="agenda", words=False) is False, "a close naming another card leaves this show alone"


def test_a_close_naming_nobody_shows_nothing_and_any_other_verdict_shows(monkeypatch):
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", _brief_reading({tb.CANVAS_KEY: "close", tb.TARGET_KEY: "none"}))
    assert _door.show_under_close(brief=object(), wid="youtube", words=False) is True
    monkeypatch.setattr(tb, "read", _brief_reading({tb.CANVAS_KEY: "show"}))
    assert _door.show_under_close(brief=object(), wid="youtube", words=False) is False
    monkeypatch.setattr(tb, "read", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no brief")))
    assert _door.show_under_close(brief=None, wid="youtube", words=False) is False, "no brief, no veto"


def test_the_paid_verdict_naming_the_card_reopens_it_at_the_door(monkeypatch):
    """refactor2710-04b T-03 — the door reads the turn's verdict before any word: a sure `canvas=show` whose catalogue
    names the just-closed card brings it back even when his words alone resolve to nothing; one naming another card
    does not. Disarm: `_shows_this` → False and the first assertion goes red."""
    from nucleo.turn import brief as tb
    _fresh(monkeypatch)
    lic.note_operator_close("youtube")
    monkeypatch.setattr(tb, "read", _brief_reading({tb.CANVAS_KEY: "show", tb.CATALOG_KEY: "youtube"}))
    assert _door.reopen_ordered("youtube", "bla bla bla", brief=object()) is True
    monkeypatch.setattr(tb, "read", _brief_reading({tb.CANVAS_KEY: "show", tb.CATALOG_KEY: "agenda"}))
    assert _door.reopen_ordered("youtube", "bla bla bla", brief=object()) is False
