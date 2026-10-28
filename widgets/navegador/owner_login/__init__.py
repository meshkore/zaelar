"""The browser's LOGIN flow: reaching a site's login, the visible window the operator signs in through, watching
for the session, and resuming the tasks that were waiting for it (V2-778 F1).

Every module-level name these functions read — each other included — is read through the owner (`_o.<name>`), so a
patch on `owner` governs every call; the owner imports them back under their names. The state the login flips
(`_visible_override`, `_auth_active`) stays the owner's. Modules: `authenticate` (reaching the login, opening the
window) and `watch` (waiting for the session, resuming); this facade re-exports every name.
"""
from __future__ import annotations

from widgets.navegador import owner as _o

from widgets.navegador.owner_login.authenticate import (  # noqa: E402,F401 — re-export
    _login_url_for, _click_login_affordance, _reach_login, _cookie_fingerprint, _authenticate,
    _block_for_no_window, _authenticate_on_daemon, _begin_login)
from widgets.navegador.owner_login.watch import (  # noqa: E402,F401 — re-export
    _arm_login_watch, _is_logged_in, _login_watch, _auth_done, _resume_paused_tasks, _LOGIN_STRICT_RE,
    _find_login_affordance, _already_authenticated, _probe_logged_in, _login_site_of)
