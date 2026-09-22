#
# CLOSE-order grammar (V2-045/V2-567/V2-600/V2-631) — extracted from `router_guards.py` on 2026-09-09 paying
# the architecture ratchet (V2-555's rule: a red ratchet is paid by extracting a module, never by raising a
# ceiling). A CLOSED set: nothing that stays in router_guards defines anything these need, and they only need
# the shared normalizer. Callers keep importing through `router_guards`/`router` — re-exported there.
#
from __future__ import annotations

import re as _re

from .text_norm import _norm_txt

_CLOSE_VERB_RE = _re.compile(r"\b(cierr\w*|cerr\w*|ocult\w*|escond\w*|apag\w*|quit\w*|close|hide|turn\s+off)\b")
_DELETE_VERB_RE = _re.compile(r"\b(borr|elimin|delete|remove|deshaz)\w*")
# Negated close: "no cierres / no lo cierres / don't close" — must not count as close (prevents doing the
# opposite).
#
# V2-678 — the English half was the contraction ALONE, so «Do not close the widgets.» read as a close ORDER,
# and through `hard_interrupt` (which has no negation check of its own) it wiped the canvas. Measured live
# 2026-09-12 (session 352268b5, 10:59:51): «I said reposition widgets. Do not close the widgets.» →
# `✋ interrupción dura atendida` → every card gone, on the sentence that said not to. Reproduced standalone.
# Same asymmetry V2-677 found in the request verbs, now in the guard that exists to prevent damage: a miss
# here is not a missed order, it is a destroyed desktop.
_NO_CLOSE_RE = _re.compile(
    r"\bno\s+(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:cierr\w*|ocult\w*|escond\w*|apagu\w*|quit\w*)\b"
    r"|\b(?:do\s+not|don'?t|never|please\s+do\s*n'?o?t)\s+(?:\w+\s){0,2}?"
    r"(?:close|hide|shut|remove|clear)\b")
# A close VERB FORM that cannot be an order (V2-631). Measured live 2026-09-09 (session 7be94951): the close
# backstop closed the music card TWICE — killing the audio, which lives inside that card — on turns that only
# MENTIONED closing: «¿Van a cerrar anuncios?» (a question about ads; «van a cerrar» has somebody else as its
# subject) and «No sigue sonando porque has cerrado el widget de música.» (a complaint narrating a close that
# already happened — and the guard's True also made show_contradicts_the_order discard the show_widget the
# model had CORRECTLY called to reopen it). Grammar, not intent (V2-095): a participle after «haber» / «you've»
# narrates the past, and «va(n) a <infinitive>» is third-person — neither can be an order addressed to zaelar.
# These spans are STRIPPED before testing, not used to veto: «has cerrado el widget; ciérralo otra vez» keeps
# its close because the imperative survives the strip.
_NARRATED_CLOSE_RE = _re.compile(
    r"\b(?:has|ha|han|habias?|habian|habeis|hemos)\s+(?:\w+\s)?(?:cerrado|ocultado|escondido|apagado|quitado)\b"
    r"|\b(?:va|van)\s+a\s+(?:cerrar|ocultar|apagar|quitar)\w*\b"
    r"|\byou(?:'?ve| have)\s+(?:closed|hidden)\b|\bthey(?:'?re| are|'?ll| will)\s+(?:going\s+to\s+)?close\b")


def is_negated_or_narrated(text: str) -> bool:
    """True when this text NEGATES a close («do not close the widgets») or NARRATES one already done.

    Exported for callers with their OWN close vocabulary — `voice/attention.py`'s close-ALL door knows
    verbs this module does not («limpia el escritorio»), so it needs the veto WITHOUT the positive half.
    Using `looks_like_close` there would have silently dropped every verb the two lists do not share, which
    is how a guard becomes a regression (found by its own test, V2-678).
    """
    n = _norm_txt(text)
    return bool(_NO_CLOSE_RE.search(n) or _NARRATED_CLOSE_RE.search(n))


def looks_like_close(text: str) -> bool:
    """True if the turn asks to CLOSE (hide) a widget, NOT delete it. EXECUTION GUARD for delete_widget (V2-045,
    V2-017 invariant 'cerrar ≠ borrar'): the non-reasoning model sometimes chooses delete_widget for 'cierra el
    widget de X'; deletion is FOREVER and closing is reversible → with a close verb and NO delete verb, it is a
    close. Deterministic and accent-free (the input is normalized). Ignores NEGATION ('no cierres') and NARRATED
    closes ('has cerrado el widget', '¿van a cerrar anuncios?') — see _NARRATED_CLOSE_RE."""
    n = _norm_txt(text)
    if _DELETE_VERB_RE.search(n) or _NO_CLOSE_RE.search(n):
        return False
    n = _NARRATED_CLOSE_RE.sub(" ", n)
    return bool(_CLOSE_VERB_RE.search(n))


# A CLOSE order answered with an OPEN is not obedience (V2-567). Measured live 2026-09-03 19:02:35:
# «Cierra los contactos» → the model called `show_widget(mensajeria)`; contactos only closed because the close
# backstop rescued it, so ONE order produced TWO mutations — a spurious open landing beside the ordered close.
# The probe channel had already written the rule down («un canvas:show ESPURIO en un turno de cerrar SÍ debe
# corregirse a close») and the voice channel never applied it: the show executed anyway. This is GRAMMAR, not
# intent (V2-095): with a close verb and no un-negated open verb anywhere in the turn, a show_widget call
# contradicts the very words that produced it. A compound «cierra X y enséñame Y» keeps its show — the open
# verb licenses it — and «no abras nada, cierra los contactos» does not: a negated open licenses nothing.
_OPEN_VERB_RE = _re.compile(r"\b(abr\w*|muestr\w*|ensen\w*|desplieg\w*|saca\w*|pon\w*|vuelv\w*|open|show|display|bring\s+up)\b")
_NO_OPEN_RE = _re.compile(r"\bno\s+(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:abr\w*|muestr\w*|ensen\w*|saqu\w*|pong\w*)\b"
                          r"|\bdon'?t\s+(?:open|show|display)\b")


def show_contradicts_the_order(text: str) -> bool:
    """True when the turn is a CLOSE order that licenses no open — so a `show_widget` call must be discarded
    (the close backstop still does the closing; nothing is lost, one mutation happens instead of two)."""
    if not looks_like_close(text):
        return False
    n = _norm_txt(text)
    return not (_OPEN_VERB_RE.search(n) and not _NO_OPEN_RE.search(n))


def is_short_close_order(text: str) -> bool:
    """A SHORT order that is plainly «close this» — so a declared data-op must not answer it (V2-713 R3).

    The incident it is made of, from the voice rail where it has lived alone since 2026-07-16: «Vale,
    ciérralo» produced `widget_data(youtube, mute)` — a DECLARED action, so nothing else would stop it — and
    the video ended up muted instead of closed, with the operator correcting by hand.

    ⚠️ It was written INLINE in `voice/…/nucleo.py` and never reached `probe.py`, so the text channel — the one
    the use-case harness drives — answered «ciérralo» differently from the product. That is the R3 class: not
    a mirror that drifted, a rule that only ever existed on one side. Measured 2026-09-16: `looks_like_close`
    appears at six voice sites and three probe sites, and this length-bounded redirect at exactly one.

    It is EXTRACTED rather than copied on purpose. This repo's own ratchet says a new mirror is vetoed —
    «si dos canales necesitan la misma regla, extrae primero» — and copying the condition would have cost a
    marker while leaving two places to edit. Both channels now call this.

    The length bound is the whole rule and it is deliberate: a short sentence carrying a close verb has no
    room for anything else, while «cierra la sesión de spotify del widget» is a real data-op that happens to
    contain «cierra» and must go through untouched.
    """
    return bool(looks_like_close(text)) and len((text or "").split()) <= _SHORT_ORDER_WORDS


#: Five words, as the voice rail has used since 2026-07-16 — the pronoun plus the widget and nothing else.
_SHORT_ORDER_WORDS = 5


def is_short_order(text: str) -> bool:
    """«¿Cabe algo más en esta frase?» — the length half of the close rules, on its own (V2-713 R3).

    ⚠️ Found by the test written for the extraction above: the literal `len(text.split()) <= 5` was in THREE
    places, not one. Two of them are the close BACKSTOP (voice and probe), a different guard from the redirect
    but the same bound, unlabelled, sitting as a bare number in two channels that have to agree. A magic
    number duplicated across the two channels is the R3 class in miniature: nothing makes them move together,
    and nothing says what the 5 means.

    No close verb is checked here — that is `looks_like_close`'s job and the backstop has already asked it a
    different way. This answers only about LENGTH.
    """
    return len((text or "").split()) <= _SHORT_ORDER_WORDS


def dataop_close_licensed(text: str, widget_id: str, *, brief=None, emit=None) -> bool:
    """May the model's `widget_data(<card>, "close")` run, when the close GRAMMAR saw no close verb?

    THE INCIDENT (live session 46dcfcb4, 2026-09-22). The operator said «Uf, me he equivocado. Páralo,
    y vuelve al inicio.» The model answered with exactly the right call — `youtube:close` is declared
    as «PARA el vídeo de verdad y lo quita del reproductor», which is both halves of that order — and
    the V2-635 guard read the sentence, found no verb from `_CLOSE_VERB_RE` («parar» is not a close
    verb and never should be), called it context-bleed and ATE it. Five times in ninety seconds, while
    the engine said «lo paro y vuelvo al inicio» over a video that never stopped. The operator watched
    it and said: «veo que es incapaz de pararlo».

    The guard is not wrong to exist — a `close` data-op EMPTIES the player, and V2-635 measured the
    model dragging one into «Johnny eres tonto». What is wrong is that a VERB TABLE was left as the
    sole decider of a route, which is the rule the operator has stated three times and that
    [[feedback_una_tabla_de_verbos_no_es_un_enrutador]] carries: a grammar may PROPOSE, never decide,
    and it may never contradict a paid verdict.

    And the repair for exactly this already existed ONE BRANCH OVER: the canvas [[close]] guard in the
    voice provider has consulted `show_target.close_has_order` since V2-635 — grammar first, a
    confident Jev second. This branch, the DATA-OP close, never got the escape hatch. The same rule
    installed on one of two branches is [[feedback_una_regla_instalada_en_una_sola_de_dos_ramas]], and
    here the un-repaired branch is the one that fires on a real player.

    The second reader is the turn's OWN paid verdict — `screen_action`, enumerated from the manifests
    of what is on screen and already bought for this turn — read through `direct_action.endorses`, the
    same predicate `video_license` consults. It must name THIS card and THIS action; a verdict aimed
    at another action of the same card grants nothing, because «pausa el vídeo» must stay a pause.

    Grammar hit → True with no verdict read. A deterministic NEGATED or NARRATED close («no lo
    cierres», «has cerrado el vídeo») → False even against a confident verdict, exactly as
    `close_has_order` vetoes: a cheap model's opinion never beats the operator's own «no». Emits are
    optional so the pure decision stays testable; the caller passes the turn's `emit`.
    """
    if looks_like_close(text):
        return True
    if is_negated_or_narrated(text):
        return False
    from nucleo.flash import direct_action as _da
    licensed = _da.endorses(brief, widget_id, "close")
    if emit is not None:
        emit("brain",
             "🔓 data-op close licenciada por el veredicto de pantalla (la gramática no veía orden)"
             if licensed else
             "🛡️ data-op close ignorada — el operador no ha pedido cerrar nada (context-bleed)",
             text=(text or "")[:120], role="system",
             extra={"cat": "flash", "id": widget_id,
                    "kind_diag": "close_jev_licensed" if licensed else "close_without_order"})
    return licensed
