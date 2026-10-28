#
# views/ — the READ side of the messaging widget (V2-624): resolving a spoken chat name, the conversation
# view a thread renders from, the per-platform ACTIVITY criteria, `peek` (a conversation handed whole to the
# brain) and the autoresponder previews.
#
# One-directional seam: data.py imports THIS at the top; anything here that needs data.py imports it LAZILY.
# stdlib plus the `widgets` package — `connectors` only LAZILY, as this widget is in validator's _STDLIB_EXEMPT.
#
# By concern — `thread` (one conversation), `chats` (lists, criteria, policy, autoresponder previews), `archive`
# (the permanent archive and the mailbox behind it); every name is re-exported here, so a patch on it governs.
#
from .thread import (  # noqa: F401
    _PEEK_MAX_MSGS, _PEEK_MAX_BODY, _PEEK_BUDGET, _norm_txt, _known_chats, _find_chat_by_name, _thread_view,
    _thread_meta, _peek_answer)
from .chats import (  # noqa: F401
    _criteria_for, _activity_chats, _activity_answer, _autoresponder_preview, _autoresponder_view, _group_chats,
    _open_ref, _notify_policy_view)
from .archive import (  # noqa: F401
    _ARCHIVE_MAX_ROWS, _ARCHIVE_MAX_BODY, archive_rows, _named_sender_first, _WORD_RE, _MAILBOX_MAX_TERMS,
    _MAILBOX_MAX_HITS, _MAILBOX_ASKED_TTL, _MAILBOX_ASKED, mailbox_fill, _unknown_terms, read_query_answer,
    _search_archive_answer, _chat_digest_answer)
