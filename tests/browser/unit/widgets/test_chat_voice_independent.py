"""CHAT y VOZ son INDEPENDIENTES — V2-088.

Historia, porque explica por qué estos tests existen y por qué son tan literales:

V2-054 introdujo «modo chat = voz off»: abrir el ChatWall silenciaba a zaelar, con la idea de que abrir el chat
significaba «prefiero leer». La premisa es FALSA — el panel tiene cuatro pestañas (Chat/Procesos/Crons/Clusters)
y el operador entra a mirar una lista sin querer callar a nadie. Peor: el síntoma resultante («se ven los
subtítulos, procesa, hay volumen, pero no oigo nada») es indistinguible de un TTS averiado, y costó una sesión
entera diagnosticando una avería inexistente.

Hoy el reparto es: **el icono 🔊 es el ÚNICO dueño del silencio** y el chat es una VISTA MÁS — la respuesta
aparece en el chat igual que en los subtítulos y en la voz, las tres a la vez, nunca excluyéndose.

Son tests de FUENTE (no hay navegador en la batería determinista) y por eso comprueban ausencias además de
presencias: lo que hay que impedir es que alguien vuelva a CABLEAR el chat con el altavoz.
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[4] / "frontend" / "app"


def _code(path: Path) -> str:
    """El fichero SIN comentarios de línea. Estos tests prohíben ciertas llamadas, y la prosa que EXPLICA por qué
    están prohibidas las nombra — sin esto, el propio comentario que documenta la regla la hace fallar."""
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in path.read_text(encoding="utf-8").split("\n"))


CHATWALL = _code(FRONTEND / "components" / "ChatWall.js")
SESSION_LK = _code(FRONTEND / "services" / "session-lk.js")
SSE = _code(FRONTEND / "services" / "sse.js")
AGENT = (Path(__file__).resolve().parents[4] / "voice" / "engine" / "pipeline" / "agent.py").read_text(encoding="utf-8")


# ── el chat NO toca la voz ───────────────────────────────────────────────────────────────────────────────────
def test_chatwall_never_touches_the_speaker():
    """Ni silencia, ni des-silencia, ni manda la señal de síntesis. Abrir un panel no es una orden de audio."""
    assert "toggleBotMute" not in CHATWALL, "el ChatWall vuelve a mover el altavoz"
    assert "setVoiceOutput" not in CHATWALL, "el ChatWall vuelve a mandar la señal de síntesis al server"
    assert "botMuted" not in CHATWALL, "el ChatWall vuelve a leer el estado del altavoz"


def test_no_leftover_mute_restore_machinery():
    """El `_prevMuted` guardaba/restauraba el altavoz alrededor del chat. Si reaparece, el acoplamiento volvió."""
    assert "_prevMuted" not in CHATWALL


# ── el icono es el ÚNICO dueño del silencio ──────────────────────────────────────────────────────────────────
def test_the_speaker_toggle_is_what_tells_the_server():
    """Un solo interruptor, un solo dueño: `toggleBotMute` mueve el <audio> local Y avisa al server. Si solo
    hiciera lo primero, el icono volvería a mentir (se pondría en ON sin que nadie sintetice)."""
    body = SESSION_LK.split("export function toggleBotMute()")[1].split("\n}")[0]
    assert "setBotMuted" in body and "applyBotMute" in body
    assert "setVoiceOutput(!next)" in body, "el icono no avisa al server → volvería a mentir"


def test_reconnect_reconciles_against_the_icon_not_the_chat():
    """Al (re)conectar, el cliente re-afirma el estado deseado. Debe mirar el ICONO: reconciliar contra
    `chatOpen` deshacía la decisión del operador en cada reconexión."""
    assert "setVoiceOutput(!store.botMuted())" in SESSION_LK
    assert "setVoiceOutput(!store.chatOpen())" not in SESSION_LK


# ── la respuesta se ve en el chat SIEMPRE, con voz o sin ella ────────────────────────────────────────────────
def test_the_reply_reaches_the_chat_independently_of_audio():
    """`transcript/assistant` → `pushAgentChat`. Cuelga del texto, no del audio: por eso el chat muestra la
    respuesta tanto si zaelar la está diciendo en voz alta como si está silenciado."""
    branch = SSE.split('d.kind === "transcript"')[1].split("else if")[0]
    assert 'd.role === "assistant"' in branch and "pushAgentChat" in branch


# ── el servidor: la señal existe, pero su dueño es el operador ───────────────────────────────────────────────
def test_server_voice_toggle_is_not_labelled_as_chat_mode():
    """La etiqueta del evento es lo que un agente lee en /api/debug para diagnosticar «no se oye». Si dice
    «modo chat» apunta a una causa que ya no existe, y eso cuesta horas."""
    assert "zaelar-voice" in AGENT
    assert "voz OFF (modo chat" not in AGENT, "la etiqueta sigue culpando al chat"
    assert re.search(r"voz OFF \(el operador silenci", AGENT)


# ── el ruteo del panel conoce las cuatro pestañas ────────────────────────────────────────────────────────────
def test_panel_routing_whitelist_covers_every_tab():
    """El backend canonicaliza a chat|procesos|crons|clusters; si la lista blanca del frontend se queda corta,
    el server rutea bien y el cliente lo tira al suelo abriendo «Chat» (le pasó a `clusters` al nacer)."""
    from nucleo.flash import router
    branch = SSE.split('d.kind === "panel"')[1].split("else if")[0]
    for tab in ("procesos", "crons", "clusters"):
        assert f'"{tab}"' in branch, f"el frontend no acepta la pestaña «{tab}»"
        assert router._canon_panel(tab) == tab
