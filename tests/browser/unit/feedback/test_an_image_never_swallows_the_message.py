"""A picture is an ATTACHMENT too — and it is the heaviest one (V2-695).

The operator asked to be able to paste or upload an image into a report: half of any real bug report is
«look at what my screen says». What that adds to a submission is bytes, on a path with NO queue and NO
local copy — `submit_feedback` is a live 5-second POST, and if it fails the only thing that survives is
the text still sitting in the box.

So this is V2-519's rule with one more piece to shed, and the ORDER is the whole point: pictures go
first, because shedding a 30 KB session bundle while 600 KB of screenshots stay is a retry that fails
again for exactly the same reason.
"""
from __future__ import annotations

import asyncio

import pytest

from server import feedback_api as fb


def _shot(kb: int, mime: str = "image/webp", name: str = "captura.webp") -> dict:
    # base64 is 4 chars per 3 bytes, which is what the server measures rather than trusting `bytes`.
    return {"name": name, "mime": mime, "bytes": kb * 1000, "data": "A" * ((kb * 1000 * 4) // 3)}


class _Resp:
    def __init__(self, status: int):
        self.status_code = status

    def json(self):
        return {"id": "fb1", "status": "received"}


def _capture(monkeypatch, statuses: list[int]):
    sent: list[dict] = []
    seq = list(statuses)

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent.append(json or {})
            return _Resp(seq.pop(0))

    monkeypatch.setattr(fb.httpx, "AsyncClient", lambda **k: _Client())
    monkeypatch.setattr(fb, "_build_evidence", lambda sid: {"summary": {"id": "s"}, "events": [1, 2]})
    from observability import identity
    monkeypatch.setattr(identity, "session_info", lambda: {"session_id": "s1"})
    monkeypatch.setattr(identity, "user_id", lambda: "4cd1b39d-d879-4137-90d1-fea5c7e9e2d4")
    return sent


# ── what a report SAYS it is ────────────────────────────────────────────────────────────────────────────

def test_the_kind_travels_and_defaults_to_an_issue(monkeypatch):
    sent = _capture(monkeypatch, [200, 200])
    asyncio.run(fb.submit_feedback(message="no me deja conectar", email="", kind="idea"))
    assert sent[0]["type"] == "idea"
    asyncio.run(fb.submit_feedback(message="no me deja conectar", email=""))
    assert sent[1]["type"] == "issue", "a report with no kind is a report of something wrong"


def test_an_UNKNOWN_kind_becomes_an_issue_rather_than_travelling(monkeypatch):
    """A category nobody filters by is the same as no category at all."""
    sent = _capture(monkeypatch, [200])
    asyncio.run(fb.submit_feedback(message="x", email="", kind="rant"))
    assert sent[0]["type"] == "issue"


# ── the budget is enforced HERE too ─────────────────────────────────────────────────────────────────────

def test_the_caps_are_enforced_on_the_SERVER_not_only_in_the_browser(monkeypatch):
    """A client is not a guard: this endpoint is reachable by anything that can speak HTTP to loopback."""
    sent = _capture(monkeypatch, [200])
    asyncio.run(fb.submit_feedback(message="x", email="", shots=[_shot(50) for _ in range(6)]))
    assert len(sent[0]["shots"]) == fb._MAX_SHOTS


def test_one_oversized_picture_is_dropped_and_the_others_still_travel(monkeypatch):
    sent = _capture(monkeypatch, [200])
    asyncio.run(fb.submit_feedback(message="x", email="", shots=[_shot(400, name="enorme.webp"), _shot(20)]))
    names = [s["name"] for s in sent[0]["shots"]]
    assert names == ["captura.webp"], names


def test_a_shape_that_is_not_an_image_never_travels(monkeypatch):
    sent = _capture(monkeypatch, [200])
    asyncio.run(fb.submit_feedback(message="x", email="", shots=[
        {"name": "log.txt", "mime": "text/plain", "data": "AAAA"},   # he asked for images only
        {"name": "empty.webp", "mime": "image/webp", "data": ""},    # nothing to show
        "not-a-dict",
        _shot(10),
    ]))
    assert [s["name"] for s in sent[0]["shots"]] == ["captura.webp"]


def test_no_pictures_means_the_key_never_appears(monkeypatch):
    sent = _capture(monkeypatch, [200])
    asyncio.run(fb.submit_feedback(message="x", email=""))
    assert "shots" not in sent[0], "an empty list is noise on every report that has no picture"


# ── the message is the point ────────────────────────────────────────────────────────────────────────────

def test_a_refused_report_sheds_the_PICTURES_first(monkeypatch):
    """⚠️ The order is the load-bearing half. Pictures are by far the heaviest thing in the body, so
    shedding the session bundle first would produce a retry that fails again for the same reason."""
    sent = _capture(monkeypatch, [413, 200])
    res = asyncio.run(fb.submit_feedback(message="mira lo que me sale", email="", include_session_evidence=True,
                                         shots=[_shot(120)]))
    assert res["ok"] is True and res["shots_dropped"] is True
    assert res.get("evidence_dropped") is not True, "the session did not have to go"
    assert len(sent) == 2
    assert "shots" in sent[0] and "session_evidence" in sent[0]
    assert "shots" not in sent[1] and "session_evidence" in sent[1]
    assert sent[1]["message"] == "mira lo que me sale"


def test_a_SECOND_refusal_costs_the_session_too_and_the_message_still_lands(monkeypatch):
    sent = _capture(monkeypatch, [413, 413, 200])
    res = asyncio.run(fb.submit_feedback(message="sigue fallando", email="", include_session_evidence=True,
                                         shots=[_shot(120)]))
    assert res["ok"] is True and res["shots_dropped"] is True and res["evidence_dropped"] is True
    assert len(sent) == 3
    assert "shots" not in sent[2] and "session_evidence" not in sent[2]
    assert sent[2]["message"] == "sigue fallando"


def test_a_rate_limit_is_not_about_the_attachments(monkeypatch):
    sent = _capture(monkeypatch, [429])
    res = asyncio.run(fb.submit_feedback(message="x", email="", shots=[_shot(120)]))
    assert res["ok"] is False and res["status"] == 429 and len(sent) == 1
