"""The owner's lifecycle: a cheap start (Chromium launches on first use), stop, closing the window while keeping
the profile, and whether it runs headless.
Moved out of `owner.py`; the owner's state and every module name are read through the package (`_o.<name>`), so a
patch on `owner` still governs every call.
"""

import os

from widgets.navegador import owner as _o


# ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────────
async def start() -> None:
    """Intentionally cheap: does not launch Chromium (lazy start on first handle). Leaves the state as 'ready'."""
    _o._write(loading=False, error="")
    _o._emit("ready", "navegador listo (Chromium se lanza al primer uso)")
    # RECOVERY after restart: tasks live in RAM and die with the process, but a HALF-FINISHED login leaves a DURABLE
    # breadcrumb in memory → on startup we remind the operator once (we cannot resume it ourselves because the task no
    # longer exists; the operator decides whether to resume). Best-effort: never breaks widget startup.
    try:
        from widgets.navegador import auth_memory
        pend = auth_memory.read_auth_pending()
        if pend and pend.get("sitio"):
            from voice import proactive
            await proactive.notify("navegador", _o._say().login_left_halfway.format(site=pend["sitio"]),
                                   kind="notify")
            auth_memory.clear_auth_pending()          # already notified → do not repeat the reminder on every startup
    except Exception:
        pass


async def stop() -> None:
    for closer in (lambda: _o._context and _o._context.close(),
                   lambda: _o._browser and _o._browser.close(),
                   lambda: _o._pw and _o._pw.stop()):
        try:
            r = closer()
            if r is not None:
                await r
        except Exception:
            pass
    _o._pw = _o._browser = _o._context = _o._page = None
    _o._emit("stopped")


async def _close_browser() -> None:
    """Close the browser WINDOW at the operator's request ("close the browser"), WITHOUT deleting the profile →
    cookies/session are preserved and the next navigation relaunches with the session intact. Leaves the desktop clean."""
    await _o.stop()                                      # close the only window; the profile persists on disk
    _o._write(mode="blank", url="", title="Navegador cerrado", loading=False, error="",
           youtube_id="", youtube_title="")
    _o._emit("closed_window", "ventana cerrada (sesión guardada)")


def _headless() -> bool:
    """HEADLESS by DEFAULT (2026-07-08): runs IN THE BACKGROUND, without a window → it does not steal the operator's
    focus/cursor (they can type on their computer while the bot automates) and it does not need to be watched —
    screenshots are enough. To SEE IT (manual driving / LOGIN), enable visible mode: store `navegador_visible=true`,
    env ZAELAR_NAVEGADOR_VISIBLE=1, or authenticate's runtime override."""
    if _o._visible_override is not None:      # authenticate forces visible for login, then returns to headless
        return not _o._visible_override
    if os.environ.get("ZAELAR_NAVEGADOR_VISIBLE", "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        import json as _json
        from config.settings import SETTINGS_FILE
        if SETTINGS_FILE.is_file():
            if (_json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) or {}).get("navegador_visible"):
                return False
    except Exception:
        pass
    if os.environ.get("ZAELAR_NAVEGADOR_HEADLESS", "").strip().lower() in ("0", "false", "no"):
        return False
    return True   # default: headless (in the background)
