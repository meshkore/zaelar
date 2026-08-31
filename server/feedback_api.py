"""server/feedback_api.py — send a suggestion/bug report straight to the developers (V2-100, 2026-08-16).

The one new class of outbound call a self-hosted install makes: every other "phone home" path in this
repo (`nucleo/energy_meter.py`, `observability/identity.py::_report_to_control_plane`) is gated on
`CONTROL_PLANE_URL`/`ZAELAR_USER_ID`, which only a cloud-provisioned Machine has. Feedback needs to work
for a self-hoster with no account at all, so it gets its own endpoint default (`ZAELAR_FEEDBACK_URL`)
and a fully separate, unauthenticated ingestion path on the control-plane
(`cloud/control-plane/src/index.js::handleFeedbackAnonymous`, rate-limited there — not this repo's
business what the caps are).

Two branches, same shape as `energy_meter._post_usage_cloud_account`: a cloud engine (workload
credential already present) reports itself and gets tied to the real account; a self-hosted engine
reports only its stable per-install id (`observability.identity.user_id()` — already existed for
observability, no new "keypair on first boot" needed).

The optional "attach this session" evidence bundle is built by calling `observability.flows` directly
— IN-PROCESS, not over `/api/observability/*` — because that HTTP surface is loopback/token-guarded
(`observability/api.py::_allowed()`) and the frontend never sends `X-Observability-Token`, so a browser
call to it would silently 403 on a cloud deployment. Running server-side sidesteps the guard entirely.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Body

router = APIRouter()

_FEEDBACK_URL_DEFAULT = "https://zaelar-control-plane.rjj.workers.dev"
_MAX_EVIDENCE_EVENTS = 200
# The ingestion endpoint rejects a bundle over 40_000 bytes with a flat 400 (`_MAX_EVIDENCE_BYTES` in
# `cloud/control-plane/src/index.js`), and its comment there claimed "generous margin over the ~30KB the
# engine caps itself to" — a self-cap that was never written. Measured 2026-08-31 on the operator's own
# session: 200 events serialised to 212_037 bytes, 5.3× the ceiling, so EVERY submission that ticked
# "include this session" was refused and the operator's message was lost with it. The engine caps itself
# by BYTES here, and the count stays as the cheap first cut.
_MAX_EVIDENCE_BYTES = 30_000
_TIMEOUT_S = 5.0


def _feedback_url() -> str:
    return (os.getenv("ZAELAR_FEEDBACK_URL") or _FEEDBACK_URL_DEFAULT).rstrip("/")


def _control_plane_url() -> str:
    return (os.getenv("CONTROL_PLANE_URL") or "").strip()


def _service_token() -> str:
    return (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()


def _fit_evidence(summary: dict, events: list) -> dict | None:
    """Trim the bundle until it fits `_MAX_EVIDENCE_BYTES`, keeping the MOST RECENT events — what the
    operator is reporting just happened, and the oldest events are the ones they are least likely to mean.
    Returns `None` when even the summary alone does not fit (nothing sensible left to attach).

    Halving instead of dropping one at a time: a session can carry thousands of events and this runs on the
    request path. `truncated` travels in the bundle so the reader never mistakes a trimmed session for a
    short one — the receiving end must not have to guess whether it is seeing everything."""
    import json as _json

    def _size(obj) -> int:
        return len(_json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    base = {"summary": summary, "events": []}
    if _size(base) > _MAX_EVIDENCE_BYTES:
        return None
    kept = list(events)
    while kept and _size({"summary": summary, "events": kept}) > _MAX_EVIDENCE_BYTES:
        kept = kept[-(len(kept) // 2):] if len(kept) > 1 else []
    out: dict = {"summary": summary, "events": kept}
    if len(kept) < len(events):
        out["truncated"] = {"kept": len(kept), "of": len(events), "reason": "size"}
    return out


def _build_evidence(session_id: str) -> dict | None:
    """Capped, session-scoped-only bundle — never the operator's full history. Fails open to `None`:
    a bad evidence bundle must never block the message itself from sending."""
    if not session_id:
        return None
    try:
        from observability import flows as _flows
        summary = _flows.session(session_id)
        if not summary:
            return None
        events = _flows.events(session_id=session_id, limit=_MAX_EVIDENCE_EVENTS)
        return _fit_evidence(summary, events)
    except Exception:
        return None


@router.get("/api/feedback")
async def list_feedback():
    from nucleo import cloud_account
    from observability import identity as _identity

    url = _feedback_url()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            if cloud_account.is_cloud_account() and _control_plane_url():
                resp = await client.get(
                    _control_plane_url().rstrip("/") + "/feedback",
                    headers={"X-Service-Token": _service_token()},
                )
            else:
                resp = await client.get(
                    url + "/feedback/anonymous",
                    params={"install_id": _identity.user_id()},
                )
        if resp.status_code >= 400:
            return {"ok": False, "items": []}
        return {"ok": True, **(resp.json() or {})}
    except Exception:
        return {"ok": False, "items": []}


@router.post("/api/feedback")
async def submit_feedback(
    message: str = Body(..., embed=True),
    email: str = Body("", embed=True),
    include_session_evidence: bool = Body(False, embed=True),
):
    from nucleo import cloud_account
    from observability import identity as _identity

    message = (message or "").strip()
    if not message:
        return {"ok": False, "error": "empty_message"}

    evidence = None
    if include_session_evidence:
        evidence = _build_evidence(_identity.session_info().get("session_id") or "")

    body: dict = {"message": message}
    if email.strip():
        body["email"] = email.strip()
    if evidence is not None:
        body["session_evidence"] = evidence

    async def _post(payload: dict):
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            if cloud_account.is_cloud_account() and _control_plane_url():
                return await client.post(
                    _control_plane_url().rstrip("/") + "/feedback",
                    json=payload,
                    headers={"X-Service-Token": _service_token()},
                )
            payload = {**payload, "install_id": _identity.user_id()}
            return await client.post(_feedback_url() + "/feedback/anonymous", json=payload)

    try:
        resp = await _post(body)
        # THE MESSAGE IS THE POINT; the session bundle is an ATTACHMENT. A refusal while carrying one is
        # retried WITHOUT it, so a rejected attachment can never swallow what the operator actually wrote
        # (measured 2026-08-31: an oversized bundle turned every ticked submission into a flat 400 and the
        # text was lost). Only for a 4xx — a 5xx or a rate limit is not about the attachment, and retrying
        # those would just be a second knock at a door that is closed for another reason.
        dropped_evidence = False
        if resp.status_code in (400, 413, 422) and "session_evidence" in body:
            retry_body = {k: v for k, v in body.items() if k != "session_evidence"}
            resp = await _post(retry_body)
            dropped_evidence = resp.status_code < 400
        if resp.status_code >= 400:
            return {"ok": False, "error": "send_failed", "status": resp.status_code}
        out = {"ok": True, **(resp.json() or {})}
        if dropped_evidence:
            out["evidence_dropped"] = True          # the panel says the message went but the session did not
        elif isinstance(evidence, dict) and evidence.get("truncated"):
            out["evidence_truncated"] = evidence["truncated"]
        return out
    except Exception as e:  # noqa: BLE001 — fail-open, the user still sees a clear "couldn't send" state
        return {"ok": False, "error": "send_failed", "detail": str(e)}
