"""The SCOREBOARD — which promoted use cases actually work right now, and which don't.

The operator's ask (2026-08-18): *«que tuviéramos claro cuáles están funcionando bien y cuáles no»*. Before
this, every run wrote a fresh dated report into `tests/runs/use_cases/` and nothing accumulated — so
answering "does the flights case work?" meant opening reports by hand and guessing which was the most
recent meaningful one. This keeps a durable, committed, per-scenario last-known verdict.

PRIVACY (this repo is PUBLIC — see CLAUDE.md's «catálogo sí, diario no» rule, and the 2026-08-15 leak of 444
files of session transcripts): the ledger stores SCORES and a one-line verdict per scenario, never the
transcript, never the driver's invented persona details, never extracted listing data. The CATALOG of what is
tested and whether it passes is useful to anyone who clones the engine; the DIARY of what was said in a run
is not, and stays in `tests/runs/` (gitignored).
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def _code_stamp() -> dict:
    """Imported lazily so a ledger read never drags the config module (and its key loading) in."""
    try:
        from . import config
        return config.code_stamp()
    except Exception:
        return {}

LEDGER_PATH = Path(__file__).resolve().parents[3] / "use_cases" / "status.json"
BOARD_PATH = Path(__file__).resolve().parents[3] / "use_cases" / "STATUS.md"

PASS_THRESHOLD = 4          # same bar `run.py` prints and `cron_tick.sh` reads: overall >= 4


def load() -> dict:
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"scenarios": {}}


def record(results: list[dict], *, sandboxed: bool, provisional: str = "") -> dict:
    """Fold one batch's results into the ledger. Only scenarios that actually ran are touched — a batch of
    one must never look like it invalidated the other four.

    `provisional` carries WHY a round cannot be banked as a measurement (today: it ran on a moving tree via
    `--allow-dirty`). The row is still written — the evidence in it is often the point of the round — but it
    is flagged, because on 2026-08-20 a round measured while another agent was editing
    `widgets/navegador/act_api.py` wrote its score into the board while the harness operator was, in the same
    minute, telling the cluster that he was discarding it. A rule that lives only in prose is not a rule.
    """
    led = load()
    scen = led.setdefault("scenarios", {})
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    for r in results:
        verdict = r.get("verdict") or {}
        overall = verdict.get("overall")
        mech = (r.get("run") or {}).get("mechanism_report") or {}
        registry = mech.get("task_registry") or {}
        entry = {
            "last_run": stamp,
            "overall": overall,
            # WHICH RULER graded it. Measured on 2026-08-20: the same case had been graded by four different
            # judges across one day (glm-4.6 and two aliases of deepseek-v4-flash, plus older unsealed runs),
            # because the judge chain falls back when the vendor is rate-limited. Their averages over that
            # day's gradings differ by 0.44 of a point. A case that "went from 3 to 2" between two rounds may
            # simply have changed ruler, and the board would show that as a regression.
            "judge": (verdict.get("_judge_model") or "").replace("deepseek/", ""),
            # WHICH BRAIN it was graded ON — the same argument as `judge`, one floor down and heavier: the
            # judge is the instrument, the brain IS the product. Measured 2026-08-27: a US batch ran with
            # z.ai out of 5-hour quota, so its Brain Workers were served by the relay rung
            # (`deepseek-v4-flash`) instead of the titular the cloud contracts (`glm-5.3`). Five rows of 1-2
            # were about to sit next to titular-measured rows, indistinguishable. Caught by reading the log
            # by hand; nothing on the board or in this ledger recorded it. `+` between two names means the
            # chain MOVED mid-round: half that row is about one product and half about another.
            "brain": _brain_stamp(mech),
            "state": _state(overall, r),
            # Por qué, si fue INFRA. Ver `_infra`: las cuatro puertas piden acciones opuestas.
            "infra_reason": r.get("_infra_reason") or None,
            "scores": verdict.get("scores") or {},
            "verdict": (verdict.get("veredicto") or "")[:400],
            "missing_signals": mech.get("missing_signals") or [],
            # CUÁNTOS TURNOS le ocultamos lo que ya tenía (V2-432). Va a la fila porque es lo que decide si el
            # rojo de esa fila es del producto o nuestro, y el juez ya lo dice en prosa: sin el número aquí,
            # leerlo obliga a abrir el informe de cada ronda una por una.
            "blind_turns": int(((mech.get("sheet_hidden_from_the_prompt") or {}).get("n")) or 0),
            # The FULL stream audit, kept for the same reason as `families`: the close is decided by the tick
            # in the parent process, where the run dict no longer exists. A case does NOT close with anomalies
            # here, even if the judge gives it a 5 — see `tick._retest_pending`.
            "audit_anomalies": ((mech.get("audit") or {}).get("anomalies") or []),
            "sandboxed": sandboxed,
            # Set => this row is EVIDENCE, not a measurement. Anything that counts cases must skip it.
            "provisional": provisional or None,
            "tier": r.get("tier"),
            # Recorded so a LATER re-file can rebuild an honest round from the ledger alone. The tick's re-file
            # (`initiative.rotate_failure` from `tick._retest_pending`) runs in the parent process, where the full
            # run dict no longer exists — without these two the successor's evidence block claimed "0 turnos" and
            # "ninguna familia" for a case that had used its whole budget, which reads as a broken run instead of
            # a bad one, and the fixing agent reads exactly that block.
            "turns_used": len((r.get("run") or {}).get("transcript") or []) // 2,
            "families": mech.get("families_observed") or [],
            "drive_model": r.get("drive_model") or "",
            # WHICH CODE this row measured. Without it a row is a score with no subject: the fixing agent asks
            # "did my commit run in that round?" and the only answer is reading boot timestamps by hand.
            "code": _code_stamp(),
            # WHAT ELSE the machine was doing. Two rounds are only comparable if the box was — see
            # `config.machine_stamp`; a round measured while another agent held 39 GB in the GPU used to look
            # identical to one on an idle machine.
            "machine": r.get("machine") or {},
        }
        # What this case could HONESTLY be graded on. Recorded per row so a reader of the board knows a `PASS`
        # on a bookable case means "found real options and stopped at the wall", not "made a reservation" —
        # otherwise the scoreboard would quietly overclaim what the product does.
        try:
            from . import derived as D
            kind, missing = D.data_scope(r["scenario"].split("__")[0])
            if kind:
                entry["data_limit"] = {"kind": kind, "missing": missing}
        except Exception:
            pass
        if registry:
            entry["max_concurrent"] = registry.get("max_concurrent")
            entry["distinct_kinds"] = registry.get("distinct_kinds") or []
        # The workspace pointer SURVIVES a re-run. Everything else here is per-round and rightly replaced, but
        # the initiative is the case's home for its whole life — dropping it on the next round would send the
        # fixing agent back to guessing the filename, and it is the round-2 runs that need it most.
        prior = scen.get(r["scenario"]) or {}
        if prior.get("workspace") and not entry.get("workspace"):
            entry["workspace"] = prior["workspace"]
        scen[r["scenario"]] = entry
    led["updated"] = stamp
    LEDGER_PATH.write_text(json.dumps(led, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _render(led)
    return led


def _brain_stamp(mech: dict) -> str:
    """The models that actually ran the Brain Worker this round, busiest first, `+`-joined when the chain
    moved mid-round. The BACKEND is dropped on purpose (it is `claude_code` for every rung today, so it adds
    width and no information); `verify.brains_that_ran` keeps the full breakdown for the report.

    Empty string = no worker ran at all, which is a legitimate answer for a conversational case and must not
    read as "we forgot to stamp it".
    """
    by = ((mech.get("brains") or {}).get("n_by_worker") or {})
    if not by:
        return ""
    names = sorted(by, key=lambda k: (-by[k], k))
    return "+".join(n.split("/", 1)[-1] for n in names)


def _infra(r: dict, motivo: str) -> str:
    """Marca la fila INFRA **y deja escrito por qué**, en el propio resultado de la ronda.

    `INFRA` sin motivo es un agujero de operación, no de estilo. Las cuatro puertas que llevan a él —arnés
    caído, turnos vacíos, recall degradado, juez sin nota— piden acciones OPUESTAS: una es un bug del
    instrumento, otra es recargar un proveedor, otra es levantar el prewarm y la cuarta es mirar la cadena del
    juez. Desde el tablero se ven las cuatro igual.

    Medido el 2026-08-28, con el plató 24/7 ya corriendo: dos filas pasaron de FAIL a INFRA en una hora y
    reconstruir cuál de las cuatro ramas las movió fue imposible sin el dict de la ronda, que para entonces ya
    no existe. En un bucle que nadie mira durante ocho horas, ésa es exactamente la diferencia entre «está
    midiendo» y «lleva toda la noche produciendo basura a toda velocidad» — y la segunda es peor que estar
    parado, porque parado se nota.
    """
    r["_infra_reason"] = motivo
    return "INFRA"


def _state(overall, r: dict) -> str:
    """INFRA is deliberately its own state, never a FAIL: a network timeout or a crashed harness says nothing
    about whether the use case works, and folding the two together is how a scoreboard starts lying.

    CAPPED is its own state for the same reason, and it was the operator's call (2026-08-20). A case whose
    remaining half needs the user's own credentials — buying the tickets, closing the booking, paying the bill —
    cannot be finished here at all: today the product has no way to hold a user's login, and the local route
    (open a browser, let the person authenticate, keep the cookies) is exactly what a backend harness cannot
    simulate. Grading those as FAIL put permanent red rows on the board and fed the improvement loop work it
    can never close. So they get their own state: measured for HONESTY, kept off the pass/fail denominator.

    The half that IS reachable keeps being graded in full. Finding the options and handing them over is the
    completable case; closing and paying is the capped one. `derived.data_scope` is what says which is which.
    """
    run = r.get("run") or {}
    # `crashed` NO es «se cayó»: es un campo con TRES inquilinos, y cada uno trae ya escrita su propia
    # frase — el conductor fuera de papel (V2-313), una fuente de verdad ilegible (V2-396), o una excepción
    # de verdad con su autopsia. Escribí aquí un motivo genérico («el arnés se cayó») y era falso para los
    # tres: medido a la hora, sobre `best-plumber-same-day__us`, cuya frase real decía «el conductor se salió
    # de su papel en 1 línea(s) del transcript (turno 13): la ronda no mide al producto». Adivinar un motivo
    # teniendo el bueno delante es el mismo error que este nodo existe para arreglar, un piso más arriba.
    _dicho = str(run.get("crashed") or "").strip()
    if _dicho:
        return _infra(r, _dicho[:200])
    if (r.get("verdict") or {}).get("veredicto", "").startswith("INFRA"):
        return _infra(r, "el juez devolvió un veredicto marcado INFRA")
    # AN AGENT THAT SAID NOTHING WAS NOT MEASURED, whatever the cause. Measured 2026-08-21 on
    # `compare-broadband-plans__es`: DeepSeek answered HTTP 402 «Insufficient Balance» and z.ai had been out
    # of quota since the previous day, so every single zaelar turn came back EMPTY — and the round was filed
    # as 1/1/1/1/1 FAIL, a permanent red row about a case nobody had actually exercised. The scoreboard would
    # then have carried a product verdict earned by an unpaid invoice.
    mech_ = (run.get("mechanism_report") or {})
    mute = (mech_.get("mute_turns") or {}).get("n") or 0
    turns = max(1, len((run.get("transcript") or [])) // 2)
    if mute and mute >= max(2, turns // 2):
        return _infra(r, f"{mute} de {turns} turnos de zaelar volvieron VACÍOS (proveedor caído o sin saldo)")
    # SEMANTIC RECALL OFF IS NOT A PRODUCT VERDICT. If the round's own process resolved its embeddings to
    # `hash` (lexical only) or `fastembed` (collapses at scale, T176), every memory-dependent check was
    # graded against a memory that could not answer by meaning — and it fails QUIET, looking exactly like an
    # agent that forgot. The memory agent established (2026-08-21) that a process reporting `ollama` at
    # prewarm cannot degrade later, so this line is a reliable statement about the round that ran.
    if ((mech_.get("embeddings") or {}).get("degraded")):
        _b = (mech_.get("embeddings") or {}).get("backend") or "sin prewarm"
        return _infra(r, f"recall semántico DEGRADADO en esta ronda (backend: {_b})")
    # UN PLATÓ SIN NAVEGADOR NO MIDE UNA BÚSQUEDA. Medido el 2026-08-30: el Chromium del plató US se cayó y no
    # volvió, el log repetía «Waiting for the browser to settle before retrying» con HARD RESET cada pocos
    # minutos, y las rondas salían con la hoja VACÍA — indistinguibles de «el producto no encuentra nada». La
    # serie asentada bajó 3→3→2→1→0→0 y yo estaba a un mensaje de mandarlo como defecto de extracción.
    #
    # La firma es inequívoca y no se confunde con una búsqueda mala: el worker INTENTÓ navegar (`navigations`
    # > 0) y NO aterrizó en ninguna página (`page_journey.n_pages` == 0). Un worker que busca mal aterriza en
    # páginas malas; uno sin navegador no aterriza en ninguna. Se exige `read` para no acusar cuando el
    # recorrido simplemente no se pudo leer — una ausencia de dato no es un dato.
    _pj, _wo = mech_.get("page_journey") or {}, mech_.get("worker_outcome") or {}
    if _pj.get("read") and not _pj.get("n_pages") and (_wo.get("navigations") or 0) > 0:
        return _infra(r, f"el plató NO tiene navegador: {_wo.get('navigations')} intento(s) de navegar y "
                         f"NINGUNA página alcanzada (revisa el Chromium del plató)")
    if overall is None:
        return _infra(r, "el juez no devolvió nota")
    # El MECANISMO manda sobre la nota agregada. Medido el 2026-08-19: `reorder-prescription__es` sacó overall 4
    # (conducta impecable: 5 en naturalidad, adaptación y resultado) con **mecanismo 1**, y el propio juez
    # escribió «desincronización crítica: el sistema reporta estado 'working' con cero actividad de fondo». El
    # umbral agregado lo cerró como PASADO y tiró ese hallazgo a la basura. La regla fundacional de este arnés
    # es que el informe de mecanismo es la fuente de verdad sobre el texto (ver el docstring de judge.py), así
    # que un 1-2 en mecanismo NO puede salir en verde aunque la media dé: sigue habiendo un defecto medido, y su
    # sitio es una iniciativa, no un tick verde.
    mech_score = ((r.get("verdict") or {}).get("scores") or {}).get("mecanismo")
    # CAPPED before PASS/FAIL: the cap does not depend on how well it does, but on its other half demanding a
    # user credential that does not exist here. The score is kept and shown — a capped 5 means "it got as far
    # as anyone can get, and flawlessly" — but it counts as neither a pass nor a failure.
    try:
        from . import derived as D
        kind, _missing = D.data_scope((r.get("scenario") or "").split("__")[0])
    except Exception:
        kind = ""
    if kind:
        return "CAPPED"
    if overall >= PASS_THRESHOLD and isinstance(mech_score, (int, float)) and mech_score <= 2:
        return "FAIL"
    return "PASS" if overall >= PASS_THRESHOLD else "FAIL"


_ICON = {"PASS": "✅", "FAIL": "❌", "INFRA": "⚠️", "CAPPED": "🔒"}


def _parked_reason(scenario_id: str) -> str:
    """The operator-owned environmental parking reason, or "" — guarded so an unreadable boundary cannot
    blank the board."""
    try:
        from . import phases as _ph
        return _ph.parked_reason(scenario_id)
    except Exception:  # noqa: BLE001
        return ""


#: Cómo abre el juez cuando su conclusión es que NO. Se mira solo el ARRANQUE del veredicto: en el cuerpo la
#: misma frase aparece a menudo negada («no está listo… salvo por») y buscarla en cualquier sitio marcaría
#: filas que dicen lo contrario.
_NO_LISTO = ("no está listo", "no esta listo", "no listo", "el caso no está listo")


def _judge_says_not_ready(verdict: str | None) -> bool:
    return (str(verdict or "").strip().lower()).startswith(_NO_LISTO)


def _brain_cell(e: dict) -> str:
    """A row from BEFORE this field existed has no brain, and it must not be shown as if it had none: `—` is
    a measured absence (no worker ran), `?` is an unknown one. Conflating them would let every old row read
    as a conversational case."""
    if "brain" not in e:
        return "?"
    return f"`{e['brain']}`" if e["brain"] else "—"


def _render(led: dict) -> None:
    scen: dict = led.get("scenarios") or {}
    lines = [
        "# Use-case scoreboard — what actually works right now",
        "",
        "**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by",
        "every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.",
        "",
        f"Last updated: **{led.get('updated', '—')}**",
        "",
        "`✅ PASS` = judge overall ≥ 4 **and** mechanism ≥ 3 (a measured mechanism defect never shows green, "
        "however good the average) · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,",
        "says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not",
        "the operator's live one.",
        "",
        "`🔒 CAPPED` is NOT a failure and NOT a pass: the case's remaining half needs the user's own",
        "credentials (buy the tickets, close the booking, pay the bill) and there is no way to reach it from",
        "here — the product holds no user logins today, and the local route (open a browser, let the person",
        "log in, keep the cookies) cannot be simulated by a backend harness. These rows are measured for",
        "HONESTY only, keep their grade, and are **excluded from the pass/fail count** so they stop feeding",
        "the improvement loop work it can never close. Operator's rule, 2026-08-20.",
        "",
        "`brain` = which model actually ran the Brain Worker in that round, read from the event stream and "
        "not from config. It is part of the row because the score is ABOUT it: the same case measured on the "
        "titular the cloud contracts and on a relay rung is two different products. `a+b` means the chain "
        "moved mid-round. Blank = no worker ran (fine for a purely conversational case).",
        "",
        "| | scenario | tier | overall | brain | last run | sandbox | verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for sid in sorted(scen, key=lambda s: (scen[s].get("tier") or 0, s)):
        e = scen[sid]
        st = e.get("state", "INFRA")
        overall = e.get("overall")
        verdict = (e.get("verdict") or "").replace("|", "·").replace("\n", " ")
        if e.get("state") == "PASS" and _judge_says_not_ready(e.get("verdict")):
            # EL DESACUERDO, VISIBLE. `PASS` es el umbral del arnés (overall ≥ 4 y mecanismo ≥ 3) y «listo
            # para producción» es la opinión del juez: son dos preguntas distintas y las dos valen, así que
            # no se fuerza a que coincidan. Lo que no puede es ESCONDERSE — una fila verde que abre diciendo
            # «No está listo para producción» le da al lector dos cosas contrarias en la misma línea y la que
            # se queda es el icono. Medido el 2026-08-28: 2 de las 13 verdes.
            verdict = f"**⚠️ el juez dice que NO está listo, aunque la nota pase** · {verdict}"
        if e.get("state") == "INFRA" and e.get("infra_reason"):
            # El motivo MANDA sobre el veredicto en una fila INFRA: el veredicto habla de un producto que en
            # esa ronda no llegó a medirse, y leerlo como si sí invita justo al diagnóstico equivocado.
            verdict = f"**INFRA — {e['infra_reason']}** · (veredicto no medible: {verdict})"
        if len(verdict) > 160:
            verdict = verdict[:157] + "…"
        lines.append(
            f"| {_ICON.get(st, '⚠️')} | `{sid}` | {e.get('tier', '—')} | "
            f"{overall if overall is not None else '—'} | {_brain_cell(e)} | {e.get('last_run', '—')} | "
            f"{'yes' if e.get('sandboxed') else 'no'} | {verdict} |")

    capped = [s for s, e in scen.items() if e.get("state") == "CAPPED"]
    # Parked for an ENVIRONMENTAL wall (phases.GEO_PARKED): same treatment as capped, different reason — the
    # blocker is the outside world of THAT locale and the sibling twin proves the capability. Rendered here as
    # well as in the Observatory on purpose: this board and that page read ONE dataset, and a distinction added
    # to only one of the two surfaces does not fail with noise — it fails by coming out empty on the other.
    parked = [s for s in scen if _parked_reason(s)]
    countable = {s: e for s, e in scen.items() if s not in capped and s not in parked}
    passed = sum(1 for e in countable.values() if e.get("state") == "PASS")
    failed = sum(1 for e in countable.values() if e.get("state") == "FAIL")
    infra = sum(1 for e in countable.values() if e.get("state") == "INFRA")
    # The denominator is the cases we CAN finish. Counting the capped ones in turned the board into a tally of
    # perpetual debt: every batch measured them again and they came back red, with nothing to fix.
    lines += ["", f"**{passed} passing · {failed} failing · {infra} infra** of "
                  f"{len(countable)} scenarios we can actually finish."]
    if parked:
        lines += ["", "Plus **" + str(len(parked)) + " 🌍 parked** for an environmental wall a user in that "
                      "country would not hit (the sibling twin proves the capability). Visible, not counted, "
                      "each with its reason:"]
        lines += [f"- `{s}` — {_parked_reason(s)}" for s in sorted(parked)]
    if capped:
        good = sum(1 for s in capped if (scen[s].get("overall") or 0) >= PASS_THRESHOLD)
        lines += ["", f"Plus **{len(capped)} 🔒 capped** (need the user's own credentials; measured for honesty "
                      f"only, not counted above — {good} of them behaving impeccably up to the wall): "
                      + ", ".join(f"`{s}`" for s in sorted(capped)) + "."]
    lines += [""]

    # COVERAGE, next to the results. Without it "1 passing · 4 failing" reads like the whole answer to "which
    # use cases work?", when the honest answer also has to say how much of the catalog nobody has run yet —
    # and an UNRUN case is not a passing one. Broken down by tier and locale because that is how the walk is
    # actually driven (`--tier N --locale es`), so this doubles as the progress board for it.
    try:
        from . import scenarios as SC
        allsc = SC.all_scenarios()
    except Exception:
        allsc = []
    if allsc:
        done = set(scen)
        # SEGMENTATION FIRST. "13 of 125 ever run" invites the reading that the other 112 are pending work, and
        # 78 of them cannot be run at all today — they need a credential the operator has to hand over, or a
        # capability we have not built. Denominators that mix the two make the board look like a backlog when
        # it is really three different asks (operator request, 2026-08-19).
        try:
            from . import segments as G
        except Exception:
            G = None
        if G is not None:
            lines += ["## Segments — what can be carried out END TO END today", "",
                      "`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it "
                      "(an account, a card, a phone, a real bill/flight/prescription to act on). "
                      "`🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, "
                      "placing a call, a peer agent to negotiate with) — no credential would help. "
                      "Classification: `tests/use_cases/e2e/agent/segments.py`.", "",
                      "| segment | scenarios | run | passing |", "|---|---|---|---|"]
            for group, icon in ((G.COMPLETABLE, "✅"), (G.CREDENTIALS, "🔑"), (G.CAPABILITY, "🚧")):
                ids = [s.id for s in allsc if G.group_of(s.id) == group]
                ran = [i for i in ids if i in done]
                ok = sum(1 for i in ran if scen[i].get("state") == "PASS")
                lines.append(f"| {icon} {group} | {len(ids)} | {len(ran)} | {ok} |")
            lines.append("")

        runnable = [s for s in allsc if G is None or G.is_completable(s.id)]
        ran_all = [s.id for s in runnable if s.id in done]
        lines += [f"## Coverage of the RUNNABLE list — {len(ran_all)} of {len(runnable)} ever run "
                  f"({len(runnable) - len(ran_all)} never run)", "",
                  "An unrun case is **not** a passing one. This is the walk's progress board, and its "
                  "denominator is the `completable` segment only — a blocked case is not pending work, it is "
                  "waiting on something outside the harness.", "",
                  "| tier | locale | run | of | passing |", "|---|---|---|---|---|"]
        keys = sorted({(s.tier, s.locale) for s in runnable})
        for tier, loc in keys:
            group = [s.id for s in runnable if s.tier == tier and s.locale == loc]
            ran = [sid for sid in group if sid in done]
            ok = sum(1 for sid in ran if scen[sid].get("state") == "PASS")
            lines.append(f"| {tier} | {loc} | {len(ran)} | {len(group)} | {ok} |")
        lines.append("")

    limited = {s: e["data_limit"] for s, e in scen.items() if e.get("data_limit")}
    if limited:
        lines += ["## Cases with no real data behind them — what they are graded on", "",
                  "Operator's rule (2026-08-18): renewing a gym membership can never work with no gym, no "
                  "account and no membership — *«eso no es un fallo del use case»*. So the OUTCOME is withdrawn "
                  "from judgement while the CONDUCT is not: saying precisely what is missing scores full "
                  "marks, and claiming it was done is still the gravest failure. `no_booking` cases keep their "
                  "SEARCH half graded in full — only closing the booking is out of reach. Same in ES and US.",
                  "", "| scenario | scope | what is missing |", "|---|---|---|"]
        for sid in sorted(limited):
            d = limited[sid]
            lines.append(f"| `{sid}` | {d.get('kind')} | {d.get('missing')} |")
        lines.append("")

    # A CAPPED case also shows up here when its reachable half fell short. The cap takes the case off the
    # board, not its defects off the map: "get me the tickets" cannot be closed without a card, but FINDING
    # them can, and that is where the most useful findings of the day live (the theatre's blocked `cd`, the
    # restaurant's honest exit). If this table only looked at FAIL, the new state would have hidden exactly the
    # work that can still be done.
    work = {s: e["workspace"] for s, e in scen.items()
            if e.get("workspace") and (e.get("state") == "FAIL"
                                       or (e.get("state") == "CAPPED"
                                           and (e.get("overall") or 0) < PASS_THRESHOLD))}
    if work:
        lines += ["## Where the work on each failing case happens", "",
                  "Includes 🔒 capped cases whose REACHABLE half fell short: the cap keeps them out of the "
                  "score, not out of the work.", "",
                  "One initiative per use case — that initiative IS the workspace for it, and it carries the "
                  "transcript, the mechanism report and the reproduce command. Both folders are gitignored "
                  "(«ni nuestro pasado ni nuestro futuro se publican»), so these paths are local-only.", "",
                  "| scenario | initiative (the workspace) | fix task |", "|---|---|---|"]
        for sid in sorted(work):
            w = work[sid]
            lines.append(f"| `{sid}` | `{w.get('initiative', '—')}` | `{w.get('task', '—')}` |")
        lines.append("")

    # LO QUE NO LE DIJIMOS, junto y con su número. Sale antes de las secciones de mecanismo porque cambia
    # cómo se leen las notas de arriba: una fila con turnos ciegos tiene una parte de su rojo puesta por
    # nosotros (V2-432 — 45 de 48 rondas guardadas, 257 turnos).
    ciegas = {s: e["blind_turns"] for s, e in scen.items() if e.get("blind_turns")}
    if ciegas:
        lines += ["## Rondas en las que NO le dijimos lo que ya tenía", "",
                  "Turnos posteriores a que la hoja tuviera filas con nombre en los que el prompt de zaelar "
                  "**no decía que hubiera nada**. En esos turnos, un «sigo buscando» no es retener ni negar: "
                  "es repetir lo que le pusimos delante. Parte del rojo de estas filas es nuestro.", "",
                  "| scenario | turnos ciegos |", "|---|---|"]
        for sid in sorted(ciegas, key=lambda k: -ciegas[k]):
            lines.append(f"| `{sid}` | {ciegas[sid]} |")
        lines.append("")

    multi = {s: e for s, e in scen.items() if e.get("max_concurrent") is not None}
    if multi:
        lines += ["## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)", "",
                  "| scenario | max concurrent tasks | distinct worker kinds |", "|---|---|---|"]
        for sid, e in sorted(multi.items()):
            kinds = ", ".join(e.get("distinct_kinds") or []) or "—"
            lines.append(f"| `{sid}` | {e.get('max_concurrent')} | {kinds} |")
        lines.append("")

    BOARD_PATH.write_text("\n".join(lines), encoding="utf-8")


def summary_line() -> str:
    scen = (load().get("scenarios") or {})
    if not scen:
        return "no recorded results yet"
    countable = {s: e for s, e in scen.items() if not _parked_reason(s)}
    passed = sum(1 for e in countable.values() if e.get("state") == "PASS")
    return f"{passed}/{len(countable)} scenarios passing (see tests/use_cases/STATUS.md)"


def attach_workspaces(mapping: dict) -> None:
    """Record WHERE the work on each failing case happens, so the board is the entry point to it.

    The initiative is the workspace for a use case, but it lives among 100+ others in a gitignored folder —
    a fixing agent handed only "quick-fact-opening-hours is failing" has to know the naming convention to find
    anything. This closes that gap: the board names the file. Only PATHS are stored, never content — the paths
    are already-public case ids, while the initiative itself holds the transcript and stays local.

    Called AFTER filing (the paths do not exist before it), so it updates and re-renders rather than being
    folded into `record()`.
    """
    if not mapping:
        return
    led = load()
    scen = led.setdefault("scenarios", {})
    for sid, paths in mapping.items():
        if sid in scen:
            scen[sid]["workspace"] = paths
    LEDGER_PATH.write_text(json.dumps(led, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _render(led)


def failing_count() -> int:
    """How many cases are FAILING on the board right now — the walk's stop budget.

    Only `FAIL` counts. An `INFRA` row (crashed harness, network timeout) says nothing about a use case, and
    letting it consume the budget would stop the walk early with nothing real to work on.
    """
    return sum(1 for e in (load().get("scenarios") or {}).values() if e.get("state") == "FAIL")
