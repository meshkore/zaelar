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

    def note(who: str, text: str) -> None:
        transcript.append({"who": who, "text": text, "at": round(time.time(), 2)})

    utterance = driver.opening()
    note("tester", utterance)
    print(f"  tester  · {utterance}")

    for turn in range(max(1, scenario.turns)):
        res = probe_client.say(utterance, session, execute=(scenario.channel == "probe"))
        reply_text = (res.get("reply") or "").strip()
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
    mech = verifymod.mechanism_report(all_events, scenario.expected_signals, concurrency)

    run_data = {"transcript": transcript, "mechanism_report": mech, "watchdog_log": watchdog_log}
    print("  judging…")
    verdict = judgemod.judge(scenario, run_data)
    return {"scenario": scenario.id, "tier": scenario.tier, "channel": scenario.channel,
            "run": run_data, "verdict": verdict}


def _run_batch(chosen: list, *, sandboxed: bool) -> int:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for scenario in chosen:
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

    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    report_path = reportmod.build(results, stamp, config.RUNS_DIR)
    print(f"\n✓ report → {report_path}")
    statusmod.record(results, sandboxed=sandboxed)
    print(f"✓ scoreboard → {statusmod.BOARD_PATH} ({statusmod.summary_line()})")

    overalls = [r["verdict"].get("overall") for r in results if r["verdict"].get("overall") is not None]
    passed = sum(1 for o in overalls if o >= 4)
    print(f"PASSED {passed}/{len(results)} (overall>=4)")
    return 0 if passed == len(results) else 1


def run(args: argparse.Namespace) -> int:
    if args.scenario == "all":
        chosen = SC.SCENARIOS
    else:
        if args.scenario not in SC.BY_ID:
            print(f"unknown scenario {args.scenario!r} — known: {sorted(SC.BY_ID)}", file=sys.stderr)
            return 2
        chosen = [SC.BY_ID[args.scenario]]

    if not args.sandbox:
        print(f"▲ running against the LIVE engine at {config.ZAELAR_URL} — its memory, widgets and running "
              f"tasks are the operator's. Use --sandbox for an isolated one.")
        return _run_batch(chosen, sandboxed=False)

    # ISOLATED: boot a throwaway engine (own port, own DB, own workspace, own logs) and point the whole
    # suite at it by rewriting config.ZAELAR_URL — probe_client reads that attribute per call, so no other
    # module needs to know. Equivalent to exporting TESTER_ZAELAR_URL, without asking the caller to.
    from tests.platform.sandbox_engine import sandbox_engine
    print("▶ booting an isolated sandbox engine (own DB/port/workspace)…")
    with sandbox_engine() as eng:
        print(f"✓ sandbox up at {eng.base_url} (workspace {eng.workspace})")
        config.ZAELAR_URL = eng.base_url
        try:
            return _run_batch(chosen, sandboxed=True)
        finally:
            print(f"  sandbox engine log tail:\n{eng.log_tail(12)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="zaelar use-case tester — driver + watchdog + verify + judge")
    ap.add_argument("--scenario", default="all", help="'all' or a scenario id")
    ap.add_argument("--sandbox", action="store_true",
                    help="boot an ISOLATED engine (own DB/port/workspace) instead of using the live one — "
                         "never touches the operator's memory, widgets or running tasks")
    sys.exit(run(ap.parse_args()))


if __name__ == "__main__":
    main()
