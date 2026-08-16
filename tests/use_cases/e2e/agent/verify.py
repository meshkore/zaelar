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


def mechanism_report(all_events: list[dict], expected_signals: list[str]) -> dict:
    """Structured, transcript-independent record of what actually happened this scenario."""
    families = families_in(all_events)
    missing = [f for f in expected_signals if f not in families]
    task_id = find_navegador_task_id(all_events)
    task_view: dict = {}
    if task_id:
        task_view = poll_navegador_task(task_id)
    return {
        "families_observed": sorted(families),
        "expected_signals": expected_signals,
        "missing_signals": missing,
        "navegador_task_id": task_id,
        "navegador_task": task_view,
        "n_events": len(all_events),
    }
