"""A CONTROL call on one player while another player is open: whose order is it? (V2-781, after V2-740)

Measured in `tres-tarjetas-y-el-video-por-alusion` (ES+EN, 2026-10-10): the Dune trailer on the `youtube` card and
the `musica` card both open and playing, «turn the volume down a bit» / «bájale un poco el volumen». The model
called `play_music {action: volume_down}`, and the turn silently turned the MUSIC down («Volume at 55 percent»,
«Le bajo el volumen a la música»). The tool's name decides nothing here: both widgets declare the same control
actions, which is what makes them both players.

The decision already existed and every `widget_data` call consults it: `frontend.which_card` — keep the model's
card, move the order to the card the turn brief's `screen_action` verdict names for THIS action, or ASK which one
(`consent.ASK_WHICH`'s sentence, with each card's live label). `play_music` is a separate global tool, so it never
reached that question. This module is the one place both channels ask it for a player tool:

  · `plan`        — the decision (no side effects). Only a pure CONTROL is in question: a call with no query.
                    A play asks for something to sound and is about the tool's own player, bare or not (the
                    tool describes an empty query as «resume what was playing»); every other control is
                    narrowed by `which_card` itself to the actions the OTHER open player also DECLARES — the
                    manifests are the list, there is none here.
  · `voice_route` — the voice provider's half (`tool_executor_calls._t_play_music`).
  · `probe_route` — the text channel's half (`probe_decide.name_the_action`).

A moved order runs through the target card's own data-op rail (`widget_data`), the same one its own tool uses; an
asked order runs nothing. It never changes the ACTION, only the card — the same invariant as `which_card`.

`play_video` is not wired: its `action` is only ever `play` or `list` (`video_turn.normalize_action`), so it never
carries a control. The video's own controls arrive as `widget_data youtube:*`, which already consults the decision.
"""
from __future__ import annotations

from loguru import logger

#: Which card each player TOOL drives — ownership, not vocabulary.
CARD_OF_TOOL = {"play_music": "musica", "play_video": "youtube"}

#: How sure the screen verdict must be to pick between two open players on its own (V2-781, second round). Measured
#: in the same case: «turn the volume down a bit» read `musica:volume_down` at 0.54 (EN) and 0.60 (ES) — «used», so
#: the music was turned down in silence, and the judge called it what it is: luck. Two players that both declare
#: the control are a coin the verdict only settles when it is sure; below this the operator is asked which.
#: Raised 0.8 → 0.9 (EN round 2026-10-11): «Turn the volume down.» with nothing naming a card read 0.81, the music
#: went down in silence and he had to ask which one — a guess that scrapes the bar is still a guess.
PLAYER_SURE = 0.9


def _open_now() -> list[str]:
    """The cards on screen, for a turn whose brief carries no open set (Jev off). Never raises."""
    try:
        from memory import api as _memapi
        return [str(w) for w in ((_memapi.state() or {}).get("open_widgets") or [])]
    except Exception:  # noqa: BLE001
        return []


def _ask_phrase() -> str:
    try:
        from i18n import langs as _langs
        return _langs.current_language().ask_which_item
    except Exception:  # noqa: BLE001
        return ""


def _named_player(operator_text: str, open_ids, action: str = "") -> str:
    """The ONE open player his words make the TARGET («turn the music down», «bájale a la música, el vídeo no lo
    toques»), else "". A player named only to be left alone is never it (`named_target`, V2-781)."""
    if not (operator_text or "").strip():
        return ""
    try:
        from nucleo.flash import named_target as _nt
        players = set(CARD_OF_TOOL.values())
        open_players = [w for w in (open_ids or []) if str(w).split("::", 1)[0].strip().lower() in players]
        named = _nt.target(operator_text, open_players, action)
        return str(named).split("::", 1)[0].strip().lower() if named else ""
    except Exception:  # noqa: BLE001
        return ""


def plan(tool: str, action: str, query: str = "", *, brief=None, ask_phrase: str = "", operator_text: str = "") -> dict:
    """`frontend.card_decision` for a player tool's call, plus `route`: "keep" | "card" | "ask".

    `card` is where to act, `ask` the sentence to say INSTEAD of acting; `label/text/extra` one observability event.
    A player his words NAME decides first; otherwise the verdict decides only when sure (`PLAYER_SURE`).
    """
    own = CARD_OF_TOOL.get(str(tool or "").strip())
    act = str(action or "").strip().lower()
    keep = {"route": "keep", "card": own or "", "action": act, "ask": "", "label": "", "text": "", "extra": {}}
    if not own or not act or act == "play" or str(query or "").strip():
        return keep
    from nucleo.flash import frontend as _fe
    has_screen = isinstance(brief, dict) and bool(brief.get("open_ids"))
    named = _named_player(operator_text, brief.get("open_ids") if has_screen else _open_now(), act)
    if named and act in (_fe.declared_actions(named) or {}):
        return keep if named == own else {**keep, "route": "card", "card": named,
                                          "label": "🎯 la orden era del OTRO reproductor — lo nombra él",
                                          "text": f"{own}→{named}:{act}", "extra": {"id": named, "from": own,
                                                                                   "action": act, "src": "words"}}
    cd = _fe.card_decision(own, act, brief=brief, ask_phrase=ask_phrase or _ask_phrase(),
                           open_ids=() if has_screen else _open_now(), min_confidence=PLAYER_SURE)
    route = "ask" if cd.get("ask") else ("card" if cd.get("card") and cd["card"] != own else "keep")
    return {**cd, "route": route, "action": act}


def voice_route(tool: str, args: dict, *, brief, apply_widget_data, acted, clarify, emit, ask_phrase: str = "",
                operator_text: str = "") -> bool:
    """The voice half. True when this call was HANDLED here (moved to the other card, or asked about) and the
    tool's own rail must not run it; False to let the tool run as always."""
    args = args if isinstance(args, dict) else {}
    p = plan(tool, str(args.get("action") or ""), str(args.get("query") or ""), brief=brief, ask_phrase=ask_phrase,
             operator_text=operator_text)
    if p["route"] == "keep":
        return False
    if p["label"]:
        emit("brain", p["label"], role="system", text=p["text"], extra=p["extra"])
    if p["route"] == "ask":
        acted["widget"] = True
        clarify["msg"] = p["ask"]
        return True
    apply_widget_data(p["card"], p["action"], {})
    return True


def probe_route(tool: str, req: dict, tool_calls: list, *, brief, text: str = "") -> dict:
    """The text half: what the turn's action becomes. `{}` keeps the caller's own action; otherwise
    `{"action": "widget_data", "spoken": ""}` (the moved call is appended to `tool_calls` for the data-op rail to
    run, and the reply is left to the result, as `act_repair` does — the model's words named the other player) or
    `{"action": "clarify", "spoken": <the question>}` — the question is SAID, so the model's claim about an
    order that did not run («Volume at 55 percent») never reaches the operator."""
    req = req if isinstance(req, dict) else {}
    p = plan(tool, str(req.get("action") or ""), str(req.get("query") or ""), brief=brief, operator_text=text)
    if p["route"] == "ask":
        return {"action": "clarify", "spoken": p["ask"]}
    if p["route"] == "card":
        tool_calls.append({"name": "widget_data", "args": {"widget_id": p["card"], "action": p["action"],
                                                           "payload": {}, "_repair": True}})
        return {"action": "widget_data", "spoken": ""}   # its words were about the other player; the result speaks
    return {}


#: How sure the escalate verdict must be for a commission to outrank a player's one-shot play (V2-794). Measured live
#: on the escalate question (2026-10-24, 22 sentences): «put together a list of …» in four domains read `escalate`
#: at 0.88-0.98, every one-step play read `handle_inline` at 1.00.
COMMISSION_SURE = 0.85


def commissioned(brief, args) -> bool:
    """A player's one-shot `play` on a turn the brief reads SURELY as a commission — `escalate_or_inline = escalate`
    at `COMMISSION_SURE` and an ORDER: what he asked for is put together by a worker, not played as a search query
    («monta una lista para ambientar un cumpleaños» played «Cumpleaños feliz»). The verdict that the turn is real
    background work is the one paid reading of the whole turn; a play that takes his description as a title would
    discard it. Controls (pause, next, volume…), a bare resume and an unsure or absent verdict keep the play."""
    try:
        args = args if isinstance(args, dict) else {}
        if str(args.get("action") or "play").strip().lower() != "play" or not str(args.get("query") or "").strip():
            return False
        from nucleo.flash import turn_brief as _tb
        esc, info = _tb.read(brief, _tb.ESCALATE_KEY, "", min_confidence=COMMISSION_SURE)
        kind, kinfo = _tb.read(brief, _tb.REQUEST_KEY, "")
        return info is not None and esc == "escalate" and kinfo is not None and kind == "order"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"player_control: commission verdict unreadable: {e!r}")
        return False


def open_player_owns(card: str, operator_text: str, *, open_ids=None) -> str:
    """The card a late catalogue answer acts on when it named a CLOSED player while ANOTHER player is open.

    Measured in `build-a-video-playlist-from-links` (2026-10-10): the list «la de la tarde» built and named on the
    open `youtube` card, the music card closed, «Dale, ¿y qué está sonando ahora?». The screen verdict read a sure
    «none», so `card_commission.named_or_catalogue` asked the catalogue — which only describes cards, not what is on
    screen — and it answered `musica` (0.98): «what is playing» is any player's question. The repair pass then
    invented `musica:play_playlist {"playlist": "Favoritos"}` and the turn said it could not find «Favoritos».

    A bare order or question about «the player» — no card named in his words — belongs to the player in front of
    him. Returns that open player, or `card` unchanged: when his words NAME a card («ponme música», «pon el vídeo
    de gatos»), when `card` is not a player, when it is itself open, or when not exactly one other player is open.
    """
    card = str(card or "").strip()
    base = card.split("::", 1)[0].lower()
    players = set(CARD_OF_TOOL.values())
    if base not in players:
        return card
    ids = _open_now() if open_ids is None else open_ids
    open_bases = {str(w).split("::", 1)[0].strip().lower() for w in (ids or []) if str(w or "").strip()}
    if base in open_bases:
        return card
    others = sorted(p for p in players if p in open_bases)
    if len(others) != 1:
        return card
    try:
        from nucleo.flash import direct_action as _da
        if _da.named_cards(operator_text):
            return card
    except Exception:  # noqa: BLE001
        return card
    return others[0]
