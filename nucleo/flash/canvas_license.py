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


def _his_words(text: str) -> str:
    """The operator's own words — never the composed turn with our `[SISTEMA]` notes glued to it (V2-678).

    Applied at the ENTRY of every license in this module rather than at each call site, because that is the
    third door of this class in two days (V2-677's escalation guard, V2-666's errand, this) and each one
    broke the same way: the decider receives a variable called `text` and has no way to know what is inside
    it. Measured live 2026-09-12 (session 352268b5, 10:58:57): the widget action logged the words that
    licensed it as «Now show me\n\n[SISTEMA] Avisos pendientes — SOLO cuando hayas atendido y contestado…»,
    so the grammar that decides what may touch his screen was reading our own Spanish prose.

    Fail-open: an unreadable note boundary returns the text untouched, which is exactly today's behaviour.
    """
    try:
        from voice import brain_notes
        return brain_notes.operator_half(text)
    except Exception:  # noqa: BLE001
        return text or ""


def asks_for_media(text: str) -> bool:
    """True only when the turn carries a conjugated media REQUEST VERB. The half of `video_license` that
    does not include the bare affirmative — see `replay_license` for why the distinction has to exist."""
    return bool(_MEDIA_REQ_RE.search(_NEG_MEDIA_RE.sub(" ", _norm_txt(_his_words(text)))))


def answered_an_offer(last_reply: str) -> bool:
    """Did OUR previous turn actually put a question to him? (V2-723)

    The bare-affirmative escape below exists to answer the model's own offer — «¿busco de nuevo el vídeo?»
    → «Sí» — and until now nothing checked that an offer had been made. Measured 2026-09-17 in a live
    session: «Okay. What if» (three words, one «okay», the operator starting an unrelated sentence) was
    licensed as a media request, and the music he had PAUSED BY HAND resumed. That is the second
    interpretation engine the audit warned about — a keyword gate quietly disagreeing with the model — and
    the cheapest way to stop it is not more words in the table but the fact that gives the table its
    meaning: a «yes» is an answer only where there was a question."""
    r = str(last_reply or "")
    return "?" in r or "¿" in r


def _producing_vocabulary() -> tuple[str, ...]:
    """The words the widgets that DECLARE production call themselves — their own aliases and keywords, no
    table of ours. Cached by nobody on purpose: `runtime` already caches the catalog, and a fork that adds
    a player brings its vocabulary with it."""
    out: list[str] = []
    try:
        from widgets import producers, runtime
        for w in runtime.catalog():
            wid = str(w.get("id") or "")
            if not wid or not producers.spec(wid):
                continue
            man = runtime.get(wid) or {}
            for v in list(man.get("aliases") or []) + list(man.get("keywords") or []):
                v = _norm_txt(str(v))
                if len(v) >= 4:
                    out.append(v)
    except Exception:  # noqa: BLE001
        return ()
    return tuple(out)


def bare_affirmative(text: str) -> bool:
    """A SHORT yes and nothing else — the shape that can only mean «do the thing you just proposed»."""
    n = _NEG_MEDIA_RE.sub(" ", _norm_txt(_his_words(text)))
    return len(n.split()) <= 4 and bool(_AFFIRM_RE.search(n))


def offer_about(wid: str, last_reply: str) -> bool:
    """Was OUR still-pending question a proposal about THIS widget? (V2-724)

    The sibling of `offer_of_media` for the other effect a “yes” can authorize: putting a card back. Same
    correction behind both — an affirmative answers ONE proposal, so the proposal has to be the one whose
    effect is about to be spent — and the same declared source, the certainty resolver every show uses."""
    w = str(wid or "").split("::", 1)[0].strip().lower()
    if not w or not answered_an_offer(last_reply):
        return False
    try:
        from widgets import runtime
        return str((runtime.identify(str(last_reply)) or {}).get("match") or "").split("::", 1)[0] == w
    except Exception:  # noqa: BLE001
        return False


def offer_of_media(last_reply: str) -> bool:
    """Was OUR still-pending question a proposal to PLAY something? (V2-724)

    The audit's adjacent correction, and it is right: «we previously asked something» is necessary and not
    sufficient. With only that, a «sí» to «¿te apunto la cita del dentista?» still licensed a video load —
    an answer to one proposal spending the authority of another. So the affirmative is bound to the
    proposal's own effect class, and the class is read from DECLARED data twice over: the certainty
    resolver every show already uses, and failing that the vocabulary the producing widgets publish about
    themselves. Both halves are the widgets' own words; neither is a verb table of ours.

    Its known limit, written down rather than patched with more words: an offer that names no medium at all
    («want me to play something else?») is not recognised, so a bare «sure» to it licenses nothing and he
    has to say it with a noun. That is the safe direction — the failure of this predicate costs a repeat,
    and its false positive costs music nobody asked for."""
    r = str(last_reply or "")
    if not answered_an_offer(r):
        return False
    try:
        from widgets import producers, runtime
        wid = str((runtime.identify(r) or {}).get("match") or "").split("::", 1)[0]
        if wid and producers.spec(wid):
            return True
    except Exception:  # noqa: BLE001
        pass
    folded = _norm_txt(r)
    return any(v in folded for v in _producing_vocabulary())


def video_license(text: str, last_reply: str = "") -> bool:
    """True when the turn ASKS for media — the words that may carry a `play_video` (a load that replaces
    whatever is playing). Chatter, praise, insults and complaints about a past change license nothing.

    A bare affirmative licenses media only as the answer to a still-pending proposal that was ITSELF about
    playing something (`offer_of_media`); with no reply to read, it licenses nothing, which is the safe
    direction: he can always say it with a verb."""
    n = _NEG_MEDIA_RE.sub(" ", _norm_txt(_his_words(text)))
    if _MEDIA_REQ_RE.search(n):
        return True
    return len(n.split()) <= 4 and bool(_AFFIRM_RE.search(n)) and offer_of_media(last_reply)


def close_license(text: str) -> bool:
    """True when the turn ORDERS a close — `close_guards.looks_like_close` verbatim (negations and
    narrated closes already excluded there). A model-emitted [[close]] without it is drag, not obedience."""
    return looks_like_close(_his_words(text))


def fullscreen_license(text: str) -> str:
    """'' (no screen-size words at all: a fullscreen_widget call is drag — the measured «pausa el vídeo» →
    fullscreen), 'minimize' (the turn asks to go smaller / leave full screen), or 'fullscreen' (the turn
    asks for full screen / bigger — the toggle)."""
    n = _norm_txt(_his_words(text))
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
        seen = runtime.identify(_his_words(text)) or {}
        m = seen.get("match")
        if m and str(m).strip().lower() != str(wid).strip().lower():
            return False
        # V2-678 — AMBIGUOUS counts as «not clearly this one». Measured live 2026-09-12 (session 352268b5,
        # 10:59:15): «I said, show me the music widget, not the video widget.» names BOTH cards, so
        # `identify` correctly returns no winner — and a replay re-loaded the video for the third time, on
        # the very sentence complaining about it. A replay REPLACES what is playing, so ambiguity is the
        # one thing that must not authorise it; his next word can still start it.
        if seen.get("ambiguous") and any(
                str(c.get("id", "")).lower() != str(wid).strip().lower()
                for c in (seen.get("candidates") or [])):
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


def reopen_license(wid: str, text: str, open_ids=None, recent_ids=None, last_reply: str = "") -> bool:
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
    if video_license(text, last_reply):
        return True
    # …and an affirmative answering a proposal about THIS card reopens it: that proposal's own effect is
    # the presentation, which media's grammar has no reason to recognise (V2-724).
    if bare_affirmative(text) and offer_about(w, last_reply):
        return True
    try:
        from widgets import runtime
        m = runtime.identify(text, open_ids=list(open_ids or []), recent_ids=list(recent_ids or [])) or {}
        return m.get("match") == w
    except Exception:
        # An unreadable resolver over a just-closed widget: staying closed is the cheap wrong — the
        # operator can reopen with a word; a card resurrected over chatter is the measured bug.
        return False
