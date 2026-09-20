"""The EFFECTIVENESS bench for the decision model — opt-in, real API, never in the default suite.

V2-726 §7.3 and A6b. Every other Jev test in this repo fakes the transport: they prove the WIRING
and the PARITY, and a mocked verdict can say nothing about whether the answers are any good. The
criteria text is the product surface of these decisions — measured, `desc` alone got 6 of 9 and
«Name» + the same desc got 8 of 9 — and a product surface with no regression number degrades
without anyone noticing.

HOW TO RUN IT (it is never run for you, and that is deliberate):

    ZAELAR_JEV_BENCH=1 ./.venv/bin/python -m pytest -q -s tests/voice/bench

THE THREE HARD RULES, each from something that already happened:

1. **Never in the default pass.** It spends network and money, and a red here is not a red of code —
   it is a measurement that moved. Opt-in by env var, outside the ordinary run.

2. **Never writes the operator's timeline.** On 2026-09-20 a probe of this very audit put four fake
   events into `.meshkore/logs/timeline-latest.jsonl` (no `sid`, latency 0) and they had to be
   removed by hand; a smoke test of `jev.decide` put a fifth there the night A1 shipped. `jev._emit`
   calls `voice.observer.emit`, which writes the REAL log. This file silences that emitter into its
   own sink, and asserts it did.

3. **Two runs are comparable only if they measured the same WORDING.** Two «identical» runs during
   the audit gave 8/9 and 6/9 because the criteria construction changed in between. The report
   archives the criteria text it measured, or it is not a baseline.

AND THE METRIC IS NOT ACCURACY. «Ábreme el vídeo» failed 0/8 at 0.52-0.61 — ABOVE the gate, which
means the engine would have acted on it. A bench that only counts hits reports 89% and hides the one
failure mode that matters. **wrong-and-confident is the number, and its target is zero.**
"""
from __future__ import annotations

import json
import os
import pathlib
import statistics
import time

import pytest

BENCH = os.getenv("ZAELAR_JEV_BENCH", "").strip() not in ("", "0", "no", "false")
pytestmark = pytest.mark.skipif(not BENCH, reason="opt-in: set ZAELAR_JEV_BENCH=1 (spends money)")

REPORTS = pathlib.Path(__file__).resolve().parents[3] / "tests" / "runs" / "jev-bench"

#: The operator's own sentences, which is where this bench starts (V2-726 §4-bis). `expect` is the
#: adjudicated answer; `None` means «nothing on screen is meant» (the `none` option).
CATALOG_CASES = [
    ("ábreme el vídeo", "youtube"),
    ("abre YouTube", "youtube"),
    ("abre el tiempo", None),          # no shipped widget claims generic weather — `none` is correct
    ("pon música", "musica"),
    ("enséñame mi agenda", "agenda"),
    ("abre mis mensajes", "mensajeria"),
    ("¿qué hora es?", None),           # a question, not an order naming a card
]

#: Screen targeting, with what is open. `expect` is `<widget>:<action>` or None.
SCREEN_CASES = [
    (["musica", "results"], "dale al play", "musica:play"),
    (["musica", "results"], "reproduce", "musica:play"),
    (["musica", "results"], "baja el volumen", "musica:volume_down"),
    (["musica", "results"], "siguiente canción", "musica:next"),
    (["musica", "results"], "enséñame el tercero", "results:detail"),
    (["musica", "results"], "¿qué hora es?", None),
]


@pytest.fixture(autouse=True)
def _never_the_operators_timeline(monkeypatch):
    """Rule 2, enforced rather than remembered. Returns the sink so a case can assert on it."""
    sink: list = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda *a, **k: sink.append((a, k)))
    real = pathlib.Path(__file__).resolve().parents[3] / ".meshkore" / "logs" / "timeline-latest.jsonl"
    before = real.stat().st_size if real.exists() else 0
    yield sink
    after = real.stat().st_size if real.exists() else 0
    assert after == before, (
        f"the bench wrote {after - before} bytes into the operator's real timeline — §7.3 rule 2")


def _score(rows: list[dict]) -> dict:
    """The four numbers, and the one that governs: wrong-and-confident."""
    hits = [r for r in rows if r["got"] == r["expect"]]
    confident_wrong = [r for r in rows if r["got"] != r["expect"] and r["conf"] >= 0.5]
    return {
        "n": len(rows),
        "hits": len(hits),
        "wrong_and_confident": len(confident_wrong),
        "under_gate_pct": round(100 * sum(1 for r in rows if r["conf"] < 0.5) / max(1, len(rows))),
        "confidence_p50": round(statistics.median([r["conf"] for r in rows] or [0]), 3),
        "latency_p50_ms": round(statistics.median([r["ms"] for r in rows] or [0])),
        "latency_p95_ms": round(sorted(r["ms"] for r in rows)[int(0.95 * (len(rows) - 1))]) if rows else 0,
    }


def _archive(name: str, rows: list[dict], criteria: dict, score: dict) -> pathlib.Path:
    """Rule 3: the report keeps the WORDING it measured, or it is not a baseline."""
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}.json"
    out.write_text(json.dumps({"question": name, "score": score, "rows": rows,
                               "criteria_measured": criteria}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return out


def test_which_widget_does_he_NAME():
    from nucleo import jev
    from nucleo.flash import turn_brief as tb
    assert jev.enabled(), "no key: the bench cannot measure anything"
    q = tb.catalog_question()
    assert q, "the catalogue question is not being built"

    rows = []
    for phrase, expect in CATALOG_CASES:
        t0 = time.monotonic()
        v = jev.choose_many_sync(phrase, {tb.CATALOG_KEY: q}, question_id="bench-catalog") or {}
        ans = v.get(tb.CATALOG_KEY) or {}
        got = ans.get("choice") or ""
        rows.append({"phrase": phrase, "expect": expect or "none", "got": got or "none",
                     "conf": float(ans.get("confidence") or 0.0),
                     "ms": int((time.monotonic() - t0) * 1000)})
    score = _score([{**r, "expect": r["expect"], "got": r["got"]} for r in rows])
    path = _archive("catalog", rows, q["criteria"], score)
    print(f"\n[bench] catalogue → {score}\n[bench] archived: {path}")
    for r in rows:
        print(f"    {r['phrase']!r:32} → {r['got']:14} ({r['conf']:.2f}) expected {r['expect']}")
    assert score["wrong_and_confident"] == 0, (
        "a wrong answer ABOVE the gate is the failure mode this bench exists for: the engine acts on "
        "it. «Ábreme el vídeo» used to score 0/8 at 0.52-0.61, which is why the metric is not accuracy.")


def test_which_action_of_what_is_ON_SCREEN():
    from nucleo import jev
    from nucleo.flash import turn_brief as tb
    assert jev.enabled(), "no key: the bench cannot measure anything"

    rows, criteria_seen = [], {}
    for open_ids, phrase, expect in SCREEN_CASES:
        q = tb.target_question(open_ids)
        assert q, f"no screen question for {open_ids}"
        criteria_seen = q["criteria"]
        t0 = time.monotonic()
        v = jev.choose_many_sync(phrase, {tb.TARGET_KEY: q}, question_id="bench-screen") or {}
        ans = v.get(tb.TARGET_KEY) or {}
        rows.append({"phrase": phrase, "open": open_ids, "expect": expect or "none",
                     "got": ans.get("choice") or "none",
                     "conf": float(ans.get("confidence") or 0.0),
                     "ms": int((time.monotonic() - t0) * 1000)})
    score = _score(rows)
    path = _archive("screen", rows, criteria_seen, score)
    print(f"\n[bench] screen → {score}\n[bench] archived: {path}")
    for r in rows:
        print(f"    {r['phrase']!r:26} → {r['got']:26} ({r['conf']:.2f}) expected {r['expect']}")
    assert score["wrong_and_confident"] == 0


def test_the_brief_costs_ONE_trip_whatever_it_carries():
    """The efficiency claim, against the real API rather than a counter: the whole turn's questions
    in one request take what one question takes. Measured 2026-09-20 at 708-826 ms for four."""
    from nucleo import jev
    from nucleo.flash import turn_brief as tb
    assert jev.enabled(), "no key: the bench cannot measure anything"

    one = {tb.CANVAS_KEY: tb.build("dale al play", open_ids=[])[tb.CANVAS_KEY]}
    whole = tb.build("dale al play", open_ids=["musica", "results"])

    t0 = time.monotonic()
    jev.choose_many_sync("dale al play", one, question_id="bench-one")
    ms_one = int((time.monotonic() - t0) * 1000)
    t0 = time.monotonic()
    jev.choose_many_sync("dale al play", whole, question_id="bench-whole")
    ms_whole = int((time.monotonic() - t0) * 1000)

    print(f"\n[bench] 1 question {ms_one} ms · {len(whole)} questions {ms_whole} ms")
    assert ms_whole < ms_one * 2.5, (
        f"the whole brief ({len(whole)} questions, {ms_whole} ms) costs more than a small multiple "
        f"of one question ({ms_one} ms) — the design assumes the cost is the TRIP")
