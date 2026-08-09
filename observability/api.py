"""
observability/api.py — superficie HTTP de lectura (`/api/observability/*`) + ciclo de vida de la SESIÓN.

Lectura (para el visor, para un análisis a mano y, más adelante, para el backoffice):
  GET  /api/observability/identity          → quién es esta instalación y qué sesión hay abierta
  GET  /api/observability/flows             → últimos flujos con su resumen (duración, piezas, tokens, errores)
  GET  /api/observability/flow/{corr_id}    → un flujo completo, en orden
  GET  /api/observability/sessions          → últimas sesiones de trabajo
  GET  /api/observability/stats             → cobertura de los ejes (cuántos eventos llevan corr/sesión/usuario)

Escritura — SOLO el ciclo de sesión, y solo desde el frontend, porque es el único que sabe cuándo el operador
arranca y para el agente de verdad (abrir/cerrar la pestaña, botón ⏻):
  POST /api/observability/session/start
  POST /api/observability/session/end

`end` acepta cuerpo vacío a propósito: lo dispara `sendBeacon` al cerrar la pestaña, que no puede negociar nada.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import flows as _flows
from . import identity as _identity

router = APIRouter()


@router.get("/api/observability/identity")
async def identity_state():
    return JSONResponse(_identity.session_info())


@router.get("/api/observability/flows")
async def list_flows(limit: int = 50, session_id: str = "", user_id: str = ""):
    return JSONResponse({"flows": _flows.flows(limit=min(limit, 500), session_id=session_id, user_id=user_id)})


@router.get("/api/observability/flow/{corr_id}")
async def one_flow(corr_id: str, limit: int = 500):
    return JSONResponse({"corr_id": corr_id, "events": _flows.flow(corr_id, limit=min(limit, 2000))})


@router.get("/api/observability/sessions")
async def list_sessions(limit: int = 30, user_id: str = ""):
    return JSONResponse({"sessions": _flows.sessions(limit=min(limit, 500), user_id=user_id)})


@router.get("/api/observability/stats")
async def stats():
    return JSONResponse(_flows.stats())


@router.post("/api/observability/session/start")
async def session_start(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    info = _identity.begin_session(str((body or {}).get("source") or "frontend"),
                                   force=bool((body or {}).get("force")))
    return JSONResponse({"session_id": info.get("id"), "user_id": _identity.user_id()})


@router.post("/api/observability/session/end")
async def session_end(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    info = _identity.end_session(str((body or {}).get("reason") or "frontend"))
    return JSONResponse({"ended": info.get("id")})
