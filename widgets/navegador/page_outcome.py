"""widgets/navegador/page_outcome.py — what every navigation BROUGHT BACK (V2-837 G6).

A 403 used to be inferred from a page title («Ups! Parece que algo no va bien»): 0 of 425 browser events of one
session carried a status code, a load time or a size, so «the site blocked us» could not be told from «the page was
slow» or «it loaded and had nothing». One listener on the browser CONTEXT — every tab, every navigation, a `goto` or
a click alike — keeps the last main-frame document outcome per page:

    status   the HTTP status (0 = the request failed before any answer)
    ms       time to the end of the response, from the browser's own timing
    bytes    the document's declared size (`content-length`), when the server says it
    wall     none · antibot · captcha · http — read through `walls.py`, the one definition of a wall

It is taken ONCE by the next row the tab already emits (`screenshot`), so the record gains the facts without a new
event. Pure bookkeeping, fail-soft: a listener that throws never touches the navigation.
"""
from __future__ import annotations

from loguru import logger

_last: dict[int, dict] = {}        # id(page) → the latest main-frame outcome, until a row takes it


def classify(status: int, url: str) -> str:
    """The wall an outcome is, from the one wall vocabulary (`walls.py`): a captcha page, an anti-bot refusal (by its
    status or its URL), any other HTTP failure, or none. Login is not decidable from a response: the login watcher
    owns it."""
    from scrape import walls
    u = (url or "").lower()
    if "/recaptcha/" in u:
        return "captcha"
    if walls.status_wall_reason(int(status or 0)) or walls.wall_reason(url):
        return "antibot"
    if not status or int(status) >= 400:
        return "http"
    return "none"


def _ms(request) -> int | None:
    try:
        t = request.timing or {}
        end = t.get("responseEnd")
        if end is None or end < 0:
            end = t.get("responseStart")
        return round(end) if end is not None and end >= 0 else None
    except Exception as e:  # noqa: BLE001
        logger.debug(f"page_outcome._ms: {e!r}")
        return None


def _main_document(request) -> bool:
    try:
        return request.resource_type == "document" and request.frame == request.frame.page.main_frame
    except Exception as e:  # noqa: BLE001
        logger.debug(f"page_outcome._main_document: {e!r}")
        return False


def _note(page, out: dict) -> None:
    if len(_last) > 64:                # pages that closed without a row taking theirs
        _last.clear()
    _last[id(page)] = out


def on_response(response) -> None:
    try:
        req = response.request
        if not _main_document(req):
            return
        headers = response.headers or {}
        size = headers.get("content-length")
        out = {"status": int(response.status), "ms": _ms(req),
               "bytes": int(size) if str(size or "").isdigit() else None,
               "wall": classify(response.status, response.url)}
        _note(req.frame.page, {k: v for k, v in out.items() if v is not None})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"page_outcome.on_response: {e!r}")
        pass


def on_failed(request) -> None:
    try:
        if _main_document(request):
            _note(request.frame.page, {"status": 0, "wall": "http", "ms": _ms(request),
                                       "error": str(request.failure or "")[:120]})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"page_outcome.on_failed: {e!r}")
        pass


def attach(context) -> None:
    """Called once where the browser context is born: every page it opens is covered."""
    try:
        context.on("response", on_response)
        context.on("requestfailed", on_failed)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"page_outcome.attach: {e!r}")
        pass


def take(page) -> dict:
    """The outcome of the navigation this page last made, once (the next row's), or {} when none is new."""
    return _last.pop(id(page), None) or {}
