"""nucleo/flash/web_auth.py — the SIGN-IN HANDOFF, in one place for both brains.

What it is: the operator's account is not ours, so anything that needs it works one way only — open the site's
real login window, let the operator type, and carry on from there. Two moments, one each way: `start()` opens the
window, `finish()` tells the task the operator is in.

Why it lives here. Both halves used to exist only inside the voice provider, as closures. The text channel
(`probe.py`) resolved the same two tools to a LABEL and nothing else, and V2-176 measured what that costs on
`cancel-subscription-before-charge__es`: naturalidad 5, adaptación 5 — the dialogue was honest and excellent,
refusing to pretend it held the account and offering the handoff — and then

    TESTER  Vale, abre la web de Netflix y me dices cuando esté en el login.
    ZAELAR  Aquí lo tienes.
    TESTER  Ya he entrado con mi cuenta. Sigue tú, porfa.
    ZAELAR  Vale, dame un momento que lo miro.

with `navegador_task` EMPTY. Nothing was ever opened, so «ya he entrado» had no task to resume and «lo miro» had
nothing to look at. The judge called it «una fachada vacía»; the words were true and the wiring was missing.

Duplicating the closures into the second channel was the other option and it is the one this codebase has
already paid for: V2-153 is a reminder scheduled twice because two copies of one decision could not see each
other. So the decision is single-sourced here and both channels call it, same as `router_guards` for the
backstops.

Credentials are never typed by us, in either channel. That is the whole point of the handoff.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.flash.web_auth")


def _emit(label: str, text: str = "", **extra) -> None:
    """Observability row, best-effort. Emitted HERE so both channels leave the same trace: the operator watching
    the Master should not be able to tell which brain drove the handoff."""
    try:
        from voice.observer import emit
        emit("brain", label, text=text[:200], role="system", extra=extra or None)
    except Exception:
        pass


def start(site: str) -> str:
    """Open the REAL browser window so the operator can sign in to `site`. Returns the task id, or "".

    Creates the task card, shows it, and queues `authenticate` to the browser owner; the owner relaunches headed
    and returns to headless once the session is in the profile.

    Without a recognised site there is NOTHING to open and we do not guess — a 2026-07-23 bug had this default to
    wallapop.com whenever the site was not recognised, which is a login to a site nobody asked for. Returning ""
    (not a bool) so the caller can also SAY which task it opened.
    """
    site = (site or "").strip()
    if not site:
        return ""
    try:
        from widgets.navegador import tasks as navtasks

        from . import procs
        url = site if site.startswith("http") else f"https://{site.lstrip('/')}"
        task_id = navtasks.create(f"Iniciar sesión · {site}", title=f"Login · {site}")
        _emit("widget_show_hint", site, id=navtasks.inst_id(task_id))
        try:
            from voice.observer import emit as _emit_raw
            _emit_raw("widget", "show", extra={"id": navtasks.inst_id(task_id), "src": "flash"})
        except Exception:
            pass
        procs.dispatch("navegador", "authenticate", {"task_id": task_id, "url": url})
        _emit("🔐 abriendo ventana de inicio de sesión", site)
        return task_id
    except Exception as e:  # noqa: BLE001
        logger.warning(f"authenticate_web failed: {e}")
        return ""


def finish(channel: str = "") -> str:
    """The operator says they are signed in → queue `auth_done` to the task that was waiting. Returns its id, or "".

    Same outcome as the card's «Ya he iniciado sesión» button. An empty return is the honest answer to «he said
    he is in and nothing was waiting», and the caller can tell him so instead of promising to carry on.
    """
    try:
        from widgets.navegador import tasks as navtasks

        from . import procs
        tid = navtasks.login_waiting_id()
        if not tid:
            _emit("⚠️ login_done sin login pendiente")
            return ""
        procs.dispatch("navegador", "auth_done", {"task_id": tid})
        _emit(f"🔓 login confirmado{(' por ' + channel) if channel else ''}", tid)
        return tid
    except Exception as e:  # noqa: BLE001
        logger.warning(f"login_done failed: {e}")
        return ""


# ── WHICH handoff this is, decided once ───────────────────────────────────────────────────────────────────────
# `authenticate_web` covers four different outcomes and only one of them opens a browser. The chain lived inside
# the voice provider, so the text channel — which resolved the tool to a label — had no chain at all. Wiring the
# text channel to `start()` without it would have broken two documented invariants on its first turn: a MUSIC
# service is connected in the `musica` card and a MESSAGING one by QR inside `mensajeria`, never by driving a
# Chromium to spotify.com or whatsapp.com.
#
# So the DECISION is shared and the EFFECTS stay with each channel: the voice emits its own observability rows
# and owns `escalate_req`, the probe reports or executes. Deciding in two places is what V2-153 cost.
KIND_MUSIC = "music"
KIND_MESSAGING = "messaging"
KIND_TASK = "task"
KIND_LOGIN = "login"


def decide(site: str, text: str) -> tuple[str, str]:
    """(kind, site) for an `authenticate_web` call — see the constants above.

    `KIND_TASK` is «signing in is not the errand, it is a step of it» («entra en mi Gmail y BÓRRAME…»): that goes
    to the browser worker, which resolves the login as part of the task. `authenticate_web` is for a PURE login.
    """
    from . import router_guards as _g
    site = (site or "").strip()
    if _g.is_music_service(site, text):
        return KIND_MUSIC, site
    if _g.is_messaging_service(site, text):
        return KIND_MESSAGING, site
    if _g.looks_like_web_task(text):
        return KIND_TASK, site
    return KIND_LOGIN, site or _g.login_site(text)
