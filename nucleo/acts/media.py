"""The media door (refactor2710-06 T-01): whose player an order is for, and what the player made of it.

  · `control(request, args)` — a CONTROL call on one player while another is open (V2-781): the music and the video
    card declare the same actions, so the tool's name decides nothing. A player his words NAME as the target decides
    first; otherwise `frontend.card_decision` keeps the card, moves the order to the one the brief's `screen_action`
    names when SURE (`PLAYER_SURE`), or asks which. It never changes the ACTION, only the card. A play asks for
    something to sound and stays with its own player.
  · `commissioned` — a one-shot play on a turn the brief reads SURELY as a commission goes to a worker (V2-794).
  · `open_player_owns` — a late catalogue answer that named a CLOSED player while another is open acts on the open one.
  · `outcome` / `settled` — what a play/next ENDED in on the video player: the op's `ok` is the card accepting the
    order; whether it plays is the embedded player's answer, ~1 s later (`build-a-video-playlist-from-links`). The
    mouth's verdict case reads it (`nucleo.turn.reply_receipts`).
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from nucleo.acts.outcome import Outcome
from nucleo.circuit import verdict as V

#: Which card each player TOOL drives — ownership, not vocabulary.
CARD_OF_TOOL = {"play_music": "musica", "play_video": "youtube"}
#: How sure the screen verdict must be to pick between two open players on its own: «turn the volume down» read
#: `musica:volume_down` at 0.54-0.81 with nothing naming a card — a guess that scrapes the bar is still a guess.
PLAYER_SURE = 0.9
#: How sure `escalate_or_inline = escalate` must be for a commission to outrank a one-shot play (measured 0.88-0.98
#: on «put together a list of …», every one-step play at `handle_inline` 1.00).
COMMISSION_SURE = 0.85
#: The player's refusal arrives ~1 s after the load (measured 0.98 s, then 0.65 s more for the swap's own).
QUIET_S = 1.6
_POLL_S = 0.1


def _note(what: str) -> None:
    logger.debug(f"acts.media: {what}")


def _open_now() -> list[str]:
    """The cards on screen, for a turn whose brief carries no open set (Jev off). Never raises."""
    try:
        from memory import api as _memapi
        return [str(w) for w in ((_memapi.state() or {}).get("open_widgets") or [])]
    except Exception as e:  # noqa: BLE001
        _note(f"no open set ({e!r})")
        return []


def _ask_phrase() -> str:
    try:
        from i18n import langs as _langs
        return _langs.current_language().ask_which_item
    except Exception as e:  # noqa: BLE001
        _note(f"no ask phrase ({e!r})")
        return ""


def _named_player(operator_text: str, open_ids, action: str = "") -> str:
    """The ONE open player his words make the TARGET, else "". A player named to be left alone never is (V2-781)."""
    if not (operator_text or "").strip():
        return ""
    try:
        from nucleo.flash import named_target as _nt
        players = set(CARD_OF_TOOL.values())
        named = _nt.target(operator_text, [w for w in (open_ids or []) if str(w).split("::", 1)[0].strip().lower()
                                           in players], action)
        return str(named).split("::", 1)[0].strip().lower() if named else ""
    except Exception as e:  # noqa: BLE001
        _note(f"no named player ({e!r})")
        return ""


def plan(tool: str, action: str, query: str = "", *, brief=None, ask_phrase: str = "", operator_text: str = "") -> dict:
    """`frontend.card_decision` for a player tool's call, plus `route`: "keep" | "card" | "ask". `card` is where to
    act, `ask` the sentence to say INSTEAD of acting; `label/text/extra` one observability event."""
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


def control(request: dict, args: dict, *, tool: str, apply_widget_data, acted, clarify, emit,
            ask_phrase: str = "") -> Outcome:
    """`fired` when this call was HANDLED here — moved to the other card through its own data-op rail, or asked
    about — and the tool's own rail must not run it; not fired to let the tool run as always."""
    args = args if isinstance(args, dict) else {}
    p = plan(tool, str(args.get("action") or ""), str(args.get("query") or ""), brief=(request or {}).get("brief"),
             ask_phrase=ask_phrase, operator_text=str((request or {}).get("text") or ""))
    if p["route"] == "keep":
        return Outcome(False, V.SKIPPED.name)
    if p["label"]:
        emit("brain", p["label"], role="system", text=p["text"], extra=p["extra"])
    if p["route"] == "ask":
        acted["widget"] = True
        clarify["msg"] = p["ask"]
        return Outcome(True, V.ASKED.name, p["ask"])
    apply_widget_data(p["card"], p["action"], {})
    return Outcome(True, V.STARTED.name, data={"card": p["card"], "action": p["action"]})


def commissioned(brief, args) -> bool:
    """A one-shot `play` on a turn the brief reads SURELY as an ORDER for background work («monta una lista para
    ambientar un cumpleaños» played «Cumpleaños feliz»). Controls, a bare resume and an unsure verdict keep the play."""
    try:
        args = args if isinstance(args, dict) else {}
        if str(args.get("action") or "play").strip().lower() != "play" or not str(args.get("query") or "").strip():
            return False
        from nucleo.turn import brief as _tb
        esc, info = _tb.read(brief, _tb.ESCALATE_KEY, "", min_confidence=COMMISSION_SURE)
        kind, kinfo = _tb.read(brief, _tb.REQUEST_KEY, "")
        return info is not None and esc == "escalate" and kinfo is not None and kind == "order"
    except Exception as e:  # noqa: BLE001
        _note(f"commission verdict unreadable: {e!r}")
        return False


def open_player_owns(card: str, operator_text: str, *, open_ids=None) -> str:
    """The open player a bare order about «the player» belongs to, when the catalogue named a CLOSED one («¿y qué
    está sonando ahora?» over the open video answered `musica`). `card` unchanged when his words NAME a card, when it
    is not a player, when it is itself open, or when not exactly one other player is open."""
    card = str(card or "").strip()
    base = card.split("::", 1)[0].lower()
    players = set(CARD_OF_TOOL.values())
    if base not in players:
        return card
    open_bases = {str(w).split("::", 1)[0].strip().lower() for w in ((_open_now() if open_ids is None else open_ids)
                                                                     or []) if str(w or "").strip()}
    others = sorted(p for p in players if p in open_bases)
    if base in open_bases or len(others) != 1:
        return card
    try:
        from nucleo.flash import direct_action as _da
        return card if _da.named_cards(operator_text) else others[0]
    except Exception as e:  # noqa: BLE001
        _note(f"named cards unreadable ({e!r})")
        return card


# ── what the player made of it ───────────────────────────────────────────────────────────────────────────────

def outcome(card: str) -> dict:
    """`{"state": "playing"|"blocked"|"swapped"|"", "title", "to"}` for the video card: `blocked` is an error on the
    current video, a terminal notice or its id on the blocklist; `swapped` refused and replaced. "" when unread."""
    empty = {"state": "", "title": "", "to": ""}
    if str(card or "").split("::", 1)[0].strip().lower() != "youtube":
        return empty
    try:
        from widgets import store as _st
        from widgets.youtube import availability as _av
        db = _st.load("youtube") or {}
        title = str(db.get("title") or "").strip()
        bn = db.get("blocked_notice") if isinstance(db.get("blocked_notice"), dict) else {}
        kind, vid = str(bn.get("kind") or ""), str(db.get("videoId") or "")
        if kind in ("exhausted", "explicit"):
            return {"state": "blocked", "title": str(bn.get("from") or title), "to": ""}
        if str(db.get("player_error") or "").strip() or (vid and vid in _av.blocked_ids(db)):
            return {"state": "blocked", "title": title, "to": ""}
        if kind == "swapped":
            return {"state": "swapped", "title": str(bn.get("from") or ""), "to": str(bn.get("to") or title)}
        return {"state": "playing" if title else "", "title": title, "to": ""}
    except Exception as e:  # noqa: BLE001
        _note(f"card unread — {e}")
        return empty


def _on_screen(card: str) -> bool:
    try:
        from nucleo.flash import canvas_visibility as _cv
        return _cv.is_open(card)
    except Exception as e:  # noqa: BLE001
        _note(f"canvas unread — {e}")
        return False


async def settled(card: str, *, quiet_s: "float | None" = None, min_wait: float = 0.0) -> dict:
    """`outcome(card)` once the player had its say: a refusal ends the wait, a swap restarts it (the replacement can be
    refused too), a quiet window means it plays. Without a screen there is no player to wait for. `min_wait` lets an
    op still in flight (the voice rail dispatches detached) land first."""
    quiet_s = QUIET_S if quiet_s is None else quiet_s
    if min_wait > 0:
        await asyncio.sleep(min_wait)
    out = outcome(card)
    if out["state"] in ("", "blocked") or not _on_screen(card):
        return out
    deadline = time.monotonic() + quiet_s
    seen, refused = out, []
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_S)
        out = outcome(card)
        if out["state"] == "swapped" and out["title"] and out["title"] not in refused:
            refused.append(out["title"])          # the first refused, its replacement in its place: both are named
        if out["state"] == "blocked":
            break
        if out != seen:
            seen, deadline = out, time.monotonic() + quiet_s
    if out["state"] == "blocked" and out["title"] and out["title"] not in refused:
        refused.append(out["title"])
    return {**out, "refused": refused or ([out["title"]] if out["state"] == "blocked" and out["title"] else [])}
