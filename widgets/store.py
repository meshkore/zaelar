#
# Per-widget isolated store (HANDOFF §3.4 — "memoria complementaria por widget", recommended for isolation and
# scale). CODE (widgets/<id>/) and DATA (widgets/_data/<id>/) are deliberately separate directories: [[modify]]/
# [[delete]]/regeneration rewrite the CODE folder — if data lived there too, an edit would wipe it. Each widget
# gets its OWN data directory (widgets/_data/<id>/), not a shared blob and not a bare file: `state.json` is the
# primary JSON (same load/save contract as before), and `data_dir(id)` hands out the directory itself for
# anything beyond a flat JSON (media/, attachments, whatever an "app-like" widget needs) — still fully isolated
# to that one widget's namespace. NO shared DB, NO coupling to the voice core.
#
import json
import os
import shutil
import threading

from nucleo import workspace as _workspace

HERE = os.path.dirname(os.path.abspath(__file__))
# `<workspace>/widgets/_data` — `<workspace>` is the repo root unless `ZAELAR_WORKSPACE` points at a
# mounted volume (Fase 3, real paid accounts). Unset (self-host, today's behavior) this is BYTE
# IDENTICAL to the old `HERE/_data` (workspace.root() falls back to the engine repo root, and `HERE`
# already lives one level inside it at `widgets/`).
DATA_DIR = os.path.join(str(_workspace.root()), "widgets", "_data")
os.makedirs(DATA_DIR, exist_ok=True)
_lock = threading.Lock()
_last_hash: dict = {}   # widget_id -> hash of last-saved content, so an idempotent re-save neither rewrites nor emits


def _safe_id(widget_id: str) -> str:
    return "".join(c for c in widget_id if c.isalnum() or c in "-_")


def data_dir(widget_id: str) -> str:
    """The widget's OWN data directory (widgets/_data/<id>/) — the sanctioned place for anything beyond
    state.json (media/, files/, a triage-criteria doc, whatever). Created on first use. A widget must never
    write outside its own data_dir() — that boundary is the whole isolation guarantee."""
    d = os.path.join(DATA_DIR, _safe_id(widget_id))
    os.makedirs(d, exist_ok=True)
    return d


def _legacy_path(widget_id: str) -> str:
    return os.path.join(DATA_DIR, f"{_safe_id(widget_id)}.json")


def _path(widget_id: str) -> str:
    p = os.path.join(data_dir(widget_id), "state.json")
    # Lazy migration (same philosophy as the schema `_v` migration below): a widget that still has the OLD flat
    # widgets/_data/<id>.json gets moved into widgets/_data/<id>/state.json the first time it's touched. No
    # migration script, no upfront rewrite, no data loss — the new code just relocates it on first read/write.
    legacy = _legacy_path(widget_id)
    if not os.path.exists(p) and os.path.exists(legacy):
        try:
            with _lock:
                if not os.path.exists(p) and os.path.exists(legacy):
                    shutil.move(legacy, p)
        except Exception:
            pass
    return p


def load(widget_id: str, default: dict | None = None, *, version: int | None = None, migrate=None) -> dict:
    """Load the widget's store. Optional LAZY VERSIONING: pass `version` (the schema this data.py expects) and
    the store tracks it in a reserved `_v` field; when the file carries an older `_v`, `migrate(data, from_v)`
    is called ON READ to upgrade it (return the migrated dict). No migration daemon, no upfront rewrite — a
    widget's schema evolves the first time the new code reads old data. Backward compatible: without `version`
    this behaves exactly as before."""
    p = _path(widget_id)
    data = None
    with _lock:
        if os.path.exists(p):
            try:
                data = json.load(open(p, encoding="utf-8"))
            except Exception:
                pass
    if not isinstance(data, dict):
        data = dict(default or {})
    if version is not None:
        have = int(data.get("_v") or 0)
        if have < version and callable(migrate):
            try:
                data = migrate(data, have) or data
            except Exception:
                data = dict(default or {})              # a broken migration degrades to the seed, never raises
        data["_v"] = version
    return data


def save(widget_id: str, data: dict) -> dict:
    p = _path(widget_id)
    # CHANGE-GATED: a connector's poll loop (e.g. messaging, _POLL=1s) re-saves the SAME content constantly. Writing
    # + emitting on every idempotent save floods the SSE observer (seen: 1495 `widget/data mensajeria` events in one
    # session) → drowns the debug column and the canvas refresh. So serialize once, and if the content is byte-for-byte
    # identical to what we last wrote, do NOTHING (no disk write, no SSE emit). Only a REAL change touches the canvas.
    body = json.dumps(data, ensure_ascii=False, indent=2)
    h = hash(body)
    with _lock:
        if _last_hash.get(widget_id) == h and os.path.exists(p):
            return data                                  # unchanged → skip write + skip emit (kills the poll flood)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, p)   # atomic: readers never see a half-written file
        _last_hash[widget_id] = h
    # THE single choke point for "this widget's data CHANGED" — every mutation path (a widget's own ctx.action,
    # Hermes via [[widget.data]], a connector writing directly, the generator seeding defaults) ends up here, so
    # this is the ONE place that needs to notify the canvas. The open widget (if any) gets pushed one SSE event and
    # re-fetches/re-renders itself exactly once (frontend/app/widgets/desktop.js).
    try:
        from voice.observer import emit
        from widgets.provenance import who
        emit("widget", "data", extra={"id": widget_id, "src": who(widget_id)})   # V2-039: QUIÉN cambió el dato
    except Exception:
        pass
    return data


def exists(widget_id: str) -> bool:
    return os.path.exists(_path(widget_id))


def forget(widget_id: str) -> None:
    """Olvida la huella del último guardado. Hay que llamarla cuando el `state.json` se toca POR FUERA de `save()`
    (hoy: el reset lo borra para dejar la superficie en blanco) — si no, el anti-flood de `save` cree que lo que
    hay en disco es lo último que escribió y se SALTA el siguiente guardado idéntico, dejando el widget vacío en
    pantalla con datos nuevos que nunca llegaron a escribirse."""
    with _lock:
        _last_hash.pop(widget_id, None)


def delete(widget_id: str) -> bool:
    """Remove the widget's ENTIRE data directory (state.json + any media/files it kept there). Called when the
    widget itself is deleted — per-widget storage lives and dies with its widget, so no orphan files pile up
    under _data/. Also sweeps the legacy flat-file path, in case it was never migrated (widget never re-read)."""
    d = os.path.join(DATA_DIR, _safe_id(widget_id))
    legacy = _legacy_path(widget_id)
    had = False
    with _lock:
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                had = True
            except Exception:
                pass
        if os.path.exists(legacy):
            try:
                os.remove(legacy)
                had = True
            except Exception:
                pass
        _last_hash.pop(widget_id, None)
    return had
