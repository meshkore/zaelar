"""Which of his errands does a sentence NAME? (three-tasks-at-once, 2026-10-10 20:00)

Two doors needed the same answer and had none:

  · the status line (`errands_of_a_turn.status_owed`) answered «but the jump, did you actually make it higher?»
    with every live errand's phase — the report and the monitor, never the game he asked about, three times;
  · the list lane (`nucleo/batch`) took «del coche, ¿qué tal de autonomía real? ¿Y el juego? …» — four
    sentences about three errands already running — for a NEW list, and answered each of four such turns with
    the same canned receipt.

The yardstick is the attribution's own (`dispatch._ref_words` / `dispatch._same_thing`: singular/plural, glued
punctuation), over every errand he can be talking about: the LIVE ones and the ones PARKED on a question to him
(a parked errand left `_SESSIONS`, and his refinements while it waits are part of what it is). No word list: the
same tokenizer in every language, ranked by the length of the words matched.
"""
from __future__ import annotations

from loguru import logger


def known() -> list[dict]:
    """Every errand he can be asking about: {id, label, request, phase, waiting_on, parked}. Never raises."""
    from nucleo import dispatch as _d
    out: list[dict] = []
    try:
        for e in _d.pending_summaries() or []:
            rec = _d.get_record(e.get("id"))
            label = str(getattr(rec, "label", "") or "").strip()
            out.append({"id": str(e.get("id") or ""), "label": "" if label.endswith("…") else label,
                        "request": str(e.get("request") or "").strip(), "phase": str(e.get("phase") or ""),
                        "note": str(e.get("note") or ""), "waiting_on": e.get("waiting_on") or "", "parked": False})
    except Exception as e:  # noqa: BLE001 — a reader never breaks a turn
        logger.debug(f"named_errand: live errands unreadable — {type(e).__name__}: {e}")
    try:
        from nucleo import dispatch_confirm as _dc     # the gate's own store (`pending_confirm` reads this one)
        for tid, p in list((getattr(_dc, "_PENDING_CONFIRM", None) or {}).items()):
            refs = " ".join(str(r) for r in (p.get("refinements") or []))
            out.append({"id": str(tid), "label": "", "request": str(p.get("request") or "").strip(),
                        "extra": refs, "phase": "", "note": "", "waiting_on": "user", "parked": True})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"named_errand: parked errands unreadable — {type(e).__name__}: {e}")
    return out


def _words(text: str) -> set[str]:
    from nucleo import dispatch as _d
    return _d._ref_words(_d._norm(text))


def named(text: str, errands: list[dict] | None = None) -> list[dict]:
    """Every errand `text` names, strongest first; [] when it names none. ALL of them, not the top one: «del coche,
    ¿qué tal de autonomía? ¿Y el juego? Del monitor no te olvides…» asks about three, and a top-1 would answer
    the monitor alone. A short word shared by chance can add an errand he did not mean — one line too many,
    which is the cheaper error than leaving out the one he asked about."""
    from nucleo import dispatch as _d
    errands = known() if errands is None else errands
    said = _words(text)
    if not said or not errands:
        return []
    scored = []
    for e in errands:
        hay = _words(f"{e.get('label', '')} {e.get('request', '')} {e.get('extra', '')}")
        scored.append((sum(len(w) for w in said if any(_d._same_thing(w, h) for h in hay)), e))
    scored.sort(key=lambda se: -se[0])
    return [e for s, e in scored if s]


def asks_about_all(text: str) -> bool:
    """«¿Cómo va todo?» / «how's everything going?» — the attribution's own «all» reading (`dispatch._ALL_RE`)."""
    from nucleo import dispatch as _d
    return bool(_d._ALL_RE.search(_d._norm(text)))
