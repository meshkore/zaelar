"""widgets/youtube/tab_answer.py — what a face of the card SHOWS, as the answer of the op that turned to it.

Measured in `build-a-video-playlist-from-links` (ES, 2026-10-11, turns 2 and 7): «¿qué hay en la lista?» and «revisa
la cola» both ran `show_tab {tab: cola}` with two videos in the list. The op answered `{"ok": true, "tab": "cola"}`,
the text channel composed the spoken reply from that answer (`widget_data_turn.answer_in_words`), and with nothing
in it the reply was «la pestaña de la cola aparece vacía» — then «no hay ningún segundo puesto… ya no está en la
lista». Turning to a face that lists the queue answers with the queue, as the card holds it.
"""
from __future__ import annotations

from . import playability as _plays

#: The faces that render the queue.
QUEUE_TABS = frozenset({"cola", "player"})


def result(db: dict, tab: str) -> dict:
    """`{"queue": [...], "total": N}` for a face that shows the queue, {} for any other."""
    if tab not in QUEUE_TABS:
        return {}
    pos = int(db.get("pos", -1))
    rows = []
    for i, it in enumerate(db.get("list") or []):
        if not isinstance(it, dict):
            continue
        row = {"n": i + 1, "title": str(it.get("title") or it.get("url") or "")[:90]}
        if str(it.get("channel") or "").strip():
            row["channel"] = str(it["channel"])[:40]
        if i == pos:
            row["current"] = True
        if _plays.unplayable(db, it):
            row["cannot_play_here"] = _plays.hint(db, it)
        rows.append(row)
    return {"queue": rows, "total": len(rows)}
