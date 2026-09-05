"""nucleo/workflows/store.py — the workflow table's runtime (V2-594).

## What it is for

Before an errand pays for a browser or a worker, something has to answer «do we already know a faster way to
do this?». That answer used to live nowhere. The mesh had a learned route (`mesh_agents.route_for`), but it
only ever remembered SUCCESS, and only under an Oracle intent it was willing to key on — so the two most
expensive cases were both un-cacheable:

  · «nobody on the mesh does wellness» — thrown away every time, so every massage errand paid the Oracle round
    trip again, and then paid a language model to narrate the emptiness.
  · anything the Oracle classified `general` — which was events, shopping and wellness, i.e. most of it.

A negative row with a TTL fixes both. It expires ON PURPOSE: a new agent appears on the mesh and the answer
has to be allowed to change, or the system decides once, in its first week, and is wrong for ever.

## What it costs

Nothing per turn. It is a lexical key (`domains.domain_of`, one regex sweep) plus one indexed SELECT. It is
NEVER carried in a prompt: a table that has to be pasted into the context to be useful would cost more than
the work it saves — the same rule the connector catalogue is held to.

## What it is NOT

Not a second `action_map`. That maps a PHRASE to a LOCAL action on a widget and never leaves the machine;
this maps a DOMAIN of errand to the ORDER of EXTERNAL channels. When a phrase is a local action, the action
map wins and this is never consulted — the fast lane must not grow a network call.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# A learned route is a shortcut, not a truth. Positive rows live a week; a NEGATIVE row lives less, because
# «nobody serves this» is the answer most likely to stop being true — the mesh gains agents on the order of
# days (two arrived the afternoon this was written).
TTL_OK_S = 7 * 24 * 3600
TTL_NONE_S = 3 * 24 * 3600

# Channels, best-known first. Names are namespaced so a row says WHAT kind of thing it points at.
CH_CONNECTOR = "connector"      # a connector already built into the engine
CH_MESH = "mesh"                # an agent on the MeshKore network
CH_BROWSER = "browser"          # the embedded browser against a trusted site
CH_WORKER = "worker"            # a full BrainWorker: the slowest, and always available


@dataclass
class Plan:
    """What to do about one errand, decided without a model and without the network."""
    domain: str = ""
    channels: list[dict] = field(default_factory=list)
    ask_mesh: bool = True
    known_empty: bool = False

    @property
    def best(self) -> dict | None:
        return self.channels[0] if self.channels else None

    def __bool__(self) -> bool:
        return bool(self.domain)


def _fresh(row: dict, now: float) -> bool:
    checked, ttl = row.get("checked_at"), row.get("ttl_s")
    if not checked or not ttl:
        return False
    return (now - float(checked)) < float(ttl)


def plan(request: str, locale: str | None = None) -> Plan:
    """The plan for this errand. Never raises, never blocks, never calls a model or the network."""
    domain = ""
    try:
        from .domains import domain_of
        domain = domain_of(request, locale)
    except Exception:
        pass
    if not domain:
        return Plan()
    now = time.time()
    rows = _rows(domain)
    live = [r for r in rows if r.get("status") == "active" and _fresh(r, now)]
    # The browser channel is DERIVED from the site catalogue, not stored: it has no TTL because it is not an
    # observation about the outside world, it is what this engine already knows. Appended last on purpose —
    # a live mesh agent beats opening a browser, always.
    name, url = site_for(domain, locale)
    if name:
        live = live + [{"channel": CH_BROWSER, "target": name, "evidence": url, "rank": 500,
                        "status": "active", "source": "catalog"}]
    # A negative row only silences the mesh while it is FRESH. Stale means «ask again», which is the entire
    # reason it carries a TTL rather than a flag.
    empty = any(r.get("status") == "none" and r.get("channel") == CH_MESH and _fresh(r, now) for r in rows)
    return Plan(domain=domain, channels=live, ask_mesh=not empty, known_empty=empty)


def _rows(domain: str) -> list[dict]:
    try:
        from memory import api as memory
        return memory.workflows_for(domain)
    except Exception:
        return []


def _pinned(domain: str, channel: str) -> bool:
    """True when the OPERATOR fixed this row by hand. Learning never overwrites a human decision — the same
    invariant the action map holds for a disabled seed row."""
    for r in _rows(domain):
        if r.get("channel") == channel and r.get("source") == "operator":
            return True
    return False


def learn(domain: str, channel: str, *, target: str = "", evidence: str = "",
          rank: int = 100, source: str = "learned", ttl_s: int = TTL_OK_S) -> None:
    """Record that this channel SERVED this domain. Called after a real success, never after a guess."""
    if not domain or not channel:
        return
    if source != "operator" and _pinned(domain, channel):
        return
    try:
        from memory import api as memory
        memory.workflow_upsert(domain, channel, status="active", rank=rank, source=source,
                               target=target, evidence=evidence, ttl_s=ttl_s)
    except Exception:
        pass


def note_empty(domain: str, channel: str = CH_MESH, *, evidence: str = "", ttl_s: int = TTL_NONE_S) -> None:
    """Record that this channel has NOTHING for this domain — the row that saves the most work.

    This is what stops «un masaje» paying an Oracle round trip every single time it is asked, and it is also
    what lets the caller answer «nobody does this yet» as a FACT instead of sending an empty result through a
    language model to have the emptiness described back."""
    if not domain or _pinned(domain, channel):
        return
    try:
        from memory import api as memory
        memory.workflow_upsert(domain, channel, status="none", rank=999, source="learned",
                               evidence=evidence, ttl_s=ttl_s)
    except Exception:
        pass


def forget(domain: str, channel: str = "") -> None:
    """Drop what was learned — the operator correcting the route, or a test cleaning up."""
    try:
        from memory import api as memory
        memory.workflow_forget(domain, channel)
    except Exception:
        pass

# V2-594 F2 · what we ALREADY know, without asking anything.
#
# The operator's rule: «there will be tools we know because we already have them in our memory, and others
# that live on the MeshKore network». The mesh half learns itself from real errands. This is the other half:
# the site catalogue has held a TRUSTED SITE per category for months, and that is a channel — a known site is
# strictly better than a search, and the worker prompt already says so in its own words.
#
# It is derived, never duplicated: the catalogue stays the source and this reads it. A copy would be a second
# inventory of trusted sites, and this house has already paid for that once (`_WEB_RE` and
# `router_guards._KNOWN_SITES` drifted apart for weeks, and twelve sites lived in only one of them).
_CATALOG_CATEGORY = {
    "restaurant": "restaurant_booking", "hotel": "hotel_booking", "flight": "flight_search",
    "events": "event_tickets", "local": "local_business", "shopping": "general_classifieds",
}


def site_for(domain: str, locale: str | None = None) -> tuple[str, str]:
    """The trusted site for this domain as (name, url), or ("", "") when the catalogue has none."""
    cat = _CATALOG_CATEGORY.get(domain or "")
    if not cat:
        return ("", "")
    try:
        from nucleo.flash import site_catalog as _sc
        entry = _sc.entry_for(cat, locale)
    except Exception:
        return ("", "")
    if not entry:
        return ("", "")
    name = getattr(entry, "name", "") or ""
    url = getattr(entry, "url", "") or getattr(entry, "home", "") or ""
    return (str(name), str(url))
