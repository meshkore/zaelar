#
# HTTP surface for the «Colmena» cron — powers the UI ⏰ panel (frontend/app/components/CronPanel.js).
#
# v2 «Colmena» (V2-005/009): replaces the old Hermes `/api/cron` (brains/hermes/cron_api.py, retired).
# The engine's OWN proactivity lives in `nucleo/scheduler.py` (tasks persisted in `memory.journal`,
# fired by the orchestrator loop `nucleo/loop.py`). This router is only the MANUAL surface: list,
# create and delete scheduled tasks. Mounted under the brain whose loop actually fires them (V2-601
# T-14: mounting it under a brain that does not run the loop is the V2-121 silent-alarm class).
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
    # The panel expects {jobs:[{id,name,schedule,prompt,state,paused,...}]}. `state`/`paused` are from
    # the Hermes era (pause/resume); this scheduler does not pause — a task is active until it is met
    # or deleted.
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
