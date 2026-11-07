"""The long-haul memory run (V2-858): years of a generated life on one isolated, time-travelled DB.

    ./.venv/bin/python -m tests.memory.e2e.longhaul.runner --days 1095            # three years, ~25k writes
    ./.venv/bin/python -m tests.memory.e2e.longhaul.runner --days 365 --scale 0.3 # what the integration test runs

No network and no model: hash embeddings, the deterministic REM synthesis hook and a grouping stub that knows the
generator's own label pairs (the stand-in for the model call that folds concept hubs). What it measures, at every
checkpoint and at the end, is what «the memory holds up for years» has to mean in numbers:

  · RECALL — a sample of the named facts said on every stretch of the run, asked back by name: found@12.
  · TRUTH — every singular fact (home, job, car, diet) has ONE valid row carrying the latest value, and `as_of`
    answers what it was on past days.
  · SAFETY — the allergy said on day 9 is still valid at the end, through every diet change.
  · HYGIENE — nothing past its TTL is still valid; no superseded shell is still in the vector index after the
    prune window; the concept hubs stay one per meaning after the language moved half-way.
  · COST — query latency p50/p95 over the recall probes, DB size, rows.
  · INTEGRITY — SQLite and FTS integrity checks.
The report is JSON (`--out`); the exit code is the gates' verdict.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
import time
from pathlib import Path

from .life import CONCEPTS, DAY, Life

GATES = {"found_at_12": 0.90, "slot_truth": 1.0, "as_of_truth": 1.0, "p95_ms": 400.0}
PRUNE_GRACE_DAYS = 3


def _group_stub(names):
    out = []
    for es, en in CONCEPTS.values():
        g = [x for x in (es, en) if x in names]
        if len(g) == 2:
            out.append(g)
    return out


def _synth_stub(groups):
    return [{"concept": g["concept"], "insight": f"Sustained interest in {g['concept']} "
                                                 f"({len(g['pills'])} references)."} for g in groups]


def _found(result: dict, needle) -> bool:
    return any(needle.name.lower() in (m.get("text") or "").lower() for m in result.get("memories") or [])


def _probe(memory, life: Life, upto_day: int, k: int = 60) -> dict:
    said = [x for x in life.needles if x.day <= upto_day]
    if not said:
        return {"probes": 0}
    step = max(1, len(said) // k)
    sample = said[::step][:k]
    hits, lat, by_age = 0, [], {}
    for nd in sample:
        t0 = time.perf_counter()
        r = memory.query(nd.question, reinforce_used=False, limit=12)
        lat.append((time.perf_counter() - t0) * 1000)
        ok = _found(r, nd)
        hits += ok
        bucket = f"{(upto_day - nd.day) // 180 * 6}m+"
        b = by_age.setdefault(bucket, [0, 0])
        b[0] += ok
        b[1] += 1
    lat.sort()
    return {"probes": len(sample), "found_at_12": round(hits / len(sample), 3),
            "by_age": {k_: round(v[0] / v[1], 3) for k_, v in sorted(by_age.items())},
            "p50_ms": round(statistics.median(lat), 1), "p95_ms": round(lat[int(len(lat) * 0.95) - 1], 1)}


def _truth(memory, db, life: Life, now_day: int, base: int) -> dict:
    slot_ok = slot_n = asof_ok = asof_n = 0
    bad = []
    for slot, hist in life.truth.items():
        hist = [h for h in hist if h[0] <= now_day]
        if not hist:
            continue
        rows = db.query("SELECT text FROM memories WHERE valid=1 AND slot=?", (slot,))
        slot_n += 1
        if len(rows) == 1 and hist[-1][1].lower() in rows[0]["text"].lower():
            slot_ok += 1
        else:
            bad.append({"slot": slot, "valid_rows": [r["text"] for r in rows], "truth": hist[-1][1]})
        for i, (d, v) in enumerate(hist):
            probe_day = d + 1 if i + 1 >= len(hist) else (d + hist[i + 1][0]) // 2
            if probe_day > now_day:
                continue
            got = memory.as_of(slot, base + probe_day * DAY + 3600) or {}
            asof_n += 1
            if v.lower() in str(got.get("text") or got.get("value") or "").lower():
                asof_ok += 1
            else:
                bad.append({"slot": slot, "as_of_day": probe_day, "got": got.get("text"), "truth": v})
    return {"slot_truth": round(slot_ok / slot_n, 3) if slot_n else 1.0,
            "as_of_truth": round(asof_ok / asof_n, 3) if asof_n else 1.0, "violations": bad[:6]}


def _hygiene(db, now: int) -> dict:
    q1 = lambda sql, *a: db.query_one(sql, a)["c"]  # noqa: E731
    return {
        "rows": q1("SELECT COUNT(*) c FROM memories"),
        "valid": q1("SELECT COUNT(*) c FROM memories WHERE valid=1"),
        "vec_rows": q1("SELECT COUNT(*) c FROM vec_memories") if db.vec_available else None,
        "expired_still_valid": q1("SELECT COUNT(*) c FROM memories WHERE valid=1 AND pinned=0 AND ttl_days IS NOT "
                                  "NULL AND created + CAST(ttl_days*86400 AS INTEGER) <= ?", now - DAY),
        "stale_shells_indexed": q1("SELECT COUNT(*) c FROM vec_memories v JOIN memories m ON m.id=v.memory_id "
                                   "WHERE m.valid=0 AND m.updated < ?", now - PRUNE_GRACE_DAYS * DAY)
        if db.vec_available else None,
        "concept_hubs": q1("SELECT COUNT(*) c FROM memories WHERE kind='concept' AND valid=1"),
        "allergy_valid": q1("SELECT COUNT(*) c FROM memories WHERE valid=1 AND (text LIKE '%alérgico%' "
                            "OR text LIKE '%allergic%')"),
    }


def run(days: int = 1095, scale: float = 1.0, seed: int = 7, checkpoint_every: int = 90,
        db_path: str | None = None, verbose: bool = True) -> dict:
    tmp = None
    if not db_path:
        tmp = tempfile.mkdtemp(prefix="zaelar-longhaul-")
        db_path = str(Path(tmp) / "zaelar.longhaul.db")
    os.environ["ZAELAR_DB"] = db_path
    os.environ["ZAELAR_EMBED_BACKEND"] = "hash"
    os.environ["MEMORY_RERANK"] = "off"
    os.environ["MEM_SEMANTIC_DEDUP"] = "0"
    from memory import api as memory
    from memory import db as memdb
    from memory import embeddings, rem
    from memory.clock import travel
    embeddings.reset()
    memdb.reset_db()
    db = memdb.get_db()
    life = Life(days=days, seed=seed, scale=scale)
    base = int(time.time()) - days * DAY
    t_start = time.perf_counter()
    writes = recalls = reinforced_hits = 0
    checkpoints = []
    last_day = -1
    for i, (day, op, p) in enumerate(life.schedule()):
        now = base + day * DAY + (i % 80000)
        with travel(now):
            if op == "write":
                kw = {k: v for k, v in p.items() if k not in ("text", "needle")}
                memory.write_now(p["text"], **kw)
                writes += 1
            elif op == "recall":
                r = memory.query(p["needle"].question, reinforce_used=p["reinforce"], limit=12)
                recalls += 1
                reinforced_hits += _found(r, p["needle"])
            elif op == "sleep":
                memory.consolidate(now=now)
            elif op == "rem":
                rem.run(_synth_stub, verify_fn=None, paraphrase_fn=None)
                memory.fold_concepts(_group_stub)
        if day != last_day and day > 0 and day % checkpoint_every == 0:
            with travel(now):
                cp = {"day": day, "writes": writes, **_probe(memory, life, day - 1),
                      **_truth(memory, db, life, day - 1, base), **_hygiene(db, now)}
            checkpoints.append(cp)
            if verbose:
                print(f"day {day:4d} · writes {writes:6d} · valid {cp['valid']:6d} · rows {cp['rows']:6d} · "
                      f"found@12 {cp.get('found_at_12')} · truth {cp['slot_truth']}/{cp['as_of_truth']} · "
                      f"hubs {cp['concept_hubs']} · p95 {cp.get('p95_ms')} ms", flush=True)
        last_day = day
    end = base + days * DAY
    with travel(end):
        final = {"day": days, "writes": writes, **_probe(memory, life, days, k=150),
                 **_truth(memory, db, life, days, base), **_hygiene(db, end)}
        final["integrity"] = db.query_one("PRAGMA integrity_check")[0]
        try:
            db.execute("INSERT INTO fts_memories(fts_memories) VALUES ('integrity-check')")
            final["fts_integrity"] = "ok"
        except Exception as e:  # noqa: BLE001
            final["fts_integrity"] = f"{type(e).__name__}: {e}"
    final["db_mb"] = round(sum(Path(db_path + s).stat().st_size for s in ("", "-wal") if Path(db_path + s).exists())
                           / 1e6, 1)
    final["reinforced_recall"] = round(reinforced_hits / recalls, 3) if recalls else None
    final["canonical_concepts"] = len(CONCEPTS)
    gates = {
        "found_at_12": final.get("found_at_12", 0) >= GATES["found_at_12"],
        "slot_truth": final["slot_truth"] >= GATES["slot_truth"],
        "as_of_truth": final["as_of_truth"] >= GATES["as_of_truth"],
        "allergy_survives": final["allergy_valid"] >= 1,
        "nothing_expired_is_valid": final["expired_still_valid"] == 0,
        "no_stale_shell_indexed": not final["stale_shells_indexed"],
        "one_hub_per_meaning": final["concept_hubs"] <= len(CONCEPTS) + 2,
        "latency_p95": final.get("p95_ms", 1e9) <= GATES["p95_ms"],
        "integrity": final["integrity"] == "ok" and final["fts_integrity"] == "ok",
    }
    memdb.reset_db()
    report = {"days": days, "scale": scale, "seed": seed, "wall_s": round(time.perf_counter() - t_start, 1),
              "final": final, "gates": gates, "passed": all(gates.values()), "checkpoints": checkpoints}
    if tmp:
        for s in ("", "-wal", "-shm"):
            Path(db_path + s).unlink(missing_ok=True)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Long-haul memory simulation (years of a generated life)")
    ap.add_argument("--days", type=int, default=1095)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--checkpoint-every", type=int, default=90)
    ap.add_argument("--out", type=str, default="")
    a = ap.parse_args()
    rep = run(days=a.days, scale=a.scale, seed=a.seed, checkpoint_every=a.checkpoint_every)
    text = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    print(json.dumps({"final": rep["final"], "gates": rep["gates"], "passed": rep["passed"],
                      "wall_s": rep["wall_s"]}, ensure_ascii=False, indent=1))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
