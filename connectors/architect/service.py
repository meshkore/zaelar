#
# service.py — encargos al Architect: lanza el ask, hace poll (30s-10min por turno) y cierra el bucle.
#
# Mismo patrón que la generación de widgets (widgets/server_api.py): la acción es fire-and-forget para el brain
# (emite la tag y sigue hablando), y el RESULTADO vuelve por dos vías cuando llega — voz+UI (voice/proactive,
# que ya preempta y degrada solo) y una nota [SISTEMA] al siguiente turno (voice/brain_notes) para que el brain
# sepa el desenlace REAL y pueda responder follow-ups sin inventar ni cantar "hecho" antes de tiempo.
#
# Un encargo a la vez POR PROYECTO (regla del daemon: nunca dos asks en paralelo al mismo manager); un segundo
# encargo al mismo proyecto no se encola aquí — se rechaza con nota para que el brain lo gestione en conversación.
#
import asyncio
import os
import time

from loguru import logger

from connectors.architect import client
from connectors.architect.client import ArchitectBusy, ArchitectError

ASK_TIMEOUT = float(os.getenv("ARCHITECT_ASK_TIMEOUT", "900"))   # un turno del manager puede tardar ~10 min
_POLL_FAST, _POLL_SLOW = 3.0, 5.0                                # cadencia de poll: fina el 1er minuto, luego suave
_SPOKEN_MAX = 600            # respuestas más largas se hablan recortadas; el texto íntegro va en la nota [SISTEMA]

_inflight: dict[str, dict] = {}          # project -> {"text": str, "t0": float}


def inflight() -> dict[str, dict]:
    """Encargos en vuelo (para el brief del brain: que pueda responder '¿cómo va?' sin inventar)."""
    return dict(_inflight)


def _emit(*a, **k):
    try:
        from voice.observer import emit
        emit(*a, **k)
    except Exception:
        pass


def _note(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


async def ask(project: str, request: str) -> None:
    """Encargo (pregunta u orden, lenguaje natural) al architect-master de *project*. Corre hasta el desenlace."""
    project = (project or "").strip().lower()
    request = (request or "").strip()
    if not project or not request:
        return
    if not client.configured():
        _note(f"[SISTEMA] Encargo al Architect '{project}' NO enviado: falta ARCHITECT_TOKEN en .env.")
        return
    if project in _inflight:
        _note(f"[SISTEMA] El architect de '{project}' YA tiene un encargo en curso "
              f"(\"{_inflight[project]['text'][:80]}\"). El nuevo NO se envió; reenvíalo cuando termine.")
        return
    _inflight[project] = {"text": request, "t0": time.time()}
    _emit("brain", f"🏗️ Architect · ask → {project}", text=request, role="system")
    try:
        await _run_ask(project, request)
    finally:
        _inflight.pop(project, None)


async def _run_ask(project: str, request: str) -> None:
    from voice import proactive
    try:
        r = await client.ask(project, request)
        rid = str(r.get("request_id") or "")
        if not rid:
            raise ArchitectError(f"respuesta sin request_id: {str(r)[:120]}")
    except ArchitectBusy:
        _note(f"[SISTEMA] El architect de '{project}' está ocupado con otro turno (429). "
              "Encargo NO enviado; reintenta en unos minutos.")
        return
    except Exception as e:
        logger.warning(f"architect ask failed ({project}): {e}")
        _note(f"[SISTEMA] FALLO al enviar el encargo al architect de '{project}': {e}")
        await proactive.notify("Architect", f"No he podido enviar el encargo al proyecto {project}.", speak=True)
        return

    t0, last_err = time.time(), None
    while time.time() - t0 < ASK_TIMEOUT:
        await asyncio.sleep(_POLL_FAST if time.time() - t0 < 60 else _POLL_SLOW)
        try:
            st = await client.poll(project, rid)
            last_err = None
        except Exception as e:
            last_err = e                 # transitorio (daemon reiniciando, red): seguimos hasta el timeout
            continue
        status = (st.get("status") or "").lower()
        if status == "done":
            await _deliver(project, (st.get("result_text") or "").strip())
            return
        if status == "error":
            msg = (st.get("result_text") or "error sin detalle").strip()
            _note(f"[SISTEMA] El architect de '{project}' devolvió ERROR: {msg[:800]}")
            await proactive.notify(f"Architect · {project}",
                                   f"El encargo al proyecto {project} ha fallado.", speak=True)
            return
    tail = f" (último error de poll: {last_err})" if last_err else ""
    _note(f"[SISTEMA] Encargo al architect de '{project}' SIN respuesta tras {int(ASK_TIMEOUT / 60)} min{tail}. "
          "Puede seguir corriendo (visible en el cockpit); pregunta más tarde con otro [[architect.ask]].")


async def _deliver(project: str, result: str) -> None:
    from voice import proactive
    result = result or "(el manager no devolvió texto)"
    t0 = (_inflight.get(project) or {}).get("t0")
    extra = {"architect_ms": round((time.time() - t0) * 1000)} if t0 else None
    _emit("brain", f"🏗️ Architect · {project}: done", text=result, role="assistant", extra=extra)
    _note(f"[SISTEMA] El architect de '{project}' ha terminado tu encargo. Su respuesta (para tu contexto; "
          f"si ya se entregó por voz, no la repitas entera):\n{result[:4000]}")
    spoken = result if len(result) <= _SPOKEN_MAX else \
        result[:_SPOKEN_MAX].rsplit(" ", 1)[0] + " … (te cuento el resto si quieres)"
    await proactive.notify(f"Architect · {project}", spoken, speak=True)


async def new_project(data: dict | None) -> None:
    """[[architect.new]]{"name", "parent"?} — crear un proyecto nuevo; parent cae a ARCHITECT_PARENT (.env)."""
    from voice import proactive
    data = data or {}
    name = (data.get("name") or "").strip()
    parent = (data.get("parent") or os.getenv("ARCHITECT_PARENT", "")).strip()
    if not name:
        _note('[SISTEMA] [[architect.new]] sin "name" — no se creó nada.')
        return
    if not parent:
        _note(f"[SISTEMA] No sé en qué carpeta crear el proyecto '{name}': falta \"parent\" en la tag "
              "y ARCHITECT_PARENT en .env. Pregunta al operador dónde debe vivir.")
        return
    _emit("brain", f"🏗️ Architect · new project '{name}'", text=parent, role="system")
    try:
        await client.create_project(parent, name)
    except Exception as e:
        logger.warning(f"architect create_project failed ({name}): {e}")
        _note(f"[SISTEMA] FALLO creando el proyecto '{name}' en {parent}: {e}")
        await proactive.notify("Architect", f"No he podido crear el proyecto {name}.", speak=True)
        return
    from connectors.architect import brief
    brief.invalidate()
    _note(f"[SISTEMA] Proyecto '{name}' creado en {parent} (estándar MeshKore + equipo por defecto). "
          f"Ya puedes encargarle trabajo con [[architect.ask:{name}]].")
    await proactive.notify("Architect", f"Proyecto {name} creado y listo.", speak=True)
