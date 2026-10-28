"""Which card a close means (refactor2710-04b T-06: `close_which` + `close_identify`, beside the canvas door).

A `close_widget` on a piece with several cards open, and no word to tell them apart, ASKS which (node 2.645).

two-searches-two-sheets (ES, 2026-10-14, sandbox 024032-es): a plumber hunt and a car hunt, each with its own
results sheet open, and «cierra los resultados». The model called `close_widget(results)`; `show_target.close_target`
kept the bare id because two real sheets were open and nothing focused one («the tag's own resolution asks»), but
the tool path never asked — the bare close reached the canvas and BOTH sheets went: «He cerrado Resultados. Ya no
queda nada en pantalla.» — «¿cuál has cerrado? Te he dicho los resultados, pero tengo dos búsquedas».

The question already exists and is the [[close]] tag's (`widgets.instances.resolve_close`): one instance named →
that one, «los dos» → all, a title word → that sheet, otherwise «¿cuál cierro, «…» o «…»?». Both tool paths —
the voice executor (`show_target.close_dispatch`) and the text channel (`probe_decide`) — now read it here.
"""
from __future__ import annotations

from loguru import logger


def resolve(card: str, text: str, open_ids=None) -> tuple[str, str]:
    """(the card to close, the question to ask INSTEAD) for a close resolved to `card`. Never raises.

    Only a BARE piece id can be ambiguous — an instance id (`results::t7`) already names one card. A title word in
    his sentence narrows the bare id to that sheet; «los dos» keeps it (the bare close takes every card of it)."""
    card = str(card or "").strip()
    if not card or "::" in card:
        return card, ""
    try:
        from widgets import instances as _inst
        if open_ids is None:
            from server.voice_api import open_instances
            open_ids = open_instances()
        out = _inst.resolve_close(card, list(open_ids or []), text)
    except Exception as e:  # noqa: BLE001 — unreadable screen: close as before, a spurious question is worse
        logger.debug(f"close_which: open cards unreadable — {type(e).__name__}: {e}")
        return card, ""
    if out.get("ask"):
        return card, str(out["ask"])
    ids = list(out.get("ids") or [])
    return (ids[0] if len(ids) == 1 else card), ""


def probe_action(args: dict, card: str, text: str) -> tuple[str, str]:
    """(the text channel's action, the question it says) for a `close_widget` call resolved to `card`."""
    mode = "minimize" if str((args or {}).get("mode") or "") == "minimize" else "close"
    card, question = resolve(card, text) if mode == "close" else (card, "")
    if question:
        _emit(card, question)
        return "clarify", question
    return (f"canvas:{mode}:{card}" if card else "clarify"), ""


def _emit(card: str, question: str) -> None:
    try:
        from voice.observer import emit
        emit("brain", "❓ close of a piece with several cards open — asking which", text=card, role="system",
             extra={"cat": "flash", "ask": question[:160]})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_which: emit failed — {e}")


# ── the card a close BACKSTOP reads from his words (was `close_identify`) ──
#: The card a close BACKSTOP reads from his words — never one he told to stay (both channels, 2026-10-14).
def identify(text: str, open_ids) -> dict:
    """`runtime.identify` over the close words of `text`; `{}` when the card it reaches is one he told to stay."""
    ids = list(open_ids or [])
    try:
        from widgets import instances as _inst, naming as _naming, runtime as _rt
        res = _rt.identify(_naming.without_kept(text), open_ids=ids) or {}
        stay = {_inst.base_of(k) for k in _inst.kept_named(text, ids)}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_identify: skipped — {e}")
        return {}
    if res.get("match") and _inst.base_of(str(res["match"])) in stay:
        return {}
    return res
