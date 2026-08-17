"""tests/memory/judge/calibrate.py — tanda pequeña de calibración del juez (V2-105, 2026-08-17).

Norma del operador: antes de comprometerse a un corpus completo con el juez (coste real por checkpoint),
correr una tanda pequeña primero. Este script toma los checkpoints REALES del tramo longitudinal
(`tests/memory/e2e/timeline/cases.py::_real_tramo`, ya poblado en `zaelar.timeline.db` por un `--all`
determinista previo) — contradicción/paráfrasis/competencia — pregunta al RETRIEVER real y pide al juez un
veredicto, comparándolo con la comprobación determinista por substring que YA pasa. El valor del juez no está
en duplicar lo que el substring ya cubre bien (marker/not_marker limpios) — está en las paráfrasis, donde el
substring por diseño no puede afirmar nada sobre si el hecho sigue vigente.

Uso: ./.venv/bin/python -m tests.memory.judge.calibrate
Requiere que `zaelar.timeline.db` ya esté poblado (`python -m tests.memory.e2e.timeline.runner --all`).
"""
from __future__ import annotations

import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
DB_PATH = REPO / "memory" / "_data" / "zaelar.timeline.db"


# slot sintético (sin el sufijo `.N`) → pregunta en LENGUAJE NATURAL — la clave interna (`goal.job.0`) no
# comparte vocabulario con el texto guardado ("Quiero dedicarme a consultoría técnica"); preguntarle eso
# literalmente al retriever no encuentra nada, no porque el retriever falle sino porque la pregunta está mal
# planteada (hallazgo de la primera corrida de este script — el 4/6 "determinista: FALLO" de entonces era un
# bug de ESTE calibrador, no de la memoria).
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
    os.environ["ZAELAR_EMBED_BACKEND"] = "hash"  # misma BD/backend con la que el --all determinista la pobló
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
