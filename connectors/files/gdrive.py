#
# gdrive.py — Google Drive v3 client (V2-557). Speaks HTTP to Drive and returns the NORMALIZED entry shape
# defined in `service.py`; it knows nothing about widgets, prompts or the brain.
#
# Two Drive facts that shape every function here and are easy to get wrong:
#   · A FOLDER is just a file whose mimeType is `application/vnd.google-apps.folder`. There is no separate
#     endpoint and no `isFolder` flag — the mime IS the type, which is why `_entry` checks it first.
#   · A Google-native document (Docs, Sheets, Slides) has NO `size` and cannot be downloaded as-is; it has to
#     be EXPORTED to a concrete format. Reporting a missing size as `0` would render as «0 B» next to every
#     document the operator owns, so it stays None and the widget prints nothing.
#
from __future__ import annotations

import logging
import urllib.parse

logger = logging.getLogger("zaelar.files.gdrive")

FOLDER_MIME = "application/vnd.google-apps.folder"
ROOT_ID = "root"
_FIELDS = "nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink,parents,shortcutDetails)"
# Native Google documents export instead of downloading. Only the three that actually appear in a personal
# Drive; anything else falls through to a plain download.
_EXPORT_AS = {
    "application/vnd.google-apps.document": "application/pdf",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "application/pdf",
}


def _escape(term: str) -> str:
    """Drive's query language is single-quoted, so a quote or a backslash in the operator's words would end the
    string early and turn the rest of their sentence into syntax. Escaping is not cosmetic here: without it
    «Pepe's contract» is a 400 the operator reads as «search is broken»."""
    return str(term or "").replace("\\", "\\\\").replace("'", "\\'")


def _entry(f: dict) -> dict:
    mime = str(f.get("mimeType") or "")
    is_folder = mime == FOLDER_MIME
    size = f.get("size")
    return {
        "id": str(f.get("id") or ""),
        "name": str(f.get("name") or "(sin nombre)"),
        "kind": "folder" if is_folder else "file",
        "mime": mime,
        "size": int(size) if str(size or "").isdigit() else None,
        "modified": str(f.get("modifiedTime") or ""),
        "web_url": str(f.get("webViewLink") or ""),
        "provider": "gdrive",
    }


def _get(token: str, path: str, params: dict, api_base: str) -> dict:
    import httpx
    r = httpx.get(f"{api_base}{path}", params=params,
                  headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"drive {r.status_code}: {r.text[:200]}")
    return r.json()


def list_folder(token: str, api_base: str, folder_id: str = "", page: str = "",
                limit: int = 200) -> dict:
    """{entries, next} for one folder. `orderBy=folder,name` puts directories first, which is what every file
    manager does and what makes a long list scannable."""
    fid = (folder_id or ROOT_ID).strip() or ROOT_ID
    params = {
        "q": f"'{_escape(fid)}' in parents and trashed = false",
        "fields": _FIELDS, "pageSize": max(1, min(int(limit or 200), 1000)),
        "orderBy": "folder,name_natural",
        # Without these two a Shared-drive file is invisible even to a token that may read it.
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
    }
    if page:
        params["pageToken"] = page
    data = _get(token, "/files", params, api_base)
    return {"entries": [_entry(f) for f in (data.get("files") or [])],
            "next": str(data.get("nextPageToken") or "")}


def search(token: str, api_base: str, query: str, limit: int = 100) -> dict:
    """Name match OR full-text. Both, because the operator says «the Axa contract» meaning either the file
    called that or the file that says that inside, and picking one of the two silently loses half the cases."""
    q = _escape(query)
    if not q:
        return {"entries": [], "next": ""}
    params = {
        "q": f"(name contains '{q}' or fullText contains '{q}') and trashed = false",
        "fields": _FIELDS, "pageSize": max(1, min(int(limit or 100), 1000)),
        "orderBy": "folder,name_natural",
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
    }
    data = _get(token, "/files", params, api_base)
    return {"entries": [_entry(f) for f in (data.get("files") or [])],
            "next": str(data.get("nextPageToken") or "")}


def item(token: str, api_base: str, file_id: str) -> dict:
    """One entry plus its `parents`, which is what a breadcrumb is built from."""
    data = _get(token, f"/files/{urllib.parse.quote(str(file_id))}",
                {"fields": "id,name,mimeType,size,modifiedTime,webViewLink,parents",
                 "supportsAllDrives": "true"}, api_base)
    out = _entry(data)
    out["parents"] = [str(p) for p in (data.get("parents") or [])]
    return out


def download_url(api_base: str, file_id: str, mime: str = "") -> str:
    """The URL that yields the BYTES. A native Google doc has to go through `/export`; everything else uses
    `alt=media`. The caller adds the bearer token — this returns no credential."""
    fid = urllib.parse.quote(str(file_id))
    export = _EXPORT_AS.get(str(mime or ""))
    if export:
        return f"{api_base}/files/{fid}/export?mimeType={urllib.parse.quote(export)}"
    return f"{api_base}/files/{fid}?alt=media&supportsAllDrives=true"
