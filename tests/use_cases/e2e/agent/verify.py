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
    evs = [e for e in all_events if isinstance(e, dict)]
    errors = [{"cat": e.get("cat"), "kind": e.get("kind"), "label": e.get("label"),
               "span": e.get("span"), "rel_ms": e.get("rel_ms"),
               "text": str(e.get("text") or "")[:240]}
              for e in evs if e.get("is_error")]
    evidence = [e for e in evs if e.get("evidence")]
    tools: dict[str, int] = {}
    for e in evs:
        if t := e.get("tool"):
            tools[t] = tools.get(t, 0) + 1

    spans: dict[str, dict] = {}
    for e in evs:
        sp = e.get("span")
        if not sp:
            continue
        d = spans.setdefault(sp, {"n": 0, "first_ms": e.get("rel_ms"), "last_ms": e.get("rel_ms"),
                                  "errors": 0, "last_label": ""})
        d["n"] += 1
        d["last_ms"] = e.get("rel_ms")
        d["last_label"] = e.get("label") or ""
        if e.get("is_error"):
            d["errors"] += 1

    stamps = sorted(e.get("rel_ms") for e in evs if isinstance(e.get("rel_ms"), (int, float)))
    gap = max((b - a for a, b in zip(stamps, stamps[1:])), default=0)

    anomalies: list[dict] = []
    for e in errors:
        anomalies.append({"clase": "error_interno", "certeza": "hecho",
                          "que": f"{e['cat']}/{e['kind']} «{e['label']}»: {e['text'][:160]}"})
    for d in dropped_actions(evs):
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
        "unexpected_families": sorted(families_in(evs) - set(exp)) if exp else [],
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
        # The full walk of the stream, not just which families showed up. A case does NOT close with
        # anomalies here, however good the transcript reads — see `tick`.
        "audit": audit(all_events, expected_signals),
    }
    if scheduled is not None:
        out["scheduled_jobs"] = scheduled
    if concurrency is not None:
        out["task_registry"] = concurrency.report()
    return out
