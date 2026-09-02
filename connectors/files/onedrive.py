#
# onedrive.py — OneDrive client over Microsoft Graph v1.0 (V2-557). Same contract as `gdrive.py`: speaks HTTP,
# returns the NORMALIZED entry shape from `service.py`, knows nothing above itself.
#
# Where Graph differs from Drive, and each difference is a bug if assumed away:
#   · A folder is marked by the PRESENCE of a `folder` facet, not by a mime type. An item with neither `folder`
#     nor `file` is a facet we do not model (a package, a bundle) — treated as a file so it is at least listed.
#   · The root is addressed by the path `/me/drive/root`, and children of anything else by ITEM ID. They are
#     two different URLs, which is why `_children_path` exists instead of formatting one template.
#   · Graph returns `@odata.nextLink` as a WHOLE URL, not a token, so paging follows the link verbatim rather
#     than rebuilding a query it did not author.
#
from __future__ import annotations

import logging
import urllib.parse

logger = logging.getLogger("zaelar.files.onedrive")

ROOT_ID = "root"
_SELECT = "id,name,size,lastModifiedDateTime,webUrl,folder,file,parentReference"


def _entry(it: dict) -> dict:
    is_folder = isinstance(it.get("folder"), dict)
    size = it.get("size")
    return {
        "id": str(it.get("id") or ""),
        "name": str(it.get("name") or "(sin nombre)"),
        "kind": "folder" if is_folder else "file",
        "mime": str(((it.get("file") or {}) if isinstance(it.get("file"), dict) else {})
                    .get("mimeType") or ("inode/directory" if is_folder else "")),
        "size": int(size) if isinstance(size, int) and not is_folder else None,
        "modified": str(it.get("lastModifiedDateTime") or ""),
        "web_url": str(it.get("webUrl") or ""),
        "provider": "onedrive",
    }


def _get(token: str, url: str, params: dict | None, api_base: str) -> dict:
    import httpx
    full = url if url.startswith("http") else f"{api_base}{url}"
    r = httpx.get(full, params=params or None,
                  headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"graph {r.status_code}: {r.text[:200]}")
    return r.json()


def _children_path(folder_id: str) -> str:
    fid = (folder_id or ROOT_ID).strip() or ROOT_ID
    if fid == ROOT_ID:
        return "/me/drive/root/children"
    return f"/me/drive/items/{urllib.parse.quote(fid)}/children"


def list_folder(token: str, api_base: str, folder_id: str = "", page: str = "",
                limit: int = 200) -> dict:
    """{entries, next}. `next` is a full Graph URL when there is more; `page` accepts it back verbatim."""
    if page:
        data = _get(token, page, None, api_base)
    else:
        data = _get(token, _children_path(folder_id),
                    {"$select": _SELECT, "$top": max(1, min(int(limit or 200), 999)),
                     "$orderby": "folder,name"}, api_base)
    return {"entries": [_entry(i) for i in (data.get("value") or [])],
            "next": str(data.get("@odata.nextLink") or "")}


def search(token: str, api_base: str, query: str, limit: int = 100) -> dict:
    """Graph's own search over the whole drive. The term goes inside `search(q='…')`, so a single quote in it
    would break the OData function call the same way it breaks Drive's query language."""
    q = str(query or "").replace("'", "''")
    if not q.strip():
        return {"entries": [], "next": ""}
    path = f"/me/drive/root/search(q='{urllib.parse.quote(q)}')"
    data = _get(token, path, {"$select": _SELECT, "$top": max(1, min(int(limit or 100), 999))}, api_base)
    return {"entries": [_entry(i) for i in (data.get("value") or [])],
            "next": str(data.get("@odata.nextLink") or "")}


def item(token: str, api_base: str, file_id: str) -> dict:
    fid = (file_id or ROOT_ID).strip() or ROOT_ID
    path = "/me/drive/root" if fid == ROOT_ID else f"/me/drive/items/{urllib.parse.quote(fid)}"
    data = _get(token, path, {"$select": _SELECT}, api_base)
    out = _entry(data)
    parent = (data.get("parentReference") or {}) if isinstance(data.get("parentReference"), dict) else {}
    pid = str(parent.get("id") or "")
    out["parents"] = [pid] if pid else []
    return out


def download_url(api_base: str, file_id: str, mime: str = "") -> str:
    """Graph serves the bytes from `/content` for every item — no export special case, because OneDrive stores
    real files rather than native documents that only exist in the cloud."""
    return f"{api_base}/me/drive/items/{urllib.parse.quote(str(file_id))}/content"
