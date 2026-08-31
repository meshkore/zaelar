"""The session bundle is an ATTACHMENT — it can never swallow the message (V2-519).

Measured 2026-08-31 on the operator's own engine: ticking "incluir lo que ha pasado en esta sesión"
turned every submission into a flat 400 and the written message was lost with it. Two causes, stacked:

  · the engine capped the bundle by COUNT (200 events) and never by BYTES, while the ingestion endpoint
    rejects anything over 40_000 bytes. The operator's 200 events serialised to 212_037 — 5.3× the
    ceiling. The control-plane's own comment asserted "the ~30KB the engine caps itself to": a self-cap
    that had never been written, believed on both sides because nobody measured it.
  · a refusal carrying the attachment killed the whole submission, when the attachment is the optional
    half and the message is the point.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from server import feedback_api as fb


def _events(n: int, size: int = 400) -> list:
    return [{"i": i, "text": "x" * size} for i in range(n)]


def test_a_bundle_is_trimmed_to_fit_the_endpoints_ceiling():
    out = fb._fit_evidence({"id": "s1"}, _events(200))
    assert out is not None
    raw = len(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    assert raw <= fb._MAX_EVIDENCE_BYTES
    assert fb._MAX_EVIDENCE_BYTES < 40_000            # the receiving end's hard ceiling, with margin


def test_what_survives_the_trim_is_the_RECENT_end():
    """The operator is reporting what just happened; the oldest events are the ones they least mean."""
    out = fb._fit_evidence({"id": "s1"}, _events(200))
    assert out["events"], "a trim that keeps nothing is not a trim"
    assert out["events"][-1]["i"] == 199              # the newest event survives
    assert out["events"][0]["i"] > 0                  # …and older ones were the ones dropped


def test_a_trimmed_bundle_SAYS_it_was_trimmed():
    """A reader must never mistake a trimmed session for a short one."""
    out = fb._fit_evidence({"id": "s1"}, _events(200))
    assert out["truncated"]["of"] == 200 and out["truncated"]["kept"] == len(out["events"])
    small = fb._fit_evidence({"id": "s1"}, _events(2, size=10))
    assert "truncated" not in small                   # nothing was dropped → nothing is claimed


def test_the_builder_ACTUALLY_applies_the_trim(monkeypatch):
    """The WIRING, not just the rule: an earlier version of this file only exercised `_fit_evidence`, so
    deleting its call from `_build_evidence` — the exact shipped bug — left every test green."""
    from observability import flows
    monkeypatch.setattr(flows, "session", lambda sid: {"id": sid})
    monkeypatch.setattr(flows, "events", lambda session_id, limit: _events(200))
    out = fb._build_evidence("s1")
    assert out is not None
    assert len(json.dumps(out, ensure_ascii=False).encode("utf-8")) <= fb._MAX_EVIDENCE_BYTES
    assert out["truncated"]["of"] == 200


def test_a_summary_that_cannot_fit_attaches_nothing():
    assert fb._fit_evidence({"id": "s1", "blob": "x" * (fb._MAX_EVIDENCE_BYTES + 10)}, []) is None


class _Resp:
    def __init__(self, status: int, payload: dict | None = None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def _capture(monkeypatch, statuses: list[int]):
    """Fake the transport; record every payload the endpoint tried to send."""
    sent: list[dict] = []
    seq = list(statuses)

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent.append(json or {})
            return _Resp(seq.pop(0), {"id": "fb1", "status": "received"})

    monkeypatch.setattr(fb.httpx, "AsyncClient", lambda **k: _Client())
    monkeypatch.setattr(fb, "_build_evidence", lambda sid: {"summary": {"id": "s"}, "events": [1, 2]})
    from observability import identity
    monkeypatch.setattr(identity, "session_info", lambda: {"session_id": "s1"})
    monkeypatch.setattr(identity, "user_id", lambda: "4cd1b39d-d879-4137-90d1-fea5c7e9e2d4")
    return sent


def test_a_refused_attachment_does_not_lose_the_message(monkeypatch):
    sent = _capture(monkeypatch, [400, 200])
    res = asyncio.run(fb.submit_feedback(message="el correo no se conecta",
                                         email="", include_session_evidence=True))
    assert res["ok"] is True and res["evidence_dropped"] is True
    assert len(sent) == 2
    assert "session_evidence" in sent[0]               # first try carried it…
    assert "session_evidence" not in sent[1]           # …the retry did not
    assert sent[1]["message"] == "el correo no se conecta"   # and the MESSAGE survived intact


def test_a_failure_that_is_not_about_the_attachment_is_not_retried(monkeypatch):
    """A 5xx or a rate limit is closed for another reason — knocking twice is noise, not resilience."""
    sent = _capture(monkeypatch, [429])
    res = asyncio.run(fb.submit_feedback(message="hola", email="", include_session_evidence=True))
    assert res["ok"] is False and res["status"] == 429
    assert len(sent) == 1


def test_a_send_without_an_attachment_is_never_retried(monkeypatch):
    sent = _capture(monkeypatch, [400])
    res = asyncio.run(fb.submit_feedback(message="hola", email="", include_session_evidence=False))
    assert res["ok"] is False and len(sent) == 1
