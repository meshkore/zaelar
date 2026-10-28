"""A refusal correction may only select a list he named or the card holds (music-playlist-reads-clean__es).

2026-10-11: «Ponme la lista True Blue.» → `musica:play_playlist {"playlist": "True Blue"}` was refused (no such
list). The same-turn correction (`act_repair.call_for_refusal`) re-issued it as `{"playlist": "Favoritos"}` — the
card's default list name, which he never said and the card did not hold. That call ran, was refused too, and its
refusal was the first thing he heard («No encuentro ninguna lista que se llame «Favoritos»»), so he apologised for
a word he never used. `repair_grounding.list_was_named` already bounded the promise pass; the refusal pass did not.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import act_repair as A
from nucleo.flash import repair_grounding as RG

EMPTY_CARD = "items ahora: NINGUNO — la tarjeta está ABIERTA pero VACÍA"


def _model_corrects_to(monkeypatch, fixed: dict, digest: str = EMPTY_CARD):
    from nucleo.flash import widget_read as WR
    from nucleo.llm import fast_client as FC

    async def _complete(self, msgs, on_tool_call=None, **kw):
        on_tool_call("widget_data", {"widget_id": "musica", "action": "play_playlist", "payload": fixed})
        return ""
    monkeypatch.setattr(FC.FastClient, "complete", _complete)
    monkeypatch.setattr(WR, "read", lambda wid: digest)
    notes = []
    monkeypatch.setattr(A, "_note", lambda wid, why, **kw: notes.append(why))
    return notes


def _correct(text: str = "Ponme la lista True Blue."):
    return asyncio.run(A.call_for_refusal(text, "musica", "play_playlist", {"playlist": "True Blue"},
                                          "No encuentro ninguna lista que se llame «True Blue»."))


def test_a_list_nobody_named_is_not_run_in_his_turn(monkeypatch):
    notes = _model_corrects_to(monkeypatch, {"playlist": "Favoritos"})
    assert _correct() is None
    assert any("nobody named" in n for n in notes), notes


@pytest.mark.parametrize("fixed, digest, text", [
    ({"playlist": "True Blue (Madonna)"}, "Listas: «True Blue (Madonna)» (9 canciones)", "Ponme la lista True Blue."),
    ({"playlist": "Favoritos"}, EMPTY_CARD, "Ponme la lista True Blue, o mis favoritos."),
])
def test_a_list_he_said_or_the_card_holds_still_corrects(monkeypatch, fixed, digest, text):
    _model_corrects_to(monkeypatch, fixed, digest)
    got = _correct(text)
    assert got and got["payload"] == fixed


def test_the_bound_reads_his_words_and_the_card_only():
    assert not RG.refusal_fix_grounded("musica", "play_playlist", {"playlist": "Favoritos"}, "pon True Blue", "")
    assert RG.refusal_fix_grounded("musica", "play_playlist", {"query": "Madonna"}, "pon True Blue", "")
