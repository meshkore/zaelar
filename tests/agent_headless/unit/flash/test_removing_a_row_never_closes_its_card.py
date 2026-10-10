"""V2-781 — «remove the third one in the list, whatever it is» CLOSED the video card.

Measured in `la-cola-de-video-con-palabras-imprecisas` (ES and EN, 2026-10-10). Two doors closed the card on
a sentence about one of its rows:

  · the canvas verdict read `close` at 0.98 for «remove the third one in the list» / «quita el tercero» —
    its criterion said «remove a widget or card», and a ROW is not a card (fixed in its wording, measured live
    before and after: 0.98 close → 0.88 neither);
  · the close backstop (voice `post_stream_lanes`, text `probe_mirrors`) reaches the only open card BY
    CONTEXT — `identify` answers `youtube` with `by_context` for any sentence when it is the one card open —
    and `quita` is a close verb. «Quita el tercero» therefore took the whole player off the screen.

A sentence that reaches a card only by context and names one of its ROWS — a position word, or a row's own
title — is an order inside the card, not a close of it. Read from the card's state (`ref_index`) and from the
closed position-word class `refs` already owns, never from a verb table.
"""
from __future__ import annotations

import pathlib

import pytest

from nucleo.flash import close_guards as CG

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def queue(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.youtube import data as yt
    db = yt._load()
    db["list"] = [{"videoId": "aaaaaaaaaaa", "title": "Opus - Live Is Life | Maradona Calentamiento 1989"},
                  {"videoId": "bbbbbbbbbbb", "title": "El Mejor Documental de Diego Armando Maradona"},
                  {"videoId": "ccccccccccc", "title": "Diego Maradona Prime Argentina"}]
    store.save(yt.WID, db)
    return yt


@pytest.mark.parametrize("said", [
    "quita el tercero",
    "Weird. Ok just remove the third one in the list, whatever it is.",
    "El número dos, tío, el segundo de la lista. Ese quítalo.",
    "drop the last one",
    "quita el 2",
])
def test_a_position_word_names_a_row(said):
    assert CG.names_a_row("youtube", said) is True


def test_a_rows_title_names_a_row(queue):
    assert CG.names_a_row("youtube", "Mejor quita el de Live Is Life, que no me apetece.") is True


@pytest.mark.parametrize("said", ["quítalo", "ciérralo", "close it", "quita eso", "hide that"])
def test_a_bare_close_names_no_row(said, queue):
    assert CG.names_a_row("youtube", said) is False


def test_both_close_backstops_ask_it():
    """The two channels' close backstops must agree — the rule is shared as a function, never copied — and so
    does the verdict's own completion of a mute turn (`complete_canvas`, read by both)."""
    for rel in ("nucleo/flash/post_stream_lanes.py", "nucleo/flash/probe_mirrors.py"):
        assert "_closeg.unless_a_row(" in (ENGINE / rel).read_text(encoding="utf-8"), rel
    assert "_cg.keep_cards(" in (ENGINE / "nucleo/flash/direct_action.py").read_text(encoding="utf-8")


def test_a_card_reached_by_context_is_kept_when_a_row_is_named():
    by_context = {"match": "youtube", "by_context": True}
    assert CG.unless_a_row("youtube", "quita el tercero", by_context) is None
    assert CG.unless_a_row("youtube", "quita el tercero", {}) is None          # the one-open-card fallback
    assert CG.unless_a_row("youtube", "quítalo", by_context) == "youtube"


def test_a_card_he_named_still_closes():
    named = {"match": "youtube", "by_context": False}
    assert CG.unless_a_row("youtube", "cierra el vídeo del tercero", named) == "youtube"
    assert CG.unless_a_row(None, "quita el tercero", {}) is None


def test_a_sure_close_verdict_over_a_row_closes_nothing(monkeypatch):
    """`complete_canvas` with a 0.99 `close` and no card named: a row reference keeps the card on screen."""
    from nucleo.flash import direct_action as DA
    from nucleo.flash import show_target as ST
    monkeypatch.setattr(DA, "sure_canvas", lambda brief: "close")
    monkeypatch.setattr(DA, "from_brief", lambda brief: ("", ""))
    monkeypatch.setattr(DA, "named_cards", lambda text: [])
    monkeypatch.setattr(ST, "close_target", lambda wid: "youtube")
    tags = []
    verb = DA.complete_canvas({}, tag_emit=lambda a, x: tags.append((a, x)), emit=lambda *a, **k: None,
                              operator_text="Weird. Ok just remove the third one in the list, whatever it is.")
    assert tags == [] and verb == ""
    verb = DA.complete_canvas({}, tag_emit=lambda a, x: tags.append((a, x)), emit=lambda *a, **k: None,
                              operator_text="close it")
    assert tags == [("close", {"id": "youtube"})] and verb == "close"
