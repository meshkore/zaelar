"""widgets/results/hard_checks.py — each HARD requirement of his is a column every row carries: yes · no · «?».

Measured in `rental-car-automatic-airport` (2026-10-11, ES and EN, 2/5 both). He asked for an automatic car with
pick-up and return at the airport, and repeated it three and four times. The browser navigated sixteen times and
extracted twice; the sheet ended with twelve rows of `title + price` and not one of them said whether it was
automatic. Asked «¿el Polo es automático y en el aeropuerto?», the turn had nothing to read — the row had no such
field — so it answered with a template. In the EN round the worker did end up writing «Transmission: Automatic (US
standard — not confirmed on the deal page)», on a `present` three minutes after the question.

The sheet already had the place for the requirement (`criteria.hard`, seeded from a research brief or written by
the worker) and the place for a row's hard data (`facts`). What it lacked was the link between them: a criterion
nobody checks per row is a sentence on another tab. So every door into the sheet (`actions._file_pages`) stamps the
rows here — one fact per hard criterion, labelled with the criterion, value «?» until somebody verifies it — and the
reply tells the worker how many rows still say «?». A verified value starts with yes/no and says where it was seen;
anything else reads as not verified, because a value that does not commit is not a confirmation.

Whether a row MEETS a requirement stays the worker's judgement, made on the listing; this module only makes the
question impossible to skip and the answer readable by the turn (`nucleo/flash/row_check.py`).
"""
from __future__ import annotations

import re
import unicodedata

UNKNOWN = "?"
YES, NO, UNVERIFIED = "yes", "no", "unknown"

#: The words a verified value OPENS with. Closed and short on purpose: the worker is told to write exactly this.
_YES_WORDS = {"yes", "si", "true", "ok", "confirmado", "confirmed", "verificado", "verified"}
_NO_WORDS = {"no", "false"}
_MAX_FACTS = 30            # same bound as the sheet's own (`record._MAX_FACTS`)
_SOURCE_SPLIT_RE = re.compile(r"\s*(?:—|–|-|:|\(|,)\s*")


def _norm(text) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def stems(text) -> set[str]:
    """The comparable stems of a phrase: words of 4+ letters cut to 6, so «automático» meets «automatic»."""
    return {w[:6] for w in re.findall(r"[a-z]{4,}", _norm(text))}


def hard_of(data: dict) -> list[str]:
    """His hard requirements on this sheet, in the order they were written."""
    return [str(c).strip() for c in (((data or {}).get("criteria") or {}).get("hard") or []) if str(c).strip()]


def fact_for(item: dict, criterion: str) -> dict | None:
    """The row's fact about this criterion: same label, or a label sharing a stem with it."""
    facts = [f for f in ((item or {}).get("facts") or []) if isinstance(f, dict)]
    want = _norm(criterion)
    for f in facts:
        if _norm(f.get("label")) == want:
            return f
    crit = stems(criterion)
    for f in facts:
        if crit & stems(f.get("label")):
            return f
    return None


def status(value) -> tuple[str, str]:
    """`(yes|no|unknown, source)` of a fact value. Only a value that OPENS with yes/no commits; the rest of it is
    where it was seen. «Automatic (not confirmed on the deal page)» commits to nothing, so it reads unknown."""
    v = _norm(value)
    m = re.match(r"[a-z]+", v)
    first = m.group(0) if m else ""
    rest = _SOURCE_SPLIT_RE.split(str(value or "").strip(), maxsplit=1)
    source = rest[1].strip(" )") if len(rest) > 1 else ""
    if v.startswith(UNKNOWN) or not first:
        return UNVERIFIED, ""
    if first in _YES_WORDS:
        return YES, source
    if first in _NO_WORDS:
        return NO, source
    return UNVERIFIED, ""


def stamp(data: dict) -> int:
    """Give every row one fact per hard criterion it does not carry yet (value «?»). Returns how many
    (row, criterion) pairs are still not verified — stamped now or already «?»."""
    hard = hard_of(data)
    if not hard:
        return 0
    open_pairs = 0
    for item in (data.get("items") or []):
        if not isinstance(item, dict):
            continue
        facts = [f for f in (item.get("facts") or []) if isinstance(f, dict)]
        for crit in hard:
            f = fact_for({"facts": facts}, crit)
            if f is None:
                if len(facts) >= _MAX_FACTS:
                    open_pairs += 1
                    continue
                facts.append({"label": crit[:120], "value": UNKNOWN})
                open_pairs += 1
            elif status(f.get("value"))[0] == UNVERIFIED:
                open_pairs += 1
        item["facts"] = facts
    return open_pairs


def merge_into(items: list, incoming: dict) -> bool:
    """A row sent again (same title+url) carries what the worker verified: its facts replace the stored ones
    by label, and a «?» never overwrites a yes/no. True when something changed."""
    key = ((incoming or {}).get("title"), (incoming or {}).get("url"))
    new_facts = [f for f in ((incoming or {}).get("facts") or []) if isinstance(f, dict) and f.get("label")]
    if not new_facts:
        return False
    for item in items or []:
        if (item.get("title"), item.get("url")) != key:
            continue
        facts = [f for f in (item.get("facts") or []) if isinstance(f, dict)]
        changed = False
        for nf in new_facts:
            old = next((f for f in facts if _norm(f.get("label")) == _norm(nf.get("label"))), None)
            if old is None:
                facts.append(dict(nf))
                changed = True
            elif status(nf.get("value"))[0] != UNVERIFIED or status(old.get("value"))[0] == UNVERIFIED:
                if old.get("value") != nf.get("value"):
                    old["value"] = nf.get("value")
                    changed = True
        item["facts"] = facts[:_MAX_FACTS]
        return changed
    return False


def file(data: dict, extra: dict) -> None:
    """Stamp the rows and, when some are still «?», tell the worker in the action's reply."""
    open_pairs = stamp(data)
    if not open_pairs:
        return
    hard = hard_of(data)
    extra["hard_unverified"] = open_pairs
    extra["note_for_worker"] = (extra.get("note_for_worker", "") + (
        f" {open_pairs} row×requirement pairs still say «?» for: " + " · ".join(f"«{h}»" for h in hard)
        + ". Check each on its listing (`visit <url>`) and send the row again with `append` and "
        "facts {\"<requirement>\": \"yes — <where you saw it>\"} or \"no — …\"; one you could not check keeps «?». "
        "Never present a «?» row as meeting it.")).strip()


def worker_block() -> str:
    """The lines a worker filling a results sheet reads: declare his hard requirements, then answer them per row."""
    return ("HIS HARD REQUIREMENTS ARE COLUMNS. Before the first row, write the requirements he stated as "
            "must-haves (a feature, a place, a date — in his words, one short line each) with "
            "`python -m nucleo.widget_cli data results criteria @crit.json` → {\"hard\": [\"…\", \"…\"]}. Every row "
            "on the sheet then carries one fact per requirement, «?» until you check it on the listing; set it to "
            "«yes — <where you saw it>» or «no — <where>». A row nobody checked is not a row that meets it, and "
            "when he asks about one, the turn reads exactly that fact.")
