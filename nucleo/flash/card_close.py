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
    """The open cards his words call by their catalogue NAME (never by an alias or by context) — outside the clauses
    that tell a card to STAY: «…just keep the calendar up» names the calendar to keep it (`naming.split_kept`)."""
    ids = _open_now() if open_ids is None else [str(i) for i in open_ids or []]
    words = _close_words(operator_text)
    return [w for w in ids if _says(words, w)]


def _close_words(operator_text: str) -> str:
    try:
        from widgets import naming as _naming
        return _naming.without_kept(operator_text)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_close: keep split skipped — {e}")
        return operator_text or ""


def kept(operator_text: str, open_ids=None) -> set[str]:
    """The BASES of the open cards his sentence tells to stay — no close reaches them (`instances.kept_named`)."""
    try:
        from widgets import instances as _inst
        ids = _open_now() if open_ids is None else [str(i) for i in open_ids or []]
        return {_base(w) for w in _inst.kept_named(operator_text, ids)}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_close: kept cards unread — {e}")
        return set()


def verdict_unless_named(verdict_wid: str, operator_text: str, open_ids=None) -> str:
    """The screen verdict's card, or "" when his words name a DIFFERENT open card and not the verdict's own —
    «Close the music» over `youtube:close` (0.54) is the music's close. "" hands the choice to the named cards."""
    if not verdict_wid or _says(_close_words(operator_text), verdict_wid):
        return verdict_wid
    others = [w for w in named_open(operator_text, open_ids) if _base(w) != _base(verdict_wid)]
    return "" if others else verdict_wid


def player_close(tool: str, action: str, operator_text: str, open_ids=None) -> str:
    """The player card to CLOSE when the model answered «close the music» with that player's stop/pause, or "".

    All of: a stop/pause (a play or a volume is never a close), a card-only close verb that is not negated or
    narrated (`close_guards.looks_like_close`), his words naming THIS player's card and no other open card, and the
    card open. «pausa la música y cierra la agenda» names two cards and keeps its pause."""
    from nucleo.acts import media as _pc
    return _player_card_close(_pc.CARD_OF_TOOL.get(str(tool or "").strip(), ""), action, operator_text, open_ids)


def data_close(widget_id: str, action: str, operator_text: str, *, brief=None, open_ids=None) -> bool:
    """A declared data-op his words make the CLOSE of its card (both channels, `widget_data`):

      · a SHORT close order («Vale, ciérralo» → `youtube:mute`, V2-713 R3) — unless the verdict names this very
        action («ya la puedes cerrar» → `close_meeting`, V2-770);
      · a player's stop/pause under a close verb naming that card («cierra la música, que ya no la quiero» →
        `musica:pause`, «Hecho en Música», and the card stayed — ES round 2026-10-11): `player_close`'s rule."""
    from nucleo.flash import close_guards as _cg, direct_action as _da, verdict_card as _vc
    from nucleo.acts import media as _pc
    if _cg.is_short_close_order(operator_text):   # …nor when a sure close names another view of this card
        return _da.from_brief(brief) != (widget_id, action) and not _vc.a_view_his_close_names(
            brief, widget_id, action, operator_text)
    base = _base(widget_id)
    if base in set(_pc.CARD_OF_TOOL.values()):
        return bool(_player_card_close(base, action, operator_text, open_ids))
    return False


def _player_card_close(card: str, action: str, operator_text: str, open_ids=None) -> str:
    from nucleo.flash import close_guards as _cg
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
        from nucleo.turn import brief as _tb
        names = [_tb._card_label(c) for c in cands or []]
        return _langs.current_language().ask_which_item.format(cands=", ".join(names[:3]))
    except Exception:  # noqa: BLE001
        return ""


def run_gesture(brief, *, tag_emit, emit, operator_text: str = "") -> str:
    """`direct_action.complete_canvas`'s body: the model called NOTHING and the brief SURELY names a canvas gesture —
    do it on the card the turn is about (the verdict's card, else the card his last turn acted on, else the only one
    open), through the same tag funnel the model's own calls use. Returns the gesture, or "". Never raises.

    The cards are read from his words WITHOUT the clauses that tell a card to stay (`naming.split_kept`), and a card
    he told to stay is never a target, whoever proposed it: «get rid of the video too, just keep the calendar up»
    named only the calendar, so the verdict's `youtube:close` yielded to it and the CALENDAR closed (EN t7)."""
    try:
        from nucleo.flash import direct_action as _da
        verb = _da.sure_canvas(brief)   # …unless the verdict's inner order outranks the close (`inner_order_wins`)
        if not verb or __import__("nucleo.flash.verdict_card", fromlist=["x"]).inner_order_wins(brief, operator_text):
            return ""
        if verb != "arrange" and __import__("nucleo.turn.brief", fromlist=["x"]).names_elsewhere(brief):
            return ""     # refactor2710-07: what he named is not a card on screen — no gesture lands on one
        if verb == "arrange":
            # the whole canvas, no card to pick: the same emit `arrange_canvas` and POST /api/canvas/arrange make
            from nucleo.acts import canvas
            canvas.apply("arrange", src="flash", emit=emit)
            emit("brain", "🎯 el veredicto completa al modelo (sin tool) — arrange", role="system",
                 extra={"cat": "flash", "action": "arrange", "said": (operator_text or "")[:120]})
            return verb
        from nucleo.flash import close_guards as _cg, show_target as _st
        words = operator_text   # the name readers are keep-aware (`named_open`, `also_named`); `stay` filters the rest
        stay = kept(operator_text, _da._open_now()) if verb in ("close", "minimize") else set()
        verdict_wid = verdict_unless_named(_da.from_brief(brief)[0], operator_text)   # V2-781: his NAME wins
        if _base(verdict_wid) in stay:
            verdict_wid = ""                     # the verdict proposed the card he said to keep
        named = [n for n in _da.named_cards(words) if _base(n) not in stay]
        if picks := [n for n in (brief.get("_close_picks") or []) if _base(n) not in stay] if isinstance(brief, dict) else []:
            verdict_wid, named = "", picks     # the cards the close question picked on screen (`brief_screen.named_to_close`)
        if verdict_wid and not named and not _da._action_sure(brief):
            # an UNSURE card verdict over words that name no card: «that» is the card his last turn acted on
            # (M4: the Nasdaq chart he had just asked for, not the agenda at 0.55)
            verdict_wid = position_or_focus(words, _st.close_target("")) or verdict_wid
        if verdict_wid:
            targets = [_st.close_target(verdict_wid)]
        elif named:
            # HIS words name the cards (demo pass 2026-09-28, C6: «close the calendar and the messages», neither
            # open — the gesture fell back to the card his last turn touched and closed the VIDEO). Named cards that
            # are open get the gesture; named cards that are not open mean there is nothing to do.
            open_now = _da._open_now()
            targets = [t for t in (_st.close_target(n) for n in named) if t in open_now]
        elif verb == "exit_fullscreen":    # the SCREEN says which card is at full screen (node 2.927)
            targets = [t for t in [_st.at_full_screen()] if t]
        else:
            targets = [position_or_focus(words, _st.close_target(""))]   # «the top one»
        targets = _cg.keep_cards(targets, words, rows_too=verb == "close" and not named)   # V2-781
        if verb == "close" and targets:
            # …and the OTHER open cards his sentence names (full21 C6: «close the calendar and the messages» — the
            # verdict's card was the messages; the calendar stayed and the reply said both were off the screen)
            try:
                from widgets import instances as _inst
                targets += [x for x in _inst.also_named(words, _da._open_now(), exclude=targets) if x not in targets]
            except Exception as e:  # noqa: BLE001
                logger.debug(f"card_close: also-named skipped — {e}")
        targets = [t for t in targets if _base(t) not in stay]
        if not targets:
            return ""
        for wid in targets:
            if verb == "close":
                tag_emit("close", {"id": wid})
            elif verb == "minimize":
                tag_emit("minimize", {"id": wid})
            else:
                tag_emit("fullscreen", {"id": wid, "on": verb == "fullscreen"})
            emit("brain", f"🎯 el veredicto completa al modelo (sin tool) — {verb}", text=wid, role="system",
                 extra={"cat": "flash", "widget": wid, "action": verb, "said": (operator_text or "")[:120]})
        return verb
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_close: gesture skipped — {type(e).__name__}: {e}")
        return ""


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
