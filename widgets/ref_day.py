"""widgets/ref_day.py — a reference that names its day keeps the day (agenda-everyday-edits EN, 2026-10-14).

The model names an existing row in `item` the way a person would: «Abril's piano lesson on 2026-10-20». The
resolver (`refs.resolve`) turns that into the row's id — for the agenda, its bare title — and the day went with
the rest of the words. On a series that is the difference between moving ONE day and moving every week: the
re-sent «move the 20th to the 21st» ran undated and moved the whole series to Wednesday (sandbox
20261014-121305-en, turn 12), which is what later left a day of it standing after «delete the whole series».

Narrow on purpose: one ISO day in the reference, an action whose manifest declares `date`, and a payload that
carries no day of its own. The day only ever NARROWS which row is meant; it never widens anything.
"""
from __future__ import annotations

import re

_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _declares_date(widget_id: str, action: str) -> bool:
    from . import runtime
    spec = (((runtime.get(widget_id) or {}).get("actions") or {}).get(action) or {}).get("payload")
    return isinstance(spec, dict) and "date" in spec


def carried(widget_id: str, action: str, ref: str, payload: dict) -> dict:
    """`payload` with the day `ref` names in `date`, when it names exactly one and nothing else gave a day."""
    days = set(_ISO.findall(str(ref or "")))
    if len(days) != 1 or str(payload.get("date") or "").strip() or not _declares_date(widget_id, action):
        return payload
    return {**payload, "date": days.pop()}
