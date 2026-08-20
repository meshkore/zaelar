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

from . import initiative as I, scenarios as SC, segments as SG, status as statusmod

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
    """Never-tried cases that can actually FINISH, in catalog order (ES before US, low tier first).

    A case with ANY recorded verdict is skipped — including a passing one. Re-running a case that already
    passed is what the verify path is for; the queue is topped up with genuinely new ground.

    RUNNABLE ONLY (`segments.is_completable`). This filter is the difference between measuring the product and
    burning the night on the environment: 78 of the 125 catalogue cases cannot reach their own goal here, either
    because they need a credential/payment/real object only the operator can supply (54) or because the
    capability is not built yet (24). Launching one costs the same 3-6 minutes as a real case and ends the same
    way every time — "it asked me to log in" — so the loop would file initiative after initiative against a
    fixing agent who has no way to act on any of them, and the board would fill with work nobody can do while
    the runnable cases sat untouched. Blocked cases are not forgotten: they stay in the catalogue with the
    reason recorded, and `run.py --segment` runs them on purpose the day the operator unblocks them.
    """
    # A VERDICT is PASS or FAIL. An `INFRA` entry means the harness itself died before judging anything — the
    # case was never measured, so it has to stay in the queue. Treating any ledger key as "done" quietly
    # retired `build-workout-tracker-widget`, the one runnable case covering widget generation: it died on a
    # broker 403 and from then on every tick skipped it as already-tried (found 2026-08-20).
    led = statusmod.load().get("scenarios") or {}
    judged = {k for k, e in led.items() if (e or {}).get("state") in ("PASS", "FAIL")}
    out = [s for s in SC.all_scenarios() if s.id not in judged and SG.is_completable(s.id)]
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
    # An UNRESOLVABLE slug is reported, never dropped in silence — `scenarios_awaiting_verification`'s own
    # docstring says so, and until 2026-08-20 this line was where the promise broke: two tasks
    # (`progreso-fabricado`, `progreso-fabricado-idioma`) asked for a re-test of a PATTERN rather than a case,
    # so they resolved to no scenario, got filtered out here, and stayed `status: next` for ever. The fixing
    # agent waits for a re-test that can never run, and `esperando re-test` reports a number that is mostly
    # fiction. The tick cannot ACT on them, but it can say their names.
    orphan = [p for p in pend if not p["scenario"]]
    if orphan:
        _log("paso 1 · tareas de verify que NO apuntan a ningún caso del catálogo (nadie las va a correr; "
             "hace falta una por CASO, o cerrarlas): "
             + "; ".join(f"{p['task'].name} (slug «{p['slug']}»)" for p in orphan))
    # TWO verify tasks can name the SAME case (the dev agent answers a case in two separate fixes, as
    # T434+T438 did for `find-theatre-tickets__es` on 2026-08-20). `run.py --verify` measures it ONCE and
    # closes both tasks, so a duplicate here is never a second measurement — it is the bookkeeping below
    # running twice off one verdict, which appends the SAME round to the umbrella twice and inflates the
    # re-tested count. Collapse by case, keep the first, and say so.
    seen: set[str] = set()
    unique, dup = [], []
    for p in ready:
        if p["scenario"] in seen:
            dup.append(p["task"].name)
            continue
        seen.add(p["scenario"])
        unique.append(p)
    ready = unique
    if dup:
        _log("paso 1 · varias tareas de verify para el MISMO caso; se mide una vez y se cierran todas: "
             + ", ".join(dup))
    if not ready:
        return {"retested": 0, "orphan": [p["task"].name for p in orphan]}

    before = {p["scenario"]: I.find_initiative(p["scenario"]) for p in ready}
    # When each case was last MEASURED, read before the batch. What comes back is compared against it below:
    # a row whose `last_run` did not move was not re-measured, whatever the batch's exit code said.
    led_before = statusmod.load().get("scenarios") or {}
    stamp_before = {p["scenario"]: (led_before.get(p["scenario"]) or {}).get("last_run") for p in ready}
    _log(f"paso 1 · re-probando {len(ready)} caso(s) ya arreglado(s): "
         f"{', '.join(p['scenario'] for p in ready)}")
    rc, out = _run(["--verify", "--sandbox"], timeout_s=60 * 60)
    # PERSISTIR el stdout de la tanda. Antes solo se logueaba el rc, y el 2026-08-19 a las 16:56 cinco casos
    # murieron con «Connection refused» sin que quedara NADA para saber en qué punto: ni el traceback, ni el
    # orden real de ejecución, ni si el sandbox se cayó o nunca arrancó para ese grupo. Reconstruirlo a mano
    # costó más que la propia corrida. Un tick desatendido que tira su única evidencia obliga a reproducir el
    # fallo para diagnosticarlo, y un fallo intermitente puede no volver.
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        (LOG_PATH.parent / f"verify-stdout-{stamp}.log").write_text(out or "(sin salida)", encoding="utf-8")
    except Exception:
        pass
    # El rc SOLO no basta para reconstruir qué pasó. El 2026-08-20 a las 02:46 un tick con `rc=1` en 0 segundos
    # clasificó su caso como BLOQUEADO en vez de como no-medido, y el marcador decía que su `last_run` no se
    # había movido — o sea que el guard de arriba debería haber saltado y no saltó. No se pudo explicar con lo
    # que había en el log, así que se registran los DOS sellos por caso: la próxima vez el log es la evidencia
    # en vez del punto de partida de una investigación.
    _log(f"paso 1 · terminado rc={rc} · sellos "
         + ", ".join(f"{p['scenario']}: {stamp_before.get(p['scenario'])!r}→"
                     f"{((statusmod.load().get('scenarios') or {}).get(p['scenario']) or {}).get('last_run')!r}"
                     for p in ready))

    led = statusmod.load().get("scenarios") or {}
    passed, rotated, inconclusive, blocked, unrun = [], [], [], [], []
    for p in ready:
        sid = p["scenario"]
        e = led.get(sid) or {}
        # DID IT ACTUALLY RUN? A batch can exit having measured nothing — the case that taught us this was an
        # ORPHANED SANDBOX (`python -m server`, PPID 1) left behind by a killed batch: it kept port 43918, so
        # every later `run.py --verify` died on boot in under a second. `_runner_alive()` does not see it (it
        # looks for a `…agent.run` process, not the engine the batch spawns), so the tick kept starting batches
        # that could not work, and then read the ledger's PREVIOUS verdict and acted on it: it logged
        # "re-probado" for a case nobody re-ran, and worse, `rotate_failure` would file an initiative
        # describing a run from an hour ago as if it were new evidence. Stale evidence is worse than none —
        # the fixing agent cannot tell it apart. `last_run` not moving is the proof, and it is a general one:
        # it holds for any reason a batch fails to measure, not just this one.
        if e.get("last_run") == stamp_before.get(sid):
            unrun.append(sid)
            continue
        if e.get("state") == "PASS":
            I.close_on_pass(sid, verdict=e.get("verdict", ""), overall=e.get("overall"))
            passed.append(sid)
        elif e.get("state") == "FAIL":
            # A GROUPED case does NOT rotate: `run.py --verify` already appended its round to the shared
            # umbrella, and opening a per-case successor here would re-fragment exactly what the grouping
            # exists to hold together. Whether the remaining error is still the shared one is a judgement on
            # the evidence — it is made by reading the umbrella's rounds, not by the tick guessing.
            if I.grouped_for(sid) is not None:
                rotated.append(f"{sid} → ronda en {I.grouped_for(sid).name} (agrupado, no rota)")
                continue
            # A BLOCKED case does not become a work order either (see `initiative.file_failure`). Said here too
            # so the tick's own log names it instead of going quiet about a case it just re-ran.
            seg = SG.segment_of(sid)
            if seg is not None and seg.group != SG.COMPLETABLE:
                # LOG ONLY — do not file. `run.py --verify` already appended this case's round to the shared
                # umbrella (`initiative.file_failure` routes a blocked case there), exactly like the grouped
                # branch above. Filing again here wrote the SAME round twice, same case, same minute — caught
                # reading V2-176 on 2026-08-20, rounds 3 and 4 identical. The tick's job in this branch is to
                # NAME what it re-ran, not to re-file it.
                blocked.append(f"{sid} ({SG.group_of(sid)} · necesita "
                               f"{getattr(seg, 'missing', '') or 'algo que no tenemos aquí'})")
                continue
            # Re-file from the ledger's summary: the full run dict lives in the child process, and the
            # initiative's own round already carries the transcript the runner appended.
            fake = {"scenario": sid, "tier": e.get("tier"),
                    "run": {"transcript": [], "turns_used": e.get("turns_used"),
                            "mechanism_report": {"missing_signals": e.get("missing_signals") or [],
                                                 "families_observed": e.get("families") or []},
                            "watchdog_log": []},
                    "verdict": {"overall": e.get("overall"), "scores": e.get("scores") or {},
                                "findings": [], "improvements": [], "veredicto": e.get("verdict", "")}}
            scn = SC.registry().get(sid)
            if scn is not None:
                res = I.rotate_failure(fake, scenario=scn, sandboxed=True, previous=before.get(sid))
                if res.get("initiative"):
                    rotated.append(f"{sid} → {res['initiative'].name}")
        else:
            # Neither PASS nor FAIL: the run died before producing a verdict (INFRA). Not a verdict, so nothing
            # closes and nothing rotates — but it must not vanish either, or the fixing agent's consumed verify
            # task looks like it was ignored.
            if I.note_inconclusive(sid, detail=e.get("verdict", "") or "sin veredicto"):
                inconclusive.append(sid)
    if passed:
        _log(f"paso 1 · PASAN y se cierran: {', '.join(passed)}")
    if rotated:
        _log(f"paso 1 · siguen fallando → iniciativa NUEVA: {'; '.join(rotated)}")
    if unrun:
        _log(f"paso 1 · NO SE MIDIERON (la tanda salió sin medir nada — mira si quedó un sandbox huérfano "
             f"ocupando el puerto: `lsof -nP -iTCP:43918 -sTCP:LISTEN`). Su tarea de verify sigue pendiente y "
             f"el próximo tick lo reintenta; NO se toca su iniciativa: {', '.join(unrun)}")
    if blocked:
        _log(f"paso 1 · BLOQUEADOS (su objetivo no se alcanza aquí; solo se mide la HONESTIDAD, y la ronda "
             f"va al paraguas compartido): {'; '.join(blocked)}")
    if inconclusive:
        _log(f"paso 1 · NO CONCLUYENTE (fallo de arnés, ni cierra ni rota; hace falta una tarea de verify NUEVA): "
             f"{', '.join(inconclusive)}")
    return {"retested": len(ready), "passed": passed, "rotated": rotated,
            "inconclusive": inconclusive, "blocked": blocked, "unrun": unrun,
            "orphan": [p["task"].name for p in orphan]}


def _top_up() -> dict:
    """Step 2: keep ~QUEUE_FLOOR cases waiting for the dev agent."""
    have = I.awaiting_fix_count()
    if have >= QUEUE_FLOOR:
        _log(f"paso 2 · la cola ya tiene {have}/{QUEUE_FLOOR} casos esperando arreglo — no lanzo nada nuevo")
        return {"queue": have, "ran": 0}
    todo = _unrun_scenarios()
    if not todo:
        _log(f"paso 2 · cola en {have}/{QUEUE_FLOOR} pero NO quedan casos EJECUTABLES sin probar. "
             f"Los que quedan están bloqueados (credenciales del operador o capacidad sin construir): "
             f"`run.py --list --segment credentials` los enumera con su motivo.")
        return {"queue": have, "ran": 0, "exhausted": True}

    # One locale per batch: ZAELAR_LANGUAGE is process-wide, so a mixed batch would grade ES cases on English
    # replies (the artefact that nearly produced false bug reports on 2026-08-18).
    lang = todo[0].locale
    picked = [s for s in todo if s.locale == lang][:min(MAX_PER_TICK, QUEUE_FLOOR - have)]
    _log(f"paso 2 · cola en {have}/{QUEUE_FLOOR} · pruebo {len(picked)} caso(s) nuevo(s) "
         f"({lang}): {', '.join(s.id for s in picked)}")
    rc, out = _run(["--sandbox", "--locale", lang, "--scenario", "all",
                    "--start-at", picked[0].id, "--limit", str(len(picked))], timeout_s=60 * 60)
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        (LOG_PATH.parent / f"newground-stdout-{stamp}.log").write_text(out or "(sin salida)", encoding="utf-8")
    except Exception:
        pass
    _log(f"paso 2 · terminado rc={rc} · cola ahora {I.awaiting_fix_count()}/{QUEUE_FLOOR}")
    return {"queue": I.awaiting_fix_count(), "ran": len(picked)}


def main() -> int:
    ap = argparse.ArgumentParser(description="one cycle of the continuous use-case loop")
    ap.add_argument("--hours", type=float, default=0.0,
                    help="arm the loop for this many hours from now (writes the deadline, then ticks once)")
    ap.add_argument("--stop", action="store_true", help="disarm: every later tick becomes a no-op")
    ap.add_argument("--status", action="store_true", help="print the loop's state and exit")
    ap.add_argument("--retest-only", action="store_true",
                    help="step 1 ONLY (re-test what the dev agent answered), works with the loop disarmed and "
                         "never launches new cases from the catalog")
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

    # RETEST-ONLY: step 1 alone, and it does NOT require the loop to be armed. That is the point — the operator
    # stopped launching new cases until a shared fault is fixed (2026-08-19), but the re-test still has to fire
    # the moment the dev agent answers, and arming the loop would bring step 2 (top up the queue from the
    # catalog) back with it. It also stays SILENT when there is nothing pending: this runs every 5 minutes.
    if args.retest_only:
        if _runner_alive():
            _log("retest-only: ya hay una tanda corriendo — salto este turno")
            return 0
        pend = [p for p in I.scenarios_awaiting_verification(SC.registry()) if p["scenario"]]
        if not pend:
            print("no-op · nada que re-probar (ninguna tarea de verificación pendiente)")
            return 0
        _log(f"── RETEST-ONLY · {len(pend)} caso(s) pendiente(s) ──")
        r1 = _retest_pending()
        _log(f"── FIN RETEST-ONLY · re-probados {r1.get('retested', 0)} · {statusmod.summary_line()}")
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
