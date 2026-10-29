"""nucleo/circuit/compose.py — an inline WRITE, both halves: what it must leave, and what it REALLY left (refactor2710-02b).

WHAT IT MUST LEAVE (was `write_harness`, demo pass 144): «save Quinn and Rowan in my contacts» made ONE `add_contact`
and said «Done.»; a per-call `done_when` attests the calls made, never the one that was not. So, off the hot path
after the turn's ops ran: `spec.infer` writes the end state of his words; only rows that must be PRESENT on the card
the turn wrote to are kept; `spec.attest` checks (met or unreadable ends it); ONE pass may repeat an action this turn
already ran on that card (never one that leaves), and the spec is attested again (`after_turn`, `check`). A row is
owed WITH the data his words gave it (`with`), and the repair carries it (`grounded`, T-19 R2).

WHAT IT LEFT (was `write_outcome`, V2-769): a widget may say which keys it IGNORED (`add_meeting` with an unknown
`recurrence` wrote one Tuesday and answered success) — turned into a note the model must act on, never read out raw
(`ignored_note`); and a create whose sentence CONTAINS an earlier create's sentence on the same card within
`WINDOW_S` completes it — the earlier piece is taken back out with the `revert` its widget named (`superseded`).
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata

from loguru import logger

#: How long the turn's own ops get to land before the end state is read.
SETTLE_S = 1.5
_BG: set = set()

_SYS = (
    "You are the brain of a voice assistant. The operator's order below was carried out only IN PART on the card "
    "«{wid}»: what is still missing is listed. Make now the `widget_data` calls that add exactly what is missing — "
    "widget_id «{wid}», only these actions: {allowed}, the payload taken from his words. Never repeat what the card "
    "already holds; if nothing fits, call nothing. Write any text in the OPERATOR's language.\n\nActions of «{wid}»:\n"
    "{actions}\n\nWHAT THE CARD HOLDS NOW:\n{digest}"
)


def _base(wid) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def writes_of(ops) -> list[tuple[str, str]]:
    """The turn's (card, action) pairs that WROTE and stay home: no view, nothing that leaves."""
    from nucleo.flash import data_ops as _do, frontend as _fe
    out: list[tuple[str, str]] = []
    for w, a in ops or ():
        w, a = _base(w), str(a or "").strip()
        if w and a and not _do.is_view_op(w, a) and not _fe.at_least_sensitive(w, a) and (w, a) not in out:
            out.append((w, a))
    return out


def after_turn(order_text: str, ops, *, spec=None) -> None:
    """Schedule the check for this turn's writes. Never raises, never waits."""
    try:
        writes = writes_of(ops)
        order = str(order_text or "").strip()
        if not (writes and order) or order.startswith("[SISTEMA]") or len({w for w, _ in writes}) != 1:
            return
        t = asyncio.ensure_future(check(order, writes, spec=spec))
        _BG.add(t)
        t.add_done_callback(_BG.discard)
    except RuntimeError as e:
        logger.debug(f"write harness: no running loop to schedule on ({e})")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"write harness not scheduled: {type(e).__name__}: {e}")


def goal_on(done_when, card: str, order: str = "") -> dict | None:
    """The inferred end state, cut to rows that must be PRESENT on `card` and that HIS words name — the only part this
    turn can owe. Demo pass 145, INIT: «Remember: … the Tesla insurance renews on March 12…» inferred four agenda
    rows («Ducati insurance renewal», «Tesla next service»…) and the harness wrote three meetings nobody asked for;
    a row is owed only when every value that names it is in what he said."""
    from nucleo.circuit import verify as _verify
    if not done_when:
        return None
    said = " ".join(str(order or "").lower().split())
    def _said(v): return isinstance(v, str) and " ".join(v.lower().split()) in said   # noqa: E301,E704
    kept = [_owed(c, _said) for c in _verify._clauses(done_when)[1]
            if _verify.kind_of(c) == "rows" and _base(c.get("widget")) == card
            and str(c.get("expect") or "present") == "present"
            and _names_a_row(c) and all(_said(v) for v in (c.get("where") or {}).values() if isinstance(v, str))]
    return {"all": kept} if kept else None


def _owed(clause: dict, said) -> dict:
    """The clause with only the `with` values his own words carry: one the model reshaped is not his to write."""
    stated = {k: v for k, v in (clause.get("with") or {}).items() if said(v)}
    out = {k: v for k, v in clause.items() if k != "with"}
    return {**out, "with": stated} if stated else out


def _names_a_row(clause: dict) -> bool:
    """A row clause OWES a row only when some value of its `where` names one: `title~=""` matches no row and is in every
    sentence, so it read «unmet» and the pass moved the meeting AGAIN (demo sandbox 2026-10-28, C4)."""
    where = clause.get("where") if isinstance(clause.get("where"), dict) else {}
    return any(str(v).strip() for v in where.values() if isinstance(v, (str, int, float)))


async def check(order: str, writes: list, *, spec=None, settle_s: float = SETTLE_S) -> int:
    """Run the loop once; the number of repair calls applied. Never raises."""
    try:
        from nucleo import circuit as _circuit
        from nucleo.circuit import spec as _spec, verify as _verify
        card = writes[0][0]
        goal = goal_on(await _spec.infer(order), card, order)
        if not goal:
            return 0
        await asyncio.sleep(settle_s)
        e = _spec.open(goal, text=order, source="turn+inferred", widget=card)
        if (read := _spec.attest(e)) is not False:
            if read:
                _circuit.settle(e, verdict="met")
            return 0
        calls = await _missing_calls(order, card, [a for _, a in writes], _verify.missing(goal), spec=spec)
        calls = [(a, grounded(card, a, p, goal)) for a, p in calls]
        from widgets.server_api import brain_action
        for action, payload in calls[: len(goal["all"])]:
            await brain_action(card, action, payload)
        if calls:
            from voice.observer import emit
            emit("brain", "🔁 arnés: la orden pedía más de lo que se hizo — completado", role="system",
                 text=f"{card}: {', '.join(a for a, _ in calls)}", extra={"cat": "flash", "widget": card})
            await asyncio.sleep(settle_s)
            if _spec.attest(e):
                _circuit.settle(e, verdict="met")
        return len(calls)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"write harness: {type(e).__name__}: {e}")
        return 0


async def _missing_calls(order: str, card: str, allowed: list, missing: list, *, spec=None) -> list[tuple[str, dict]]:
    """One pass, bounded to the actions this turn already ran on `card`."""
    from nucleo.flash import act_repair as _ar, repair_grounding as _rg, widget_read as _wr
    from nucleo.llm.fast_client import FastClient
    from widgets import runtime as _rt
    tool = _ar._widget_data_tool()
    manifest = _rt.get(card) or {}
    if not tool or not manifest:
        return []
    got: list[tuple[str, dict]] = []
    system = _rg.in_his_lang(_SYS).format(wid=card, allowed=", ".join(allowed), actions=_ar._actions_block(manifest),
                                          digest=str(_wr.read(card) or "")[:1500])
    await FastClient().complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": f"Operator: «{order[:600]}»\nStill missing: {'; '.join(missing)[:600]}"}],
        spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
        on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
    out: list[tuple[str, dict]] = []
    for name, args in got:
        action = str(args.get("action") or "").strip()
        if name == "widget_data" and _base(args.get("widget_id")) == card and action in allowed:
            out.append((action, args.get("payload") if isinstance(args.get("payload"), dict) else {}))
    return out


def grounded(card: str, action: str, payload: dict, goal) -> dict:
    """The repair's payload carrying the data HIS order gave the row it writes (T-19 R2): each `with` value goes under
    its field when the action declares that field and the payload does not carry the value anywhere yet."""
    from widgets import rows as _rows
    out, fields = dict(payload or {}), set(declared_fields(card, action))
    for c in (goal or {}).get("all") or []:
        names = [_rows._fold(v) for v in (c.get("where") or {}).values() if str(v).strip()]
        if not (names and all(n in _rows._fold(out) for n in names)):
            continue                                    # not the row this call writes
        for key, value in (c.get("with") or {}).items():
            field = next((f for f in _rows._split(key)[0].split("|") if f in fields), "")
            if field and _rows._fold(value) not in _rows._fold(out) and not str(out.get(field) or "").strip():
                out[field] = value
    return out


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
