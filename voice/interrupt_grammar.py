"""The HARD interruption grammar: stop / close-all, deterministic, never through the model (V2-778 F1, 2026-10-01).

Moved out of `voice/attention.py` (1,034 lines, over the 900 a new file may reach), unchanged: the morphology of
the close and stop imperatives (enclitic pronouns included), what a quantifier governs before it means «the whole
canvas», the remainder of a sentence after a stop or a close-all, and the input clamp. `attention` imports every
name back, so `attention.hard_interrupt` and its siblings are reached exactly as before.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(text: str) -> str:
    """Lowercase without accents (robust es/en STT comparison)."""
    n = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


# ── HARD interruption (T136): STOP always handled, BYPASSES the gate, DETERMINISTIC (does not depend on the LLM) ────
# ENCLITIC PRONOUN (fix 2026-08-12, REAL live failure): in Spanish, the imperative is ATTACHED to the pronoun —
# «close-it all», «stop-it all», «remove-them» — and `\bcierra\b` does NOT match «cierralo» (after 'cierra' come
# more word characters, so there is no boundary). Measured result (13:01:51): the operator said «Close it all
# and stop it all», the detector returned None, the command ENDED UP IN THE MODEL — which stalled on that turn — and nothing was closed.
# Exactly what this deterministic path exists to prevent: closing and stopping cannot depend on the LLM.
# This is not a phrase table: it is the MORPHOLOGY of the Spanish imperative (up to two pronouns: «devuélveMeLO»), so it
# covers any verb in the list and any that are added.
_ENCLITIC = r"(?:(?:me|te|se|nos|os|lo|la|le|los|las|les){1,2})?"


# Close EVERYTHING: closing verb + "everything/widgets" word. Short, language-agnostic (es/en).
_CLOSE_VERB_RE = re.compile(
    r"\b(?:cierra|cierre|cierr|quita|elimina|esconde|oculta|limpia|despeja)" + _ENCLITIC + r"\b"
    r"|\b(?:close|hide|clear)\b")


# The CARDS themselves — these nouns name the canvas, so a close verb next to one is a close-ALL on its own.
_ALL_RE = re.compile(
    r"\b(widgets|tarjetas|ventanas|pantalla|escritorio|everything)\b")


# V2-664 — A BARE QUANTIFIER IS NOT THE CANVAS UNTIL IT SAYS SO. «todo/todos/todas/all» used to count
# anywhere in the turn, so a close verb in one clause and a quantifier fifteen words later in ANOTHER wiped
# the desktop. Measured live 2026-09-11 (session eedf7f9b): «Vale, quita, por favor, los datos de comidas de
# la agenda… todas esas entradas de la…» — an order to delete ROWS INSIDE the agenda — matched «quita» +
# «todas» and closed every card he had open, twice (the glued fragments re-fired it).
# What decides is structural and needs no lexicon of intentions: look at what the quantifier GOVERNS. It is
# the canvas when it governs nothing («cierra todo», «ciérralo todo ya») or governs a card noun («todos los
# widgets»); it is a thing inside a widget when it governs any other noun («todas esas entradas»).
_QUANT_RE = re.compile(
    r"\b(?:todo|toda|todos|todas|all|everything)\b"
    r"(?:\s+(?:los|las|el|la|mis|tus|sus|esos|esas|estos|estas|the|my|your)\b)?"
    r"(?:\s+(\w+))?")


# Nouns that ARE the cards (what a quantifier may govern and still mean the whole canvas) …
_CARD_WORD_RE = re.compile(
    r"^(?:widgets?|tarjetas?|ventanas?|cards?|pantallas?|escritorios?|canvas|mural|esto|eso|abierto|abiertos)$")


# … and the particles that are not a noun at all, so the quantifier governs NOTHING through them.
_PARTICLE_RE = re.compile(
    r"^(?:ya|ahora|porfa|por|favor|please|now|de|una|vez|y|pero|vale|ok|anda|venga|gracias)$")


def _quantifies_the_canvas(n: str) -> bool:
    """True when some bare quantifier in `n` means THE CARDS — see `_QUANT_RE` above."""
    for m in _QUANT_RE.finditer(n):
        w = m.group(1) or ""
        if not w or _PARTICLE_RE.match(w) or _CARD_WORD_RE.match(w):
            return True
    return False


# REAL BUG 2026-07-23 (new fullscreen feature): "exit fullscreen" (exit fullscreen for ONE
# widget) matched "close/remove the SCREEN" (closing verb + 'pantalla' from _ALL_RE) and triggered closing
# ALL widgets — "fullscreen"/"full screen" is a mode of ONE widget, not a synonym for "everything".
# «completamente» is how the STT renders «pantalla completa» often enough to matter (measured live 2026-09-05,
# session 3050e623: «Cierra la pantalla completamente.» → the guard missed, close-ALL fired, and re-fired on
# every glued fragment of the chain — the operator's own next words were «te he dicho que cerraras la pantalla
# completa, no que cerraras el widget»). A false veto here just hands the turn to the model, which can still
# close; a miss destroys the whole canvas instantly, so the guard errs wide.
_FULLSCREEN_RE = re.compile(r"\bpantalla\s+completa(?:mente)?\b|\bfull\s*screen\b|\bfullscreen\b", re.I)


def mentions_fullscreen(text: str) -> bool:
    """True when the turn talks about «pantalla completa»/fullscreen — a SCREEN-STATE subject, not a close
    order. Consumed by the generic close BACKSTOPS (voice provider + probe mirror): a turn that mentions
    fullscreen next to a close verb is asking to leave that mode (or narrating it), and the backstop closing
    the whole widget there is the measured failure of 2026-09-05 — it closed `youtube` twice more while the
    operator was DESCRIBING the first close. One copy of the decision, read by both channels (V2-252)."""
    return bool(_FULLSCREEN_RE.search(_norm(text)))


# Unambiguous STOP (triggers even if the turn is long).
_STOP_HARD_RE = re.compile(
    r"\b(silencio|calla(?:te|os|d)?|basta|stop|shh+|quiet[oa]|detente|para\s+ya|para\s+de|parate|shut\s*up)\b"
    # An attached pronoun is NOT the preposition «para», so it is unambiguous AS A VERB — but that is not the
    # same as being unambiguous ABOUT WHAT. V2-393: only the REFLEXIVE/DATIVE («stop yourself», «stop», «stop me») refers
    # to zaelar; the 3rd-person ACCUSATIVE («stop it», «stop her») has a DIRECT OBJECT, meaning it refers to a THING — and a
    # barge-in has no object: it means silence. Measured in `watch-a-video-not-listen-to-it` (2026-08-27 14:04), which
# had passed 5/5 two hours earlier: «Stop it now, please» about a loaded video consumed the ENTIRE turn
# — the hard stop generates no response — and the backstop «Can you repeat that?» appeared. The tester repeated it with other
# words («Stop the video») and it worked on the first try: the command was clear, the guard was ours.
    r"|\b(?:para|pare|deten|detenga)(?:me|te|se|nos|os|le|les){1,2}\b"
    # …unless the object is EVERYTHING: «stop it all» is global, and there the object is not a specific thing.
    r"|\b(?:para|pare|deten|detenga)(?:lo|la|los|las)\s+(?:todo|toda|todos|todas)\b")


# Ambiguous STOP ("para"/"pare"/"espera" — also a preposition): only as a SHORT imperative (avoids "para la cena").
_STOP_SOFT_RE = re.compile(r"\b(para|pare|espera)\b")


# V2-584: a stop verb followed by DETERMINER + NOUN names a THING — «para el vídeo», «stop the video»,
# «para la música». That is an order ABOUT something, not a silence order, and swallowing it here is how a
# pause order stopped the SPEECH and left the video playing (measured live 2026-09-05, twice, with the
# operator's explicit complaint in the transcript). Structural, never a phrase table: the determiner is what
# separates «para el vídeo» (object) from «para ya» / «para por favor» (no object → still a barge-in stop).
# The pronoun forms («para eso», «páralo») deliberately stay OUT: a bare pronoun after a stop verb is how
# people silence an ongoing speech, and V2-038's worker-stop precedence already handles «para eso» over live
# workers one level up.
_STOP_OBJECT_RE = re.compile(
    r"\b(?:para|pare|espera|stop)\s+"
    r"(?:el|la|los|las|un|una|este|esta|ese|esa|mi|tu|su|the|this|that|my|your)\s+\w+")


# V2-678 — the close-ALL door is the most destructive thing the operator can trigger by accident: it
# bypasses the attention gate, executes immediately, and there is no undo. It was also the ONLY close door
# with no grammar behind it — `close_guards` has vetoed negations and narrated closes since V2-631, and this
# one asked two bare questions of the WHOLE turn: «is there a close verb anywhere?» and «is there a canvas
# quantifier anywhere?».
#
# Measured live 2026-09-12 (session 352268b5), twice in six seconds:
#   10:59:45  «Close also the agenda. And reposition all the widgets.» → every card gone. The close verb
#             was in the FIRST clause and the quantifier in the SECOND, where the verb is «reposition».
#   10:59:51  «I said reposition widgets. Do not close the widgets.» → every card gone AGAIN, on the
#             sentence that says not to.
#
# V2-664 taught the quantifier WHAT it governs; this teaches it which VERB governs it. Both directions of
# failure are not equal — a false veto hands the turn to the model, which can still close everything; a
# false positive destroys the desktop — so it errs toward NOT firing.
_AND_SPLIT_RE = re.compile(r"[.;!?\n]|\sy\s|\sand\s|\spero\s|\sbut\s", re.I)


def _closes_the_whole_canvas(n: str) -> bool:
    """True when SOME CLAUSE of the turn orders the whole canvas closed — verb and quantifier together."""
    if _FULLSCREEN_RE.search(n):
        return False                       # a screen-state subject is never a close-all (V2-600)
    for clause in _AND_SPLIT_RE.split(n):
        c = (clause or "").strip()
        if not c or not _CLOSE_VERB_RE.search(c):
            continue
        if not (_ALL_RE.search(c) or _quantifies_the_canvas(c)):
            continue
        try:
            from nucleo.flash.close_guards import is_negated_or_narrated
            if is_negated_or_narrated(c):
                continue                   # «do not close the widgets», or narrating one already done
        except Exception:  # noqa: BLE001
            pass                           # unreadable guard: the clause already carries verb + quantifier
        return True
    return False


def hard_interrupt(text: str) -> str | None:
    """Detects a hard STOP that is ALWAYS executed immediately (bypasses the attention gate):
      - 'close'  → close ALL widgets ("close the widgets / close everything").
      - 'stop'   → silence/stop (LiveKit's barge-in already cut the TTS; no new response is generated).
    Returns the type or None. The 'close' case was the real bug: it was buried in a huge turn and truncated.
    A stop verb that NAMES a thing («para el vídeo») is not a hard interrupt: the turn must run so the model
    (or the action map) can act on that thing — the barge-in upstream already silenced the voice either way."""
    n = _norm(text)
    if _closes_the_whole_canvas(n):
        return "close"
    has_object = bool(_STOP_OBJECT_RE.search(n))
    if _STOP_HARD_RE.search(n) and not has_object:
        return "stop"
    if _STOP_SOFT_RE.search(n) and not has_object and len(n.split()) <= 4:
        return "stop"
    return None


#: Clause splitter for the REMAINDER, and the one difference from `_AND_SPLIT_RE` is the comma. That one is
#: deliberately comma-blind: `_closes_the_whole_canvas` wants a whole enumeration («cierra el vídeo, la música
#: y todo lo demás») to read as ONE closing clause. Here the question is the opposite one — where does the
#: closing order END and the next order begin — and in speech that boundary is almost always a comma.
_REST_SPLIT_RE = re.compile(r"[,;.!?\n]|\sy\s|\sand\s|\spero\s|\sbut\s", re.I)


#: A clause that is only politeness or timing carries no request. Without this, «cierra todo, por favor» would
#: come back with «por favor» as its remainder and spend a whole model turn on it.
_COURTESY_CLAUSE_RE = re.compile(
    r"^(?:por\s+favor|porfa|please|gracias|thanks|thank\s+you|venga|vale|ok|okay|ya|ahora(?:\s+mismo)?|"
    r"right\s+now|now|anda|hombre|tio|tia|hey)$", re.I)


def close_all_remainder(text: str) -> str:
    """What the operator asked for BESIDES closing the canvas, or "" when closing was the whole request.

    `hard_interrupt()` answers «close» and the caller executes it DETERMINISTICALLY and returns — the
    guarantee that a close order can never be buried in a long turn (T136), paid for by a real incident
    where it fell outside a 14k-char excerpt. What that early return also did, and nobody had measured,
    is throw away every other clause of the same sentence.

    Measured live 2026-09-14, flow `T10·c053`: «close all, open agenda, connect to my google calendar».
    The entire event chain is `✋ interrupción dura atendida · widget close · flow end`. No tool, no model
    call, no reply — two thirds of a compound order discarded in silence, and the operator was told
    nothing. The canvas cleared, which looks enough like obedience to hide the other two.

    The close keeps its guarantee; the rest of the sentence keeps its turn. **The closing clause is
    REMOVED rather than left in**, because a model that reads «close all» against an already-empty canvas
    re-emits it (the context-bleed shape V2-635 catalogued), and that second close would land on whatever
    the very same sentence had just asked to open.

    Conservative by construction: anything it cannot confidently read as a second order comes back "",
    and the caller then behaves exactly as it did before — a remainder that is only courtesy, or a single
    bare word, buys a model turn that answers nothing.
    """
    if not _closes_the_whole_canvas(_norm(text)):
        return ""                              # not a canvas close at all: nothing for this to split
    kept: list[str] = []
    for clause in _REST_SPLIT_RE.split(text or ""):
        c = (clause or "").strip(" \t,;.")
        if not c:
            continue
        n = _norm(c)
        if _closes_the_whole_canvas(n) or _COURTESY_CLAUSE_RE.match(n.strip()):
            continue
        kept.append(c)
    rest = ", ".join(kept).strip(" ,;.")
    return rest if len(rest.split()) >= 2 else ""


#: A clause that is only a negation interjection carries no request. Without this, «No. So no. Stop it.
#: Okay. Show me the WhatsApp messages» would come back with «No, So no» glued to the order — and a model
#: reading «No … show me» hears the cancellation, not the order. Anchored like `_COURTESY_CLAUSE_RE`: a
#: clause that SAYS something («no abras eso») is never this.
_NEGATION_CLAUSE_RE = re.compile(r"^(?:no|nah|nope|non|nein|so\s+no|oh\s+no|no\s+no)$", re.I)


def stop_remainder(text: str) -> str:
    """What the operator asked for BESIDES silence, or "" when stopping was the whole request.

    The stop twin of `close_all_remainder` (V2-688 fixed the close branch; the stop branch kept the same
    hole). Measured live in session 6d19df41: «No. So no. Stop it. Okay. Show me the WhatsApp messages.»
    ended the turn on the stop — the WhatsApp order died in silence, the operator repeated it, and the
    model blamed the Carwow email instead: the dropped order left no trace, so the stale context was all
    it had.

    The stop keeps its guarantee (the barge-in already cut the voice; a bare stop still ends the turn);
    the rest of the sentence keeps its turn. Conservative like its twin: an unparseable remainder comes
    back "", and the caller behaves exactly as before.
    """
    if hard_interrupt(text) != "stop":
        return ""                              # not a bare stop at all: nothing for this to split
    kept: list[str] = []
    for clause in _REST_SPLIT_RE.split(text or ""):
        c = (clause or "").strip(" \t,;.")
        if not c:
            continue
        n = _norm(c)
        if (hard_interrupt(c) == "stop" or _COURTESY_CLAUSE_RE.match(n.strip())
                or _NEGATION_CLAUSE_RE.match(n.strip())):
            continue
        kept.append(c)
    rest = ", ".join(kept).strip(" ,;.")
    return rest if len(rest.split()) >= 2 else ""


# ── bounded turn end + command preservation (T135) ───────────────────────────────────────────────
# Explicit command clause (open/close/show/stop…), so a length-based truncation NEVER loses it.
_COMMAND_RE = re.compile(
    r"[^.!?\n]*\b(cierra|cierre|abre|abra|muestra|muestrame|ensena|ensename|pon|saca|sube|para|pare|stop|"
    r"silencio|calla|basta|close|open|show|hide|clear|quita|oculta|esconde|limpia|despeja)\b[^.!?\n]*")


def clamp_input(text: str, max_len: int) -> tuple[str, bool]:
    """Bounds the turn text to `max_len` chars while PRESERVING the explicit command (close/stop/show…): if the
    turn is long and contains a command, its clause is preserved (rather than blindly truncating the last N chars, which
    caused "close the widgets" to end up OUTSIDE the excerpt). Returns (text, truncated?)."""
    if max_len <= 0 or len(text) <= max_len:
        return text, False
    tail = text[-max_len:]
    cmds = [m.group(0).strip() for m in _COMMAND_RE.finditer(text)]
    cmd = cmds[-1] if cmds else ""      # the last command = the most recent thing the operator requested
    if cmd and cmd not in tail:
        keep = cmd[: max(0, max_len // 2)]
        room = max_len - len(keep) - 3   # " … "
        tail = keep + " … " + (tail[-room:] if room > 0 else "")
    return tail, True
