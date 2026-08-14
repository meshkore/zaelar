#
# brief.py — what the BRAIN needs to know about the Architect provider: tags + live projects + in-flight tasks.
#
# COMPACT: re-injected every turn (duo rebuilds its system prompt per turn) and MUST NOT block —
# build_fast_system() is synchronous — so the project list is served from cache and refreshed in the background
# when it expires. The token NEVER appears here.
#
import asyncio
import time

from loguru import logger

PROTOCOL = """[ARCHITECT MeshKore] Proveedor de código/proyectos (daemon local compartido): cada proyecto tiene un manager (architect-master) que planifica, ancla tareas en su roadmap y despacha agentes; tú solo le transmites la intención del operador en lenguaje natural (preguntas Y órdenes van igual). Tags SILENCIOSAS (nunca se hablan):
  [[architect.ask:<proyecto>]]<pregunta u orden, clara y con el contexto necesario>[[/architect.ask]] — ASÍNCRONO (30s-10min): el resultado llega solo por voz/nota. Al emitirla di que lo pones en marcha; NUNCA digas "hecho" ni inventes el resultado.
  [[architect.new]]{"name":"<nombre>","parent":"<carpeta absoluta, opcional>"}[[/architect.new]] — crea un proyecto nuevo (estándar MeshKore + equipo por defecto); luego se le encarga trabajo con architect.ask.
Un encargo a la vez por proyecto. El manager recuerda su conversación: para seguimiento, pregunta de nuevo ("¿cómo va X?"). Toda la actividad es visible para el operador en su cockpit."""

_TTL = 60.0
_cache = {"projects": None, "ts": 0.0}
_refreshing = {"v": False}
_TASKS: set = set()          # strong refs: asyncio only keeps weak refs to tasks


def invalidate() -> None:
    """Force project relisting on the next brief (e.g. after creating a new one)."""
    _cache["ts"] = 0.0


def _refresh_soon() -> None:
    if _refreshing["v"]:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return                          # no loop (tests/CLI): keep whatever cache exists

    async def _do():
        try:
            from connectors.architect import client
            projects = await client.list_projects()
            _cache["projects"] = [str(p.get("id") or p.get("name") or "") for p in projects if isinstance(p, dict)]
            _cache["ts"] = time.time()
        except Exception as e:
            logger.debug(f"architect brief refresh failed: {e}")
            _cache["ts"] = time.time() - _TTL + 15.0    # retry in ~15s, without hammering the daemon
        finally:
            _refreshing["v"] = False

    _refreshing["v"] = True
    t = loop.create_task(_do())
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


def for_brain() -> str:
    """Protocol + live projects (cached) + in-flight tasks, for brain context. Never blocks."""
    from connectors.architect import client, service
    if not client.configured():
        return PROTOCOL + "\n[Architect ahora] SIN token (ARCHITECT_TOKEN en .env) — canal no operativo."
    if time.time() - _cache["ts"] > _TTL:
        _refresh_soon()
    ps = _cache["projects"]
    status = "\n[Proyectos ahora] " + (", ".join(p for p in ps if p) if ps else
                                       "aún sin listar (la lista llega en unos segundos)")
    jobs = service.inflight()
    if jobs:
        lines = "; ".join(f"{p}: \"{j['text'][:60]}\" (hace {max(1, int((time.time() - j['t0']) / 60))} min)"
                          for p, j in jobs.items())
        status += f"\n[Encargos Architect en curso] {lines} — sigue(n) corriendo; NO digas que está hecho."
    return PROTOCOL + status
