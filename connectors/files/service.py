#
# service.py — the PROVIDER-AGNOSTIC facade over the cloud-file connectors (V2-557). Everything above this line
# (the `archivos` widget, the registry, the control plane) speaks ONE vocabulary; everything below it
# (`gdrive.py`, `onedrive.py`) speaks its provider's. Adding a third provider touches `providers.py` plus one
# client module and NOTHING here — that is the whole point of the seam.
#
# ── THE NORMALIZED ENTRY, which is the contract ────────────────────────────────────────────────────────────
#   {id, name, kind: "folder"|"file", mime, size|None, modified, web_url, provider}
# `size` is None and not 0 for anything that has no size (a folder, a native Google document): «0 B» next to a
# real document is a statement, and it is false.
#
# ── EVERY FUNCTION IS FAIL-SAFE ────────────────────────────────────────────────────────────────────────────
# They return {"ok": False, "error": "<something the operator can act on>"} and never raise. A file browser
# whose provider is down must degrade to a card that says so, never take a voice turn with it.
#
# ── AND THE PART THAT IS NOT AN ERROR ──────────────────────────────────────────────────────────────────────
# A token granted the narrow Google tier (`drive.file`) can list nothing: the API answers 200 with an empty
# array, which is INDISTINGUISHABLE from «this folder is empty» and would read as a broken connector. So a
# non-browsable tier is answered with `ok: True`, zero entries and an explicit `reason` — the widget prints the
# reason instead of an empty folder. Same rule as everywhere in this engine: a refusal that cannot say what it
# is gets diagnosed as the wrong defect.
#
from __future__ import annotations

import logging

from connectors.files import gdrive as _gdrive
from connectors.files import oauth as _oauth
from connectors.files import onedrive as _onedrive
from connectors.files import providers as _pv

logger = logging.getLogger("zaelar.files.service")

_CLIENTS = {"gdrive": _gdrive, "onedrive": _onedrive}
# The widget asks for a page at a time; a folder with thousands of entries is paged, never truncated silently.
PAGE_SIZE = 200


def _client(provider_id: str):
    return _CLIENTS.get((provider_id or "").strip().lower())


def providers_public() -> list[dict]:
    return _pv.public_list()


def status() -> dict:
    """{ok, providers[], connected[], active}. `active` is the provider a caller gets when it names none."""
    provs = _oauth.status()
    connected = [p["id"] for p in provs if p.get("connected")]
    return {"ok": True, "providers": provs, "connected": connected,
            "active": connected[0] if connected else ""}


def active_provider(preferred: str = "") -> str:
    """The provider to work with. An explicit `preferred` wins IF it is connected — a stale preference pointing
    at a disconnected provider must not silently produce «empty drive»; it falls back to a connected one."""
    st = status()
    want = (preferred or "").strip().lower()
    if want and want in st["connected"]:
        return want
    return st["active"]


def _prepared(provider_id: str) -> tuple[object, str, str, str]:
    """(client, token, api_base, error). One place resolves provider → client → token, so every entry point
    reports the same three failures with the same words."""
    p = _pv.get(provider_id)
    if not p:
        return None, "", "", f"proveedor desconocido: {provider_id or '(ninguno)'}"
    cli = _client(p.id)
    if cli is None:
        return None, "", "", f"sin cliente para {p.label}"
    if not _oauth.configured(p.id):
        return None, "", "", f"{p.label} no tiene app OAuth registrada todavía"
    tok = _oauth.access_token(p.id)
    if not tok:
        return None, "", "", f"{p.label} no está conectado (o caducó la sesión): vuelve a conectarlo"
    return cli, tok, p.api_base, ""


def _browsable(provider_id: str) -> tuple[bool, str]:
    p = _pv.get(provider_id)
    if not p:
        return False, ""
    tier = p.tier(_oauth.granted_tier(p.id))
    if tier.browsable:
        return True, ""
    return False, (f"Le diste a zaelar el permiso «{tier.label}», que no puede listar carpetas. "
                   f"Reconéctalo eligiendo el permiso de navegación si quieres explorar tu {p.label}.")


def list_folder(provider: str = "", folder_id: str = "", page: str = "") -> dict:
    """{ok, provider, entries, next, reason}. `reason` is set when the call SUCCEEDED and the result is still
    empty for a knowable cause — the distinction the widget needs to avoid lying about an empty drive."""
    pid = active_provider(provider)
    if not pid:
        return {"ok": False, "error": "no hay ningún servicio de archivos conectado"}
    cli, tok, base, err = _prepared(pid)
    if err:
        return {"ok": False, "provider": pid, "error": err}
    ok_browse, reason = _browsable(pid)
    if not ok_browse:
        return {"ok": True, "provider": pid, "entries": [], "next": "", "reason": reason}
    try:
        res = cli.list_folder(tok, base, folder_id or "", page or "", PAGE_SIZE)
    except Exception as e:
        logger.warning(f"list_folder failed ({pid}): {e}")
        return {"ok": False, "provider": pid, "error": f"no pude leer la carpeta: {e}"[:200]}
    return {"ok": True, "provider": pid, "entries": res.get("entries") or [],
            "next": res.get("next") or "", "reason": ""}


def search(query: str, provider: str = "") -> dict:
    """{ok, provider, entries, query}. An empty query is refused rather than sent — every provider answers a
    blank search with its whole drive, which looks like a listing and is not one."""
    q = " ".join(str(query or "").split())
    if not q:
        return {"ok": False, "error": "dime qué busco"}
    pid = active_provider(provider)
    if not pid:
        return {"ok": False, "error": "no hay ningún servicio de archivos conectado"}
    cli, tok, base, err = _prepared(pid)
    if err:
        return {"ok": False, "provider": pid, "error": err}
    ok_browse, reason = _browsable(pid)
    if not ok_browse:
        return {"ok": True, "provider": pid, "entries": [], "query": q, "reason": reason}
    try:
        res = cli.search(tok, base, q, PAGE_SIZE)
    except Exception as e:
        logger.warning(f"search failed ({pid}): {e}")
        return {"ok": False, "provider": pid, "error": f"la búsqueda falló: {e}"[:200]}
    return {"ok": True, "provider": pid, "entries": res.get("entries") or [], "query": q, "reason": ""}


def item(file_id: str, provider: str = "") -> dict:
    """One entry plus `parents`. Used for the breadcrumb and for opening a file's detail."""
    pid = active_provider(provider)
    cli, tok, base, err = _prepared(pid)
    if err:
        return {"ok": False, "provider": pid, "error": err}
    try:
        return {"ok": True, "provider": pid, "entry": cli.item(tok, base, file_id)}
    except Exception as e:
        return {"ok": False, "provider": pid, "error": f"no pude leer el archivo: {e}"[:200]}


def breadcrumb(folder_id: str, provider: str = "", max_depth: int = 12) -> dict:
    """The chain root → … → this folder, as [{id, name}]. Walks `parents` upward, bounded: a cycle or a very
    deep tree must cost a truncated trail, never a hung voice turn. Best-effort by design — a breadcrumb that
    cannot be built is a cosmetic loss, so it degrades to the folder itself."""
    pid = active_provider(provider)
    fid = (folder_id or "").strip()
    if not fid or fid in ("root", ""):
        return {"ok": True, "provider": pid, "trail": []}
    cli, tok, base, err = _prepared(pid)
    if err:
        return {"ok": False, "provider": pid, "error": err, "trail": []}
    trail: list[dict] = []
    seen: set[str] = set()
    cur = fid
    try:
        for _ in range(max(1, int(max_depth))):
            if not cur or cur in seen or cur == "root":
                break
            seen.add(cur)
            ent = cli.item(tok, base, cur)
            trail.append({"id": ent.get("id") or cur, "name": ent.get("name") or ""})
            parents = ent.get("parents") or []
            cur = str(parents[0]) if parents else ""
    except Exception as e:
        logger.warning(f"breadcrumb partial ({pid}): {e}")
    trail.reverse()
    return {"ok": True, "provider": pid, "trail": trail}


def download(file_id: str, provider: str = "", mime: str = "", max_bytes: int = 8_000_000) -> dict:
    """{ok, content: bytes, mime, name} — the file's BYTES, capped. The cap is not politeness: this is called
    from a voice turn to hand a document to another widget, and an unbounded read of somebody's drive is how a
    single misheard word costs a gigabyte of memory."""
    import httpx
    pid = active_provider(provider)
    cli, tok, base, err = _prepared(pid)
    if err:
        return {"ok": False, "provider": pid, "error": err}
    try:
        meta = cli.item(tok, base, file_id)
        url = cli.download_url(base, file_id, mime or meta.get("mime") or "")
        with httpx.stream("GET", url, headers={"Authorization": f"Bearer {tok}"},
                          timeout=60, follow_redirects=True) as r:
            if r.status_code >= 400:
                return {"ok": False, "provider": pid, "error": f"descarga {r.status_code}"}
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    return {"ok": False, "provider": pid,
                            "error": f"el archivo pasa de {max_bytes // 1_000_000} MB; ábrelo en su web"}
    except Exception as e:
        return {"ok": False, "provider": pid, "error": f"no pude descargarlo: {e}"[:200]}
    return {"ok": True, "provider": pid, "content": bytes(buf),
            "mime": meta.get("mime") or "", "name": meta.get("name") or ""}
