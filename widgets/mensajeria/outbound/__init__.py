"""widgets/mensajeria/outbound/ — writing to a PERSON who has not written to us (V2-683), besides answering one.

Resolve WHO and by WHICH channel (answered by `widgets/directory.py`), refuse when either is in doubt, and hand the
order to the SAME queue → bus → connector seam a reply travels; each connector keeps its own tested send.

The refusals are the feature: a reply can only say the wrong thing to the right person, this door can say the right
thing to the WRONG person — so an ambiguous name, a channel we cannot honour and an empty text stop here, naming what
is missing. `resolve_target` never guesses and never picks the first row. A bare email ADDRESS is accepted (it is a
complete capability), only for email; he hears it in the confirmation like every other send.
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
