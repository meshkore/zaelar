"""Every host that paints a card gives it the WHOLE `ctx` the cards use — a member one host forgets is a TypeError
inside the card the moment it is tapped.

Found 2026-10-26 by the messaging card's render tests: seven cards call `ctx.openConnector` (the one door to ⚙
Conectores), and the phone's deck and the desktop's activity rail had never been given it — on the phone, every
«connect» tap in every card threw, and nothing said so. The same two hosts lacked `upload` and `connect`, and the
rail `top` and `scroll`. One host is free to implement a member as an honest no-op or a «do this from your computer»
note; it is not free to leave it out.

Read from source on purpose: the members a card can reach are the `ctx.<name>` it writes, and a host's members are
the keys of the object literal it hands to `render`. Generic by construction — the next member a card starts using
is held to every host the day it appears.
"""
from __future__ import annotations

import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]

_HOSTS = {
    "desktop card": ("frontend/app/widgets/desktop.js", 0),
    "desktop activity rail": ("frontend/app/widgets/desktop.js", 1),
    "phone deck": ("frontend/mobile/app/shell/Deck.js", 0),
}


def _used() -> set[str]:
    names: set[str] = set()
    for f in (ENGINE / "widgets").glob("*/widget.js"):
        names |= set(re.findall(r"\bctx\.([A-Za-z_]\w*)", f.read_text(encoding="utf-8")))
    return names


def _ctx_literal(src: str, nth: int) -> str:
    """The text of the nth `const ctx = { … }` object literal, braces balanced; strings, templates and comments
    skipped (a comment's apostrophe is not a quote)."""
    starts = [m.end() - 1 for m in re.finditer(r"const ctx\s*=\s*\{", src)]
    j, depth, quote = starts[nth], 0, None
    while j < len(src):
        c = src[j]
        if quote:
            if c == "\\":
                j += 2
                continue
            if c == quote:
                quote = None
        elif src.startswith("//", j):
            j = src.find("\n", j)
            continue
        elif src.startswith("/*", j):
            j = src.find("*/", j) + 2
            continue
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                lit = src[starts[nth]:j + 1]
                assert len(lit) < 8000, "the ctx literal was not found whole — the scan ran past it"
                return lit
        j += 1
    raise AssertionError("unbalanced ctx literal")


def _members(literal: str) -> set[str]:
    return set(re.findall(r"(?:^|[,{]\s*|\n\s*)(?:get\s+|async\s+)?([A-Za-z_]\w*)\s*(?::|\()", literal))


def test_every_host_gives_every_member_a_card_uses():
    used = _used()
    missing = {}
    for host, (rel, nth) in _HOSTS.items():
        have = _members(_ctx_literal((ENGINE / rel).read_text(encoding="utf-8"), nth))
        if used - have:
            missing[host] = sorted(used - have)
    assert not missing, f"a host leaves out ctx members cards call (a TypeError on tap): {missing}"
