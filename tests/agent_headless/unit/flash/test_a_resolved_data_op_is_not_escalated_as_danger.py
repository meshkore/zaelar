"""A resolved data-op on his own card is not re-routed to a worker as a dangerous order (V2-781 T530, pair 17).

«Pues mira, al final anúlala, que ya llamaré yo más adelante» — the model called `agenda:cancel_meeting` on the
appointment; `danger.is_dangerous` reads «anular» as an irreversible real-world cancel, and the text channel's
V2-128 backstop escalated the turn to a Brain Worker, so the data-op never ran («Hecho, la anulo» over an untouched
agenda). The voice rail already yields once a data-op went through its funnel (`data_done`, V2-748); the old text
channel listed `widget_data` among the actions it overrides (it is gone since refactor2710-01: one turn). A data-op
has a funnel; the gate is for what has none.
"""
from __future__ import annotations


def test_the_voice_rail_keeps_its_data_done_guard():
    src = open("voice/engine/llm/providers/turn_after.py", encoding="utf-8").read()
    i = src.index("_danger_bk.is_dangerous(_op_text)")
    assert "not data_done[\"v\"]" in src[src.rindex("\n    if ", 0, i):i]
