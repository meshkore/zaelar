"""Execute the six-month memory timeline on one isolated, time-travelled DB."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Any

from .cases import CASES, case_id, platform_group

ENGINE = Path(__file__).resolve().parents[4]
DB_PATH = ENGINE / "memory" / "_data" / "zaelar.timeline.db"
DAY_SECONDS = 86400


def _clean_db() -> None:
    from memory import db
    db.reset_db()
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(DB_PATH) + suffix)
        if path.exists():
            path.unlink()
    db.reset_db()
    db.get_db()


def _blob(marker: str, *, valid: bool = True) -> str:
    from memory import db
    rows = db.get_db().query("SELECT text FROM memories WHERE valid=?", (1 if valid else 0,))
    return "\n".join(row["text"] or "" for row in rows).lower()


def _execute(case: dict[str, Any], now: int) -> tuple[bool, str, dict[str, Any]]:
    from memory import api as memory
    from memory import db
    from memory import rem
    op = case["op"]
    if op == "advance":
        return True, f"reloj situado en día {case['day']}", {"timestamp": now, "day": case["day"]}
    if op == "write":
        mid = memory.write_now(case["text"], level=case.get("level", "short"), kind=case.get("kind", "event"),
                               importance=case.get("importance"), weight=case.get("weight", 0.5),
                               ttl_days=case.get("ttl_days"), pinned=case.get("pinned", False),
                               slot=case.get("slot"))
        row = dict(db.get_db().query_one(
            "SELECT id,level,kind,importance,weight,ttl_days,pinned,valid,slot,created FROM memories WHERE id=?",
            (mid,)))
        return True, f"guardado id={mid} · {row['level']}/{row['kind']} · peso={row['weight']:.3f}", row
    if op == "recall":
        result = memory.query(case["query"], reinforce_used=bool(case.get("reinforce")))
        text = " ".join(item.get("text", "") for item in result["memories"]).lower()
        ok = case["marker"].lower() in text
        return ok, f"recall ids={result['ids']} · marker={case['marker']!r} {'OK' if ok else 'AUSENTE'}", result
    if op == "consolidate":
        report = memory.consolidate(limit=int(case.get("limit", 180)), now=now)
        return True, "sueño ligero · " + json.dumps(report, ensure_ascii=False), report
    if op == "rem":
        report = rem.run(None)
        return True, "REM determinista · " + json.dumps(report, ensure_ascii=False), report
    if op in {"active", "inactive"}:
        present = case["marker"].lower() in _blob(case["marker"], valid=True)
        ok = present if op == "active" else not present
        return ok, f"{case['marker']!r} activo={present} (esperado {op})", {"active": present}
    if op == "slot":
        rows = db.get_db().query("SELECT text FROM memories WHERE valid=1 AND slot=?", (case["slot"],))
        text = " ".join(row["text"] or "" for row in rows).lower()
        ok = len(rows) == 1 and case["marker"].lower() in text and case.get("not_marker", "").lower() not in text
        return ok, f"slot={case['slot']} vigentes={len(rows)} · {text[:120]}", {"rows": [dict(r) for r in rows]}
    if op == "weight_compare":
        rows = {row["slot"]: dict(row) for row in db.get_db().query(
            "SELECT slot,weight,access_count FROM memories WHERE valid=1 AND slot IN (?,?)",
            (case["stronger"], case["weaker"]))}
        strong, weak = rows.get(case["stronger"]), rows.get(case["weaker"])
        ok = bool(strong and weak and strong["weight"] > weak["weight"] and
                  strong["access_count"] > weak["access_count"])
        return ok, f"{case['stronger']}={strong} vs {case['weaker']}={weak}", rows
    if op == "valid_count":
        count = db.get_db().query_one("SELECT COUNT(*) c FROM memories WHERE valid=1")["c"]
        ok = count <= int(case["maximum"])
        return ok, f"recuerdos activos={count} ≤ {case['maximum']}", {"valid": count}
    return False, f"operación desconocida: {op}", {}


def run(until: int) -> dict[str, Any]:
    os.environ["ZAELAR_DB"] = str(DB_PATH)
    os.environ.setdefault("ZAELAR_EMBED_BACKEND", "hash")
    os.environ["MEM_SEMANTIC_DEDUP"] = "0"
    _clean_db()
    from memory.clock import travel

    observer = None
    if os.getenv("ZAELAR_TEST_RUN_DIR"):
        from tests.platform.events import EventWriter
        observer = EventWriter(os.environ["ZAELAR_TEST_RUN_DIR"], run_id=os.getenv("ZAELAR_TEST_RUN_ID"))
    selected = CASES[:until + 1]
    if observer:
        mapped = platform_group()["cases"][:until + 1]
        for index, item in enumerate(mapped, start=1):
            observer.emit("test.discovered", test_id=item["id"], suite="memory", label=item["title"],
                          index=index, total=len(mapped), case=item)
        observer.emit("collection.finished", suite="memory", total=len(mapped))

    base = int(time.time()) - 180 * DAY_SECONDS
    results = []
    for index, case in enumerate(selected):
        timestamp = base + int(case["day"]) * DAY_SECONDS + index
        started = time.perf_counter()
        if observer:
            observer.emit("test.started", test_id=case_id(index), suite="memory", label=case["title"])
            observer.emit("interaction.input", test_id=case_id(index), suite="memory",
                          input=case, expectation=case.get("expected"), simulated_day=case["day"])
        try:
            with travel(timestamp):
                ok, detail, output = _execute(case, timestamp)
        except Exception as exc:  # noqa: BLE001
            ok, detail, output = False, f"{type(exc).__name__}: {exc}", {}
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        result = {"id": case_id(index), "index": index, "day": case["day"], "op": case["op"],
                  "ok": ok, "detail": detail, "duration_ms": elapsed}
        results.append(result)
        if observer:
            observer.emit("interaction.output", test_id=case_id(index), suite="memory", output=output,
                          text=detail, simulated_day=case["day"])
            observer.emit("test.finished", test_id=case_id(index), suite="memory", label=case["title"],
                          status="passed" if ok else "failed", duration_ms=elapsed,
                          output={"detail": detail, "simulated_day": case["day"]})
        print(f"{'✓' if ok else '×'} #{index + 1:04d} · día {case['day']:03d} · {case['op']:<12} · {detail}", flush=True)
        if not ok:
            break
    passed = sum(item["ok"] for item in results)
    return {"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulación cronológica de memoria durante seis meses")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--target", type=int, help="reproduce desde cero hasta este índice inclusive")
    args = parser.parse_args()
    until = len(CASES) - 1 if args.all else args.target
    if until is None or not 0 <= until < len(CASES):
        parser.error(f"target fuera de rango 0..{len(CASES) - 1}")
    report = run(until)
    print(f"\nCronología: {report['passed']}/{report['total']} operaciones correctas")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
