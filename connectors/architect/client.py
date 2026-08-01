#
# client.py — HTTP client del daemon MeshKore (remote control del Architect).
#
# El daemon es un servicio ÚNICO compartido en esta máquina (NO por-proyecto) que sirve a todos los proyectos
# del cluster. Este cliente habla su API REST: listar/crear proyectos y conversar con el architect-master de
# cada proyecto (ask asíncrono + poll). Reglas del daemon que este cliente respeta: Authorization en cada
# request, X-MeshKore-Project para enrutar, y UN turno a la vez por proyecto (429 → ArchitectBusy).
#
# Config (.env, gitignored — el token JAMÁS se commitea ni se muestra):
#   ARCHITECT_URL    — base del daemon (def: https://127.0.0.1:5573)
#   ARCHITECT_TOKEN  — bearer token del remote control (el operador lo rota desde el cockpit si se filtra)
#
import os
from urllib.parse import urlparse

import aiohttp


class ArchitectError(RuntimeError):
    pass


class ArchitectBusy(ArchitectError):
    """El manager del proyecto ya tiene un turno en vuelo (429) — esperar y reintentar, nunca en paralelo."""


def base_url() -> str:
    # V2-083: store dinámico manda (configurable desde Conectores); env como fallback power-user; default loopback.
    try:
        from config import connectors as _cfg
        u = str((_cfg.get("architect") or {}).get("url") or "").strip()
        if u:
            return u.rstrip("/")
    except Exception:
        pass
    return os.getenv("ARCHITECT_URL", "https://127.0.0.1:5573").rstrip("/")


def token() -> str:
    # V2-083: el token vive en el store dinámico de conectores (config/connectors.json), gestionable/revocable desde
    # la pestaña Conectores. `.env` (ARCHITECT_TOKEN) queda solo como fallback power-user/headless.
    try:
        from config import connectors as _cfg
        t = str((_cfg.get("architect") or {}).get("token") or "").strip()
        if t:
            return t
    except Exception:
        pass
    return (os.getenv("ARCHITECT_TOKEN") or "").strip()


def configured() -> bool:
    return bool(token())


def _ssl():
    # El daemon usa TLS autofirmado: relajamos la verificación SOLO cuando es loopback (su despliegue normal).
    host = (urlparse(base_url()).hostname or "").lower()
    return False if host in ("127.0.0.1", "localhost", "::1") else None


def _headers(project: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {token()}"}
    if project:
        h["X-MeshKore-Project"] = project
    return h


async def _request(method: str, path: str, *, project: str | None = None,
                   body: dict | None = None, timeout: float = 20.0):
    if not configured():
        raise ArchitectError("ARCHITECT_TOKEN no configurado en .env")
    to = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=to, connector=aiohttp.TCPConnector(ssl=_ssl())) as s:
        async with s.request(method, base_url() + path, headers=_headers(project), json=body) as r:
            if r.status == 429:
                raise ArchitectBusy(f"{path}: el proyecto ya tiene un turno en curso (429)")
            if r.status in (401, 403):
                raise ArchitectError(f"{path}: acceso revocado o token rotado ({r.status}) — "
                                     "pide al operador el token nuevo (cockpit → Config → Remote control)")
            if r.status >= 400:
                raise ArchitectError(f"{path}: HTTP {r.status} · {(await r.text())[:200]}")
            return await r.json()


async def list_projects() -> list[dict]:
    """Proyectos vivos en el daemon: [{id, name, path}]. Cambia — re-listar siempre que haya duda."""
    data = await _request("GET", "/projects")
    return data if isinstance(data, list) else (data or {}).get("projects", [])


async def ask(project: str, text: str) -> dict:
    """Envía el intent del operador al architect-master del proyecto. → 202 {"request_id", "conv"}."""
    return await _request("POST", "/team/architect-master/ask", project=project, body={"text": text})


async def poll(project: str, request_id: str) -> dict:
    """Estado de un ask: {"status": "queued|running|done|error", "result_text": "..."}."""
    return await _request("GET", f"/team/requests/{request_id}", project=project)


async def create_project(parent: str, name: str) -> dict:
    """Crea un proyecto nuevo (carpeta + estándar MeshKore + equipo por defecto) y lo registra en el daemon."""
    return await _request("POST", "/projects", body={"parent": parent, "name": name}, timeout=120.0)
