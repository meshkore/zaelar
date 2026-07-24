"""Screen routes (HTML). The interface is a self-contained module under frontend/."""
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .common import ZAELAR_DIR

router = APIRouter()

FRONTEND = os.path.join(ZAELAR_DIR, "frontend")


def front(*parts: str) -> str:
    return os.path.join(FRONTEND, *parts)


@router.get("/")
async def home():
    # no-store so a reload always gets the latest UI (avoids running stale cached JS)
    return FileResponse(front("index.html"), headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/debug")
async def debug_page():
    return FileResponse(front("pages", "debug.html"), headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/api/brain")
async def brain():
    """The brain active for this run — "nucleo" (zaelar's own «Colmena» brain) by default, or a baseline
    ("direct"/"local"). The UI uses it to decide which brain-specific affordances to show."""
    from config.v2 import active_brain
    return {"brain": active_brain()}
