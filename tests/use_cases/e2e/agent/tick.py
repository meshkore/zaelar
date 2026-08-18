"""ONE cycle of the continuous use-case loop. Meant to be fired every ~15 minutes.

The operator's mechanism (2026-08-18): two agents work the same board in parallel and neither waits for the
other. The DEV agent reads the pending use-case initiatives, fixes, and leaves a verify task saying "you can
re-test this now". THIS tick does the other half:

  1. RE-TEST whatever the dev agent has answered (verify tasks with `status: next`).
     · passes → close that initiative, the work is done.
     · fails  → CLOSE it and open a SUCCESSOR for the error that remains. Not a third round: the previous
       error was addressed and what is left is a different one, so one initiative = one concrete error with
       its task, readable at a glance. (Measured, not assumed — V2-121's round 2 had all three original
       blockers genuinely fixed and failed for a fourth reason one layer up.)
  2. TOP UP the queue so the dev agent always has ~5 cases waiting. Runs never-tried cases until
     `awaiting_fix_count()` reaches the floor.

Design constraints that shaped this:

· **A tick must never overlap another.** Two batches would fight over the sandbox port and interleave their
  scoreboard writes. A lock FILE is not enough (a killed tick leaves it behind), so the guard is "is a runner
  process actually alive", plus a stale-lock age.
· **A tick must fit in its window.** Scenarios take 2-6 minutes, so it runs at most `MAX_PER_TICK` of them
  and leaves the rest for the next fire. Falling behind is fine; a tick that runs for an hour is not.
· **Re-tests come FIRST, always.** They unblock the dev agent (who is waiting to know if the fix worked) and
  they are the only thing that can lower the queue below the floor. Filling the queue with new failures while
  answered ones sit unverified would grow the board without moving anything to done.
· **A DEADLINE, not an infinite loop.** `--hours` writes a stop time; past it the tick is a no-op that says
  so. The operator asked for ~10 hours; an unattended loop with no horizon is how a machine ends up running
  batches into next week.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import initiative as I, scenarios as SC, status as statusmod

ENGINE = I.ENGINE          # the repo root a batch must be launched from (`python -m tests…` needs it as cwd)

STATE_PATH = Path(__file__).resolve().parents[3] / "runs" / "use_cases" / "tick-state.json"
LOG_PATH = Path(__file__).resolve().parents[3] / "runs" / "use_cases" / "tick.log"
QUEUE_FLOOR = 5          # how many cases the dev agent should always have in front of him
MAX_PER_TICK = 3         # scenarios per fire — a tick must fit inside its 15-minute window
LOCK_STALE_S = 3600      # a lock older than this is assumed to be from a killed tick


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(st: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass


def _runner_alive() -> bool:
    """Is a use-case batch running right now (this tick's or a human's)?

    Checked by PROCESS, not by a lock file: a tick killed mid-batch would leave a lock behind and stall the
    loop for the rest of the night, which is a worse failure than a rare double-run.
    """
    try:
        out = subprocess.run(["pgrep", "-f", "use_cases.e2e.agent.run"],
                             capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip())
    except Exception:
        return False


def _run(args: list[str], *, timeout_s: float) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "tests.use_cases.e2e.agent.run", *args]
    try:
        r = subprocess.run(cmd, cwd=str(ENGINE), capture_output=True, text=True, timeout=timeout_s)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        return 124, f"TIMEOUT tras {timeout_s}s\n{(e.stdout or '')[-2000:]}"


def _unrun_scenarios() -> list:
    """Never-tried cases, in catalog order (ES before US, low tier first).

    A case with ANY recorded verdict is skipped — including a passing one. Re-running a case that already
    passed is what the verify path is for; the queue is topped up with genuinely new ground.
    """
    done = set((statusmod.load().get("scenarios") or {}).keys())
    out = [s for s in SC.all_scenarios() if s.id not in done]
    out.sort(key=lambda s: (0 if s.locale == "es" else 1, s.tier, s.id))
    return out


def _retest_pending() -> dict:
    """Step 1: run every case the dev agent has answered, then rotate or close each.

    Verified cases are run through `run.py --verify`, which already resolves the tasks, batches by locale
    (language is process-wide) and closes the verify tasks afterwards. What this adds is the two-state
    bookkeeping the runner deliberately does not do: passing → close; failing → close + successor.
    """
    pend = I.scenarios_awaiting_verification(SC.registry())
    ready = [p for p in pend if p["scenario"]]
    if not ready:
        return {"retested": 0}

    before = {p["scenario"]: I.find_initiative(p["scenario"]) for p in ready}
    _log(f"paso 1 · re-probando {len(ready)} caso(s) ya arreglado(s): "
         f"{', '.join(p['scenario'] for p in ready)}")
    rc, out = _run(["--verify", "--sandbox"], timeout_s=60 * 60)
    _log(f"paso 1 · terminado rc={rc}")

    led = statusmod.load().get("scenarios") or {}
    passed, rotated = [], []
    for p in ready:
        sid = p["scenario"]
        e = led.get(sid) or {}
        if e.get("state") == "PASS":
            I.close_on_pass(sid, verdict=e.get("verdict", ""), overall=e.get("overall"))
            passed.append(sid)
        elif e.get("state") == "FAIL":
            # Re-file from the ledger's summary: the full run dict lives in the child process, and the
            # initiative's own round already carries the transcript the runner appended.
            fake = {"scenario": sid, "tier": e.get("tier"),
                    "run": {"transcript": [], "mechanism_report": {"missing_signals": e.get("missing_signals")
                                                                   or []}, "watchdog_log": []},
                    "verdict": {"overall": e.get("overall"), "scores": e.get("scores") or {},
                                "findings": [], "improvements": [], "veredicto": e.get("verdict", "")}}
            scn = SC.registry().get(sid)
            if scn is not None:
                res = I.rotate_failure(fake, scenario=scn, sandboxed=True, previous=before.get(sid))
                if res.get("initiative"):
                    rotated.append(f"{sid} → {res['initiative'].name}")
    if passed:
        _log(f"paso 1 · PASAN y se cierran: {', '.join(passed)}")
    if rotated:
        _log(f"paso 1 · siguen fallando → iniciativa NUEVA: {'; '.join(rotated)}")
    return {"retested": len(ready), "passed": passed, "rotated": rotated}


def _top_up() -> dict:
    """Step 2: keep ~QUEUE_FLOOR cases waiting for the dev agent."""
    have = I.awaiting_fix_count()
    if have >= QUEUE_FLOOR:
        _log(f"paso 2 · la cola ya tiene {have}/{QUEUE_FLOOR} casos esperando arreglo — no lanzo nada nuevo")
        return {"queue": have, "ran": 0}
    todo = _unrun_scenarios()
    if not todo:
        _log(f"paso 2 · cola en {have}/{QUEUE_FLOOR} pero NO quedan casos sin probar en el catálogo")
        return {"queue": have, "ran": 0, "exhausted": True}

    # One locale per batch: ZAELAR_LANGUAGE is process-wide, so a mixed batch would grade ES cases on English
    # replies (the artefact that nearly produced false bug reports on 2026-08-18).
    lang = todo[0].locale
    picked = [s for s in todo if s.locale == lang][:min(MAX_PER_TICK, QUEUE_FLOOR - have)]
    _log(f"paso 2 · cola en {have}/{QUEUE_FLOOR} · pruebo {len(picked)} caso(s) nuevo(s) "
         f"({lang}): {', '.join(s.id for s in picked)}")
    rc, out = _run(["--sandbox", "--locale", lang, "--scenario", "all",
                    "--start-at", picked[0].id, "--limit", str(len(picked))], timeout_s=60 * 60)
    _log(f"paso 2 · terminado rc={rc} · cola ahora {I.awaiting_fix_count()}/{QUEUE_FLOOR}")
    return {"queue": I.awaiting_fix_count(), "ran": len(picked)}


def main() -> int:
    ap = argparse.ArgumentParser(description="one cycle of the continuous use-case loop")
    ap.add_argument("--hours", type=float, default=0.0,
                    help="arm the loop for this many hours from now (writes the deadline, then ticks once)")
    ap.add_argument("--stop", action="store_true", help="disarm: every later tick becomes a no-op")
    ap.add_argument("--status", action="store_true", help="print the loop's state and exit")
    args = ap.parse_args()

    st = _state()
    if args.stop:
        st["deadline"] = 0
        _save(st)
        _log("loop DESARMADO a mano — los ticks siguientes no harán nada")
        return 0
    if args.hours:
        st["deadline"] = time.time() + args.hours * 3600
        st["armed_at"] = time.time()
        _save(st)
        _log(f"loop ARMADO {args.hours}h · hasta "
             f"{time.strftime('%H:%M', time.localtime(st['deadline']))}")
    if args.status:
        dl = st.get("deadline", 0)
        left = max(0, dl - time.time()) / 3600
        print(f"deadline: {time.strftime('%Y-%m-%d %H:%M', time.localtime(dl)) if dl else '(sin armar)'} "
              f"({left:.1f}h restantes)")
        print(f"esperando arreglo: {I.awaiting_fix_count()}/{QUEUE_FLOOR} · "
              f"esperando re-test: {len(I.scenarios_awaiting_verification(SC.registry()))}")
        print(f"tablero: {statusmod.summary_line()}")
        return 0

    dl = st.get("deadline", 0)
    if not dl:
        _log("tick: el loop no está armado (usa --hours N) — no hago nada")
        return 0
    if time.time() > dl:
        _log("tick: fuera del plazo armado — no hago nada. El cron se puede borrar.")
        return 0
    if _runner_alive():
        _log("tick: ya hay una tanda corriendo — salto este turno (nunca dos a la vez)")
        return 0

    started = time.time()
    _log(f"── TICK · {(dl - time.time()) / 3600:.1f}h de plazo restante ──")
    r1 = _retest_pending()
    r2 = _top_up() if time.time() - started < 8 * 60 else {"queue": I.awaiting_fix_count(), "ran": 0,
                                                           "skipped": "sin tiempo en la ventana"}
    st["last_tick"] = time.time()
    st["last_result"] = {"retest": r1, "top_up": r2}
    _save(st)
    _log(f"── FIN TICK · re-probados {r1.get('retested', 0)} · nuevos {r2.get('ran', 0)} · "
         f"cola {r2.get('queue')}/{QUEUE_FLOOR} · {statusmod.summary_line()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
