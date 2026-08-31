#
# translated implementation note
#
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
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
    # translated implementation note
    # translated implementation note
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
