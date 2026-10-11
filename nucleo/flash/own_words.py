"""nucleo/flash/own_words.py — a row zaelar NAMED is never denied when he quotes it back (V2-782).

search-buy-used-car ES (2026-10-11): the delivery backstop said «Peugeot 3008 — € 7.999» from the errand's sheet. One
turn later he asked its year; the reply was «¿De dónde te sale el Peugeot 3008? no lo tienes», and quoted verbatim, «no
aparece en la hoja de resultados». Root cause, from the turn's prompt: the model had written an EMPTY base sheet over
the errand's own one, and the errand sheet's digest carried its first rows only (all of them junk), so the row it had
named was nowhere in front of it — and it trusted the prompt over its own previous line.

The fix is not a sentence in the prompt. Its own words are a FACT of the conversation: when his sentence names a row
the assistant quoted («…») in this window and the reply denies having it, the denial is replaced by what is true —
I named it, and where it is now: still on a sheet (with what its listing carries), discarded (and why), or gone from
the list. The sheets are read directly, every one of them, so a wrong sheet in the prompt cannot hide it again.
"""
from __future__ import annotations

import re

from search.asked import norm as _norm

_QUOTED = re.compile(r"«([^«»]{2,160})»")
#: A reply that says the row does not exist, is not his, or was never said (ES + EN), over normalised text.
_DENIES = re.compile(
    r"(de donde (te )?sale|no lo tienes|no lo tengo|no (aparece|existe|esta) en la hoja|no aparece|no existe|"
    r"no hay ninguna? (ficha|fila|anuncio|resultado)|nunca (te )?(he dicho|dije|nombre)|yo no (he dicho|dije)|"
    r"where did you get|doesn'?t exist|does not exist|(isn'?t|is not|not) on the (results )?sheet|"
    r"i never (said|mentioned|named)|i didn'?t (say|mention|name)|there'?s no such)")
_SENT = re.compile(r"(?<=[.!?])\s+")


def _tokens(title: str) -> list[str]:
    return [w for w in _norm(title).split() if any(c.isdigit() for c in w) or len(w) >= 4]


def _named_by_us(window) -> list[str]:
    """Every «…» the assistant said in this window, newest first, as «title — datum» strings."""
    out: list[str] = []
    for m in reversed(list(window or [])):
        if (m or {}).get("role") != "assistant":
            continue
        for q in _QUOTED.findall(str((m or {}).get("content") or "")):
            if q not in out:
                out.append(q)
    return out


def _quoted_back(heard: str, named: list[str]) -> str:
    """The row of ours his sentence names: all its digit tokens, or two of its words, or its only word."""
    h = set(_norm(heard).split())
    for row in named:
        toks = _tokens(row.split(" — ")[0])
        if not toks:
            continue
        digits = [t for t in toks if any(c.isdigit() for c in t)]
        hits = [t for t in toks if t in h]
        if (digits and all(t in h for t in digits) and hits) or len(hits) >= min(2, len(toks)):
            return row
    return ""


def _where_now(row: str) -> tuple[str, dict]:
    """("still" | "discarded" | "gone", the sheet row or rejected entry). Reads every sheet on disk."""
    title = _norm(row.split(" — ")[0])
    try:
        from widgets.results import data as _d
        for sid in _d.sheets():
            view = _d.view_data(sid)
            for it in view.get("items") or []:
                if _norm(it.get("title")) == title:
                    return "still", it
            for rj in view.get("rejected") or []:
                if _norm(rj.get("title")) == title:
                    return "discarded", rj
    except Exception as e:  # noqa: BLE001 — unreadable sheets: say what is surely true, that we named it
        _emit("🗣 own words: sheets unreadable", error=f"{type(e).__name__}: {e}"[:120])
    return "gone", {}


def _facts(item: dict) -> str:
    parts = [str(item.get("subtitle") or "").strip()]
    for f in item.get("facts") or []:
        if isinstance(f, dict) and f.get("value") and str(f.get("label") or "").lower() not in ("origen", "origin"):
            parts.append(f"{f.get('label')}: {f.get('value')}".strip(": "))
    return " · ".join(p for p in parts if p)[:220]


def keep_its_word(reply: str, window, heard_now: str = "") -> str:
    """`reply` unchanged — unless it denies a row the assistant named and he just quoted. Never raises."""
    try:
        if not reply or not heard_now or not _DENIES.search(_norm(reply)):
            return reply
        row = _quoted_back(heard_now, _named_by_us(window))
        if not row:
            return reply
        from i18n import langs as _langs
        lang = _langs.current_language()
        state, entry = _where_now(row)
        said = [lang.own_row_named.format(row=row)]
        if state == "still":
            facts = _facts(entry)
            said += [lang.own_row_still, lang.own_row_facts.format(facts=facts) if facts else lang.own_row_no_facts]
        elif state == "discarded":
            said.append(lang.own_row_discarded_off if entry.get("source") == "category gate"
                        else lang.own_row_discarded.format(why=str(entry.get("why") or "").rstrip(".")))
        else:
            said.append(lang.own_row_gone)
        rest = [s for s in _SENT.split(reply) if s.strip() and not _DENIES.search(_norm(s))]
        _emit("🗣 own words kept: a named row is not denied", row=row[:80], state=state)
        return " ".join(said + rest).strip()
    except Exception as e:  # noqa: BLE001 — a repair that fails leaves the reply as it was, and says so
        _emit("🗣 own words: repair failed", error=f"{type(e).__name__}: {e}"[:120])
        return reply


def _emit(label: str, **extra) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        __import__("logging").getLogger(__name__).debug("own_words emit failed: %s", e)
