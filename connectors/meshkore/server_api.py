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
    # The residual GET (V2-601 T-14, audit C-2): a SAME-origin fetch from a DNS-rebound page carries NO Origin
    # header at all, so the check above never sees it — but the browser still names the site it thinks it is on
    # in `Host`. A legitimate local caller says localhost/127.0.0.1/::1 (or local.zaelar.com, whose DNS pins to
    # 127.0.0.1 by design); a rebound page says the attacker's domain. Exact hostname match, port stripped;
    # missing Host fails closed like the rest of this guard.
    raw_host = (request.headers.get("host") or "").strip().lower()
    if raw_host.startswith("["):                                  # [::1]:44317
        hostname = raw_host[1:raw_host.index("]")] if "]" in raw_host else raw_host
    else:
        hostname = raw_host.rsplit(":", 1)[0] if ":" in raw_host else raw_host
    if hostname not in ("localhost", "127.0.0.1", "::1", "local.zaelar.com"):
        raise HTTPException(status_code=403, detail="host not a loopback name (DNS rebind?)")


class ConnectBody(BaseModel):
    name: str
    cluster_id: str = ""
    token: str = ""
    handle: str = "zaelar"
    vis: str = ""            # "public" -> open cluster, no token (V2-086)


class StageBody(BaseModel):
    name: str
    cluster_id: str
    token: str = ""          # V2-086: empty in a public cluster — not missing, nonexistent
    handle: str = "zaelar"
    vis: str = ""


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
    store.stage(body.name, body.cluster_id, body.token, body.handle, body.vis)
    return JSONResponse({"ok": True, "name": body.name})


@router.post("/api/meshkore/connect")
async def connect(body: ConnectBody, _=Depends(_guard)):
    creds = store.resolve(body.name, body.cluster_id, body.token, body.handle, getattr(body, "vis", "") or "")
    if not creds:
        return JSONResponse({"ok": False, "error": "falta el cluster_id (y el token si es privado)"},
                            status_code=400)
    vis = creds.get("vis", "")
    await meshkore.get_manager().connect(body.name, creds["cluster_id"], creds["token"], creds.get("handle"),
                                         vis=vis)
    store.save_cluster(body.name, creds["cluster_id"], creds["token"], creds.get("handle", "zaelar"), vis=vis)
    return JSONResponse({"ok": True, "name": body.name, "public": bool(vis == "public")})


@router.post("/api/meshkore/confirm")
async def confirm(body: dict, _=Depends(_guard)):
    """Resolve the Yes/No confirmation to CONNECT to a cluster from the native "Clusters" tab (V2-086).

    This did not exist before: confirmation was requested on the `cluster-registro` widget card, but
    `/widgets/{id}/confirm` only knew how to resolve DELETES — so the button never connected anything and the only
    path that closed the loop was saying "yes" by voice. Now the button works through the SAME path
    (`dispatch_tag("cluster.connect")`) and with the same gate: no socket opens without an explicit "yes"."""
    from widgets import confirm as _confirm
    ok = bool((body or {}).get("ok"))
    p = _confirm.resolve(_confirm.NATIVE_CLUSTERS, ok)
    if p is None:
        return JSONResponse({"ok": False, "error": "no hay confirmación pendiente"}, status_code=409)
    if not ok:
        return JSONResponse({"ok": True, "cancelled": True})
    op = p.get("op") or {}
    if op.get("action") != "connect_cluster":
        return JSONResponse({"ok": False, "error": f"acción no soportada: {op.get('action')}"}, status_code=400)
    await meshkore.dispatch_tag("cluster.connect", {"data": op.get("payload") or {}})
    return JSONResponse({"ok": True, "name": (op.get("payload") or {}).get("name", "")})


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
    # OBSERVABILITY (2026-07-25, operator request to verify a send): the REST/widget send path left NO trace — only
    # the bridge (`bridge.dispatch`) journaled, so an operator request to send something to zalo went out WITHOUT a
    # record and it was impossible to confirm what/whether it was sent. Record the send here just like the bridge
    # does (DURABLE journal + `cluster` event in the timeline/UI), marked `via:"rest"` to distinguish origin.
    try:
        from connectors.meshkore import journal
        journal.record({"chan": "out", "action": "cluster.send", "via": "rest",
                        "extra": {"name": body.name, "data": {"to": body.to, "text": text}}})
    except Exception:
        pass
    try:
        from voice.observer import emit as _emit
        _emit("cluster", f"⇢ {body.name}·{body.to or '*'}", text=text, role="assistant",
              extra={"cluster": body.name, "to": body.to or "*", "dir": "out", "via": "rest"})
    except Exception:
        pass
    return JSONResponse({"ok": True})


@router.post("/api/meshkore/disconnect")
async def disconnect(body: NameBody, _=Depends(_guard)):
    await meshkore.get_manager().disconnect(body.name)
    store.remove_cluster(body.name)
    return JSONResponse({"ok": True})
