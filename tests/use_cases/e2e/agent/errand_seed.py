"""Seed FINISHED errands into a sandbox before the opening line (V2-781 T517, 2026-10-04).

`memory_seed` tells the agent something in a prior session; this is the same idea one level up: a commission
that ran days ago, whose results sheet is already gone (the premise of `flat-hunt-recall-the-report`). A fresh
sandbox holds no errand, so without this a round measured «says it has nothing», not recall.

What is written is exactly what `nucleo/tasks.py` leaves behind when a commission closes — the durable row and
its `task_artifacts` (`result`, `criteria`, `considered`) — and nothing else: no sheet on disk, so a reply that
shows the report HAD to rebuild it from the task. It is written AFTER the between-cases `hard_reset`, because
that reset clears the board (`nucleo/reset.py::reset_all` → `tasks.board_cleared`).

The write runs in a child process with `ZAELAR_DB` pointing at the sandbox's DB: the runner never imports the
engine's store against its own environment, which is how a script once wrote into the operator's real data.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]

_CHILD = """
import json, sys
from memory import tasks_store as ts
for e in json.loads(sys.stdin.read()):
    ts.task_put(e["row"])
    for slot, payload in e["artifacts"].items():
        ts.artifact_put(e["row"]["id"], slot, payload)
"""


def _flat(tid: str, title: str, goal: str, days_ago: float, kept: list[dict], rejected: list[dict],
          hard: list[str], now: float) -> dict:
    at = int(now - days_ago * 86400)
    return {"row": {"id": tid, "title": title, "goal": goal, "kind": "research", "mode": "now", "state": "done",
                    "visible": True, "origin": "voz", "surface": "lista", "created_at": at, "started_at": at,
                    "finished_at": at + 600, "outcome": f"{len(kept)} kept, {len(rejected)} discarded"},
            "artifacts": {"result": {"title": title, "items": kept},
                          "criteria": {"goal": goal, "hard": hard},
                          "considered": {"considered": len(kept) + len(rejected), "kept": len(kept),
                                         "rows": rejected}}}


def errands_for(case_id: str, locale: str, now: float | None = None) -> list[dict]:
    """The errands a case declares. Two flat hunts on purpose: the reference «the flat I told you about» fits
    both, so the ambiguity half (ASK, naming them) is measured in the same round as the recall half."""
    if not case_id.startswith("flat-hunt-recall-the-report"):
        return []
    now = now or time.time()
    if locale == "es":
        return [
            _flat("seed-flat-gracia", "Pisos de alquiler en Gràcia", "piso de alquiler en Gràcia hasta 1.200 €/mes",
                  4, [{"title": f"Piso en Gràcia · Verdi {n}", "url": f"https://example.com/gracia/{n}",
                       "price": f"{1040 + n * 25} €/mes"} for n in range(1, 6)],
                  [{"title": f"Ático en Gràcia · Torrent de l'Olla {n}", "url": f"https://example.com/gx/{n}",
                    "why": f"{1250 + n * 40} €/mes, por encima del tope de 1.200", "source": "idealista"}
                   for n in range(1, 5)] + [{"title": "Piso en Gràcia · Travessera 41", "why": "sin ascensor, 4.º piso",
                                             "url": "https://example.com/gx/t41", "source": "fotocasa"}],
                  ["hasta 1.200 €/mes", "en Gràcia"], now),
            _flat("seed-flat-santantoni", "Pisos de alquiler en Sant Antoni", "piso de alquiler en Sant Antoni",
                  9, [{"title": f"Piso en Sant Antoni · Comte Borrell {n}", "url": f"https://example.com/sa/{n}",
                       "price": f"{1150 + n * 30} €/mes"} for n in range(1, 4)],
                  [{"title": "Estudio en Sant Antoni · Parlament 12", "why": "28 m², menos de los 50 pedidos",
                    "url": "https://example.com/sax/1", "source": "idealista"}],
                  ["al menos 50 m²", "en Sant Antoni"], now),
        ]
    return [
        _flat("seed-flat-williamsburg", "Apartments for rent in Williamsburg", "apartment for rent in Williamsburg "
              "under $3,200/month", 4,
              [{"title": f"Williamsburg 1BR · Bedford Ave {n}", "url": f"https://example.com/wb/{n}",
                "price": f"${2900 + n * 50}/month"} for n in range(1, 6)],
              [{"title": f"Williamsburg 2BR · Grand St {n}", "url": f"https://example.com/wbx/{n}",
                "why": f"${3300 + n * 100}/month, over the $3,200 cap", "source": "streeteasy"} for n in range(1, 5)]
              + [{"title": "Williamsburg 1BR · Metropolitan Ave 88", "why": "5th-floor walk-up, no elevator",
                  "url": "https://example.com/wbx/m88", "source": "zillow"}],
              ["under $3,200/month", "in Williamsburg"], now),
        _flat("seed-flat-astoria", "Apartments for rent in Astoria", "apartment for rent in Astoria", 9,
              [{"title": f"Astoria 1BR · 31st St {n}", "url": f"https://example.com/as/{n}",
                "price": f"${2400 + n * 60}/month"} for n in range(1, 4)],
              [{"title": "Astoria studio · Ditmars Blvd 12", "why": "300 sq ft, under the 500 asked for",
                "url": "https://example.com/asx/1", "source": "streeteasy"}],
              ["at least 500 sq ft", "in Astoria"], now),
    ]


def sow(db_path: str, errands: list[dict], workspace: str = "") -> list[str]:
    """Write the errands into the sandbox DB through the engine's own store. Returns the ids READ BACK."""
    if not errands:
        return []
    env = dict(os.environ, ZAELAR_DB=str(db_path))
    if workspace:
        env["ZAELAR_WORKSPACE"] = str(workspace)
    subprocess.run([sys.executable, "-c", _CHILD], input=json.dumps(errands, ensure_ascii=False), text=True,
                   cwd=str(ENGINE), env=env, check=True, timeout=60)
    ids = [e["row"]["id"] for e in errands]
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        got = {r[0] for r in con.execute(f"SELECT id FROM tasks WHERE id IN ({','.join('?' * len(ids))})", ids)}
    finally:
        con.close()
    return [i for i in ids if i in got]


def opened(db_path: str, ids: list[str], since: float) -> list[str]:
    """Which seeded task rows the round reached after `since` — any event that names the id (the recall
    verdict, the rebuilt sheet, the canvas show). The report prints this so a reader sees WHICH report came
    back, because opening the wrong one looks exactly like opening the right one."""
    if not ids:
        return []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return [i for i in ids if con.execute("SELECT 1 FROM events WHERE ts_ms >= ? AND payload LIKE ? LIMIT 1",
                                                  (int(since * 1000), f"%{i}%")).fetchone()]
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — a store we cannot read reports nothing opened, never a crash
        return []


def step(scenario, db_path: str) -> dict:
    """The runner's one call: seed what the case declares and say what landed."""
    workspace = str(Path(db_path).parents[2]) if db_path else ""
    errands = errands_for(str(getattr(scenario, "id", "")).split("__")[0], getattr(scenario, "locale", "es"))
    if not errands or not db_path:
        return {}
    try:
        landed = sow(db_path, errands, workspace)
    except Exception as e:  # noqa: BLE001 — reported, so a round with no errand is not judged as recall
        return {"seeded": [], "error": str(e)[:200]}
    print(f"  ▸ sembrados {len(landed)}/{len(errands)} encargos terminados: {', '.join(landed)}")
    return {"seeded": landed, "titles": [e["row"]["title"] for e in errands]}


def judge_note(seeded: dict | None) -> str:
    """What the judge must know before it reasons: the errands are ours, and which one the round reopened."""
    if not seeded:
        return ""
    if not seeded.get("seeded"):
        return (f"\n⚠️ AVISO DE ARNÉS — la siembra de encargos FALLÓ ({seeded.get('error', 'sin filas')}): el "
                f"motor no tenía ningún encargo que recordar, así que «no tengo nada» no es un fallo de memoria.")
    titles = seeded.get("titles") or []
    return (f"\n⚠️ AVISO DE ARNÉS — ENCARGOS SEMBRADOS: antes de la primera frase se escribieron "
            f"{len(seeded['seeded'])} encargos TERMINADOS de hace días ({' · '.join(titles)}), con su informe "
            f"en la tarea y SIN hoja en disco. El que la persona quiere es «{titles[0] if titles else '?'}». "
            f"Filas que la ronda tocó después de la primera frase: {', '.join(seeded.get('opened') or []) or 'NINGUNA'}. "
            f"Preguntar cuál de los dos es CORRECTO; abrir el otro sin preguntar, o volver a buscar en internet, "
            f"es FALLO.")
