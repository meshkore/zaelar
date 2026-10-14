"""The FIRST backed rows of an errand he asked to be told about are said to him once, unprompted (V2-782).

Measured 2026-10-14 on the text channel: search-buy-boat-multicountry — five Lagoon 440 rows landed on the errand's
sheet 34 s after his last turn («ok, just lmk when something lands»); find-kid-friendly-activities — 18 s after.
The worker was still running, so its end-of-work delivery (`workers/session._deliver`) had not fired, and the turn
backstop (`flash/delivery`) only rides a reply: with no further turn, nothing reached him.

The sheet's door (`widgets/results/actions`, every route ends there) calls `landed` after it saved. The notice is
owed when ALL hold:
  · the sheet belongs to a LIVE errand and now holds rows backed by a link or a source;
  · this errand was never noticed before (one per errand, never repeated);
  · he asked to be told («avísame», «keep me posted») or we promised to tell him («te aviso», «I'll flag it») since
    the errand started — the cues are language DATA (`LangSpec.tell_me_cues` / `tell_you_cues`);
  · no turn is in flight (a turn that is running gets the rows from its own backstop — we wait for it to end, then
    ask whether its reply already named them).
It goes through `voice.proactive.notify` — spoken with a live voice session after the queue and the quiet wait,
the chat wall plus a note for the next turn otherwise — and waits out a stop's hush first.
"""
from __future__ import annotations

import asyncio
import threading
import time
import unicodedata

#: errand id → when its first rows were noticed (or found already said). Bounded by the process's errands.
_TOLD: dict[str, float] = {}
#: errand ids with a check already scheduled: two appends a second apart must not race two notices.
_PENDING: set[str] = set()
_LOCK = threading.Lock()
_POLL_S = 1.0
_MAX_WAIT_S = 120.0
_MAX_ROWS = 3


def _norm(text) -> str:
    s = unicodedata.normalize("NFKD", str(text or "").lower().replace("’", "'"))
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def _bare(sheet) -> str:
    return str(sheet or "").strip().removeprefix("results::")


def backed(items) -> list[dict]:
    """The rows a link or a source backs, in the sheet's order."""
    return [i for i in (items or []) if isinstance(i, dict) and str(i.get("title") or "").strip()
            and (str(i.get("url") or "").strip() or str(i.get("source") or "").strip())]


def lines(events) -> list[tuple[float, str, str]]:
    """(t_ms, role, text) of the conversation, from the observer ring: the voice transcripts and the text channel's
    wall lines alike."""
    out = []
    for e in events or []:
        if not isinstance(e, dict) or e.get("role") not in ("user", "assistant") or not str(e.get("text") or "").strip():
            continue
        if e.get("kind") == "transcript" or (e.get("kind") == "brain" and e.get("wall")):
            out.append((float(e.get("t_ms") or 0), str(e["role"]), str(e["text"])))
    return out


def in_flight(convo) -> bool:
    """His last line has no reply yet."""
    last = {r: t for t, r, _ in convo}
    return last.get("user", 0.0) > last.get("assistant", 0.0)


def _cues(field: str) -> list[str]:
    from i18n import langs
    return sorted({_norm(c) for sp in langs.supported() for c in (getattr(sp, field, ()) or ()) if c})


def asked_to_be_told(convo, since_ms: float) -> bool:
    """He asked to be told, or we promised to tell him, since the errand started."""
    mine, ours = _cues("tell_me_cues"), _cues("tell_you_cues")
    for t, role, text in convo:
        if t < since_ms:
            continue
        n = _norm(text)
        if any(c in n for c in (mine if role == "user" else ours)):
            return True
    return False


def already_said(rows, convo, since_ms: float, errand_words: str) -> bool:
    """A reply since the errand started named one of these rows (a distinctive title word: a digit, or ≥5 letters
    not in the errand's own words)."""
    said = " ".join(_norm(x) for t, r, x in convo if r == "assistant" and t >= since_ms)
    common = set(_norm(errand_words).split())
    for row in rows:
        toks = [w for w in _norm(row.get("title")).split()
                if (any(c.isdigit() for c in w) or len(w) >= 5) and w not in common]
        if any(f" {w} " in f" {said} " for w in toks):
            return True
    return False


def line(title: str, rows) -> str:
    """The sentence, in his language, naming the best ≤3 rows («title — price»)."""
    from i18n import langs
    named = "; ".join(str(r.get("title")).strip() + (f" — {str(r.get('price')).strip()}" if r.get("price") else "")
                      for r in rows[:_MAX_ROWS])
    return langs.current_language().first_rows_notice.format(title=str(title or "").strip(), rows=named)


def decide(sheet: str, data: dict, *, errand: dict | None, events, now_ms: float) -> tuple[str, str]:
    """(sentence, "") when the notice is owed now, else ("", why not). `why` = "in flight" asks the caller to wait."""
    rows = backed((data or {}).get("items"))
    if not errand:
        return "", "no live errand"
    if str(errand.get("id")) in _TOLD:
        return "", "already noticed"
    if not rows:
        return "", "no backed rows"
    convo = lines(events)
    if in_flight(convo):
        return "", "in flight"
    from nucleo.flash import asked_fact_hold as _hold   # never a row that lacks what he asked about (vinyl, 10-14)
    if not (rows := _hold.items_owed(str(errand.get("request") or ""), rows, [t for _ts, r, t in convo if r == "user"])):
        return "", "rows lack what he asked about"
    since = now_ms - 1000.0 * float(errand.get("secs") or 0)
    words = f"{errand.get('request') or ''} {(data or {}).get('title') or ''}"
    if already_said(rows[:_MAX_ROWS], convo, since, words):
        _TOLD[str(errand["id"])] = time.time()
        return "", "already said"
    if not asked_to_be_told(convo, since):
        return "", "not asked"
    return line(str((data or {}).get("title") or errand.get("request") or ""), rows), ""


def _errand_of(sheet: str) -> dict | None:
    from nucleo import dispatch
    return next((t for t in dispatch.pending_summaries() or [] if _bare(t.get("sheet")) == _bare(sheet)), None)


async def _run(sheet: str, errand_id: str) -> bool:
    try:
        return await _check(sheet)
    except Exception as e:  # noqa: BLE001 — a notice that fails is logged, and the turn backstop still delivers
        from loguru import logger
        logger.warning(f"first_rows_notice: check failed for {sheet} — {type(e).__name__}: {e}")
        return False
    finally:
        with _LOCK:
            _PENDING.discard(errand_id)


async def _check(sheet: str) -> bool:
    from voice import observer, proactive
    from widgets.results import data as sheet_data
    waited = 0.0
    while True:
        errand = _errand_of(sheet)
        said, why = decide(sheet, sheet_data.view_data(sheet), errand=errand,
                           events=observer.debug_events(), now_ms=observer.now_ms())
        if why not in ("in flight",) and not (said and proactive.hushed()):
            break
        if waited >= _MAX_WAIT_S:
            return False
        await asyncio.sleep(_POLL_S)
        waited += _POLL_S
    if not said:
        return False
    _TOLD[str(errand["id"])] = time.time()
    observer.emit("widget", "🔔 first rows of the errand, told unprompted", role="system", text=said[:200],
                  extra={"id": f"results::{_bare(sheet)}", "errand": str(errand["id"])})
    await proactive.notify("zaelar", said, speak=True, key=f"first_rows:{errand['id']}")
    return True


def landed(sheet: str, items) -> bool:
    """The sheet's door saved rows. Schedules the check off the door's thread. True when scheduled. Never raises."""
    if not _bare(sheet) or not backed(items):
        return False                      # the default sheet belongs to no errand
    try:
        errand = _errand_of(sheet)
        eid = str((errand or {}).get("id") or "")
        with _LOCK:
            if not eid or eid in _TOLD or eid in _PENDING:
                return False
            _PENDING.add(eid)
        threading.Thread(target=asyncio.run, args=(_run(str(sheet), eid),), daemon=True,
                         name="first-rows-notice").start()
        return True
    except Exception as e:  # noqa: BLE001 — a notice that cannot be scheduled never blocks the sheet
        with _LOCK:
            _PENDING.discard(locals().get("eid", ""))
        from loguru import logger
        logger.warning(f"first_rows_notice: not scheduled for {sheet} — {type(e).__name__}: {e}")
        return False


def forget() -> None:
    _TOLD.clear()
    _PENDING.clear()
