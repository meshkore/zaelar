"""His sentence that commissions an errand travels with the request to the errand it opens (refactor2710-02 input).

find-concert-tickets ES: «Búscame entradas para un concierto de Rosalía en Madrid este mes» became a worker errand
whose sheet never had `asked` — the row door judges rows by his words, so it judged nothing and offered rows that were
not about Rosalía. The old text channel noted his sentence at launch (`commission_words`, node 2.630) and the voice
turn never did; refactor2710-01 deleted the old channel's half. The class is the Request's: born once with his words,
it carries them to the worker and the sheet. Strict expected failure until refactor2710-02 makes the escalation the
turn records carry them.
"""
from __future__ import annotations

import pytest

from tests.brain import harness as H

HEARD = "Búscame entradas para un concierto de Rosalía en Madrid este mes."


@pytest.mark.xfail(reason="refactor2710-02: the request carries his words", strict=True)
def test_the_worker_door_carries_his_commissioning_words():
    case = {"id": "commission-words", "lang": "es", "phrase": HEARD, "source": "node 2.630",
            "screen": {"open": []}, "expect": "escalate",
            "model": {"say": "Me pongo con ello.",
                      "tools": [{"name": "escalate_to_slowbrain",
                                 "args": {"request": "entradas concierto Rosalía Madrid", "surface": "results"}}]}}
    out = H.run_case(case)
    assert not out.error, out.error
    rows = [e for e in (out.events or []) if e.get("kind") == "brain" and "escalada registrada" in str(e.get("label"))]
    assert out.action == "escalate" and rows, "the turn did not escalate — the premise of this test"
    assert rows[0].get("asked") == HEARD, rows[0]
