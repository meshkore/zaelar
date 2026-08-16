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
_TIMEOUT_S = 5.0


def _feedback_url() -> str:
    return (os.getenv("ZAELAR_FEEDBACK_URL") or _FEEDBACK_URL_DEFAULT).rstrip("/")


def _control_plane_url() -> str:
    return (os.getenv("CONTROL_PLANE_URL") or "").strip()


def _service_token() -> str:
    return (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()


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
        return {"summary": summary, "events": events}
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

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            if cloud_account.is_cloud_account() and _control_plane_url():
                resp = await client.post(
                    _control_plane_url().rstrip("/") + "/feedback",
                    json=body,
                    headers={"X-Service-Token": _service_token()},
                )
            else:
                body["install_id"] = _identity.user_id()
                resp = await client.post(_feedback_url() + "/feedback/anonymous", json=body)
        if resp.status_code >= 400:
            return {"ok": False, "error": "send_failed", "status": resp.status_code}
        return {"ok": True, **(resp.json() or {})}
    except Exception as e:  # noqa: BLE001 — fail-open, the user still sees a clear "couldn't send" state
        return {"ok": False, "error": "send_failed", "detail": str(e)}
