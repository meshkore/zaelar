"""Blocking a channel: which channel the order names, the block itself, and the pasted link that outranks it.

Moved out of `actions.py` (V2-596's two handlers) and extended after `video-blocked-channel-respected`
(2026-10-10): «Bloquéame este canal, no me lo vuelvas a sugerir» names NO channel — the referent is on the card.
`block_channel` stored whatever string arrived, so the brain either had to know the name (it did not: the EN turn
fell back to a style directive, the ES one sent a Brain Worker probing nonexistent widgets for 210 s) or would
have blocked the literal «este canal». `follow_channel` already read the playing video's author when the order
named nobody (V2-632); blocking is the same reference and now reads it the same way.

The reference, in order: a row number (the band he is looking at: search results, else suggestions, else the
queue) → nothing / a bare pointer («este», «that one») → the playing video's channel, else the ONE channel on
screen, else the question naming the candidates → a fragment that names exactly one channel on the card → the
full name as the card shows it. Anything else is stored as he said it (`_is_blocked` matches fragments).
"""
from __future__ import annotations

import re

from . import blocked_order as _bo
from . import data as _d

# A pointer at the card, not a name: what is left after these words is the name, if any.
_POINTER = re.compile(r"\b(este|ese|esta|esa|aquel|aquella|el|la|del|de|canal|canales|uno|video|"
                      r"this|that|the|one|channel|current|actual|video's|videos)\b")


def _pick(es: str, en: str) -> str:
    return _d._hl.pick(es, en)


def _on_screen(db: dict) -> list:
    """Distinct channel names the card is showing, in the order he would see them."""
    out = []
    rows = [{"channel": db.get("channel")}] if db.get("videoId") else []
    rows += list(db.get("search_results") or []) + list(db.get("suggested") or []) + list(db.get("list") or [])
    for it in rows:
        ch = str((it or {}).get("channel") or "").strip()
        if ch and all(_d._norm(ch) != _d._norm(o) for o in out):
            out.append(ch)
    return out


def _by_number(db: dict, n: int) -> str:
    for band in ("search_results", "suggested", "list"):
        rows = db.get(band) or []
        if rows:
            return str((rows[n - 1] or {}).get("channel") or "").strip() if 0 < n <= len(rows) else ""
    return ""


def resolve(p: dict, db: dict) -> "tuple[str, dict | None]":
    """(channel, None) when the order names one; ("", refusal) when it has to ask which."""
    raw = str(p.get("channel") or p.get("name") or p.get("item") or "").strip()[:80]
    if raw.isdigit():
        ch = _by_number(db, int(raw))
        if ch:
            return ch, None
        return "", {"ok": False, "error": "no_channel",
                    "message": _pick(f"No hay ninguna fila {raw} con canal en pantalla: dime qué canal bloqueo.",
                                     f"There is no row {raw} with a channel on screen: tell me which channel to block.")}
    if raw and _POINTER.sub(" ", _d._norm(raw)).strip(" .,'¿?¡!"):
        seen = [c for c in _on_screen(db) if _d._is_blocked(c, [raw])]
        return (seen[0] if len(seen) == 1 else raw), None
    cur = str(db.get("channel") or "").strip() if db.get("videoId") else ""
    if cur:
        return cur, None
    seen = _on_screen(db)
    if len(seen) == 1:
        return seen[0], None
    if seen:
        names = ", ".join(f"«{c}»" for c in seen[:4])
        return "", {"ok": False, "error": "which_channel", "candidates": seen[:4],
                    "message": _pick(f"¿Qué canal bloqueo? En pantalla hay {names}.",
                                     f"Which channel should I block? On screen there are {names}.")}
    return "", {"ok": False, "error": "no_channel",
                "message": _pick("No veo ningún canal en pantalla: dime su nombre, como sale en la lista.",
                                 "I don't see any channel on screen: tell me its name, as it shows in the list.")}


def block(action, p, db) -> dict:
    # V2-596 — «no quiero ver este canal»: the filter the operator educates by voice. Blocking also SWEEPS the
    # queue and the suggestions band — a channel he just refused must not keep sitting there — but never cuts
    # what is already playing (V2-366's rule: only `close` stops playback).
    ch, refusal = resolve(p, db)
    if refusal is not None:
        return refusal
    blocked = db.setdefault("blocked_channels", [])
    if any(_d._norm(b) == _d._norm(ch) for b in blocked):
        _d.store.save(_d.WID, db)
        return {"ok": True, "already_blocked": True, "channel": ch, "blocked": list(blocked),
                "message": _pick(f"«{ch}» ya estaba bloqueado.", f"«{ch}» was already blocked.")}
    blocked.append(ch)
    lst = db.get("list") or []
    cur = lst[int(db.get("pos", -1))] if 0 <= int(db.get("pos", -1)) < len(lst) else None
    kept = [it for it in lst if not _d._is_blocked(it.get("channel") or "", [ch])]
    swept = len(lst) - len(kept)
    db["list"] = kept
    db["pos"] = kept.index(cur) if cur is not None and cur in kept else -1
    sug = db.get("suggested") or []
    db["suggested"] = [it for it in sug if not _d._is_blocked(it.get("channel") or "", [ch])]
    swept += len(sug) - len(db["suggested"])
    _d.store.save(_d.WID, db)
    return {"ok": True, "channel": ch, "removed_from_list": swept, "blocked": list(blocked),
            "message": _pick(f"Bloqueado «{ch}»: ya no saldrá en búsquedas ni en sugerencias.",
                             f"Blocked «{ch}»: it won't show up in searches or suggestions any more.")}


def unblock(action, p, db) -> dict:
    ch = str(p.get("channel") or p.get("name") or p.get("item") or "").strip()
    blocked = db.get("blocked_channels") or []
    n = _d._norm(ch)
    hit = next((b for b in blocked if _d._norm(b) == n or (n and n in _d._norm(b))), None)
    if hit is None and len(blocked) == 1 and not _POINTER.sub(" ", n).strip(" .,'¿?¡!"):
        hit = blocked[0]                       # «desbloquéalo» with ONE blocked channel names that one
    if hit is None:
        return {"ok": False, "error": "not_blocked", "channel": ch, "blocked": list(blocked),
                "message": "Ese canal no está bloqueado." if blocked
                           else "No hay ningún canal bloqueado."}
    blocked.remove(hit)
    _d.store.save(_d.WID, db)
    return {"ok": True, "channel": hit, "blocked": list(blocked)}


def channel_of(db: dict, vid: str) -> str:
    """The channel the card already knows for this id (a row it showed, or his history) — "" when none does.
    The oembed lookup is best-effort and fails open to "", which would let a pasted link from a blocked channel
    play without the notice."""
    for band in ("list", "search_results", "suggested", "history"):
        for it in db.get(band) or []:
            if str((it or {}).get("videoId") or "") == vid and str(it.get("channel") or "").strip():
                return str(it["channel"]).strip()
    return ""


def explicit_link_notice(db: dict, explicit: bool, channel: str, title: str, queued: bool = False) -> dict:
    """A link he PASTED from a channel he blocked plays (or is queued) — an explicit order outranks a standing filter
    (V2-604) — and says so: the card in its banner when it plays, and the turn's reply through the stamp
    `blocked_order` leaves for `nucleo.flash.blocked_channel_receipt`. Returns the notice ({} when nothing to say)."""
    if not (explicit and channel and _d._is_blocked(channel, db.get("blocked_channels") or [])):
        return {}
    _bo.stamp(db, channel, title, queued)
    if queued:
        return {"notice": "channel_blocked", "channel": channel,
                "message": _pick(f"Lo añado a la cola, aunque es de «{channel}», un canal que tienes bloqueado.",
                                 f"Queued it, though it's from «{channel}», a channel you blocked.")}
    db["blocked_notice"] = {"kind": "channel_blocked", "from": str(title or "")[:100], "channel": channel[:80]}
    return {"notice": "channel_blocked", "channel": channel,
            "message": _pick(f"Lo pongo, aunque es de «{channel}», un canal que tienes bloqueado.",
                             f"Playing it, though it's from «{channel}», a channel you blocked.")}
