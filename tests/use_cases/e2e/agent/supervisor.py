"""Supervisor: the set NEVER STOPS. Chains use cases one at a time and cuts off anything that hangs.

Operator's instruction (2026-08-27): “the system must not stop and we should make the most of the time,” with an
explicit standard — *“we cannot spend ten minutes doing a search for a guitar on Amazon; the search is supposed
to take one minute, two or three at most.”*

ONE AT A TIME, and this is not a preference: there is **one browser** per set. Two rounds at once fight over
the same tab and both measure incorrectly — exactly the defect the harness itself reports as “2 workers for ONE
task.” So the cycle is: is something running? → yes: monitor it; no: launch the next one.

WHAT COUNTS AS HUNG, and why: we measure not DURATION but SILENCE. A legitimate round may
take time if things are happening (the operator accepted this: “if you have precise, observable control of every
movement, we can let it run longer”); what it cannot do is stop signaling. Two cutoffs, with the second because the
first is not enough:

  · SILENCE — the round's log does not grow for `HANG_S`. This catches a dead process, an unresponsive model, or
    a stuck browser. Cheap and without false positives: the runner prints every turn.
  · CEILING — the entire round exceeds `CAP_S`. It catches the opposite: one that does speak but gets nowhere,
    exactly the one that spent 21 minutes delivering zero cars.

When cutting it off, we RECORD WHY. A round killed by the supervisor is not the judge's verdict and cannot be
counted as one: it enters the journal as `hung`/`capped`, with its log, so readers know that this is a failure,
not a measurement.

What this file does NOT do: fix anything. It measures and chains; a human or agent reading `diario.jsonl` makes
the corrections. A supervisor that also touched the engine would be measuring itself.
"""
from __future__ import annotations

import hashlib as _hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[4]
_SALIDA = _RAIZ / "tests" / "runs" / "use_cases" / "supervisor"
_DIARIO = _SALIDA / "diario.jsonl"

#: No signal in the log for this long → hung. The runner prints every turn, so three silent minutes are
#: a failure, not slowness.
HANG_S = int(os.getenv("UC_HANG_S", "180"))
#: Ceiling for the entire round. Based on the operator's standard (a search takes 1–3 min), with room for a
#: conversation of ~20 turns on top.
CAP_S = int(os.getenv("UC_CAP_S", "720"))
#: Breathing room between rounds: lets the engine close tabs and release the browser before the next one.
PAUSA_S = int(os.getenv("UC_PAUSA_S", "20"))
#: Extension when the round has ALREADY reached the verdict. First measured with: `weekend-adventure-sports-bilbao`
#: (2026-08-27) hit the ceiling **inside `verifying mechanism`** — the conversation had ended, the
#: browser was no longer consuming resources, and only the report was missing. Killing it there wastes all twelve
#: minutes and leaves no measurement, exactly the opposite of the ceiling's purpose. The ceiling protects against
#: work that gets nowhere; the verdict DOES arrive, and it is what we came for.
VERIFICA_EXTRA_S = int(os.getenv("UC_VERIFICA_EXTRA_S", "300"))
#: Signals the runner prints when moving to the verdict phase. If they appear, the expensive part is done.
_EN_VEREDICTO = ("verifying mechanism", "judging")

#: What `run.stale_engine_refusal` prints when the set has old code. The guard does the right thing
#: —it REFUSES to measure— but then nobody restarts anything, and that is the defect: each subsequent round
#: refuses again in ~45 s, so the loop appears alive (the journal fills, scenarios rotate) while measuring NOTHING.
#: Measured on 2026-08-27: `search-buy-camera__es` was INFRA at 45 s and continued only because I was watching and
#: restarted it manually. With two agents pushing engine changes every ~20 min, that is a stopped loop disguised as a loop.
_PLATO_RANCIO = "no es el mismo codigo"


def _apunta(**fila) -> None:
    _SALIDA.mkdir(parents=True, exist_ok=True)
    fila["t"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with _DIARIO.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"[supervisor] {fila.get('escenario')} → {fila.get('resultado')} ({fila.get('segundos')}s)", flush=True)


def _sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_RAIZ,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


def plato_de(escenario: str) -> str:
    """Which SET this case belongs to. The ID suffix is the sole source: `__us` runs on the US set.

    `main()` did not pass a set, so the default `es` remained for EVERYTHING — and a San Francisco case was
    run by Marc, from Madrid, answering in Spanish inside an English brief. It does not fail: it measures, and
    measures a tester contradicting itself. It is the same family that on 2026-08-27 left 19 US scenarios
    responding with Spanish reality, invisible from outside because the round is infrastructure-green.
    """
    return "us" if escenario.endswith("__us") else "es"


def una_ronda(escenario: str, lab: str = "es", fresh: bool = True) -> dict:
    """Launches ONE round and monitors it. Returns the report, including the reason if it had to be cut off.

    `fresh=False` (CONTINUOUS mode, operator 2026-08-29): the set is NOT reset between cases — the memory
    of the agent survives, like a real person chaining tasks in the same session during their day."""
    _SALIDA.mkdir(parents=True, exist_ok=True)
    log = _SALIDA / f"{escenario}.log"
    sha, t0 = _sha(), time.time()
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.Popen(
            [sys.executable, "-m", "tests.use_cases.e2e.agent.run", "--lab", lab,
             "--scenario", escenario, "--rounds", "1"] + (["--fresh"] if fresh else []),
            cwd=_RAIZ, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)

    motivo, ultimo_tam, ultimo_cambio = "", -1, time.time()
    while True:
        if p.poll() is not None:
            break
        tam = log.stat().st_size if log.exists() else 0
        if tam != ultimo_tam:
            ultimo_tam, ultimo_cambio = tam, time.time()
        ahora = time.time()
        # Is it already at the verdict? Look only at the log TAIL: reading it all every three seconds is free I/O
        # multiplied over hours, and these two signals appear at the end by construction.
        _cerca = ""
        try:
            with log.open("rb") as fh:
                fh.seek(max(0, tam - 4096))
                _cerca = fh.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        _techo = CAP_S + (VERIFICA_EXTRA_S if any(x in _cerca for x in _EN_VEREDICTO) else 0)
        if ahora - ultimo_cambio > HANG_S:
            motivo = f"hung: {HANG_S}s sin una línea nueva en el log"
        elif ahora - t0 > _techo:
            motivo = f"capped: la ronda pasó de {_techo}s"
        if motivo:
            # The entire group: the runner has children (the set engine, the browser).
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:  # noqa: BLE001
                pass
            try:
                p.wait(timeout=20)
            except Exception:  # noqa: BLE001
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except Exception:  # noqa: BLE001
                    pass
            break
        time.sleep(3)

    segundos = int(time.time() - t0)
    cola = ""
    try:
        cola = log.read_text(encoding="utf-8", errors="replace")[-2500:]
    except Exception:  # noqa: BLE001
        pass
    resultado = motivo.split(":")[0] if motivo else _veredicto_de_cola(cola)
    parte = {"escenario": escenario, "resultado": resultado, "segundos": segundos, "sha": sha,
             "motivo": motivo, "log": str(log)}
    _apunta(**parte)
    # Deliberately outside the report sent to the journal: it is a signal for the loop, not a fact about the scenario,
    # and the journal is what the operator reads to decide where to work.
    return dict(parte, _rancio=(_PLATO_RANCIO in cola))


def _veredicto_de_cola(cola: str) -> str:
    """What happened to the round, read from what the runner printed. Deliberately OUTSIDE the function that runs
    the round: testing it there would require an entire set, and it decides based on a string.

    Four outcomes, none a nuance of another — each directs investigation to a different place:

    * **PASS/FAIL** — hubo medida.
    * **BLOQUEADO** (V2-448) — the case is for the FUTURE: its roadmap tasks remain pending, so the
      runner refuses to run it (operator rule, 2026-08-21) and exits in 3 s. Nothing is broken and there is
      nothing to fix today.
    * **INFRA** (V2-363) — the instrument broke. The runner also prints «PASSED 0/1» when the round ran
      completely and the JUDGE returned no JSON: 10.7 minutes of real browser time were recorded as FAIL in the
      journal, which is the list used to decide where to work.

    Order matters: BLOQUEADO comes BEFORE INFRA because a blocked case's tail contains no «PASSED» of any kind
    and would fall into the `else`, which is INFRA.
    """
    if "PASSED 1/1" in cola:
        return "PASS"
    if "no queda ningún caso conducible" in cola or "no se conducen" in cola:
        return "BLOQUEADO"
    if "INFRA" in cola or "el juez no devolvió JSON" in cola:
        return "INFRA"
    if "PASSED 0/1" in cola:
        return "FAIL"
    return "INFRA"


def _reinicia_plato(lab: str = "es") -> bool:
    """Takes the set down and brings it up so the current tree runs. `True` if it came back up.

    Preserves port, memory, and profile — it is the same pair of commands printed by the runner's own guard,
    not a second way to restart it.
    """
    for cual in ("down", "up"):
        try:
            r = subprocess.run([sys.executable, "-m", "tests.use_cases.lab", cual, lab],
                               cwd=_RAIZ, capture_output=True, text=True, timeout=180)
        except Exception as e:  # noqa: BLE001
            print(f"[supervisor] no pude {cual} el plató: {e}", flush=True)
            return False
        if cual == "up" and r.returncode != 0:
            print(f"[supervisor] el plató no volvió a levantarse: {(r.stderr or r.stdout)[-200:]}", flush=True)
            return False
    return True


def intercala(ids: list[str]) -> list[str]:
    """Alternates the two sets WITHIN a priority group, preserving each one's order.

    Priority (“broken first, never-measured next, passing cases last”) is what matters in the
    rotation and is not changed. What is fixed is that within each group the order came from the scoreboard's
    scoreboard, where the `__us` cases were grouped: measured on 2026-08-28, the first US case was in
    **position 21** of 132 — about two hours and three quarters of set time in. A loop that runs all night and
    never reaches half the catalog is not measuring that half, even if it has it in the list.

    Alternate, do not shuffle: shuffling would make consecutive passes incomparable, while rotation is
    precisely what makes passes comparable.
    """
    es = [x for x in ids if not x.endswith("__us")]
    us = [x for x in ids if x.endswith("__us")]
    fuera: list[str] = []
    for a, b in zip(es, us):
        fuera += [a, b]
    fuera += es[len(us):] + us[len(es):]      # the longer one finishes on its own
    return fuera


def rotacion() -> list[str]:
    """The order in which they are traversed, and order MATTERS because set time is the scarce resource.

    `UC_ROTACION` (comma-separated) always takes precedence — it is the control for focusing on a case while
    iterating on it. Without it, rotation comes from the SCOREBOARD (`status.json`), not the catalog: only ~32 of
    the catalog's 135 cases have a runner, and traversing the other 103 would waste the browser on nothing.

    Among those that run, **failures** come first, where there is something to gain; passing cases follow so a
    regression is visible without taking a broken case's turn. `capped` cases (missing a user credential with no
    way forward) stay OUT: the operator excluded them from the improvement loop on 2026-08-20 precisely so they
    would not create work nobody can close.
    """
    env = (os.getenv("UC_ROTACION") or "").strip()
    if env:
        return [x.strip() for x in env.split(",") if x.strip()]
    try:
        import json as _j
        d = _j.loads((_RAIZ / "tests" / "use_cases" / "status.json").read_text(encoding="utf-8"))
        filas = (d.get("scenarios") or {}).items()
        rotos = [k for k, v in filas if str(v.get("state")) in ("FAIL", "INFRA")]
        buenos = [k for k, v in filas if str(v.get("state")) == "PASS"]
        # V2-367 — those that HAVE a runner and have NEVER been measured. The scoreboard lists only what has run
        # at least once, so without this a new scenario is INVISIBLE to the loop FOREVER: nobody runs it, so it never
        # enters the scoreboard, so nobody runs it. Measured on 2026-08-27: 135 scenarios with runners, 32 on the
        # scoreboard — **103 outside the loop**, including the TWO multimedia ones (`play-music-and-build-playlist`,
        # `watch-a-video-not-listen-to-it`), meaning two entire product surfaces without a single measurement.
        # From outside this does not look like a gap: the scenario EXISTS, the catalog lists it, and the scoreboard
        # —where people look— does not say it is missing. Same family as “a test outside the map CLAIMS it ran.”
        try:
            # V2-448 — and EXCLUDE FUTURE cases. The runner refuses to run one whose roadmap tasks
            # remain pending (operator, 2026-08-21), so it exits in 3 s without measuring anything — but because it never
            # reaches the scoreboard, `nunca` selects it again on every pass, forever. Measured on
            # 2026-08-28: `repeat-a-finished-search` (pending V2-260) consumed a rotation turn and
            # left a false row in the journal. Same treatment as `capped`: work nobody can close today does not enter
            # the improvement loop. It returns only when its initiative unlocks it.
            from tests.use_cases.e2e.agent import segments as _G
            nunca = [x.id for x in _con_runner()
                     if x.id not in dict(filas) and not _G.blocked_by(x.id)]
        except Exception:  # noqa: BLE001 — un catálogo ilegible NO puede costar la rotación entera
            nunca = []
        if rotos or buenos or nunca:
            # Broken first (where there is something to gain and we already know where to look), NEVER MEASURED next
            # (new information, but each costs a full set round), and passing cases last so a regression is visible
            # without consuming anyone's turn.
            # EACH SET WITH ITS OWN PRIORITY QUEUE, alternating between the two.
            #
            # Interleaving WITHIN each group was not enough, as the figures showed: 25 ES rounds versus 7 US in
            # the first four hours of 24/7. ES has many more broken cases, so after exhausting the US cases in the
            # “broken” group, thirteen consecutive ES cases remained BEFORE the “never measured” group began
            # —where the 52 untouched US cases live—. Priority was respected, yet the operator still had no US data.
            #
            # Thus each set traverses broken → never → good independently, and they alternate turn by turn: priority
            # remains intact WITHIN each locale, where it has meaning, and neither can wait for the other to finish its list.
            cola_es = [x for x in rotos + nunca + buenos if not x.endswith("__us")]
            cola_us = [x for x in rotos + nunca + buenos if x.endswith("__us")]
            return intercala(cola_es + cola_us)
    except Exception:  # noqa: BLE001
        pass
    return ["search-buy-used-car"]


def _con_runner() -> list:
    """Scenarios that HAVE a runner, or an empty list if the catalog cannot be read.

    Kept separate so `rotacion()` continues using the known rotation if this fails: losing the rotation is worse
    than losing the never-measured cases.
    """
    try:
        from tests.use_cases.e2e.agent.scenarios import all_scenarios
        return list(all_scenarios())
    except Exception:  # noqa: BLE001
        return []


# ── V2-372: THE SUPERVISOR RELOADS ITSELF ─────────────────────────────────────────────────────────────
# A Python process does not reread its own file. This one had been running the code from 07:59 since 08:03,
# so TWO fixes made that same morning were inert without anything saying so:
# V2-363 (a harness failure is not a failing case — 09:42) and V2-367 (the 103 scenarios that had never
# run — 10:12). Measured: the `things-to-do-nearby-weekend__es` round was INFRA in its report —the judge
# returned no JSON after three attempts— and the journal recorded it as FAIL, exactly what V2-363 fixed three hours
# earlier. And rotation was still the 32-case one.
#
# What makes this SILENT is the asymmetry: `una_ronda` launches the round as a SUBPROCESS, so the runner, judge,
# scenarios, and entire engine DO reload each time. Only this file —the one that classifies the result and chooses
# the order— falls behind. From outside everything appears current, and the report even carries the `sha` of
# HEAD read at the start of the round: the journal CLAIMS to have measured a commit whose classifier was not loaded.
#
# This is the fourth instance of the same family (“a clean tree is not an up-to-date process”) and the first in
# which the party paying for it is the instrument used to decide where to work.
_FUENTE = Path(__file__).resolve()


def _huella() -> str:
    try:
        return _hashlib.sha256(_FUENTE.read_bytes()).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        return ""


def _fuente_utilizable() -> bool:
    """Does the new file at least COMPILE? Re-executing against a partially written file would kill the loop, and
    the loop cannot stop — it is the one requirement the operator has repeated. When in doubt, continue with the
    old code: measuring with something outdated is a defect; measuring nothing is worse."""
    try:
        compile(_FUENTE.read_text(encoding="utf-8"), str(_FUENTE), "exec")
        return True
    except Exception:  # noqa: BLE001
        return False


def _recargar_si_cambie(huella_inicial: str) -> None:
    """Between rounds —never halfway through one— restart with the new code. No-op if nothing changed."""
    if not huella_inicial or _huella() in ("", huella_inicial):
        return
    if not _fuente_utilizable():
        print("[supervisor] la fuente cambió pero NO compila — sigo con la cargada", flush=True)
        return
    _apunta(escenario="—", resultado="RECARGA", segundos=0, sha=_sha(),
            motivo=f"supervisor.py cambió ({huella_inicial} → {_huella()}); me reinicio con el código nuevo",
            log="")
    os.execv(sys.executable, [sys.executable, "-m", "tests.use_cases.e2e.agent.supervisor"])


def main(argv: list[str] | None = None) -> int:
    # The LAUNCH BATTERY (operator 2026-08-29): `--phase 1` limits rotation to the scope of the
    # production version (phases.py, operator boundary); `--continuo` keeps memory between
    # cases — a real person chaining tasks; `--vueltas N` stops after N passes (0 = endless).
    import argparse
    ap = argparse.ArgumentParser(prog="supervisor")
    ap.add_argument("--phase", type=int, default=0, help="limitar a la fase de lanzamiento (1|2); 0 = todas")
    ap.add_argument("--continuo", action="store_true",
                    help="no resetear el plató entre casos: la memoria sobrevive (persona continua)")
    ap.add_argument("--vueltas", type=int, default=0, help="parar tras N pasadas completas (0 = sin fin)")
    # `argv=None` (llamada programática/tests) = defaults; la CLI pasa sys.argv[1:] explícito.
    a = ap.parse_args(argv if argv is not None else [])
    orden = rotacion()
    if a.phase:
        from tests.use_cases.e2e.agent import phases as _ph
        orden = [x for x in orden if _ph.phase_of(x) == a.phase]
        if not orden:
            print(f"[supervisor] la fase {a.phase} no tiene casos en la rotación", flush=True)
            return 1
    _mia = _huella()
    print(f"[supervisor] {len(orden)} escenarios · hang={HANG_S}s cap={CAP_S}s · diario={_DIARIO} "
          f"· fuente {_mia} · HEAD {_sha()}"
          + (f" · FASE {a.phase}" if a.phase else "") + (" · CONTINUO (memoria viva)" if a.continuo else ""),
          flush=True)
    i = 0
    while True:
        if a.vueltas and i >= a.vueltas * len(orden):
            print(f"[supervisor] {a.vueltas} vuelta(s) completas — fin", flush=True)
            return 0
        esc = orden[i % len(orden)]
        i += 1
        try:
            # In continuous mode, ONLY the first round resets (the person's clean start); afterward the
            # memory is part of what is measured. The kwarg is passed only when it differs from the default: test
            # doubles (and any old caller) retain the (esc, lab) signature.
            _kw = {"fresh": False} if (a.continuo and i > 1) else {}
            parte = una_ronda(esc, plato_de(esc), **_kw)
            if parte.get("_rancio"):
                # ONCE only, and without a loop: if it is still stale after restarting, the round enters as INFRA and
                # move on to the next. Retrying until it works would turn a set that does not start into an
                # infinite loop that measures nothing — the same failure in another form.
                _apunta(escenario=esc, resultado="RECARGA-PLATO", segundos=0, sha=_sha(),
                        motivo="el plató corría código viejo; lo reinicio y repito la ronda", log="")
                if _reinicia_plato(plato_de(esc)):
                    una_ronda(esc, plato_de(esc))
        except Exception as e:  # noqa: BLE001 — el supervisor NUNCA muere por una ronda
            _apunta(escenario=esc, resultado="ERROR", segundos=0, sha=_sha(), motivo=str(e)[:200], log="")
        time.sleep(PAUSA_S)
        _recargar_si_cambie(_mia)


if __name__ == "__main__":
    import sys as _sys
    raise SystemExit(main(_sys.argv[1:]))
