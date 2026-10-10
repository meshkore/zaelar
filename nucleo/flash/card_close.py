"""A close that names a card closes THAT card — by its name, or by where it sits on the canvas (V2-781).

Measured in `tres-tarjetas-y-el-video-por-alusion` (ES+EN, 2026-10-10), the trailer on `youtube`, the music on
`musica` and the agenda all open:

  · «Close the music actually.» — the model called nothing and said «Done.»; the canvas verdict read `close` (0.99)
    and the screen verdict `youtube:close` (0.54). The text channel ran the promise repair BEFORE the verdict's own
    canvas gesture (the voice channel runs them the other way round), the repair took the card from the screen
    verdict, and `youtube:close` emptied the player. The music kept playing and no card left the canvas.
  · «cierra la música, que ya está bien de fondo» → `play_music {action: stop}` → «Pausado.», twice, the second
    time over «ciérrala, no la pauso». The close backstop knew the order and stood down, because a music call
    had «already decided» the turn — a rule written for «apaga la música» (= stop the audio), not for «cierra».
  · «Actually close the top one too.» — no card named, a sure `close`, an unsure screen verdict; the repair
    reached `youtube` by card mass and emptied the player again.

Three answers, one per hole, and none of them a new decider:

  · `verdict_unless_named` — the screen verdict's card yields to the card his words CALL by its catalogue name
    (`widgets.naming.says_the_name`, the same reader as `direct_action.closes_the_named_card`). An alias does not
    count, so «close the video» still empties the player and leaves the card (V2-753).
  · `player_close` — a stop/pause of a player whose card his words name, under a verb that only ever means the
    card («cierra», «close», «shut» — never «apaga»/«turn off», which stop the audio and keep their old meaning),
    is that card's close. The model's call proposed; the operator's sentence names the card and the gesture.
  · `by_position` — «the top one», «la de la derecha»: the card at that place in the layout the desktop reports
    (`canvas_layout`, the same snapshot `GET /api/canvas/layout` restores). Without the geometry of every open
    card it cannot be said, and the operator is ASKED which (`consent.ASK_WHICH`'s sentence) — a guessed close is
    the one gesture he has to undo by hand.

`complete_canvas_mirror` is the text channel's run of the verdict's canvas gesture (moved out of
`probe_mirrors.mirror_the_voice_backstops`), now also called BEFORE the promise repair, as the voice runs it.
"""
from __future__ import annotations

from loguru import logger

import re

from nucleo.flash.text_norm import _norm_txt

#: Verbs that only ever mean «take the card off the screen». «apaga / turn off / quita» are NOT here on purpose:
#: «apaga la música» stops the audio and keeps the card (the close backstop's documented broad-verb rule).
_CARD_CLOSE_VERB_RE = re.compile(r"\b(?:cierr\w*|cerr\w*|close[sd]?|closing|shut)\b")
#: Player controls a «close» order can arrive dressed as.
_STOPS = frozenset({"stop", "pause"})

#: Where on the canvas a card is, in his words. A spatial place only: «the first one» is a ROW (`close_guards`).
_POSITION_RE = (
    ("top", re.compile(r"\b(?:the\s+)?(?:top|upper|uppermost|topmost)(?:\s+(?:one|card|widget|window))\b"
                       r"|\bthe\s+one\s+(?:on|at)\s+(?:the\s+)?top\b|\b(?:el|la|lo)\s+de\s+arriba\b"
                       r"|\b(?:tarjeta|ventana|widget)\s+(?:de\s+arriba|superior)\b")),
    ("bottom", re.compile(r"\b(?:the\s+)?(?:bottom|lower|lowest|bottommost)(?:\s+(?:one|card|widget|window))\b"
                          r"|\bthe\s+one\s+(?:on|at)\s+(?:the\s+)?bottom\b|\b(?:el|la|lo)\s+de\s+abajo\b"
                          r"|\b(?:tarjeta|ventana|widget)\s+(?:de\s+abajo|inferior)\b")),
    ("left", re.compile(r"\b(?:the\s+)?(?:leftmost|left-hand)(?:\s+(?:one|card|widget|window))?\b"
                        r"|\bthe\s+one\s+on\s+the\s+left\b|\bthe\s+left\s+(?:one|card|widget|window)\b"
                        r"|\b(?:el|la|lo)\s+de\s+la\s+izquierda\b")),
    ("right", re.compile(r"\b(?:the\s+)?(?:rightmost|right-hand)(?:\s+(?:one|card|widget|window))?\b"
                         r"|\bthe\s+one\s+on\s+the\s+right\b|\bthe\s+right\s+(?:card|widget|window)\b"
                         r"|\b(?:el|la|lo)\s+de\s+la\s+derecha\b")),
)
#: Two cards closer than this (px) on the asked axis are side by side for «the top one»: the place is a tie.
_TIE_PX = 24.0


def _open_now() -> list[str]:
    try:
        from server.voice_api import open_instances
        return [str(i) for i in open_instances() if str(i)]
    except Exception:  # noqa: BLE001
        return []


def _base(wid: str) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def _says(text: str, wid: str) -> bool:
    try:
        from widgets import naming as _naming
        return _naming.says_the_name(text, _base(wid))
    except Exception:  # noqa: BLE001
        return False


def named_open(operator_text: str, open_ids=None) -> list[str]:
    """The open cards his words call by their catalogue NAME (never by an alias or by context)."""
    ids = _open_now() if open_ids is None else [str(i) for i in open_ids or []]
    return [w for w in ids if _says(operator_text, w)]


def verdict_unless_named(verdict_wid: str, operator_text: str, open_ids=None) -> str:
    """The screen verdict's card, or "" when his words name a DIFFERENT open card and not the verdict's own —
    «Close the music» over `youtube:close` (0.54) is the music's close. "" hands the choice to the named cards."""
    if not verdict_wid or _says(operator_text, verdict_wid):
        return verdict_wid
    others = [w for w in named_open(operator_text, open_ids) if _base(w) != _base(verdict_wid)]
    return "" if others else verdict_wid


def player_close(tool: str, action: str, operator_text: str, open_ids=None) -> str:
    """The player card to CLOSE when the model answered «close the music» with that player's stop/pause, or "".

    All of: a stop/pause (a play or a volume is never a close), a card-only close verb that is not negated or
    narrated (`close_guards.looks_like_close`), his words naming THIS player's card and no other open card, and the
    card open. «pausa la música y cierra la agenda» names two cards and keeps its pause."""
    from nucleo.flash import close_guards as _cg, player_control as _pc
    card = _pc.CARD_OF_TOOL.get(str(tool or "").strip(), "")
    if not card or str(action or "").strip().lower() not in _STOPS:
        return ""
    if not (_CARD_CLOSE_VERB_RE.search(_norm_txt(operator_text)) and _cg.looks_like_close(operator_text)):
        return ""
    ids = _open_now() if open_ids is None else [str(i) for i in open_ids or []]
    named = named_open(operator_text, ids)
    if not named or any(_base(w) != card for w in named):
        return ""
    return next((w for w in ids if _base(w) == card), "")


def place_named(operator_text: str) -> str:
    """"top" | "bottom" | "left" | "right" when his words point at a PLACE on the canvas, else ""."""
    n = _norm_txt(operator_text)
    return next((place for place, rx in _POSITION_RE if rx.search(n)), "")


def _px(v) -> float | None:
    try:
        return float(str(v).strip().lower().removesuffix("px"))
    except (TypeError, ValueError):
        return None


def _geometry(open_ids: list[str]) -> dict[str, tuple[float, float]]:
    """`{card: (left, top)}` for the open cards the desktop's last layout report placed. Never raises."""
    try:
        from memory import api as _memapi
        snap = _memapi.kv_get("canvas_layout") or {}
        items = snap.get("items") if isinstance(snap, dict) else None
    except Exception:  # noqa: BLE001
        items = None
    out: dict[str, tuple[float, float]] = {}
    for it in items or []:
        if not isinstance(it, dict) or str(it.get("min") or "").lower() in ("1", "true"):
            continue                        # a minimized card is not on the screen to sit anywhere
        cid = str(it.get("id") or "")
        left, top = _px(it.get("left")), _px(it.get("top"))
        if cid in open_ids and left is not None and top is not None:
            out[cid] = (left, top)
    return out


def by_position(operator_text: str, open_ids=None) -> dict:
    """`{"place", "card", "cands"}` for a sentence that points at a place on the canvas; `{}` when it points at none.

    `card` is the one card at that place; when it cannot be said — a card without geometry, or two side by side —
    `card` is "" and `cands` lists the cards to ask between."""
    place = place_named(operator_text)
    if not place:
        return {}
    ids = _open_now() if open_ids is None else [str(i) for i in open_ids or []]
    geo = _geometry(ids)
    if len(ids) == 1:
        return {"place": place, "card": ids[0], "cands": ids}
    if not ids or len(geo) < len(ids):
        return {"place": place, "card": "", "cands": ids}
    axis, sign = {"top": (1, 1), "bottom": (1, -1), "left": (0, 1), "right": (0, -1)}[place]
    ranked = sorted(ids, key=lambda w: sign * geo[w][axis])
    best = sign * geo[ranked[0]][axis]
    tied = [w for w in ranked if abs(sign * geo[w][axis] - best) <= _TIE_PX]
    return {"place": place, "card": tied[0] if len(tied) == 1 else "", "cands": tied if len(tied) > 1 else ids}


def position_or_focus(operator_text: str, focus: str) -> str:
    """The card a place in his words points at, else `focus` (the caller's own fallback)."""
    return by_position(operator_text).get("card") or focus


def ask_which(cands) -> str:
    """`consent.ASK_WHICH`'s sentence over these cards' live labels — the one question, the one phrase."""
    try:
        from i18n import langs as _langs
        from nucleo.flash import turn_brief as _tb
        names = [_tb._card_label(c) for c in cands or []]
        return _langs.current_language().ask_which_item.format(cands=", ".join(names[:3]))
    except Exception:  # noqa: BLE001
        return ""


def complete_canvas_mirror(brief, operator_text: str, *, blocked: bool) -> dict:
    """The text channel's run of the verdict's sure canvas gesture when the model called nothing — the mirror of the
    voice `direct_action.complete_canvas`. `{}` when nothing ran; else the turn's new `action`, `spoken` and
    `_already`. A close over a place nobody can locate asks instead (`action: clarify`). Never raises."""
    if blocked:
        return {}
    try:
        from voice.observer import emit as _emit
        from nucleo.flash import direct_action as _da
        if _da.sure_canvas(brief) == "close" and not _da.named_cards(operator_text):
            pos = by_position(operator_text)
            if pos and not pos["card"] and pos["cands"]:
                _emit("brain", "❓ cerrar «el de " + pos["place"] + "» sin saber dónde está cada tarjeta — pregunto",
                      role="system", extra={"cat": "flash", "place": pos["place"], "cands": pos["cands"][:4]})
                return {"action": "clarify", "spoken": ask_which(pos["cands"]), "_already": True}
        got: list = []
        verb = _da.complete_canvas(brief, tag_emit=lambda a, x: got.append((a, x)), emit=_emit,
                                   operator_text=operator_text)
        if verb == "arrange":
            return {"action": "canvas:arrange", "spoken": "", "_already": True}
        if verb and got:
            cid = str(got[0][1].get("id") or "")
            action = {"close": f"canvas:close:{cid}", "minimize": f"canvas:minimize:{cid}",
                      "fullscreen": f"canvas:fullscreen:{cid}"}.get(verb, f"canvas:unfullscreen:{cid}")
            return {"action": action, "spoken": "", "_already": True}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_close: canvas mirror skipped — {type(e).__name__}: {e}")
    return {}


def music_keeps_its_turn(music_req: dict, operator_text: str) -> bool:
    """The voice close backstop's «a music call already decided this turn» — False when that call was the stop of a
    music card his words told to CLOSE (`player_close`); the stop is then dropped, the close does both."""
    req = (music_req or {}).get("v") if isinstance(music_req, dict) else None
    if not req:
        return False
    if player_close("play_music", str(req.get("action") or ""), operator_text):
        music_req["v"] = None
        return False
    return True
