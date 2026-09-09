"""The libtorrent session as a lazy process singleton, plus sequential-download + streaming plumbing.

This is the ONLY file that imports libtorrent, so a machine without the wheel disables the whole feature here
(`available()` is False) instead of anywhere else raising an ImportError. The session is built on FIRST use,
never in the ASGI lifespan — the lifespan runs twice per process (HTTP + HTTPS listeners) and a singleton born
lazily sidesteps that entirely; a stopped-and-restarted engine gets a fresh one.

Streaming reads from DISK once the covering pieces are present, rather than through libtorrent's read_piece
alert queue: a completed piece is checked and flushed to the file by default storage, so a Range handler can
prioritize the pieces it is about to serve (`set_piece_deadline`), wait for `have_piece`, and then read the
byte slice from the file like any other. Sequential download plus a per-file priority keeps the front of the
chosen video arriving first, which is what makes «play while it downloads» work.
"""
from __future__ import annotations

import os
import threading
import time

# What counts as "the file we came for" is decided by `library.formats`, never by a list kept here — this
# module had its own copy in V2-637 and it was WRONG (`.mkv`/`.avi` were listed as playable video; no
# mainstream browser decodes either), which could pick a file the player was structurally unable to show.
# One table, in the module that owns the question.

_lock = threading.RLock()
_session = None            # the one libtorrent.session, or None until first use / when unavailable
_handles: dict = {}        # info_hash (v1 hex) -> {"h": torrent_handle, "file": int, "added": float}
_import_error = ""         # remembered so the facade can say WHY it is off, once


def _lt():
    """Import libtorrent once, remembering failure. Returns the module or None (never raises)."""
    global _import_error
    try:
        import libtorrent as lt
        return lt
    except Exception as e:  # noqa: BLE001 — a missing/broken wheel disables the feature, it does not crash boot
        _import_error = str(e)[:200]
        return None


def available() -> bool:
    return _lt() is not None


def import_error() -> str:
    _lt()
    return _import_error


def _downloads_dir() -> str:
    """The client's SANDBOX — `library/downloads/`, and nothing else, ever (operator's isolation rule).

    It is the agent's own filesystem (V2-638), so a finished file is reachable by every widget instead of
    being trapped in one widget's private store, which is where V2-637 first put it. Filing it onto its shelf
    (video/, audio/, documents/) is OUR move afterwards — this client never needs a path outside its sandbox."""
    from library import paths
    return str(paths.downloads_dir())


def _get_session():
    """The one session, built lazily. `None` when libtorrent is unavailable."""
    global _session
    lt = _lt()
    if lt is None:
        return None
    with _lock:
        if _session is None:
            # DHT + a couple of well-known routers so a magnet with no trackers still resolves metadata; a
            # random high listen port so two engines on one machine (the operator runs several) do not collide.
            _session = lt.session({
                "listen_interfaces": "0.0.0.0:0",
                "enable_dht": True,
                "alert_mask": lt.alert.category_t.error_notification | lt.alert.category_t.status_notification,
            })
        return _session


def _pick_file(ti, want: str = "media", keep: bool = False) -> int:
    """Index of the file we came for: the LARGEST one matching `want` that policy allows, or -1.

    Largest, because a release folder is padded with samples, .nfo and .srt and the feature is always the big
    one. `want` is the SHELF asked for (`video`/`audio`/`document`, or `media` for either of the first two,
    or `any`), which is what lets the same client serve the video widget, the music widget and a document
    fetch. `keep` lifts the browser-playable default — the operator's explicit «I want the file itself» —
    and is the only way an `.mkv` or an `.epub` is ever chosen."""
    from library import formats
    fs = ti.files()
    wanted = {"media": ("video", "audio"), "any": ("video", "audio", "document", "image", "other")}.get(
        want, (want,))
    best, best_size = -1, -1
    for i in range(fs.num_files()):
        name = fs.file_name(i)
        if formats.kind_of(name) not in wanted:
            continue
        if not formats.allowed(name, keep=keep):
            continue
        if fs.file_size(i) > best_size:
            best, best_size = i, fs.file_size(i)
    return best


def _best_rejected(ti, want: str) -> str:
    """The biggest file we DECLINED, so the refusal can name it and offer the way round (V2-638). A bare
    «no reproducible» over a torrent that plainly holds the film reads as a broken client."""
    from library import formats
    fs = ti.files()
    wanted = {"media": ("video", "audio"), "any": ("video", "audio", "document", "image", "other")}.get(
        want, (want,))
    best, best_size = "", -1
    for i in range(fs.num_files()):
        name = fs.file_name(i)
        if formats.kind_of(name) in wanted and fs.file_size(i) > best_size:
            best, best_size = name, fs.file_size(i)
    return best


def _hash_of(h) -> str:
    try:
        return str(h.info_hashes().v1)
    except Exception:  # noqa: BLE001 — older bindings expose info_hash()
        return str(h.info_hash())


def add_magnet(magnet: str, *, want: str = "media", keep: bool = False,
               metadata_timeout_s: float = 30.0) -> dict:
    """Add a magnet, resolve its metadata, and sequentially download ONLY the one file we came for.

    Returns `{"ok": True, "id": <info_hash>}` or `{"ok": False, "error": ...}`. Idempotent on the info hash:
    re-adding a magnet already present returns the existing id instead of a duplicate download."""
    magnet = (magnet or "").strip()
    if not magnet.startswith("magnet:"):
        return {"ok": False, "error": "eso no es un enlace magnet"}
    lt = _lt()
    ses = _get_session()
    if lt is None or ses is None:
        return {"ok": False, "error": "el cliente de torrent no está disponible en esta instalación"}
    try:
        params = lt.parse_magnet_uri(magnet)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"enlace magnet ilegible: {str(e)[:120]}"}
    try:
        info_hash = str(params.info_hashes.v1)
    except Exception:  # noqa: BLE001
        info_hash = str(getattr(params, "info_hash", "")) or ""
    with _lock:
        if info_hash and info_hash in _handles:
            return {"ok": True, "id": info_hash, "reused": True}
    params.save_path = _downloads_dir()
    params.flags |= lt.torrent_flags.sequential_download
    try:
        h = ses.add_torrent(params)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"no pude añadir el torrent: {str(e)[:120]}"}

    deadline = time.monotonic() + max(5.0, float(metadata_timeout_s))
    while time.monotonic() < deadline:
        if h.status().has_metadata:
            break
        time.sleep(0.25)
    if not h.status().has_metadata:
        try:
            ses.remove_torrent(h)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": "no encontré fuentes para este torrent (nadie lo comparte)"}

    ti = h.torrent_file()
    fidx = _pick_file(ti, want, keep)
    if fidx < 0:
        try:
            ses.remove_torrent(h)
        except Exception:  # noqa: BLE001
            pass
        # NAME what was there and refused, with the way round it (V2-638). «No hay nada reproducible» over a
        # torrent that plainly holds the film reads as a broken client; «es un .mkv, dime que lo guarde y te
        # lo bajo» is the same fact with the door left open.
        from library import formats
        rejected = _best_rejected(ti, want)
        if rejected and not keep:
            return {"ok": False, "error": formats.refusal(rejected), "unplayable": rejected}
        return {"ok": False, "error": "este torrent no contiene nada que encaje con lo que buscas"}

    # Download ONLY the chosen file: 0 = skip, 4 = normal. Sequential flag then delivers its pieces front-first.
    prio = [0] * ti.files().num_files()
    prio[fidx] = 4
    try:
        h.prioritize_files(prio)
    except Exception:  # noqa: BLE001
        pass
    rid = _hash_of(h)
    with _lock:
        _handles[rid] = {"h": h, "file": fidx, "added": time.time()}
    return {"ok": True, "id": rid}


def _record(rid: str):
    with _lock:
        return _handles.get(rid)


def status(rid: str) -> dict:
    """A speakable snapshot of one download. `streamable` is the only field the widget waits on to show the
    player: metadata present, the file's first pieces down, and enough of it buffered to start."""
    rec = _record(rid)
    if not rec:
        return {"ok": False, "error": "ese torrent ya no está activo"}
    h, fidx = rec["h"], rec["file"]
    st = h.status()
    ti = h.torrent_file() if st.has_metadata else None
    out = {
        "ok": True, "id": rid,
        "name": st.name or (ti.name() if ti else ""),
        "progress": round(float(st.progress), 4),
        "download_rate": int(st.download_rate),
        "num_peers": int(st.num_peers),
        "downloaded": int(st.total_wanted_done),
        "size": int(st.total_wanted),
        "state": str(st.state),
    }
    out["streamable"] = _is_streamable(h, fidx, ti) if ti else False
    return out


def _file_piece_range(ti, fidx: int, offset: int, length: int):
    """(first_piece, last_piece) covering [offset, offset+length) of file `fidx`, clamped to the file."""
    fs = ti.files()
    fsize = fs.file_size(fidx)
    offset = max(0, min(offset, max(0, fsize - 1)))
    length = max(1, min(length, fsize - offset))
    first = ti.map_file(fidx, offset, 0).piece
    last = ti.map_file(fidx, offset + length - 1, 0).piece
    return first, last


def _is_streamable(h, fidx: int, ti) -> bool:
    """Enough buffered to START: the file's first ~4 MB of pieces are present. Playback then rides the
    sequential download; the Range handler blocks per-chunk if the reader outruns the wire."""
    if ti is None:
        return False
    fs = ti.files()
    if fs.file_size(fidx) <= 0:
        return False
    head = min(4 * 1024 * 1024, fs.file_size(fidx))
    first, last = _file_piece_range(ti, fidx, 0, head)
    return all(h.have_piece(p) for p in range(first, last + 1))


def file_info(rid: str) -> dict:
    """`{ok, size, name, mime}` for the chosen video file, once metadata is in."""
    rec = _record(rid)
    if not rec:
        return {"ok": False, "error": "ese torrent ya no está activo"}
    h, fidx = rec["h"], rec["file"]
    if not h.status().has_metadata:
        return {"ok": False, "error": "todavía sin metadatos"}
    ti = h.torrent_file()
    fs = ti.files()
    name = fs.file_name(fidx)
    ext = os.path.splitext(name)[1].lower()
    mime = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
            ".mkv": "video/x-matroska", ".avi": "video/x-msvideo", ".ogv": "video/ogg"}.get(ext, "video/mp4")
    return {"ok": True, "size": int(fs.file_size(fidx)), "name": name, "mime": mime}


def saved_path(rid: str) -> str:
    """Absolute path of the file being downloaded, inside the sandbox. "" if unknown."""
    rec = _record(rid)
    if not rec:
        return ""
    h, fidx = rec["h"], rec["file"]
    st = h.status()
    if not st.has_metadata:
        return ""
    return os.path.join(st.save_path, h.torrent_file().files().file_path(fidx))


def is_complete(rid: str) -> bool:
    """Has the file we asked for finished? (Only the chosen file is wanted, so `total_wanted` is the ruler.)"""
    rec = _record(rid)
    if not rec:
        return False
    st = rec["h"].status()
    return bool(st.has_metadata and st.total_wanted > 0 and st.total_wanted_done >= st.total_wanted)


def _ensure_pieces(h, ti, fidx: int, offset: int, length: int, *, wait_s: float) -> bool:
    """Hurry and wait for the pieces covering [offset, length). True once all present, False on timeout."""
    first, last = _file_piece_range(ti, fidx, offset, length)
    for p in range(first, last + 1):
        try:
            h.set_piece_deadline(p, 700)   # ms — bring these to the front of the sequential fetch
        except Exception:  # noqa: BLE001
            pass
    deadline = time.monotonic() + max(1.0, wait_s)
    while time.monotonic() < deadline:
        if all(h.have_piece(p) for p in range(first, last + 1)):
            return True
        time.sleep(0.1)
    return all(h.have_piece(p) for p in range(first, last + 1))


def iter_range(rid: str, start: int, length: int, *, chunk: int = 262144, wait_s: float = 45.0):
    """Yield the bytes of file `fidx` over [start, start+length), waiting per-chunk for the wire to catch up.

    The reader (a browser seeking, or playing straight through) drives it: each chunk's covering pieces are
    prioritized and awaited before the slice is read from disk. Raises TimeoutError if a chunk never arrives —
    the HTTP layer turns that into a closed stream, not a hang."""
    rec = _record(rid)
    if not rec:
        raise FileNotFoundError("torrent not active")
    h, fidx = rec["h"], rec["file"]
    if not h.status().has_metadata:
        raise FileNotFoundError("no metadata")
    ti = h.torrent_file()
    fs = ti.files()
    path = os.path.join(h.status().save_path, fs.file_path(fidx))
    remaining = length
    pos = start
    while remaining > 0:
        step = min(chunk, remaining)
        if not _ensure_pieces(h, ti, fidx, pos, step, wait_s=wait_s):
            raise TimeoutError(f"piece for offset {pos} did not arrive")
        with open(path, "rb") as f:
            f.seek(pos)
            data = f.read(step)
        if not data:
            break
        yield data
        pos += len(data)
        remaining -= len(data)


def remove(rid: str, *, delete_files: bool = True) -> dict:
    """Stop a download and (by default) delete its files — a streamed movie is not something we hoard."""
    lt = _lt()
    ses = _get_session()
    with _lock:
        rec = _handles.pop(rid, None)
    if not rec or ses is None:
        return {"ok": True, "removed": False}
    try:
        flags = lt.session.delete_files if (delete_files and lt is not None) else 0
        ses.remove_torrent(rec["h"], flags)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}
    return {"ok": True, "removed": True}


def list_active() -> list:
    with _lock:
        ids = list(_handles.keys())
    return [status(rid) for rid in ids]


def reset_for_tests():
    """Drop all in-memory handles and the session — unit tests never touch a real session."""
    global _session
    with _lock:
        _handles.clear()
        _session = None
