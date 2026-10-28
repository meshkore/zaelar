#
# consent_hooks.py — the hooks the consent rule and the pending-work reader ask this card (V2-800, V2-799, V2-807):
# the held row an order confirms, the channel that refines a send's class, the rows held for his word, a text that
# belongs on one of them, and what the card sent lately. Moved out of data.py (which re-exports every name) with no
# behaviour change; each hook never raises.
#
from . import held as _held
from . import outbound as _outbound
from .shape import load_db


# ── V2-800 · the consent rule's two hooks (read by `nucleo/flash/frontend.py`, same shape as the agenda's) ─────────

def held_row(action: str, payload: dict | None = None) -> dict | None:
    """The draft this send would deliver when he has already SEEN it — the row his explicit order confirms."""
    try:
        from nucleo import his_words
        return _held.held_row(str(action or ""), dict(payload or {}), load_db(), his_words.since)
    except Exception as e:  # noqa: BLE001 — an unreadable hook leaves the friction where it was
        _held.logger.info(f"held_row unreadable ({e}) — the send keeps its question")
        return None


def consent_scope(action: str, payload: dict | None = None) -> dict:
    """The CHANNEL refines a send's class (`messaging.send_new@email`), so a rule he gives for one channel («no me
    pidas confirmación para los correos») governs that channel only; `consent.class_policy` falls back to the bare
    class when the channel has no rule of its own. A call whose channel cannot be read keeps the declared class."""
    try:
        if action not in ("send_draft", "send_to", "reply", "forward"):
            return {}
        p = dict(payload or {})
        plat = ""
        if action == "send_draft":
            db = load_db()
            k = _held.draft_for(db, str(p.get("contact") or "")) if p.get("contact") else None
            k = str(p["key"]) if str(p.get("key") or "") in (db.get("drafts") or {}) else k
            d = ((db.get("drafts") or {}).get(k) if k else None) or db.get("draft") or {}
            plat = str((d.get("target") or {}).get("platform") or "")
        elif p.get("contact") or p.get("to"):
            t = _outbound.resolve_target({**p, "text": p.get("text") or "-"})
            plat = str(t.get("platform") or "") if t.get("ok") else ""
        return {"class": f"messaging.send_new@{plat}"} if plat else {}
    except Exception as e:  # noqa: BLE001 — the declared class stands
        _held.logger.info(f"consent_scope unreadable ({e}) — the declared class stands")
        return {}


def pending_rows() -> list[dict]:
    """V2-799 — what this card holds for his word, for `nucleo/pending_work.py`: each held draft, and how it resumes
    (its own `send_draft`, so a «finish those» reaches it through the same confirm gate as a «send it»).

    V2-807 T-10 — and what it IS, whichever cards are open: its body's excerpt and the declared actions that show,
    rewrite, send or drop it, named by its recipient. This row is the one place a held draft reaches the prompt."""
    try:
        return [{"id": d["key"], "title": f"{d['platform'] or 'message'} → {d['to']}: {d['subject'] or d['text'][:60]}",
                 "state": "draft waiting for his OK", "at": d["at"], "excerpt": d["text"],
                 "verbs": ["open_draft", "draft", "send_draft", "discard_draft"], "args": {"contact": d["to"]},
                 "resume": {"action": "send_draft", "payload": {"contact": d["to"]}}}
                for d in _held.held(load_db()) if d["to"]]
    except Exception as e:  # noqa: BLE001
        _held.logger.info(f"pending_rows unreadable ({e})")
        return []


def claim_text(text: str, title: str = "") -> dict | None:
    """V2-807 T-09 — the hook `widgets/text_home.py` asks: is this text, about to be written on another card, a
    version of a message held here? Then it belongs on its row (`held.claim`). None when it is not, or unreadable."""
    try:
        return _held.claim(load_db(), str(text or ""), str(title or ""))
    except Exception as e:  # noqa: BLE001 — an unreadable store claims nothing: the text goes where it was sent
        _held.logger.info(f"claim_text unreadable ({e})")
        return None


def recent_facts() -> list[str]:
    """V2-807 T-12 — what this card SENT lately and what is still leaving, as the record every turn reads
    (`nucleo/pending_work.fact_lines`): a claim about what left is read from the body as it left."""
    try:
        from . import inbox_read
        return inbox_read.sent_facts()
    except Exception as e:  # noqa: BLE001
        _held.logger.info(f"recent_facts unreadable ({e})")
        return []
