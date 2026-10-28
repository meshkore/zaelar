"""nucleo/picture_errand.py — an errand whose deliverable is PICTURES lands in the photo viewer.

Measured on `show-real-photo-of-a-new-car__us` (sandbox 20261011-115914-en, 3/5): eight photos of the Ferrari
Amalfi were on screen in `imagenes`; «are they really the Amalfi? … I'd rather be sure it's not the Roma» was
escalated with the surface `lista`, so a results SHEET opened beside the viewer, the research composer asked the
worker for ≥40 candidates, every `use_tool` search was forced to the fact route (23 web searches, none of them an
image search) and the one row that came back — «Ferrari Amalfi - Ferrari.com», a PAGE — went to the table. The
verified press photos the worker finally reached never got to the box he was looking at.

Four pieces, each at the seam both channels already share:

  · `from_screen` — the surface reading. The brief's own closed question now has a `imagenes` value
    (`surfaces.IMAGES`); when his words were unsure, the SCREEN decides: a turn that corrects what we just did
    (`corrects_last`, the brief's sure verdict) while the viewer holds pictures is about those pictures. No verb
    table: two verdicts and the viewer's state.
  · `prompt_blocks` — what the worker is told: the viewer is open, replace its set, scope the image search to
    the official site, and stop once it is delivered.
  · `search_route` — the worker's searches go to the IMAGE module of the search service.
  · `deliver` — what an image search brings is handed to the viewer by the engine, filtered to the site the query
    was scoped to, the same way `findings.hand_search_rows` hands rows to a sheet (V2-320).
"""
from __future__ import annotations

import re

from loguru import logger

VIEWER = "imagenes"
#: The fewest pictures that replace the set on screen: one lone match is not «the official photos».
MIN_PICTURES = 2
_SITE_RE = re.compile(r"\bsite:\s*([a-z0-9][a-z0-9.-]*\.[a-z]{2,})", re.I)

PICTURES_BLOCK = (
    "ENTREGA COMO FOTOS (la superficie de este encargo es el VISOR `imagenes`): el operador está MIRANDO el visor "
    "con las fotos de antes y lo que pidió es que esas fotos sean las buenas. NO hay hoja de resultados para este "
    "encargo: no escribas en `results`. Busca IMÁGENES, no páginas: `python -m nucleo.cli.bridge act use_tool "
    "\"<qué> site:<dominio oficial>\"` va al buscador de imágenes, y lo que devuelva DE ESE DOMINIO el motor lo "
    "pone él solo en el visor (lo verás en `viewer` del resultado). En cuanto `viewer.shown` traiga fotos del "
    "sitio oficial, TERMINA: di en una frase de dónde salen. Si el buscador no da nada del dominio, entra en su "
    "sala de prensa con el navegador y entrega tú con `python -m nucleo.cli.widget data imagenes show @fotos.json` "
    "(cada foto `{url, thumb, title, site, page}`, `source` = el dominio). Nada de dar vueltas: dos búsquedas "
    "acotadas al sitio antes del navegador, no veinte.")


def viewer_holds_pictures() -> bool:
    """Is the photo viewer on screen WITH pictures in it? Never raises."""
    try:
        from memory import api as memory
        if VIEWER not in ((memory.state() or {}).get("open_widgets") or []):
            return False
        from widgets.imagenes import data as _img
        return bool(_img.view_data().get("items"))
    except Exception as e:  # noqa: BLE001 — a reader never breaks a turn
        logger.debug(f"picture_errand: viewer unreadable — {type(e).__name__}: {e}")
        return False


def from_screen(brief, reading: str) -> str:
    """The brief's surface `reading`, or `imagenes` when his words were unsure and the screen is not.

    Only a reading that is empty or a sheet (`lista`/`item`) is overruled: a sure `informe`, `voz` or `silenciosa`
    is his words naming another deliverable, and the viewer being open does not change what he asked for."""
    from nucleo import surfaces as _s
    if reading not in ("", _s.LIST, _s.ITEM):
        return reading
    try:
        from nucleo.turn import brief as _tb
        verdict, info = _tb.read(brief, "corrects_last", "")
    except Exception:  # noqa: BLE001
        return reading
    if info is not None and verdict == "corrects_last" and viewer_holds_pictures():
        return _s.IMAGES
    return reading


def prompt_blocks(surface: str) -> list:
    from nucleo import surfaces as _s
    return [PICTURES_BLOCK] if _s.delivers_pictures(surface) else []


def search_route(rec) -> str:
    """The search-service module a worker's `use_tool` search runs on."""
    from nucleo import surfaces as _s
    return "images" if _s.delivers_pictures(getattr(rec, "surface", "")) else "inline_fact"


def _host(url: str) -> str:
    h = str(url or "").split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].lower()
    return h[4:] if h.startswith("www.") else h


def _of_site(host: str, site: str) -> bool:
    return bool(host) and (host == site or host.endswith("." + site))


def pictures_of_site(query: str, rows) -> tuple[str, list]:
    """(site, viewer items) — the rows whose picture OR page is on the site `query` was scoped to (`site:x`).
    No scope → ("", []): an unscoped search is not «from the official site» and must not replace his set."""
    m = _SITE_RE.search(str(query or ""))
    site = _host(m.group(1)) if m else ""
    if not site:
        return "", []
    items = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        img, page = str(r.get("image") or "").strip(), str(r.get("url") or "").strip()
        if img and (_of_site(_host(img), site) or _of_site(_host(page), site)):
            items.append({"url": img, "thumb": img, "title": str(r.get("title") or "")[:160],
                          "site": site, "page": page})
    return site, items


def deliver(rec, query: str, res: dict) -> bool:
    """Hand a picture errand's image search to the viewer. True = this errand delivers pictures (so nothing goes
    to a sheet), whether or not anything was shown; `res["viewer"]` tells the worker what happened."""
    from nucleo import surfaces as _s
    if not _s.delivers_pictures(getattr(rec, "surface", "")):
        return False
    site, items = pictures_of_site(query, res.get("candidates") or [])
    if len(items) < MIN_PICTURES:
        res["viewer"] = {"shown": 0, "site": site,
                         "why": "no site: scope in the query" if not site else f"fewer than {MIN_PICTURES} from {site}"}
        return True
    try:
        from widgets.imagenes import data as _img
        out = _img.apply_action("show", {"items": items, "query": str(query)[:120], "source": site,
                                         "title": str(getattr(rec, "title", "") or query)[:120]})
    except Exception as e:  # noqa: BLE001 — the viewer failing is said to the worker, never raised
        res["viewer"] = {"shown": 0, "site": site, "why": f"viewer error: {type(e).__name__}"}
        return True
    res["viewer"] = {"shown": int(out.get("n") or 0) if out.get("ok") else 0, "site": site}
    _open_if_closed(rec)
    return True


def _open_if_closed(rec) -> None:
    """The viewer comes up beside his work when it is not on screen (a worker's show opens in the background)."""
    try:
        from memory import api as memory
        if VIEWER in ((memory.state() or {}).get("open_widgets") or []):
            return
        from nucleo.acts import canvas
        canvas.apply("show", VIEWER, src=f"worker:{getattr(rec, 'task_id', '')}")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"picture_errand: viewer not opened — {type(e).__name__}: {e}")
