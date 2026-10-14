"""His sentence that COMMISSIONED an errand reaches that errand's sheet, so its door can judge rows by his words.

find-concert-tickets ES (2026-10-14, sandbox 021207-es). «Búscame entradas para un concierto de Rosalía en Madrid
este mes» became a worker errand, and the worker's sheet never had `asked`: only the listing fast pass wrote it
(`listing_turn`). The door (`widgets/results/category_gate`) reads subjects and specs from `asked` alone — never from a
title or a request the MODEL wrote, which is Titlecase by style — so it judged nothing, and «Miguel Lago», «El Club de
los Poetas Muertos» and «El Cascanueces» were offered as Rosalía tickets.

The text channel launches the turn's errands in one place (`probe_after._launch`), with his sentence in hand; the
sheet opens later, on the dispatcher's side, from the request alone (`sheets._sheet_open`). This module is the hand-
over between the two: `note` when the turn launched exactly ONE errand (a sentence that commissions two would hand
one errand's subject to the other: «entradas de Rosalía y un hotel en Sevilla»), `take` when that errand's sheet
opens. Keyed by the request text, bounded, and forgotten once taken.
"""
from __future__ import annotations

import time

#: request key → (his words, when). Bounded: an escalation folded into a live errand never opens a sheet to take it.
_HEARD: dict[str, tuple[str, float]] = {}
_MAX = 16
_TTL_S = 600.0


def _key(request: str) -> str:
    return " ".join(str(request or "").split())[:160].lower()


def note(requests, heard: str) -> bool:
    """Remember `heard` for the turn's single errand. True when noted. Never raises."""
    reqs = [r for r in (requests or []) if str(r or "").strip()]
    try:
        from voice.brain_notes import operator_half
        heard = operator_half(str(heard or ""))      # our [SISTEMA] notes glued to his turn are never his words
    except Exception:  # noqa: BLE001 — without the splitter the text is taken as it came
        heard = str(heard or "")
    words = " ".join(heard.split("[SISTEMA]")[0].split())   # a bare note with no header is not his either
    if len(reqs) != 1 or not words:
        return False
    now = time.time()
    for k in [k for k, (_, ts) in _HEARD.items() if now - ts > _TTL_S]:
        _HEARD.pop(k, None)
    while len(_HEARD) >= _MAX:
        _HEARD.pop(next(iter(_HEARD)))
    _HEARD[_key(reqs[0])] = (words, now)
    return True


def take(request: str) -> str:
    """His words for the errand `request` names ("" when none were noted). Taken once."""
    got = _HEARD.pop(_key(request), None)
    return got[0] if got and time.time() - got[1] <= _TTL_S else ""


def seed(sheet: str, request: str) -> bool:
    """Hand his words to the errand's sheet when it opens. True when the sheet took them. Never raises."""
    words = take(request)
    if not words or not str(sheet or "").strip():
        return False
    try:
        from widgets.results import category_gate
        took = category_gate.hear(str(sheet), words)
    except Exception as e:  # noqa: BLE001 — a sheet that cannot hear him keeps today's behaviour
        from loguru import logger
        logger.warning(f"commission_words: his words did not reach {sheet} — {type(e).__name__}: {e}")
        return False
    if took:
        try:
            from voice.observer import emit
            emit("widget", "📋 his commissioning words reached the errand's sheet", role="system",
                 extra={"sheet": str(sheet), "words": words[:120]})
        except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never blocks the sheet
            from loguru import logger
            logger.debug(f"commission_words: emit failed — {e}")
    return took


def forget() -> None:
    _HEARD.clear()
