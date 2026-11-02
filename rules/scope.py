"""rules/scope.py — the scope grammar and a request's path (V2-806).

    global
    <domain>[/<channel>[/<act>]]      messaging · messaging/email · messaging/email/send_new · messaging/*/send_new
    widget:<id>[/<action>]
    item:<id>

`*` in a ROW's scope matches any one segment. A REQUEST's path holds concrete anchors, except a channel the call
cannot name, which is `*` — and a row for a named channel never matches it (a rule for email never reaches a send
whose channel is unknown).

Nothing here reads words: a scope is built from what the request already carries (its consent class, channel,
widget, action, item) — declared data some other layer resolved.
"""
from __future__ import annotations

GLOBAL = "global"
ANY = "*"
VOICE = "voice"
SEARCH = "search"            # what he is shown when the assistant finds things for him (V2-838)

# The levels of a path, general → specific. A row matched at a higher level runs later and wins.
L_GLOBAL, L_DOMAIN, L_CHANNEL, L_WIDGET, L_ACTION, L_ITEM = range(6)


def norm(scope) -> str:
    """Canonical spelling: lower-case, no blanks, no empty segments. The legacy `general` is `global`."""
    s = "".join(str(scope or "").strip().lower().split())
    if not s or s in ("general", "all"):
        return GLOBAL
    head, sep, tail = s.partition(":")
    if sep:
        segs = [x for x in tail.split("/") if x]
        return f"{head}:{'/'.join(segs)}" if segs else GLOBAL
    return "/".join(x for x in s.split("/") if x) or GLOBAL


def _parts(scope: str) -> tuple[str, list[str]]:
    s = norm(scope)
    if s == GLOBAL:
        return "global", []
    head, sep, tail = s.partition(":")
    if sep:
        return head, tail.split("/")
    return "domain", s.split("/")


def covers(rule_scope: str, anchor: str) -> bool:
    """Does a row's scope match this one anchor of a request's path? Segment by segment; `*` in the row matches
    anything, a concrete segment matches only itself (an anchor's `*` included)."""
    fr, sr = _parts(rule_scope)
    fa, sa = _parts(anchor)
    if fr != fa or len(sr) != len(sa):
        return False
    return all(r == ANY or r == a for r, a in zip(sr, sa))


def wildcards(scope: str) -> int:
    return _parts(scope)[1].count(ANY)


def split_key(key: str) -> tuple[str, str]:
    """A consent key `<domain>.<act>[@<channel>]` → (class, channel)."""
    k = str(key or "").strip()
    cls, _, ch = k.partition("@")
    return cls.strip(), ch.strip().lower()


def class_scope(cls: str, channel: str = "") -> str:
    """The scope of a consent class, refined by its channel: `messaging.send_new@email` → `messaging/email/send_new`;
    unrefined → `messaging/*/send_new` (every channel)."""
    cls = str(cls or "").strip().lower()
    if not cls:
        return GLOBAL
    domain, dot, act = cls.partition(".")
    if not dot:
        return norm(domain)
    return norm(f"{domain}/{str(channel or '').strip().lower() or ANY}/{act.replace('/', '_')}")


def path(*, cls: str = "", channel: str = "", widget: str = "", action: str = "", item: str = "",
         surface: str = "") -> list[tuple[int, str]]:
    """The request's anchors, general → specific, each with its level. `cls` may carry its channel (`a.b@c`)."""
    c, ch = split_key(cls)
    ch = (str(channel or "").strip().lower() or ch)
    out: list[tuple[int, str]] = [(L_GLOBAL, GLOBAL)]
    if surface:
        out.append((L_DOMAIN, norm(surface)))
    domain = c.partition(".")[0].strip().lower() if c else ""
    if domain:
        out.append((L_DOMAIN, norm(domain)))
        if ch:
            out.append((L_CHANNEL, norm(f"{domain}/{ch}")))
    wid = str(widget or "").split("::", 1)[0].strip().lower()
    if wid:
        out.append((L_WIDGET, f"widget:{wid}"))
    if c and "." in c:
        out.append((L_ACTION, class_scope(c, ch)))
    if wid and action:
        out.append((L_ACTION, norm(f"widget:{wid}/{str(action).strip().lower()}")))
    if item:
        out.append((L_ITEM, f"item:{str(item).strip().lower()}"))
    return out


def level_in(rule_scope: str, anchors: list[tuple[int, str]]) -> int | None:
    """The level at which a row's scope matches the path, or None when it matches no anchor."""
    hit = [lvl for lvl, a in anchors if covers(rule_scope, a)]
    return max(hit) if hit else None


def excluded(excepts, anchors: list[tuple[int, str]]) -> bool:
    """A row's `except` list names narrower scopes it does NOT cover."""
    return any(covers(e, a) for e in (excepts or []) for _lvl, a in anchors)
