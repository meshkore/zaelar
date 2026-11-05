"""A repair pass knows what day it is (V2-781 pair 7, 2026-10-10).

Saturday 10 Oct: «el martes que viene no hay clase, quítamelo solo ese día» → `cancel_meeting {title}` was refused
(«which day?») and the same-turn correction (retired in V2-851 F2) picked 2026-10-20 — the class of the 13th stayed, with its notice. The
turn's own prompt carries today and the next seven days (`prompt.live_state`); the small repair passes carried only
the card, so «el martes que viene» was mental arithmetic. They carry the same lookup now.
"""
from __future__ import annotations

import time

from nucleo.acts import card_pass


def test_the_days_line_maps_named_days_to_dates():
    line = card_pass.days()
    today = time.strftime("%Y-%m-%d")
    assert today in line and time.strftime("%Y-%m-%d", time.localtime(time.time() + 3 * 86400)) in line
