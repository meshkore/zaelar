"""nucleo/request/kind.py — WHICH KIND of errand this is: a question of the turn's brief, never a reading of its words.

The kind picks the worker's tools: `web` gets a browser, `code` goes to the card generator (behind the gate that asks
him first, CRIT-C4), `generic` is everything else. It was six regexes and a chain of site and money word tables, each
born of a worker that went off to do what was not asked — «rellena el widget» read as code, «un proyecto» of a
second-hand boat read as a software project, a known site in a question read as navigation. Every one of those was a
reading of the REQUEST, which is what the brief's model reads anyway, in any language (V2-851 F4, audit P0-4).

So the kind is one more DECLARED question of the brief (`QUESTION`, asked with the others in the turn's one Jev call),
carried in the errand's context as `errand_kind` by the portal (`acts.errand.escalate_to_slowbrain`) and read here at
the licence. Without a sure verdict (a cron relaunch, a list row, a brief in flight) the errand is `generic`: a worker
without a browser asks for what it needs, a browser nobody asked for is the failure this file was written against.
"""
from __future__ import annotations

KEY = "errand_kind"
WEB, BUILD, CHANGE, GENERIC = "web", "build_card", "change_card", "generic"
#: The answers, declared once: the brief asks them, the readers below map them to the worker's kind.
_KINDS = (
    (WEB, "it has to be DONE ON a website: navigate or sign in to a site, book a table, a room or a flight, buy, pay a "
         "bill, cancel or change a subscription or account on the provider's site"),
    (BUILD, "build him a NEW card (a widget, an app on his screen)"),
    (CHANGE, "change the CODE or the design of one of his existing cards, or work on one of his software projects"),
    (GENERIC, "anything else: research, comparing options, writing a document or a report, reading his own messages "
             "or data, filling one of his cards with data"),
)


def question(_ctx=None) -> dict:
    """The brief's question: which kind of worker an errand he commissions needs."""
    return {"instructions": "If the operator commissions an errand, which kind of work is it?", "criteria": dict(_KINDS)}


def verdict(brief) -> dict | None:
    """The brief's `errand_kind` as `{choice, confidence}`, carried in the errand's context; None when unread."""
    try:
        from nucleo.turn import verdicts as _v
        choice, info = _v.read(brief, KEY, None, min_confidence=0.0)
        return {"choice": str(choice), "confidence": float((info or {}).get("confidence") or 0.0)} if choice and info else None
    except Exception:  # noqa: BLE001 — an unreadable brief is no verdict
        return None


def carry(ctx: dict) -> None:
    """The errand carries what the turn's brief decided about it: its kind and its consent class, read once at the one
    portal (`acts.errand.escalate_to_slowbrain`), so no door downstream re-reads his words to decide them."""
    if ctx.get(KEY) and ctx.get("errand_class"):
        return
    try:
        from nucleo.acts import errand as _errand
        from nucleo.turn import brief as _tb
        b = _tb.of_this_turn()
        for key, read in ((KEY, verdict), ("errand_class", _errand.class_verdict)):
            v = None if ctx.get(key) else read(b)
            if v:
                ctx[key] = v
    except Exception as e:  # noqa: BLE001 — no brief: the dispatcher reads «generic» and the money vocabulary
        from loguru import logger
        logger.debug(f"kind: the turn's verdicts unread — {e!r}")


def _sure(v: dict | None) -> str:
    from nucleo.turn import verdicts as _v
    choice, conf = str((v or {}).get("choice") or ""), float((v or {}).get("confidence") or 0.0)
    return choice if choice in dict(_KINDS) and conf >= _v.LICENCE else ""


def kind_of(v: dict | None) -> str:
    """The worker's kind from the verdict: `web` · `code` (a card built or changed) · `generic` (unsure included)."""
    choice = _sure(v)
    return WEB if choice == WEB else "code" if choice in (BUILD, CHANGE) else "generic"


def code_change(v: dict | None) -> str:
    """`"create"` / `"modify"` / `""` — WHICH card work this errand is, from the same verdict `kind_of` reads, so the
    gate's sentence and the worker it would start cannot disagree (V2-757)."""
    choice = _sure(v)
    return "create" if choice == BUILD else "modify" if choice == CHANGE else ""


def code_change_question(request: str, change: str = "") -> str:
    """The sentence the operator HEARS before we build or rewrite one of his cards (V2-757), in HIS language (V2-682):
    the gate stops the product doing something, so it says what, as he asked for it."""
    t = (request or "").strip()
    short = (t[:120] + "…") if len(t) > 120 else t
    from i18n import langs as _lg
    sp = _lg.current_language()
    tpl = sp.widget_build_confirm if change == "create" else sp.widget_change_confirm
    return tpl.format(what=short)


def default_label(kind: str, request: str = "") -> str:
    """The task row's label before the worker says anything, in the instance's language."""
    from nucleo.workers.progress import say as _say
    key, en = {"web": ("label_web", "Searching the web…"), "code": ("label_code", "Working on a widget…"),
               "memory": ("label_memory", "Updating memory…"),
               "research": ("label_research", "Researching…")}.get(kind, ("label_generic", "Thinking…"))
    return _say(key, en)
