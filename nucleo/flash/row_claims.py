"""nucleo/flash/row_claims.py — a reply names a candidate, or says what it is, only from a source (2026-10-14).

Shortlist rounds of 2026-10-14, healthy chain, every failure an UNBACKED CLAIM about a row:

  · search-buy-phone EN — «wait is the 699 one new?» → «Yes, the 699 listing is new and unused… not refurbished»,
    then «Yes — the iPhone 17 256GB at 699 is still available». The row («iphone 17 256gb — 699», an eBay agent
    listing) carried «Producto NUEVO…: ?» and «Disponible…: ?». `row_check` stayed silent: he named the row by its
    PRICE, which no title word carries, and «new» is three letters (no stem).
  · search-buy-washing-machine ES — «Sí, la Evvo Terra de 329 es de 8 kilos y clase A.» with `row_check`'s own
    «…Clase energética…, sin verificar» appended after it: a confirmation that un-confirms itself.

The rule bounds the CONSEQUENCE, not the judgement: the model still picks, ranks and answers, but a sentence of the
text channel's reply may (a) name a candidate with a price or in «quotes», or (b) state an attribute of a row he or
it named (condition, availability, capacity, energy class, «automatic» — `claim_vocab`) only when a source carries
it (`claim_backing`: a row of a recent sheet with its whole title and its valued facts, a discarded row, his words
and the notes pushed into his turns, the in-turn search, the live errands' steps). Otherwise the sentence goes and
the honest line comes in its place: «De «X» no tengo verificado: …». And (c) a «sí … sin verificar» never stands.

Voice cannot cut what streamed: `said_after` says the correction after the words. Never raises.
"""
from __future__ import annotations

import math
import re

from . import claim_backing as B, claim_vocab as V

_SENT = re.compile(r"(?<=[.!?])\s+(?=[^\s»])")
_QUOTED = re.compile(r"«([^«»]{2,160})»")
_AMOUNT = re.compile(r"(?:[$€£]\s?\d[\d.,]*|\d[\d.,]*\s?(?:€|eur\b|euros?\b|usd\b|dollars?\b|d[oó]lares\b|bucks\b)"
                     r"|(?:\bat|\bfor|\bpor|\ba|—|–)\s+\d{3}[\d.,]*(?!\s*(?:nits|hz|rpm|kg|gb|km|mm|cm|inch|pulgadas|w\b)))",
                     re.I)
_NUMBER = re.compile(r"(?<![\w.,])\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?(?![\w])|(?<![\w.,])\d{3,}(?![\w])")
_NAME_STOP = frozenset((
    "the", "a", "an", "la", "el", "los", "las", "un", "una", "yes", "no", "si", "i", "it", "this", "that", "best",
    "also", "then", "and", "or", "right", "now", "actually", "bueno", "ahora", "mira", "tell", "dime", "want",
    "ok", "vale", "perfect", "perfecto", "great", "done", "hecho", "still", "here", "us", "eur", "usd", "and", "y",
    "de", "del", "con", "for", "at", "por", "is", "es", "my", "your", "tu", "su", "one", "uno", "plus"))
_MAX_SHORT = 40


def _short(item: dict) -> str:
    t = " ".join(str(item.get("title") or "").split()).rstrip("…")
    return t if len(t) <= _MAX_SHORT else t[:_MAX_SHORT - 1].rstrip() + "…"


def _int_digits(amount: str) -> str:
    """«329,50 €» → «329», «1.035,00» → «1035», «699» → «699»: the integer part a person says."""
    s = re.sub(r"[.,]\d{1,2}(?!\d)\s*\D*$", "", str(amount or "").strip())
    return "".join(c for c in s if c.isdigit())


def _sentences(text: str) -> list[str]:
    return [s for s in _SENT.split(str(text or "")) if s.strip()]


def _named(sentence: str, rows: list[dict]) -> list[dict]:
    """The candidate rows a sentence names: by a title word only that row has, or by the price he/it said."""
    from . import row_ask as RA
    live, seen = [], set()
    for r in rows:
        key = B.fold(r["item"].get("title"))
        if not r["rejected"] and key not in seen:
            seen.add(key)
            live.append(r)
    hit = {id(i) for i in RA.named_in(sentence, [r["item"] for r in live])}
    said = {_int_digits(n) for n in _NUMBER.findall(sentence)} - {""}
    said = {d for d in said if len(d) >= 3}
    return [r for r in live if id(r["item"]) in hit or (said and _int_digits(r["item"].get("price")) in said)]


def _name_tokens(phrase: str, his: set[str], first: str) -> list[str]:
    out = []
    for w in re.findall(r"[^\s,;:()«»\"]+", phrase):
        core = w.strip(".!?'’-—–")
        f = B.fold(core)
        if not f or f == first or f in _NAME_STOP or f in his or f.isdigit():
            continue
        mixed = any(c.isdigit() for c in f) and any(c.isalpha() for c in f)
        if (core[:1].isupper() and len(f) >= 3) or (mixed and len(f) >= 2):
            out += [t for t in re.findall(r"[a-z0-9]+", f) if not t.isdigit() and t not in _NAME_STOP]
    return list(dict.fromkeys(out))


def _candidates(sentence: str, his: set[str], figures: set[str] = frozenset()) -> list[tuple[str, list[str]]]:
    """`(phrase, name tokens)` for each candidate the sentence names: a «quoted» row, or a name before a price that
    is not his own figure («up to $250» repeats his ceiling). A sentence about what it will do names none."""
    if V.intends(sentence):
        return []
    first = B.fold((re.findall(r"[^\W\d_]+", sentence) or [""])[0])
    out = [(q, _name_tokens(q.split(" — ")[0], his, "")) for q in _QUOTED.findall(sentence)
           if " — " in q and _AMOUNT.search(" — " + q.split(" — ")[-1])]      # a quoted ROW: «title — price»
    bare = _QUOTED.sub(" ", sentence)
    for m in _AMOUNT.finditer(bare):
        if _int_digits(re.sub(r"[^\d.,]", "", m.group(0))) in figures:
            continue
        head = re.split(r"[,;:()]|\s(?:and|y|or|o|then|luego|tienes|have|plus|between|entre)\s", bare[:m.start()])[-1]
        head = " ".join(head.split()[-6:])
        toks = _name_tokens(head, his, first)
        if toks:
            out.append((head, toks))
    return [(p, t) for p, t in out if t]


def _backed_name(toks: list[str], units: list[set[str]]) -> bool:
    need = max(1, math.ceil(len(toks) / 2))
    return any(len(set(toks) & u) >= need for u in units)


def _carried(concept: str, key: str, named: list[dict], evidence: list[str]) -> bool:
    if any(V.carries(r["text"], concept, key) for r in named):
        return True
    from . import row_ask as RA
    for text in evidence:                         # a note or a search that says it OF THAT ROW backs it too
        for s in _sentences(text):
            if RA.named_in(s, [r["item"] for r in named]) and V.carries(s, concept, key):
                return True
    return False


def review(reply: str, window=None, heard: str = "", *, rows=None, evidence=None, goals=None,
           errand: bool | None = None) -> dict:
    """`{"parts": [...], "lines": [...], "cut": [...]}` — the reply in order, each unbacked claim replaced by its
    honest line (`lines`, for the voice correction); `cut` is what went and why."""
    out = {"parts": [], "lines": [], "cut": []}
    sents = _sentences(reply)
    if not any(V.claims(s) or V.contradicts(s) or _QUOTED.search(s) or _AMOUNT.search(s) for s in sents):
        out["parts"] = sents
        return out
    if not (B.in_errand() if errand is None else errand):
        rows, errand = [], False                 # outside a shortlist only (c), the self-contradiction, is repaired
    rows = B.rows() if rows is None else rows
    evidence = B.texts(window, heard) if evidence is None else evidence
    his_text = B.his_words(window, heard) + " " + (B.goals() if goals is None else goals)
    his = B.tokens(his_text)
    figures = {_int_digits(n) for n in _NUMBER.findall(his_text)} - {""}
    units = [B.tokens(r["text"]) for r in rows] + [B.tokens(t) for t in evidence] + [his]
    heard_rows = _named(B.his_words([], heard), rows)
    from i18n import langs as _lg
    lang = _lg.current_language()
    for s in sents:
        if s.rstrip().endswith("?"):
            out["parts"].append(s)
            continue
        claims = V.claims(s)
        contradicts = V.contradicts(s)
        if V.disclaims(s) and not contradicts:
            out["parts"].append(s)
            continue
        named = _named(s, rows) or (heard_rows[:3] if claims else [])
        bad = [c for c in claims if named and not _carried(c[0], c[1], named, evidence)]
        if bad or (contradicts and claims and named):
            row = ", ".join(f"«{_short(r['item'])}»" for r in named[:2])
            what = ", ".join(dict.fromkeys(p for _, _, p in (bad or claims)))
            kept = ", ".join(dict.fromkeys(c[2] for c in claims if c not in bad)) if bad else ""
            line = lang.claim_unverified.format(row=row, what=what) + (f" {lang.claim_backed.format(what=kept)}" if kept else "")
            _replace(out, s, line, "attribute", what)
            continue
        if contradicts:
            _replace(out, s, lang.claim_not_verified, "yes_and_unverified", "")
            continue
        ghost = [p for p, toks in _candidates(s, his, figures) if not _backed_name(toks, units)] if errand is not False else []
        if ghost:
            out["cut"].append({"why": "candidate", "sentence": s.strip()[:160], "what": ghost[0][:80]})
            continue
        out["parts"].append(s)
    return out


def _replace(out: dict, sentence: str, line: str, why: str, what: str) -> None:
    out["cut"].append({"why": why, "sentence": sentence.strip()[:160], "what": what})
    if line not in out["lines"]:
        out["lines"].append(line)
        out["parts"].append(line)


def guard(reply: str, window=None, heard: str = "") -> str:
    """The text channel's reply with every unbacked claim cut and said as «not verified». Unchanged when clean."""
    try:
        r = review(str(reply or ""), window, heard)
        if not r["cut"]:
            return reply
        body = " ".join(p.strip() for p in r["parts"] if p.strip())
        if not body:
            from i18n import langs as _lg
            body = _lg.current_language().claim_candidate_unbacked
        B.emit("🧾 row claims: unbacked claim cut", cut=r["cut"][:3])
        return body
    except Exception as e:  # noqa: BLE001 — the reply as written beats no reply; the timeline says why
        B.emit("row claims: guard failed", error=f"{type(e).__name__}: {e}"[:160])
        return reply


def said_after(spoken: str, send, speech, heard: str = "", window=None) -> str:
    """Voice: the words streamed, so the correction is said after them. Returns what the turn said in total.

    `window` is the conversation, as the text channel's `guard` gets it (demo pass 124, M2: «how's apple stock doing
    today» then «what about the last month» → «Apple is at 342.08 USD…» was cut as an unbacked candidate, because
    the voice read only this turn's words and «apple» was in the one before)."""
    try:
        r = review(str(spoken or ""), window, heard)
        lines = list(dict.fromkeys(r["lines"]))
        if not lines and any(c["why"] == "candidate" for c in r["cut"]):
            from i18n import langs as _lg
            lines = [_lg.current_language().claim_candidate_unbacked]
        if not lines:
            return spoken
        from i18n import langs as _lg
        line = f"{_lg.current_language().claim_correction} {' '.join(lines)}"
        send(speech.sanitize(line, drop_metadata=False))
        B.emit("🧾 row claims: correction said after the words", cut=r["cut"][:3])
        return f"{str(spoken or '').rstrip()} {line}".strip()
    except Exception as e:  # noqa: BLE001 — the turn's words stand; the timeline says the correction was lost
        B.emit("row claims: voice correction failed", error=f"{type(e).__name__}: {e}"[:160])
        return spoken
