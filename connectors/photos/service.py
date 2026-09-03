#
# service.py — the provider-agnostic facade over the photo connectors (V2-564). Everything above this line
# (the `fotos` widget, the registry, the control plane) speaks ONE vocabulary; everything below it
# (`google_photos.py`) speaks its provider's. A second provider is a client module plus an entry in
# `providers.py` and NOTHING here — same seam as `connectors/files/service.py`.
#
# ── EVERY FUNCTION IS FAIL-SAFE ────────────────────────────────────────────────────────────────────────────
# {"ok": False, "error": "..."} , never an exception upward — a widget open on this card must never take a
# voice turn down with it because Google's picker API hiccuped.
#
# ── WHAT MAKES THIS DIFFERENT FROM `connectors/files/service.py` ──────────────────────────────────────────
# Drive can be re-listed on demand; Google Photos cannot (see `providers.py`). So THIS facade is not a thin
# pass-through — it owns the import pipeline (picker session → download thumbnails while the signed URL is
# still valid → persist into `store.py`) and answers browse/search from the LOCAL index, never from a live
# Google call. `list_page`/`search` therefore never touch the network at all.
#
from __future__ import annotations

import logging
import re
import time

from connectors.photos import google_photos as _gp
from connectors.photos import oauth as _oauth
from connectors.photos import providers as _pv
from connectors.photos import store as _store

logger = logging.getLogger("zaelar.photos.service")

PROVIDER_ID = "google-photos"
# A thumbnail this size is plenty for a grid tile and small enough that a few thousand of them do not become a
# storage problem on their own — the operator's own worry about "a thousand photos on screen" applies just as
# much to disk as to the DOM.
THUMB_SIZE = 480
PAGE_SIZE = 120


def providers_public() -> list[dict]:
    return _pv.public_list()


def status() -> dict:
    st = _oauth.status()
    row = st[0] if st else {}
    return {
        "ok": True,
        "provider": PROVIDER_ID,
        "app_configured": bool(row.get("app_configured")),
        "connected": bool(row.get("connected")),
        "session_pending": bool(_store.pending_session()),
        "item_count": _store.item_count(),
    }


# ── the picker round trip ─────────────────────────────────────────────────────────────────────────────────
def start_session() -> dict:
    """Create a fresh Google Photos picker session and remember it as PENDING. Returns {ok, picker_uri}."""
    if not _oauth.configured(PROVIDER_ID):
        return {"ok": False, "error": "sin app OAuth registrada para Google Photos. Entra en Configuración → "
                                      "Conectores y pega ahí su client_id (una sola vez).", "needs_app": True}
    token = _oauth.access_token(PROVIDER_ID)
    if not token:
        return {"ok": False, "error": "Google Photos no está conectado todavía", "needs_connect": True}
    try:
        sess = _gp.create_session(token)
    except Exception as e:
        return {"ok": False, "error": f"no pude abrir el selector de Google Photos: {e}"}
    _store.set_pending_session({**sess, "created_at": int(time.time())})
    return {"ok": True, "picker_uri": sess["picker_uri"], "poll_interval_s": sess.get("poll_interval_s") or 5}


def poll_session() -> dict:
    """Check the pending session (if any). {ok, ready, imported, pending} — imports automatically the moment
    Google reports `mediaItemsSet`, then clears the pending flag so nothing polls forever."""
    pend = _store.pending_session()
    if not pend:
        return {"ok": True, "pending": False, "ready": False, "imported": 0}
    token = _oauth.access_token(PROVIDER_ID)
    if not token:
        _store.set_pending_session(None)
        return {"ok": False, "error": "se perdió la conexión con Google Photos mientras esperaba"}
    try:
        sess = _gp.get_session(token, pend["id"])
    except Exception as e:
        # A session that no longer resolves (expired, revoked) is not a system error worth surfacing loudly —
        # it just means the operator has to reopen the picker.
        logger.info(f"photos session poll failed, dropping pending: {e}")
        _store.set_pending_session(None)
        return {"ok": True, "pending": False, "ready": False, "imported": 0,
                "reason": "la sesión del selector caducó, vuelve a intentarlo"}
    if not sess.get("media_items_set"):
        return {"ok": True, "pending": True, "ready": False, "imported": 0}
    imported = _import_session(token, pend["id"])
    _gp.delete_session(token, pend["id"])
    _store.set_pending_session(None)
    return {"ok": True, "pending": False, "ready": True, "imported": imported}


def _import_session(token: str, session_id: str) -> int:
    """Pull every media item of a finished session, download a THUMBNAIL for each while its `baseUrl` is
    still valid, and persist the batch. Returns how many NEW items landed (re-running is safe — `store.py`
    upserts by id)."""
    raw_items: list[dict] = []
    page_token = ""
    for _ in range(20):                    # hard cap: a picker selection is a human choosing photos, not a library
        res = _gp.list_media_items(token, session_id, page_token)
        raw_items.extend(res.get("items") or [])
        page_token = res.get("next") or ""
        if not page_token:
            break
    normalized = []
    for raw in raw_items:
        entry = _normalize(raw)
        if entry:
            _download_thumb(entry)
            normalized.append(entry)
    if not normalized:
        return 0
    batch_id = _store.add_batch([e["id"] for e in normalized], PROVIDER_ID)
    return _store.upsert_items(normalized, batch_id)


def _normalize(raw: dict) -> dict | None:
    mf = raw.get("mediaFile") or {}
    iid = str(raw.get("id") or "")
    if not iid:
        return None
    meta = mf.get("mediaFileMetadata") or {}
    return {
        "id": iid,
        "filename": str(mf.get("filename") or "(sin nombre)"),
        "taken_at": _iso_date(str(raw.get("createTime") or "")),
        "mime": str(mf.get("mimeType") or ""),
        "width": int(meta.get("width") or 0) or None,
        "height": int(meta.get("height") or 0) or None,
        "provider": PROVIDER_ID,
        "_base_url": str(mf.get("baseUrl") or ""),   # only used to fetch the thumbnail right now; never persisted
    }


def _iso_date(rfc3339: str) -> str:
    """`createTime` → `YYYY-MM-DD`, best-effort. An unparsable/missing value returns "" rather than a guess —
    an undated photo sorts after dated ones instead of lying about when it was taken."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", rfc3339 or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _download_thumb(entry: dict) -> None:
    base = entry.pop("_base_url", "")
    if not base:
        return
    try:
        data = _gp.download_bytes(_gp.thumb_url(base, THUMB_SIZE))
        _store.thumb_path(entry["id"]).write_bytes(data)
        entry["has_thumb"] = True
    except Exception as e:
        logger.info(f"photos thumbnail download failed for {entry.get('id')}: {e}")
        entry["has_thumb"] = False


def disconnect() -> dict:
    _oauth.forget(PROVIDER_ID)
    _store.set_pending_session(None)
    return {"ok": True}


# ── browsing the LOCAL index (no network, ever) ───────────────────────────────────────────────────────────
def years() -> list[dict]:
    return _store.years_summary()


def list_page(offset: int = 0, size: int = PAGE_SIZE) -> dict:
    res = _store.page(offset, size)
    return {"ok": True, **res, "items": [_public_item(it) for it in res["items"]]}


def label_last_batch(label: str) -> dict:
    bid = _store.last_batch_id()
    if not bid:
        return {"ok": False, "error": "todavía no has importado ninguna foto que etiquetar"}
    _store.label_batch(bid, label)
    return {"ok": True, "batch_id": bid, "label": label}


def search(query: str) -> dict:
    """Date-range + label/filename matching over the LOCAL index — never the model, never Google (see the
    module docstring for why full content search is not on the table this pass)."""
    date_from, date_to, residue = _parse_date_hint(query)
    matches = _store.filter_items(date_from, date_to, residue)
    return {"ok": True, "count": len(matches), "date_from": date_from, "date_to": date_to,
            "label": residue, "items": [_public_item(it) for it in matches[:60]]}


def _public_item(it: dict) -> dict:
    iid = str(it.get("id") or "")
    has_thumb = bool(it.get("has_thumb")) or _store.thumb_path(iid).exists()
    return {"id": iid, "filename": it.get("filename") or "", "taken_at": it.get("taken_at") or "",
            "provider": it.get("provider") or "", "thumb": f"/api/photos/thumb/{iid}" if has_thumb else ""}


# ── a small, PAST-oriented date-range parser ──────────────────────────────────────────────────────────────
# `nucleo/scheduler.py::parse_when` looks similar but is strictly FUTURE-facing (reminders: "tomorrow", "next
# Thursday") and returns a single point in time, not a range — the wrong shape for "last year's trip" or "in
# June". This is intentionally small: year + last/this year + a month name (± year) + "N years ago". Anything
# else falls through as a plain label search, which is the honest v1 scope agreed with the operator.
_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
_RE_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_RE_YEARS_AGO = re.compile(r"\bhace\s+(\d{1,2})\s+a[ñn]os?\b|\b(\d{1,2})\s+years?\s+ago\b", re.I)
_RE_LAST_YEAR = re.compile(r"\b(el\s+)?a[ñn]o\s+pasado\b|\blast\s+year\b", re.I)
_RE_THIS_YEAR = re.compile(r"\beste\s+a[ñn]o\b|\bthis\s+year\b", re.I)


def _strip(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


def _parse_date_hint(text: str, now: float | None = None) -> tuple[str, str, str]:
    """(date_from, date_to, residual_label_text) — bounds are "" when nothing date-shaped was found, and the
    WHOLE input becomes the label search in that case.

    The date phrase is matched against `n`, an accent-stripped/lowercased copy of `raw` — but the SPANS are
    used to blank out characters in `raw` itself, never a string substitution of the matched (accent-free)
    text. `raw.replace(consumed, "")` would silently fail to remove "el año pasado" because the match found
    on `n` reads "el ano pasado" (no ñ) — accent-folding a Spanish phrase and then re-searching for it in the
    ORIGINAL, accented text finds nothing, and the date phrase leaks into the label search untouched. Index
    alignment holds because NFKD-decomposing then dropping combining marks turns one accented codepoint into
    exactly one plain one (e.g. "ñ" -> "n"), so `n` and `raw` are always the same length."""
    now = now if now is not None else time.time()
    year_now = int(time.strftime("%Y", time.localtime(now)))
    raw = text or ""
    n = _strip(raw)
    spans: list[tuple[int, int]] = []

    m = _RE_YEARS_AGO.search(n)
    if m:
        spans.append(m.span())
        y = year_now - int(m.group(1) or m.group(2))
        return f"{y}-01-01", f"{y}-12-31", _residue(raw, spans)

    m = _RE_LAST_YEAR.search(n)
    if m:
        spans.append(m.span())
        y = year_now - 1
        return f"{y}-01-01", f"{y}-12-31", _residue(raw, spans)

    m = _RE_THIS_YEAR.search(n)
    if m:
        spans.append(m.span())
        return f"{year_now}-01-01", f"{year_now}-12-31", _residue(raw, spans)

    ym = _RE_YEAR.search(n)
    for name, num in _MONTHS.items():
        mm = re.search(rf"\b{name}\b", n)
        if mm:
            spans.append(mm.span())
            if ym:
                spans.append(ym.span())
            year = int(ym.group(0)) if ym else (year_now if num <= int(time.strftime("%m", time.localtime(now)))
                                                 else year_now - 1)
            last_day = 31 if num in (1, 3, 5, 7, 8, 10, 12) else (30 if num != 2 else 29)
            return f"{year:04d}-{num:02d}-01", f"{year:04d}-{num:02d}-{last_day:02d}", _residue(raw, spans)

    if ym:
        spans.append(ym.span())
        y = ym.group(0)
        return f"{y}-01-01", f"{y}-12-31", _residue(raw, spans)

    return "", "", raw.strip()


def _residue(raw: str, spans: list[tuple[int, int]]) -> str:
    """The label text with the recognized date-phrase SPANS blanked out, so "fotos de Marruecos el año
    pasado" searches the label for "Marruecos" instead of failing to match a batch literally called that plus
    a leftover date phrase."""
    chars = list(raw)
    for s, e in spans:
        for i in range(s, min(e, len(chars))):
            chars[i] = " "
    out = re.sub(r"\s+", " ", "".join(chars)).strip()
    for stop in ("fotos de", "fotos del", "photos of", "photos from", "de", "del", "of", "from", "en", "in"):
        m = re.match(rf"^{re.escape(stop)}\b\s*", out, flags=re.I)
        if m:
            out = out[m.end():]
            break
    return out.strip()
