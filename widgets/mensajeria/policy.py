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
#   · notify  — which arriving messages INTERRUPT (brain note + spoken notice). DEFAULT: never (V2-607).
#       never      → nothing interrupts. The widget still receives and lists everything; reading is not notifying
#       direct     → only messages addressed to the operator
#       important  → the historical predicate: triaged important AND (addressed to me OR high urgency)
#       all        → every message that is not already taken in
#   · highlight — which messages the SUMMARY tab (the unified list, no lens) puts in front of him. DEFAULT:
#       direct. Same vocabulary minus "never" (a summary that shows nothing is a broken screen, not a policy).
#       The per-platform lenses ignore it entirely: there, everything unread is listed.
#   · speak — whether a notice may also be SPOKEN (through voice/proactive, which serializes deliveries,
#       V2-527). speak=False still leaves the [SYSTEM] brain note: silencing the voice must not blind the brain,
#       or follow-up questions get invented answers — the same reason announce() always leaves the note.
#
# Why notify defaults to NEVER (operator, 2026-09-07). Arriving mail is not an event that deserves his attention
# by construction — he is often READING the very messages that arrive, and a thousand-message backlog can now
# reach the widget (V2-606), so "important" as a default turns a working inbox into a loudspeaker. Being told is
# something he asks for ("avísame cada vez que llegue un mensaje"), and `set_notify` is how he asks. The two
# things that used to be one knob are now two: what ARRIVES is not what INTERRUPTS.
#
# Deliberate boundaries, so the next reader does not "fix" them:
#   · muted_channels stays SEPARATE and is enforced upstream (ingest drop + announce filter). It is a per-chat
#     override with delete semantics; this is per-connector routing. Folding them together would give mute the
#     weaker semantics of the two.
#   · An EXPLICIT reminder (agenda reminder, cron) is NEVER governed by this policy — an order the operator gave is
#     its own permission to interrupt (the V2-522 principle). This module is consulted only by the messaging
#     ingest path; the scheduler's delivery does not read it, on purpose.
#   · Pure and stateless over the dict it is given: callers pass the loaded store (or a policy dict), nothing here
#     does I/O. A malformed shape degrades to DEFAULT, which since V2-607 IS silence for `notify` — deliberately,
#     because the setting a broken config must not resurrect is the one that talks. `highlight` degrades to
#     "direct", so a broken config never empties the summary either.
#
LEVELS = ("never", "direct", "important", "all")
#: The summary criterion has no "never": an empty main tab is a broken screen, not a configuration.
HIGHLIGHT_LEVELS = ("direct", "important", "all")
DEFAULT = {"notify": "never", "speak": True, "highlight": "direct"}


def normalize(raw) -> dict:
    """One platform's policy, normalized. Anything unrecognizable degrades to DEFAULT."""
    if not isinstance(raw, dict):
        return dict(DEFAULT)
    notify = raw.get("notify")
    if notify not in LEVELS:
        notify = DEFAULT["notify"]
    highlight = raw.get("highlight")
    if highlight not in HIGHLIGHT_LEVELS:
        highlight = DEFAULT["highlight"]
    speak = raw.get("speak")
    if not isinstance(speak, bool):
        speak = DEFAULT["speak"]
    return {"notify": notify, "speak": speak, "highlight": highlight}


def policy_for(db: dict, platform: str) -> dict:
    """The effective policy for one platform, out of a loaded messaging store dict."""
    try:
        return normalize((db.get("notify_policy") or {}).get(platform))
    except Exception:
        return dict(DEFAULT)


def _matches(level: str, verdict: dict) -> bool:
    """One message against one criterion level. The "important" branch is byte-for-byte the predicate that was
    frozen inside notify.surface() before V2-532, so a channel configured back to it behaves exactly as it did.

    Single-sourced because `notify` and `highlight` speak the SAME vocabulary over the same verdict shape
    (importante / dirigido_a_mi / urgencia). Writing the ladder twice is how the two knobs would drift apart."""
    if level == "never":
        return False
    if level == "all":
        return True
    if level == "direct":
        return bool(verdict.get("dirigido_a_mi"))
    return bool(verdict.get("importante")
                and (verdict.get("dirigido_a_mi") or verdict.get("urgencia") == "alta"))


def wants_notice(policy: dict, verdict: dict) -> bool:
    """May THIS message INTERRUPT him (brain note + possibly voice) under THIS policy?

    Since V2-607 this answers a strictly narrower question than it used to: it no longer decides whether the
    message is STORED. Everything triaged reaches the widget; this only decides who gets told."""
    return _matches(policy.get("notify", DEFAULT["notify"]), verdict)


def wants_highlight(policy: dict, verdict: dict) -> bool:
    """Does THIS message belong in the SUMMARY tab — the unified list he sees with no lens selected?

    Separate from `wants_notice` on purpose (operator, 2026-09-07): what is worth putting in front of him when he
    looks is not the same question as what is worth interrupting him with. Default `direct` = addressed to him.
    A message that does not make it here is not hidden: it is in its own platform section, unread, like always."""
    return _matches(policy.get("highlight", DEFAULT["highlight"]), verdict)


def wants_voice(policy: dict, items: list) -> bool:
    """May this surfaced batch also be SPOKEN? The historical urgency criterion stays — policy can only take the
    voice away (speak=False), never force speech onto a batch nothing in which is urgent or addressed."""
    if not policy.get("speak", True):
        return False
    return any(i.get("urgencia") == "alta" or i.get("dirigido_a_mi") for i in items)


def set_policy(db: dict, platform: str, notify=None, speak=None, highlight=None) -> dict:
    """Mutate `db` (the loaded store) with a partial update and return the resulting effective policy.
    Unknown values raise ValueError — a voice-set policy must fail loudly, not save garbage that later reads as
    DEFAULT and makes the operator think his change took."""
    if notify is not None and notify not in LEVELS:
        raise ValueError(f"notify must be one of {LEVELS}")
    if highlight is not None and highlight not in HIGHLIGHT_LEVELS:
        raise ValueError(f"highlight must be one of {HIGHLIGHT_LEVELS}")
    if speak is not None and not isinstance(speak, bool):
        raise ValueError("speak must be a bool")
    pol = dict(policy_for(db, platform))
    if notify is not None:
        pol["notify"] = notify
    if speak is not None:
        pol["speak"] = speak
    if highlight is not None:
        pol["highlight"] = highlight
    db.setdefault("notify_policy", {})[platform] = pol
    return pol
