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
    vis: str = ""            # "public" → cluster abierto, sin token (V2-086)


class StageBody(BaseModel):
    name: str
    cluster_id: str
    token: str = ""          # V2-086: vacío en un cluster público — no falta, es que no existe
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
    """Resuelve la confirmación Sí/No de CONECTAR a un cluster desde la pestaña nativa «Clusters» (V2-086).

    Antes esto no existía: la confirmación se pedía sobre la tarjeta del widget `cluster-registro`, pero
    `/widgets/{id}/confirm` solo sabía resolver BORRADOS — así que el botón nunca conectaba nada y el único
    camino que cerraba el círculo era decir «sí» por voz. Ahora el botón funciona, por el MISMO camino
    (`dispatch_tag("cluster.connect")`) y con el mismo gate: sin un «sí» explícito no se abre ningún socket."""
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
    # OBSERVABILIDAD (2026-07-25, petición del operador "verificar que se haya enviado"): la ruta REST/widget de
    # envío NO dejaba rastro — solo journalizaba el bridge (`bridge.dispatch`), así que un "manda a zalo …" del
    # operador salía SIN registro y era imposible confirmar qué/si se mandó. Registramos aquí el envío igual que
    # el bridge (journal DURABLE + evento `cluster` en el timeline/UI), marcado `via:"rest"` para distinguir origen.
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
