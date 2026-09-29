"""nucleo/circuit.py — one loop, one bound, one report (V2-776 L3).

## What this replaces

Three fragments verified an end state, each with its own owner, clock and cap, none of them the path a
request takes (four read-only maps of the brain, 2026-09-29):

  · `nucleo/harness.py` (V2-660): one goal kind, in RAM, 300 s, re-verified by the pulse, never retried;
  · `nucleo/workers/goal.py` (V2-707 F2): the worker's own `done_when`, checked once in `_finish`; the retry
    bound was `goal_retried` on a record every relay rebuilds — so the real cap was `relay_gen < 2`, shared
    with the context and provider relays; `None` ended on the worker's `ok` and was spoken as «It is done»;
  · `nucleo/errands/verify.py` (V2-683): one hand-written condition for third-party errands.

## What this is

The pulse re-verifies every open spec (`nucleo/spec.py`'s ledger — inline actions and errands alike); a
worker's ending is JUDGED here, not by its own word; the retry bound is explicit, its own, and the operator's
to set (genesis `circuit.retries`, overridable per install); an ending that cannot be read is a verdict of its
own («unverifiable») that the mouth says as such; and what the operator hears at the end is the VERDICT:
«done» only over `met`, «what is missing» over `gave_up`.

The V2-660 rule is kept verbatim: `None` (unreadable) is never failure and never opens a retry. The cure for
unreadable is a readable widget (L2), never a guess.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from loguru import logger

_GENESIS = Path(__file__).resolve().parent / "genesis.json"
RETRIES_DEFAULT = 2                 # «hemos probado dos o tres veces, no somos capaces» — the operator, 2026-09-29
CHECK_EVERY_S = 5.0                 # an open spec is read at most this often by the pulse
VERDICTS = ("met", "unmet", "retrying", "gave_up", "unverifiable", "undeclared", "skipped")


# ── the bound is the operator's ────────────────────────────────────────────────────────────────────────────

def settings() -> dict:
    """`circuit` of genesis, with the per-install override (`<workspace>/config/circuit.json`) on top —
    the same two layers `style`, `consent` and `errands` use."""
    out: dict = {}
    try:
        out.update((json.loads(_GENESIS.read_text(encoding="utf-8")) or {}).get("circuit") or {})
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo import workspace as _ws
        p = _ws.root() / "config" / "circuit.json"
        if p.exists():
            got = json.loads(p.read_text(encoding="utf-8")) or {}
            out.update({k: v for k, v in got.items() if not str(k).startswith("_")})
    except Exception:  # noqa: BLE001
        pass
    return {k: v for k, v in out.items() if not str(k).startswith("_")}


def retries() -> int:
    try:
        return max(0, int(settings().get("retries", RETRIES_DEFAULT)))
    except Exception:  # noqa: BLE001
        return RETRIES_DEFAULT


# ── the pulse ──────────────────────────────────────────────────────────────────────────────────────────────

def tick(now: float | None = None) -> list[dict]:
    """Re-verify the open specs; a met one closes with its event. Returns what closed now. No voice: an inline
    action's refusal already spoke through `report_failure`, and a worker's ending speaks through `close`."""
    from nucleo import spec as _spec
    now = time.time() if now is None else now
    closed: list[dict] = []
    for e in _spec.open_specs(now):
        if now - float(e.get("checked_at") or 0) < CHECK_EVERY_S:
            continue
        e["checked_at"] = now
        try:
            if _spec.attest(e, now=now) is True:
                closed.append(e)
        except Exception as ex:  # noqa: BLE001
            logger.debug(f"circuit: attest skipped ({ex})")
    return closed


# ── the ending of a worker ─────────────────────────────────────────────────────────────────────────────────

def _entry_for(rec):
    from nucleo import spec as _spec
    uid = str(getattr(rec, "uid", "") or "")
    for e in _spec.open_specs():
        if uid and e.get("task_id") == uid:
            return e
    return None


def _emit(rec, verdict: str, *, missing: str = "", tries: int = 0) -> None:
    try:
        from nucleo import verify as _verify
        from voice.observer import emit
        emit("task", {"met": "✅ circuito: estado final CUMPLIDO y verificado",
                      "retrying": "🔁 circuito: sin cumplir → relanzada con lo que falta",
                      "gave_up": "❌ circuito: sin cumplir y sin más intentos — se dice lo que falta",
                      "unverifiable": "🫥 circuito: no verificable — se entrega como NO comprobado",
                      "undeclared": "🤷 circuito: sin condición declarada — no se afirma nada",
                      "skipped": "⏭ circuito: no se juzga (cancelada o relevada)"}.get(verdict, verdict),
             text=_verify.describe(getattr(rec, "done_when", None)) or str(getattr(rec, "goal", "") or "")[:120],
             extra={"id": getattr(rec, "task_id", ""), "uid": getattr(rec, "uid", ""), "verdict": verdict,
                    "tries": tries, "missing": missing[:300], "cat": "circuit"})
    except Exception:  # noqa: BLE001
        pass


def verdict_of(rec, now: float | None = None) -> tuple[str, str]:
    """(verdict, what is missing) for a record, with NO side effects — what a budget kill or a stuck worker
    asks before it closes, so the operator hears the end state and not only the clock."""
    from nucleo import verify as _verify
    dw = getattr(rec, "done_when", None) or {}
    if not dw:
        # Demo pass 62, T1: a trip plan's end state is the REPORT — nothing a widget attests — and «unverifiable»
        # made the delivery say «I couldn't verify the prices myself». An errand whose spec could not be written is
        # one whose result is its words: undeclared. «Unverifiable» is a DECLARED clause the product cannot read.
        return "undeclared", ""
    try:
        from nucleo import spec as _spec
        dw = _spec.bind_sheet(dw, getattr(rec, "sheet", ""))
    except Exception:  # noqa: BLE001
        pass
    try:
        met = _verify.check(dw, now)
    except Exception:  # noqa: BLE001
        met = None
    if met is True:
        return "met", ""
    if met is None:
        return "unverifiable", ""
    return "unmet", "; ".join(_verify.missing(dw, now)) or "el objetivo declarado no se cumple"


def close(rec, relay_cap: int) -> str:
    """Judge a worker's ending against its spec and act on it. Returns the verdict; mutates `rec` (`ok`,
    `result_summary`, `handoff`, `verdict`). Never raises.

    The shape `workers/goal.py` had, with the bound made explicit and its own: `tries` lives on the spec
    (persisted on the task row), `genesis.circuit.retries` says how many, and a record that already spent its
    retry (`goal_retried`, the legacy flag a relay carries) counts as one try spent."""
    try:
        return _close(rec, relay_cap)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"circuit: could not judge the ending of {getattr(rec, 'task_id', '?')}: {e}")
        return "undeclared"


def _close(rec, relay_cap: int) -> str:
    from nucleo import spec as _spec
    if getattr(rec, "status", "") == "cancelled" or getattr(rec, "handoff", ""):
        rec.verdict = "skipped"
        return "skipped"
    verdict, missing = verdict_of(rec)
    entry = _entry_for(rec)
    tries = int((entry or {}).get("tries") or 0) + (1 if getattr(rec, "goal_retried", False) else 0)
    # An INFERRED spec is the model's guess at the end state, never the operator's words (demo pass 64: the INIT list
    # was given «contactos.contacts[title~=Richard]»). A guess may say «unverified»; it may never relaunch an errand
    # — a relaunch repeats side effects — nor tell him the errand failed.
    _src_entry = entry or _spec.of_task(str(getattr(rec, "uid", "") or "")) or {}
    if verdict == "unmet" and "inferred" in str(_src_entry.get("source") or ""):
        verdict, missing = "unverifiable", ""
    if verdict == "unmet":
        budget = retries()
        if tries < budget and int(getattr(rec, "relay_gen", 0) or 0) < relay_cap:
            # ITERATE — carrying WHAT IS MISSING, so the relaunch starts from the gap instead of from zero.
            rec.goal_retried = True
            try:
                from nucleo.flash import escalate as _esc
                _esc.escalate_to_slowbrain(
                    f"{rec.goal}\n\n[ARNÉS] Esto quedó SIN cumplir y es lo que hay que terminar: {missing}. "
                    f"Lo demás ya está hecho: no lo repitas.",
                    context={"src": "goal_unmet", "kind": rec.kind, "trace": rec.trace_id,
                             "sheet": str(getattr(rec, "sheet", "") or ""),
                             "surface": str(getattr(rec, "surface", "") or ""),
                             "done_when": dict(rec.done_when), "depth": int(rec.depth or 0),
                             "relay_gen": int(rec.relay_gen or 0) + 1,
                             "task_uid": str(getattr(rec, "uid", "") or "")})
                rec.result_summary = ""            # no delivery: the relay takes it over, without noise
                rec.ok = False
                rec.handoff = f"objetivo sin cumplir → retomada ({missing[:80]})"
                verdict = "retrying"
                if entry is not None:
                    entry["tries"] = tries + 1
                    _spec.persist(entry["task_id"], entry)
                logger.warning(f"worker[{rec.task_id}]: objetivo SIN cumplir → relanzada ({tries + 1}/{budget}) · {missing}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"worker[{rec.task_id}]: no pude relanzar por objetivo: {e}")
                rec.ok = False
                verdict = "gave_up"
        else:
            # No budget left: the operator hears the TRUTH — an errand nobody could finish is never delivered
            # as a finished one, and what it DID achieve is not thrown away.
            rec.ok = False
            rec.result_summary = (f"No he podido dejarlo terminado. Queda: {missing}."
                                  + (f" {rec.result_summary.strip()}" if rec.result_summary.strip() else ""))
            verdict = "gave_up"
            # …and ONE question, once (the operator, 2026-09-29: «acabar de definir mejor la request… después de
            # cada iteración»): the relaunch is PARKED on his answer through the confirm-gate's own register, so
            # his «sí» — with whatever he adds — is what launches it, and silence lets it expire.
            if entry is not None:
                entry["status"] = "gave_up"
                if bool(settings().get("ask_on_give_up", True)) and not entry.get("asked"):
                    if _park_retry(rec, missing):
                        entry["asked"] = True
                        rec.result_summary += " " + RETRY_QUESTION
                _spec.persist(entry["task_id"], entry)
    elif verdict == "met" and entry is not None and entry.get("status") == "open":
        entry["status"], entry["met_at"] = "met", time.time()
        _spec.persist(entry["task_id"], entry)
    rec.verdict = verdict
    _emit(rec, verdict, missing=missing, tries=tries)
    return verdict


RETRY_QUESTION = "¿Lo intento otra vez, con alguna pista tuya?"


def _park_retry(rec, missing: str) -> bool:
    try:
        from nucleo import dispatch_confirm as _dc
        _dc.remember_offer(
            f"{rec.goal}\n\n[ARNÉS] Esto quedó SIN cumplir y es lo que hay que terminar: {missing}. "
            f"Lo demás ya está hecho: no lo repitas.",
            context={"src": "goal_unmet", "kind": rec.kind, "trace": rec.trace_id,
                     "sheet": str(getattr(rec, "sheet", "") or ""), "surface": str(getattr(rec, "surface", "") or ""),
                     "done_when": dict(rec.done_when), "depth": int(rec.depth or 0),
                     "task_uid": str(getattr(rec, "uid", "") or "")},
            question=f"No he podido dejarlo terminado: queda {missing[:160]}. {RETRY_QUESTION}")
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"circuit: could not park the retry: {e}")
        return False


def ending_note(rec, now: float | None = None) -> tuple[str, str]:
    """(verdict, missing) for an ending the pulse forces (a budget kill, a stall): what the operator hears
    beside the clock — the END STATE, which is the thing he asked about. No side effects."""
    return verdict_of(rec, now)


# ── the mouth ──────────────────────────────────────────────────────────────────────────────────────────────

OUTCOMES = {
    "met": "It is done, and you checked the result yourself.",
    "undeclared": "It is done.",
    "unverifiable": "The work was done, but you could NOT check the result yourself — say so plainly: done, "
                    "unverified. Never say it is done as a fact.",
    "gave_up": "It could not be completed. Say what is missing; do not dress it up.",
    "unmet": "It could not be completed. Say what is missing.",
}


def outcome_line(verdict: str, ok: bool) -> str:
    """The outcome sentence the spoken delivery is built on — the verdict's, never the worker's `ok`."""
    v = str(verdict or "")
    if v in OUTCOMES:
        return OUTCOMES[v]
    return "It is done." if ok else "It could not be completed."


def voice_rules_line() -> str:
    """The operator's standing rules for how the assistant speaks (scope `voice`), so a delivery composed off
    the turn obeys them like a turn does — `proactive.notify` never read them."""
    try:
        from memory import api as _memapi, rules as _rules
        rs = _rules.for_surface(_memapi.state() or {}, "voice")
        if not rs:
            return ""
        return "The person's standing rules for how you speak, which you obey: " + " · ".join(str(r)[:160] for r in rs[:6])
    except Exception:  # noqa: BLE001
        return ""
