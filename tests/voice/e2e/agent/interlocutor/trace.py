"""Frontend/brain/LLM OBSERVABILITY capture — the judge's eyes without watching a screen.

zaelar emits EVERYTHING that matters through one event bus (voice.observer.emit → GET /events SSE):
voice states/transcripts, brain prompts/replies, TTS, per-turn metrics, and — crucially — widget/canvas
actions (kind="widget", e.g. "show:agenda"/"close:clock"), cluster/cron/architect/whatsapp dispatches, and
alerts. This subscribes to that stream and records the events so the judge can VERIFY what actually happened
in the frontend/brain (a widget opened, a [[deep]] escalated, which model answered), not just what zaelar said.

Independent: talks to zaelar only over HTTP SSE. Imports no zaelar code."""
from __future__ import annotations

import asyncio
import json

import aiohttp

from .. import config


class Trace:
    """Subscribes to zaelar's /events SSE in the background and collects events. Slice per scenario with mark()."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        url = f"{config.ZAELAR_URL}/events"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                async for raw in resp.content:
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:].strip())
                    except Exception:
                        continue
                    ev["_at"] = _mono()
                    self.events.append(ev)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # SSE drop / zaelar restart: the trace just stops growing, never crashes the run

    def mark(self) -> int:
        """Return the current index — call before a scenario; slice_from(idx) after to get that scenario's events."""
        return len(self.events)

    def slice_from(self, idx: int) -> list[dict]:
        return self.events[idx:]

    async def aclose(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self._session:
            await self._session.close()


def _mono() -> float:
    return asyncio.get_event_loop().time()


# --- summarizers: turn a raw event slice into what the judge needs to verify frontend/brain behaviour ----------

_WIDGET_KINDS = {"widget"}
_BRAIN_KINDS = {"brain", "alert"}


def frontend_actions(events: list[dict]) -> list[str]:
    """Widget/canvas + connector actions zaelar actually FIRED (the observable frontend effect)."""
    out = []
    for e in events:
        k, lbl = e.get("kind"), e.get("label", "")
        if k in _WIDGET_KINDS:
            wid = e.get("id")  # strip_tags emits ("show"/"close", {"id": <widget>}) → the id is included in the event
            out.append(f"widget:{lbl}:{wid}" if wid else f"widget:{lbl}")
        elif isinstance(lbl, str) and any(lbl.startswith(p) for p in ("cluster.", "cron.", "architect.", "wa.")):
            out.append(f"{k}:{lbl}")
    return out


def zaelar_texts(events: list[dict]) -> list[str]:
    """zaelar's OWN replies from the observability stream — the authoritative record of what zaelar SAID, immune to
    the tester's Deepgram STT dropping zaelar's audio (which caused false timeouts → false all-1s).
    Two reliable sources, NOT interchangeable: (a) `transcript` events (role assistant/bot) — the audio-based
    ground truth, includes any filler phrase spoken before the composed reply; (b) the duo fast layer's reply event
    (`kind=brain`, label '…reply', role=assistant) — emitted for EVERY completed duo turn, but captures ONLY the
    composed text, never a preceding filler. When BOTH fire for the same turn they are NOT byte-identical (the
    transcript is "filler + reply", the brain event is just "reply") — joining both double-counted the reply
    (bug found in the 2026-07-26 audit: every filler-preceded turn showed as "reply … filler … reply" to the
    judge). Fix: prefer transcript (truer to what was actually spoken) and use brain-reply only as a FALLBACK for
    the turns where transcript never fires (conversation_item_added doesn't always fire) — never both at once."""
    transcripts, brain_replies = [], []
    for e in events:
        k, role, lbl = e.get("kind"), e.get("role"), (e.get("label") or "")
        t = (e.get("text") or "").strip()
        if not t:
            continue
        if k == "transcript" and role in ("assistant", "bot"):
            transcripts.append(t)
        elif k == "brain" and role == "assistant" and "reply" in lbl.lower():
            brain_replies.append(t)
    out = []
    for t in (transcripts or brain_replies):
        if not out or out[-1] != t:   # dedup consecutive identical within the chosen source
            out.append(t)
    return out


def brain_trace(events: list[dict]) -> list[str]:
    """Brain/LLM activity: prompts, replies, escalations, model/metrics — for debugging why it did what it did."""
    out = []
    for e in events:
        if e.get("kind") in _BRAIN_KINDS:
            t = (e.get("text") or "")[:120]
            out.append(f"{e.get('label','')}: {t}".strip())
        elif e.get("kind") == "log" and "Metrics" in (e.get("text") or ""):
            out.append(e["text"][:120])
    return out


def summary(events: list[dict]) -> dict:
    """Compact observability summary for the judge + report."""
    from collections import Counter
    return {
        "frontend_actions": frontend_actions(events),
        "brain_trace": brain_trace(events)[:40],
        "event_kinds": dict(Counter(e.get("kind") for e in events)),
        "n_events": len(events),
    }
