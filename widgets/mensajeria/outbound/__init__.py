"""widgets/mensajeria/outbound/ — writing to a PERSON who has not written to us (V2-683).

Every outbound path in this widget until now answered an existing conversation: `reply`, `draft` and
`send_draft` all resolve against a stored item or the open thread, and the queue they feed carries a
`chatId` that only exists because somebody already wrote. So «contacta con Iván Petrenko» had no door at
all — not a missing tool, a missing DIRECTION.

This is that direction, and it is deliberately small: resolve WHO and by WHICH channel (both answered by
`widgets/directory.py`, never here), refuse honestly when either is in doubt, and hand the order to the
SAME queue → bus → connector seam a reply already travels. Nothing new reaches the network: each
connector keeps its own tested send.

## The refusals are the feature

A reply can only go to the conversation it answers, so the worst it can do is say the wrong thing to the
right person. This door can say the right thing to the WRONG person, which is not recoverable — so an
ambiguous name, a channel we cannot honour and an empty text all stop here, naming what is missing so the
next attempt can succeed. `resolve_target` never guesses and never picks the first row.

## Why an address may be given directly

«Manda un correo a reservas@…» is a real errand with no contact behind it, and an address IS a complete
capability (the module note in `directory.py`). It is accepted only when it looks like one and only for
email; the operator hears it in the confirmation before anything is sent, like every other send.
"""
from __future__ import annotations

# Two concerns, re-exported here under their names: `targets` (WHO a send goes to) and `queue` (putting it in the
# store's outbound queue, with the files it carries).
from .targets import (  # noqa: F401
    _EMAIL_RE, PLATFORMS, _LABEL, label, _directory, resolve_reply_target, _resolve_recipient, _near_recipient,
    _one_mailbox, resolve_target, describe, _message_ref)
from .queue import (  # noqa: F401
    enqueue_reply, new_ref, _MAILBOX_FILES, _MAILBOX_MAX_ASKS, _mailbox_files, _mail_identities, attachments_of,
    forward_without_files, enqueue, SAME_FILES_S, _send_key, _file_key, same_files_just_sent)
