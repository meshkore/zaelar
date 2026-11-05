"""A commission whose deliverable is a SHEET is never replaced by one call on the errand's instruments (node 2.603).

Two «Done.» of 2026-10-14, both the text channel's ack over a repaired call that replaced the commission:
  · compare-insurance-quotes EN, turn 1: «can you compare a few insurers…?» (brief: escalate · lista) → the promise
    repair ran `navegador:search` and dropped «On it — I'll pull together a comparison…» → «Done.», no worker.
  · best-plumber-same-day EN, turn 10: «I need to know if any of them are top-rated and can actually come today»
    (escalate · lista, verdict `results:criteria`) → the V2-770 rung ran `results:progress` → «Done.», and his
    refinement never reached the live worker.
The rung keeps its job on a card that holds his data (`agenda:cancel_meeting`), and with no sure verdict.
"""
from __future__ import annotations

import threading


from nucleo.flash import commission_keep


def _brief(route: str = "escalate", surface: str = "lista") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [], "_call_id": "t",
            "result": {"escalate_or_inline": {"choice": route, "confidence": 1.0},
                       "errand_surface": {"choice": surface, "confidence": 1.0}}}


def test_the_rule_itself():
    assert commission_keep.keeps_the_worker(_brief(), "results")
    assert commission_keep.keeps_the_worker(_brief(), "agenda"), "V2-794: a LIST deliverable keeps it on any card"
    assert not commission_keep.keeps_the_worker(_brief(surface="item"), "agenda")
    assert commission_keep.keeps_the_worker(_brief(surface="item"), "results")
    assert not commission_keep.keeps_the_worker(None, "navegador")
