"""
observability/api.py — superficie HTTP de lectura (`/api/observability/*`) + ciclo de vida de la SESIÓN.

Dos superficies con permisos DISTINTOS, y la diferencia importa:

**ABIERTA** — la usa la propia interfaz de esta instalación desde el navegador del operador, que en un despliegue
remoto NO es loopback. No expone contenido:
  GET  /api/observability/identity          → quién es esta instalación y qué sesión hay abierta
  GET  /api/observability/catalog           → el mapa de familias/tipos que pinta el filtro del visor
  POST /api/observability/session/start     → ciclo de la sesión de trabajo: solo el frontend sabe cuándo el
  POST /api/observability/session/end         operador arranca y para el agente de verdad (pestaña, botón ⏻)

**PROTEGIDA** — devuelve el CONTENIDO (frases del operador, prompts, resultados de búsqueda, lo que trajo un
worker). Quien pueda leer esto puede leer la conversación entera, así que pasa por `_allowed()`:
  GET  /api/observability/flows             → últimos flujos con su resumen (duración, piezas, tokens, errores)
  GET  /api/observability/flow/{corr_id}    → un flujo completo, en orden
  GET  /api/observability/sessions          → últimas sesiones de trabajo
  GET  /api/observability/session/{sid}     → UNA sesión con su forma (para abrirla y auditarla)
  GET  /api/observability/events            → eventos en crudo con cursor `since_id` (seguir una sesión viva)
  GET  /api/observability/stats             → cobertura de los ejes

`session/end` acepta cuerpo vacío a propósito: lo dispara `sendBeacon` al cerrar la pestaña, que no puede
negociar nada.
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import flows as _flows
from . import identity as _identity

router = APIRouter()

# ── QUIÉN PUEDE LEER EL CONTENIDO ─────────────────────────────────────────────────────────────────────────────
# Estas rutas nacieron para el visor local y eran ABIERTAS: en una instalación en casa da igual (el puerto solo
# lo alcanza la propia máquina), pero el mismo código corre en despliegues donde el puerto SÍ es alcanzable —
# y ahí «abierto» significa que cualquiera que dé con la URL se lleva las conversaciones. Patrón
# guarded-until-configured, el mismo del resto del sistema:
#
#   · sin `ZAELAR_OBS_TOKEN` → **solo loopback**. Una instalación local funciona exactamente igual que antes.
#   · con `ZAELAR_OBS_TOKEN` → hace falta la cabecera `X-Observability-Token`, venga de donde venga. Es lo que
#     permite que una herramienta de operación consulte una instancia remota SIN abrir el contenido al mundo.
#
# Fail-closed: si no se puede determinar el origen (sin `request.client`), se deniega.
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def _allowed(request: Request) -> bool:
    token = (os.getenv("ZAELAR_OBS_TOKEN") or "").strip()
    if token:
        got = request.headers.get("x-observability-token") or ""
        return hmac.compare_digest(got, token)     # comparación en tiempo constante: no filtra el prefijo válido
    host = (getattr(request, "client", None).host if getattr(request, "client", None) else "") or ""
    return host in _LOOPBACK


_DENIED = JSONResponse(
    {"error": "forbidden",
     "detail": "la observabilidad con contenido es local; define ZAELAR_OBS_TOKEN y manda X-Observability-Token"},
    status_code=403,
)


@router.get("/api/observability/identity")
async def identity_state():
    return JSONResponse(_identity.session_info())


@router.get("/api/observability/catalog")
async def catalog():
    """El MAPA COMPLETO de lo que se puede filtrar: cada `kind` que el sistema sabe emitir y a qué familia
    pertenece. El visor lo pinta ENTERO al desplegar los filtros, en vez de ir descubriéndolo según llegan
    eventos — así el operador ve de una lo que puede encender y apagar, incluso lo que hoy no ha ocurrido.

    La fuente es `voice/observer.py::_CAT`, la MISMA que sella la familia de cada evento: el frontend no
    duplica el mapa, lo pide. Un test impide que un kind nuevo se quede fuera
    (`tests/infrastructure/unit/core/test_observer_categories.py`)."""
    from voice import observer as _obs
    return JSONResponse({"kinds": dict(sorted(_obs._CAT.items()))})


@router.get("/api/observability/flows")
async def list_flows(request: Request, limit: int = 50, session_id: str = "", user_id: str = ""):
    if not _allowed(request):
        return _DENIED
    return JSONResponse({"flows": _flows.flows(limit=min(limit, 500), session_id=session_id, user_id=user_id)})


@router.get("/api/observability/flow/{corr_id}")
async def one_flow(request: Request, corr_id: str, limit: int = 500):
    if not _allowed(request):
        return _DENIED
    return JSONResponse({"corr_id": corr_id, "events": _flows.flow(corr_id, limit=min(limit, 2000))})


@router.get("/api/observability/sessions")
async def list_sessions(request: Request, limit: int = 30, user_id: str = ""):
    if not _allowed(request):
        return _DENIED
    # `current` deja claro cuál de ellas está VIVA. Sin esto, quien lee tiene que adivinarlo comparando marcas de
    # tiempo — y una sesión viva y una que murió hace un minuto se parecen mucho.
    # `session_id`, NO `id`: es la clave que devuelve `identity.session_info()`. Con la clave equivocada esto
    # daba "" en silencio y NINGUNA sesión salía marcada como viva — el fallo más caro posible en una vista de
    # auditoría, porque no parece un error: parece que no hay nadie trabajando.
    return JSONResponse({"sessions": _flows.sessions(limit=min(limit, 500), user_id=user_id),
                         "current": _identity.session_info().get("session_id") or ""})


@router.get("/api/observability/session/{session_id}")
async def one_session(request: Request, session_id: str):
    if not _allowed(request):
        return _DENIED
    info = _flows.session(session_id)
    if not info:
        return JSONResponse({"error": "unknown_session", "session_id": session_id}, status_code=404)
    info["live"] = (session_id == (_identity.session_info().get("session_id") or ""))
    # `flows` (número, del resumen) y `flows_detail` (la lista) son campos DISTINTOS a propósito: meter la lista
    # en `flows` pisaba el contador del resumen y quien leyera «flows» recibía a veces un número y a veces un
    # array según la ruta. Un mismo nombre con dos tipos es una trampa para el que consuma esto.
    info["flows_detail"] = _flows.flows(limit=500, session_id=session_id)
    return JSONResponse(info)


@router.get("/api/observability/events")
async def raw_events(request: Request, session_id: str = "", corr_id: str = "",
                     since_id: int = 0, limit: int = 500):
    """Eventos en crudo con cursor. Es la ruta que sirve para DOS cosas a la vez: seguir una sesión viva
    (llamando con el último `id` visto) y archivarla entera (paginando desde 0)."""
    if not _allowed(request):
        return _DENIED
    rows = _flows.events(session_id=session_id, corr_id=corr_id,
                         since_id=since_id, limit=min(limit, 2000))
    return JSONResponse({"events": rows, "last_id": (rows[-1]["id"] if rows else int(since_id)),
                         "more": len(rows) == min(limit, 2000)})


@router.get("/api/observability/stats")
async def stats(request: Request):
    if not _allowed(request):
        return _DENIED
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
