"""What each messaging action does, one function per action; `data.ACTIONS` maps the names to them (V2-778).

Handlers live by concern — `open` (the screen), `send` (writing to somebody), `fetch` (the connector, reads),
`groups` (groups, muting, policy, signature, media) — re-exported here so `actions._a_<verb>` resolves. Every
module-level name of `data` is read through it (`_d.<name>`), so a patch on `data` still governs every call.
"""
from __future__ import annotations

from .open import (  # noqa: F401
    _a_show_view, _a_open, _a_close, _a_load_more, _a_chats_more, _a_readchat)
from .send import (  # noqa: F401
    _a_reply, _NO_TARGET_FOR_THE_MODEL, _no_reply_say, _no_reply_target, _a_draft, _draft_new, _a_cancel_send,
    _a_send_draft, _a_send_to, _a_forward)
from .fetch import (  # noqa: F401
    _a_fetch_now, _a_set_autoresponder, _a_clear_autoresponder, _a_search_archive, _a_peek, _a_unread, _a_archive)
from .groups import (  # noqa: F401
    _GROUP_PLATFORMS, _a_create_group, _a_set_media_days, _a_set_signature, _a_set_signature_line,
    _a_clear_signature, _a_hide, _a_set_notify, _a_unhide)
