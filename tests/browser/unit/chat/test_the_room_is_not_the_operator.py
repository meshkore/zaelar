"""Exposes the ambient-isolation contract to pytest/Test Observatory (see the .mjs for the measured session)."""

import shutil
import subprocess
from pathlib import Path

import pytest
from tests import voice_turn_source as _vts   # V2-778 F1: a split file is read with its moved pieces

SCRIPT = Path(__file__).with_name("test_the_room_is_not_the_operator.mjs")


def test_the_room_is_not_the_operator() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the ambient-isolation contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_typed_line_reaches_every_wall_and_the_typing_tab_paints_it_once() -> None:
    """V2-773 — the operator, watching his own Chrome while an orchestrator drove the agent through the chat:
    every reply was on his wall and none of the orders. `sse.js` had been waiting for a `text-injected`
    transcript nobody emitted; the tab that types paints its own bubble and no other tab ever heard of it.
    Now the engine announces every typed line the way the STT announces a final transcript, and the tab that
    typed it recognises its own last line instead of painting it twice."""
    root = Path(__file__).resolve().parents[4]
    agent = _vts.read(root / "voice/engine/pipeline/agent.py")
    i = agent.index('_emit("brain", "📥 chat/paste recibido", text=txt, role="user")')
    assert '_emit("transcript", "text-injected chat", text=txt, role="user")' in agent[i:i + 900], (
        "a typed line must leave the same trace as a spoken one, right after it is received")
    sse = (root / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    assert '(d.label || "").startsWith("text-injected")' in sse, "the wall reads the typed label by prefix"
    j = sse.index("if (typed) {")
    block = sse[j:j + 700]
    assert 'store.chatMsgs' in block and 'last.role === "you" && last.text === d.text' in block, (
        "the typing tab must recognise its own bubble, or every typed line paints twice there")
    assert 'store.pushChat({ role: "you", text: d.text })' in block
