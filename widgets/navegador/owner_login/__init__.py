"""The browser's LOGIN flow: reaching a site's login, the visible window the operator signs in through, watching
for the session, and resuming the tasks that were waiting for it (V2-778 F1, 2026-10-01).

Moved out of `widgets/navegador/owner.py` (1,713 lines) with no behaviour change. Every module-level name these
functions read — each other included — is read through the owner (`_o.<name>`), so a patch on `owner` still
governs every call, and the owner imports them back under their names. The two pieces of module state the login
flips (`_visible_override`, `_auth_active`) stay the owner's: what was `global` there is `_o.<name>` here.

A package since refactor2710-12: `authenticate` (reaching the login and opening the window) and `watch` (waiting for
the session and resuming). This facade re-exports every name, so `owner` imports them from here as before.
"""
from __future__ import annotations

from widgets.navegador import owner as _o

from widgets.navegador.owner_login.authenticate import (  # noqa: E402,F401 — re-export
    _login_url_for,
    _click_login_affordance,
    _reach_login,
    _cookie_fingerprint,
    _authenticate,
    _block_for_no_window,
    _authenticate_on_daemon,
    _begin_login,
)
from widgets.navegador.owner_login.watch import (  # noqa: E402,F401 — re-export
    _arm_login_watch,
    _is_logged_in,
    _login_watch,
    _auth_done,
    _resume_paused_tasks,
    _LOGIN_STRICT_RE,
    _find_login_affordance,
    _already_authenticated,
    _probe_logged_in,
    _login_site_of,
)
