"""How far back a connected resource can SEE — one declared answer per connector family (refactor2710-13 T-02).

A worker's first step compares the spec («mail before 2025-01-01») with what the resource holds; without this door
an impossible spec is retried in silence (V2-825 F6). Each family declares the ONE fact that bounds it:

  · `mail`         — the INTERNALDATE of the oldest message in the INBOX (the mailbox's first readable item).
  · `cloud_files`  — the date of the drive's root (what the provider reports for it).
  · `messaging`    — the oldest message the archive holds for that platform (what a search can find).

`reach()` never raises and never guesses: `known=False` says the family is not declared here, `earliest=None`
with a `detail` says the resource was asked and could not answer. Dates are ISO 8601 in UTC. This module only
declares and routes; the step that reads it against a spec lives with the worker (refactor2710-09).
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Reach:
    family: str
    provider: str = ""
    earliest: str | None = None   # ISO 8601, UTC
    source: str = ""              # what was asked, e.g. "imap:INBOX:INTERNALDATE"
    known: bool = True            # False: no connector family declares its reach under this name
    detail: str = ""              # why `earliest` is None, in a word the worker can repeat

    def as_dict(self) -> dict:
        return asdict(self)


def _mail(provider: str) -> Reach:
    from connectors.email.reach import earliest_readable
    return earliest_readable()


def _cloud_files(provider: str) -> Reach:
    from connectors.files.reach import earliest_readable
    return earliest_readable(provider)


def _messaging(provider: str) -> Reach:
    from connectors.messaging.reach import earliest_readable
    return earliest_readable(provider)


#: family → the function that measures it, named by the function itself (one place says what a family is called).
#: A family missing here is a capability the worker cannot bound.
FAMILIES = {fn.__name__.lstrip("_"): fn for fn in (_mail, _cloud_files, _messaging)}


def _said(r: Reach, t0: float) -> Reach:
    """Every measurement leaves one `spec`/`reach` event (family `worker`, beside the spec it is read against): the
    connector family, the value, why it is missing, and how long the resource took to answer."""
    try:
        from voice.observer import emit
        emit("spec", "reach", extra={**r.as_dict(), "ms": round((time.monotonic() - t0) * 1000)})
    except Exception as e:  # noqa: BLE001 — the timeline is a witness; the answer goes back to the worker anyway
        logging.getLogger("zaelar.connectors.reach").debug(f"reach event not emitted: {e!r}")
    return r


def reach(family: str, provider: str = "") -> Reach:
    fam = (family or "").strip().lower()
    t0 = time.monotonic()
    fn = FAMILIES.get(fam)
    if fn is None:
        return _said(Reach(family=fam, provider=provider, known=False, detail="family_not_declared"), t0)
    try:
        return _said(fn(provider), t0)
    except Exception as e:  # noqa: BLE001 — a measurement that fails is an answer, never a crash in a worker
        return _said(Reach(family=fam, provider=provider, detail=f"{type(e).__name__}"), t0)
