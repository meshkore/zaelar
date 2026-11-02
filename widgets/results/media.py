"""widgets/results/media.py — every row brings its picture (V2-840 H4, the door half).

A row a worker hands over with a `url` and no `image` is a thing with a page and no face: the sheet drew a monogram
where the car, the flat or the guitar should have been (2026-11-02: three AutoScout24 ads, not one photo, not even in
the record). The page already DECLARES its cover — `og:image`/`twitter:image`, the picture a site gives every link
preview — so the door reads it (`search.extract.declared_cover`) instead of asking the worker to.

And a picture that reaches the sheet as a remote URL is still not on screen: a hotlink block, a CDN link that expires
or an `http://` image inside the engine's page each leave an empty plate. So every picture is COPIED once into the
results widget's own data folder and the row points at the engine's asset route (`/widgets/results/asset/<name>`).

The rules, in the order they bite:
  · **after the push, never in it** — `fill()` only decides what is missing and hands it to a background thread;
    the row lands now, the picture arrives with a later save and its own repaint event;
  · **one fetch per page or picture** — rows that share a page share its fetch; a key already being fetched, or
    resolved in this process, is not fetched again;
  · **bounded** — `_WORKERS` fetches at a time, each with its timeout and byte cap (`search.public_fetch`, which also
    refuses any host that is not public, at every redirect);
  · **images only** — a header that says `image/` AND bytes that are a JPEG, PNG, GIF, WebP or AVIF; SVG is not one
    (it is a document that can carry script), nor is anything a server labels as an image and is not;
  · **a template without a plate gets nothing** — an `offer` row draws its seller's logo and a `link` row its site's
    icon (`js/parts.js::itemKind`); their kind is read the same way here, so a tariff never grows a photo;
  · **a failure leaves the row as it was** and is counted by reason in the `widget media` event.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from .sheet_names import WIDGET_ID

#: Off inside the test suite (`tests/conftest.py`): the default fetcher is the network. Tests inject `fetch`.
LIVE = True

#: A picture is what its BYTES say (`_signature`), whatever its header claimed: the header must only say `image/`.
_PAGE_TYPES = ("text/html", "application/xhtml+xml")
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_PAGE_BYTES = 600 * 1024        # the head of a page, where it declares its cover
_TIMEOUT_S = 8.0
_WORKERS = 4
_MEMO_MAX = 600
_RETRY_FAILED_S = 900.0             # a page that refused is not asked again on every append, but not forever either
_PREFIX = "pic-"
_MAX_FILES = 800                    # the folder keeps the newest pictures; an older sheet's row falls back to its plate
LOCAL = f"/widgets/{WIDGET_ID}/asset/"

#: The kinds whose template has no photo plate (mirrors `js/parts.js::ITEM_KINDS` minus `video`, which has one).
_NO_PLATE = ("offer", "link")

_pool = ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="results-media")
_lock = threading.Lock()
_inflight: set[str] = set()
_memo: dict[str, tuple[str, str, float]] = {}      # key → (local url, "", at) or ("", reason, at)


def is_local(url) -> bool:
    return str(url or "").startswith(LOCAL)


def _remote(url) -> bool:
    return str(url or "").startswith(("http://", "https://"))


def _kind(it: dict, list_kind: str, layout: str) -> str:
    """The template a row is drawn with — the same reading as `js/parts.js::itemKind`."""
    own = str(it.get("kind") or "").strip().lower()
    if own in ("offer", "video", "link"):
        return own
    lk = str(list_kind or "").strip().lower()
    if lk in ("offer", "video", "link"):
        return lk
    if layout != "rows" or it.get("parts") or it.get("blocks"):
        return ""
    if it.get("price"):
        return "offer"
    if it.get("url") and not it.get("score"):
        return "link"
    return ""


def has_picture(it: dict) -> bool:
    return bool(it.get("image") or [u for u in (it.get("images") or []) if u])


def wants_picture(it: dict, data: dict) -> bool:
    """A row whose template draws a photo. A tariff (`offer`) or a page (`link`) keeps its no-photo template."""
    return _kind(it, data.get("kind") or "", str(data.get("layout") or "")) not in _NO_PLATE


def jobs(data: dict) -> list[tuple[str, str]]:
    """What the sheet is missing, as (job, url): `cover` = read this page's declared cover, `copy` = make this remote
    picture local. One entry per distinct url, in list order."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(job, url):
        if (job, url) not in seen:
            seen.add((job, url))
            out.append((job, url))
    for it in data.get("items") or []:
        if not isinstance(it, dict) or not wants_picture(it, data):
            continue
        if _remote(it.get("image")):
            add("copy", it["image"])
        for u in it.get("images") or []:
            if _remote(u):
                add("copy", u)
        if not has_picture(it) and _remote(it.get("url")):
            add("cover", it["url"])
    return out


# ── the fetchers (network) ───────────────────────────────────────────────────────────────────────────────────
def _net_get(url: str, *, accept, max_bytes: int, truncate: bool = False):
    from search import public_fetch
    return public_fetch.get(url, accept=accept, max_bytes=max_bytes, timeout=_TIMEOUT_S, truncate=truncate)


def _signature(body: bytes) -> str:
    """The image type the BYTES say, whatever the header said; "" when they are not one of ours."""
    if body[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    if body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis"):
        return ".avif"
    return ""


def _folder() -> str:
    from widgets import store
    return store.data_dir(WIDGET_ID)


def copy_picture(url: str, get=_net_get) -> str:
    """The picture at `url`, downloaded once into the widget's folder → its local URL. Raises `Refused`."""
    from search.public_fetch import Refused
    name = _PREFIX + hashlib.sha256(url.encode("utf-8", "replace")).hexdigest()[:24]
    folder = _folder()
    for e in os.scandir(folder):
        if e.name.startswith(name + "."):
            return LOCAL + e.name                          # downloaded before: the same file serves again
    got = get(url, accept=("image/",), max_bytes=_MAX_IMAGE_BYTES)
    ext = _signature(got.body)
    if not ext:
        raise Refused("not_an_image")
    path = os.path.join(folder, name + ext)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(got.body)
    os.replace(tmp, path)
    _prune(folder)
    return LOCAL + name + ext


def _prune(folder: str) -> None:
    try:
        pics = sorted((e for e in os.scandir(folder) if e.name.startswith(_PREFIX) and e.is_file()),
                      key=lambda e: e.stat().st_mtime)
        for e in pics[:max(0, len(pics) - _MAX_FILES)]:
            os.remove(e.path)
    except OSError as e:
        logger.debug(f"results.media: prune failed ({e!r})")


def cover_of(page_url: str, get=_net_get) -> str:
    """The page's declared cover, copied → its local URL. Raises `Refused` (`no_cover` when it declares none)."""
    from search import extract
    from search.public_fetch import Refused
    page = get(page_url, accept=_PAGE_TYPES, max_bytes=_MAX_PAGE_BYTES, truncate=True)
    cover = extract.declared_cover(page.body.decode("utf-8", "replace"), page.url)
    if not _remote(cover):
        raise Refused("no_cover")
    return copy_picture(cover, get)


def _resolve(job: str, url: str, get) -> tuple[str, str]:
    from search.public_fetch import Refused
    try:
        local = cover_of(url, get) if job == "cover" else copy_picture(url, get)
        return local, ""
    except Refused as e:
        return "", e.reason
    except Exception as e:  # noqa: BLE001 — a picture that cannot be fetched never takes the sheet with it
        return "", "error:" + type(e).__name__


# ── the door's hook ──────────────────────────────────────────────────────────────────────────────────────────
def fill(sheet: str, data: dict, *, get=None, spawn=None) -> dict:
    """Called after a push is saved: {no_picture, queued}. `no_picture` = rows on the list whose template draws a
    photo and that carry none; `queued` = page or picture fetches handed to the background now."""
    rows = [it for it in data.get("items") or [] if isinstance(it, dict)]
    missing = sum(1 for it in rows if wants_picture(it, data) and not has_picture(it))
    if get is None and not LIVE:
        return {"no_picture": missing, "queued": 0}
    todo = []
    with _lock:
        for job, url in jobs(data):
            key = job + " " + url
            if key in _inflight:
                continue
            _inflight.add(key)
            todo.append((job, url))
    if todo:
        run = lambda: _run(sheet, todo, get or _net_get)  # noqa: E731
        (spawn or (lambda fn: _pool.submit(fn)))(run)
    return {"no_picture": missing, "queued": len(todo)}


def _run(sheet: str, todo: list[tuple[str, str]], get) -> None:
    t0 = time.monotonic()
    resolved: dict[str, tuple[str, str]] = {}
    try:
        for job, url in todo:
            key = job + " " + url
            with _lock:
                m = _memo.get(key)
            if m is not None and (not m[1] or time.monotonic() - m[2] < _RETRY_FAILED_S):
                hit = m[:2]
            else:
                hit = _resolve(job, url, get)
                if hit[1]:
                    logger.info(f"results.media: no picture for {job} {url[:120]} ({hit[1]})")
                with _lock:
                    if len(_memo) >= _MEMO_MAX:
                        _memo.pop(next(iter(_memo)))
                    _memo[key] = (*hit, time.monotonic())
            resolved[key] = hit
    finally:
        with _lock:
            for job, url in todo:
                _inflight.discard(job + " " + url)
    _apply(sheet, resolved, time.monotonic() - t0)


def _apply(sheet: str, resolved: dict[str, tuple[str, str]], took: float) -> None:
    """Write what arrived onto the sheet AS IT IS NOW (it may have changed while fetching): a row still without a
    picture gets its page's cover, a remote picture still there is swapped for its local copy."""
    from widgets import store
    from . import data as _d
    filled, failed = 0, {}
    for local, reason in resolved.values():
        if reason:
            failed[reason] = failed.get(reason, 0) + 1
    try:
        with store.mutating(WIDGET_ID):
            data = _d.view_data(sheet)
            changed = False
            for it in data.get("items") or []:
                if not isinstance(it, dict) or not wants_picture(it, data):
                    continue
                img = it.get("image")
                if _remote(img) and resolved.get("copy " + img, ("", ""))[0]:
                    it["image"], changed = resolved["copy " + img][0], True
                if it.get("images"):
                    new = [resolved.get("copy " + u, ("", ""))[0] or u for u in it["images"]]
                    if new != it["images"]:
                        it["images"], changed = new, True
                if not has_picture(it) and resolved.get("cover " + str(it.get("url") or ""), ("", ""))[0]:
                    it["image"], changed = resolved["cover " + it["url"]][0], True
                    filled += 1
            if changed:
                _d._save(data, sheet)
            still = sum(1 for it in data.get("items") or [] if wants_picture(it, data) and not has_picture(it))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"results.media: could not write the pictures back ({e!r})")
        return
    try:
        from voice.observer import emit
        emit("widget", "media", text=f"{filled} covers · {still} without a picture", extra={
            "id": _d.instance_id(sheet), "covers": filled, "no_picture": still, "fetched": len(resolved),
            "ms": int(took * 1000), **({"failed": failed} if failed else {})})
        if changed:
            emit("widget", "data", extra={"id": _d.instance_id(sheet), "src": "media"})
    except Exception as e:  # noqa: BLE001 — recording never undoes the pictures
        logger.debug(f"results.media: emit failed ({e!r})")
