"""Orchestrator for the use-case tester — drives one or all scenarios against a running zaelar over the
text/probe channel, verifies real mechanism (not just the transcript), judges, and writes a report.

Run (zaelar up, `make run`):
    ./.venv/bin/python -m tests.use_cases.e2e.agent.run --scenario hotel-under-15-days
    ./.venv/bin/python -m tests.use_cases.e2e.agent.run                      # all scenarios

Synchronous and independent: plain HTTP to zaelar's probe + observability APIs. No LiveKit, no asyncio —
the text channel doesn't need either, which is part of why it's the default for this suite.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid

from . import config, driver as drivermod, judge as judgemod, probe_client, report as reportmod, scenarios as SC
from . import initiative as initiativemod
from . import llm as llmmod
from . import status as statusmod
from . import verify as verifymod
from . import watchdog as watchdogmod


def _run_scenario(scenario) -> dict:
    scenario_started_ms = time.time() * 1000
    session = f"use-cases-{scenario.id}-{uuid.uuid4().hex[:6]}"
    probe_client.reset(session)
    driver = drivermod.Driver(scenario)
    transcript: list[dict] = []
    watchdog_log: list[dict] = []
    pending_nudge = ""
    # Multi-flow scenarios need concurrency measured WHILE it happens (see ConcurrencyTracker's docstring):
    # a post-hoc event dump can show N tasks existed but never that two overlapped in time.
    concurrency = verifymod.ConcurrencyTracker() if scenario.concurrent_tasks else None
    # Snapshot the scheduler BEFORE the first turn. Jobs are durable by design and outlive a conversation, so
    # an absolute count would credit this case with a reminder an earlier case in the same batch created —
    # only the DELTA can claim "this conversation left a trigger behind".
    try:
        jobs_before = probe_client.scheduled_jobs()
    except Exception:
        jobs_before = []

    def note(who: str, text: str) -> None:
        transcript.append({"who": who, "text": text, "at": round(time.time(), 2)})

    utterance = driver.opening()
    note("tester", utterance)
    print(f"  tester  · {utterance}")

    for turn in range(max(1, scenario.turns)):
        res = probe_client.say(utterance, session, execute=(scenario.channel == "probe"))
        reply_text = llmmod._as_text(res.get("reply")).strip()
        note("zaelar", reply_text)
        print(f"  zaelar  · {reply_text[:160]}")
        driver.hears(reply_text)

        if concurrency is not None:
            concurrency.sample(at_turn=turn)
            live = concurrency.samples[-1] if concurrency.samples else {}
            print(f"           ↳ tareas vivas: {live.get('n_live', '?')} "
                  f"(máx {concurrency.max_concurrent}, {len(concurrency.seen)} distintas)")

        if driver.done:
            break

        # The watchdog's grounding: for a multi-flow run the live TASK REGISTRY is the right truth (three
        # workers grinding away normally must not read as "stuck"); for a single-task run it's the browser
        # task's own state.
        mech_hint = ""
        if concurrency is not None:
            mech_hint = concurrency.hint()
        elif scenario.expected_signals:
            mech_hint = verifymod.live_navegador_snapshot(scenario_started_ms)
        verdict = watchdogmod.evaluate(scenario, transcript, mech_hint)
        if verdict["action"] != "continue":
            watchdog_log.append(verdict)
            print(f"  [watchdog] {verdict['health']}/{verdict['action']}: {verdict['reason']}")
        if verdict["action"] == "abandon":
            break
        pending_nudge = verdict.get("nudge_text", "") if verdict["action"] == "nudge" else ""

        if turn == scenario.turns - 1:
            break
        utterance = driver.reply(nudge=pending_nudge)
        note("tester", utterance)
        print(f"  tester  · {utterance}")

    if scenario.expected_signals:
        print("  verifying mechanism (this may wait for a background worker/browser task)…")
    # The observability session_id is a server-wide, one-at-a-time concept (see `current_session_id()`'s
    # docstring) that spans the engine's whole uptime, not just this scenario — so it's ALSO filtered to
    # events at/after `scenario_started_ms`, or a prior unrelated task in the same live session could donate a
    # false "worker"/"widget" signal to a scenario that never actually triggered one itself.
    if concurrency is not None:
        concurrency.sample(at_turn=-1)      # final read: what was still in flight when the talking stopped
    live_session_id = probe_client.current_session_id()
    all_events = [e for e in probe_client.session_events(live_session_id)
                  if (e.get("ts_ms") or 0) >= scenario_started_ms]
    try:
        jobs_after = probe_client.scheduled_jobs()
    except Exception:
        jobs_after = None
    scheduled = verifymod.scheduled_report(jobs_before, jobs_after) if jobs_after is not None else None
    mech = verifymod.mechanism_report(all_events, scenario.expected_signals, concurrency, scheduled)

    run_data = {"transcript": transcript, "mechanism_report": mech, "watchdog_log": watchdog_log}
    print("  judging…")
    verdict = judgemod.judge(scenario, run_data)
    return {"scenario": scenario.id, "tier": scenario.tier, "channel": scenario.channel,
            "run": run_data, "verdict": verdict}


def _run_batch(chosen: list, *, sandboxed: bool, args_no_file: bool = False,
               verify_tasks: dict | None = None, stop_after_failures: int = 0,
               failures_already: int = 0) -> int:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    # Stop the walk once there is enough to work on (operator, 2026-08-18: "cuando tengas 10 fallando, para —
    # habrá mucho que hacer"). Counting only sub-threshold verdicts, never INFRA: a crashed harness is not a
    # use-case failure and must not consume the budget. `failures_already` carries the count from earlier
    # batches, since the whole point is a budget over the WALK, not per batch.
    failures = failures_already
    for scenario in chosen:
        if stop_after_failures and failures >= stop_after_failures:
            print(f"\n■ parando el walk: {failures} casos fallando (tope --stop-after-failures "
                  f"{stop_after_failures}). Quedan {len(chosen) - len(results)} escenarios de esta tanda sin "
                  f"correr — se retoman con --start-at {scenario.id}")
            break
        print(f"\n▶ scenario: {scenario.id} (tier {scenario.tier}, {scenario.locale}, {scenario.channel})")
        try:
            results.append(_run_scenario(scenario))
        except Exception as e:  # one scenario's infra hiccup must not lose the whole batch's report
            print(f"  ✗ scenario crashed: {e}")
            results.append({"scenario": scenario.id, "tier": scenario.tier, "channel": scenario.channel,
                            "run": {"transcript": [], "mechanism_report": {}, "watchdog_log": [],
                                    "crashed": str(e)},
                            "verdict": {"scores": {}, "overall": None, "findings": [], "improvements": [],
                                       "veredicto": f"INFRA: {e}"}})
        last = (results[-1].get("verdict") or {}).get("overall")
        if last is not None and last < statusmod.PASS_THRESHOLD:
            failures += 1
            if stop_after_failures:
                print(f"           ↳ fallando: {failures}/{stop_after_failures}")

    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    report_path = reportmod.build(results, stamp, config.RUNS_DIR)
    print(f"\n✓ report → {report_path}")
    statusmod.record(results, sandboxed=sandboxed)
    print(f"✓ scoreboard → {statusmod.BOARD_PATH} ({statusmod.summary_line()})")

    # FILE each real failure as a MeshKore initiative + task (one workspace per use case, appended to on
    # re-test). Operator's rule: the harness measures and files, it does not patch. INFRA verdicts are
    # skipped deliberately — a crashed harness or a network timeout is not a use-case bug and would send the
    # fixing agent chasing nothing.
    rounds: dict[str, int | None] = {}
    workspaces: dict[str, dict] = {}
    if not args_no_file:
        by_id = {s.id: s for s in chosen}
        for r in results:
            v = r.get("verdict") or {}
            overall = v.get("overall")
            if overall is None or overall >= statusmod.PASS_THRESHOLD:
                continue
            scn = by_id.get(r["scenario"])
            if scn is None:
                continue
            filed = initiativemod.file_failure(r, scenario=scn, sandboxed=sandboxed)
            if filed.get("error"):
                print(f"  ⚠️ no pude archivar la iniciativa de {r['scenario']}: {filed['error']}")
            elif filed.get("created"):
                print(f"  📋 iniciativa NUEVA → {filed['initiative'].name}  ·  tarea → {filed['task'].name}")
            else:
                print(f"  📋 ronda {filed['round']} añadida a {filed['initiative'].name}")
            rounds[r["scenario"]] = filed.get("round")
            if filed.get("initiative"):
                workspaces[r["scenario"]] = {
                    "initiative": str(filed["initiative"].relative_to(initiativemod.ENGINE)),
                    "task": str(filed["task"].relative_to(initiativemod.ENGINE))
                    if filed.get("task") else "",
                }

    # Point the board AT the workspaces just filed, so "which cases fail?" and "where do I work on them?" are
    # answered in the same place instead of requiring knowledge of the naming convention.
    statusmod.attach_workspaces(workspaces)

    # Close every verify task we honoured — pass OR fail. The task asked "run this again", and it did run;
    # leaving it `next` on a failure would make the next --verify batch re-run it forever without anyone having
    # changed anything in between. A case that still fails continues in its initiative, which is the workspace.
    for sid, task in (verify_tasks or {}).items():
        if any(r["scenario"] == sid for r in results):
            if initiativemod.close_verification(task, round_no=rounds.get(sid)):
                print(f"  ✅ tarea de verificación cerrada → {task.name}")
            else:
                print(f"  ⚠️ no pude cerrar la tarea de verificación {task.name}")

    overalls = [r["verdict"].get("overall") for r in results if r["verdict"].get("overall") is not None]
    passed = sum(1 for o in overalls if o >= 4)
    print(f"PASSED {passed}/{len(results)} (overall>=4)")
    return 0 if passed == len(results) else 1


def run(args: argparse.Namespace) -> int:
    # LINE-buffer stdout. A batch of these scenarios runs for the better part of an hour and the operator is
    # meant to be able to follow it (that is why the sandbox prints its WATCH IT LIVE urls at all) — but the
    # moment this is piped to a file or a log, Python switches to 4-8KB block buffering and the transcript
    # arrives in silent lumps, so an hour-long run looks indistinguishable from a hung one.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    registry = SC.registry()
    ordered = SC.all_scenarios()
    verify_tasks: dict[str, object] = {}
    if args.verify:
        # The RETURN half of the handoff contract: a fixing agent that changed something leaves a
        # `*-uc-<slug>-verify.md` task with `status: next`, and this assembles the re-test batch from exactly
        # those. Without it the contract was one-directional — we filed the failure and nothing on our side
        # ever picked the answer up, so "you can re-test now" depended on a human remembering.
        pend = initiativemod.scenarios_awaiting_verification(registry)
        unresolved = [p["slug"] for p in pend if not p["scenario"]]
        if unresolved:
            print(f"⚠️ tareas de verificación cuyo escenario ya no existe (¿renombrado?): "
                  f"{', '.join(unresolved)}", file=sys.stderr)
        chosen = [registry[p["scenario"]] for p in pend if p["scenario"]]
        verify_tasks = {p["scenario"]: p["task"] for p in pend if p["scenario"]}
        if not chosen:
            print("no hay ninguna tarea de verificación pendiente — nada que re-probar")
            return 0
        print(f"▶ re-probando {len(chosen)} caso(s) a petición de una tarea de verificación: "
              f"{', '.join(s.id for s in chosen)}")
    elif args.scenario == "all":
        chosen = ordered
    elif args.scenario == "handwritten":
        chosen = SC.SCENARIOS
    else:
        if args.scenario not in registry:
            print(f"unknown scenario {args.scenario!r} — {len(registry)} known; "
                  f"use --list to see them", file=sys.stderr)
            return 2
        chosen = [registry[args.scenario]]

    if args.tier:
        chosen = [s for s in chosen if s.tier in args.tier]
    if args.locale:
        chosen = [s for s in chosen if s.locale == args.locale]
    if args.limit:
        chosen = chosen[:args.limit]
    if args.start_at:
        ids = [s.id for s in chosen]
        if args.start_at not in ids:
            print(f"--start-at {args.start_at!r} is not in the selected set", file=sys.stderr)
            return 2
        chosen = chosen[ids.index(args.start_at):]
    if not chosen:
        print("no scenarios selected", file=sys.stderr)
        return 2

    if not args.sandbox:
        print(f"▲ running against the LIVE engine at {config.ZAELAR_URL} — its memory, widgets and running "
              f"tasks are the operator's. Use --sandbox for an isolated one.")
        return _run_batch(chosen, sandboxed=False, args_no_file=args.no_file,
                          verify_tasks=verify_tasks,
                          stop_after_failures=args.stop_after_failures,
                          failures_already=statusmod.failing_count() if args.stop_after_failures else 0)

    # ISOLATED: boot a throwaway engine (own port, own DB, own workspace, own logs) and point the whole
    # suite at it by rewriting config.ZAELAR_URL — probe_client reads that attribute per call, so no other
    # module needs to know. Equivalent to exporting TESTER_ZAELAR_URL, without asking the caller to.
    # LANGUAGE FIDELITY (found 2026-08-18, first sandboxed batch): every ES scenario came back answered in
    # ENGLISH. Not a product bug in itself — a fresh sandbox workspace has no language chosen, and the engine
    # deliberately boots in English ("arranque idiomático", langs.DEFAULT_LANG="en") until the first sentence
    # is detected. That detection did NOT fire over the probe channel, so an ES case was being graded on an
    # English conversation and the judge (correctly) marked it down for it. Measuring the wrong thing.
    #
    # Language is process-wide by design — `voice/engine/core/langs.py::current_code()` reads ZAELAR_LANGUAGE
    # and the probe consults the same global, so an es case and a us case CANNOT share one engine (CASES.md
    # §"Running ES vs US" already documented this and left it to whoever wired the first batch: this is it).
    # So: one sandbox PER LOCALE, pinned explicitly, run back to back.
    locales = sorted({s.locale for s in chosen})
    if len(locales) > 1:
        rc = 0
        for loc in locales:
            print(f"\n═══ locale {loc}: {sum(1 for s in chosen if s.locale == loc)} scenarios "
                  f"(separate sandbox — language is process-wide) ═══")
            sub = argparse.Namespace(**{**vars(args), "locale": loc})
            rc |= _sandbox_batch([s for s in chosen if s.locale == loc], sub,
                                 verify_tasks=verify_tasks)
        return rc
    return _sandbox_batch(chosen, args, verify_tasks=verify_tasks)


def _sandbox_batch(chosen: list, args: argparse.Namespace, *, verify_tasks: dict | None = None) -> int:
    from tests.platform.sandbox_engine import preferred_port, sandbox_engine
    # The workspace is KEPT, under a timestamped dir, and the port is a stable-by-preference one — both so
    # the operator can actually WATCH this run: open the URL below while it works and the ◷ visor / the
    # observability API show this agent's flows, tasks and events. A fresh workspace per batch means a fresh
    # `config/identity.json`, i.e. each batch is a NEW install/user_id in observability rather than mixing
    # into the operator's own session. Ephemeral+random would be tidier but invisible, and invisible defeats
    # the point of running these at all.
    lang = "es" if (chosen and chosen[0].locale == "es") else "en"
    ws = config.RUNS_DIR / "sandbox" / time.strftime("%Y%m%d-%H%M%S", time.localtime())
    print(f"▶ booting an isolated sandbox engine (own DB/port/workspace, fresh user_id, "
          f"ZAELAR_LANGUAGE={lang})…")
    with sandbox_engine(keep_workspace=ws, port=preferred_port(43918),
                        extra_env={"ZAELAR_LANGUAGE": lang}) as eng:
        print(f"✓ sandbox up at {eng.base_url}")
        print(f"  ▸ WATCH IT LIVE: {eng.base_url}  (flows/events/tasks of this test agent)")
        print(f"  ▸ observability API: {eng.base_url}/api/observability/flows?limit=30")
        print(f"  ▸ workspace kept for inspection: {eng.workspace}")
        config.ZAELAR_URL = eng.base_url
        try:
            return _run_batch(chosen, sandboxed=True, args_no_file=args.no_file,
                              verify_tasks=verify_tasks,
                              stop_after_failures=args.stop_after_failures,
                              failures_already=statusmod.failing_count() if args.stop_after_failures else 0)
        finally:
            leaked = eng.new_widget_dirs()
            if leaked:
                # Not deleted on purpose — see sandbox_engine's leak note. Printed so it's a visible,
                # deliberate cleanup decision for the operator instead of silent repo litter.
                print(f"\n⚠️ widget folders written into the REAL engine/widgets/ by this run "
                      f"(generated widget CODE is not workspace-isolated): {', '.join(leaked)}\n"
                      f"   review and remove them if they were only test artifacts.")
            print(f"  sandbox engine log tail:\n{eng.log_tail(12)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="zaelar use-case tester — driver + watchdog + verify + judge")
    ap.add_argument("--scenario", default="all",
                    help="'all' (119 scenarios: hand-written + derived), 'handwritten', or a scenario id")
    ap.add_argument("--verify", action="store_true",
                    help="re-test exactly the cases a fixing agent asked for (a `*-uc-*-verify.md` task with "
                         "status: next), then close those tasks — the return half of the handoff")
    ap.add_argument("--sandbox", action="store_true",
                    help="boot an ISOLATED engine (own DB/port/workspace) instead of using the live one — "
                         "never touches the operator's memory, widgets or running tasks")
    ap.add_argument("--tier", type=int, nargs="*", help="only these difficulty tiers (e.g. --tier 1 2)")
    ap.add_argument("--locale", choices=["es", "us"], help="only this locale")
    ap.add_argument("--limit", type=int, help="stop after N scenarios (walk the catalog in batches)")
    ap.add_argument("--start-at", help="skip ahead to this scenario id, then continue in order")
    ap.add_argument("--list", action="store_true", help="print the selectable scenarios and exit")
    ap.add_argument("--stop-after-failures", type=int, default=0, metavar="N",
                    help="stop the walk once N cases are FAILING on the scoreboard (INFRA never counts). "
                         "Counts failures already recorded by earlier batches, not just this one")
    ap.add_argument("--no-file", action="store_true",
                    help="do NOT open a MeshKore initiative/task for a failure (measure only)")
    args = ap.parse_args()
    if args.list:
        for s in SC.all_scenarios():
            hand = " (hand-written)" if s.id in {x.id for x in SC.SCENARIOS} else ""
            print(f"{s.tier}  {s.locale}  {s.id}{hand}")
        sys.exit(0)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
