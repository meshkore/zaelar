#
# MeshKore connector HTTP API — /api/meshkore/*  (always mounted; the connector is native, not brain-gated).
#
# The PRIMARY flow is brain-driven: the operator pastes creds + speaks the goal → Hermes emits [[cluster.*]]
# tags → the bridge acts. These endpoints are the out-of-band controls: paste-staging, a status readout for the
# UI, and manual connect/send/disconnect for testing or a form-based path. Tokens are never echoed back.
#
import ipaddress
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from connectors import meshkore
from connectors.meshkore import store, security

router = APIRouter()


def _guard(request: Request):
    """Control-plane guard. These endpoints stage credentials, connect zaelar to arbitrary clusters (persisted), and
    send to peers — they MUST NOT be callable by a random local process or a DNS-rebind browser page. Policy:
      • If MESHKORE_API_TOKEN is set → require header `X-MeshKore-Token` to match (works for remote/prod).
      • Else (default) → loopback callers only, and reject cross-origin browser calls (DNS-rebinding defense).
    Fail-closed: anything not clearly allowed is 403."""
    tok = os.getenv("MESHKORE_API_TOKEN", "").strip()
    if tok:
        import hmac
        given = request.headers.get("x-meshkore-token") or ""
        if hmac.compare_digest(given, tok):              # constant-time: no timing oracle on the token (audit V9)
            return
        raise HTTPException(status_code=403, detail="bad or missing X-MeshKore-Token")
    host = (request.client.host if request.client else "") or ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise HTTPException(status_code=403,
                            detail="meshkore control-plane is loopback-only; set MESHKORE_API_TOKEN to allow remote")
    origin = request.headers.get("origin") or ""
    if origin:
        # DNS-rebind defense: EXACT hostname match, not substring. A substring test lets
        # `http://localhost.attacker.com` (host = "localhost.attacker.com") slip through because it *contains*
        # "localhost"; parse the Origin and compare the host itself against the loopback set (audit V5).
        from urllib.parse import urlparse
        host = (urlparse(origin).hostname or "").lower()
        if host not in ("localhost", "127.0.0.1", "::1"):
            raise HTTPException(status_code=403, detail="cross-origin blocked")


class ConnectBody(BaseModel):
    name: str
    cluster_id: str = ""
    token: str = ""
    handle: str = "zaelar"


class StageBody(BaseModel):
    name: str
    cluster_id: str
    token: str
    handle: str = "zaelar"


class SendBody(BaseModel):
    name: str
    to: str | None = None
    text: str = ""


class NameBody(BaseModel):
    name: str


@router.get("/api/meshkore/status")
async def status(_=Depends(_guard)):
    # Guarded like the rest of the control plane: it discloses connected clusters + peer handles + engagement
    # state, which a random local process or a DNS-rebind page must not read (audit V4).
    b = meshkore.get_bridge()
    engaged = getattr(b, "_engaged", {}) if b else {}
    return JSONResponse({"clusters": meshkore.get_manager().clusters(), "engaged": engaged,
                         "wired": b is not None})


@router.post("/api/meshkore/stage")
async def stage(body: StageBody, _=Depends(_guard)):
    """Hold pasted credentials in memory so a later name-only connect resolves the token WITHOUT it going through
    the LLM. Returns nothing sensitive."""
    store.stage(body.name, body.cluster_id, body.token, body.handle)
    return JSONResponse({"ok": True, "name": body.name})


@router.post("/api/meshkore/connect")
async def connect(body: ConnectBody, _=Depends(_guard)):
    creds = store.resolve(body.name, body.cluster_id, body.token, body.handle)
    if not creds:
        return JSONResponse({"ok": False, "error": "no cluster_id/token (stage or pass them)"}, status_code=400)
    await meshkore.get_manager().connect(body.name, creds["cluster_id"], creds["token"], creds.get("handle"))
    store.save_cluster(body.name, creds["cluster_id"], creds["token"], creds.get("handle", "zaelar"))
    return JSONResponse({"ok": True, "name": body.name})


@router.post("/api/meshkore/send")
async def send(body: SendBody, _=Depends(_guard)):
    # Same outbound guard as the brain tag path (bridge.dispatch): a hard secret blocks the send entirely.
    text, blocked = security.scan_outbound(body.text or "")
    if blocked:
        return JSONResponse({"ok": False, "error": f"outbound blocked — possible secret leak ({blocked})"},
                            status_code=400)
    try:
        await meshkore.get_manager().send(body.name, to=body.to, text=text)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/api/meshkore/disconnect")
async def disconnect(body: NameBody, _=Depends(_guard)):
    await meshkore.get_manager().disconnect(body.name)
    store.remove_cluster(body.name)
    return JSONResponse({"ok": True})
