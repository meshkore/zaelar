"""V2-787 — a video he NAMES in this turn is not context-bleed, and a refused close is not claimed as done.

1. `play_video` was vetoed as context-bleed on «Venga, ponnos un vídeo de Madonna.»: the verb table had no
   «ponnos» and the turn verdict was off, so the only reader left was a conjugation list. Bleed is the model
   replaying a PREVIOUS call — whose query is absent from his words. A call whose query he named in this very
   turn cannot be bleed. The licence reads the call's own terms against his words (any language, no verb
   table) and subtracts the player's declared vocabulary and whatever the player already holds, so praise or
   a complaint about what plays still reloads nothing.
2. `close_widget` logged «🪟 close_widget(close) → canvas» right after the canvas route refused the same close,
   and counted the call as an act, while the card stayed. The route's refusal is now its caller's answer.
"""
from __future__ import annotations

import pytest

from nucleo.flash import canvas_license as lic


@pytest.fixture
def player(monkeypatch):
    """The player's store, set per test: what is loaded right now."""
    from widgets import store
    state = {"db": {}}
    real = store.load

    def _load(wid, default=None, **kw):
        if wid == "youtube":
            if isinstance(state["db"], Exception):
                raise state["db"]
            return dict(state["db"])
        return real(wid, default, **kw)

    monkeypatch.setattr(store, "load", _load)
    return state


# ── 1 · the licence: his words name the call's content ───────────────────────────────────────────────────

def test_the_measured_order_licenses_its_own_load(player):
    said = "Venga, ponnos ponnos un vídeo de Madonna."
    assert lic.video_license(said, query="Madonna") is True
    # …and its follow-ups, which named her again over an empty card
    assert lic.video_license("Pues no estamos viendo ningún vídeo de Madonna, se ha abierto YouTube, "
                             "pero está todo en blanco.", query="Madonna") is True
    assert lic.video_license("no lo has cambiado por Like a Prayer. Para encontrar esa canción.",
                             query="Madonna Like a Prayer") is True


def test_the_verb_table_did_not_grow(player):
    """CRIT-W10: the fix is the class. Without the call's query the same sentence licenses nothing."""
    assert lic.video_license("Venga, ponnos ponnos un vídeo de Madonna.") is False


def test_it_reads_any_alphabet(player):
    assert lic.video_license("Давай Мадонну", query="Мадонну") is True
    assert lic.video_license("gimme some Madonna", query="Madonna greatest hits") is True


def test_bleed_still_dies(player):
    """The previous query replayed into a turn that names nothing of it."""
    player["db"] = {"videoId": "abc", "title": "Ronaldinho skills", "channel": "Futbol"}
    for t in ("Muy bien, señora.", "¿Pero por qué lo has cambiado otra vez?", "Johnny eres tonto.",
              "Refresca la página."):
        assert lic.video_license(t, query="Ronaldinho") is False, t


def test_praise_naming_what_plays_does_not_reload_it(player):
    player["db"] = {"videoId": "v1", "title": "Vogue (Official Video)", "channel": "Madonna"}
    assert lic.video_license("Qué bien suena Madonna.", query="Madonna") is False
    assert lic.video_license("¿Por qué has puesto Madonna?", query="Madonna Vogue") is False
    # …but naming something ELSE of hers is a new order
    assert lic.video_license("Madonna, Like a Prayer.", query="Madonna Like a Prayer") is True


def test_the_players_own_vocabulary_names_a_card_not_content(player):
    assert lic.video_license("¿Qué vídeo es este?", query="vídeo de gatos") is False
    assert lic.video_license("Is that youtube?", query="youtube") is False


def test_an_unreadable_player_keeps_the_old_veto(player):
    player["db"] = RuntimeError("store down")
    assert lic.video_license("Madonna.", query="Madonna") is False


def test_voice_execute_runs_the_named_load():
    from nucleo.flash import video_turn as vt
    applied, deduped = [], {"v": False}
    vt.voice_execute({"query": "Madonna"}, "Venga, ponnos ponnos un vídeo de Madonna.",
                     lambda *a, **k: None, lambda *a: applied.append(a), deduped)
    assert applied == [("youtube", "load", {"query": "Madonna"})]
    assert deduped["v"] is False


# ── 2 · a refused close is not a close ───────────────────────────────────────────────────────────────────

def test_a_close_the_canvas_route_refuses_is_not_claimed():
    from nucleo.flash import show_target
    events = []
    rid = show_target.close_dispatch({"widget_id": "agenda", "mode": "close"}, lambda a, x: False,
                                     lambda *a, **k: events.append(a))
    assert rid == "", "a refused close is not an act of the turn"
    assert not any("close_widget(" in str(a[1]) for a in events), events


def test_a_close_the_route_runs_is_claimed_as_before():
    from nucleo.flash import show_target
    events = []
    rid = show_target.close_dispatch({"widget_id": "agenda", "mode": "close"}, lambda a, x: None,
                                     lambda *a, **k: events.append(a))
    assert rid == "agenda"
    assert any("close_widget(close)" in str(a[1]) for a in events)


def test_the_voice_close_guard_answers_false(monkeypatch):
    """The voice tag route returns False on its context-bleed refusal — the value `close_dispatch` reads."""
    from nucleo.flash import tool_executor_widget as txw, tool_executor_widget_calls as calls
    monkeypatch.setattr(txw._close_cancel, "inside_or_cancelled", lambda *a, **k: False)
    monkeypatch.setattr(txw._canvas_lic, "close_license", lambda *a, **k: False)
    monkeypatch.setattr(txw._show_target, "close_has_order", lambda *a, **k: (False, ""))
    rows, deduped = [], {"v": False}
    out = calls._tag_emit(
        "close", {"id": "youtube"}, _apply_widget_data=None, _brief=None, _is_meta_widget_question=None,
        _norm_nfkd=None, _on_tool_call=None, _request_delete_confirm=None, _show_guard_target=None,
        _show_target_instance=None, _shown_ids=set(), _spawn=None, acted={}, aside={}, brain=None, canvas_h=None,
        cron_seen={}, deduped=deduped, emit=lambda *a, **k: rows.append(a), escalate_req={"v": None},
        text="Desde el principio.")
    assert out is False and deduped["v"] is True
    assert not any(a[0] == "widget" for a in rows), "the refused close must not reach the canvas"
