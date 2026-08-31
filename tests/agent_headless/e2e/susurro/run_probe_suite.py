"""“Susurro” integration group (V2-053) — headless suite through FlashBrain’s TEST channel.

Verifies the COMPLETE cycle against the LIVE server (make run / make flash-serve):
  simulated friction (operator complaint via probe) → Susurro trigger → request/response to the auditor LLM
  (events with payload in the timeline) → corrections applied → spoken repair_say on the following turn.

The MACHINERY is required (without trigger/request/response = FAIL); the model’s JUDGMENT is reported without failing the
suite (deciding corrections=[] for a healthy segment is correct). Each run APPENDS its summary to
`tests/agent_headless/e2e/susurro/history.jsonl` — the LONGITUDINAL metric the operator requested to see whether the system
improves (less friction, better diagnoses) over time.

Usage:  ./.venv/bin/python tests/agent_headless/e2e/susurro/run_probe_suite.py  [--base http://localhost:43917]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

TIMELINE = os.path.join(".meshkore", "logs", "timeline-latest.jsonl")
HISTORY = os.path.join(os.path.dirname(__file__), "history.jsonl")


def _post(base: str, path: str, body: dict, timeout: float = 60) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _susurro_events(since_ts: float) -> list[dict]:
    out = []
    try:
        with open(TIMELINE, encoding="utf-8") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                # the timeline records the epoch in ms as `t_ms` (not `ts`)
                if ev.get("kind") == "susurro" and float(ev.get("t_ms") or 0) / 1000.0 >= since_ts:
                    out.append(ev)
    except FileNotFoundError:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:43917")
    ap.add_argument("--session", default="susurro-e2e")
    args = ap.parse_args()

    t_start = time.time()
    print("── susurro e2e: turno normal + QUEJA por el probe ──")
    r1 = _post(args.base, "/api/flash/say",
               {"text": "abre el widget del reloj", "session": args.session, "ingest": False})
    print(f"  turno 1 ok={r1.get('ok')} acción={r1.get('action')}")
    time.sleep(1.0)
    r2 = _post(args.base, "/api/flash/say",
               {"text": "te he dicho que abrieras la AGENDA, no el reloj, y no me estás haciendo caso",
                "session": args.session, "ingest": False})
    print(f"  turno 2 (queja) ok={r2.get('ok')} trace={r2.get('trace')}")

    print("── esperando ciclo de auditoría (máx 90s) ──")
    labels: list[str] = []
    deadline = time.time() + 90
    while time.time() < deadline:
        evs = _susurro_events(t_start)
        labels = [e.get("label", "") for e in evs]
        if any("auditoría completa" in l for l in labels) or any("fail-open" in l for l in labels):
            break
        time.sleep(2)
    evs = _susurro_events(t_start)
    labels = [e.get("label", "") for e in evs]

    has_trigger = any("fricción" in l for l in labels)
    has_request = any("request → LLM" in l for l in labels)
    has_response = any("response ← LLM" in l for l in labels)
    done = next((e for e in evs if "auditoría completa" in e.get("label", "")), None)
    applied = [e for e in evs if "repair_say" in e.get("label", "") or "finding" in e.get("label", "")]

    print(f"  eventos susurro: {len(evs)} · trigger={has_trigger} request={has_request} "
          f"response={has_response} completa={bool(done)} correcciones={len(applied)}")
    if done:
        # the timeline FLATTENS `extra` into the event
        print(f"  assessment: {str(done.get('assessment'))[:200]}")
        print(f"  tipos: {done.get('types')} · total_ms: {done.get('total_ms')}")

    repair_spoken = ""
    if any("repair_say" in e.get("label", "") for e in applied):
        print("── turno 3: la reparación debe salir hablada (probe drena brain_notes) ──")
        r3 = _post(args.base, "/api/flash/say", {"text": "vale", "session": args.session, "ingest": False})
        repair_spoken = str(r3.get("reply") or r3.get("text") or "")[:200]
        print(f"  respuesta: {repair_spoken}")

    ok = has_trigger and has_request and has_response and bool(done)
    row = {"ts": time.time(), "ok": ok, "n_events": len(evs), "n_corrections": len(applied),
           "assessment": (done or {}).get("assessment", ""),
           "types": (done or {}).get("types", []),
           "total_ms": (done or {}).get("total_ms"),
           "repair_spoken": repair_spoken}
    try:
        with open(HISTORY, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    print(f"\nVEREDICTO: {'PASS' if ok else 'FAIL'} (maquinaria del ciclo)"
          + ("" if ok else " — falta trigger/request/response/completa; mira /debug kind=susurro"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
