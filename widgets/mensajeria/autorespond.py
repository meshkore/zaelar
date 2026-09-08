#
# autorespond.py — WHETHER an arriving message gets an automatic reply (V2-624, the go-ahead for what
# connectors/whatsapp/client.py has called "Phase 4" since INI-014).
#
# Same placement contract as policy.py: a ZERO-import module inside the widget package, so the stdlib-only
# data.py and the connector-side owner read the SAME rule — a decision that exists twice is a decision that
# drifts. Callers pass the loaded store dict; nothing here does I/O or knows a platform's transport.
#
# Shape, stored in the unified messaging store (widgets/_data/mensajeria/state.json):
#
#     "autoresponder": { "<platform>": { "enabled": bool, "text": str, "hours": "HH:MM-HH:MM"|None } }
#     "auto_replied":  { "<platform>|<chatId>": <ts of the last auto-reply to that chat> }
#
# The RULES, each one a deliberate boundary:
#   · NEVER a group. An automatic reply inside a group chat speaks to everybody about the operator's absence
#     and answers people who were not talking to him. Non-negotiable, not configurable.
#   · Email only when the triage says the mail is ADDRESSED TO HIM (dirigido_a_mi): a vacation reply to every
#     newsletter and receipt is spam with his name on it. WhatsApp/Telegram 1:1 chats are addressed to him by
#     construction, so the flag is not required there.
#   · One auto-reply per chat per COOLDOWN (24 h): the point is "I'm away", said once — WhatsApp's own
#     business auto-reply behaves the same way. The ledger is DURABLE (in the store), because an in-memory
#     guard cannot dedupe against a durable source (V2-607: the triple-announced Amazon mail).
#   · `hours` ("HH:MM-HH:MM", local time, wrap-around allowed: "22:00-08:00") bounds WHEN it speaks; absent
#     means whenever it is enabled. Malformed hours read as "always" — a broken config must degrade to the
#     state the operator explicitly enabled, never to silent surprise windows.
#
COOLDOWN_S = 24 * 3600
_KEY = "autoresponder"
_LEDGER = "auto_replied"
_LEDGER_CAP = 400


def config_for(db: dict, platform: str) -> dict:
    """One platform's autoresponder config, normalized. Disabled/absent → {"enabled": False, ...}."""
    raw = (db.get(_KEY) or {}).get(platform)
    if not isinstance(raw, dict):
        return {"enabled": False, "text": "", "hours": None}
    text = str(raw.get("text") or "").strip()
    return {
        "enabled": bool(raw.get("enabled")) and bool(text),
        "text": text,
        "hours": raw.get("hours") if isinstance(raw.get("hours"), str) and raw.get("hours") else None,
    }


def set_config(db: dict, platform: str, text=None, hours=None, enabled=None) -> dict:
    """Partial update; returns the resulting effective config. Bad `hours` raises — a voice-set window must
    fail loudly, not save a string that later silently reads as "always" (the policy.py rule)."""
    if hours is not None and hours != "" and _parse_hours(hours) is None:
        raise ValueError('hours must look like "HH:MM-HH:MM" (e.g. "22:00-08:00")')
    cur = (db.get(_KEY) or {}).get(platform)
    cur = dict(cur) if isinstance(cur, dict) else {}
    if text is not None:
        cur["text"] = str(text).strip()[:1000]
    if hours is not None:
        cur["hours"] = str(hours) or None
    if enabled is not None:
        cur["enabled"] = bool(enabled)
    elif text is not None and cur.get("text"):
        cur["enabled"] = True          # dictating a message IS asking for it, unless told otherwise
    db.setdefault(_KEY, {})[platform] = cur
    return config_for(db, platform)


def clear_config(db: dict, platform: str) -> None:
    (db.get(_KEY) or {}).pop(platform, None)


def active_platforms(db: dict) -> list[str]:
    """Platforms with an enabled autoresponder — for the settings panel and the brain's brief."""
    return [p for p in (db.get(_KEY) or {}) if config_for(db, p)["enabled"]]


def _parse_hours(spec) -> tuple | None:
    """"HH:MM-HH:MM" → ((h,m),(h,m)) or None if unreadable."""
    try:
        a, _, b = str(spec).partition("-")
        h1, m1 = a.strip().split(":")
        h2, m2 = b.strip().split(":")
        h1, m1, h2, m2 = int(h1), int(m1), int(h2), int(m2)
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
            return None
        return ((h1, m1), (h2, m2))
    except (ValueError, AttributeError):
        return None


def within_hours(spec, now_hm: tuple) -> bool:
    """Is local time `now_hm` = (hour, minute) inside the window? Wrap-around ("22:00-08:00") supported.
    No/malformed window → True (the window only NARROWS an enabled responder, it never enables one)."""
    win = _parse_hours(spec) if spec else None
    if win is None:
        return True
    (h1, m1), (h2, m2) = win
    start, end, now = h1 * 60 + m1, h2 * 60 + m2, now_hm[0] * 60 + now_hm[1]
    if start == end:
        return True
    if start < end:
        return start <= now < end
    return now >= start or now < end       # wraps midnight


def should_reply(db: dict, item: dict, now_ts: float, now_hm: tuple) -> str | None:
    """The text to auto-send for this just-stored inbound item, or None. Pure decision — the caller records
    the ledger entry (`note_replied`) only once the reply is actually queued."""
    platform = item.get("platform")
    if not platform or item.get("chatId") is None:
        return None
    cfg = config_for(db, platform)
    if not cfg["enabled"]:
        return None
    if item.get("isGroup"):
        return None
    if platform == "email" and not item.get("dirigido_a_mi"):
        return None
    if not within_hours(cfg["hours"], now_hm):
        return None
    key = f"{platform}|{item.get('chatId')}"
    last = (db.get(_LEDGER) or {}).get(key)
    try:
        if last is not None and (float(now_ts) - float(last)) < COOLDOWN_S:
            return None
    except (TypeError, ValueError):
        pass
    return cfg["text"]


def note_replied(db: dict, platform: str, chat_id, now_ts: float) -> None:
    """Record the auto-reply in the durable ledger, oldest entries dropped past the cap."""
    ledger = db.get(_LEDGER)
    if not isinstance(ledger, dict):
        ledger = {}
        db[_LEDGER] = ledger
    ledger[f"{platform}|{chat_id}"] = float(now_ts)
    if len(ledger) > _LEDGER_CAP:
        for k in sorted(ledger, key=lambda k: ledger[k])[: len(ledger) - _LEDGER_CAP]:
            ledger.pop(k, None)
