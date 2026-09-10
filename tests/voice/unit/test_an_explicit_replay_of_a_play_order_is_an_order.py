"""V2-650 — an explicit replay of a play order is an ORDER, not context-bleed.

One live morning (session aed0736c, 2026-09-10): the «True Blue» playlist was built, playback failed
in silence, and the operator said «Vale, pues reproduce la lista», then «Vamos, dale al play, a la
primera canción» — and the data-op dedupe guard (V2-038) ate every replay, because its only escape
measures word overlap between the turn and the PAYLOAD, and no natural play order names
{"playlist": "true-blue"}. The missing discriminator is declared data plus grammar (V2-635 doctrine,
never intent): the widget itself declares which actions start production (`runtime.produce`), and the
turn either carries a conjugated media request or it does not. Agenda-class ops declare no production,
so the guard's founding case («borra el reloj» dragging the dentist's add_meeting) stays dead.
"""
from __future__ import annotations

import pathlib
import re

from nucleo.flash import canvas_license as lic

ENGINE = pathlib.Path(__file__).resolve().parents[3]


# ── 1 · the license, against the session's own sentences ─────────────────────────────────────────────────

def test_the_sessions_eaten_play_orders_now_pass():
    for t in ("Vale, pues reproduce la lista.", "Vamos, dale al play, a la primera canción."):
        assert lic.replay_license("musica", "play_playlist", t) is True, t


def test_turns_about_something_else_stay_deduped():
    """The other two turns of the same session that re-emitted play_playlist really WERE drag."""
    for t in ("Johnny, activa el modo word activate.",
              "Que ya aquí, como ya hay una ahí. Uf, tienen que quitar aquí."):
        assert lic.replay_license("musica", "play_playlist", t) is False, t


def test_a_widget_that_declares_no_production_never_gets_the_escape():
    """The guard's founding case: «borra el reloj» dragged the dentist's add_meeting (V2-038). Even a
    turn full of media verbs must not revive an agenda-class duplicate."""
    assert lic.replay_license("agenda", "add_meeting", "apunta otra vez lo del dentista") is False
    assert lic.replay_license("agenda", "add_meeting", "ponme un vídeo de gatos") is False


def test_a_non_produce_action_on_a_media_widget_stays_deduped():
    """add_to_playlist mutates the library, not the speaker: repeating it silently would re-add."""
    assert lic.replay_license("musica", "add_to_playlist", "reproduce la lista") is False


def test_the_declaration_is_read_not_hardcoded():
    """The escape rides `runtime.produce` — the declared list, exactly as producers.py reads it."""
    from widgets import producers
    assert producers.starts_production("musica", "play_playlist") is True
    assert producers.starts_production("agenda", "add_meeting") is False


# ── 2 · the voice provider consults the license inside the dedupe guard ──────────────────────────────────

def test_the_dedupe_guard_consults_the_replay_license():
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    m = re.search(r"_last = brain\._last_dataop.*?deduped\[\"v\"\] = True", src, re.S)
    assert m, "the dedupe guard block moved — re-anchor this test"
    assert "replay_license(wid, action_name, text)" in m.group(0), \
        "the guard must ask the replay license before eating an identical data-op"
