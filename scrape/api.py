"""scrape/api.py — the HTTP face of the module (V2-846): `POST /api/scrape/read` {url, want?, country?}.

The same door as `scrape.read`, for whoever reads a page from outside this process (a generated widget reaches the
web only through the host, the panel, a test). The HTML stays inside: the answer is the records and how they came.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body

router = APIRouter()


@router.post("/api/scrape/read")
async def read(body: dict = Body(...)):
    from scrape import read as _read
    b = body if isinstance(body, dict) else {}
    url = str(b.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"url": url, "n": 0, "records": [], "failure": "an absolute http(s) url is required", "tried": []}
    res = await asyncio.to_thread(_read, url, str(b.get("want") or "listings"), country=str(b.get("country") or ""))
    return res.to_dict()
