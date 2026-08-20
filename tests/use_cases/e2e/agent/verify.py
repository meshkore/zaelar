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


def mechanism_report(all_events: list[dict], expected_signals: list[str],
                     concurrency: ConcurrencyTracker | None = None,
                     scheduled: dict | None = None) -> dict:
    """Structured, transcript-independent record of what actually happened this scenario."""
    families = families_in(all_events)
    missing = [f for f in expected_signals if f not in families]
    task_id = find_navegador_task_id(all_events)
    task_view: dict = {}
    if task_id:
        task_view = poll_navegador_task(task_id)
    out = {
        "families_observed": sorted(families),
        "expected_signals": expected_signals,
        "missing_signals": missing,
        "navegador_task_id": task_id,
        "navegador_task": task_view,
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
            out.append({"turn": row.get("turn"), "objective": clash[0][:120], "n": len(clash)})
    return out


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
    """Did ANY of what the browser found appear in something zaelar SAID? `None` when nothing was found."""
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
