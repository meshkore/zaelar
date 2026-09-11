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
import time as _time

from .close_guards import looks_like_close
from .text_norm import _norm_txt
from .verb_forms import alternation as _en

# Conjugated REQUEST forms only — a participle after «haber» narrates the past and licenses nothing
# («¿por qué lo has cambiado?» is a complaint, not an order), which is why the stems are spelled out
# instead of a broad \w* that would swallow «cambiado»/«puesto». «otro/otra/siguiente» license a swap by
# themselves («otro vídeo de Ronaldinho»).
#
# V2-664 — the INFINITIVE is a request form too, and it was the one missing. Spanish asks for media through
# a periphrasis far more often than through a bare imperative: «me vas a poner el vídeo», «¿puedes ponerme
# la canción?», «voy a ponerte…». Every other verb here already spells its infinitive out (cargar, buscar,
# reproducir, abrir, cambiar, repetir) — `poner` did not, and `pon(?:me|te|le|lo|la|gas?|ed)?` cannot reach
# it, because «poner» is «pon» followed by word characters and the \b fails. Measured live 2026-09-11
# (session eedf7f9b): «Bien, me vas a poner el vídeo del Apolo 11 llegando a la luna» → the model fired
# `play_video(query="Apolo 11 llegando a la luna")`, this license read it as context-bleed and ate it, and
# the turn ended saying «Y ahora te pongo el vídeo del Apolo 11» over a video that never loaded.
_MEDIA_REQ_RE = _re.compile(
    r"\b(?:pon(?:me|te|le|lo|la|gas?|ed)?|"
    r"pon(?:er|iendo|dr[aáeé])\w*|mostrar(?:me|lo|la)?|ensenar(?:me|lo|la)?|"
    r"carga(?:me|lo|la)?|cargar|busca(?:me|lo|la)?|buscar|"
    r"reproduce(?:me|lo|la)?|reproducir|quiero|dame|dale|abre(?:me|lo|la)?|abrir|muestra(?:me)?|"
    r"ensena(?:me)?|veamos|vemos|ver|cambia(?:me|lo|la)?|cambiar|repite(?:me|lo)?|repetir|"
    # «otro/otra» licenses only NEXT TO a media noun: «otra vez» in a complaint («¿por qué lo has
    # cambiado otra vez?») and «otra cosa» in chatter were the measured false positives.
    r"otr[oa]\s+(?:video\w*|cancion\w*|tema|peli\w*|capitulo|episodio|clip|documental)|"
    r"siguiente|anterior|"
    # V2-677 — the English half used to be BARE STEMS while the Spanish half was fully conjugated, so
    # «with playing the video», «start playing it» and «keep showing me» licensed nothing. Measured live
    # (session 366787ed): four English video orders in two minutes eaten as context-bleed. `verb_forms`
    # derives the inflections instead of spelling them out, so a stem added here brings its own forms.
    + _en("play", "put", "load", "show", "search", "find", "watch", "open", "display", "bring")
    + r"|another|next|previous)\b")
_NEG_MEDIA_RE = _re.compile(
    r"\bno\s+(?:me\s+|te\s+|lo\s+|la\s+|los\s+|las\s+)?(?:pong\w*|carg\w*|busq\w*|reproduz\w*|"
    r"cambi\w*|abr\w*|muestr\w*|repit\w*)\b|\bdon'?t\s+(?:play|put|load|show|search)\b")

# Screen-size grammar: the same "conjugated forms, no participles" rule. GROW routes to the fullscreen
# toggle; SHRINK routes to the canvas `minimize` order (desktop.shrink decides the one honest step down).
_GROW_RE = _re.compile(
    r"\b(?:pantalla\s+completa|full\s*screen|fullscreen|maximiza\w*|agranda\w*|amplia\w*|"
    r"(?:mas|más)\s+grande|bigger|larger|" + _en("maximize", "enlarge", "expand") + r")\b")
_SHRINK_RE = _re.compile(
    r"\b(?:minimiza\w*|encoge\w*|achica\w*|(?:mas|más)\s+peque\w*|smaller|"
    + _en("minimize", "shrink") + r"|reduce\w*)\b")
# «quita/sal de la pantalla completa» asks to LEAVE the mode — shrink, not the grow toggle.
# V2-677 — «get out of full screen» matched no exit verb, fell through to _GROW_RE on its own «full
# screen», and TOGGLED the card INTO full screen: the exact opposite of the order, which is the failure
# `fullscreen_target` already refuses to make on the argument side. English leaves a mode with a PARTICLE
# («get out of», «come out of», «take it off»), not with a bare verb, so the particle is what to read.
_EXIT_FS_RE = _re.compile(
    # «sácame de la pantalla completa» measured INVERTING while writing this batch's tests: `sacar` was not
    # in the list, `sal` cannot reach «sácame» across the \b, so the sentence fell through to _GROW_RE on
    # its own «pantalla completa» — the Spanish half of exactly the English bug above.
    r"\b(?:quita\w*|saca\w*|sac[aá]\w*|sal|salir|salte|cierra|deja|"
    + _en("exit", "leave", "quit", "get", "come", "take") +
    r")\b[^.]{0,25}\b(?:pantalla\s+completa|full\s*screen|fullscreen)\b"
    r"|\b(?:out\s+of|off)\s+(?:the\s+)?(?:full\s*screen|fullscreen)\b")


# A SHORT bare affirmative answers the model's own offer («¿busco de nuevo el vídeo?» → «Sí») and must
# keep licensing the load. Short only: «si» in a long sentence is a conditional, not a yes.
_AFFIRM_RE = _re.compile(r"\b(?:si|vale|venga|claro|hazlo|ok|okey|okay|yes|yeah|sure|adelante)\b")


def asks_for_media(text: str) -> bool:
    """True only when the turn carries a conjugated media REQUEST VERB. The half of `video_license` that
    does not include the bare affirmative — see `replay_license` for why the distinction has to exist."""
    return bool(_MEDIA_REQ_RE.search(_NEG_MEDIA_RE.sub(" ", _norm_txt(text))))


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
    # V2-677 — the bare affirmative is deliberately NOT enough here, and the widget the turn NAMES decides
    # the rest. Measured live 2026-09-11 (session 366787ed, English): «And show me show me the agenda. My
    # agenda.» and «Yeah. Okay.» each re-licensed the youtube load that had just run, so the video reloaded
    # itself twice over orders aimed at another card and over a backchannel. A replay REPLACES what is
    # playing, so it is the one mutation that must hear the verb: «dale al play» (the V2-650 case this
    # exists for) always does. And a turn that resolves to a DIFFERENT widget is talking about that one.
    if not asks_for_media(text):
        return False
    try:
        from widgets import runtime
        m = (runtime.identify(text) or {}).get("match")
        if m and str(m).strip().lower() != str(wid).strip().lower():
            return False
    except Exception:
        pass
    return True


# ── A show of a JUST-CLOSED widget needs the operator's words again (V2-650b) ────────────────────────────
_RECENT_CLOSES: dict = {}
_REOPEN_WINDOW_S = 120.0


def note_operator_close(wid: str) -> None:
    """Every door that executes an operator-licensed close records the widget here (the [[close]] tag
    funnel, the named-close backstop, the close-not-delete guard, the action map's fast lane): for the
    next two minutes a model-emitted show of the SAME widget needs the operator's words again. Never
    raises — a bookkeeping failure must not break a close."""
    try:
        w = str(wid or "").strip().lower()
        if w:
            _RECENT_CLOSES[w] = _time.time()
    except Exception:
        pass


def reopen_license(wid: str, text: str, open_ids=None, recent_ids=None) -> bool:
    """False only when the model shows a widget the operator JUST ordered closed and the turn's words
    ask for nothing of the kind. Measured live 2026-09-10 (sid 3d394…): «Johnny, cierra el widget de
    YouTube» closed it, and eight seconds later room chatter («Avisando de… cuidado, que aquí está
    pasando algo») made the model re-emit its previously DISCARDED show_widget — the card reopened over
    nobody's order. Same doctrine as the close/video/fullscreen licenses: what appears on the operator's
    screen needs the operator's words in the turn that fires it. A widget not recently closed is
    untouched by this gate; a recently closed one reopens on a conjugated media/show request
    (`video_license`) or when the operator's OWN words resolve to that widget through the certainty
    resolver every show already uses — never on chatter."""
    w = str(wid or "").strip().lower()
    ts = _RECENT_CLOSES.get(w)
    if not ts or (_time.time() - ts) > _REOPEN_WINDOW_S:
        return True
    if video_license(text):
        return True
    try:
        from widgets import runtime
        m = runtime.identify(text, open_ids=list(open_ids or []), recent_ids=list(recent_ids or [])) or {}
        return m.get("match") == w
    except Exception:
        # An unreadable resolver over a just-closed widget: staying closed is the cheap wrong — the
        # operator can reopen with a word; a card resurrected over chatter is the measured bug.
        return False
