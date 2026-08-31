"""V2-469 · a watchdog verdict is another model's OPINION, and the judge amplified a false one as [high].

Measured in `cheapest-monitor__us` (23:53): the tester said, verbatim, «and honestly a bit cheaper than
$250 would be great if it's still good» — and the live watchdog filed «Zaelar invented a $250 limit that
the user did not give», which the judge then amplified into the round's [high] blocker, citing «the watchdog
detected this deviation» as its backing. The transcript was in front of both. The watchdog is a
hot-path nudger and it errs; the judge's prompt now says so where the verdicts are handed over: contrast
each one against the transcript before adopting it, and never cite the watchdog itself as evidence.
"""
from tests.use_cases.e2e.agent import judge


def test_the_handover_names_the_watchdog_as_opinion():
    prompt = judge.build_judge_prompt if hasattr(judge, "build_judge_prompt") else None
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/judge.py").read_text(encoding="utf-8")
    seg = src.split("VEREDICTOS DEL WATCHDOG", 1)[1][:900]
    assert "OPINIÓN" in seg
    assert "transcript" in seg.lower()
    assert "no cites al watchdog" in seg.lower() or "nunca cites al watchdog" in seg.lower()


def test_the_watchdog_window_covers_a_whole_round():
    """The plumbing half: the window was `transcript[-10:]` (5 exchanges) and the round's $250 turn sat at
    index 7 of 21 — OUTSIDE it, so «a limit the user never gave» was true of the window and false of the
    conversation. A fact that leaves the window becomes an accusation (the V2-176 family, in the
    instrument). Rounds cap at ~11 exchanges, so 24 entries covers any whole round."""
    from tests.use_cases.e2e.agent import watchdog

    class _S:  # minimal scenario stub
        persona_brief = ""
        success_checks = ""
        opening_line = ""

    tr = ([{"who": "tester", "text": "a bit cheaper than $250 would be great", "at": 1.0}] +
          [{"who": ("zaelar" if i % 2 else "tester"), "text": f"turno {i}", "at": float(i + 2)}
           for i in range(20)])
    msgs = watchdog.build_messages(_S(), tr)
    todo = " ".join(str(m.get("content") or "") for m in msgs)
    assert "$250" in todo, "el turno que fija la restricción tiene que estar en la ventana"
