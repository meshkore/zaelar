"""widgets/lifecycle.py: widget lifecycle plus memory integration (V2-017).

A widget is born (CREATE), changes (MODIFY), and dies (DELETE). Each transition must leave a trace in central
memory (`memory/`), not so the widget "exists" in memory (the live catalog is the source of truth for what is on
the canvas), but so zaelar has human memory of what it did: if tomorrow the operator asks where an old widget went,
zaelar can answer that it was deleted on a specific date.

Rules (see `zaelar-memory.md` actions <-> memory section):
  - **History is never deleted.** Deleting a widget removes its CODE and DATA from disk, but writes a memory event
    saying it was deleted on the date at the operator's request. The creation memory is preserved; having both
    created-at and deleted-at is the history. The retriever serves them; the live catalog no longer lists it, so
    zaelar does not hallucinate that it is still present.
  - **Widgets write memory through the facade** (`memory.write`, loop-agnostic async queue); durable widgets are
    sanctioned memory writers (see CLAUDE.md).

DELETE is deterministic (rm folder + `store.delete` + invalidate catalog + close the card). It does NOT need the
headless code agent, which is only for CREATE/MODIFY because those write code. Therefore FlashBrain can trigger it
instantly after confirmation (see `widgets/confirm.py`) in the loop resolving confirmation, either the voice
job-thread or the server loop: `delete_widget` is a coroutine that runs disk I/O in a thread.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time

from loguru import logger

from . import hidden, runtime, store

from widgets import paths

HERE = paths.BUILTIN_ROOT


def _emit_widget(action: str, wid: str, src: str = "system") -> None:
    """Canvas event (observer -> SSE /events): the frontend closes/updates the card. Best-effort.
    V2-039: `src` = who ordered deletion (flash / user / worker / system)."""
    try:
        from voice.observer import emit
        emit("widget", action, extra={"id": wid, "src": src})
    except Exception:
        pass


def _mem_write(text: str, importance: float) -> None:
    """Write a lifecycle event to central memory. `memory.write` enqueues loop-agnostically
    (call_soon_threadsafe), so it is safe from the voice job-thread or the server loop."""
    try:
        from memory import api as memory
        memory.write(text, kind="event", level="mid", importance=importance)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"widget lifecycle: memory write skipped: {e}")


def record_created(widget_id: str, spec: str = "") -> None:
    """Register a newly created widget in memory as a recallable event with id, purpose, and date. Called by the
    SlowBrain code agent after generation. Best-effort."""
    wid = (widget_id or "").strip().lower()
    if not wid:
        return
    meta = runtime.get(wid) or {}
    title = meta.get("title") or wid
    what = (meta.get("whenToUse") or "").strip() or (spec or "").strip()[:100]
    when = time.strftime("%Y-%m-%d")
    tail = f" for: {what}." if what else "."
    _mem_write(f"[widget:{wid}] Widget '{title}' was CREATED on {when}{tail}", importance=0.5)


async def delete_widget(widget_id: str, src: str = "system") -> dict:
    """Delete a widget forever: remove its folder (`widgets/<id>/`) and private store (`_data/<id>/`), invalidate
    the catalog, close its card on the canvas, and write the tombstone to memory with history preserved.
    Deterministic, no headless agent. Runs disk I/O in a thread. Never raises.
    V2-039: `src` = who ordered deletion for canvas audit."""
    wid = (widget_id or "").strip().lower()
    if not wid:
        return {"ok": False, "error": "id vacío"}
    meta = runtime.get(wid) or {}
    folder = paths.dir_for(wid) or os.path.join(paths.generated_root(), wid)
    if not meta and not os.path.isdir(folder):
        return {"ok": False, "error": "widget no encontrado"}
    title = meta.get("title") or wid
    what = (meta.get("whenToUse") or "").strip()

    def _rm() -> None:
        # V2-515: ENGINE SOURCE is never removed from disk (measured 2026-08-30: a lab's delete took
        # `widgets/clock` and `widgets/musica` out of the tree). A deletable folder — a generated widget,
        # a fork — is removed as before; a shipped one survives on disk and gets HIDDEN below instead.
        if os.path.isdir(folder) and not paths.is_repo_source(folder):
            try:
                shutil.rmtree(folder)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"widget lifecycle: rmtree {folder} failed: {e}")
        # Whatever still resolves for this id after the rmtree is repo source (the shipped widget itself,
        # or the shipped counterpart a deleted fork was shadowing) → hide it. "Delete" must mean GONE from
        # the catalog, never "back to stock" — coming back is `restore_widget`'s job, on explicit request.
        left = paths.dir_for(wid)
        if left and paths.is_repo_source(left):
            hidden.hide(wid)
        try:
            store.delete(wid)          # its private store dies with it (state.json + media)
        except Exception:
            pass

    await asyncio.to_thread(_rm)
    paths.forget_modules(wid)          # a live process must not keep answering from the deleted code
    runtime.invalidate()               # catalog/identify stop knowing it immediately; the brain will not show it
    _emit_widget("delete", wid, src)   # close the open card on the canvas, with provenance

    # Memory tombstone: do NOT delete history. Recallable event saying the operator ordered deletion on this date.
    when = time.strftime("%Y-%m-%d")
    desc = f" ({what})" if what else ""
    _mem_write(
        f"[widget:{wid}] Widget '{title}'{desc} was DELETED on {when} at the operator's request. It no longer "
        f"exists on the canvas; if the operator asks about it, remind them they ordered its deletion.",
        importance=0.55,
    )
    logger.info(f"widget lifecycle: DELETED '{wid}' (folder+store+memory tombstone)")
    return {"ok": True, "id": wid, "title": title}


def restorable_ids() -> list[str]:
    """Ids with something to RESTORE (V2-515): a fork shadowing shipped source, or a hidden ("deleted")
    shipped widget. A purely user-created widget has no shipped version underneath — nothing to restore."""
    gen = paths.generated_root()
    try:
        names = set(os.listdir(gen)) if os.path.isdir(gen) else set()
    except OSError:
        names = set()
    out = []
    for wid in sorted(names | set(hidden.ids())):
        if not os.path.isfile(os.path.join(paths.BUILTIN_ROOT, wid, "manifest.json")):
            continue
        if wid in hidden.ids() or os.path.isfile(os.path.join(gen, wid, "manifest.json")):
            out.append(wid)
    return out


def restorable_id(text: str) -> str:
    """Loose match of the operator's words against what is restorable — by id, or by the SHIPPED manifest's
    name/title/aliases. It must not lean on `runtime.identify`: a hidden widget is out of the catalog (that
    is the point of hiding it), so the normal resolver cannot see exactly the widgets this verb exists for."""
    q = runtime._norm(text or "")
    if not q:
        return ""
    for wid in restorable_ids():
        w = runtime._norm(wid)
        if w and (w in q or q == w):
            return wid
        try:
            man = json.load(open(os.path.join(paths.BUILTIN_ROOT, wid, "manifest.json"), encoding="utf-8"))
        except Exception:
            man = {}
        names = [man.get("name") or "", man.get("title") or ""]
        names += [str(a) for a in (man.get("aliases") or man.get("keywords") or [])]
        if any(runtime._norm(n) and runtime._norm(n) in q for n in names):
            return wid
    return ""


async def restore_widget(widget_id: str, src: str = "system") -> dict:
    """Bring a widget back to the (newest) SHIPPED version (V2-515): discard the user's fork if one shadows
    it, unhide the id if it was "deleted". Because the shipped folder was never touched while shadowed —
    engine updates kept landing on it — restore always returns the LATEST system version, not the one the
    fork was cut from. Deterministic, runs disk I/O in a thread, never raises."""
    wid = (widget_id or "").strip().lower()
    if not wid:
        return {"ok": False, "error": "empty id"}
    shipped = os.path.join(paths.BUILTIN_ROOT, wid)
    if not os.path.isfile(os.path.join(shipped, "manifest.json")):
        return {"ok": False, "id": wid, "error": "no shipped version to restore to"}
    fork = os.path.join(paths.generated_root(), wid)
    had_fork = os.path.isdir(fork)

    def _restore() -> None:
        if had_fork and not paths.is_repo_source(fork):
            shutil.rmtree(fork, ignore_errors=True)
        hidden.unhide(wid)

    await asyncio.to_thread(_restore)
    paths.forget_modules(wid)          # a live process must stop answering from the discarded fork
    runtime.invalidate()
    meta = runtime.get(wid) or {}
    title = meta.get("title") or wid
    _emit_widget("restore", wid, src)  # audit trail: what happened is a RESTORE…
    _emit_widget("delete", wid, src)   # …and the open card (stale fork UI + cached code) must close/flush
    when = time.strftime("%Y-%m-%d")
    tail = " The customized fork was discarded at the operator's request." if had_fork else ""
    _mem_write(f"[widget:{wid}] Widget '{title}' was RESTORED to the shipped version on {when}.{tail}",
               importance=0.5)
    logger.info(f"widget lifecycle: RESTORED '{wid}' to shipped (fork discarded: {had_fork})")
    return {"ok": True, "id": wid, "title": title, "discarded_fork": had_fork}
