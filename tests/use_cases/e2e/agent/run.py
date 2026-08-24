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


class ScenarioCrash(RuntimeError):
    """A scenario died mid-conversation — but the turns that DID happen are already paid for.

    Until 2026-08-23 the crash handler in `_run_batch` recorded `transcript: []`: a run that timed out on
    turn 6 lost all five real turns from the record, and the INFRA row said nothing about what the engine
    was doing when it died. This carries both up to the handler."""

    def __init__(self, err: str, *, transcript: list | None = None, autopsy: dict | None = None) -> None:
        super().__init__(err)
        self.transcript = list(transcript or [])
        self.autopsy = dict(autopsy or {})


def engine_autopsy(err: str) -> dict:
    """Answer the operator's first three questions BEFORE giving up, instead of leaving them to a human.

    Measured the omission on 2026-08-23, `cheapest-monitor`: the verdict said «INFRA: timed out» and nothing
    else, while the engine's own log ended in `Fetching 5 files… jina-reranker` — the whole diagnosis (the
    memory reranker downloading 1.1 GB on the event loop) sat one `tail` away and took half an hour of manual
    process-sampling to rediscover. The harness holds the answer at crash time; it must print it.

    Three cheap probes, all fail-soft — an autopsy error must never mask the original crash:
      · is the engine ALIVE (answers /api/status), WEDGED (listens but never answers), or DEAD (refused)?
      · the last lines of the engine's own log (lab: `logs/engine.log` · sandbox: `logs/sandbox-engine.log`),
        derived from `config.SANDBOX_DB` the same way `verify.py` already does.
    """
    out: dict = {"error": (err or "")[:300]}
    import urllib.request
    try:
        req = urllib.request.Request(config.ZAELAR_URL.rstrip("/") + "/api/status",
                                     headers={"User-Agent": "zaelar-uc-autopsy"})
        with urllib.request.urlopen(req, timeout=5.0) as r:
            r.read(200)
        out["engine"] = "VIVO (/api/status responde) — el fallo fue del turno o del tester, no del motor"
    except Exception as e2:
        s = str(e2).lower()
        if "refused" in s or "errno 61" in s:
            out["engine"] = "MUERTO (conexión rechazada) — el proceso del motor no está escuchando"
        elif "timed out" in s or "timeout" in s:
            out["engine"] = ("CLAVADO (escucha pero /api/status no contesta en 5 s) — event loop bloqueado; "
                             "la última línea del log suele decir en qué")
        else:
            out["engine"] = f"ilocalizable ({str(e2)[:120]})"
    try:
        from pathlib import Path
        if config.SANDBOX_DB:
            logs = Path(config.SANDBOX_DB).resolve().parents[2] / "logs"
            for name in ("engine.log", "sandbox-engine.log"):
                p = logs / name
                if not p.exists():
                    continue
                with p.open("rb") as f:            # tail, never the whole file: engine logs grow to MBs
                    f.seek(0, 2)
                    f.seek(max(0, f.tell() - 65536))
                    chunk = f.read().decode("utf-8", "replace")
                lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
                out["log"] = str(p)
                out["log_tail"] = lines[-5:]
                break
    except Exception as e3:
        out["log_error"] = str(e3)[:120]
    return out


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
    driver = drivermod.Driver(scenario, persona_name=config.PERSONA_NAME)
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
        try:
            res = probe_client.say(utterance, session, execute=(scenario.channel == "probe"),
                                   ingest=sandboxed)
        except Exception as e:
            # The engine-side turn died. Autopsy NOW, while the state that killed it is still there, and
            # carry the turns already driven — see ScenarioCrash/engine_autopsy.
            raise ScenarioCrash(f"turno {turn + 1}: {e}", transcript=transcript,
                                autopsy=engine_autopsy(str(e))) from e
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
            # …Y CONTRA EL ÚLTIMO TURNO, que es lo que separa «no entregó nunca» de «llegó tarde». `sheet_timing`
            # se medía desde V2-227 y NO LO LEÍA NADIE — ni el juez ni el informe. Medido en la tanda del
            # 2026-08-24: tres casos entregaron en el turno 9 de 10 porque la hoja se llena a los 130-220 s y la
            # conversación dura ~120; el juez, sin este dato, escribió «tuvo resultados y no los entregó» en dos
            # de ellos. La distinción no es de matiz: una manda a arreglar la conducta y la otra la LATENCIA.
            mech["sheet_timing"]["last_turn_ms"] = (transcript[-1].get("at") or 0) * 1000 if transcript else None
            _fr, _lt = mech["sheet_timing"].get("first_result_ms"), mech["sheet_timing"].get("last_turn_ms")
            mech["sheet_timing"]["after_last_turn_s"] = (
                round((_fr - _lt) / 1000.0, 1) if (_fr and _lt) else None)
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
            # …Y CUÁNTOS DE ELLOS HACÍAN LO MISMO. «4 lanzados» se lee como concurrencia sana; cuatro
            # workers sobre el MISMO encargo es una factura por cuatro y una pantalla llena de tarjetas.
            mech["duplicate_errands"] = verifymod.duplicate_errands(config.SANDBOX_DB, since=started_at)
            mech["search_returns"] = verifymod.search_returns(config.SANDBOX_DB, since=started_at)
            # WHY the dead ones died. A worker that errors emits nothing saying why, so this crosses the
            # store with the engine's own log — the cross-reference that found the cause of a whole family.
            mech["worker_deaths"] = verifymod.worker_deaths(config.SANDBOX_DB, since=started_at)
        except Exception as e:
            mech["worker_outcome_error"] = str(e)[:200]
        mech["memory_language"] = verifymod.memory_language(config.SANDBOX_DB)
        # WHICH backend served the recalls. `hash`/`fastembed` means semantic recall was off for the
        # whole round — a confound on every memory-dependent case, and one that fails QUIET: it looks
        # like an agent that did not remember, not like an instrument that could not.
        mech["embeddings"] = verifymod.embeddings_backend(config.SANDBOX_DB)
        # The locale travels with it so the judge can compare: `en` is CORRECT for a US case and a mismatch
        # only for an ES one. Warning on the language alone would cry wolf on half the catalogue.
        mech["locale"] = scenario.locale
    # THE TESTER LEAVING ITS OWN ROLE is a harness fault, and the round has to say so. Measured 2026-08-20 in
    # `weekend-adventure-sports-bilbao__es`: the "tester" turn delivered the assistant's answer — surf schools
    # with prices and URLs — and zaelar sensibly replied that the message looked cut off. Grading that as a
    # product defect grades the harness. `driver.reply` retries once; a flip that survives makes this INFRA,
    # because zaelar's reaction to a nonsense turn says nothing about zaelar.
    # ⚠️ EL AVISO SE ANOTA APARTE Y SE PLIEGA ABAJO, y no es un detalle de estilo: esto escribía en `run_data`
    # TREINTA Y SIETE LÍNEAS ANTES de que `run_data` existiera, así que la única rama que existe para decir «la
    # ronda no mide al producto» reventaba con un `UnboundLocalError` — y la ronda salía INFRA con el texto de
    # una excepción de Python en lugar del motivo. Medido el 2026-08-24 12:35 en `search-buy-camera__es`:
    # «INFRA: cannot access local variable 'run_data' where it is not associated with a value», 0 turnos, sin
    # transcript y sin informe de mecanismo. O sea que el camino escrito para reconocer una avería del arnés
    # era, él mismo, una avería del arnés — y no había corrido nunca.
    crashed = ""
    if getattr(driver, "role_flips", 0):
        mech["role_flips"] = driver.role_flips
        if driver.role_flips > 1:
            crashed = (f"el DRIVE se salió de su papel {driver.role_flips} vez/veces y no volvió "
                       f"ni tras reintentarlo: la ronda no mide al producto")
    # …and a SWEEP of what actually ended up in the transcript, which is not the same question. The counter
    # above only sees flips the live guard caught; a line that slipped every face, or one the retry accepted
    # on the second attempt, reaches the judge with nothing marking it. Measured 2026-08-23 in round 6 of
    # `cheapest-monitor`: an assistant-voiced tester line («Sí, Marc, le he mirado las reseñas…») was read by
    # the judge — reasonably, from the content — as zaelar's, and filed as one of the round's three [alta]
    # blockers. The `TESTER`/`ZAELAR` labels were right there in the prompt and the content overrode them.
    # So the flip is named line by line rather than left for the judge to infer from a label.
    #
    # Y LA SEÑAL QUE NO ES DE REDACCIÓN: la persona NO PUEDE saber los nombres de los candidatos. Los produjo
    # nuestro worker y viven en NUESTRA hoja; si una línea del tester los recita, la escribió el asistente.
    # Medido en `search-buy-guitar__es` (2026-08-24 03:48), turno 18: «He estado mirando y tengo un par de
    # opciones … la Yamaha F370BL por 100 € y la Fender CD-60 por 120 €» — y el turno siguiente de zaelar
    # contesta como usuario («me quedo con la Yamaha»). Las seis caras del conductor no la vieron: no lleva el
    # nombre de la persona, no ofrece nada, y «he estado mirando» no es «he mirado». Ensanchar la séptima regex
    # es la cinta de correr; el título de un anuncio de NUESTRA hoja es un hecho.
    _known = [str(t) for t in ((mech.get("results_sheet") or {}).get("titles") or [])]
    _known += [str(t) for t in ((mech.get("offered") or {}).get("named") or [])]
    try:
        flipped = [{"turn": i + 1, "text": (t.get("text") or "")[:400]}
                   for i, t in enumerate(transcript)
                   if t.get("who") == "tester"
                   and (drivermod.looks_like_the_assistant(t.get("text") or "", config.PERSONA_NAME)
                        or verifymod.recites_our_candidates(t.get("text") or "", _known))]
    except Exception:  # noqa: BLE001
        flipped = []
    if flipped:
        mech["role_flip_lines"] = flipped
    if mute_turns:
        mech["mute_turns"] = {"turns": mute_turns, "n": len(mute_turns)}
    try:
        mech["agenda_meetings"] = probe_client.widget_rows("agenda", "meetings")
    except Exception as e:
        mech["agenda_meetings"] = None
        mech["agenda_error"] = str(e)

    run_data = {"transcript": transcript, "mechanism_report": mech, "watchdog_log": watchdog_log}
    if crashed:
        run_data["crashed"] = crashed
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
               failures_already: int = 0, provisional: str = "", allow_dirty: bool = False) -> int:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    # Stop the walk once there is enough to work on (operator, 2026-08-18: "cuando tengas 10 fallando, para —
    # habrá mucho que hacer"). Counting only sub-threshold verdicts, never INFRA: a crashed harness is not a
    # use-case failure and must not consume the budget. `failures_already` carries the count from earlier
    # batches, since the whole point is a budget over the WALK, not per batch.
    failures = failures_already
    # EL ÁRBOL SE COMPRUEBA EN CADA CASO, no solo al arrancar la tanda. Las dos guardas —árbol sucio y motor
    # rancio— corren UNA vez, antes del primer caso, y eso bastaba cuando una corrida era un caso. Una TANDA
    # dura horas: medido el 2026-08-24, arranqué cuatro casos con el árbol limpio y edité el motor mientras
    # corrían, así que del segundo en adelante se midió código que ya no existía en disco — con el marcador
    # escribiéndose por escenario, o sea que la basura entra en el tablero compartido caso a caso.
    #
    # Es exactamente el daño que `dirty_tree_refusal` existe para impedir («una ronda medida a mitad de una
    # edición no se puede comparar con ninguna otra»), y la guarda no podía verlo porque solo mira al empezar.
    # Se PARA la tanda en vez de saltar el caso: lo que ha cambiado es el sujeto de la medida, así que los
    # casos que quedan tampoco valen — y se dice con qué `--start-at` se retoman, como el tope de fallos.
    # Se compara una HUELLA del árbol contra sí misma, no «¿está sucio?». Escrito así el 2026-08-24 después de
    # medir el coste de la versión anterior: preguntaba `code_stamp()` —que MEMOIZA— y declaraba movimiento con
    # `or bool(dirty)`, o sea que (a) no podía ver una edición a mitad de tanda, que es justo lo que venía a
    # cazar, y (b) paraba la tanda tras el primer caso siempre que el árbol ya estuviera sucio al arrancar.
    # Un árbol sucio y QUIETO —otro agente con dos ficheros en vuelo desde antes— es perfectamente comparable
    # consigo mismo; lo que rompe la comparación es que el contenido CAMBIE, con commit o sin él.
    _tree_at_start = config.engine_fingerprint()
    _head_at_start = config.current_head()
    for scenario in chosen:
        if results and not allow_dirty:
            if config.engine_moved(_tree_at_start, config.engine_fingerprint()):
                print(f"\n■ parando el walk: el MOTOR se ha movido desde que arrancó la tanda "
                      f"({_head_at_start[:9] or '?'} → {config.current_head()[:9] or '?'}). "
                      f"Lo que queda mediría código distinto del de los casos ya corridos, así que no se "
                      f"podrían comparar. Se retoma con --start-at {scenario.id}")
                break
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
        # Y ANTES DEL PRIMERO TAMBIÉN. Hasta 2026-08-21 esto era `if results:` — o sea, se limpiaba ENTRE casos
        # y nunca al empezar. El plató es persistente a propósito (mismo puerto, se mira en vivo), así que el
        # primer caso de cada tanda heredaba el canvas, las tareas y los workers de la RONDA ANTERIOR: el
        # operador cargó el test ES y lo primero que vio fue pantalla sucia de la corrida de antes. La regla que
        # pidió es exactamente lo que `hard_reset()` hace y lo que NO hace: mata el trabajo vivo y borra el
        # canvas, y deja en pie la memoria y el estado (`/reset/hard`, no `/api/reset/full` con `wipe_memory`).
        # UN CASO CADA VEZ, Y SE COMPRUEBA (norma del operador, 2026-08-24, con cuatro hojas de casos
        # distintos apiladas en su pantalla: «we do one, we close, we continue with another»). Pedir el
        # reset no es haberlo conseguido: aquí había una espera FIJA de dos segundos y detrás la línea «motor reseteado
        # (sin trabajo ni canvas anterior)» impresa PASARA LO QUE PASARA. Los dos segundos eran un número
        # inventado —medido ese mismo día, un worker de investigación seguía escribiendo en la hoja del caso
        # anterior después del reset— y la línea era una afirmación que nadie comprobaba, justo donde el
        # operador la lee para fiarse de que el caso siguiente se mide solo.
        try:
            probe_client.hard_reset()
            st = probe_client.settle_after_reset()
            if st["clean"]:
                print(f"  ▸ motor limpio en {st['waited_s']}s: sin trabajo vivo ni tarjetas "
                      f"(memoria y estado intactos)")
            else:
                # No se para la tanda: un worker que tarda en morir cuesta menos que perder la medida. Pero
                # se DICE lo que quedó vivo, con su nombre, para que el veredicto se pueda leer sabiéndolo.
                print(f"  ⚠️ el motor NO quedó limpio tras {st['waited_s']}s — este caso arrastra: "
                      f"{'trabajo ' + str(st['tasks']) if st['tasks'] else ''}"
                      f"{' tarjetas ' + str(st['items']) if st['items'] else ''}")
        except Exception as e:
            print(f"  ⚠️ no pude resetear el motor antes del caso: {e} — este caso puede arrastrar "
                  f"trabajo de antes")
        try:
            results.append(_run_scenario(scenario, ran_before=[r["scenario"] for r in results],
                                          sandboxed=sandboxed, provisional=provisional))
        except Exception as e:  # one scenario's infra hiccup must not lose the whole batch's report
            print(f"  ✗ scenario crashed: {e}")
            # Say WHAT STATE the engine was in and WHAT ITS LOG SAYS, right here — the answer exists at this
            # moment and «INFRA: timed out» alone already cost half an hour of manual diagnosis (2026-08-23).
            # A ScenarioCrash arrives with its autopsy taken at death; anything else gets one now.
            autop = getattr(e, "autopsy", None) or engine_autopsy(str(e))
            print(f"    ⚕ motor: {autop.get('engine', '?')}")
            for ln in (autop.get("log_tail") or [])[-3:]:
                print(f"    ⚕ log: {ln[:160]}")
            results.append({"scenario": scenario.id, "tier": scenario.tier, "channel": scenario.channel,
                            "run": {"transcript": list(getattr(e, "transcript", []) or []),
                                    "mechanism_report": {}, "watchdog_log": [],
                                    "crashed": str(e), "autopsy": autop},
                            "verdict": {"scores": {}, "overall": None, "findings": [], "improvements": [],
                                       "veredicto": f"INFRA: {e} · motor: {autop.get('engine', '?')}"}})
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


def window_of(rows: list, start_at: str = "", limit: int = 0) -> tuple[list, str]:
    """La VENTANA de la tanda: desde `start_at`, como mucho `limit`. Devuelve `(filas, error)`.

    UNA sola casa para los dos flags que acotan el walk, porque tenerlo en dos costó las dos formas del mismo
    fallo el 2026-08-24:

      · el ORDEN de aplicación estaba invertido en el camino de correr — `--limit` recortaba a los N PRIMEROS
        y luego se buscaba el id ahí dentro, así que «cuatro casos empezando por la bicicleta» no seleccionaba
        nada y fallaba con «is not in the selected set», que apunta a la selección y no a la aridad.
      · y `--list` ignoraba los dos, así que se usó para comprobar qué iba a correr una tanda y contestó por
        la selección ENTERA. Su propio comentario ya arreglaba esto mismo para `--segment`.

    Y arreglar `--list` por su cuenta habría sido PEOR que el fallo: ese camino ordena por (tier, locale, id)
    y el de correr respeta el orden de `all_scenarios()`, que NO es el mismo — comprobado, difieren desde el
    primer elemento. El listado habría previsualizado una tanda distinta de la que corre, con toda la
    seguridad de un listado correcto.
    """
    ids = [s.id for s in rows]
    if start_at:
        if start_at not in ids:
            return rows, f"--start-at {start_at!r} is not in the selected set"
        rows = rows[ids.index(start_at):]
    return (rows[:limit] if limit else rows), ""


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
    # CASOS DE FUTURO: no se conducen hasta que sus tareas de roadmap estén hechas (operador, 2026-08-21:
    # «y así ahora mismo jamás lo ejecutarías, porque sabrías que esas tareas están pendientes»). Conducir uno
    # hoy costaría una conversación entera para producir un fallo que ya está escrito en su iniciativa, y
    # encima archivaría una ronda duplicada. Se DICEN, nunca se saltan en silencio: un caso que desaparece de
    # la selección sin explicación se lee como que no existe.
    if not getattr(args, "include_blocked", False):
        from . import segments as _G
        gated = [(s_, _G.blocked_by(s_.id)) for s_ in chosen]
        blocked = [(s_, refs) for s_, refs in gated if refs]
        if blocked:
            chosen = [s_ for s_, refs in gated if not refs]
            print(f"⏳ {len(blocked)} caso(s) de FUTURO, no se conducen (usa --include-blocked para forzarlo):")
            for s_, refs in blocked:
                print(f"   · {s_.id} ← pendiente de {', '.join(refs)}")
        if not chosen:
            print("no queda ningún caso conducible en esta selección")
            return 0
    chosen, _err = window_of(chosen, args.start_at, args.limit)
    if _err:
        print(_err, file=sys.stderr)
        return 2
    if not chosen:
        print("no scenarios selected", file=sys.stderr)
        return 2

    # `--lab` is checked HERE and not only at the routing loop below, because this branch RETURNS: without it a
    # `--lab es` round fell straight through to the operator's own engine and measured THEIR memory, widgets and
    # running tasks — with the banner cheerfully saying so while the lab agent sat idle on its bookmarked port.
    if not args.sandbox and not getattr(args, "lab", ""):
        print(f"▲ running against the LIVE engine at {config.ZAELAR_URL} — its memory, widgets and running "
              f"tasks are the operator's. Use --sandbox for an isolated one.")
        # Y DECIR LO QUE ESTA RONDA SE VA A LLEVAR POR DELANTE. Desde 2026-08-21 cada caso empieza con un
        # `hard_reset()` (el plató tiene que verse limpio en cada test, petición del operador): eso mata el
        # trabajo de fondo y borra el canvas. En un sandbox no hay nada que perder; en el motor del operador
        # lo que se mata es SUYO. La memoria y el estado se quedan — es `/reset/hard`, no un borrado.
        print("  ▲ y ADEMÁS lo va a RESETEAR antes de empezar: mata el trabajo de fondo y borra el canvas "
              "(la memoria y el estado se quedan). Si el operador tiene algo en marcha, se pierde.")
        # LA MISMA GUARDA DE ÁRBOL SUCIO QUE LAS OTRAS DOS RUTAS. Vivía solo en `_sandbox_batch` y
        # `_lab_batch`, y eso no es un descuido menor: una ronda es una MEDIDA se corra donde se corra, y
        # una que no se puede atribuir a un commit ensucia el marcador COMPARTIDO igual desde aquí.
        # Encontrado tropezando con ello (2026-08-21): un `tests run use_cases` con el árbol sucio escribió
        # su veredicto en el marcador sin que nada lo parase.
        _stamp = config.code_stamp()
        config.machine_stamp()
        _refusal = dirty_tree_refusal(_stamp, allow_dirty=getattr(args, "allow_dirty", False))
        if _refusal:
            print(_refusal)
            return 3
        return _run_batch(chosen, sandboxed=False, args_no_file=args.no_file,
                          allow_dirty=getattr(args, "allow_dirty", False),
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
            rc |= (_lab_batch(g, args, verify_tasks=verify_tasks) if getattr(args, "lab", "")
                   else _sandbox_batch(g, args, verify_tasks=verify_tasks))
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
        chain, moved = _live_rung_first(chain)
        # THE LADDER IS NOT THE TITULAR. `config.v2.fast_model_spec()` reads `fast.model` / `fast.base_url`,
        # NOT `fast.providers[0]`, so seeding only the ladder left the sandbox on the hardcoded fallback and
        # the reorder above changed nothing that the turn actually used: the probe still went to the rung
        # with no balance and came back 402 with `spec: deepseek/deepseek-v4-pro`. Measured 2026-08-21, on
        # the fix for this very problem. The head travels with the ladder, and when a rung is promoted the
        # head is repointed at it — otherwise the promotion is decoration.
        head = _fast_head(src) or {}
        if moved and chain:
            head = {**head, "model": chain[0].get("model"), "base_url": chain[0].get("base_url"),
                    "provider": chain[0].get("provider") or head.get("provider")}
        dst = _P(ws) / "config"
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "v2.json").write_text(
            _json.dumps({"fast": {**head, "providers": chain}}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return " → ".join(str(x.get("name") or "?") for x in chain) + (f"  [{moved}]" if moved else "")
    except Exception:
        return ""




def _fast_head(src) -> dict:
    """The operator's `fast` head — provider/model/base_url and nothing else.

    `api_key` is deliberately NOT copied: the engine resolves the key by endpoint from the credential store,
    so the sandbox needs no secret written into a file under `tests/runs/` that nothing ever cleans up.
    """
    import json as _json
    try:
        fast = ((_json.loads(src.read_text(encoding="utf-8")) or {}).get("fast") or {})
    except Exception:
        return {}
    return {k: fast[k] for k in ("provider", "model", "base_url") if fast.get(k)}


def rung_answers(rung: dict, *, timeout: float = 25.0) -> tuple[bool, str]:
    """Does THIS rung of the chain answer, right now? Returns (answers, what it said).

    One tiny OpenAI-compatible call, four tokens. Not a health system: a single question asked once, at
    seed time, whose only job is to keep a refusing provider out of the FIRST position.
    """
    import json as _json
    import urllib.error as _ue
    import urllib.request as _ur
    try:
        from config import credentials as _cred
        key = next((_cred.get(k) for k in (rung.get("env") or []) if _cred.get(k)), "")
    except Exception:
        import os as _os
        key = next((_os.getenv(k) or "" for k in (rung.get("env") or []) if _os.getenv(k)), "")
    if not key:
        return False, "sin credencial"
    url = str(rung.get("base_url") or "").rstrip("/") + "/chat/completions"
    body = _json.dumps({"model": rung.get("model"), "max_tokens": 4,
                        "messages": [{"role": "user", "content": "di solo: ok"}]}).encode()
    # A bare urllib request has NO User-Agent and Cloudflare answers 1010 to it. Measured on 2026-08-21: a
    # first probe declared two live providers dead for exactly this reason, and I was one message away from
    # telling the operator there were none left.
    req = _ur.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "User-Agent": "zaelar-use-cases-harness/1.0"})
    try:
        with _ur.urlopen(req, timeout=timeout) as r:
            return (200 <= r.status < 300), f"HTTP {r.status}"
    except _ue.HTTPError as e:
        try:
            detail = (e.read() or b"")[:160].decode("utf-8", "replace")
        except Exception:
            detail = ""
        return False, f"HTTP {e.code} {detail}".strip()
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:100]}"


def _live_rung_first(chain: list) -> tuple[list, str]:
    """Put a rung that ANSWERS at the head of the chain. Returns (chain, what was done — "" if nothing).

    Why the harness has to do this at all: **the text channel does not relay.** Measured 2026-08-21 —
    `POST /api/flash/say` came back `{"ok": false, "error": "402 Insufficient Balance"}` while, in the same
    second of the same log, the voice channel said «SIN SALDO → relevo a aimlapi-failover» and i18n relayed
    too. `nucleo/flash/probe.py` catches the provider error, records the cooldown, and returns it: it never
    tries the next rung. So for THIS channel the chain is not a chain — only rung one exists. Eight hours of
    window were spent retrying a preflight that could never pass with a live failover sitting behind a dead
    titular. Reported to the engine agent; until it lands, the harness hands the channel a head that talks.

    Nothing is dropped and the operator's relative order is kept: the first rung that answers is moved to
    the front, everyone else follows in their original order. Reordering the ROUTE is infrastructure and
    legitimate; the model measured stays whatever that rung declares, which is why `seed_provider_chain`
    already appends a broker rung carrying the TITULAR's model — so a reorder does not silently swap the
    brain under measurement for a smaller one.

    If nobody answers, the chain is left exactly as the operator wrote it: the preflight then refuses with
    the real reason, which is the correct outcome. Faking a head that cannot talk would only move the
    failure later and make it look like the product's.
    """
    if not chain:
        return chain, ""
    ok0, why0 = rung_answers(chain[0])
    if ok0:
        return chain, ""
    # SAME BRAIN FIRST, other route. The operator's failover carries a SMALLER model (`deepseek-v4-flash`
    # behind a `deepseek-v4-pro` titular), so promoting it by position would quietly swap the brain under
    # measurement — and a round against flash is not comparable with yesterday's against pro. Rungs whose
    # model matches the titular's are asked first; only if none of those answers does a different brain get
    # the head, and the caller says so out loud.
    titular_model = str(chain[0].get("model") or "").split("/")[-1]
    rest_idx = list(range(1, len(chain)))
    same = [i for i in rest_idx if str(chain[i].get("model") or "").split("/")[-1] == titular_model]
    other = [i for i in rest_idx if i not in same]
    for i in same + other:
        ok, _why = rung_answers(chain[i])
        if ok:
            head = chain[i]
            rest = [x for j, x in enumerate(chain) if j != i]
            note = (f"«{chain[0].get('name')}» no contesta ({why0[:60]}) → "
                    f"al frente «{head.get('name')}»")
            if i in other:
                note += f" · ⚠️ OTRO CEREBRO ({head.get('model')} en vez de {titular_model})"
            return [head] + rest, note
    return chain, f"NINGÚN escalón contesta; se deja el orden del operador ({why0[:60]})"


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
    # THE ANSWER WAS IN THE BOX ALL ALONG. For eight hours this refusal said «look at the sandbox log» while
    # the very response it was holding carried `error: 402 Insufficient Balance` and the `spec` of the rung
    # that refused. A retry loop read «no se puede medir» 46 times and never once learned which provider or
    # why. An instrument that has the diagnosis and prints a suggestion to go find it is hiding it.
    why = str((out or {}).get("error") or "").strip()
    spec = str((out or {}).get("spec") or "").strip()
    said = ""
    if why:
        said = f"   LO QUE DIJO EL MOTOR: {why[:300]}\n"
        if spec:
            said += f"   ESCALÓN QUE SE INTENTÓ: {spec}\n"
    return ("✗ EL CEREBRO NO PUEDE HABLAR: un turno de prueba ha vuelto VACÍO antes de empezar.\n"
            + said +
            "   Casi siempre es la cadena de proveedores agotada (saldo o cuota). Mira el log del sandbox:\n"
            "   «Insufficient Balance», «sin cuota hasta …», «SIN RELEVO disponible».\n"
            "   NO se mide: una ronda así apunta un fallo de producto que en realidad es una factura.")



def bridge_allowlist_refusal() -> str:
    """CAN A WORKER REACH ITS OWN BRIDGES? Returns "" when yes, or the refusal to print.

    The worker drives the browser, reads memory and asks the network through `python -m nucleo.<bridge>`, and
    those commands are only permitted because `claude_session._BRIDGE_TOOLS` lists the exact interpreter. That
    list is built from `_ZAELAR` (derived from `__file__`) while the prompt hands the worker `bridge_python()`
    (`sys.executable`). In the engine's own tree the two are the same path and nobody notices.

    MEASURED 2026-08-21, on a pinned measuring worktree: `_ZAELAR` was the WORKTREE and `sys.executable` the
    real engine's venv — because a worktree's `.venv` is a symlink and Python resolves it — so the interpreter
    the prompt DICTATES was not in the allowlist and EVERY bridge call came back «This command requires
    approval». In headless nobody approves. The worker narrated it exactly right («el entorno donde estoy
    corriendo ha bloqueado todas las herramientas… aquí nadie puede aprobarlas»), the round scored 1/5 on
    resultado, and the judge's headline finding was that zaelar claimed results while its environment blocked
    every tool. The blockade was the measuring rig's. Five earlier rounds carried the same defect: every
    worktree round that spawned a worker at all shows 18-27 denials.

    So this is asked BEFORE a round rather than diagnosed after one. It reads the same two values production
    reads — never a copy of the rule, which would be a second place to drift.
    """
    try:
        from nucleo.workers import claude_session as _cs
        py = _cs.bridge_python()
        if py in _cs._INTERPRETERS:
            return ""
        return ("✗ LOS PUENTES DEL WORKER NO ESTÁN PERMITIDOS: el intérprete que el prompt le dicta no está en\n"
                f"   la allowlist, así que TODA llamada a un puente volverá «requires approval».\n"
                f"   dicta   (bridge_python) : {py}\n"
                f"   permite (_INTERPRETERS) : {', '.join(str(i) for i in _cs._INTERPRETERS)}\n"
                "   Casi siempre es medir desde un worktree: `_ZAELAR` sale de `__file__` (el worktree) y\n"
                "   `sys.executable` del venv REAL (un `.venv` symlinkeado lo resuelve Python). NO se mide:\n"
                "   el worker saldría sin navegador, sin memoria y sin red, y eso se lee como un fallo suyo.")
    except Exception as e:
        # Fail-open: no poder COMPROBAR el candado no es lo mismo que saber que está cerrado, y una ronda
        # perdida por una comprobación que se rompió sola es peor que la ronda que quería proteger.
        return ""


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


def running_engine_sha(base_url: str) -> str:
    """The sha of the code the engine that will ANSWER is actually running, or "" if it cannot be read.

    Read from `/api/status`, whose `version` item carries `extra.sha` — the same stamp the product shows
    the operator.
    """
    try:
        import json as _json
        import urllib.request
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/status", timeout=6) as r:
            data = _json.loads(r.read().decode("utf-8", "replace"))
        for item in (data.get("items") or []):
            if item.get("key") == "version":
                return str(((item.get("extra") or {}).get("sha")) or "").strip()
    except Exception:
        return ""
    return ""


def engine_code_changed_between(running: str, head: str) -> bool | None:
    """Did anything the ENGINE runs change between these two commits? `None` when it cannot be answered.

    A sha mismatch is not by itself a reason to refuse a round: this tree carries the harness AND the
    engine, and the harness commits several times an hour. Restarting the lab agent for a commit that only
    touched `tests/` costs the operator the session they are watching and measures exactly the same code.

    What matters is whether the PRODUCT moved. Anything outside `tests/` counts, including docs — a doc-only
    commit does not change behaviour, but guessing which paths are inert is how a real change gets waved
    through, and the cost of being wrong here is a whole round measured against code that no longer exists.

    `None` (a sha the local tree does not have, no git) is NOT "nothing changed": the caller keeps refusing,
    which is the answer that was safe before this function existed.
    """
    import pathlib
    import subprocess
    try:
        out = subprocess.run(["git", "diff", "--name-only", f"{running}..{head}"],
                             cwd=str(pathlib.Path(__file__).resolve().parents[4]),
                             capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    if out.returncode != 0:
        return None                      # unknown sha (shallow clone, commit not fetched) — cannot answer
    paths = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    if not paths:
        return False
    return any(not p.startswith("tests/") for p in paths)


def stale_engine_refusal(base_url: str, stamp: dict) -> str:
    """Refuse when the engine SERVING the round is running code older than the tree, or "" to go ahead.

    2026-08-21, and it cost a whole batch: the lab agent had been up since 12:47 on `3.15+4abaf9c` while
    four commits landed on top of it. The tree was clean, so `dirty_tree_refusal` said yes, and every round
    of the afternoon measured code that no longer existed. The verdicts were not merely stale — one of them
    was about to be reported to the engine agent as a regression in a feature he had just shipped and that
    the running process had never loaded.

    A clean tree and an up-to-date process are DIFFERENT questions, and the second one is the one that
    decides what the round measured. A lab agent is persistent on purpose (that is the whole point: the
    operator watches it on a fixed port), so nothing restarts it when a commit lands — the staleness grows
    in silence and looks exactly like a healthy setup.

    Unreadable version = a WARNING and not a refusal, and the difference is deliberate: refusing on "I could
    not ask" would block every round the moment `/api/status` changes shape, and the round is still worth
    something. What is not acceptable is silence, which is what let this happen.
    """
    running = running_engine_sha(base_url)
    head = str((stamp or {}).get("sha") or "")
    if not running or not head:
        return ""
    if running.startswith(head) or head.startswith(running):
        return ""
    if engine_code_changed_between(running, head) is False:
        # Los shas no cuadran y el MOTOR no se ha movido: lo que cambió es el arnés. Se dice —callarlo
        # dejaría la ronda pareciendo que corre justo el árbol que hay— y se sigue: reiniciar el plató por
        # un commit de `tests/` le cuesta al operador la sesión que está mirando y mide el mismo código.
        print(f"⚠  el plató corre {running} y el arbol esta en {head}, pero entre los dos solo cambian tests/:\n"
              f"   es el MISMO motor. Sigo sin reiniciar.")
        return ""
    return (f"\u2717 el motor que va a contestar corre {running} y el arbol esta en {head}: no es el mismo codigo.\n"
            f"   Un arbol limpio dice que NADIE esta editando, no que el proceso lleve los ultimos commits — un\n"
            f"   plato es persistente a proposito y nada lo reinicia cuando aterriza un commit.\n"
            f"   Reinicialo (conserva puerto, memoria y perfil):  python -m tests.use_cases.lab down <k> && "
            f"python -m tests.use_cases.lab up <k>")


def _lab_batch(chosen: list, args: argparse.Namespace, *, verify_tasks: dict | None = None) -> int:
    """Drive the round against a LAB agent (`tests/use_cases/lab/`) instead of a throwaway sandbox.

    Same harness, same judge, same ledger — the only thing that changes is which engine answers. It
    exists because a sandbox dies with the round: the operator can watch it while it runs and has
    nothing left to open afterwards. A lab agent stays, on a port they already have bookmarked, with its
    memory and its widgets exactly as the round left them.

    IT DOES NOT WIPE THE AGENT BY DEFAULT. A reset reseeds the profile and is a good idea before a measured
    round, but doing it here on its own would silently erase whatever the operator was looking at. It stays
    theirs to give — either as the standalone command (`python -m tests.use_cases.lab reset es`) or, now,
    as `--fresh` on the round itself.

    WHAT `--fresh` IS FOR, measured 2026-08-23 on `cheapest-monitor`. A lab agent is persistent, so it holds
    the memory of every round ever driven against it. The third attempt at that case opened with zaelar
    saying «tú antes hablabas de un 27" 4K por unos 300 euros» — a preference from the attempt that had died
    two hours earlier. The agent was not solving today's errand; it was finishing the old one, and a judge
    reading that transcript would have graded the wrong conversation.

    The harness already stamps `memory_carryover` for cases sharing a batch, but that list is built from the
    cases THIS invocation ran. A single-case round against a long-lived lab therefore reported an EMPTY
    carryover while the agent demonstrably remembered — evidence that was not wrong so much as blind. Hence
    the warning below: a non-fresh lab round now says out loud that prior memory is in play, because the
    failure mode is not a red round, it is a green one nobody questions.

    The clean-tree refusal still applies: a round measured mid-edit compares with nothing, and that is
    true whichever engine served it.
    """
    from tests.use_cases.lab import profiles as labp
    from tests.use_cases.lab import stage as labs

    prof = labp.get(args.lab)
    if getattr(args, "fresh", False):
        print(f"▶ reseteando el plató «{prof.key}» antes de medir (memoria borrada, perfil resembrado)…")
        labs.reset(prof)
    st = labs.status(prof)
    if not st.running:
        print(f"✗ el agente de plató «{prof.key}» no está en marcha.\n"
              f"   Arráncalo:  python -m tests.use_cases.lab up {prof.key}")
        raise SystemExit(4)
    wrong = [c for c in chosen if c.locale != prof.key]
    if wrong:
        # A US scenario on the Spanish agent measures the wrong country and looks like a product failure:
        # `operator.location` says Madrid, so the errand goes to Madrid and the judge marks it wrong.
        print(f"✗ el agente «{prof.key}» no puede medir escenarios de otro locale: "
              f"{', '.join(c.id for c in wrong[:4])}")
        raise SystemExit(3)

    stamp = config.code_stamp()
    config.machine_stamp()
    # NO HAY NEGATIVA POR ÁRBOL SUCIO EN EL CAMINO DEL PLATÓ, y es deliberado (2026-08-21, tras perder 23
    # minutos de paseo por ella). Un plató es un proceso PERSISTENTE: corre el código que cargó al arrancar,
    # así que una edición sin commitear que otro agente haga AHORA no puede entrar en esta ronda — no hay
    # nada que contaminar. La pregunta que sí decide qué se está midiendo es qué código lleva el plató
    # DENTRO, y de eso se ocupa la guarda de abajo. Esperar a que el árbol esté limpio sería esperar por un
    # fichero que este proceso no va a leer, y en un árbol compartido por varios agentes eso es esperar
    # indefinidamente. (En el sandbox SÍ se aplica: allí el motor se levanta del árbol en ese momento.)
    _stale = stale_engine_refusal(st.base_url, stamp)
    if _stale:
        print(_stale.replace("<k>", prof.key))
        # Código PROPIO: el que llama tiene que poder distinguir «reinicia el plató» de cualquier otra
        # negativa. Compartir el 3 hizo que el paseo anunciara «plató rancio» durante 23 minutos mientras
        # lo que pasaba era otra cosa — un diagnóstico equivocado que además parecía correcto.
        raise SystemExit(5)

    config.ZAELAR_URL = st.base_url
    config.SANDBOX_DB = str(labs.workspace_of(prof) / "memory" / "_data" / "sandbox.db")
    # The persona's own name, so the DRIVE model can be caught addressing itself by it (driver face 5).
    config.PERSONA_NAME = str((prof.state or {}).get("operator_name") or "")
    config.PERSONA_PROFILE = prof.persona_ground()
    print(f"▶ midiendo contra el agente de plató «{prof.key}» — {prof.title}")
    print(f"  ▸ MÍRALO EN VIVO: {st.base_url}")
    print(f"  ▸ cadena sembrada: {st.chain or '(desconocida)'}")
    if not getattr(args, "fresh", False):
        # Said EVERY time rather than only when contamination is detected, because detecting it would mean
        # knowing what the agent remembers, and the round that proved this necessary is exactly the one where
        # the harness believed nothing had carried over.
        print("  ⚠️ memoria del plató NO borrada: este agente recuerda las rondas anteriores y puede "
              "responder desde ellas. Usa --fresh para medir en limpio.")
    for _refusal in (brain_preflight(), bridge_allowlist_refusal()):
        if _refusal:
            print(_refusal)
            raise SystemExit(4)
    return _run_batch(chosen, sandboxed=True, args_no_file=args.no_file,
                      allow_dirty=getattr(args, "allow_dirty", False),
                      verify_tasks=verify_tasks, provisional=_provisional(args),
                      stop_after_failures=args.stop_after_failures,
                      failures_already=statusmod.failing_count() if args.stop_after_failures else 0)


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
        # …y si el cerebro habla pero el worker no puede tocar nada, tampoco se mide. Mismo código de salida:
        # las dos dicen NO SE PUEDE MEDIR, que es distinto de NO SE DEBE (3, árbol sucio).
        _br = bridge_allowlist_refusal()
        if _br:
            print(_br)
            raise SystemExit(4)
        try:
            return _run_batch(chosen, sandboxed=True, args_no_file=args.no_file,
                      allow_dirty=getattr(args, "allow_dirty", False),
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
    ap.add_argument("--fresh", action="store_true",
                    help="con --lab: borrar la memoria del agente y resembrar su perfil ANTES de medir, para "
                         "que la ronda no se conteste con lo que quedó de la anterior")
    ap.add_argument("--lab", choices=["es", "us"], default="",
                    help="medir contra el agente PERSISTENTE de tests/use_cases/lab/ (que el operador "
                         "puede mirar) en vez de contra un sandbox de usar y tirar")
    ap.add_argument("--include-blocked", action="store_true",
                    help="conducir TAMBIÉN los casos de futuro (los que declaran tareas de roadmap "
                         "pendientes en segments.py). Por defecto se saltan: su fallo ya está escrito")
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
        # …Y TAMBIÉN los dos que ACOTAN LA TANDA, por la MISMA función que los aplica al correr y sobre el
        # MISMO orden. Ordenar aquí y no allí es lo que haría del listado una mentira con forma de listado:
        # `all_scenarios()` no viene en orden (tier, locale, id) — comprobado, difieren desde el primero.
        rows, _err = window_of(rows, args.start_at, args.limit)
        if _err:
            print(_err, file=sys.stderr)
            sys.exit(2)
        _pretty = not (args.start_at or args.limit)     # solo se reordena cuando no hay ventana que respetar
        hand_ids = {x.id for x in SC.SCENARIOS}
        for s in (sorted(rows, key=lambda x: (x.tier, x.locale, x.id)) if _pretty else rows):
            seg = G.segment_of(s.id)
            mark = {G.COMPLETABLE: "✅", G.CREDENTIALS: "🔑", G.CAPABILITY: "🚧"}.get(seg.group if seg else "", "❓")
            hand = " (hand-written)" if s.id in hand_ids else ""
            why = f"  ← {seg.missing}" if seg and seg.missing else ""
            if seg and seg.blocked_by:
                mark = "⏳"
                why = f"  ← pendiente de {', '.join(seg.blocked_by)} · {seg.missing}"
            print(f"{mark} t{s.tier}  {s.locale}  {s.id}{hand}{why}")
        print(f"\n{len(rows)} de {len(SC.all_scenarios())} escenarios"
              + (f" · segmento {args.segment}" if args.segment else ""))
        sys.exit(0)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
