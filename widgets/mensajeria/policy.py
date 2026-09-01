#
# policy.py — WHO gets interrupted, decided by CONFIGURATION instead of a hardcoded predicate (V2-532).
#
# It lives in the WIDGET package on purpose: data.py's contract is stdlib-only plus the `widgets` package (it must
# not import `connectors`), while the connector-side notifier may import widgets lazily — the exact direction the
# unified store already travels (connectors write widgets/_data/mensajeria through widgets.store). This module has
# ZERO imports so either side can hold it without dragging a domain along.
#
# Until now the "deserves attention" filter lived as one frozen expression inside notify.surface()
# (important AND (addressed-to-me OR high urgency)) and the only knob anywhere was muted_channels — a per-chat
# blocklist living in the widget store. The operator's direction (2026-09-01): whether he gets interpellated must
# be configurable PER CONNECTOR, and on top of that per his own criteria. This module is that structure.
#
# Shape, stored in the unified messaging store (widgets/_data/mensajeria/state.json → "notify_policy"):
#
#     { "<platform>": { "notify": "never"|"direct"|"important"|"all", "speak": bool } }
#
#   · notify  — which arriving messages surface AT ALL (brain note + widget prominence):
#       never      → nothing surfaces proactively (the widget still lists everything; reading is not notifying)
#       direct     → only messages addressed to the operator
#       important  → the historical predicate: triaged important AND (addressed to me OR high urgency). DEFAULT.
#       all        → every triaged message that is not already seen
#   · speak — whether a surfaced batch may also be SPOKEN (through voice/proactive, which serializes deliveries,
#       V2-527). speak=False still leaves the [SYSTEM] brain note: silencing the voice must not blind the brain,
#       or follow-up questions get invented answers — the same reason announce() always leaves the note.
#
# Deliberate boundaries, so the next reader does not "fix" them:
#   · muted_channels stays SEPARATE and is enforced upstream (ingest drop + announce filter). It is a per-chat
#     override with delete semantics; this is per-connector routing. Folding them together would give mute the
#     weaker semantics of the two.
#   · An EXPLICIT reminder (agenda reminder, cron) is NEVER governed by this policy — an order the operator gave is
#     its own permission to interrupt (the V2-522 principle). This module is consulted only by the messaging
#     ingest path; the scheduler's delivery does not read it, on purpose.
#   · Pure and stateless over the dict it is given: callers pass the loaded store (or a policy dict), nothing here
#     does I/O. Fail-open to DEFAULT on any malformed shape — a broken config must degrade to today's behavior,
#     never to silence.
#
LEVELS = ("never", "direct", "important", "all")
DEFAULT = {"notify": "important", "speak": True}


def normalize(raw) -> dict:
    """One platform's policy, normalized. Anything unrecognizable degrades to DEFAULT (fail-open)."""
    if not isinstance(raw, dict):
        return dict(DEFAULT)
    notify = raw.get("notify")
    if notify not in LEVELS:
        notify = DEFAULT["notify"]
    speak = raw.get("speak")
    if not isinstance(speak, bool):
        speak = DEFAULT["speak"]
    return {"notify": notify, "speak": speak}


def policy_for(db: dict, platform: str) -> dict:
    """The effective policy for one platform, out of a loaded messaging store dict."""
    try:
        return normalize((db.get("notify_policy") or {}).get(platform))
    except Exception:
        return dict(DEFAULT)


def wants_notice(policy: dict, verdict: dict) -> bool:
    """Does THIS triaged message deserve proactive surfacing under THIS policy?

    `verdict` is one triage result (the shape notify.surface already receives): importante / dirigido_a_mi /
    urgencia. The "important" branch is byte-for-byte the historical predicate, so an untouched install behaves
    exactly as before this module existed."""
    level = policy.get("notify", DEFAULT["notify"])
    if level == "never":
        return False
    if level == "all":
        return True
    if level == "direct":
        return bool(verdict.get("dirigido_a_mi"))
    return bool(verdict.get("importante")
                and (verdict.get("dirigido_a_mi") or verdict.get("urgencia") == "alta"))


def wants_voice(policy: dict, items: list) -> bool:
    """May this surfaced batch also be SPOKEN? The historical urgency criterion stays — policy can only take the
    voice away (speak=False), never force speech onto a batch nothing in which is urgent or addressed."""
    if not policy.get("speak", True):
        return False
    return any(i.get("urgencia") == "alta" or i.get("dirigido_a_mi") for i in items)


def set_policy(db: dict, platform: str, notify=None, speak=None) -> dict:
    """Mutate `db` (the loaded store) with a partial update and return the resulting effective policy.
    Unknown values raise ValueError — a voice-set policy must fail loudly, not save garbage that later reads as
    DEFAULT and makes the operator think his change took."""
    if notify is not None and notify not in LEVELS:
        raise ValueError(f"notify must be one of {LEVELS}")
    if speak is not None and not isinstance(speak, bool):
        raise ValueError("speak must be a bool")
    pol = dict(policy_for(db, platform))
    if notify is not None:
        pol["notify"] = notify
    if speak is not None:
        pol["speak"] = speak
    db.setdefault("notify_policy", {})[platform] = pol
    return pol
