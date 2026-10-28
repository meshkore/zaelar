"""How a verdict of the brief is READ — asymmetric, in one place (refactor2710-07).

A verdict and the model can disagree. Who wins depends on the direction:

  · LICENCE (≥ `LICENCE`, Jev's own floor): a verdict may license or complete an act the model did not make;
  · VETO (≥ `VETO`): a verdict may refuse what the model CALLED only when it is this sure — a weaker reader never
    silently overrules a stronger one (CRIT-K1/K2);
  · between the two, a disagreement with the model's call is a DOUBT, and a doubt about what will be touched is asked
    (`consent.ASK_WHICH`), never refused in silence and never executed blind.

The pieces that already read this way are here too: a sure «tell me» vetoes an unsure action (`tell_vetoes_unsure_action`,
was `words_only`), two calls the verdict heard in his sentence are two orders (`both_heard`, was `two_orders`), and an
order is sure at the operator's own threshold (`sure_order`). Every read emits the `jev read` event (`nucleo.jev.read`).
"""
from __future__ import annotations

from loguru import logger

#: A verdict below this is a shrug (`jev.MIN_CONFIDENCE`).
LICENCE = 0.5
#: A verdict must be at least this sure to refuse what the model called.
VETO = 0.85
#: A call the verdict heard with at least this mass in the distribution was in his sentence (`both_heard`).
HEARD_FLOOR = 0.15
#: `tell_vetoes_unsure_action`: a SURE «tell me» (≥ TELL_FLOOR) over an action below ACTION_FLOOR.
TELL_FLOOR, ACTION_FLOOR = 0.9, 0.8

RUN, VETOED = "run", "veto"


def read(handle, key: str, fallback, *, min_confidence: float | None = None):
    """One verdict out of the brief: `(choice, info)` when ready and at least `min_confidence` (default the licence),
    else `(fallback, info-or-None)`. Never waits, never raises."""
    try:
        from nucleo import jev as _jev
        return _jev.read(handle, key, fallback, min_confidence=LICENCE if min_confidence is None else min_confidence)
    except Exception:  # noqa: BLE001
        return fallback, None


def against_the_model(handle, key: str, agrees) -> str:
    """The model CALLED something this verdict is about: may it run? `agrees(choice)` says whether the verdict's choice
    is what the model did. `run` · `veto` (a disagreeing verdict ≥ VETO) · `consent.ASK_WHICH` (a disagreeing verdict
    between LICENCE and VETO). No verdict, or one below the licence, lets the call run (today's path)."""
    choice, info = read(handle, key, None, min_confidence=0.0)
    if not info or not choice:
        return RUN
    try:
        if agrees(choice):
            return RUN
    except Exception as e:  # noqa: BLE001 — an unreadable comparison never refuses
        logger.debug(f"verdicts: {key} comparison failed — {e!r}")
        return RUN
    conf = float(info.get("confidence") or 0.0)
    if conf >= VETO:
        return VETOED
    if conf >= LICENCE:
        from nucleo import consent
        return consent.ASK_WHICH
    return RUN


def mass(handle, key: str, choice: str) -> float:
    """The probability the verdict's distribution gave `choice` (0 when it cannot say)."""
    try:
        from nucleo import jev as _jev
        verdict = _jev.peek(handle) if isinstance(handle, dict) else None
        ans = (verdict or {}).get(key) or {}
        probs = ans.get("probabilities") or ans.get("probs") or {}
        return float(probs.get(choice) or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def both_heard(handle, wid: str, action: str, other: str) -> bool:
    """Did `screen_action` hear BOTH payload-less actions on this card in his sentence? Then they are two ORDERS, not the
    model enumerating alternatives (`build-a-video-playlist-from-links` ES, 2026-10-10: «súbele… y pásate al siguiente»).
    False when it cannot say — the enumeration guard holds."""
    from nucleo.turn import brief
    if not handle or not action or not other or action == other:
        return False
    base = str(wid or "").split("::", 1)[0].strip().lower()
    return (mass(handle, brief.TARGET_KEY, f"{base}:{action}") >= HEARD_FLOOR
            and mass(handle, brief.TARGET_KEY, f"{base}:{other}") >= HEARD_FLOOR)


def tell_vetoes_unsure_action(handle, *, tell_floor: float = TELL_FLOOR, action_floor: float = ACTION_FLOOR) -> bool:
    """A verdict that SURELY says «tell me» and an action it names below the sure floor: the completion stands down
    (`build-a-video-playlist-from-links__us`, turn 4: «did you actually skip it?» ran `next` a second time). A sure
    action still runs whatever the words reader says. An unreadable brief vetoes nothing."""
    from nucleo.turn import brief
    words, winfo = read(handle, brief.WORDS_KEY, "", min_confidence=tell_floor)
    if winfo is None or not winfo.get("used") or str(words or "") != "tell":
        return False
    _choice, ainfo = read(handle, brief.TARGET_KEY, "", min_confidence=action_floor)
    return ainfo is not None and not ainfo.get("used")


def sure_order(handle, widget_id: str, action: str) -> bool:
    """Is the turn read as an ORDER, and its action as exactly `widget_id:action`, both at or above the operator's
    `consent.intent_act_at`? The one place a doubt is weighed against his threshold. Never raises."""
    try:
        from nucleo import consent
        from nucleo.turn import brief
        floor = consent.intent_act_at()
        kind, k_info = read(handle, brief.REQUEST_KEY, "", min_confidence=floor)
        target, t_info = read(handle, brief.TARGET_KEY, "", min_confidence=floor)
        owner, _sep, name = str(target or "").rpartition(":")
        return bool(k_info and t_info) and str(kind) == "order" and name == action \
            and owner.split("::", 1)[0].lower() == str(widget_id or "").split("::", 1)[0].lower()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"verdicts: sure_order skipped — {e}")
        return False
