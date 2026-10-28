# The durable ledger of what has ALREADY been taken in (V2-607).
#: How many (platform, messageId) pairs the ledger remembers. Eviction is oldest-first, so the only message that
#: can come back is one older than the last 4000 — by then it is not "the message he just dismissed".
TAKEN_CAP = 4000


def _taken_key(platform, message_id) -> str:
    return f"{platform}:{message_id}"


def taken_ids(db: dict) -> set:
    """Every (platform, messageId) this widget has already taken in, ACROSS RESTARTS (V2-607).

    The de-duplication used to be the in-memory `_seen` set of whoever was announcing, so every engine restart
    started from zero. Measured on the operator's engine 2026-09-07: the same email (uid 219719, «Pago
    rechazado» from Amazon) was announced THREE times in fourteen minutes — once per restart — because the mail
    is still UNREAD on the server, so V2-606's backfill re-delivers it on every connect, correctly, forever.
    An in-memory guard cannot dedupe against a durable source; only a durable ledger can.

    It also restores what the old `_seen` comment CLAIMED to do — «do not resurrect what the operator removed» —
    which it could not, for the same reason: he dismisses a message, the engine restarts, IMAP still calls it
    unread, and it walks straight back into his list."""
    return {str(k) for k in (db.get("taken") or [])}


def new_among(db: dict, platform: str, candidates: list[dict]) -> list[dict]:
    """The candidates this widget has NOT taken in yet — the query behind both the store guard and the notice.

    Single-sourced on purpose: «already have it» decides whether it is STORED and, since V2-607, whether it may
    INTERRUPT. Two copies of that predicate is how a message gets announced but not saved, or saved twice."""
    taken = taken_ids(db)
    have = {(it.get("platform"), it.get("messageId")) for it in db.get("items") or []}
    out = []
    for m in candidates:
        mid = m.get("messageId")
        if mid is None:
            continue
        if (platform, mid) in have or _taken_key(platform, mid) in taken:
            continue
        out.append(m)
    return out
