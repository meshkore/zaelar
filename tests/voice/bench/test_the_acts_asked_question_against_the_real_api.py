"""The `acts_asked` question against the real decision model — opt-in, same rules as its sibling bench.

Demo V7 in a sandbox (2026-11-05): «ok stop the video and close youtube» → the model's one call closed the player,
which IS both things, and the verdict said «several» at 1.00 — so the mouth added «I've only done part of it, on
YouTube». The question now says that a stop or pause followed by a close of the same thing is one act
(`nucleo/turn/acts_asked.py`). This bench holds the two sides of that line: a close that ends what it closes is not
read as «several» above the veto floor, and the operator's own «favourite AND aliases» (V2-854 F4) still is.

    ZAELAR_JEV_BENCH=1 ZAELAR_TEST_JEV_LIVE=1 ./.venv/bin/python -m pytest -q -s tests/voice/bench/test_the_acts_asked_question_against_the_real_api.py

(`ZAELAR_TEST_JEV_LIVE=1` is the root conftest's gate: without it every test's Jev endpoint points at a closed port.)

The metric is the sibling's: wrong-and-confident, target zero — here «several» at or above `verdicts.VETO` on a close
that ends it, or «one» above the floor on two acts that each leave a result of their own.
"""
from __future__ import annotations

import json
import os
import pathlib
import time

import pytest

BENCH = os.getenv("ZAELAR_JEV_BENCH", "").strip() not in ("", "0", "no", "false")
pytestmark = pytest.mark.skipif(not BENCH, reason="opt-in: set ZAELAR_JEV_BENCH=1 (spends money)")

REPORTS = pathlib.Path(__file__).resolve().parents[3] / "tests" / "runs" / "jev-bench"

#: (phrase, what the mouth must NOT be told). `one` = a close that ends it: «several» must stay under the veto floor.
#: `several` = two results of their own: «several» must reach the floor, or the F4 line is lost.
CASES = [
    ("ok stop the video and close youtube", "one"),
    ("pause it and close the player", "one"),
    ("para el vídeo y cierra youtube", "one"),
    ("mark her as favorite and add the aliases Quinn and Quinn Rowan", "several"),
    ("Marca a Rowan Quill como contacto favorito y añádele los alias «Quinn» y «Quinn Rowan».", "several"),
    ("stop the music and show me the calendar", "several"),
    ("pon la agenda y mándale un telegram a Orion", "several"),
]
REPEAT = 3


@pytest.fixture(autouse=True)
def _never_the_operators_timeline(monkeypatch):
    sink: list = []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: sink.append((a, k)))
    real = pathlib.Path(__file__).resolve().parents[3] / ".meshkore" / "logs" / "timeline-latest.jsonl"
    before = real.stat().st_size if real.exists() else 0
    yield sink
    # the operator's LIVE engine writes this file too (its watchdog alerts landed 394 bytes during one run): the
    # check is on what the bench itself would have written, never on the byte count
    tail = b""
    if real.exists() and real.stat().st_size > before:
        with real.open("rb") as fh:
            fh.seek(before)
            tail = fh.read()
    assert b"bench-acts-asked" not in tail, "the bench wrote its verdicts into the operator's real timeline"


def test_a_close_ends_what_it_closes_and_two_results_stay_several(_never_the_operators_timeline):
    sink = _never_the_operators_timeline
    from nucleo import jev
    from nucleo.turn import acts_asked as A, verdicts
    assert jev.enabled(), "no key: the bench cannot measure anything"
    q = A.question()
    rows, wrong = [], []
    for phrase, want in CASES:
        for _ in range(REPEAT):
            t0 = time.monotonic()
            v = jev.choose_sync(A.KEY, phrase, instructions=q["instructions"], criteria=q["criteria"],
                                question_id="bench-acts-asked") or {}
            got, conf = str(v.get("choice") or ""), float(v.get("confidence") or 0.0)
            assert got, f"no verdict came back: {(sink[-1][1].get('extra') or {}) if sink else 'nothing emitted'}"
            row = {"phrase": phrase, "want": want, "got": got, "conf": round(conf, 2),
                   "ms": int((time.monotonic() - t0) * 1000)}
            rows.append(row)
            # the mouth reads «several» only at the veto floor (`acts_asked.several`)
            said = got == A.SEVERAL and conf >= verdicts.VETO
            if (want == "one" and said) or (want == "several" and not said):
                wrong.append(row)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{time.strftime('%Y%m%d-%H%M%S')}-acts-asked.json"
    path.write_text(json.dumps({"question": A.KEY, "rows": rows, "wrong": wrong, "criteria_measured": q},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[bench] acts_asked → {len(rows)} verdicts, {len(wrong)} wrong at the floor\n[bench] archived: {path}")
    for r in rows:
        print(f"    {r['phrase'][:60]!r:62} → {r['got']:8} ({r['conf']:.2f}) want {r['want']}")
    assert not wrong, wrong
