"""nucleo/flash/note_owed.py — a finding pushed to this turn reaches him even when the reply forgets it (2026-10-14).

search-buy-ski-gear EN (2026-10-14 10:37): the worker finished and `proactive.notify` pushed, into his next turn,
«[SISTEMA] Aviso para el operador (zaelar): The shortlist is done and on your screen. Best pick is a Nordica Nemesis
161 with Dynafit bindings in Oakland for $150. Díselo con tus palabras DESPUÉS de contestar…». His turn was a
complaint about an earlier row; the reply answered the complaint and launched a NEW search («Let me re-run it
properly»), and the next one said «it's on the sheet». The real candidates — every criterion met — were never named:
the note is one-shot, so a reply that skips it loses it for good, and nothing else carried those rows (they had gone
to a document, not to the results sheet the delivery backstop reads).

The note's own words are the delivery. When a notice of THIS turn carries a finding (a name and a price) and the
reply names none of it, the notice's sentence is said after the reply — once, as written for him (the session
language is restored downstream by `outgoing_lang`). A notice without a finding (a stall, a question) is left to the
model. Text channel only: on voice the notice is spoken by `proactive.notify` itself. Never raises.
"""
from __future__ import annotations

import math
import re

from . import claim_backing as B

_NOTICE = re.compile(r"\[SISTEMA\] Aviso para el operador \([^)]*\):\s*(.+?)\s*Díselo con tus palabras", re.S)
_PRICE = re.compile(r"[$€£]\s?\d|\d[\d.,]*\s?(?:€|eur\b|euros?\b|usd\b|dollars?\b|d[oó]lares\b)", re.I)
_STOP = frozenset(("the", "best", "pick", "shortlist", "done", "screen", "your", "also", "strong", "here", "this",
                   "that", "and", "with", "for", "lista", "hecho", "pantalla", "mejor", "opcion", "tienes"))


def _notices(window, heard: str) -> list[str]:
    last = next((m for m in reversed(list(window or [])) if (m or {}).get("role") == "user"), {}) or {}
    text = f"{last.get('content') or ''}\n{heard or ''}"
    return list(dict.fromkeys(m.group(1).strip() for m in _NOTICE.finditer(text)))


def _names(notice: str) -> set[str]:
    """The words that name what it found: capitalised words and model codes, past the notice's own frame."""
    out = set()
    for w in re.findall(r"[^\s,;:()«»*\"]+", notice):
        f = B.fold(w.strip(".!?'’-"))
        mixed = any(c.isdigit() for c in f) and any(c.isalpha() for c in f)
        if f and f not in _STOP and not f.isdigit() and ((w[:1].isupper() and len(f) >= 3) or mixed):
            out |= {t for t in re.findall(r"[a-z0-9]+", f) if not t.isdigit()}
    return out


def owed(reply: str, window=None, heard: str = "") -> str:
    """The notice sentence the reply still owes him, or "" (none pushed, none with a finding, or already said)."""
    try:
        said = B.tokens(reply)
        for notice in _notices(window, heard):
            names = _names(notice)
            if not names or not _PRICE.search(notice):
                continue
            if len(names & said) >= max(1, math.ceil(min(len(names), 4) / 2)):
                continue                                   # the reply already told him
            return notice
    except Exception as e:  # noqa: BLE001 — a delivery that cannot be read leaves the reply as it was
        B.emit("note owed: unreadable", error=f"{type(e).__name__}: {e}"[:120])
    return ""


def deliver(reply: str, window=None, heard: str = "") -> str:
    """`reply` with the owed notice after it. Unchanged when nothing is owed."""
    line = owed(reply, window, heard)
    if not line:
        return reply
    B.emit("📬 note owed: a pushed finding the reply skipped is said", notice=line[:160])
    return f"{str(reply or '').rstrip()} {line}".strip()
