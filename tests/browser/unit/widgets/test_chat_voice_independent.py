"""CHAT and VOICE are INDEPENDENT — V2-088.

History, because it explains why these tests exist and why they are so literal:

V2-054 introduced «chat mode = voice off»: opening the ChatWall muted zaelar, based on the idea that opening the chat
meant «I prefer to read». The premise is FALSE — the panel has four tabs (Chat/Processes/Crons/Clusters)
and the operator goes in to look at a list without wanting to silence anyone. Worse: the resulting symptom («the
subtitles are visible, it processes, there is volume, but I hear nothing») is indistinguishable from broken TTS, and it
took an entire session to diagnose a nonexistent failure.

Today the division is: **the 🔊 icon is the ONLY owner of muting** and the chat is JUST ANOTHER VIEW — the response
appears in the chat just as it does in the subtitles and in the voice, all three at once, never excluding one another.

These are SOURCE tests (there is no browser in the deterministic suite), so they check absences as well as
presences: what must be prevented is someone WIRING the chat back to the speaker.
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[4] / "frontend" / "app"


def _code(path: Path) -> str:
    """The file WITHOUT line comments. These tests prohibit certain calls, and the prose EXPLAINING why
    they are prohibited names them — without this, the very comment documenting the rule makes it fail."""
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in path.read_text(encoding="utf-8").split("\n"))


CHATWALL = _code(FRONTEND / "components" / "ChatWall.js")
SESSION_LK = _code(FRONTEND / "services" / "session-lk.js")
SSE = _code(FRONTEND / "services" / "sse.js")
AGENT = (Path(__file__).resolve().parents[4] / "voice" / "engine" / "pipeline" / "agent.py").read_text(encoding="utf-8")


# ── the chat does NOT touch voice ─────────────────────────────────────────────────────────────────────────────
def test_chatwall_never_touches_the_speaker():
    """It neither mutes, unmutes, nor sends the synthesis signal. Opening a panel is not an audio command."""
    assert "toggleBotMute" not in CHATWALL, "el ChatWall vuelve a mover el altavoz"
    assert "setVoiceOutput" not in CHATWALL, "el ChatWall vuelve a mandar la señal de síntesis al server"
    assert "botMuted" not in CHATWALL, "el ChatWall vuelve a leer el estado del altavoz"


def test_no_leftover_mute_restore_machinery():
    """`_prevMuted` saved/restored the speaker around the chat. If it reappears, the coupling has returned."""
    assert "_prevMuted" not in CHATWALL


# ── the icon is the ONLY owner of muting ─────────────────────────────────────────────────────────────────────
def test_the_speaker_toggle_is_what_tells_the_server():
    """One switch, one owner: `toggleBotMute` moves the local <audio> AND notifies the server. If it only
    did the former, the icon would lie again (it would switch to ON without anyone synthesizing)."""
    body = SESSION_LK.split("export function toggleBotMute()")[1].split("\n}")[0]
    assert "setBotMuted" in body and "applyBotMute" in body
    assert "setVoiceOutput(!next)" in body, "el icono no avisa al server → volvería a mentir"


def test_reconnect_reconciles_against_the_icon_not_the_chat():
    """When (re)connecting, the client reasserts the desired state. It must look at the ICON: reconciling against
    `chatOpen` undid the operator's decision on every reconnection."""
    assert "setVoiceOutput(!store.botMuted())" in SESSION_LK
    assert "setVoiceOutput(!store.chatOpen())" not in SESSION_LK


# ── the response is ALWAYS visible in the chat, with or without voice ───────────────────────────────────────
def test_the_reply_reaches_the_chat_independently_of_audio():
    """`transcript/assistant` → `pushAgentChat`. It depends on the text, not the audio: that is why the chat shows the
    response both when zaelar is saying it aloud and when it is muted."""
    branch = SSE.split('d.kind === "transcript"')[1].split("else if")[0]
    assert 'd.role === "assistant"' in branch and "pushAgentChat" in branch


# ── the server: the signal exists, but its owner is the operator ─────────────────────────────────────────────
def test_server_voice_toggle_is_not_labelled_as_chat_mode():
    """The event label is what an agent reads in /api/debug to diagnose «no sound». If it says
    «chat mode», it points to a cause that no longer exists, and that costs hours."""
    assert "zaelar-voice" in AGENT
    assert "voz OFF (modo chat" not in AGENT, "la etiqueta sigue culpando al chat"
    assert re.search(r"voz OFF \(el operador silenci", AGENT)


# ── the panel routing knows the four tabs ───────────────────────────────────────────────────────────────────
def test_panel_routing_whitelist_covers_every_tab():
    """The backend canonicalizes to chat|processes|crons|clusters; if the frontend whitelist is too short,
    the server routes correctly and the client drops it by opening «Chat» (that happened to `clusters` at birth)."""
    from nucleo.flash import router
    branch = SSE.split('d.kind === "panel"')[1].split("else if")[0]
    for tab in ("procesos", "crons", "clusters"):
        assert f'"{tab}"' in branch, f"el frontend no acepta la pestaña «{tab}»"
        assert router._canon_panel(tab) == tab


def test_the_panel_can_be_closed_by_voice_not_only_opened():
    """2026-08-10: the operator asked to close the chat FIVE times («also close the chat», «close the system
    chat», «close the chat window»), zaelar replied «okay, closed» each time, and it stayed open — it had to be
    closed with the ✕. The chat is NATIVE UI, so [[close]] does not touch it, and `show_panel` only knew how to open: the
    capability did not exist and the turn lied. Worse than being unable is saying yes."""
    branch = SSE.split('d.kind === "panel"')[1].split("} else if")[0]
    assert 'd.label === "close"' in branch, "el frontend debe distinguir abrir de cerrar"
    assert "setChatOpen(false)" in branch, "…y cerrarlo de verdad"
    assert "setChatOpen(true)" in branch, "…sin perder el abrir"
