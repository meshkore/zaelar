#
# views/ — the READ side of the messaging widget (V2-624): resolving a spoken chat name, the conversation
# view a thread renders from, the per-platform ACTIVITY criteria, `peek` (a conversation handed whole to the
# brain) and the autoresponder previews. Extracted from data.py when it crossed the architecture ratchet's
# unlisted-file cap — the ratchet is paid by EXTRACTING along a real seam, never by raising a ceiling.
#
# The seam is one-directional on purpose: data.py imports THIS module at the top; anything here that needs
# data.py's store or inbox helpers imports it LAZILY inside the function. Same widget-package contract as
# data.py itself: stdlib plus the `widgets` package — `connectors` only LAZILY and only because this
# widget sits in validator's curated _STDLIB_EXEMPT (V2-611: the email signature; V2-628: the archive).
#
# The read side lives by concern — `thread` (one conversation: name lookup, the thread view, peek), `chats` (the
# lists, criteria, policy and autoresponder previews), `archive` (the permanent archive and the mailbox behind it)
# — and every name is re-exported here, so `widgets.mensajeria.views.<name>` resolves and a patch on it governs.
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
