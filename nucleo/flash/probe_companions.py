"""The text channel runs every CARD the turn asked for, not only the one it names (V2-781).

The voice provider executes each tool call the model emitted; the probe names ONE action per turn
(`probe_decide.name_the_action`), so «put on the trailer, some music, and open my calendar» played the music and
dropped the video and the calendar while the reply said «all three». The named action stays primary and is run
where it always was; these are the media and show calls beside it, through the same rails the voice uses.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.flash")

#: Primary actions that are themselves a card or media turn — only those get companions; an escalation, a search
#: or a data-op keeps its single path. A READ is one too (three cards, ES, 2026-10-10): «pause that… and what do I have
#: on Thursday?» → `widget_data youtube:pause` + `read_widget agenda`; this channel named `read_widget`, answered
#: Thursday, and the pause never ran — the trailer kept playing while a later reply said it was paused.
def _card_turn(action: str) -> bool:
    return action in ("music", "read_widget") or str(action or "").startswith("canvas:show:")


def _show(wid: str) -> bool:
    from nucleo.flash import canvas_visibility as _cvis   # the one door: this turn's words asked for the card
    _cvis.present(wid, reason="turn-order", action="show_widget", src="flash")
    return True


async def run(action: str, tool_calls: list, text: str, *, window=None, brief=None) -> list[dict]:
    """Execute the media/show calls beside the primary `action`. Returns one report per companion run."""
    if not _card_turn(action):
        return []
    names = [str(t.get("name") or "") for t in tool_calls or []]
    out: list[dict] = []
    try:
        from nucleo.flash import canvas_license, music_turn, video_turn
        from nucleo.flash import router as _router
        from nucleo.flash.show_target import last_assistant_line
        if action != "canvas:show:youtube" and "play_video" in names and canvas_license.video_license(
                text, last_assistant_line(window), brief=brief):
            v = video_turn.request_from(tool_calls)
            out.append(await video_turn.execute(v["query"], v.get("action") or "play"))
        if action != "music" and "play_music" in names:
            m = music_turn.request_from(tool_calls)
            out.append(await music_turn.execute(m["action"], m["query"]))
        if action == "read_widget" and "widget_data" in names:   # the data-ops beside the read, as the voice runs them
            from nucleo.flash import widget_data_turn
            out.append(await widget_data_turn.execute(tool_calls, text=text, brief=brief))
        if (not action.startswith("canvas:show:") and "show_widget" in names
                and not _router.show_contradicts_the_order(text)):
            from widgets import runtime as _rt
            wid = str(next(t for t in tool_calls if t.get("name") == "show_widget").get("args", {}).get("widget_id") or "")
            if wid and _rt.get(wid.split("::", 1)[0]) is not None and _show(wid):
                out.append({"executed": "show_widget", "ok": True, "id": wid})
    except Exception:  # noqa: BLE001 — a companion never costs the primary action its turn
        logger.warning("probe companions failed", exc_info=True)
    return out
