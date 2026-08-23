"""Mechanism verification — did the RIGHT subsystems actually fire, independent of what zaelar claimed in
its replies. Polls the durable observability flow (`GET /api/observability/flow/{corr_id}`) per turn's
trace id, and for a browser-involving task, the navegador widget's own state (real extracted results),
fetched from outside the conversation.

Family vocabulary matches the canonical one `voice/observer.py::_CAT` maps every event kind into (enforced
total by `tests/infrastructure/unit/core/test_observer_categories.py`): flash (FlashBrain), worker (Brain
Workers — includes the browser: "the navegador goes HERE, opening the browser is not its own family, it's
what a worker does when it needs one"), memory, widget, system, pulse.
"""
from __future__ import annotations

import json
import unicodedata
import re
import time

from . import probe_client


def families_in(events: list[dict]) -> set[str]:
    return {e.get("cat") for e in events if e.get("cat")}


def _fields(e: dict) -> dict:
    """The event's own fields, whatever shape the durable column hands back.

    `observer.emit` does `ev.update(extra)`, so an `extra={"tool": …}` lands FLAT at the top level of the
    stored payload — not under an `"extra"` key. The payload itself arrives as a JSON STRING from the
    observability API. Both facts are easy to get wrong in a way that never raises: a reader that looks for
    `e["extra"]["tool"]` just finds nothing and reports "no dropped actions", which is indistinguishable from
    a healthy run. Flat first, then nested, then the top-level dict, so all three shapes read the same.
    """
    payload = e.get("payload")
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    payload = payload if isinstance(payload, dict) else {}
    out = dict(payload)
    out.update({k: v for k, v in (payload.get("extra") or {}).items() if v not in (None, "")})
    for k, v in (e.get("extra") or {}).items():
        if v not in (None, ""):
            out.setdefault(k, v)
    return out


def find_navegador_task_id(events: list[dict]) -> str:
    """A navegador task card shows as a widget/show event with extra id "navegador::<task_id>" (see
    nucleo/dispatch.py). The exact payload nesting is defensive here (checked both flat and under "extra")
    since it's read from the durable JSON column, not the in-process event dict."""
    for e in events:
        payload = e.get("payload")
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        payload = payload if isinstance(payload, dict) else {}
        candidates = [payload.get("id"), (payload.get("extra") or {}).get("id")]
        for cand in candidates:
            if isinstance(cand, str) and cand.startswith("navegador::"):
                return cand.split("::", 1)[1]
    return ""


def poll_navegador_task(task_id: str, *, timeout_s: float = 90.0, interval_s: float = 3.0) -> dict:
    """Wait for a browser task to reach a terminal state (or the timeout), then return its final view —
    including real extracted results, if any. This is what a real person would experience as "it's still
    searching" vs. "it found something" — the harness waits the same way instead of judging mid-flight."""
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        last = probe_client.navegador_task(task_id)
        status = (last or {}).get("status", "")
        if status in ("done", "failed", "cancelled"):
            return last
        time.sleep(interval_s)
    return last


def live_navegador_snapshot(scenario_started_ms: float) -> str:
    """A ONE-SHOT (non-polling — for `poll_navegador_task`'s patient version, see above), compact status
    line for whatever navegador task is active RIGHT NOW in this scenario's live session, or "" if none.

    Built for the watchdog (2026-08-17, live finding): two scenarios got `stuck/abandon`ed after only 2-3
    turns while their mechanism report (checked AFTER the fact) showed a real worker genuinely navigating —
    `status=working`, a real URL, a fresh screenshot. The watchdog judges purely from the conversational
    transcript, which looks IDENTICAL for "genuinely slow but working" and "actually stuck" — a real search
    with Claude Code's vision-based navigation can legitimately take minutes. This gives the watchdog the
    same system-truth grounding the final verdict already uses, mid-conversation, so a scenario doesn't get
    cut short on background work that's actually progressing normally."""
    try:
        session_id = probe_client.current_session_id()
        events = [e for e in probe_client.session_events(session_id)
                  if (e.get("ts_ms") or 0) >= scenario_started_ms]
        task_id = find_navegador_task_id(events)
        if not task_id:
            return ""
        view = probe_client.navegador_task(task_id)
        status = (view or {}).get("status", "")
        if not status:
            return ""
        url = (view or {}).get("url", "")
        shot_rev = (view or {}).get("shot_rev", 0)
        return f"status={status}, shot_rev={shot_rev} (sube = sigue avanzando), url={url}"
    except Exception:
        return ""


class ConcurrencyTracker:
    """Accumulates live-task-registry samples ACROSS a multi-flow scenario's turns (`concurrent_tasks > 0`).

    Why sampled live and not derived from the durable event stream afterwards: the events can prove N tasks
    EXISTED, but "were two of them ever in flight at the same moment?" is a question about a moment, and the
    registry only holds live sessions (finished ones move to the ledger). Reading it once per turn is enough
    — a worker task lives for minutes, far longer than a turn — and costs one loopback GET.

    Fail-open throughout: this is evidence-gathering for the judge, never a gate that can crash a run.
    """

    def __init__(self) -> None:
        self.max_concurrent = 0
        self.samples: list[dict] = []
        self.seen: dict[str, dict] = {}       # task_id → first-seen {kind, goal}

    def sample(self, *, at_turn: int) -> None:
        try:
            live = probe_client.live_tasks()
        except Exception:
            return
        self.max_concurrent = max(self.max_concurrent, len(live))
        for t in live:
            tid = str(t.get("id") or "")
            if tid and tid not in self.seen:
                self.seen[tid] = {"kind": t.get("kind") or "", "goal": (t.get("goal") or "")[:80]}
        self.samples.append({
            "turn": at_turn,
            "n_live": len(live),
            "tasks": [{"id": str(t.get("id") or ""), "kind": t.get("kind") or "",
                       "phase": (t.get("phase") or "")[:40], "status": t.get("status") or ""}
                      for t in live],
        })

    def report(self) -> dict:
        kinds = sorted({v["kind"] for v in self.seen.values() if v["kind"]})
        return {
            # THE number this scenario exists to measure: were several tasks genuinely in flight at once?
            "max_concurrent": self.max_concurrent,
            "distinct_tasks_seen": len(self.seen),
            "distinct_kinds": kinds,
            "tasks": [{"id": k, **v} for k, v in self.seen.items()],
            "samples": self.samples,
        }

    def hint(self) -> str:
        """Compact line for the watchdog — same role `live_navegador_snapshot` plays for single-task runs:
        keeps it from abandoning a run where three real workers are grinding away normally."""
        if not self.samples:
            return ""
        last = self.samples[-1]
        if not last["n_live"]:
            return f"0 tareas vivas ahora (máximo visto en la corrida: {self.max_concurrent})"
        which = ", ".join(f"{t['kind'] or '?'}:{t['phase'] or t['status']}" for t in last["tasks"])
        return (f"{last['n_live']} tareas VIVAS ahora ({which}); máximo simultáneo {self.max_concurrent}, "
                f"{len(self.seen)} tareas distintas vistas")


# Signatures of a search layer that is DOWN rather than a search that found nothing. Matched against the text
# of `kind="search"` events, which carry the tool's own reply verbatim.
_SEARCH_DEAD = (
    ("quota_exhausted", ("limit exhausted", "weekly/monthly limit", "quota", "429")),
    ("blocked",         ("captcha", "tráfico inusual", "unusual traffic", "bloqueado")),
    ("rate_limited",    ("rate limit", "too many requests")),
    ("unavailable",     ("unable to perform the search", "search service", "no pude buscar",
                         "buscador está agotado")),
)


def search_health(all_events: list[dict]) -> dict:
    """Is the search layer WORKING, or is the environment lying to us about the agent?

    This exists because of a measurement that nearly became a false bug report. A scenario asked for a
    restaurant's opening hours, the agent answered without evidence of searching, and the judge marked it down
    for stating facts it could not have looked up — a perfectly reasonable verdict about a conversation that
    took place while Google was serving a CAPTCHA and the worker's own WebSearch was returning
    "Weekly/Monthly Limit Exhausted". With the search layer dead, "it didn't search" is not a finding about
    the product; it is a finding about the machine the test ran on.

    So the confound gets DETECTED and stamped into the evidence instead of being hand-annotated case by case
    (which is what happened the first time, and does not scale past a couple of failures). It deliberately does
    NOT rewrite the verdict: an agent that invents facts while search is down is still inventing facts, and
    downgrading that to INFRA would hide the more serious half. What it changes is what the fixing agent reads
    — "re-measure this with a healthy search layer" instead of "redesign grounding".
    """
    searches = [e for e in all_events if (e.get("kind") or "") == "search"]
    reasons: dict[str, int] = {}
    for ev in searches:
        low = ((ev.get("text") or "") + " " + (ev.get("label") or "")).lower()
        for reason, needles in _SEARCH_DEAD:
            if any(n in low for n in needles):
                reasons[reason] = reasons.get(reason, 0) + 1
    return {"n_search_events": len(searches), "degraded": bool(reasons),
            "reasons": sorted(reasons.items(), key=lambda kv: -kv[1])}


def scheduled_report(before: list[dict], after: list[dict]) -> dict:
    """What TRIGGERS this scenario left behind — the DELTA, never the absolute list.

    The delta matters more than it looks: an engine can already hold jobs from an earlier scenario in the same
    batch (they are durable by design and outlive the conversation), so an absolute count would credit a case
    with a reminder a previous case created. Comparing against a snapshot taken before the first turn is what
    makes "this conversation created a trigger" a real claim.

    Fails open to `created: []` — a scheduler that cannot be read must never invent evidence of a reminder,
    and must not fail a case either: `readable` says which of the two happened.
    """
    def _key(j: dict) -> str:
        return str(j.get("id") or "") or f"{j.get('name')}|{j.get('schedule')}"

    seen = {_key(j) for j in before}
    created = [j for j in after if _key(j) not in seen]
    return {
        "readable": bool(before is not None and after is not None),
        "n_before": len(before or []), "n_after": len(after or []),
        "created": [{"name": j.get("name"), "schedule": j.get("schedule"), "type": j.get("type"),
                     "next_run": j.get("next_run"), "prompt": (j.get("prompt") or "")[:200]}
                    for j in created],
    }


def dropped_actions(all_events: list[dict]) -> list[dict]:
    """Actions the turn DECIDED to take and the system could not read (`tool_dropped`, V2-171).

    This belongs in the mechanism report and not in a log, because it is the difference between the two
    diagnoses that look identical from a transcript: «the agent never tried» and «the agent tried and the
    system threw the action away». Getting that backwards cost three days — V2-133 filed eight cases of
    «zaelar narra un progreso que no ocurre» when the FlashBrain had in fact called `escalate_to_slowbrain`
    and its arguments were truncated past parsing. A judge that cannot see this has no way to tell them apart,
    so it picks the one that reads worse.
    """
    out = []
    for e in all_events:
        f = _fields(e)
        if (e.get("kind") or f.get("kind") or "") != "tool_dropped":
            continue
        out.append({"tool": f.get("tool") or "", "reason": f.get("reason") or "",
                    "finish_reason": f.get("finish_reason") or ""})
    return out


def widget_ops(all_events: list[dict]) -> dict:
    """Which WIDGET each data-op touched, and how many — the half of the mechanism nobody could see.

    Devuelto por el agente que arregla el 2026-08-20, y tenía razón: el criterio de
    `remember-and-remind-deadline` dice literalmente «juzga por … data-ops de agenda», y el informe de
    mecanismo NO traía ninguna. Solo traía familias (`widget` aparece, pero no QUÉ widget ni qué se hizo) y el
    bloque `scheduled_jobs`, que es de CRONS. Así que un hallazgo como «no existe ni el evento de agenda ni el
    trigger» se apoyaba, para la mitad de la agenda, en un lector que no cubre las agendas: la ausencia estaba
    INFERIDA del sitio equivocado. En su reproducción la cita SÍ se escribía.

    Es exactamente la misma clase de fallo que el de `evidence` unas horas antes: un lector que mira donde no
    está no falla, RESPONDE — y responde una ausencia, que es la respuesta más creíble y más dañina.

    Forma real del evento (medida, no supuesta): `cat="widget"`, `label` ∈ {data, show, close}, y el widget
    va en `id` como `"<widget>::<algo>"` (p. ej. `navegador::t2`).
    """
    ops: dict[str, dict[str, int]] = {}
    for e in all_events:
        if not isinstance(e, dict):
            continue
        f = _fields(e)
        cat = f.get("cat") if f.get("cat") is not None else e.get("cat")
        if cat != "widget":
            continue
        raw = str((f.get("id") if f.get("id") is not None else e.get("id")) or "")
        name = raw.split("::", 1)[0] or "(sin id)"
        label = str((f.get("label") if f.get("label") is not None else e.get("label")) or "?")
        ops.setdefault(name, {})
        ops[name][label] = ops[name].get(label, 0) + 1
    return ops


def audit(all_events: list[dict], expected_signals: list[str] | None = None) -> dict:
    """Walk the WHOLE stream and report what a families summary cannot see.

    `mechanism_report` answers "did the right subsystems show up". That is not the same question as "did
    every internal step go as it should", and the gap is not theoretical: the run of 2026-08-20 10:00 carried
    `is_error: true` on a worker step — *«Exit code 2, no puedo leer el payload de sources.json»* — and NOTHING
    in the report, the judge prompt or the operator's report ever mentioned it. The family `worker` was
    present, so by the old reading the mechanism was fine.

    So this reads the fields the summary throws away: `is_error` (an internal failure), `evidence` (what the
    OUTSIDE WORLD actually brought back, which is the only thing that can make a claim true), `tool` (which
    processes really ran), `span` (each worker's own lifeline) and the clock (a long silence is a symptom).

    Anomalies are stated as facts, never as verdicts — the judge decides what they mean. And the list is
    ORDERED with the certain ones first: an `is_error` event is not an interpretation.
    """
    exp = expected_signals or []
    # EVERY field goes through `_fields`, for the reason its own docstring gives: from the observability API
    # the payload arrives as a JSON STRING, so `e.get("evidence")` reads None on every event and the audit
    # reports zero evidence for a run that had sixty. That is not a hypothetical — the first version of this
    # function read the fields directly and told three separate cases (`find-theatre`, `restaurant`,
    # `cheapest-monitor`, 2026-08-20 12:2x) that «the outside world brought nothing back», while the sandbox
    # timeline for that very batch carried 60 events with `evidence`, 26 of them from the browser. It was
    # about to be handed to the fixing agent as a measured fact. Wrong in the worst direction: an audit that
    # invents an anomaly is worse than no audit, because it sends someone to look for a defect that is mine.
    evs = [(e, _fields(e)) for e in all_events if isinstance(e, dict)]

    def _f(e: dict, f: dict, key: str):
        return f.get(key) if f.get(key) is not None else e.get(key)

    errors = [{"cat": _f(e, f, "cat"), "kind": _f(e, f, "kind"), "label": _f(e, f, "label"),
               "span": _f(e, f, "span"), "rel_ms": _f(e, f, "rel_ms"),
               "text": str(_f(e, f, "text") or "")[:240]}
              for e, f in evs if _f(e, f, "is_error")]
    evidence = [e for e, f in evs if _f(e, f, "evidence")]
    tools: dict[str, int] = {}
    for e, f in evs:
        if t := _f(e, f, "tool"):
            tools[t] = tools.get(t, 0) + 1

    spans: dict[str, dict] = {}
    for e, f in evs:
        sp = _f(e, f, "span")
        if not sp:
            continue
        rel = _f(e, f, "rel_ms")
        d = spans.setdefault(sp, {"n": 0, "first_ms": rel, "last_ms": rel,
                                  "errors": 0, "last_label": ""})
        d["n"] += 1
        d["last_ms"] = rel
        d["last_label"] = _f(e, f, "label") or ""
        if _f(e, f, "is_error"):
            d["errors"] += 1

    stamps = sorted(r for e, f in evs
                    if isinstance((r := _f(e, f, "rel_ms")), (int, float)))
    gap = max((b - a for a, b in zip(stamps, stamps[1:])), default=0)

    anomalies: list[dict] = []
    for e in errors:
        anomalies.append({"clase": "error_interno", "certeza": "hecho",
                          "que": f"{e['cat']}/{e['kind']} «{e['label']}»: {e['text'][:160]}"})
    for d in dropped_actions([e for e, _ in evs]):
        anomalies.append({"clase": "accion_descartada", "certeza": "hecho",
                          "que": f"tool={d.get('tool') or '?'} razón={d.get('reason') or '?'}"})
    # Zero evidence with a worker or browser expected means nothing came back from the outside world. A
    # claim about the world cannot be true in that run, whatever the transcript says.
    if not evidence and ({"Brain Workers", "worker", "Widgets", "widget"} & set(exp)):
        anomalies.append({"clase": "sin_evidencia_externa", "certeza": "hecho",
                          "que": "ni un solo evento con `evidence`: el mundo exterior no trajo nada"})
    for sp, d in sorted(spans.items()):
        if d["errors"]:
            anomalies.append({"clase": "span_con_error", "certeza": "hecho",
                              "que": f"{sp}: {d['errors']} error(es), último paso «{d['last_label']}»"})
    if gap >= 60_000:
        anomalies.append({"clase": "silencio", "certeza": "medida",
                          "que": f"{gap/1000:.0f}s sin un solo evento"})

    return {
        "n_events": len(evs),
        "errors": errors,
        "n_evidence": len(evidence),
        "tools_run": tools,
        "spans": spans,
        "max_gap_ms": gap,
        "unexpected_families": sorted(families_in([e for e, _ in evs]) - set(exp)) if exp else [],
        "anomalies": anomalies,
        "clean": not anomalies,
    }


def sheet_instances(all_events: list[dict]) -> dict:
    """CUÁNTAS hojas de resultados se abrieron y CON QUÉ ENCARGO cada una.

    `widget_ops` no sirve para esto y no es un descuido suyo: colapsa la instancia a propósito
    (`raw.split("::")[0]`), porque la pregunta que contesta es «qué widget se tocó». Aquí la pregunta es la
    contraria — **cuántas CAJAS distintas** hubo del mismo widget— y colapsar la instancia la borra. Un lector
    que mira donde no está no falla, responde: diría «widget results tocado 9 veces» tanto con una hoja como
    con tres, y esa respuesta es exactamente igual de creíble en los dos casos.

    Regla del operador (2026-08-21): **dos búsquedas = dos hojas**, cada una con su correlation_id, y una hoja
    terminada NUNCA se reutiliza para el encargo siguiente — se abre una nueva. La razón es que reutilizarla
    borra una búsqueda, y una búsqueda borrada no se recupera.

    Hoy el motor NO hace eso: `dispatch._sheet_open()` emite `widget/show` con el id pelado `"results"` y
    `widgets/results/data.py` guarda en UNA clave (`store.load(WIDGET_ID, …)`), así que N encargos comparten
    una hoja y se acumulan con dedup. Este lector existe para MEDIRLO, no para suponerlo: con la pieza sin
    construir devuelve `n_sheets: 1` y varias fuentes distintas apuntando a la misma caja, que es la firma
    exacta del defecto. El día que V2-259 aterrice, el mismo lector devuelve 2 sin tocar una línea.

    Se lee del flujo de eventos y no del canvas a propósito: en una corrida sin nadie mirando no hay navegador
    pintando nada, y `GET /api/desktop` solo tiene lo que el frontend le haya persistido. El evento SÍ ocurre.

    Forma real del evento (medida): `cat="widget"`, `label="show"`, `id="results"` o `"results::<algo>"`, y
    `src="worker:<task_id>"` — que es lo que hoy ATA una apertura a su encargo aunque la caja sea única.
    """
    shows: list[dict] = []
    closes: list[dict] = []
    for e in all_events:
        if not isinstance(e, dict):
            continue
        f = _fields(e)
        cat = f.get("cat") if f.get("cat") is not None else e.get("cat")
        if cat != "widget":
            continue
        raw = str((f.get("id") if f.get("id") is not None else e.get("id")) or "")
        if raw.split("::", 1)[0] != "results":
            continue
        label = str((f.get("label") if f.get("label") is not None else e.get("label")) or "")
        row = {"id": raw,
               "instance": (raw.split("::", 1)[1] if "::" in raw else ""),
               "src": str(f.get("src") or e.get("src") or "")}
        if label == "show":
            shows.append(row)
        elif label == "close":
            closes.append(row)
    ids = sorted({r["id"] for r in shows})
    srcs = sorted({r["src"] for r in shows if r["src"]})
    return {
        # LO QUE SE MIDE: cajas distintas, no aperturas. Volver a mostrar la misma hoja no es una hoja nueva.
        "n_sheets": len(ids),
        "ids": ids,
        "n_opens": len(shows),
        # Encargos distintos que pidieron hoja. Si esto es >1 y `n_sheets` es 1, DOS búsquedas compartieron
        # caja — el defecto que V2-259 arregla, dicho con la cifra que lo prueba.
        "n_errands": len(srcs),
        "srcs": srcs,
        "shared": len(srcs) > 1 and len(ids) <= 1,
        "n_closes": len(closes),
    }


def ghost_widgets(all_events: list[dict]) -> dict:
    """Cards that opened WITHOUT anyone asking for them — "only what has to open, opens".

    The case behind it (operator, 2026-08-21, with a screenshot): on top of the browser card that was really
    working, ANOTHER empty «Navegador» card appeared, blank, covering it. No errand opens it — it is the
    canvas ECHOING ITSELF. The frontend reports its open set (`desktop._reportOpen` →
    `POST /api/canvas/state`), the server NORMALISES it for the prompt (`navegador::t2` → `navegador`,
    `server/voice_api.py`), and on seeing an id that is new with respect to the previous set it emits
    `widget/show id="navegador"` as an AUDIT (V2-039, `src="user"`). But that emit travels on the SAME SSE bus
    as the ORDERS, and `sse.js` turns it into `desktop.show("navegador")`. The canvas ends up obeying its own
    report.

    WHAT IS READ, and why this event and not another: `canvas (instancias)` carries the RAW list of cards
    (`instances`), unnormalised. It exists precisely because the normalised set makes the defect invisible —
    the comment that added it cites «V2-047 F9 (two browsers, one blank)», so this was already seen once and
    left INSTRUMENTED, never closed. The signature is a BASE id and an instance of the SAME widget open at the
    same time: `["navegador::t1", "navegador"]`. Measured in the lab: `13:47:00 ["navegador::t1"]` →
    `13:47:02 [..., "navegador"]`, and again at 13:59. Always a few seconds later, never before.

    CONDITIONAL OBSERVABILITY, and it has to be said out loud: the echo needs a REAL frontend reporting its
    canvas. In a round with nobody watching, nobody makes that POST, so there is no event, no echo and no
    ghost — which is why the automated batches went days without seeing this and the operator caught it by
    looking at the screen. Hence `observed`: with no canvas attached this returns `observed=False`, which is
    NOT "clean". A reader that returned "0 ghosts" without having been able to look would be asserting a check
    it never ran — the failure shape this harness has already paid for several times.
    """
    snaps: list[list[str]] = []
    for e in all_events:
        if not isinstance(e, dict):
            continue
        f = _fields(e)
        if str(f.get("label") or e.get("label") or "") != "canvas (instancias)":
            continue
        inst = f.get("instances")
        if isinstance(inst, list):
            snaps.append([str(x) for x in inst])

    ghosts: list[dict] = []
    for inst in snaps:
        bases = {i.split("::", 1)[0] for i in inst if "::" in i}
        for wid in inst:
            if "::" not in wid and wid in bases and not any(g["id"] == wid for g in ghosts):
                ghosts.append({"id": wid,
                               "alongside": sorted(i for i in inst if i.startswith(wid + "::"))})
    return {
        "observed": bool(snaps),          # False = no canvas was attached; it does NOT mean "clean"
        "n_snapshots": len(snaps),
        "max_cards": max((len(s) for s in snaps), default=0),
        "ghosts": ghosts,
        "last": snaps[-1] if snaps else [],
    }


def results_sheet(ids: list[str] | None = None) -> dict:
    """What the RESULTS SHEET holds at the end of the round, read from the engine.

    Kept as a fact of its own next to `navegador_task`, and it is not redundancy: today the browser CARD is
    what publishes `results`, and V2-257 moves that boundary — the card becomes a monitor and stops publishing
    them, while the sheet becomes the single place every finding lands, whichever browser found it. A report
    that only reads the card would start printing `resultados=0` the day that ships, and a judge reading it
    would conclude "the browser found nothing". That is a false defect of the exact class this harness has
    already paid for twice, so both surfaces get read and reported apart until the boundary settles.

    Measured on `best-plumber-same-day__es` (2026-08-21): the sheet finished with FIVE candidates carrying
    phone, rating and source while the conversation had already closed — which also makes the case for
    `read`: an unread sheet is not an empty one, and `0` must never stand for "nobody looked".

    READ THE BOXES THAT WERE ACTUALLY OPENED, not the bare id. Since V2-259 a sheet is keyed per errand
    (`results::<task>`), and the un-instanced `results` is a DIFFERENT box that an errand no longer writes to.
    Reading it after that landed measured, on `two-searches-two-sheets` (2026-08-21), a sheet holding fifteen
    rows of hotels and cars left over from earlier rounds while the errand under measurement wrote elsewhere —
    and the judge, reading that, concluded the agent "claims to have found plumbers with no mechanism backing
    it". A reader pointed at the wrong box does not fail: it INVENTS facts, and they read exactly as credible
    as real ones. `ids` comes from `sheet_instances`, so the two readers cannot drift apart; with none (no
    sheet opened, or an engine from before V2-259) it falls back to the bare box, which is then the only one.
    """
    boxes = [i for i in (ids or []) if str(i).split("::", 1)[0] == "results"] or ["results"]
    reads = []
    for box in boxes:
        suffix = box.split("::", 1)[1] if "::" in box else ""
        got = probe_client.widget_data("results", suffix)
        if got is not None:
            reads.append((box, got))
    if not reads:
        return {"read": False, "n_items": 0, "titles": [], "n_backed": 0, "n_sites_reported": 0,
                "boxes": boxes}
    items: list[dict] = []
    n_sites = 0
    per_box: list[dict] = []
    for box, got in reads:
        got_items = [it for it in (got.get("items") or []) if isinstance(it, dict)]
        items.extend(got_items)
        # SUMADO por caja, no el de la ÚLTIMA. Antes `counts` se sobrescribía en cada vuelta mientras `items`
        # se acumulaba, así que numerador y denominador venían de cajas distintas — la forma exacta de medir
        # contra el sitio equivocado que este mismo fichero documenta dos veces más arriba.
        if isinstance(got.get("counts"), dict):
            n_sites += int((got["counts"] or {}).get("sources") or 0)
        per_box.append({"id": box, "n_items": len(got_items),
                        "title": str(got.get("title") or "")[:70]})
    d = reads[-1][1]
    return {
        "boxes": [b for b, _ in reads],
        # WHAT EACH BOX HOLDS, not just the total: with one errand per box, a total says nothing about whether
        # THIS errand was served — the box next door could be carrying it.
        "per_box": per_box,
        "read": True,
        "n_items": len(items),
        # Only what carries a real name counts as a candidate — the same rule the browser note applies
        # (V2-234): a row without a name is not a result, it is a link that happened to be on the page.
        "n_named": sum(1 for it in items if str(it.get("title") or "").strip()),
        "titles": [str(it.get("title") or "")[:90] for it in items[:8]],
        # RESPALDO POR FILA — «¿de dónde salió ESTE candidato?». Medido en `search-secondhand-monitor__es`
        # (2026-08-24 01:35): la hoja acabó con SEIS anuncios reales, cada uno con su enlace vivo a
        # milanuncios.com o es.wallapop.com, su precio y su ubicación… y este informe dijo «6 candidatos de
        # 0 fuentes». El juez lo leyó como tenía que leerlo y fichó DOS [alta] por inventarse resultados,
        # contra una entrega correcta. La causa: se contaba `counts.sources`, que es `len(data["sources"])`
        # — la PESTAÑA «Fuentes», donde el worker declara qué sitios probó y cómo le fue. Es otra pregunta.
        # Que esa pestaña esté vacía no dice nada del respaldo de las filas, y confundirlas convierte «no
        # rellenó un apartado opcional» en «se lo inventó todo».
        #
        # Tercera vez la misma clase en dos días (`results: null`, `duplicate_errands`) y la más cara: las
        # otras dos exageraban un defecto, ésta FABRICA uno sobre un acierto.
        "n_backed": sum(1 for it in items
                        if str(it.get("url") or "").strip() or str(it.get("badge") or "").strip()
                        or str(it.get("source") or "").strip()),
        # Y la pestaña, con su nombre de verdad: sigue siendo señal (un worker que declara sus sitios cuenta
        # también los que le fallaron), solo que de otra cosa.
        "n_sites_reported": n_sites,
        "note": str(d.get("note") or "")[:120],
    }


def mechanism_report(all_events: list[dict], expected_signals: list[str],
                     concurrency: ConcurrencyTracker | None = None,
                     scheduled: dict | None = None, forbidden_signals: list[str] | None = None) -> dict:
    """Structured, transcript-independent record of what actually happened this scenario."""
    families = families_in(all_events)
    missing = [f for f in expected_signals if f not in families]
    # Doing TOO MUCH is a mechanism failure too, and it needs to be a measured fact rather than a line of
    # prose the judge may or may not weigh.
    overreach = [f for f in (forbidden_signals or []) if f in families]
    task_id = find_navegador_task_id(all_events)
    task_view: dict = {}
    if task_id:
        task_view = poll_navegador_task(task_id)
    out = {
        "families_observed": sorted(families),
        "expected_signals": expected_signals,
        "missing_signals": missing,
        "forbidden_signals": list(forbidden_signals or []),
        "overreach_signals": overreach,
        "navegador_task_id": task_id,
        "navegador_task": task_view,
        # Los ids salen de `sheet_instances` para que los dos lectores no puedan apuntar a cajas distintas.
        "results_sheet": results_sheet((sheet_instances(all_events) or {}).get("ids")),
        # CUÁNTAS hojas, no solo qué había en la hoja. La regla del operador es una caja por encargo, y con la
        # hoja única de hoy el informe no podía siquiera enseñar que dos búsquedas compartían una.
        "sheet_instances": sheet_instances(all_events),
        # ONLY WHAT HAS TO OPEN, OPENS (operator, 2026-08-21): cards that appeared without any errand asking
        # for them. Measured apart from `sheet_instances` because the question is the opposite one: there
        # boxes are MISSING, here one is LEFT OVER.
        "ghost_widgets": ghost_widgets(all_events),
        "n_events": len(all_events),
        "search_health": search_health(all_events),
        "dropped_actions": dropped_actions(all_events),
        # Qué widget se tocó y cómo. Sin esto, «la cita no está en la agenda» solo se podía inferir del
        # bloque de CRONS, que no habla de agendas.
        "widget_ops": widget_ops(all_events),
        # The full walk of the stream, not just which families showed up. A case does NOT close with
        # anomalies here, however good the transcript reads — see `tick`.
        "audit": audit(all_events, expected_signals),
    }
    if scheduled is not None:
        out["scheduled_jobs"] = scheduled
    if concurrency is not None:
        out["task_registry"] = concurrency.report()
    return out


# ── WHAT THE AGENT HAD IN FRONT OF IT ──────────────────────────────────────────────────────────────────────
# The most expensive class of false finding in this suite is not "the judge was harsh", it is the judge
# asserting something the harness never measured — three retractions on 2026-08-20, all of that shape. The
# sharpest instance: a round was reported as "narrated normality over a blocked state", the memory agent spent
# an investigation proving the datum WAS written and returned, and the engine agent had to read the code to
# say where it reached. All three of us were reasoning about one thing nobody had read: the prompt the model
# actually got.
#
# It is durable and it is one query away. Every `turn.completed` event carries the full `system_prompt` and the
# window size, so the question "did it have this in front of it?" is answerable instead of arguable. Reading it
# turns two different findings into two different owners: shown-and-ignored is conduct, never-shown is
# plumbing, and today those were told apart by hand.
#
# Not served by `/api/observability/events`: that route is hardcoded to `topic = 'observer'`, so the turn rows
# are invisible to it. Rather than ask for an engine change for the harness's benefit, this reads the sandbox's
# own DB — which the suite already keeps on disk for exactly this kind of inspection. Live-engine runs simply
# get nothing, which is the honest answer there.
_NAV_MARK = "NAVEGADOR — YA EN CURSO"
# A worker that DIED is in the prompt too, on its own line: `TAREAS DE FONDO — YA ACABADAS: «…» FALLÓ`. Reading
# it is what separates the two halves of the day's dominant defect — the notice not being delivered (plumbing,
# fixed on 2026-08-20) from the notice being delivered and not said (obedience, still open). Measured in
# `book-hotel-night-known__es`: the prompt carried both the anti-robot wall and a failed background task while
# the turn kept promising progress.
_DONE_MARK = "TAREAS DE FONDO — YA ACABADAS"
_ALERT = ("⛔", "❓", "bloque", "captcha", "no puedo seguir", "confirm")


def prompt_context(db_path, *, since: float = 0.0, limit: int = 40) -> list[dict]:
    """Per turn, what the model was shown: window size, prompt size, and the browser-task line verbatim.

    `since` scopes to one scenario inside a batch that shares an engine (epoch seconds). Fails soft to `[]`:
    this is evidence that makes a verdict better, never a reason to lose one.
    """
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return []
    out: list[dict] = []
    try:
        rows = con.execute(
            "SELECT ts_ms, payload FROM events WHERE topic = 'turn.completed' AND ts_ms >= ? "
            "ORDER BY ts_ms ASC LIMIT ?", (int(since * 1000), int(limit))).fetchall()
    except Exception:
        return []
    finally:
        con.close()
    for i, (ts_ms, raw) in enumerate(rows):
        try:
            p = json.loads(raw)
        except Exception:
            continue
        sp = p.get("system_prompt") or ""
        nav = next((l.strip() for l in sp.splitlines() if _NAV_MARK in l), "")
        shown = nav.split("último:", 1)[1].strip() if "último:" in nav else ""
        done = next((l.strip() for l in sp.splitlines() if _DONE_MARK in l), "")
        live = next((l.strip() for l in sp.splitlines() if _LIVE_MARK in l), "")
        failed = "FALLÓ" in done
        out.append({"turn": i, "at_ms": ts_ms, "window_msgs": p.get("window_msgs"), "system_chars": len(sp),
                    "task_line": nav[:300], "shown_state": shown[:200], "live_line": live[:400],
                    "failed_task_line": done[:240] if failed else "",
                    "alert": any(a in shown.lower() or a in shown for a in _ALERT) or failed})
    return out


_LIVE_MARK = "TAREAS DE FONDO EN CURSO"
_MIN_OBJECTIVE = 24          # shorter than this, two objectives can collide by accident


def _objectives(line: str) -> list[str]:
    """Every «…» objective quoted in one prompt line, trimmed of the trailing ellipsis the renderer adds."""
    return [o.strip().rstrip("…. ") for o in re.findall(r"«([^»]*)»", line or "")]


def _same_objective(a: str, b: str) -> bool:
    """Two renderings of the SAME objective.

    Not equality: the two blocks truncate at different widths, so the live line can read
    «… 4 noches, con » while the finished line reads «… 4 no». Prefix comparison, with a floor,
    because a short prefix ("Busca") would match unrelated errands.
    """
    x, y = a.strip(), b.strip()
    if len(x) < _MIN_OBJECTIVE or len(y) < _MIN_OBJECTIVE:
        return False
    return x.startswith(y) or y.startswith(x)


def prompt_contradictions(prompt_rows: list[dict]) -> list[dict]:
    """Turns whose prompt said the SAME errand was both running and finished.

    This is a fault of the PROMPT, not of the turn, and it has to be reported apart from obedience:
    measured on 2026-08-20, seven of eight turns carried the same objective string in
    «TAREAS DE FONDO EN CURSO» (alive, 40%) and in «TAREAS DE FONDO — YA ACABADAS» (FAILED) at once.
    A turn answering "still waiting for results" there is not disobeying — it is resolving a
    contradiction, and resolving it correctly. Scoring obedience over a self-contradicting prompt
    measures the harness's own blindness, so this runs FIRST and, when it fires, the obedience
    reading of that turn is void.

    Needs the raw block lines, so `prompt_context` must carry them: `live_line` / `failed_task_line`.
    """
    out: list[dict] = []
    for row in prompt_rows or []:
        live = _objectives(row.get("live_line") or "")
        done = _objectives(row.get("failed_task_line") or "")
        clash = [a for a in live for b in done if _same_objective(a, b)]
        if clash:
            out.append({"turn": row.get("turn"), "objective": clash[0][:120], "n": len(clash),
                        "kind": "alive_and_finished"})
        found = _found_vs_empty(row)
        if found:
            out.append({"turn": row.get("turn"), "objective": found[:120], "n": 1,
                        "kind": "found_and_empty"})
    return out


#: What the browser block writes when the worker has already kept candidates (`prompt.py`, V2-200).
_HAS_RESULTS_MARK = "YA TIENE RESULTADOS"
#: What the live block writes when it knows the errand has brought something in (V2-222, third face).
_FOUND_MARK = "YA HA ENCONTRADO"


def _found_vs_empty(row: dict) -> str:
    """The SECOND contradiction family, measured on `search-secondhand-monitor__es` (2026-08-23 23:24).

    Same errand, two registries, opposite claims IN ONE PROMPT: the browser block said «YA TIENE
    RESULTADOS … DÁSELOS en este turno» while the live block said «en cola (llevas 23s)» and «la respuesta
    es que TODAVÍA NO LO SABES». The turn answered "I'll tell you when I have results" with 35 real
    listings on the sheet — and was graded as three [alta] acts of disobedience.

    It was not disobedience. Same reasoning as the family above: a self-contradicting prompt has no
    obedient answer, so the obedience reading of that turn is void and this has to be reported apart.

    Fires only when the live block carries NEITHER of the two things that would make it agree: the
    found-marker (V2-222's third face) or a step note saying something already landed. Its absence is the
    whole defect — a live block that mentions the candidates is not contradicting anything.
    """
    task = row.get("task_line") or ""
    live = row.get("live_line") or ""
    if _HAS_RESULTS_MARK not in task or _FOUND_MARK in live:
        return ""
    for a in _objectives(task):
        for b in _objectives(live):
            if _same_objective(a, b):
                return a
    return ""


def memory_language(db_path="") -> dict:
    """The CANONICAL language the memory distils pills in — asked of the engine, not assumed.

    Worth the query because assuming it cost a false finding on 2026-08-20: an ES scenario seeded "me da
    vértigo la altura", the harness grepped the turn's prompt for "vértigo" and concluded the preference had
    never reached the model. It had — as "The operator has a fear of heights", because the memory is monolingual
    in the operator's canonical language and that sandbox's was still `en`. The datum was there, in the language
    nobody looked in.

    Two levels, and mixing them is the trap: `state.language` is stored `null` when nobody chose explicitly, and
    `state.read()` resolves that against the active configuration. So the raw row can say null while the
    distiller writes Spanish. The engine is asked first (`/api/memory/map`, already resolved); the row is only a
    fallback, and then `explicit=False` says the value was never pinned.

    Returns `{"effective": <code>, "explicit": bool, "source": "engine"|"db"|""}`.
    """
    try:
        st = (probe_client.memory_map() or {}).get("state") or {}
        code = str(st.get("language") or "").strip()
        if code:
            return {"effective": code, "explicit": True, "source": "engine"}
    except Exception:
        pass
    if not db_path:
        return {"effective": "", "explicit": False, "source": ""}
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return {"effective": "", "explicit": False, "source": ""}
    try:
        row = con.execute("SELECT data FROM state LIMIT 1").fetchone()
    except Exception:
        return {"effective": "", "explicit": False, "source": ""}
    finally:
        con.close()
    try:
        code = str((json.loads(row[0]) or {}).get("language") or "").strip() if row else ""
    except Exception:
        code = ""
    return {"effective": code, "explicit": bool(code), "source": "db"}


def proactive_notes(db_path, *, since: float = 0.0, limit: int = 40) -> list[dict]:
    """The notes the engine PUSHED at the conversation (`📩 system note → FlashBrain`), with their clock.

    This is the instrument for the contrast measured on 2026-08-20, inside one conversation, one model, one turn
    budget:

        19:43:31  system note («el proceso pregunta: ¿A qué ciudad…?»)
        19:43:34  turn 1 relayed it, almost verbatim              → said in 3 seconds
        (no note)  the FAILED task, rendered only as a prompt state line, 7 turns running
                   turns 1-7 said "sigo esperando", "te aviso"    → 0 of 7

    Same information, two delivery paths, opposite outcomes — and the losing path was imperative and in capitals.
    That is what turned "the model disobeys" into "one kind of fact has a delivery path and the other does not",
    which is a different fix with a different owner. It was hand-queried three times before earning a place here.
    """
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return []
    try:
        rows = con.execute(
            "SELECT ts_ms, payload FROM events WHERE topic = 'observer' AND label LIKE '%system note%' "
            "AND ts_ms >= ? ORDER BY ts_ms ASC LIMIT ?", (int(since * 1000), int(limit))).fetchall()
    except Exception:
        return []
    finally:
        con.close()
    out = []
    for ts_ms, raw in rows:
        try:
            txt = str((json.loads(raw) or {}).get("text") or "")
        except Exception:
            txt = ""
        out.append({"at_ms": ts_ms, "text": txt[:300]})
    return out


def note_coverage(prompt_rows: list[dict], notes: list[dict]) -> dict:
    """Of the turns that had something to report, how many were PUSHED a note first.

    The three stretches the fixing agent asked for, separated: the mechanism marked it (their side), it reached
    the prompt (`prompt_context`), and a note was pushed (here). Whether it came out of the mouth is the judge's
    call on the transcript — the harness must not guess at that one.
    """
    alerts = [r for r in prompt_rows if r.get("alert")]
    if not alerts:
        return {"alert_turns": 0, "with_note": 0, "notes": len(notes)}
    with_note = 0
    for r in alerts:
        at = r.get("at_ms") or 0
        # A note counts for a turn if it landed BEFORE it and after the previous turn: that is the window in
        # which it could have changed what this turn said.
        prev = max((x.get("at_ms") or 0) for x in prompt_rows if (x.get("at_ms") or 0) < at) if any(
            (x.get("at_ms") or 0) < at for x in prompt_rows) else 0
        if any(prev < (n["at_ms"] or 0) <= at for n in notes):
            with_note += 1
    return {"alert_turns": len(alerts), "with_note": with_note, "notes": len(notes)}


def navegador_task_is_live() -> bool:
    """Is there a browser task still working RIGHT NOW? Fails soft to False.

    Used to decide whether closing the conversation would end it as a race between the turn budget and the
    browser (see the grace block in `run._run_scenario`). Conservative on purpose: an unreadable engine reads as
    "not live", because granting extra turns on a guess would stretch every round.
    """
    try:
        tasks = probe_client.live_tasks()
    except Exception:
        return False
    for t in tasks or []:
        if str(t.get("kind") or "") == "navegador" and str(t.get("status") or "") in ("working", "needs_input"):
            return True
    return False


def _items_in(txt: str) -> list[dict]:
    """Every COMPLETE `{...}` object in a JSON array that may have been cut off mid-flight.

    `json.loads` on the whole string is not enough and the failure is silent: the observer caps an event's
    text at 1500 characters, so a browser extraction with several hits arrives as a valid prefix and a
    severed tail. On 2026-08-20 that swallowed the only real answer of the round — «Bécquer, 100 €» with a
    live Google Travel URL, the 4-star hotel the case is about — and the report said the browser had found
    nothing but an ad for a flamenco show. The judge then scored the round for delivering junk while the
    product had actually delivered. Same shape as the truncated tool call of V2-171: a cut payload must be
    salvaged, never dropped.
    """
    out: list[dict] = []
    if not txt or "{" not in txt:
        return out
    depth = start = 0
    in_str = esc = False
    for i, ch in enumerate(txt):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(txt[start:i + 1])
                except Exception:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
            elif depth < 0:            # a severed head: resynchronise instead of giving up
                depth = 0
    # AND THE OBJECT THE CUT LANDED IN. Not a nicety: the junk arrives first and the answer arrives last, so
    # the severed object is exactly where the useful hit tends to be. On 2026-08-20 «Bécquer, 100 €» sat at
    # character 801 of a 1500-character cap with a Google Travel URL long enough to push its own closing brace
    # past the end — the one 4-star hotel of the round, unreadable by any strict parser. Title and price are
    # what answer the question «did the browser find one?»; a lost URL does not change that answer.
    if depth > 0 and start >= 0:
        frag = txt[start:]
        got = {k: m.group(1) for k, m in
               ((k, re.search(r'"' + k + r'"\s*:\s*"([^"]*)"', frag)) for k in ("title", "price", "url"))
               if m}
        if got.get("title"):
            got["partial"] = True
            out.append(got)
    return out


def worker_outcome(db_path, *, since: float = 0.0) -> dict:
    """WHAT THE WORKER ACHIEVED, and whether any of it reached the user.

    Three rounds of `hotel-under-15-days` scored 2/5 with three different stories underneath: one where the
    worker probed its own CLI and never searched, one where it navigated Booking with perfect parameters and
    extracted «Exe Sevilla Macarena, 65 €» with a URL, and one where it spent the round asking permission to
    clear a Booking filter. Same number, three mechanisms — so a single round cannot validate a fix, and reading
    three of them by hand was how that got noticed at all.

    `found` is what the browser actually extracted; `delivered` is whether its title ever appears in something
    zaelar SAID. The gap between those two is the defect the whole CID is about, so it belongs in the report
    rather than in whoever happens to open the stream.
    """
    import sqlite3
    out: dict = {"navigations": 0, "extractions": 0, "found": [], "n_found": 0}
    seen: set[str] = set()
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    try:
        rows = con.execute("SELECT label, payload FROM events WHERE topic = 'observer' AND ts_ms >= ? "
                           "AND kind = 'navegador' ORDER BY ts_ms ASC", (int(since * 1000),)).fetchall()
    except Exception:
        return out
    finally:
        con.close()
    for label, raw in rows:
        lab = label or ""
        if lab == "navigate":
            out["navigations"] += 1
        if "resultados" in lab:
            out["extractions"] += 1
        try:
            txt = str((json.loads(raw) or {}).get("text") or "")
        except Exception:
            continue
        if "{" in txt:
            for it in _items_in(txt):
                if it.get("title"):
                    out["n_found"] += 1
                    # DISTINCT titles, capped — not the first N rows. The junk arrives FIRST and repeats: on
                    # 2026-08-20 the same ad («Experiencia Premium en el Teatro Flamenco Sevilla, € 25») came
                    # back on four consecutive extractions and filled a cap of 4, so «Bécquer, 100 €» — the
                    # 4-star hotel the case is about, extracted later in the same round — was counted in
                    # `n_found` and never shown in `found`. A cap that keeps the earliest rows reports exactly
                    # the noise and hides the answer.
                    key = str(it.get("title") or "").strip().lower()
                    if key not in seen and len(out["found"]) < 6:
                        seen.add(key)
                        out["found"].append({k: str(it.get(k) or "")[:120] for k in ("title", "price", "url")})
    return out


def was_delivered(found: list | None, transcript: list[dict]) -> bool | None:
    """Did ANY of what the brain was OFFERED appear in something zaelar SAID? `None` when nothing was offered.

    Pass `offered_to_brain(...)["titles"]` here, not the browser's extraction. Judging against the extraction
    blames the turn for withholding rows that never reached it — see `offered_to_brain` for the round where
    this instrument did exactly that.
    """
    if not found:
        return None
    said = " ".join((t.get("text") or "") for t in transcript if t.get("who") == "zaelar").lower()
    for it in found:
        title = str((it or {}).get("title") or "").lower()
        # Match on the distinctive head of the title: an extracted title often carries trailing marketing a
        # human reply would never repeat verbatim.
        head = " ".join(title.split()[:3])
        if head and head in said:
            return True
    return False

_NUMERIC_HEAD = re.compile(r"^[\d.,%\s€$-]+$")


def offered_to_brain(db_path, *, since: float = 0.0) -> dict:
    """WHAT THE NOTE ACTUALLY CARRIED — which is not what the browser extracted, and that gap is a defect.

    On 2026-08-20 this instrument accused the product of hiding three real 99 EUR monitors. It had not
    hidden them: `widgets/navegador/act_api.py` built the note with `items[:3]` in DOM order, and category
    links come before product cards in every listing page there is, so rows 4-6 — the answer — were never
    in the note. The turn described faithfully the only three rows it was given.

    Judging delivery against what the BROWSER found therefore invents a behavioural defect out of a
    truncation. So `worker_outcome` keeps reporting everything extracted (the truncation has to be visible
    somewhere), and delivery is judged against this: the titles the brain was actually offered.
    """
    import sqlite3
    out: dict = {"notes": 0, "titles": [], "named": [], "n_offered": 0}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    try:
        rows = con.execute("SELECT payload FROM events WHERE topic = 'observer' AND ts_ms >= ? "
                           "AND kind = 'brain' ORDER BY ts_ms ASC", (int(since * 1000),)).fetchall()
    except Exception:
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass
    seen: set[str] = set()
    for (raw,) in rows:
        try:
            txt = str((json.loads(raw) or {}).get("text") or "")
        except Exception:
            continue
        if "SACADO" not in txt:
            continue
        out["notes"] += 1
        # The note lists rows as «title — price — url», joined by "; ", between "página, trabajando en
        # «goal»: " and the trailing ". Nadie más lo sabe". Parse that span only: the instruction prose
        # after it also contains words like "resultado" and would otherwise be read as a finding.
        m = re.search(r"»\s*:\s*(.+?)\.\s*Nadie", txt, re.S)
        if not m:
            continue
        for chunk in m.group(1).split(";"):
            head = chunk.strip().split(" — ")[0].strip()
            if not head or head.startswith("http"):
                continue
            key = head.lower()
            if key not in seen:
                seen.add(key)
                out["titles"].append(head[:120])
                # A row whose "title" is a bare number has no identity either: on 2026-08-21 the extractor
                # split «169,00 €» across the two fields, so the note read «169 — 00 € — <url>». Counting
                # that as a named result would report the note as carrying three findings when it carried
                # three price fragments — and would hide the extractor defect behind a healthy-looking count.
                if not _NUMERIC_HEAD.match(head):
                    out["named"].append(head[:120])
    out["n_offered"] = len(out["titles"])
    out["n_named"] = len(out["named"])
    return out


def worker_health(db_path, *, since: float = 0.0) -> dict:
    """HOW MANY WORKERS ACTUALLY SURVIVED. Read on 2026-08-21 for the first time, and it was overdue.

    `cheapest-monitor` that night: 8 spawned, 3 ok, 3 errored, 2 cancelled by the harness's own shutdown.
    Zaelar told the
    user "la búsqueda que estaba en marcha se ha caído sin terminar" — the truth — and the round scored it
    as vagueness, because the report had no column saying five workers had died. A harness that cannot see
    a failure will score honesty about that failure as evasion.
    """
    import sqlite3
    out: dict = {"spawned": 0, "ok": 0, "errored": 0, "cancelled": 0, "cancelled_by_shutdown": 0,
                 "relayed": 0, "still_running": 0}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    try:
        out["spawned"] = con.execute("SELECT COUNT(*) FROM events WHERE topic = 'worker.spawned' "
                                     "AND ts_ms >= ?", (int(since * 1000),)).fetchone()[0]
        # WHY it ended, not just that it did. `ok:false` alone conflates two very different things, and the
        # first reading of this metric handed the fixing agent a phantom: of five «dead» workers, two were
        # `cancelled` with `reason: shutdown` — the harness tearing the sandbox down at the end of the round,
        # with the worker still legitimately working. That is the TEST ending, not the product failing.
        for (raw,) in con.execute("SELECT payload FROM events WHERE topic = 'worker.done' AND ts_ms >= ?",
                                  (int(since * 1000),)).fetchall():
            try:
                d = json.loads(raw) or {}
            except Exception:
                continue
            status = str(d.get("status") or ("ok" if d.get("ok") else "error"))
            if d.get("ok"):
                out["ok"] += 1
            elif status == "cancelled":
                out["cancelled"] += 1
            elif status == "relevada" or d.get("handoff"):
                # A PROVIDER RELAY IS NOT A DEATH. Until V2-238 it closed with ok=false/status=error, so
                # this column counted it as one — and the round of 2026-08-21 reported a second failure
                # signature at ~1450 ms that was the relay working, not a worker dying. It also cost the
                # product twice over: the brain was told the task had died while the relay was running,
                # and the resume logic read the same ok=false and escalated twice for one handoff.
                out["relayed"] += 1
            else:
                out["errored"] += 1
        # STILL WORKING when the round was judged. This reading happens DURING the round, so a worker that
        # has not finished yet has no terminal event — and without this line the report said «4 spawned, 0
        # ok», which reads as four failures. In the round of 2026-08-21 00:29 exactly one had errored (at
        # +46s) and three were alive; their `cancelled` rows were written at +434s, all in the same instant,
        # when the harness tore the sandbox down. Three product failures invented by the clock.
        for (raw,) in con.execute("SELECT payload FROM events WHERE topic = 'worker.cancelled' AND ts_ms >= ?",
                                  (int(since * 1000),)).fetchall():
            try:
                if str((json.loads(raw) or {}).get("reason") or "") == "shutdown":
                    out["cancelled_by_shutdown"] += 1
            except Exception:
                continue
        out["still_running"] = max(0, out["spawned"] - out["ok"] - out["errored"]
                                    - out["cancelled"] - out["relayed"])
    except Exception:
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass
    return out


def duplicate_errands(db_path, *, since: float = 0.0, floor: float = 0.5) -> dict:
    """HOW MANY WORKERS RAN THE SAME ERRAND, and how alike their goals were.

    Measured live on 2026-08-21 with the operator's screenshot in hand: `kid-friendly-activity-nearby__es`
    is a SINGLE search and the lab had FOUR workers on it, each opening its own sheet — five cards on
    screen for one request, which is what he read as "five jobs at once". The two that finished cost $3.78
    and $3.93: one errand billed four times. `worker_health` said "4 spawned", and four spawns read as
    healthy concurrency.

    Grouped by CONTAINMENT (shared words over the SHORTER request), not by Jaccard, and that is the whole
    point. The brain REFORMULATES the errand on each escalation with a different amount of detail — the four
    kid-friendly requests are 668, 437, 342 and 298 characters — and Jaccard divides by the UNION, so the
    more the brain elaborates the less alike one errand looks to itself. Measured on those same four:
    Jaccard 0.319-0.450 (would be dismissed), containment 0.571-0.893. Against unrelated errands
    (plumber/hotel, flight/second-hand cars, Netflix/kids' plans) containment stays at 0.062-0.227, so the
    two populations do not overlap — it is not a looser bar, it is a bar that survives length.

    The Jaccard value is REPORTED alongside because that is the engine's own dedup metric (`find_duplicate`,
    >= 0.60 of content words, V2-123), and the report has to be able to say WHICH of the two defects this
    is: a pair above 0.60 that still spawned is a dedup that did not fire, a pair below it is a dedup that
    could not tell. Reporting only the harness number describes the symptom and names the wrong culprit.

    ⚠️ IT READS `escalate.requested`, NOT `worker.spawned`, AND THAT IS THE WHOLE ACCURACY OF THE NUMBER.
    The spawn event stores its `goal` TRUNCATED TO 120 CHARACTERS, and reformulations of one errand share a
    long opening — so a prefix comparison measures the part they have in common and calls it similarity.
    Read that way the four kid-friendly requests scored 0.647-0.80 and were reported to the engine agent as
    "above your 0.60 bar, your dedup is not firing". On the FULL text they are 0.319-0.450: the dedup had
    behaved correctly and the real defect was the paraphrase gap. Reading a truncated field does not fail —
    it manufactures a finding, and this one had already been sent. When only the truncated field exists the
    result says so (`text_source`), because a similarity read off a prefix is a CEILING, never a measurement.

    ⚠️ AND IT DROPS THE CONTINUATIONS OF ONE ERRAND — a provider relay (V2-238) and a context handoff
    (V2-117) relaunch the SAME goal on purpose, so their containment is 1.0 BY CONSTRUCTION and no bar can
    ever tell them apart from a real duplicate. They are reported apart in `continuations`, with their
    reason: the token cost is real and stays visible, but calling it a dedup failure sends whoever reads it
    to a mechanism that behaved correctly — the same reading `worker_health.relayed` already had, in a
    column of the same report.
    """
    import sqlite3
    out: dict = {"read": False, "n_spawned": 0, "groups": [], "worst": 0, "identical_repeats": 0,
                 "text_source": "", "truncated_source": False, "continuations": [],
                 "continuations_visible": False}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    def _texts(topic: str, field: str) -> list:
        try:
            rows = con.execute(f"SELECT payload FROM events WHERE topic = '{topic}' AND ts_ms >= ? "
                               "ORDER BY ts_ms", (int(since * 1000),)).fetchall()
        except Exception:
            return []
        got = []
        for (raw,) in rows:
            try:
                t = str((json.loads(raw) or {}).get(field) or "").strip()
            except Exception:
                continue
            if t:
                got.append(t)
        return got

    def _stamped(topic: str, field: str) -> list:
        try:
            rows = con.execute(f"SELECT payload, ts_ms FROM events WHERE topic = '{topic}' AND ts_ms >= ? "
                               "ORDER BY ts_ms", (int(since * 1000),)).fetchall()
        except Exception:
            return []
        got = []
        for raw, ts in rows:
            try:
                d = json.loads(raw) or {}
                t = str(d.get(field) or "").strip()
                src = str(((d.get("context") or {}) if isinstance(d.get("context"), dict) else {}).get("src") or "")
            except Exception:
                continue
            if t:
                got.append((ts, t, src))
        return got

    try:
        spawned = _texts("worker.spawned", "goal")
        spawn_ts = [ts for ts, _t, _s in _stamped("worker.spawned", "goal")]
        # SOLO las escaladas que llegaron a NACER. Una escalada DEDUPLICADA deja su `escalate.requested` y
        # ningún worker: contarla acusaría al dedup justo de los casos en los que funcionó — la forma exacta
        # del error anterior, un lector apuntado al sitio equivocado que fabrica el hallazgo en vez de fallar.
        born = [(t, src) for ts, t, src in _stamped("escalate.requested", "request")
                if any(0 <= s_ts - ts < 25000 for s_ts in spawn_ts)]
    finally:
        try:
            con.close()
        except Exception:
            pass
    out["read"] = True
    out["n_spawned"] = len(spawned)
    # UNA CONTINUACIÓN NO ES UN DUPLICADO, y su goal es IDÉNTICO POR CONSTRUCCIÓN. Medido en
    # `search-secondhand-monitor__es` (2026-08-23 23:24): dos workers, contención 1,0, reportados como «2
    # workers para UN encargo · se paga entero cada vez» — y el segundo era el RELEVO por proveedor sin cuota
    # que V2-238 construyó a propósito, el mismo que la columna de al lado (`worker_health.relayed`) ya sabía
    # llamar por su nombre. Dos lecturas del mismo hecho en el mismo informe, una acusando al producto.
    #
    # Peor que un falso positivo suelto: el relevo RELANZA `rec.goal` literal, así que la contención es 1,0
    # SIEMPRE — este detector no puede dejar de disparar sobre un relevo por mucho que se afine la vara. Y el
    # dedup del motor tampoco es el culpable: `find_duplicate` corre en `run_listener` sobre las sesiones
    # VIVAS, y quien releva ya se está muriendo.
    #
    # El coste NO se esconde: un relevo sí paga dos veces en tokens (el primer worker trabajó antes de
    # quedarse sin gasolina). Se cuenta aparte, con su motivo, para que siga siendo visible sin leerse como
    # un fallo de dedup — que manda a mirar el sitio equivocado.
    _CONTINUATIONS = {"provider_failover": "relevo de proveedor (V2-238)",
                      "context_handoff": "contexto agotado → sesión nueva (V2-117)"}
    cont = [(t, src) for t, src in born if src in _CONTINUATIONS]
    asked = [t for t, src in born if src not in _CONTINUATIONS]
    out["continuations"] = [{"src": src, "why": _CONTINUATIONS[src]} for _t, src in cont]
    # The full request when it exists; the truncated goal only as a fallback, and labelled as such.
    goals = asked or spawned
    out["text_source"] = ("escalate.requested (solo las que nacieron, sin continuaciones)" if born
                          else "worker.spawned.goal (TRUNCADO a 120 · techo)")
    out["truncated_source"] = not born
    # El `goal` del spawn NO dice de dónde viene, así que por esa vía un relevo es indistinguible de un
    # duplicado. Decirlo es la diferencia entre un número y un número con su margen: callarlo devuelve el
    # falso positivo con otra cara.
    out["continuations_visible"] = bool(born)
    if len(goals) < 2:
        return out

    def _jac(a: set, b: set) -> float:
        u = len(a | b)
        return (len(a & b) / u) if u else 0.0

    def _words(g: str) -> set:
        g = unicodedata.normalize("NFKD", g.lower())
        g = "".join(c for c in g if not unicodedata.combining(c))
        return {w for w in re.findall(r"[a-z0-9]+", g) if len(w) >= 4}

    ws = [_words(g) for g in goals]
    # Single-linkage: A with B and B with C puts the three together even when A and C alone fall short —
    # four reformulations of one errand drift apart at the ends, and pairwise-only would split them into
    # pairs and under-report the cost.
    parent = list(range(len(goals)))

    def _find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # LA VARA DEL MOTOR SE LE PREGUNTA AL MOTOR. Este informe llevaba escrito «jaccard del motor ≥ 0,60» y
    # las dos mitades eran falsas desde el mismo 2026-08-23: `find_duplicate` dejó de usar Jaccard (divide por
    # la UNIÓN, así que una reformulación más larga se ve distinta por ser más larga) y pasó a CONTENCIÓN con
    # la vara en 0,45. O sea que el informe podía tener razón en que había un duplicado y aun así mandar a
    # mirar una métrica que ya no gobierna nada. Un número copiado a mano deriva en silencio; leído de su
    # fuente, no puede.
    try:
        from nucleo import matching as _m
        _engine_bar = float(_m.SAME_ERRAND)
        _engine_metric = "contención"
    except Exception:
        _engine_bar, _engine_metric = 0.0, ""

    sims: dict = {}
    for i in range(len(goals)):
        for j in range(i + 1, len(goals)):
            a, b = ws[i], ws[j]
            if not a or not b:
                continue
            sim = len(a & b) / max(1, min(len(a), len(b)))     # CONTENCIÓN, no Jaccard
            if sim >= floor:
                sims[(i, j)] = (round(sim, 3), round(_jac(a, b), 3))
                parent[_find(i)] = _find(j)
    clusters: dict = {}
    for i in range(len(goals)):
        clusters.setdefault(_find(i), []).append(i)
    for members in clusters.values():
        if len(members) < 2:
            continue
        pair = [v for (i, j), v in sims.items() if i in members and j in members]
        texts = [goals[i] for i in members]
        jacs = [j for _c, j in pair]
        out["groups"].append({
            "n": len(members),
            "goal": texts[0][:110],
            "identical": len(set(texts)) == 1,
            "min_sim": min((c for c, _j in pair), default=None),
            "max_sim": max((c for c, _j in pair), default=None),
            # Jaccard se sigue reportando porque separa las dos poblaciones al mirarlas (mismo encargo
            # 0,319-0,450 · distintos 0,062-0,227) — pero YA NO es la vara del motor y no decide nada aquí.
            "jaccard_max": max(jacs, default=None),
            # A cuál de los dos defectos apunta el grupo, medido contra la vara REAL del motor.
            "engine_metric": _engine_metric,
            "engine_bar": _engine_bar or None,
            "over_engine_bar": bool(_engine_bar and max((c for c, _j in pair), default=0.0) >= _engine_bar),
        })
        if len(set(texts)) == 1:
            out["identical_repeats"] += len(members) - 1
    out["groups"].sort(key=lambda g: -g["n"])
    out["worst"] = max((g["n"] for g in out["groups"]), default=0)
    return out


def wait_for_quiescence(db_path, *, max_wait: float = 60.0, quiet_for: float = 6.0,
                        poll: float = 2.0) -> dict:
    """Wait until the engine STOPS writing events, so the mechanism is read after the round, not during it.

    Three separate findings were misread this way in one night, all the same shape — a column read while the
    system was still emitting, reported as if the system had finished:

      · `worker_health` said «4 spawned, 0 ok», which reads as four failures. One had errored; three were
        still working, and their terminal rows landed 434 s later, all in the same instant, at shutdown.
      · `worker_deaths` listed a corpse that was a provider handoff still in flight.
      · `notes_from_search` said 0 with twelve search answers on the wire — the notes were queued six
        seconds after the read, and it looked like a delivery fix had regressed.

    Every one of those went out to the fixing agent before being caught. So the rule is not «wait longer»,
    which only moves the race: it is to wait for the store to go QUIET, and to say in the report how long
    that took and whether it ever did. A round that never settles is itself worth knowing about — that is a
    worker still running when the conversation ended, which is a finding and not a defect.
    """
    import sqlite3
    t0 = time.time()
    last_n, last_change = -1, t0
    while True:
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            n = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            # WORK IN FLIGHT, asked as a question about the work and not about the clock. Silence alone is
            # ambiguous: a store quiet because nothing has STARTED looks exactly like one quiet because
            # everything finished, and the first draft of this function stopped on the first gap and missed
            # the write that came right after — caught by its own test before it ever ran for real.
            spawned = con.execute("SELECT COUNT(*) FROM events WHERE topic = 'worker.spawned'").fetchone()[0]
            done = con.execute("SELECT COUNT(*) FROM events WHERE topic = 'worker.done'").fetchone()[0]
            con.close()
        except Exception:
            return {"settled": None, "waited_s": round(time.time() - t0, 1), "events": None}
        now = time.time()
        pending = max(0, spawned - done)
        if n != last_n:
            last_n, last_change = n, now
        elif not pending and now - last_change >= quiet_for:
            return {"settled": True, "waited_s": round(now - t0, 1), "events": n, "pending_workers": 0}
        if now - t0 >= max_wait:
            return {"settled": False, "waited_s": round(now - t0, 1), "events": n,
                    "pending_workers": pending,
                    "note": (f"{pending} worker(s) sin final al agotarse la espera: hay trabajo vivo"
                             if pending else "el motor seguía escribiendo al agotarse la espera")}
        time.sleep(poll)


def worker_deaths(db_path, *, since: float = 0.0) -> dict:
    """WHY THE DEAD WORKERS DIED — the cross-reference that found the cause of a whole family of cases.

    A worker that ends in error emits nothing saying why: its `task|end` carries an empty text and the
    model name, and that is all. On 2026-08-21 the round of `best-plumber-same-day` reported four dead
    workers out of six with no cause anywhere in the event store — and the only error events in it
    (a permission gate, a Playwright detach) belonged to worker 2, which SURVIVED. Reading the panel would
    have blamed those.

    The cause came from crossing the store with the engine's own log, and the correlation was total:

        worker 3  REANUDA sesión nativa c5ad1d9e…  ->  error at 371 ms
        worker 4  REANUDA sesión nativa c5ad1d9e…  ->  error at 401 ms      (the same session)
        worker 6  REANUDA sesión nativa c5ad1d9e…  ->  error at 374 ms      (the same session)
        workers 2 and 5, fresh session               ->  alive

    Three workers resuming ONE native CLI session; three deaths. Nobody who opened their own died. So this
    reports the split that carries the signal — deaths among resumers vs deaths among fresh starts — rather
    than a count of corpses, which says nothing about the cause.
    """
    import re as _re
    import sqlite3
    from pathlib import Path
    out: dict = {"dead": [], "lifetimes_ms": {}, "sessions": {}, "shared_sessions": {},
                 "dead_resuming": 0, "resuming": 0, "dead_fresh": 0, "fresh": 0}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    spawned: set[str] = set()
    try:
        for (raw,) in con.execute("SELECT payload FROM events WHERE topic = 'worker.spawned' AND ts_ms >= ?",
                                  (int(since * 1000),)).fetchall():
            try:
                spawned.add(str((json.loads(raw) or {}).get("id")))
            except Exception:
                continue
        for (raw,) in con.execute("SELECT payload FROM events WHERE topic = 'worker.done' AND ts_ms >= ?",
                                  (int(since * 1000),)).fetchall():
            try:
                d = json.loads(raw) or {}
            except Exception:
                continue
            # Same exclusions as `worker_health`, and they have to agree: on 2026-08-21 this listed a
            # provider handoff as dead while `worker_health` had already learned to call it `relayed`, so
            # one round reported both «0 errored» and «dead: [1]». Two columns disagreeing about the same
            # worker is worse than either being wrong — the reader has to decide which to believe.
            if (not d.get("ok") and str(d.get("status") or "") not in ("cancelled", "relevada")
                    and not d.get("handoff")):
                out["dead"].append(str(d.get("id")))
        for ts, label, span in con.execute(
                "SELECT ts_ms, label, span FROM events WHERE topic = 'observer' AND kind = 'task' "
                "AND ts_ms >= ? AND label IN ('start', 'end') ORDER BY ts_ms ASC", (int(since * 1000),)):
            wid = str(span or "").replace("worker:", "")
            if not wid:
                continue
            (starts if label == "start" else ends).setdefault(wid, ts)
        for wid, t0 in starts.items():
            if wid in ends:
                out["lifetimes_ms"][wid] = ends[wid] - t0
    except Exception:
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass
    # The resume only shows in the engine's log; the event store never records which native session a
    # worker attached to. Derived from the DB path so the caller needs to know nothing about the layout.
    try:
        log = Path(db_path).resolve().parents[2] / "logs" / "sandbox-engine.log"
        text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    except Exception:
        text = ""
    for m in _re.finditer(r"worker\[(\d+)\]: REANUDA sesi[oó]n nativa ([0-9a-f-]+)", text):
        out["sessions"].setdefault(m.group(2), [])
        if m.group(1) not in out["sessions"][m.group(2)]:
            out["sessions"][m.group(2)].append(m.group(1))
    out["shared_sessions"] = {k: v for k, v in out["sessions"].items() if len(v) > 1}
    resuming = {w for ws in out["sessions"].values() for w in ws}
    dead = set(out["dead"])
    out["resuming"] = len(resuming & spawned) or len(resuming)
    out["dead_resuming"] = len(dead & resuming)
    fresh = (spawned - resuming) if spawned else set()
    out["fresh"] = len(fresh)
    out["dead_fresh"] = len(dead & fresh)
    return out


def search_returns(db_path, *, since: float = 0.0) -> dict:
    """WHAT THE WEB SEARCH BROUGHT BACK, and whether one word of it ever reached the brain.

    This channel was invisible to the harness until an audit of the whole event store on 2026-08-21 — which
    found the instrument was reading 490 of 1291 events. In that round the search returned exactly what the
    operator had asked for, in clean structured text («Philips 27E1N1800A/00 — 27" UHD 4K — 159,00 €»,
    «Alurin CoreVision 27" IPS 4K — 149,99 €»), and NONE of it appeared in a system note, in a turn's prompt
    or in the conversation: five of eight workers died before `_finalize_web` and the good text went with
    them. Meanwhile the whole investigation was running on the browser's mangled rows.

    So this reports what came back and whether the channel has any delivery at all. A search that answers
    the question and never leaves the worker is a delivery defect, not a search defect, and the two get
    opposite fixes.
    """
    import sqlite3
    out: dict = {"queries": 0, "returns": 0, "model_tokens_seen": 0, "notes_from_search": 0, "sample": []}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    try:
        rows = con.execute("SELECT label, payload FROM events WHERE kind = 'search' AND ts_ms >= ? "
                           "ORDER BY ts_ms ASC", (int(since * 1000),)).fetchall()
        # Is there ANY push path from this channel? A note built from a search answer would say so; today
        # every note in the store announces the BROWSER («ha SACADO esto de la página»). Zero here means the
        # question is structural — the channel has no delivery — not that this round happened to be quiet.
        out["notes_from_search"] = con.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'brain' AND ts_ms >= ? AND payload LIKE ?",
            (int(since * 1000), "%búsqueda web%")).fetchone()[0]
        for label, raw in rows:
            try:
                txt = str((json.loads(raw) or {}).get("text") or "")
            except Exception:
                continue
            if "↩" not in str(label or ""):
                out["queries"] += 1
                continue
            out["returns"] += 1
            # The distinctive head of the answer: enough to look for verbatim downstream, short enough that
            # a turn paraphrasing it would still match on the product name.
            head = " ".join(txt.split()[:60])
            if len(out["sample"]) < 3:
                out["sample"].append(head[:200])
            # Did ANY distinctive token of this answer turn up in a system note or a turn's prompt?
            # NAMED CAREFULLY, because the first draft called this «reached_brain» and it is not the same
            # thing: on 2026-08-21 «27US500-W» matched, but it had arrived through the browser's Amazon URL,
            # not through the search answer. A token can land by another route, so this counts SIGHTINGS,
            # and only `notes_from_search` answers whether this channel is delivered at all.
            tokens = [w.strip("*—,.:;()[]\"") for w in txt.split()]
            tokens = [w for w in tokens if len(w) >= 7 and any(c.isdigit() for c in w)][:12]
            landed = False
            for tok in tokens:
                hit = con.execute("SELECT 1 FROM events WHERE ts_ms >= ? AND payload LIKE ? "
                                  "AND (kind = 'brain' OR topic = 'turn.completed') LIMIT 1",
                                  (int(since * 1000), f"%{tok}%")).fetchone()
                if hit:
                    landed = True
                    break
            if landed:
                out["model_tokens_seen"] += 1
    except Exception:
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass
    return out


def progress_phases(db_path, *, since: float = 0.0) -> dict:
    """WHAT THE USER SAW WHILE WAITING, and — the number that matters — the longest silence.

    The requirement this measures is the operator's, and it is about a person, not a pipeline: "si el
    worker tarda, el usuario se aburre; no puede mirar una pantalla en blanco siete minutos". So counting
    phases is not enough: twenty phases in the first ten seconds and then four minutes of nothing is
    exactly the failure, and it averages out to something that looks healthy.

    `gap_max_s` is therefore the headline, not `n`. `phases` keeps the texts so it can be read whether
    they are sentences a person understands ("entrando en booking.com") or developer telemetry
    ("tool_use ok") — B1 and B2 of V2-227 respectively, and they fail independently.
    """
    import sqlite3
    out: dict = {"n": 0, "phases": [], "gap_max_s": 0.0, "span_s": 0.0}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    try:
        # `topic = 'worker.phase'`, con el texto en el campo `phase`. NO es `observer/kind='phase'`: eso
        # devolvía CERO mientras la ronda emitía 71 fases, y estuve a un mensaje de reportar que el
        # arreglo del otro agente no emitía nada. Cuarta vez en el día que leo un campo en el nivel
        # equivocado; por eso esto se escribió mirando la BD de una ronda real y no el contrato.
        rows = con.execute("SELECT ts_ms, payload FROM events WHERE topic = 'worker.phase' "
                           "AND ts_ms >= ? ORDER BY ts_ms ASC", (int(since * 1000),)).fetchall()
    except Exception:
        return out
    finally:
        con.close()
    seen, prev, first = [], None, None
    for ts_ms, raw in rows:
        try:
            p = json.loads(raw) or {}
            txt = str(p.get("phase") or p.get("text") or "").strip()
        except Exception:
            continue
        if not txt:
            continue
        first = first if first is not None else ts_ms
        if prev is not None:
            out["gap_max_s"] = max(out["gap_max_s"], round((ts_ms - prev) / 1000.0, 1))
        prev = ts_ms
        out["n"] += 1
        if len(seen) < 12:
            seen.append({"at_s": round((ts_ms - first) / 1000.0, 1), "text": txt[:120]})
    out["phases"] = seen
    out["span_s"] = round(((prev or 0) - (first or 0)) / 1000.0, 1)
    return out

def declared_surfaces(db_path, *, since: float = 0.0) -> list[str]:
    """QUÉ SUPERFICIE declaró el motor al ENCARGAR cada tarea (V2-227 ámbito A), en orden.

    Verificado en una ronda real: el campo viaja sellado desde el encargo con valores del vocabulario
    cerrado (`lista·item·widget·voz·silenciosa`). Se recoge aquí por dos motivos, y el segundo no es el
    obvio: la hoja de resultados con su pestaña de proceso SOLO se abre para `lista`/`item`, así que sin
    esto no se puede saber si una ronda sin pestaña de proceso es un fallo de la pestaña o una tarea que
    nunca pidió una; y una superficie mal elegida DELATA el mismo defecto que ya perseguimos por otro
    lado — declarar `lista` para «¿a qué hora abre el Prado?» es la misma sobrerreacción que levantar un
    navegador para un dato directo, vista un paso antes.
    """
    import sqlite3
    out: list[str] = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    try:
        rows = con.execute("SELECT payload FROM events WHERE ts_ms >= ? AND payload LIKE '%surface%' "
                           "ORDER BY ts_ms ASC LIMIT 200", (int(since * 1000),)).fetchall()
    except Exception:
        return out
    finally:
        con.close()
    for (raw,) in rows:
        try:
            d = json.loads(raw)
        except Exception:
            continue
        # En la ronda real vive en `context.surface` de `escalate.requested` — ni arriba del todo ni en
        # `extra`, que son los dos sitios donde miré primero. Se buscan los tres niveles porque el emisor
        # puede cambiar y un campo que se lee en un solo sitio desaparece en silencio (hoy, cuarta vez).
        ctx = d.get("context") if isinstance(d.get("context"), dict) else {}
        ext = d.get("extra") if isinstance(d.get("extra"), dict) else {}
        val = str(d.get("surface") or ctx.get("surface") or ext.get("surface") or "").strip()
        if val and val not in out:
            out.append(val)
    return out


def sheet_timing(db_path, *, since: float = 0.0) -> dict:
    """¿La hoja de resultados se abrió ANTES de que hubiera un resultado? (V2-227, el cableado de C).

    Es LA pregunta del ámbito C y no se puede responder desde el DOM: el contrato de pantalla
    (`tests/browser/e2e/results/render_process_tab.py`) prueba que el widget se comporta cuando le
    llegan los datos, no que alguien se los mande ni que la hoja se abra sola al encargar. Con el
    contrato en verde y el cableado sin hacer, la persona sigue mirando una pantalla en blanco: la
    pestaña existe y nadie se la abre.

    Se compara el instante de la PRIMERA operación sobre la hoja contra el de la primera extracción con
    título de verdad — no cualquier vuelta del navegador, porque la primera suele ser el `usage:` de un
    comando mal escrito y tomarla por un resultado adelantaría el reloj de la comparación.

    `opened_before` es `None`, nunca `False`, cuando falta alguno de los dos instantes: no medido y
    llegó-tarde son cosas distintas y confundirlas es como se inventa un fallo.
    """
    import sqlite3
    out: dict = {"sheet_ms": None, "sheet_any_ms": None, "first_result_ms": None,
                 "opened_before": None, "lead_s": None}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return out
    try:
        rows = con.execute("SELECT ts_ms, kind, payload FROM events WHERE topic = 'observer' AND ts_ms >= ? "
                           "AND kind IN ('widget', 'navegador') ORDER BY ts_ms ASC", (int(since * 1000),)
                           ).fetchall()
    except Exception:
        return out
    finally:
        con.close()
    for ts_ms, kind, raw in rows:
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if kind == "widget" and str(d.get("id") or "") == "results":
            # SOLO `show`, y esto es lo que hace que la medida DISCRIMINE. La primera versión aceptaba
            # cualquier operación sobre la hoja y daba «abrió 51 s antes» en una ronda ANTERIOR al
            # cableado: un `data` de fondo existía desde siempre. Una comprobación que sale verde con la
            # función construida y sin construir no prueba nada y encima da confianza — es peor que no
            # tenerla. Lo que el cableado añade es ABRIRLA (`show`) al encargar.
            if str(d.get("label") or "") == "show" and out["sheet_ms"] is None:
                out["sheet_ms"] = ts_ms
            elif out["sheet_any_ms"] is None:
                out["sheet_any_ms"] = ts_ms
        elif kind == "navegador" and out["first_result_ms"] is None:
            if any(it.get("title") for it in _items_in(str(d.get("text") or ""))):
                out["first_result_ms"] = ts_ms
    if out["sheet_ms"] is not None and out["first_result_ms"] is not None:
        out["lead_s"] = round((out["first_result_ms"] - out["sheet_ms"]) / 1000.0, 1)
        out["opened_before"] = out["lead_s"] > 0
    return out


def embeddings_backend(db_path, *, since: float = 0.0) -> dict:
    """WHICH embeddings backend served this round's recalls — `{backend, degraded, skipped}`.

    A sandbox boot can log BOTH «⚠️ memoria: embeddings en 'hash' — recall SEMÁNTICO prácticamente
    DESACTIVADO» and, fifteen seconds later, «prewarm embeddings OK (ollama)». They contradict each other
    and only one describes the process that answers the turns.

    Measured by the memory agent on 2026-08-21: inside ONE process a degraded backend stays pinned for
    `_BACKEND_RECHECK_S` (300 s) and nothing calls `reset()` in production, so a process reporting `ollama`
    at prewarm CANNOT have resolved `hash` earlier — the two lines are different processes, and the `⚠️`
    one (stdlib logging, no timestamp, inherited stderr) is not the one serving recalls. Once on `ollama`
    the resolver returns without re-probing, so it cannot degrade mid-round either.

    So the guard is READ THE PREWARM, not sleep five minutes. And it is read from the EVENT, not from the
    log text: `prewarm._emit_prewarm` emits `perf` with `extra {"warm": "embed", "model": <backend>}`, which
    carries the backend in a FIELD instead of inside a sentence and survives a change of log format. Same
    store every other reading here comes from.

    `skipped` is the case that matters most and the one a first version got wrong. If the prewarm THREW
    there is no OK line at all — and without a prewarm the backend is resolved by the first recall, which is
    exactly when `hash` is likeliest. An absent OK therefore cannot be read as health; only the absence of
    BOTH signals claims nothing, and then the round is graded normally.
    """
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return {}
    try:
        rows = con.execute("SELECT label, payload FROM events WHERE kind = 'perf' AND ts_ms >= ? "
                           "ORDER BY ts_ms", (int(since * 1000),)).fetchall()
    except Exception:
        return {}
    finally:
        try:
            con.close()
        except Exception:
            pass
    out: dict = {}
    for label, raw in rows:
        try:
            d = json.loads(raw) or {}
        except Exception:
            continue
        extra = d.get("extra") or d
        if str(extra.get("warm") or "") != "embed":
            continue
        backend = str(extra.get("model") or "").strip()
        # `_warm_embed` reports the exception in the label («prewarm embed 0ms — saltado: …») and passes
        # model="?" when it failed. Either shape is a prewarm that did not happen.
        skipped = ("saltado" in str(label or "")) or backend in ("", "?")
        out = {"backend": backend, "skipped": skipped,
               "degraded": bool(skipped or backend != "ollama")}
    return out
