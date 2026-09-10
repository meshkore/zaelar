#
# GRAMMAR licenses for model-driven canvas and media mutations (V2-635) — shared by BOTH channels
# (voice provider `nucleo.py` and the probe), same doctrine as `close_guards`: grammar, never intent
# (V2-095), and the same posture as stop_worker's GUARD 2 — what removes or replaces things on the
# operator's screen requires the operator to have SAID so in the very turn that fires it.
#
# Measured in ONE live session (34386d8f, 2026-09-09): «Muy bien, señora.» reloaded the playing video;
# «¿Pero por qué lo has cambiado otra vez?» reloaded it again; «Vale, Johnny, cierra el vídeo» loaded
# ANOTHER video instead of closing; «Johnny eres tonto» and «¿Y por qué lo has quitado?» each closed the
# widget nobody asked to close (the first one emptied the loaded video, so the following «Continúa el
# vídeo» honestly died with «No hay ningún vídeo cargado»); and «Johnny pausa el vídeo» / «minimiza el
# vídeo» became fullscreen three times. Every one is the model dragging its PREVIOUS tool call into a
# turn whose words license nothing of the kind — context-bleed, the exact class the data-op dedupe and
# the stop_worker guard already block for their own tools.
#
from __future__ import annotations

import re as _re

from .close_guards import looks_like_close
from .text_norm import _norm_txt

# Conjugated REQUEST forms only — a participle after «haber» narrates the past and licenses nothing
# («¿por qué lo has cambiado?» is a complaint, not an order), which is why the stems are spelled out
# instead of a broad \w* that would swallow «cambiado»/«puesto». «otro/otra/siguiente» license a swap by
# themselves («otro vídeo de Ronaldinho»).
_MEDIA_REQ_RE = _re.compile(
    r"\b(?:pon(?:me|te|le|lo|la|gas?|ed)?|carga(?:me|lo|la)?|cargar|busca(?:me|lo|la)?|buscar|"
    r"reproduce(?:me|lo|la)?|reproducir|quiero|dame|dale|abre(?:me|lo|la)?|abrir|muestra(?:me)?|"
    r"ensena(?:me)?|veamos|vemos|ver|cambia(?:me|lo|la)?|cambiar|repite(?:me|lo)?|repetir|"
    # «otro/otra» licenses only NEXT TO a media noun: «otra vez» in a complaint («¿por qué lo has
    # cambiado otra vez?») and «otra cosa» in chatter were the measured false positives.
    r"otr[oa]\s+(?:video\w*|cancion\w*|tema|peli\w*|capitulo|episodio|clip|documental)|"
    r"siguiente|anterior|"
    r"play|put|load|show|search|find|watch|another|next|previous)\b")
_NEG_MEDIA_RE = _re.compile(
    r"\bno\s+(?:me\s+|te\s+|lo\s+|la\s+|los\s+|las\s+)?(?:pong\w*|carg\w*|busq\w*|reproduz\w*|"
    r"cambi\w*|abr\w*|muestr\w*|repit\w*)\b|\bdon'?t\s+(?:play|put|load|show|search)\b")

# Screen-size grammar: the same "conjugated forms, no participles" rule. GROW routes to the fullscreen
# toggle; SHRINK routes to the canvas `minimize` order (desktop.shrink decides the one honest step down).
_GROW_RE = _re.compile(
    r"\b(?:pantalla\s+completa|full\s*screen|fullscreen|maximiza\w*|agranda\w*|amplia\w*|"
    r"(?:mas|más)\s+grande|maximize|enlarge|bigger|larger)\b")
_SHRINK_RE = _re.compile(
    r"\b(?:minimiza\w*|encoge\w*|reduce\w*|achica\w*|(?:mas|más)\s+peque\w*|"
    r"minimize|shrink|smaller)\b")
# «quita/sal de la pantalla completa» asks to LEAVE the mode — shrink, not the grow toggle.
_EXIT_FS_RE = _re.compile(
    r"\b(?:quita\w*|sal|salir|salte|cierra|deja|exit|leave|quit)\b[^.]{0,25}"
    r"\b(?:pantalla\s+completa|full\s*screen|fullscreen)\b")


# A SHORT bare affirmative answers the model's own offer («¿busco de nuevo el vídeo?» → «Sí») and must
# keep licensing the load. Short only: «si» in a long sentence is a conditional, not a yes.
_AFFIRM_RE = _re.compile(r"\b(?:si|vale|venga|claro|hazlo|ok|okey|okay|yes|yeah|sure|adelante)\b")


def video_license(text: str) -> bool:
    """True when the turn ASKS for media — the words that may carry a `play_video` (a load that replaces
    whatever is playing). Chatter, praise, insults and complaints about a past change license nothing."""
    n = _NEG_MEDIA_RE.sub(" ", _norm_txt(text))
    if _MEDIA_REQ_RE.search(n):
        return True
    return len(n.split()) <= 4 and bool(_AFFIRM_RE.search(n))


def close_license(text: str) -> bool:
    """True when the turn ORDERS a close — `close_guards.looks_like_close` verbatim (negations and
    narrated closes already excluded there). A model-emitted [[close]] without it is drag, not obedience."""
    return looks_like_close(text)


def fullscreen_license(text: str) -> str:
    """'' (no screen-size words at all: a fullscreen_widget call is drag — the measured «pausa el vídeo» →
    fullscreen), 'minimize' (the turn asks to go smaller / leave full screen), or 'fullscreen' (the turn
    asks for full screen / bigger — the toggle)."""
    n = _norm_txt(text)
    if _EXIT_FS_RE.search(n) or _SHRINK_RE.search(n):
        return "minimize"
    if _GROW_RE.search(n):
        return "fullscreen"
    return ""


def replay_license(wid: str, action: str, text: str) -> bool:
    """True when a data-op IDENTICAL to the one just executed is a fresh ORDER, not drag. The dedupe
    guard (V2-038) measures the turn's words against the payload only, so «reproduce la lista» and
    «dale al play» share zero words with {"playlist": "true-blue"} and a legitimate replay died in
    silence three turns in a row (measured live 2026-09-10, session aed0736c: playback had failed mute
    and every explicit play order after it was eaten as context-bleed). Two facts decide, no intent:
    the action must be one the widget itself DECLARES as starting production (manifest
    `runtime.produce` — agenda-class ops declare none and keep the full dedupe, so the V2-038 dentist
    duplicate stays dead), and the turn must carry a conjugated media request (the same grammar that
    licenses a video load)."""
    if not (wid and action):
        return False
    try:
        from widgets import producers
        if not producers.starts_production(wid, action):
            return False
    except Exception:
        return False
    return video_license(text)
