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
import json
import sys
import time
import uuid

from . import config, driver as drivermod, judge as judgemod, probe_client, report as reportmod, scenarios as SC
from . import initiative as initiativemod
from . import llm as llmmod
from . import status as statusmod
from . import verify as verifymod
from . import watchdog as watchdogmod


def _run_scenario(scenario, *, ran_before: list[str] | None = None, sandboxed: bool = False,
                  provisional: str = "") -> dict:
    """`sandboxed` says whether the engine under test is a throwaway one. It decides whether the
    conversation is INGESTED into durable memory: in a sandbox there is nothing to protect and half the
    cases (remember/remind) cannot pass without the write happening, so it must be on; against the
    operator's live engine it stays off, because there the original reason still holds — a test
    conversation has no business in the operator's real long-term memory."""
    scenario_started_ms = time.time() * 1000
    session = f"use-cases-{scenario.id}-{uuid.uuid4().hex[:6]}"
    probe_client.reset(session)
    driver = drivermod.Driver(scenario)
    transcript: list[dict] = []
    mute_turns: list[int] = []
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
    # Wall clock at the start, so the prompt read below can be scoped to THIS scenario: a batch shares one
    # engine, and the turn rows of the previous case sit in the same table.
    started_at = time.time()

    def note(who: str, text: str) -> None:
        transcript.append({"who": who, "text": text, "at": round(time.time(), 2)})

    # ── siembra de memoria (solo casos de descubrimiento) ────────────────────────────────────────────────
    # Se manda por el probe con `ingest=True` en una sesión APARTE y se comprueba con un recall que aterrizó.
    # La sesión aparte es el punto: si las preferencias se dijeran en el mismo hilo, el agente las tendría en
    # la ventana conversacional y el caso ya no probaría memoria.
    seed_report: dict = {}
    if getattr(scenario, "memory_seed", None):
        seed_session = f"{session}-seed"
        probe_client.reset(seed_session)
        print(f"  ▸ sembrando {len(scenario.memory_seed)} preferencia(s) en memoria (sesión aparte)…")
        for line in scenario.memory_seed:
            try:
                probe_client.say(line, seed_session, execute=False, ingest=True)
            except Exception as e:
                print(f"    ✗ siembra falló: {e}")
        # El CORAZÓN de escritura es asíncrono a propósito (invariante: escribir puede ser lento). Se espera a
        # verlo en el recall en vez de dormir un número inventado — y si no llega, se dice.
        landed, waited = False, 0.0
        probe = scenario.seed_probe_query or (scenario.memory_seed[0][:40] if scenario.memory_seed else "")
        while probe and waited < 45.0:
            hits = probe_client.recall(probe, k=8)
            if hits:
                landed = True
                break
            time.sleep(3.0)
            waited += 3.0
        seed_report = {"sown": len(scenario.memory_seed), "landed": landed, "waited_s": round(waited, 1),
                       "probe": probe}
        print(f"    {'✓' if landed else '⚠️'} siembra {'verificada' if landed else 'NO verificada'} "
              f"en recall tras {waited:.0f}s")
        probe_client.reset(session)      # la petición real arranca con la ventana LIMPIA

    utterance = driver.opening()
    note("tester", utterance)
    print(f"  tester  · {utterance}")

    # Extra turns granted only to keep a LIVE browser task's result reachable — see the grace block below.
    grace_left = 3
    for turn in range(max(1, scenario.turns)):
        res = probe_client.say(utterance, session, execute=(scenario.channel == "probe"),
                               ingest=sandboxed)
        reply_text = llmmod._as_text(res.get("reply")).strip()
        # A MUTE TURN IS NOT AN AGENT REFUSING TO HELP. The text channel resolves its provider through
        # `spec_from_config()` and never consults the failover chain, so with the titular model out of funds
        # EVERY turn comes back empty (the engine team pointed this out on 2026-08-20, and it explains the
        # `(sin respuesta)` lines already seen in `renew-gym`). Uncounted, the judge scores a provider outage as
        # product inattention — the same mistake `search_health` exists to prevent.
        if not reply_text:
            mute_turns.append(turn)
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
            # GRACE TURNS: do not close the conversation while its browser task is STILL ALIVE. Measured on
            # 2026-08-20 in `hotel-under-15-days`: the worker extracted «Exe Sevilla Macarena, 65 €» with a URL
            # at 19:45:29, the last turn came 16 s later saying "sigo pendiente", and the task was killed at
            # 19:45:55 — so the round ended as a race between the turn budget and the browser, which measures my
            # clock rather than the product. The grace removes MY confound without excusing anything: if the
            # result still never arrives, the finding is cleaner, not softer.
            if grace_left and scenario.expected_signals and verifymod.navegador_task_is_live():
                grace_left -= 1
                print(f"  ⏳ turno de gracia ({grace_left} más): la tarea de navegador sigue viva, no cierro "
                      f"la conversación con el resultado en vuelo")
                time.sleep(15.0)
                utterance = driver.reply(nudge=pending_nudge)
                note("tester", utterance)
                print(f"  tester  · {utterance}")
                continue
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
    mech = verifymod.mechanism_report(all_events, scenario.expected_signals, concurrency, scheduled,
                                      forbidden_signals=getattr(scenario, 'forbidden_signals', []))
    # WHAT ACTUALLY LANDED IN THE AGENDA, read from the engine. Looked up ALWAYS, even when the case says
    # nothing about appointments: it costs one request and it avoids the class of error that cost two rounds
    # and a false accusation against the engine team ("zero appointments persisted" about an agenda that had
    # the appointment inside). `None` means "could not look" and does NOT mean "empty" — the judge is handed
    # that difference explicitly.
    # WHAT THE AGENT HAD IN FRONT OF IT, read from its own turns (see `verify.prompt_context`). This is the
    # answer to the question that cost three retractions and one whole investigation by another agent today:
    # shown-and-ignored is conduct, never-shown is plumbing, and without this they look identical.
    if config.SANDBOX_DB:
        # READ AFTER THE ROUND, NOT DURING IT. Every column below is a snapshot, and a snapshot taken while
        # the engine is still writing has already misreported three different findings (see
        # `verify.wait_for_quiescence`). This costs seconds and buys the difference between «it failed» and
        # «it had not finished».
        mech["quiescence"] = verifymod.wait_for_quiescence(config.SANDBOX_DB)
        try:
            mech["prompt_context"] = verifymod.prompt_context(config.SANDBOX_DB, since=started_at)
        except Exception as e:
            mech["prompt_context_error"] = str(e)[:200]
        # The memory's CANONICAL language, read rather than assumed — see `verify.memory_language`. It is not
        # necessarily the language of the conversation, and a Spanish case whose memory canon was English is
        # exactly how a preference that WAS in the prompt got reported as missing.
        # WHAT THE ENGINE PUSHED, next to what the prompt merely rendered — the two delivery paths measured
        # side by side (see `verify.proactive_notes`).
        try:
            notes = verifymod.proactive_notes(config.SANDBOX_DB, since=started_at)
            mech["proactive_notes"] = notes
            mech["note_coverage"] = verifymod.note_coverage(mech.get("prompt_context") or [], notes)
            # A PROMPT THAT CONTRADICTS ITSELF voids the obedience reading of that turn, so it is measured
            # first and reported apart (see `verify.prompt_contradictions`).
            mech["prompt_contradictions"] = verifymod.prompt_contradictions(mech.get("prompt_context") or [])
            # WHAT THE USER SAW WHILE WAITING (V2-227 ámbito B). The headline is the longest silence,
            # not the count: a burst of phases followed by four minutes of nothing is the complaint.
            mech["progress"] = verifymod.progress_phases(config.SANDBOX_DB, since=started_at)
            mech["surfaces"] = verifymod.declared_surfaces(config.SANDBOX_DB, since=started_at)
            mech["sheet_timing"] = verifymod.sheet_timing(config.SANDBOX_DB, since=started_at)
        except Exception as e:
            mech["proactive_notes_error"] = str(e)[:200]
        # WHAT THE WORKER ACHIEVED and whether any of it was SAID — the gap this whole case is about.
        try:
            wo = verifymod.worker_outcome(config.SANDBOX_DB, since=started_at)
            offered = verifymod.offered_to_brain(config.SANDBOX_DB, since=started_at)
            mech["offered"] = offered
            # Delivery is judged against what the BRAIN was handed, never against what the browser scraped:
            # the note is built with a positional cut, so the two lists routinely differ.
            wo["delivered"] = verifymod.was_delivered(
                [{"title": x} for x in offered.get("titles") or []], transcript)
            wo["n_offered"] = offered.get("n_offered", 0)
            mech["worker_outcome"] = wo
            # HOW MANY WORKERS SURVIVED, and WHAT THE SEARCH BROUGHT BACK. Both channels were invisible to
            # this report until 2026-08-21, when an audit found it was reading 490 of 1291 events — and both
            # were carrying the answer to the round that was failing.
            mech["worker_health"] = verifymod.worker_health(config.SANDBOX_DB, since=started_at)
            mech["search_returns"] = verifymod.search_returns(config.SANDBOX_DB, since=started_at)
            # WHY the dead ones died. A worker that errors emits nothing saying why, so this crosses the
            # store with the engine's own log — the cross-reference that found the cause of a whole family.
            mech["worker_deaths"] = verifymod.worker_deaths(config.SANDBOX_DB, since=started_at)
        except Exception as e:
            mech["worker_outcome_error"] = str(e)[:200]
        mech["memory_language"] = verifymod.memory_language(config.SANDBOX_DB)
        # The locale travels with it so the judge can compare: `en` is CORRECT for a US case and a mismatch
        # only for an ES one. Warning on the language alone would cry wolf on half the catalogue.
        mech["locale"] = scenario.locale
    # THE TESTER LEAVING ITS OWN ROLE is a harness fault, and the round has to say so. Measured 2026-08-20 in
    # `weekend-adventure-sports-bilbao__es`: the "tester" turn delivered the assistant's answer — surf schools
    # with prices and URLs — and zaelar sensibly replied that the message looked cut off. Grading that as a
    # product defect grades the harness. `driver.reply` retries once; a flip that survives makes this INFRA,
    # because zaelar's reaction to a nonsense turn says nothing about zaelar.
    if getattr(driver, "role_flips", 0):
        mech["role_flips"] = driver.role_flips
        if driver.role_flips > 1:
            run_data["crashed"] = (f"el DRIVE se salió de su papel {driver.role_flips} vez/veces y no volvió "
                                   f"ni tras reintentarlo: la ronda no mide al producto")
    if mute_turns:
        mech["mute_turns"] = {"turns": mute_turns, "n": len(mute_turns)}
    try:
        mech["agenda_meetings"] = probe_client.widget_rows("agenda", "meetings")
    except Exception as e:
        mech["agenda_meetings"] = None
        mech["agenda_error"] = str(e)

    run_data = {"transcript": transcript, "mechanism_report": mech, "watchdog_log": watchdog_log}
    # WHAT THE ENGINE ALREADY REMEMBERS FROM THIS BATCH. A batch shares ONE sandbox and `hard_reset()`
    # deliberately does NOT wipe memory (that needs the process to die — SQLite is in use — and would restart
    # the engine, see its docstring). So from the third case onward the agent legitimately recalls the previous
    # cases' topics, and the judge was scoring that as a product defect: `renew-gym-membership__es` was marked
    # down on 2026-08-20 for "mezclando dominios (Netflix/Teatro)" — Netflix and Teatro being exactly the two
    # cases that ran before it. A fresh install cannot do that, so the finding was about our harness.
    # Stamped into the evidence rather than left to be discovered case by case, same as `search_health`.
    if ran_before:
        run_data["memory_carryover"] = list(ran_before)
    if seed_report:
        run_data["memory_seed"] = seed_report
    print("  judging…")
    try:
        verdict = judgemod.judge(scenario, run_data)
    except Exception:
        # THE CONVERSATION IS ALREADY MEASURED; only the verdict is missing. Losing an eight-minute round
        # because a provider is down is a harness bug, and this one bit three times on the same case:
        # `book-hotel-night-known__es` came back INFRA on 2026-08-20 at 09:xx, 11:xx and 18:41 — the third
        # time with the judge retry visibly firing ("retrying in 8s", "retrying in 16s") and all three
        # attempts eating a 504. Three driven conversations thrown away for a missing HTTP call.
        # So the run is PARKED on disk and can be judged later without re-driving it (`--judge-pending`).
        # The exception still propagates: the round is honestly INFRA until somebody judges it.
        _park_for_later(scenario, run_data, provisional=provisional)
        raise

    # WHO drove this conversation. Normally the titular model, but DRIVE fails over to another provider when
    # the titular runs out of funds (`llm.call`) — and a row measured with a different instrument is not
    # comparable with the earlier ones, so the instrument travels WITH the measurement instead of staying in
    # the run's log. Same reasoning for `code`: WHICH engine code produced this row (see `config.code_stamp`).
    return {"scenario": scenario.id, "tier": scenario.tier, "channel": scenario.channel,
            "run": run_data, "verdict": verdict, "drive_model": llmmod.drive_model(),
            "code": config.code_stamp(), "machine": config.machine_stamp()}


PENDING_DIR = config.RUNS_DIR / "pending"


def _park_for_later(scenario, run_data: dict, *, provisional: str = "") -> None:
    """Save a driven-but-unjudged round so the conversation is not lost with the judge call.

    `provisional` is carried into the file so a round driven on a moving tree is still flagged when its judge
    finally comes back up, however clean the tree is by then.
    """
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        path = PENDING_DIR / f"{scenario.id}-{time.strftime('%Y%m%d-%H%M%S', time.localtime())}.json"
        path.write_text(json.dumps({"scenario": scenario.id, "tier": scenario.tier,
                                    "channel": scenario.channel, "run": run_data,
                                    "drive_model": llmmod.drive_model(), "code": config.code_stamp(),
                                    "provisional": provisional or None},
                                   ensure_ascii=False, default=str), encoding="utf-8")
        print(f"  ⏸ ronda GUARDADA sin juzgar → {path}\n"
              f"     (los datos están medidos; júzgala luego con --judge-pending, sin volver a conducirla)")
    except Exception as e:
        print(f"  ⚠️ no pude guardar la ronda sin juzgar: {e}")


def _judge_pending() -> int:
    """Judge every parked round and fold it into the ledger. Deletes only what it managed to judge."""
    files = sorted(PENDING_DIR.glob("*.json")) if PENDING_DIR.exists() else []
    if not files:
        print("no hay rondas guardadas sin juzgar")
        return 0
    print(f"▶ {len(files)} ronda(s) guardada(s) sin juzgar")
    done, failed = [], []
    for f in files:
        try:
            saved = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ✗ {f.name}: ilegible ({e})")
            failed.append(f.name)
            continue
        scn = next((s for s in SC.all_scenarios() if s.id == saved.get("scenario")), None)
        if scn is None:
            print(f"  ✗ {f.name}: el escenario «{saved.get('scenario')}» ya no existe en el catálogo")
            failed.append(f.name)
            continue
        try:
            verdict = judgemod.judge(scn, saved["run"])
        except Exception as e:
            print(f"  ✗ {scn.id}: el juez sigue caído ({str(e)[:80]}) — la ronda SIGUE guardada")
            failed.append(f.name)
            continue
        res = {**saved, "verdict": verdict}
        # The flag travels with the SAVED round, not with this invocation's flags: a round parked by a dirty
        # run stays provisional however clean the tree is by the time its judge comes back up.
        statusmod.record([res], sandboxed=True, provisional=saved.get("provisional") or "")
        print(f"  ✓ {scn.id}: overall {verdict.get('overall')} — juzgada sin reconducirla")
        f.unlink(missing_ok=True)
        done.append(scn.id)
    print(f"\n{len(done)} juzgada(s), {len(failed)} sigue(n) esperando")
    return 0 if done or not failed else 1


def _run_batch(chosen: list, *, sandboxed: bool, args_no_file: bool = False,
               verify_tasks: dict | None = None, stop_after_failures: int = 0,
               failures_already: int = 0, provisional: str = "") -> int:
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
        # AISLAR los casos entre sí. Una tanda comparte UN sandbox (arrancar uno por caso costaría ~16s de boot
        # + prewarm cada vez), pero compartir el motor NO puede significar compartir el TRABAJO: medido el
        # 2026-08-19, en `find-theatre-tickets__es` el juez vio que «el sistema intentaba reservar un
        # restaurante irrelevante» — era la tarea viva de `restaurant-tonight-madrid`, el caso anterior del
        # mismo lote. Ese caso no se midió a sí mismo. `probe_client.reset()` no bastaba: limpia la ventana
        # conversacional y deja vivos los workers, las tareas y el canvas.
        if results:
            try:
                probe_client.hard_reset()
                time.sleep(2.0)          # el kill de grupo y el cierre del canvas no son instantáneos
                print("  ▸ motor reseteado (sin trabajo ni canvas del caso anterior)")
            except Exception as e:
                print(f"  ⚠️ no pude resetear el motor entre casos: {e} — este caso puede arrastrar "
                      f"trabajo del anterior")
        try:
            results.append(_run_scenario(scenario, ran_before=[r["scenario"] for r in results],
                                          sandboxed=sandboxed, provisional=provisional))
        except Exception as e:  # one scenario's infra hiccup must not lose the whole batch's report
            print(f"  ✗ scenario crashed: {e}")
            results.append({"scenario": scenario.id, "tier": scenario.tier, "channel": scenario.channel,
                            "run": {"transcript": [], "mechanism_report": {}, "watchdog_log": [],
                                    "crashed": str(e)},
                            "verdict": {"scores": {}, "overall": None, "findings": [], "improvements": [],
                                       "veredicto": f"INFRA: {e}"}})
        # PERSIST THIS SCENARIO NOW, not at the end of the batch. `record()` folds one batch into the ledger
        # and only touches the scenarios in it ("a batch of one must never look like it invalidated the other
        # four"), so a call per scenario is safe and it is what makes a batch INTERRUPTIBLE. Measured the hard
        # way on 2026-08-20: a 6-case verify batch was cut off after ~12 minutes, having already driven and
        # JUDGED `cancel-subscription-before-charge__es` — and the ledger still showed the previous run,
        # because the single `record()` at the end never happened. Every verdict the batch had earned was
        # thrown away, including the one that finally showed the CORRECT behaviour (admitting it cannot log
        # into the operator's account instead of pretending). In an unattended loop, batches run for tens of
        # minutes and an interruption is not exotic: it is a sleeping laptop, a killed tick, a crash.
        try:
            statusmod.record(results[-1:], sandboxed=sandboxed, provisional=provisional)
        except Exception as e:
            print(f"  ⚠️ no pude anotar el veredicto de {scenario.id} en el marcador: {e}")

        last = (results[-1].get("verdict") or {}).get("overall")
        if last is not None and last < statusmod.PASS_THRESHOLD:
            failures += 1
            if stop_after_failures:
                print(f"           ↳ fallando: {failures}/{stop_after_failures}")

    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    report_path = reportmod.build(results, stamp, config.RUNS_DIR)
    print(f"\n✓ report → {report_path}")
    # NO second `record()` here: every scenario already wrote its own row as it finished (see the call inside
    # the loop). Re-recording the whole batch would rewrite each row's `last_run` to the batch's END time,
    # which is not when that case ran — and that field is load-bearing: it is what tells a later reader which
    # verdicts predate an environment change (used on 2026-08-20 to retire the six measured against an engine
    # in the wrong language). A summary line is still printed, from the ledger.
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
    #
    # EXCEPT when the run produced NO verdict (INFRA): then it did NOT run. The conversation never happened —
    # the DNS died, the provider ran out of funds, the sandbox never came up — so the task's request is still
    # PENDING and closing it would strand the case until a human noticed and wrote a new one by hand. Measured
    # cost of getting this wrong: a DNS outage on 2026-08-19 12:17 took out 5 of 7 re-tests in one batch and
    # burned all five verify tasks with it. Retrying is the right default here precisely because nothing on the
    # engine side changed, and an INFRA attempt is cheap (0 turns, seconds) — the note in the initiative keeps
    # it visible if it starts happening every tick.
    def _has_verdict(sid: str) -> bool:
        return any(r["scenario"] == sid and (r.get("verdict") or {}).get("overall") is not None for r in results)

    for sid, tasks in (verify_tasks or {}).items():
        if not any(r["scenario"] == sid for r in results):
            continue
        for task in tasks:
            if not _has_verdict(sid):
                print(f"  ↩︎ dejo ABIERTA la tarea de verificación {task.name}: la corrida murió sin veredicto "
                      f"(INFRA), así que lo que pedía sigue sin hacerse")
                continue
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
        # UN caso, UNA corrida — aunque lo pidan VARIAS tareas. El agente que arregla responde el mismo caso
        # en dos arreglos distintos (T434 y T438 para `find-theatre-tickets__es`, 2026-08-20), y sin esto la
        # lista llevaba el caso dos veces: se condujo la conversación entera DOS veces (~4 min del turno
        # tirados) y se escribió la MISMA ronda dos veces en el paraguas, que hace que la evidencia cuente el
        # doble de intentos de los que hubo.
        #
        # Y el mapa de tareas era `{caso: tarea}`: de las dos, una se cerraba y la otra se quedaba en `next`
        # para siempre, pidiendo un re-test que ya se hizo. Ahora es {caso: [tareas]} y se cierran TODAS.
        chosen, verify_tasks = _verify_batch(pend, registry)
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
    if args.segment:
        from . import segments as G
        chosen = [s for s in chosen if G.group_of(s.id) == args.segment]
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
                          verify_tasks=verify_tasks, provisional=_provisional(args),
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
    return _sandbox_groups(chosen, args, verify_tasks=verify_tasks)


def _sandbox_groups(chosen: list, args: argparse.Namespace, *, verify_tasks: dict | None = None) -> int:
    """A memory-SEEDED case never shares a sandbox with another seeded one.

    `hard_reset()` between cases kills work, tasks and canvas — deliberately NOT memory, which is durable by
    design. So seeded preferences accumulate, and on 2026-08-20 that manufactured a contradiction no real user
    would ever produce: `weekend-plan-barcelona__es` seeded "loves climbing, especially via ferratas" at 17:59,
    `weekend-adventure-sports-bilbao__es` seeded "has a fear of heights" at 18:06, and the second case was then
    graded on a passive block that served both as equals. The memory agent found the four pills alive at once,
    two of them the same fact in two languages. The case measured the mechanism honestly and the product not at
    all, which is the worst kind of round: it looks like a finding.

    Cheapest correct fix: one sandbox per seeded case (~16s of boot each), unseeded ones keep sharing. Grouping
    rather than always-one-per-case, because boot+prewarm per case would triple a long walk for no gain where
    there is nothing to contaminate.
    """
    groups: list[list] = []
    for s in chosen:
        if getattr(s, "memory_seed", None):
            groups.append([s])                        # alone: its seed must not meet anyone else's
        elif groups and not getattr(groups[-1][0], "memory_seed", None):
            groups[-1].append(s)
        else:
            groups.append([s])
    if len(groups) > 1:
        seeded = sum(1 for g in groups if len(g) == 1 and getattr(g[0], "memory_seed", None))
        print(f"▲ {len(groups)} sandboxes for this batch: {seeded} case(s) seed memory and each needs its own "
              f"(a previous case's seeded preferences survive hard_reset and would be judged as this "
              f"persona's).")
    rc = 0
    rounds = max(1, int(getattr(args, "rounds", 1) or 1))
    first_stamp = None
    for n in range(rounds):
        if first_stamp is not None:
            moved = tree_moved_refusal(first_stamp, config.current_head())
            if moved:
                print(moved)
                return rc | 3
            print(f"↻ ronda {n + 1} de {rounds} (mismo código: {first_stamp.get('sha')})")
        for g in groups:
            rc |= _sandbox_batch(g, args, verify_tasks=verify_tasks)
        first_stamp = first_stamp or config.code_stamp()
    return rc


def tree_moved_refusal(stamp: dict, head_now: str) -> str:
    """The message that stops round N of a pair when HEAD moved after round 1, or "" to carry on.

    Rounds are run in pairs on purpose: in this case three rounds produced the same grade with three
    different mechanisms underneath, so one round proves nothing. But a pair is only a pair if both halves
    ran the SAME code — and on 2026-08-20 a shell loop launched two rounds across a commit boundary, which
    is nobody's fault and still ruins the comparison. The clean-tree guard does not catch it: the tree is
    clean on both sides of a commit.
    """
    was, now = (stamp or {}).get("sha") or "", head_now or ""
    if not was or not now or was == now:
        return ""
    return (f"\u2717 el motor pas\u00f3 de {was} a {now} entre rondas de la misma tanda. Dos rondas de "
            f"c\u00f3digo distinto no son un par: se para aqu\u00ed y se relanza la tanda entera sobre "
            f"{now}.")


def seed_provider_chain(ws) -> str:
    """Dale al sandbox la CADENA DE PROVEEDORES del operador, y nada más de su config.

    El sandbox arranca con un workspace nuevo, así que `config/v2.json` sale vacío, así que la cadena cae a
    la de por defecto — que en self-host es **solo el titular**. El 2026-08-21, con el titular sin saldo,
    eso salió por el log como «SIN RELEVO disponible» y yo lo reporté como un defecto del motor: el cerebro
    era el único componente sin red. Era falso. La config real del operador tiene dos escalones
    (`deepseek-directo` → `aimlapi-failover`) y AIMLAPI estaba vivo. Lo que medí fue mi propio vacío.

    Copiar SOLO `fast.providers` es deliberado: la cadena es infraestructura, y medir el producto con una
    cadena que el producto no usa mide otra cosa. Todo lo demás de su config se queda fuera —memoria,
    widgets, preferencias— porque eso sí es del operador y contaminaría la ronda; ya nos costó una noche
    descubrir que un widget suyo decidía la ciudad de un encargo.

    Devuelve lo que se sembró, para que el informe pueda decirlo. Una ronda medida con otra cadena que la
    de ayer no es comparable con la de ayer.
    """
    try:
        import json as _json
        from pathlib import Path as _P
        # `config/v2.json` está GITIGNORADO, así que un worktree de medición no lo tiene: buscar relativo a
        # `__file__` devolvía vacío y la siembra no ocurría en silencio — el mismo fallo mudo que esto
        # arregla. Se acepta una ruta explícita al motor de verdad, y si no, la de al lado del código.
        import os as _os
        cands = []
        if _os.getenv("ZAELAR_REAL_ENGINE"):
            cands.append(_P(_os.environ["ZAELAR_REAL_ENGINE"]) / "config" / "v2.json")
        cands.append(_P(__file__).resolve().parents[3].parent / "config" / "v2.json")
        src = next((c for c in cands if c.exists()), None)
        if src is None:
            return ""
        chain = ((_json.loads(src.read_text(encoding="utf-8")) or {}).get("fast") or {}).get("providers")
        if not chain:
            return ""
        # UN ESCALÓN MÁS, con el modelo del TITULAR sobre el endpoint del failover. No es un apaño para
        # medir a toda costa: es lo más fiel. El titular del operador es `deepseek-v4-pro` y su failover
        # salta a `deepseek-v4-flash`, o sea que en cuanto releva **cambia el cerebro bajo medición** —
        # y una ronda contra flash no es comparable con las de ayer contra pro. Medido el 2026-08-21,
        # además, flash daba timeout a los 75 s en AIMLAPI mientras pro contestaba en 18: el escalón
        # configurado apuntaba justo al que no servía. Este va DETRÁS de los suyos, así que no les quita
        # el turno: solo evita que una noche entera se pierda cuando los dos primeros caen.
        chain = list(chain)
        titular_model = str((chain[0] or {}).get("model") or "")
        broker = next((x for x in chain[1:] if "aimlapi" in str(x.get("base_url") or "")), None)
        if titular_model and broker and titular_model not in str(broker.get("model") or ""):
            chain.append({**broker, "name": "arnes-mismo-modelo",
                          "model": f"deepseek/{titular_model}",
                          "plan": "el arnés: mismo cerebro que el titular, sobre el broker"})
        dst = _P(ws) / "config"
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "v2.json").write_text(_json.dumps({"fast": {"providers": chain}}, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        return " → ".join(str(x.get("name") or "?") for x in chain)
    except Exception:
        return ""


def brain_preflight(*, timeout: float = 210.0) -> str:
    """CAN THE BRAIN SPEAK AT ALL? Returns "" when it can, or the refusal to print when it cannot.

    On 2026-08-21 the whole provider chain ran out at once — DeepSeek answered HTTP 402 «Insufficient
    Balance» and the log said «sin cuota hasta el 21 Aug 03:02 · SIN RELEVO disponible» — and every zaelar
    turn came back EMPTY. Two full rounds were driven and judged before anyone noticed: the first was filed
    1/1/1/1/1 FAIL on a case nobody had exercised, and the second was a case that had PASSED twice an hour
    earlier. Roughly fifteen minutes of machine time to learn something one turn answers.

    El plazo es LARGO a propósito (210 s). Con la cadena tocada, un turno puede gastar 75 s solo en agotar
    un escalón que da timeout antes de llegar al que sí contesta, y un canario impaciente declara muerto un
    cerebro que estaba a un escalón de hablar — que es exactamente el error que este canario existe para no
    cometer, cometido por el canario.

    So one throwaway turn is spent before the batch. It costs a couple of seconds against the sandbox that
    is booting anyway, and it separates «the product failed» from «nothing could think» before a single
    score is written — which is the same distinction INFRA exists for, moved earlier so it costs nothing.
    """
    try:
        out = probe_client.say("di solo: ok", session=f"preflight-{int(time.time())}",
                               execute=False, ingest=False, timeout=timeout)
    except Exception as e:
        return (f"✗ el motor no contesta al canal de prueba ({type(e).__name__}: {str(e)[:120]}).\n"
                f"   No es un fallo del caso: no se ha medido nada.")
    reply = str((out or {}).get("reply") or "").strip()
    if reply:
        return ""
    return ("✗ EL CEREBRO NO PUEDE HABLAR: un turno de prueba ha vuelto VACÍO antes de empezar.\n"
            "   Casi siempre es la cadena de proveedores agotada (saldo o cuota). Mira el log del sandbox:\n"
            "   «Insufficient Balance», «sin cuota hasta …», «SIN RELEVO disponible».\n"
            "   NO se mide: una ronda así apunta un fallo de producto que en realidad es una factura.")


def _provisional(args) -> str:
    """WHY this round cannot be banked as a measurement, or "" when it can.

    `--allow-dirty` is the deliberate escape hatch for measuring work-in-progress, and it is legitimate. What
    is not legitimate is the row it leaves behind looking exactly like a clean one: the board then counts a
    number nobody stands behind. So the flag travels with the score.
    """
    if getattr(args, "allow_dirty", False):
        return "corrida con --allow-dirty: el arbol se movia, el numero no cuenta como medicion"
    return ""


def dirty_tree_refusal(stamp: dict, *, allow_dirty: bool = False) -> str:
    """The message that stops a round from being measured on a MOVING tree, or "" to go ahead.

    The stamp already RECORDED this (`n_dirty`) and recording was not enough: on 2026-08-20 a round booted
    while the engine agent was mid-edit on two files, the number it produced contradicted the round before
    it, and neither could be trusted — half an hour of machine time for a datum that had to be thrown away.
    Noting a confound afterwards does not stop you spending the round on it, so the refusal happens BEFORE
    the boot. `allow_dirty` is for the fixing agent measuring their own work-in-progress on purpose.

    `stamp["dirty"]` already excludes `tests/`: the harness editing itself does not change the engine under
    test, so a harness commit in flight must never block a measurement.
    """
    if allow_dirty or not (stamp or {}).get("dirty"):
        return ""
    return (f"\u2717 el motor tiene {stamp['n_dirty']} fichero(s) sin commitear: "
            f"{', '.join(stamp['dirty'][:6])}\n"
            f"   Una ronda medida a mitad de una edicion no se puede comparar con ninguna otra. Espera a "
            f"que el arbol este limpio, o pasa --allow-dirty si mides tu propio cambio a posta.")


def _sandbox_batch(chosen: list, args: argparse.Namespace, *, verify_tasks: dict | None = None) -> int:
    from tests.platform.sandbox_engine import preferred_port, sandbox_engine
    # The workspace is KEPT, under a timestamped dir, and the port is a stable-by-preference one — both so
    # the operator can actually WATCH this run: open the URL below while it works and the ◷ visor / the
    # observability API show this agent's flows, tasks and events. A fresh workspace per batch means a fresh
    # `config/identity.json`, i.e. each batch is a NEW install/user_id in observability rather than mixing
    # into the operator's own session. Ephemeral+random would be tidier but invisible, and invisible defeats
    # the point of running these at all.
    lang = "es" if (chosen and chosen[0].locale == "es") else "en"
    # STAMP BEFORE BOOTING, and this is not a nicety — a lazy stamp LIES. Measured on itself 2026-08-20: the
    # sandbox booted at 19:37:07, the fixing agent committed the obedience fix at 19:39:41, the stamp was first
    # taken when the round finished, and the ledger row therefore named a commit the running server had never
    # loaded. An instrument that misattributes a round is worse than no instrument: I was one message away from
    # telling them their fix had been measured. The server reads the tree at `Popen`, so the stamp has to be
    # taken here, on the same side of the boot.
    stamp = config.code_stamp()
    config.machine_stamp()
    refusal = dirty_tree_refusal(stamp, allow_dirty=getattr(args, "allow_dirty", False))
    if refusal:
        print(refusal)
        raise SystemExit(3)
    ws = config.RUNS_DIR / "sandbox" / time.strftime("%Y%m%d-%H%M%S", time.localtime())
    _chain = seed_provider_chain(ws)
    if _chain:
        print(f"  ▸ cadena de proveedores sembrada desde la config real: {_chain}")
    print(f"▶ booting an isolated sandbox engine (own DB/port/workspace, fresh user_id, "
          f"ZAELAR_LANGUAGE={lang})…")
    with sandbox_engine(keep_workspace=ws, port=preferred_port(43918),
                        extra_env={"ZAELAR_LANGUAGE": lang}) as eng:
        print(f"✓ sandbox up at {eng.base_url}")
        print(f"  ▸ WATCH IT LIVE: {eng.base_url}  (flows/events/tasks of this test agent)")
        print(f"  ▸ observability API: {eng.base_url}/api/observability/flows?limit=30")
        print(f"  ▸ workspace kept for inspection: {eng.workspace}")
        config.ZAELAR_URL = eng.base_url
        # The turn rows are not served by `/api/observability/events` (that route is pinned to
        # `topic = 'observer'`), so the prompt read goes to the sandbox's own DB. Only set in sandbox mode: a
        # live-engine run has no business poking at the operator's database.
        config.SANDBOX_DB = str(eng.workspace / "memory" / "_data" / "sandbox.db")
        # ONE THROWAWAY TURN before the batch: see `brain_preflight`. Exit 4 keeps it apart from the
        # dirty-tree refusal (3) so a caller can tell «I must not measure» from «I cannot measure».
        _pf = brain_preflight()
        if _pf:
            print(_pf)
            raise SystemExit(4)
        try:
            return _run_batch(chosen, sandboxed=True, args_no_file=args.no_file,
                              verify_tasks=verify_tasks, provisional=_provisional(args),
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


def _verify_batch(pend: list[dict], registry: dict) -> tuple[list, dict]:
    """One case, ONE run — even when SEVERAL tasks ask for it. Returns (cases_to_run, {case: [tasks]}).

    The fixing agent answers the same case in two separate fixes (T434 and T438 both asked for
    `find-theatre-tickets__es`, 2026-08-20), and building the batch per TASK put the case in the list twice:
    the whole conversation was driven twice (~4 minutes of the window thrown away) and the SAME round was
    written twice into the shared umbrella, which makes the initiative's evidence count twice the attempts
    that happened.

    The task map used to be `{case: task}`, so of the two only ONE was closed and the other stayed `next` for
    ever asking for a re-test that had already run. Hence the list per case.
    """
    chosen, tasks = [], {}
    for pv in pend:
        sid = pv.get("scenario")
        if not sid or sid not in registry:
            continue
        if sid not in tasks:
            chosen.append(registry[sid])
            tasks[sid] = []
        tasks[sid].append(pv["task"])
    return chosen, tasks


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
    ap.add_argument("--segment", choices=["completable", "credentials", "capability"],
                    help="only cases in this segment (see segments.py). `completable` is the list that can be "
                         "carried out end to end today — the default batch to run")
    ap.add_argument("--limit", type=int, help="stop after N scenarios (walk the catalog in batches)")
    ap.add_argument("--start-at", help="skip ahead to this scenario id, then continue in order")
    ap.add_argument("--list", action="store_true", help="print the selectable scenarios and exit")
    ap.add_argument("--stop-after-failures", type=int, default=0, metavar="N",
                    help="stop the walk once N cases are FAILING on the scoreboard (INFRA never counts). "
                         "Counts failures already recorded by earlier batches, not just this one")
    ap.add_argument("--no-file", action="store_true",
                    help="do NOT open a MeshKore initiative/task for a failure (measure only)")
    ap.add_argument("--rounds", type=int, default=1, metavar="N",
                    help="run the selection N times as ONE batch; stops if the engine's HEAD moves between "
                         "rounds, because two rounds of different code are not a pair")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="measure even with uncommitted engine files (for the fixing agent's own work-in-progress)")
    ap.add_argument("--judge-pending", action="store_true",
                    help="judge the rounds parked on disk because the judge was unavailable, and fold them "
                         "into the scoreboard — without driving the conversation again")
    args = ap.parse_args()
    if args.judge_pending:
        raise SystemExit(_judge_pending())
    if args.list:
        # HONOURS the filters. It used to dump the whole catalog whatever was asked, which made
        # `--segment completable --list` print the blocked cases too — a listing that contradicts the run it is
        # supposed to preview is worse than no listing.
        from . import segments as G
        rows = SC.all_scenarios()
        if args.segment:
            rows = [s for s in rows if G.group_of(s.id) == args.segment]
        if args.tier:
            rows = [s for s in rows if s.tier in args.tier]
        if args.locale:
            rows = [s for s in rows if s.locale == args.locale]
        hand_ids = {x.id for x in SC.SCENARIOS}
        for s in sorted(rows, key=lambda x: (x.tier, x.locale, x.id)):
            seg = G.segment_of(s.id)
            mark = {G.COMPLETABLE: "✅", G.CREDENTIALS: "🔑", G.CAPABILITY: "🚧"}.get(seg.group if seg else "", "❓")
            hand = " (hand-written)" if s.id in hand_ids else ""
            why = f"  ← {seg.missing}" if seg and seg.missing else ""
            print(f"{mark} t{s.tier}  {s.locale}  {s.id}{hand}{why}")
        print(f"\n{len(rows)} de {len(SC.all_scenarios())} escenarios"
              + (f" · segmento {args.segment}" if args.segment else ""))
        sys.exit(0)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
