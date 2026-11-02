"""nucleo/circuit/breadth.py — did the search LOOK ENOUGH? The brief's own target is part of the end state (V2-840 H2).

A car search (2026-11-02) swept ONE portal, kept 15 ads, said «short market» and was judged met because its end state
was only `results.empty = false`: one row satisfied it, and the brief's `breadth.min_candidates` — the number the
composer had reasoned for that market — was measured by nothing.

There is no number here. The TARGET is the brief's (`breadth.min_candidates`, `deliverable.n_final`, `sources`); the
PROGRESS is the sheet's (`summary.explored`, the rows, the pool, the rejected, the `sources` the worker reported).
When the progress is short of the target, ONE model question decides — brief + progress + sources used →
`{enough, why, next, more_sources}`:

  · `enough: false` → the circuit runs ONE more bounded round of the SAME errand (`close`, the retry budget the
    operator set in genesis `circuit.retries`), carrying `next` so it starts from the gap, not from zero;
  · `enough: true` (a small market, walls) → the errand delivers, and `why` is written on the sheet's summary;
  · the model fails → deliver anyway and say «not judged». Delivery is never blocked here.

`judge` is async (a model call) and runs in the worker's ending before the circuit's synchronous `close`, which only
reads `rec.breadth`.
"""
from __future__ import annotations

import asyncio
import json
import re

from loguru import logger

JUDGE_TIMEOUT_S = 25.0      # a bound on the wait, not on the search: past it, the errand delivers «not judged»


def brief_of(rec) -> dict | None:
    """The errand's brief: saved under the worker's key, and under the commission's durable id once judged here."""
    try:
        from nucleo.workers import brief as _brief
        for key in (getattr(rec, "task_id", ""), getattr(rec, "uid", "")):
            if key and (b := _brief.load(key)):
                return b
    except Exception as e:  # noqa: BLE001
        logger.debug(f"breadth: brief unreadable: {e!r}")
    return None


def target(brief: dict | None) -> dict:
    """What the composer declared — never a number of ours. Empty when there is no brief."""
    if not isinstance(brief, dict) or not brief.get("goal"):
        return {}
    b, d = brief.get("breadth") or {}, brief.get("deliverable") or {}
    return {"min_candidates": int(b.get("min_candidates") or 0), "n_final": int(d.get("n_final") or 0),
            "sources": list(brief.get("sources") or []), "market": dict(brief.get("market") or {})}


def progress(sheet: str, considered: int = -1) -> dict:
    """What the sheet shows the worker did: explored, rows kept, and every source it reported with its state."""
    try:
        from widgets.results import data as _sheet
        data = _sheet.view_data(sheet)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"breadth: sheet unreadable: {e!r}")
        return {}
    rows = len(data.get("items") or [])
    held = rows + len(data.get("pool") or []) + len(data.get("rejected") or [])
    explored = max(int((data.get("summary") or {}).get("explored") or 0), int(considered or 0), held)
    srcs = [{k: s.get(k) for k in ("name", "url", "status", "found") if s.get(k) not in (None, "")}
            for s in data.get("sources") or [] if isinstance(s, dict)]
    return {"explored": explored, "rows": rows, "sources": srcs,
            "state": str((data.get("summary") or {}).get("state") or "")}


def short(tgt: dict, prog: dict) -> bool:
    """Is the progress below the brief's own target? Compared only against numbers the composer declared."""
    if not tgt or not prog:
        return False
    minc, nfin = tgt.get("min_candidates") or 0, tgt.get("n_final") or 0
    return bool((minc and prog.get("explored", 0) < minc) or (nfin and prog.get("rows", 0) < nfin))


def messages(brief: dict, tgt: dict, prog: dict) -> list[dict]:
    return [
        {"role": "system", "content": (
            "You audit a research errand a personal assistant just finished. Its brief set a target for how many "
            "candidates had to be evaluated and delivered, and which sources a local expert would use; the progress "
            "is short of that target. Decide whether what was done is ENOUGH to defend the selection in this domain "
            "and market — a small or rare market, or sources that walled the search off, can make a shortfall "
            "legitimate; one source swept when the market has several, or a search that stopped early, cannot. "
            "Also decide whether MORE SOURCES are needed. Return ONLY a JSON object: "
            '{"enough": true|false, "why": "one sentence, in the language of the request", '
            '"next": "what the next round must do, concretely (empty when enough)", '
            '"more_sources": ["sources to try next, in that market (empty when none)"]}')},
        {"role": "user", "content": json.dumps({
            "request": str(brief.get("request") or "")[:600], "goal": str(brief.get("goal") or "")[:400],
            "domain": brief.get("domain") or "", "hard": list(brief.get("hard") or [])[:8],
            "target": tgt, "progress": prog}, ensure_ascii=False)[:4000]},
    ]


def parse(raw) -> dict | None:
    m = re.search(r"\{.*\}", str(raw or ""), re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(got, dict) or not isinstance(got.get("enough"), bool):
        return None
    return {"judged": True, "enough": got["enough"], "why": str(got.get("why") or "").strip()[:300],
            "next": str(got.get("next") or "").strip()[:400],
            "more_sources": [str(x)[:80] for x in (got.get("more_sources") or []) if str(x or "").strip()][:8]}


async def _ask(msgs: list[dict], timeout: float) -> str:
    from nucleo.llm.fast_client import FastClient
    from nucleo.workers import brief as _brief
    spec, _tier = _brief._spec()          # the composer's chain: the same reasoning that set the target judges it
    if spec is None:
        raise RuntimeError("no provider")
    return await asyncio.wait_for(FastClient().complete(msgs, spec=spec, max_tokens=500, no_thinking=True),
                                  timeout=timeout)


async def judge(rec, *, timeout: float = JUDGE_TIMEOUT_S) -> dict | None:
    """Set and return `rec.breadth`: None when there is nothing to judge (no brief, no sheet, cancelled), a judged
    verdict when the progress was short, `{"judged": False}` when the model could not answer. Never raises."""
    try:
        if getattr(rec, "status", "") == "cancelled" or getattr(rec, "handoff", ""):
            return None
        sheet = str(getattr(rec, "sheet", "") or "")
        brief = brief_of(rec)
        tgt = target(brief)
        if not tgt or not sheet:
            return None
        _keep(rec, brief)
        prog = progress(sheet, int(getattr(rec, "considered", -1) or -1))
        if not short(tgt, prog):
            out = {"judged": False, "enough": True, "short": False, "target": tgt, "progress": prog}
        else:
            try:
                got = parse(await _ask(messages(brief, tgt, prog), timeout))
            except Exception as e:  # noqa: BLE001 — a judge that fails never holds the delivery back
                logger.info(f"breadth: not judged ({type(e).__name__}: {str(e)[:80]})")
                got = None
            out = {**(got or {"judged": False, "enough": True}), "short": True, "target": tgt, "progress": prog}
        rec.breadth = out
        _event(rec, out)
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug(f"breadth: judge skipped: {e!r}")
        return None


def _keep(rec, brief: dict) -> None:
    """The brief under the commission's durable id too, so a continuation or a reopen (`reopen.py`) finds it."""
    uid = str(getattr(rec, "uid", "") or "")
    if uid and uid != str(getattr(rec, "task_id", "") or ""):
        try:
            from nucleo.workers import brief as _brief
            _brief.save(uid, brief)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"breadth: brief not kept under {uid}: {e!r}")


def another_round(rec) -> str:
    """The gap a further round must close ("" = none): the model said NOT enough. Read by `close`."""
    b = getattr(rec, "breadth", None) or {}
    if not (b.get("short") and b.get("judged") and b.get("enough") is False):
        return ""
    tgt, prog = b.get("target") or {}, b.get("progress") or {}
    used = ", ".join(str(s.get("name") or s.get("url")) for s in prog.get("sources") or [])[:300] or "—"
    more = "; ".join(b.get("more_sources") or [])
    return (f"la búsqueda se quedó corta frente a su propio objetivo (evaluados {prog.get('explored', 0)} de "
            f"{tgt.get('min_candidates') or '?'}, entregados {prog.get('rows', 0)} de {tgt.get('n_final') or '?'}; "
            f"fuentes usadas: {used}). {b.get('why') or ''} Siguiente: {b.get('next') or 'amplía'}"
            + (f" Fuentes por probar: {more}." if more else ""))


def note_delivery(rec) -> None:
    """A short delivery is SAID on the sheet's summary: the reason the model gave, or that it was not judged."""
    b = getattr(rec, "breadth", None) or {}
    if not b.get("short"):
        return
    why = b.get("why") if b.get("judged") else ""
    note = why or _not_judged_line()
    try:
        from widgets.results import data as _sheet
        _sheet.apply_action("progress", {"sheet": str(getattr(rec, "sheet", "") or ""), "note": note})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"breadth: note not written: {e!r}")


def _not_judged_line() -> str:
    default = "Breadth not judged: the selection is delivered as found."
    try:
        from widgets.results import data as _sheet
        return _sheet.note_text("breadth_not_judged", default)
    except Exception:  # noqa: BLE001
        return default


def _event(rec, out: dict) -> None:
    try:
        from voice.observer import emit
        label = ("📏 breadth: met its target" if not out.get("short") else
                 "📏 breadth: short — judged enough" if out.get("judged") and out.get("enough") else
                 "📏 breadth: short — another round" if out.get("judged") else "📏 breadth: short — not judged")
        emit("task", label, role="system", text=str(out.get("why") or "")[:200],
             extra={"id": str(getattr(rec, "task_id", "") or ""), "uid": str(getattr(rec, "uid", "") or ""),
                    "cat": "circuit", "target": out.get("target"), "progress": {
                        k: (out.get("progress") or {}).get(k) for k in ("explored", "rows")},
                    "sources": len((out.get("progress") or {}).get("sources") or []),
                    "next": str(out.get("next") or "")[:200] or None})
    except Exception:  # noqa: BLE001
        pass
