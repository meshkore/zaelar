"""fix02 · an empty recall on a live-thread question is not a refusal — session 6d19df41.

Measured live: «Can you reveal the tongue? It's four messages behind.» sent the recall tool
after durable pills for something that lives in the LIVE thread. The pills came back empty,
and `recall_spoken` composed from that void («dilo con naturalidad y pregunta» + «(nada
relevante guardado)») — which the model narrated as no-access: «I can't reveal any hidden
message or coded content... secret information». The operator: «It's not a secret.»

Pills can never answer a thread position, so composing from their emptiness only manufactures
refusals. Now: an empty recall on a thread-position turn short-circuits — the voice channel
asks which message through the deterministic clarify (V2-026: a hard "which one" never loses
to invented prose), the text channel keeps its original reply. An empty recall on anything
ELSE still composes as before.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from nucleo.flash import recall_heuristics as _rh
from nucleo.flash import second_pass as _sp


def _run(coro):
    return asyncio.run(coro)


# ── the classifier: thread positions, never topics ──
@pytest.mark.parametrize("txt", [
    "Can you reveal the tongue? It's four messages behind.",
    "show me the hotel, it's three messages back",
    "the restaurant — two messages ago",
    "read me that message again",
    "previous messages",
    "enseñame ese mensaje",
    "los mensajes anteriores",
    "esta cuatro mensajes atras",
    # `anteriores?` is "anteriore"+optional s: it matched the PLURAL and never the singular, so the most
    # natural Spanish way to point one message back walked straight through the guard (review 2026-09-20).
    "el mensaje anterior",
    "leeme el mensaje anterior",
    "dos mensajes anterior",
])
def test_thread_positions_match(txt):
    assert _rh.names_thread_position(txt), txt


@pytest.mark.parametrize("txt", [
    "what did I ask you to write?",
    "remind me of my anniversary",
    "do I have anything tonight?",
    "open my messages",
    "reply to the message from Claudia",
    "",
    "   ",
])
def test_anything_else_does_not_match(txt):
    assert not _rh.names_thread_position(txt), txt


# ── voice: empty pills + thread position → flag, nothing spoken ──
def test_recall_spoken_flags_empty_thread_and_speaks_nothing(monkeypatch):
    def _no_pills(query):  # sync: recall_spoken runs it via to_thread
        return "", []

    async def _boom(*a, **k):
        raise AssertionError("nothing to compose from — the model must never see the void")

    import nucleo.flash.prompt as _prompt
    monkeypatch.setattr(_prompt, "compose_recall", _no_pills)
    out = _run(_sp.recall_spoken(
        "Can you reveal the tongue? It's four messages behind.",
        "message about reveal the tongue", spec=None,
        emit=lambda *a, **k: None, speak=_boom)
    )
    assert out == "empty_thread"


def test_recall_spoken_still_composes_when_the_pills_answer(monkeypatch):
    import nucleo.flash.prompt as _prompt

    def _pills(query):  # sync: recall_spoken runs it via to_thread
        return "Puede que venga a cuento:\n· le gusta el buceo", [7]

    monkeypatch.setattr(_prompt, "compose_recall", _pills)
    said = []

    async def _speak(*a, **k):
        said.append(a)

    out = _run(_sp.recall_spoken(
        "Can you reveal the tongue? It's four messages behind.",
        "message about reveal the tongue", spec=None,
        emit=lambda *a, **k: None, speak=_speak)
    )
    assert out is None
    assert len(said) == 1 and "buceo" in said[0][0]


def test_recall_spoken_still_composes_empty_non_thread(monkeypatch):
    """An empty recall on an ORDINARY question keeps the old behavior — the natural "I don't
    remember" the compose was built for. Only thread positions short-circuit."""
    import nucleo.flash.prompt as _prompt

    def _no_pills(query):  # sync: recall_spoken runs it via to_thread
        return "", []

    monkeypatch.setattr(_prompt, "compose_recall", _no_pills)
    said = []

    async def _speak(*a, **k):
        said.append(a)

    out = _run(_sp.recall_spoken(
        "when is my anniversary?", "anniversary date", spec=None,
        emit=lambda *a, **k: None, speak=_speak)
    )
    assert out is None
    assert len(said) == 1


# ── probe: the SAME rule as the voice half, and no wider ──
#
# The first version of this pair was two bugs in one (review 2026-09-20):
#   · `recall_answer` returned "" on ANY empty recall, not just a thread position — so on «¿qué talla
#     uso?» with nothing remembered, the model's pre-memory improvisation stood in place of the honest
#     "no tengo ese dato" the compose produces. Two channels, one fact, two different answers.
#   · the test could not have caught it: it asserted by RAISING inside `collect`, and `recall_answer`
#     ends in a bare `except Exception` that swallows an AssertionError into the very "" being asserted.
#     It passed with the gate, without the gate, and with the function deleted down to `return ""`.
# Both halves are pinned here with a flag the swallow cannot eat.
def _no_pills_with_spy(monkeypatch):
    """compose_recall returns nothing; `composed` records whether the second pass ran anyway."""
    import nucleo.flash.prompt as _prompt
    composed = []

    def _no_pills(query):  # sync: recall_answer runs it via to_thread
        return "", []

    async def _spy(*a, **k):
        composed.append(True)
        return "lo que fuera que compusiera el modelo"

    monkeypatch.setattr(_prompt, "compose_recall", _no_pills)
    monkeypatch.setattr(_sp, "collect", _spy)
    return composed


def test_recall_answer_on_a_thread_position_keeps_the_callers_reply(monkeypatch):
    composed = _no_pills_with_spy(monkeypatch)
    out = _run(_sp.recall_answer("show me the tongue, it's four messages behind", "tongue", spec=None))
    assert out == "", "empty pills on a thread position must hand the turn back untouched"
    assert not composed, "nothing may be composed from the void — that is what narrated the refusal"


def test_recall_answer_on_a_normal_question_still_composes(monkeypatch):
    """An empty recall is not a thread position by default — the compose says «no tengo ese dato» itself.

    Skipping it here would hand the turn back to a reply the model wrote BEFORE consulting the memory,
    which is the invention this seam exists to prevent (V2-1xx, auditoría 2026-08-17).
    """
    composed = _no_pills_with_spy(monkeypatch)
    out = _run(_sp.recall_answer("¿qué talla uso?", "talla", spec=None))
    assert composed, "an ordinary empty recall must still compose — the void is the ANSWER, not a skip"
    assert out, "and the composed answer is what the caller gets"


# ── provider seam: the flag becomes the deterministic question ──
def _code(rel: str) -> str:
    src = Path(rel).read_text(encoding="utf-8")
    return re.sub(r"(?m)^\s*#.*$", "", src)


def test_the_provider_asks_which_message_on_empty_thread():
    code = _code("voice/engine/llm/providers/nucleo.py")
    assert '_recall_empty_thread = await _second_v.recall_spoken' in code
    assert 'clarify["msg"] = _say().ask_which_item_bare' in code
