"""The canvas door: every card the engine shows or closes on his screen crosses `apply` (refactor2710-04 T-02).

A writer names the act, the card and its provenance (`src`, the arbiter's closed set). A show or close is judged by the
arbiter first and its verdict emitted armed (`arbiter`, with `verdict` and `source`); a veto never reaches the canvas
and `apply` says so. Other ops cross the same door unjudged, so there is one writer either way.
"""
from __future__ import annotations

import re as _re

from nucleo.acts import canvas_arbiter as _arb, canvas_turn as _turn
from voice import canvas_src

#: The ops the arbiter licenses; every other op crosses the door as it is.
JUDGED = ("show", "close")


def apply(op: str, wid: str = "", *, src: str, text: str = "", role: str = "", request: dict | None = None,
          emit=None, **extra) -> bool:
    """Put `op` on `wid` if the arbiter allows it; True when the canvas was told. `wid=""` closes every card.
    `request` is the turn the act belongs to (`canvas_turn.request_of` from a door that holds it), else the one
    the observer stream assembled (`canvas_turn.request_for`). `emit` is the caller's stream (the observer by default)."""
    op = (op or "").strip().lower()
    fields = ({"id": wid} if wid else {}) | {"src": src} | extra
    if op in JUDGED:
        req = request if request is not None else _turn.request_for(extra)
        v = _arb.decide(op, wid, src, action=str(extra.get("action") or ""), **req)
        _turn._emit_verdict(op, wid, src, str(extra.get("action") or ""), v, shadow=False, brief=req.get("verdict"))
        # an arbiter that broke fails open; a REPORT of what the screen already did is recorded, judged, never held
        if not v.allow and v.rule != "arbiter-error" and not canvas_src.is_report(src):
            return False
    if emit is None:
        from voice.observer import emit
    with _turn.judged():
        emit("widget", op, **({"text": text} if text else {}), **({"role": role} if role else {}), extra=fields)
    return True


def resolve(wid_arg: str, text: str, window, last_action, guard_target) -> tuple:
    """Which card a show means — the model's id, the guard's target or what his words name."""
    from nucleo.flash import show_target
    return show_target.resolve_show(wid_arg, text, window, last_action, guard_target)


def close_ordered(text: str, *, brief=None, called: bool = False, handle=None) -> tuple[bool, str]:
    """Does this turn ORDER a close? `(ordered, source)` — the one close licence (refactor2710-04b T-01).

    His words (never our `[SISTEMA]` notes) are read by the close grammar, and the turn's paid brief completes it:
      · a close verb orders it, unless the brief reads a NEGATION of it — a sure `canvas=neither` beside a sure
        `request_type` that is neither order nor answer («yo no te he dicho que cerraras el vídeo», CRIT-K8c);
      · a negated or narrated close («no lo cierres», «you closed it») never orders one, whatever a model says;
      · his answer to OUR «which one should I close?» carries that question's licence («Las dos.»);
      · when the model `called` a close, a sure `canvas=close` read from `handle` (the brief) forgives a grammar miss.
    `source` is grammar | verdict | answer | jev | none, so the trail says which reader moved."""
    from nucleo.flash import canvas_license as _lic, close_answer as _ca, close_guards as _cg
    his = _lic._his_words(text)
    if _cg.looks_like_close(his):
        return (False, "verdict") if brief is not None and _denies_close(brief) else (True, "grammar")
    if _cg.is_negated_or_narrated(his):
        return False, "none"
    if _ca.answers(brief):
        return True, "answer"
    if called:
        from nucleo.flash import show_target as _st
        verb, info = _st.resolve_canvas_verb(handle)
        if verb == "close" and (info or {}).get("used"):
            return True, "jev"
    return False, "none"


def _denies_close(brief) -> bool:
    """A sure `canvas=neither` alone is no negation (the verdict can miss the canvas half of an order); with a sure
    reading of the turn as something other than an order or an answer it is (V2-812 T-05)."""
    kind = _verdict(brief, "REQUEST_KEY")
    return _verdict(brief, "CANVAS_KEY") == "neither" and bool(kind) and kind not in ("order", "answer")


# A CLOSE order answered with an OPEN is not obedience (V2-567: one close order, two mutations). Grammar, not intent
# (V2-095): a close verb with no un-negated open verb in the turn licenses no show; a compound order keeps it.
_OPEN_VERB_RE = _re.compile(r"\b(abr\w*|muestr\w*|ensen\w*|desplieg\w*|saca\w*|pon\w*|vuelv\w*|open|show|display|bring\s+up)\b")
_NO_OPEN_RE = _re.compile(r"\bno\s+(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:abr\w*|muestr\w*|ensen\w*|saqu\w*|pong\w*)\b"
                          r"|\bdon'?t\s+(?:open|show|display)\b")


def show_under_close(text: str = "", *, brief=None, wid: str = "", words: bool = True) -> bool:
    """Is a show of `wid` the contradiction of this turn's close order? (refactor2710-04b T-02) The paid verdict first:
    a sure `canvas=close` with `screen_action` naming this card or nobody (V2-773: «Stop it and close the video widget»
    brought the card straight back); a close naming ANOTHER card leaves it alone. Then, where `words` (a show the model
    called), the grammar above; the lens door asks the verdict only."""
    if _closes_this(brief, wid):
        return True
    if not words:
        return False
    from nucleo.flash import close_guards as _cg
    from nucleo.flash.text_norm import _norm_txt
    if not _cg.looks_like_close(text):
        return False
    n = _norm_txt(text)
    return not (_OPEN_VERB_RE.search(n) and not _NO_OPEN_RE.search(n))


def _closes_this(brief, wid: str) -> bool:
    if _verdict(brief, "CANVAS_KEY") != "close":
        return False
    t = _verdict(brief, "TARGET_KEY").lower()
    return t.split(":", 1)[0] == str(wid or "").strip().lower() if t and t != "none" else True


def reopen_ordered(wid: str, text: str = "", *, open_ids=None, recent_ids=None, last_reply: str = "",
                   brief=None) -> bool:
    """May a show bring back `wid`? Not a card he JUST closed over chatter (V2-650b; refactor2710-04b T-03): it comes
    back on the paid verdict (`canvas=show` naming it), a media/show request, a short yes to OUR offer about that very
    card (V2-724), or his words resolving to it with certainty. A card not closed within the window is untouched."""
    from nucleo.flash import canvas_license as _lic
    w = str(wid or "").strip().lower()
    ts = _lic._RECENT_CLOSES.get(w)
    if not ts or (_lic._time.time() - ts) > _lic._REOPEN_WINDOW_S or _shows_this(brief, w):
        return True
    if _lic.video_license(text, last_reply) or (_bare_yes(text) and _offer_about(w, last_reply)):
        return True
    try:
        from widgets import runtime
        return (runtime.identify(text, open_ids=list(open_ids or []), recent_ids=list(recent_ids or [])) or {}).get("match") == w
    except Exception as e:  # noqa: BLE001 — staying closed is the cheap wrong; a card back over chatter is the bug
        return _unread("reopen_ordered: resolver unreadable", e)


def _shows_this(brief, w: str) -> bool:
    return _verdict(brief, "CANVAS_KEY") == "show" and any(
        _verdict(brief, k).split(":", 1)[0] == w for k in ("CATALOG_KEY", "TARGET_KEY"))


def _bare_yes(text: str) -> bool:
    from nucleo.flash import canvas_license as _lic
    n = _lic._NEG_MEDIA_RE.sub(" ", _lic._norm_txt(_lic._his_words(text)))
    return len(n.split()) <= 4 and bool(_lic._AFFIRM_RE.search(n))


def _offer_about(w: str, last_reply: str) -> bool:
    from nucleo.flash import canvas_license as _lic
    if not w or not _lic.answered_an_offer(last_reply):
        return False
    try:
        from widgets import runtime
        return str((runtime.identify(str(last_reply)) or {}).get("match") or "").split("::", 1)[0] == w
    except Exception as e:  # noqa: BLE001
        return _unread("reopen_ordered: offer unreadable", e)


def size_ordered(text: str, *, brief=None) -> str:
    """Which way the turn asks a card's SIZE to go: 'fullscreen' (full screen / bigger, the toggle), 'minimize'
    (smaller, put away, leave full screen) or '' — a size call over a turn that says nothing about size is drag
    (V2-635: «pausa el vídeo» → fullscreen). The paid verdict's size verbs first (refactor2710-04b T-04); the screen-size
    grammar where the verdict is silent."""
    verb = _verdict(brief, "CANVAS_KEY")
    if verb in ("fullscreen", "exit_fullscreen", "minimize"):
        return "fullscreen" if verb == "fullscreen" else "minimize"
    from nucleo.flash import canvas_license as _lic
    n = _lic._norm_txt(_lic._his_words(text))
    if _lic._EXIT_FS_RE.search(n) or _lic._SHRINK_RE.search(n):
        return "minimize"
    return "fullscreen" if _lic._GROW_RE.search(n) else ""


def _verdict(brief, key: str) -> str:
    """The brief's answer to `key` (a `turn_brief` key name) read with confidence, else ""; no brief, no (observed) read."""
    try:
        from nucleo.turn import brief as _tb
        choice, info = _tb.read(brief, getattr(_tb, key), "") if brief is not None else ("", None)
        return str(choice or "") if (info or {}).get("used") else ""
    except Exception as e:  # noqa: BLE001 — an unread brief licenses and vetoes nothing
        _unread(f"brief unread ({key})", e)
        return ""


def _unread(where: str, e: Exception) -> bool:
    """A licence that could not read its input says so and licenses nothing — the cheap wrong at this door."""
    from loguru import logger
    logger.debug(f"canvas.{where} — {e}")
    return False
