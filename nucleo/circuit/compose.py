"""nucleo/circuit/compose.py — what an inline WRITE really left (refactor2710-02b, V2-769).

WHAT IT MUST LEAVE was the other half (`write_harness`, demo pass 144): after every turn that wrote, `spec.infer` ran
the model detached to read the end state of his words and ONE more model pass added what was missing. V2-851 F5
removed it with every model re-run after the main stream: the end state is the brief's verdict, read before the line
(`spec.end_state_declared`), and an order the turn did not finish is a task with its row, not a silent repair.

WHAT IT LEFT (was `write_outcome`, V2-769): a widget may say which keys it IGNORED (`add_meeting` with an unknown
`recurrence` wrote one Tuesday and answered success) — turned into a note the model must act on, never read out raw
(`ignored_note`); and a create whose sentence CONTAINS an earlier create's sentence on the same card within
`WINDOW_S` completes it — the earlier piece is taken back out with the `revert` its widget named (`superseded`).
"""
from __future__ import annotations

import re
import time
import unicodedata

from loguru import logger

def _base(wid) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


# ── what the write REALLY left (was `write_outcome.py`) ──────────────────────────────────────────────────────────


#: How long a create stays «the piece that may still be completed». The measured gap was 13 s; a sentence
#: split by the turn layer is completed within one or two turns, never minutes later.
WINDOW_S = 45.0

_last: dict = {}


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", s))


def is_create(action: str) -> bool:
    return str(action or "").startswith("add_")


def remember(wid: str, action: str, text: str, res, *, now: float | None = None) -> None:
    """After a create LANDED: keep what could take it back out, and the sentence it came from."""
    from nucleo.flash import served_writes as _served
    _served.note(wid, action, text, res, now=now)    # any landed WRITE: its sentence is not a worker's errand
    from nucleo.circuit import spec as _spec
    _spec.landed(wid, action, res)                    # a row it already held meets the write's end state (T-19 R10)
    if not (is_create(action) and isinstance(res, dict) and isinstance(res.get("revert"), dict)):
        return
    _last[wid] = {"action": action, "text": _fold(text), "revert": res["revert"],
                  "at": time.time() if now is None else now}


def superseded(wid: str, action: str, text: str, *, now: float | None = None) -> dict | None:
    """The earlier create on this card that THIS create's sentence completes, or None."""
    prev = _last.get(wid)
    if not prev or not is_create(action):
        return None
    now = time.time() if now is None else now
    cur = _fold(text)
    if now - float(prev["at"]) > WINDOW_S or not prev["text"] or cur == prev["text"]:
        return None
    if f" {prev['text']} " not in f" {cur} " or len(cur.split()) < len(prev["text"].split()) + 2:
        return None
    return prev


def forget(wid: str) -> None:
    _last.pop(wid, None)


def reset() -> None:
    _last.clear()
    from nucleo.flash import served_writes as _served
    _served.reset()


def declared_fields(wid: str, action: str) -> list[str]:
    """The payload keys the widget's manifest declares for this action — what the model should have used.
    The model sees action NAMES only (`widgets/brief.py`), so a correction that does not name them invites the
    same guess again."""
    try:
        from widgets import runtime
        for w in runtime.catalog():
            if str(w.get("id")) == wid:
                spec = (w.get("actions") or {}).get(action) or {}
                return [str(k) for k in (spec.get("payload") or {})]
    except Exception:  # noqa: BLE001
        pass
    return []


def ignored_note(wid: str, action: str, res) -> str:
    """The correction for a write that landed WITHOUT some of what it was told, or "" when nothing was lost."""
    if not isinstance(res, dict) or res.get("ok") is False:
        return ""
    lost = [str(k) for k in (res.get("ignored") or []) if str(k).strip()]
    if not lost:
        return ""
    return (f"[SISTEMA] «{action}» sobre «{wid}» SÍ se guardó, pero SIN estos datos, que la tarjeta no sabe "
            f"guardar: {', '.join(lost[:8])}. Si le dijiste que quedaba con eso, corrígelo en tu PRÓXIMA "
            f"respuesta — lo que está guardado es lo que dice la tarjeta, no lo que mandaste."
            + (f" Sus campos son: {', '.join(fields)}; si hay que rehacerlo, usa ESOS."
               if (fields := declared_fields(wid, action)) else ""))
