"""V2-776 L3 · What the operator hears at the end is the VERDICT, not the worker's word (node 3.107).

Pass 60: four workers ended `ok=true` on their own word and `spoken_delivery` said «It is done.» for each —
including the one whose end state nobody could read. Now the spoken line is built on the circuit's verdict
(«done» only over `met`, «done, unverified» over `unverifiable`, «what is missing» over `gave_up`), and it obeys
the operator's standing voice rules. (The budget kill that spoke beside a clock is gone, V2-852 T06.)
"""
from __future__ import annotations

import asyncio

from nucleo import circuit
from nucleo.workers import spoken_delivery as sd


def test_the_outcome_sentence_is_the_verdicts():
    assert circuit.outcome_line("met", ok=True).startswith("It is done")
    assert "unverified" in circuit.outcome_line("unverifiable", ok=True)
    assert "Never say it is done" in circuit.outcome_line("unverifiable", ok=True)
    assert "missing" in circuit.outcome_line("unmet", ok=False)
    assert circuit.outcome_line("", ok=True) == "It is done." and circuit.outcome_line("", ok=False) == "It could not be completed."


def test_the_spoken_delivery_is_built_on_the_verdict_and_the_voice_rules(monkeypatch):
    monkeypatch.setattr(circuit, "voice_rules_line", lambda: "The person's standing rules for how you speak, which you obey: confirm my orders with a short line")
    msgs = sd._messages("find the wallpaper", "Set the Orion Nebula as wallpaper.", True, verdict="unverifiable")
    system = msgs[0]["content"]
    assert "unverified" in system and "It is done." not in system.split("unverified")[0]
    assert "standing rules" in system and "confirm my orders" in system
    msgs = sd._messages("find the wallpaper", "Done.", True, verdict="met")
    assert "checked the result yourself" in msgs[0]["content"]


def test_the_delivery_hands_the_verdict_to_the_mouth(monkeypatch):
    from nucleo.workers import session as S
    from nucleo.workers.session import SessionRecord
    seen: dict = {}

    async def _line(goal, summary, *, ok=True, verdict="", timeout=0):
        seen.update(goal=goal, ok=ok, verdict=verdict)
        return "said"

    async def _notify(*_a, **_k):
        return False
    monkeypatch.setattr(sd, "line", _line)
    from voice import proactive
    monkeypatch.setattr(proactive, "notify", _notify)
    rec = SessionRecord(task_id="t9", goal="g")
    rec.ok, rec.result_summary, rec.verdict = True, "Done, I think.", "unverifiable"
    asyncio.run(S._deliver(rec))
    assert seen["verdict"] == "unverifiable" and seen["ok"] is True


def test_the_mouth_knows_its_own_name_is_not_his(monkeypatch):
    """Demo pass 62, T1: «johnny, plan a five day trip…» came back as «Johnny, the three trip plans…»."""
    from nucleo.flash import presence
    monkeypatch.setattr(presence, "assistant_names", lambda: ("johnny",))
    system = sd._messages("johnny, plan a five day trip", "Three plans.", True, verdict="undeclared")[0]["content"]
    assert "YOUR own name is Johnny" in system and "never call him by it" in system
