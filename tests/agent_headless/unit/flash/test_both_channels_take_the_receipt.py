"""Both channels take the receipt (V2-781): the text channel beside its delivery backstop, the voice channel in its
bare acks, read from what HIS turn did on the canvas (`canvas_focus.this_turn_acts`) — the voice words have already
streamed, so only an ack it would have said bare is replaced (the `delivery.apply_to_reply` precedent).
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nucleo.flash import card_receipt as CR
from nucleo.flash import direct_action as DA

ENGINE = Path(__file__).resolve().parents[4]
THREE = ["youtube", "musica", "agenda"]


def _brief(screen: str = "", screen_conf: float = 0.54, canvas: str = "close", canvas_conf: float = 0.99,
           open_ids=THREE) -> dict:
    ev = threading.Event()
    ev.set()
    res = {}
    if screen:
        res["screen_action"] = {"choice": screen, "confidence": screen_conf}
    if canvas:
        res["canvas"] = {"choice": canvas, "confidence": canvas_conf}
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids), "result": res}


@pytest.fixture
def screen(monkeypatch):
    import server.voice_api as _va
    from memory import api as _memapi
    box = {"open": list(THREE)}
    monkeypatch.setattr(_va, "open_instances", lambda: list(box["open"]))
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(box["open"])})
    monkeypatch.setattr(_memapi, "kv_get", lambda k, *a, **kw: None)
    from nucleo import canvas_focus
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "")
    return box


@pytest.fixture
def english(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")


@pytest.fixture
def spanish(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")


def _gesture(brief, text: str) -> list:
    tags = []
    DA.complete_canvas(brief, tag_emit=lambda a, x: tags.append((a, x.get("id"))), emit=lambda *a, **k: None,
                       operator_text=text)
    return tags


def test_the_voice_turn_is_wired():
    settle = (ENGINE / "nucleo/flash/post_stream_settle.py").read_text(encoding="utf-8")
    assert settle.count("_pst_receipt.voice_ack(") == 2


def test_the_voice_receipt_reads_what_his_turn_did(screen, english):
    from nucleo import canvas_focus as CF
    CF.note("transcript", "", role="user")
    CF.note("widget", "close", extra={"id": "musica", "src": "flash"})
    CF.note("widget", "data:volume_down", extra={"id": "youtube", "src": "flash"})
    CF.note("widget", "close", extra={"id": "agenda", "src": "user"})     # his own tab echoing back: not his order
    assert CF.this_turn_acts() == [("musica", "close", "close"), ("youtube", "control", "volume_down")]
    assert CR.voice_ack("Done.").startswith("I've closed Music.")
    CF.note("transcript", "", role="user")
    assert CF.this_turn_acts() == [] and CR.voice_ack("Done.") == "Done."
