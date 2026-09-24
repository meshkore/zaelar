"""nucleo/flash/provider_failure.py — WHAT to do when the model stream blows up, decided ONCE.

It exists because the same decision was written twice, and that duplication has bitten THREE times:

  · 2026-08-18 (V2-118…121, `22f3674`): `probe.py` is the PARALLEL implementation of the voice provider, and the harness
    runs through that channel. The `[[cron.create]]` tags were CAPTURED there and not executed, so a scheduled notice
    could not exist through that route — the mechanism was UNREACHABLE for everything being measured.
  · 2026-08-15: failover on a HARD failure was added to voice and not here.
  · 2026-08-21, which is what left the harness **unable to measure for eight hours**: with the actual seeded chain
    (`deepseek-directo → aimlapi-failover`), a text turn returned
    `{"ok":false,"error":"modelo: 402 Insufficient Balance"}` **in the same second** that the log said
    «`deepseek-directo` SIN SALDO → relevo a `aimlapi-failover`». Voice failed over, i18n failed over, text did not.

In other words: the policy was not missing; **the text channel was not applying it**. Two copies of a decision
diverge without warning, and the warning arrives when someone measures something that fails for a reason other than the one being measured.

What is shared is the DECISION (stall or hard failure? which tier to fail over to? is any tier left?). What is NOT
shared —deliberately— is what each channel tells the operator: voice speaks, the text channel returns an object.
"""
from __future__ import annotations

from loguru import logger


def tier_for(spec, role: str):
    """The tier in the chain on which THIS turn ran, or None if it is not recognized.

    V2-252 — there are TWO sources for “who is primary” and they do not always agree: the turn builds its spec with
    `spec_from_config()` (which reads `fast.model` / `fast.base_url`) and the chain is ordered by `fast.providers`.
    The harness measured this on 2026-08-21 by reordering the ladder and seeing that **nothing changed**.

    This matters because `note_failure` without `tier` asks `pick()`, meaning “the one that would be selected NOW” — which
    after a reorder may not be the one that just failed. The cooldown then lands on a HEALTHY provider while the
    broken one remains selected: punishing the innocent and leaving the guilty free, silently. It is resolved using the
    `base_url` used for the call, which is the only datum that cannot lie about who responded.
    """
    try:
        url = (spec.resolved_base_url() or "").strip().rstrip("/") if spec is not None else ""
    except Exception:  # noqa: BLE001
        url = ""
    if not url:
        return None
    try:
        from nucleo.flash import provider_chain as pc
        # V2-307 — base_url alone is insufficient when TWO tiers share an endpoint: `deepseek-directo` and
        # `deepseek-directo-pro` both live at api.deepseek.com, and returning “the first match” ALWAYS marked
        # flash. Measured at 03:13-03:15 (2026-08-25): the primary failed for BALANCE (402), failover went
        # to pro —same empty account—, its retry 402 marked FLASH again, already in cooldown, and pro never
        # entered cooldown → the chain NEVER advanced to the broker: four silent turns with a funded tier
        # waiting beside it. With MODEL first, the (endpoint, model) pair is unique; the fallback to endpoint-only
        # is retained for a spec whose model is not in the chain (a manual pin).
        _model = ""
        try:
            _model = str(getattr(spec, "model", "") or "").strip()
        except Exception:  # noqa: BLE001
            pass
        _by_url = None
        for t in pc.chain(role):
            if (t.get("base_url") or "").strip().rstrip("/") == url:
                if _by_url is None:
                    _by_url = t
                if _model and str(t.get("model") or "").strip() == _model:
                    return t
        return _by_url
    except Exception:  # noqa: BLE001
        pass
    return None


def handle(err_text: str, *, role: str, stalled: bool = False, spec=None) -> dict:
    """Marks the tier, records health, and returns `{relay, dry}`.

    · `relay` = the tier to go to, or None if there is nowhere to go (or if the error is not provider-related).
    · `dry`   = the chain has NO healthy tier left (V2-243): this changes what is told to the operator,
                because “can you repeat that?” is a lie when there is no one left to ask.

    Entirely fail-soft: this runs inside a turn’s error handler and cannot add an exception to the one that already occurred.
    """
    from nucleo.flash import provider_chain as pc

    relay = None
    culpable = tier_for(spec, role)          # the one that ACTUALLY ran; None → let `pick()` decide, as before
    try:
        if stalled:
            # V2-246: an isolated stall is noise; two in a row mean a tier is unusable.
            relay = pc.note_stall(role=role, tier=culpable)
        else:
            relay = pc.note_failure(err_text, role=role, tier=culpable)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"provider_failure({role}): no pude anotar el fallo: {e!r}")
    dry = False
    try:
        dry = pc.pick(role) is None
    except Exception:  # noqa: BLE001
        pass
    try:
        from voice import health_state, llm_health
        if stalled:
            health_state.record("llm", "slow", "un turno se atascó sin respuesta y lo corté")
        else:
            health_state.record("llm", llm_health.classify(err_text) or "error",
                                (err_text or "")[:200] or "flash brain down")
    except Exception:  # noqa: BLE001
        pass
    return {"relay": relay, "dry": dry}


# ── OUR OWN BUG IS NOT A PROVIDER OUTAGE (V2-758, 2026-09-23) ────────────────────────────────────────────────
# Measured on his engine that evening: NINE turns reported to him as «Cerebro rápido caído — turno degradado»
# while DeepSeek answered perfectly. The real cause was `UnboundLocalError: cannot access local variable
# '_cvis'` — a local in `_on_tool_call` shadowing this repo's alias for `canvas_visibility`, so `show_images`
# and the music/messaging guards could not run at all.
#
# The error handler treated every exception as the provider's, which had three consequences, all wrong and all
# invisible: a cooldown opened on a HEALTHY tier, the panel painted the model amber/red, and the stand-in was
# promoted to serve traffic the titular could have served. A failover cannot fix a bug of ours — the same
# exception fires on the stand-in — so relaying is not merely useless here, it spends his more expensive rung
# on a fault it cannot cure and lies about whose fault it is.
#
# THE TEST IS THE EXCEPTION, NOT THE TEXT. A provider failure arrives as an HTTP status (402, 429, 5xx) or a
# transport error; a bug of ours arrives as one of Python's programming errors with no status attached. The
# status guard is kept because an SDK may wrap a real HTTP failure in a TypeError, and a real 402 must never be
# excused as «our bug».
_ENGINE_FAULTS = (UnboundLocalError, NameError, AttributeError, TypeError, KeyError, IndexError,
                  ImportError, ZeroDivisionError, AssertionError)


def is_engine_fault(exc: BaseException | None) -> bool:
    """Is this OUR bug rather than the provider's failure? `False` for anything carrying an HTTP status."""
    if exc is None or not isinstance(exc, _ENGINE_FAULTS):
        return False
    return not (getattr(exc, "status_code", None) or getattr(exc, "status", None))


def engine_fault_line(exc: BaseException | None) -> str:
    """What the timeline and the panel say about a fault of ours — it NAMES the defect, because the operator's
    first question is always «tengo que saber qué pasa… identificarlo», and «flash layer error» answered none
    of it. Deliberately not spoken: he hears the ordinary stumble; this is for the ◷ and the ◉."""
    if exc is None:
        return "fallo interno del motor"
    return f"fallo interno del motor · {type(exc).__name__}: {str(exc)[:160]}"
