"""nucleo/source_outcomes.py — what each external SOURCE did the last times a worker used it (V2-798).

    python -m nucleo.source_outcomes          # the fresh facts, newest first (JSON)
    python -m nucleo.source_outcomes --all    # including the ones that already expired

## The class this closes

Every Brain Worker started from zero. A site that answered 403 to yesterday's errand was opened again today, a
network agent that timed out twice was asked a third time, a page whose text could not be extracted was driven
for minutes before the worker gave up on it — and the same worker, on the next errand, paid it all again. The
facts were all observed (the wall detector, the extract counter, the provider's 429, the mesh timeout); none of
them outlived the process that saw it.

## What it is

A small durable table keyed by SOURCE — a site host, a network agent id, a search provider — holding, per
outcome, when it was last seen, how many times, and a short detail. Written at the doors that already observe
the fact (`cli.nav` for walls and extracts, `mesh_agents.ask` for agent answers, `providers.note_tool_blindness`
for a search provider out of quota). Read back as ONE compact line in the worker's step 0 and through the CLI
above.

## What it is NOT

Not a routing table and not a list of where to go. It states what HAPPENED, with a date; the worker decides.
Every negative fact expires on its own clock — a site that unblocks is retried — and a later success replaces
an earlier failure. That is the difference between a resource and a fence (brain-worker doctrine §5).

Fail-soft everywhere: no memory, no table, no line. Nothing here may break the door that calls it.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse

from loguru import logger

_KV = "sources:outcomes"

# The outcomes a door can report. Positive first; the rest are reasons to try something else FIRST, never bans.
SERVED = "served"            # the source gave usable rows
WALL = "wall"                # 403 / CAPTCHA / login wall / anti-bot page
EXTRACT_EMPTY = "extract_empty"  # the page loaded and `extract` found no named row on it
QUOTA = "quota"              # a provider said its quota is exhausted (429)
TIMEOUT = "timeout"          # a network agent did not answer within its timeout
EMPTY = "empty"              # a network agent answered 200 with zero rows

_NEGATIVE = (WALL, EXTRACT_EMPTY, QUOTA, TIMEOUT, EMPTY)
#: The failures that say the SOURCE could not serve at all, whatever was asked. An empty answer or an empty page
#: depends on the QUERY (a radius too small, a search with no results) and must not demote the source for the next one.
_FAILING = (WALL, QUOTA, TIMEOUT)

_H = 3600
#: How long one sighting stays a fact. Negative facts are short on purpose: the outside world changes (a site
#: lifts its block, an agent is redeployed) and a stale «it blocks us» would become exactly the fence §5 forbids.
#: A repeated failure lives longer (×n, up to ×3): one 403 can be a bad minute, three are a policy.
_TTL_S = {SERVED: 14 * 24 * _H, WALL: 3 * 24 * _H, EXTRACT_EMPTY: 2 * 24 * _H, QUOTA: 12 * _H,
          TIMEOUT: 24 * _H, EMPTY: 24 * _H}
_REPEAT_CAP = 3
#: The same fact reported again within this window is the same sighting (a wall stays on screen across several
#: actions on one page) — it refreshes the date and does not inflate the count.
_SAME_SIGHTING_S = 120
_MAX_SOURCES = 150
_DETAIL_MAX = 120

#: How the worker line names each outcome. Prompt text the worker reads, so it follows the worker prompt's language.
_SAY = {SERVED: "funcionó", WALL: "bloqueó", EXTRACT_EMPTY: "extract sin filas", QUOTA: "sin cuota",
        TIMEOUT: "no contestó a tiempo", EMPTY: "contestó vacío"}
_LINE_ITEMS = 6


def source_of_url(url: str) -> str:
    """A page's source is its host without `www.` — the unit a block applies to."""
    try:
        host = (urllib.parse.urlparse(str(url or "")).hostname or "").lower()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"source_outcomes: unparseable url {url!r}: {e}")
        return ""
    return host[4:] if host.startswith("www.") else host


def _load() -> dict:
    try:
        from memory import api as memory
        got = memory.kv_get(_KV, {}) or {}
        return got if isinstance(got, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"source_outcomes: record not readable: {e}")
        return {}


def _save(table: dict) -> None:
    try:
        from memory import api as memory
        memory.kv_set(_KV, table)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"source_outcomes: record not written: {e}")


def note(source: str, outcome: str, *, kind: str = "site", detail: str = "", errand: str = "",
         until: float = 0.0, now: float | None = None) -> None:
    """Record that `source` produced `outcome`. Called by the door that OBSERVED it — never on a guess."""
    source = str(source or "").strip().lower()
    if not source or outcome not in _TTL_S:
        return
    now = time.time() if now is None else now
    table = _load()
    row = table.get(source) if isinstance(table.get(source), dict) else {}
    seen = row.setdefault("seen", {})
    prev = seen.get(outcome) if isinstance(seen.get(outcome), dict) else {}
    same = prev and (now - float(prev.get("at") or 0)) < _SAME_SIGHTING_S
    seen[outcome] = {"at": now, "n": int(prev.get("n") or 0) + (0 if same else 1),
                     "detail": str(detail or prev.get("detail") or "")[:_DETAIL_MAX],
                     "errand": str(errand or prev.get("errand") or "")[:40],
                     **({"until": float(until)} if until else {})}
    if outcome == SERVED:
        # A success after a failure is the newer truth: the failures stop counting as repeats.
        for neg in _NEGATIVE:
            if isinstance(seen.get(neg), dict):
                seen[neg]["n"] = min(int(seen[neg].get("n") or 1), 1)
    row["kind"] = str(kind or row.get("kind") or "site")
    table[source] = row
    if len(table) > _MAX_SOURCES:
        newest = sorted(table, key=lambda s: _last_at(table[s]), reverse=True)[:_MAX_SOURCES]
        table = {s: table[s] for s in newest}
    _save(table)


def _last_at(row: dict) -> float:
    return max((float((v or {}).get("at") or 0) for v in (row.get("seen") or {}).values()), default=0.0)


def _expires_at(outcome: str, rec: dict) -> float:
    if outcome == QUOTA and float(rec.get("until") or 0) > 0:
        return float(rec["until"])            # the provider said when it comes back; believe it
    ttl = _TTL_S.get(outcome, 0)
    if outcome in _NEGATIVE:
        ttl *= max(1, min(int(rec.get("n") or 1), _REPEAT_CAP))
    return float(rec.get("at") or 0) + ttl


def verdict(source: str, now: float | None = None) -> dict | None:
    """The NEWEST fresh outcome for this source, or None when nothing current is known (= try it)."""
    row = _load().get(str(source or "").strip().lower())
    return _verdict_of(str(source or ""), row, time.time() if now is None else now)


def _verdict_of(source: str, row, now: float) -> dict | None:
    if not isinstance(row, dict):
        return None
    fresh = [(o, r) for o, r in (row.get("seen") or {}).items()
             if isinstance(r, dict) and o in _TTL_S and _expires_at(o, r) > now]
    if not fresh:
        return None
    outcome, rec = max(fresh, key=lambda x: float(x[1].get("at") or 0))
    return {"source": source, "kind": row.get("kind") or "site", "outcome": outcome,
            "at": float(rec.get("at") or 0), "n": int(rec.get("n") or 1), "detail": rec.get("detail") or "",
            "errand": rec.get("errand") or "", "expires_at": _expires_at(outcome, rec)}


def is_failing(source: str, now: float | None = None) -> bool:
    """True when the newest current fact says this source could not serve at all. Used to ORDER, never to drop."""
    v = verdict(source, now)
    return bool(v and v["outcome"] in _FAILING)


def facts(now: float | None = None, *, include_stale: bool = False) -> list[dict]:
    """Every source with a current verdict, newest first. `include_stale` adds the expired ones (for the CLI)."""
    now = time.time() if now is None else now
    out = []
    for source, row in _load().items():
        v = _verdict_of(source, row, now)
        if v is None and include_stale and isinstance(row, dict):
            v = _verdict_of(source, row, 0.0)
            if v:
                v["stale"] = True
        if v:
            out.append(v)
    return sorted(out, key=lambda v: v["at"], reverse=True)


def _day(ts: float) -> str:
    return time.strftime("%d/%m", time.localtime(ts)) if ts else "?"


def worker_line(py: str = "python", now: float | None = None) -> str:
    """ONE line for the worker's step 0 — or "" when nothing current is known (an empty table costs nothing)."""
    try:
        items = facts(now)[:_LINE_ITEMS]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"source_outcomes: no worker line: {e}")
        return ""
    if not items:
        return ""
    parts = []
    for v in items:
        when = (f"hasta {_day(v['expires_at'])}" if v["outcome"] == QUOTA else _day(v["at"]))
        rep = f", {v['n']}×" if v["n"] > 1 else ""
        parts.append(f"{v['source']} {_SAY[v['outcome']]} ({when}{rep})")
    return ("   · VISTO EN ENCARGOS ANTERIORES (hechos con fecha que caducan solos, no una lista de dónde ir): "
            + " · ".join(parts) + f". Detalle: {py} -m nucleo.source_outcomes\n")


def forget(source: str = "") -> None:
    """Drop one source (or everything) — the operator correcting the record, or a test cleaning up."""
    table = _load()
    if source:
        table.pop(str(source).strip().lower(), None)
    else:
        table = {}
    _save(table)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rows = facts(include_stale="--all" in argv)
    for v in rows:
        v["seen"], v["expires"] = _day(v.pop("at")), _day(v.pop("expires_at"))
    print(json.dumps({"ok": True, "sources": rows,
                      "note": "facts with a date, not a list of where to go; each one expires and is retried"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
