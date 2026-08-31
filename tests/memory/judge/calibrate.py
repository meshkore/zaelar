"""tests/memory/judge/calibrate.py — small judge calibration run (V2-105, 2026-08-17).

Operator rule: before committing to a full corpus with the judge (actual cost per checkpoint),
run a small batch first. This script takes the REAL checkpoints from the longitudinal segment
(`tests/memory/e2e/timeline/cases.py::_real_tramo`, already populated in `zaelar.timeline.db` by a prior
deterministic `--all`) — contradiction/paraphrase/competition — queries the real RETRIEVER and asks the judge for a
verdict, comparing it with the deterministic substring check that ALREADY passes. The judge's value is not
in duplicating what the substring already covers well (clean marker/not_marker cases) — it is in paraphrases, where the
substring cannot, by design, assert anything about whether the fact remains current.

Usage: ./.venv/bin/python -m tests.memory.judge.calibrate
Requires `zaelar.timeline.db` to already be populated (`python -m tests.memory.e2e.timeline.runner --all`).
"""
from __future__ import annotations

import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
DB_PATH = REPO / "memory" / "_data" / "zaelar.timeline.db"


# synthetic slot (without the `.N` suffix) → NATURAL-LANGUAGE question — the internal key (`goal.job.0`) does not
# share vocabulary with the stored text ("Quiero dedicarme a consultoría técnica"); asking the retriever that
# literally finds nothing, not because the retriever fails but because the question is badly
# formulated (a finding from the script's first run — the 4/6 "determinista: FALLO" at the time was a
# bug in THIS calibrator, not in the memory).
_TOPIC_QUESTIONS = {
    "goal.job": "¿A qué quiere dedicarse profesionalmente?",
    "pref.transport": "¿Cómo prefiere moverse por la ciudad?",
    "pref.diet": "¿Qué tipo de dieta sigue?",
    "goal.language": "¿Qué idioma está aprendiendo?",
    "event.next_trip": "¿Cuál es su próximo viaje planeado?",
    "pref.weekend_plan": "¿Qué tiene pensado hacer este fin de semana?",
}


def _natural_question(slot: str) -> str:
    prefix = slot.rsplit(".", 1)[0]  # "goal.job.0" → "goal.job"
    return _TOPIC_QUESTIONS.get(prefix, f"¿Qué se sabe sobre «{prefix}»?")


def _setup_env():
    os.environ["ZAELAR_DB"] = str(DB_PATH)
    os.environ["ZAELAR_EMBED_BACKEND"] = "hash"  # same DB/backend with which deterministic --all populated it
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env", override=False)
        load_dotenv(REPO / ".meshkore" / "credentials" / "zaelar.env", override=False)
    except Exception:
        pass


def main() -> int:
    if not DB_PATH.exists():
        print(f"✗ {DB_PATH} no existe — corre primero: "
              f"./.venv/bin/python -m tests.memory.e2e.timeline.runner --all")
        return 1
    _setup_env()
    from memory import retriever as memret
    from tests.memory.e2e.timeline import cases as C
    from tests.memory.judge.judge import judge_recall

    real_cases = [c for c in C.CASES if c["day"] > C.DAYS]
    slot_checks = [c for c in real_cases if c.get("op") == "slot"][:6]
    recall_checks = [c for c in real_cases if c.get("op") == "recall"][:4]

    matches, mismatches = 0, 0

    print("=" * 78)
    print(f"CALIBRACIÓN — {len(slot_checks)} contradicciones/competencias + {len(recall_checks)} paráfrasis")
    print("=" * 78)

    for case in slot_checks:
        question = _natural_question(case["slot"])
        results = memret.search(question, limit=5, expand=False, rerank=False)
        retrieved = " / ".join(r["text"] for r in results) or "(nada)"
        det_ok = case["marker"].lower() in retrieved.lower() and case["not_marker"].lower() not in retrieved.lower()
        verdict = judge_recall(question, retrieved, ground_truth=f"debe decir «{case['marker']}», NO «{case['not_marker']}»")
        agree = (verdict["veredicto"] == "correct") == det_ok
        matches += agree
        mismatches += not agree
        print(f"\n[{case['title']}]")
        print(f"  determinista: {'OK' if det_ok else 'FALLO'}  ·  juez: {verdict['veredicto']} — {verdict.get('razon', '')[:100]}")
        print(f"  {'✓ de acuerdo' if agree else '⚠️  DISCREPAN'}")

    for case in recall_checks:
        results = memret.search(case["query"], limit=5, expand=False, rerank=False)
        retrieved = " / ".join(r["text"] for r in results) or "(nada)"
        det_ok = case["marker"].lower() in retrieved.lower()
        verdict = judge_recall(case["query"], retrieved, ground_truth=f"debe mencionar algo relacionado con «{case['marker']}»")
        agree = (verdict["veredicto"] in ("correct", "stale")) == det_ok
        matches += agree
        mismatches += not agree
        print(f"\n[{case['title']}]")
        print(f"  determinista: {'OK' if det_ok else 'FALLO'}  ·  juez: {verdict['veredicto']} — {verdict.get('razon', '')[:100]}")
        print(f"  {'✓ de acuerdo' if agree else '⚠️  DISCREPAN'}")

    print("\n" + "=" * 78)
    print(f"RESULTADO: {matches}/{matches + mismatches} de acuerdo con la comprobación determinista")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
