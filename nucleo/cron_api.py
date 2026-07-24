#
# HTTP surface for the «Colmena» cron — powers the UI ⏰ panel (frontend/app/components/CronPanel.js).
#
# v2 «Colmena» (V2-005/009): sustituye al viejo /api/cron de Hermes (brains/hermes/cron_api.py, retirado). El
# motor de proactividad PROPIO vive en `nucleo/scheduler.py` (tareas persistidas en `memory.journal`, disparadas
# por el loop orquestador `nucleo/loop.py`). Este router es solo la superficie manual: listar, crear y borrar
# tareas programadas. Se monta SIEMPRE (el panel es una capacidad del sistema, ya no específica de un brain).
#
from fastapi import APIRouter
from pydantic import BaseModel

from nucleo import scheduler

router = APIRouter()


class RefBody(BaseModel):
    ref: str


class CreateBody(BaseModel):
    schedule: str
    prompt: str = ""
    name: str = ""
    repeat: str = ""


@router.get("/api/cron")
async def list_cron():
    # El panel espera {jobs:[{id,name,schedule,prompt,state,paused,...}]}. `state`/`paused` son de la era Hermes
    # (pausar/reanudar); el scheduler propio no pausa — una tarea está activa hasta que se cumple o se borra.
    jobs = []
    for j in scheduler.list_jobs(active_only=True):
        jobs.append({**j, "state": "activo", "paused": False})
    return {"jobs": jobs}


@router.post("/api/cron/create")
async def create_cron(body: CreateBody):
    r = scheduler.create(body.prompt, body.schedule, name=body.name, repeat=body.repeat)
    return {"ok": bool(r.get("ok")), "message": r.get("display") or r.get("error") or ""}


@router.post("/api/cron/remove")
async def remove_cron(body: RefBody):
    ok = scheduler.cancel(body.ref)
    return {"ok": ok, "message": "tarea cancelada" if ok else "no encontrada"}
