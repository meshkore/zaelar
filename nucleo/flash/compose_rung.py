"""nucleo/flash/compose_rung.py — a text the model can WRITE is written in one request, not by a Brain Worker.

Demo 2026-10-22: «write me a one page summary of the bitcoin whitepaper, in a document». The brief named the
`documento` card at 1.00 and the commission pass with the card in front (`act_repair.call_or_read_for_commission`)
was capped at 300 tokens — a page can never fit in a tool argument that size — so it called nothing and the errand
went to a worker: 5.5 minutes and $0.52 for what one request writes in seconds.

The decision stays the model's, with the card in front: the pass is offered one more tool, `compose_into_card`, for
a card that declares an action taking prose (`title` + `body` in its payload). It takes it only when the text can be
written from what it knows, with nothing to look up. Then the composition runs in the background as ONE request with
room for a page, lands through the card's own declared action, and the operator is told it is on screen. Anything
that goes wrong hands the commission to the worker exactly as before — the worst case is today's path.
"""
from __future__ import annotations

import asyncio
import re

from loguru import logger

TOOL_NAME = "compose_into_card"
#: Room for the document he asked for — generous on purpose (operator, 2026-10-22: a limit that clips the result
#: harms the agent). The length is his to set in his words; this only keeps one request from running forever.
MAX_TOKENS = 8000
TIMEOUT_S = 180.0

_SYS = (
    "Write the document the operator asked for, in Markdown: short headings and short paragraphs, no title line (the "
    "title is set apart). Base it on the SOURCE NOTES when there are any, and on what you know; keep to the length he "
    "asked for — «one page» is about 500 words. Write only what you are sure of; if a detail is in neither the notes "
    "nor what you are sure of, leave it out rather than guess. Write it in {lang}."
)
#: V2-831 T-26 — the ONE look-up a single-source text gets, through the search service (`search.find`). Bounded: a
#: slow source never holds the page back — the text is then written from what the model knows, as before.
SOURCE_TIMEOUT_S = 12.0


def prose_action(widget_id: str) -> str:
    """The declared action of this card that puts a whole written text on it (`title` + `body`), or ""."""
    try:
        from widgets import runtime as _rt
        actions = (_rt.get(str(widget_id or "").split("::", 1)[0]) or {}).get("actions") or {}
        for name, spec in actions.items():
            pl = spec.get("payload") if isinstance(spec, dict) else None
            if isinstance(pl, dict) and "body" in pl and "title" in pl:
                return str(name)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"compose_rung: no prose action read for {widget_id}: {e}")
    return ""


def tool() -> dict:
    """The function the commission pass may call instead of handing the text to a worker."""
    return {"type": "function", "function": {
        "name": TOOL_NAME,
        "description": ("Write this card's text yourself, now, in one go: a text written from what you know or from "
                        "ONE known source — summarise, explain or translate a named work, page or file; an "
                        "explainer, a letter, a draft. The engine looks that one source up for you. NOT for research "
                        "across several sources, comparisons or a hunt: that stays with the worker."),
        "parameters": {"type": "object", "properties": {
            "widget_id": {"type": "string"},
            "title": {"type": "string", "description": "the document's title, in the operator's language"},
            "brief": {"type": "string", "description": "what to write, in one line, with the length he asked"}},
            "required": ["widget_id", "title", "brief"]}}}


def decision(name: str, args: dict, wid: str) -> dict | None:
    """The pass's `compose_into_card` call as the commission's decision, or None."""
    if name != TOOL_NAME or str(args.get("widget_id") or "").strip().lower() != wid:
        return None
    action = prose_action(wid)
    title = " ".join(str(args.get("title") or "").split())[:120]
    if not action or not title:
        return None
    return {"kind": "compose", "widget_id": wid, "action": action, "title": title,
            "brief": " ".join(str(args.get("brief") or "").split())[:300]}


async def compose(got: dict, operator_text: str, spec, window=None) -> str:
    """The text, from ONE request with room for it. "" on any failure."""
    from nucleo.flash import act_repair as _ar, second_pass as _sp
    from nucleo.turn.prompt import builder as _prompt
    try:
        from i18n import langs as _langs
        lang = _langs.current_language().name
    except Exception:  # noqa: BLE001
        lang = "the operator's language"
    sys2 = _prompt._lang_lock() + "\n" + _SYS.format(lang=lang)
    user = (f"Operator: «{(operator_text or '').strip()[:400]}»\nDocument: «{got['title']}» — {got.get('brief', '')}"
            + await _source_notes(f"{got['title']} {got.get('brief', '')}".strip()) + _ar.conversation(window))
    raw = await asyncio.wait_for(_sp.collect(sys2, user, spec, max_tokens=MAX_TOKENS), timeout=TIMEOUT_S)
    return re.sub(r"\[\[[^\]]*\]\]", "", str(raw or "")).strip()


async def _source_notes(query: str) -> str:
    """What the search service says about the ONE source this text is written from, as a prompt block, or ""."""
    try:
        from search import find
        from search.result import INLINE_FACT
        res = await asyncio.wait_for(asyncio.to_thread(find, query, route=INLINE_FACT, k=4), timeout=SOURCE_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001 — no notes is the old path, written from what the model knows
        logger.info(f"compose_rung: no source notes for «{query[:80]}» — {type(e).__name__}: {e}")
        return ""
    urls = [p.url for p in (res.pages or [])][:4] + [getattr(s, "url", "") for s in (res.sources or [])][:4]
    if not (res.answer or "").strip():
        return ""
    return (f"\n\nSOURCE NOTES (looked up for this document, {res.provider or 'web'}):\n{res.answer.strip()[:6000]}"
            + (f"\nSources: {', '.join(u for u in urls if u)}" if any(urls) else ""))


async def run(got: dict, *, commission: str, operator_text: str, spec, window=None, emit=None) -> bool:
    """Compose, put it on the card through its declared action, and say so. On any failure the commission goes to the
    worker, as it would have without this rung. Returns whether the card got the text. Never raises."""
    _emit = emit or (lambda *a, **k: None)
    body = ""
    try:
        body = await compose(got, operator_text, spec, window)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"compose_rung: composition failed — {type(e).__name__}: {e}")
    if not body:                             # nothing came back: the worker it was going to
        _emit("brain", "✍️ redacción directa fallida — el encargo vuelve al worker", role="system",
              text=got.get("title", ""), extra={"cat": "flash", "chars": len(body)})
        return _to_the_worker(commission, operator_text)
    try:
        from nucleo.flash import canvas_visibility as _cvis, data_ops as _ops
        wid, action = got["widget_id"], got["action"]
        _cvis.present(wid, reason="turn-order", src="flash", emit=_emit, text=operator_text)
        res = await _ops.dispatch_and_report(wid, action, {"title": got["title"], "body": body}, text=operator_text)
        if isinstance(res, dict) and res.get("ok") is False:
            raise RuntimeError(str(res.get("error") or res)[:200])
        _emit("brain", "✍️ redactado en una sola petición en vez de un worker", role="system",
              text=f"{wid}:{action} «{got['title']}» ({len(body)} chars)",
              extra={"cat": "flash", "widget": wid, "action": action, "chars": len(body)})
        await _tell(got["title"])
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"compose_rung: the card refused the text — {type(e).__name__}: {e}")
        _emit("brain", "✍️ la tarjeta no aceptó el texto — el encargo vuelve al worker", role="system",
              text=str(e)[:160], extra={"cat": "flash"})
        return _to_the_worker(commission, operator_text)


async def _tell(title: str) -> None:
    try:
        from i18n import langs as _langs
        from voice import proactive
        line = str(getattr(_langs.current_language(), "composed_on_screen", "") or "").format(title=title)
        if line:
            await proactive.notify("zaelar", line, about="document")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"compose_rung: the ready line was not said: {e}")


def _to_the_worker(commission: str, operator_text: str) -> bool:
    try:
        from nucleo.acts import errand as escalate
        escalate.escalate_to_slowbrain(commission or operator_text, context={"src": "compose_rung"})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"compose_rung: the fallback escalation failed too: {e}")
    return False
