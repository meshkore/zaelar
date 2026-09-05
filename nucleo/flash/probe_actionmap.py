"""The probe channel's ACTION MAP mirror (V2-539 · V2-545 · V2-572).

Extracted from `probe.py` on the 2026-09-05 ratchet pass (the file had grown past its ceiling; the ratchet asks
for a module, never a taller ceiling). This is one half of the parallel-impl channel — the voice half lives in
`voice/engine/llm/providers/fast_lane.py` — so the wiring guards in
`tests/agent_headless/unit/actionmap/test_a_known_phrase_skips_the_model.py` read BOTH files: a guard pointed at
a single file goes green the day the lane silently falls out of the path (V2-555's lesson).

A known whole-utterance command resolves WITHOUT the model. With `execute`, the map RUNS its action here too,
and the hit is only reported if it ran (the voice rail's contract). It used to report and never run, which was
right while the map only spoke canvas verbs — a show is meaningless headless. It stopped being right the day the
map could drive a widget's DATA: «ábreme el Telegram» changes a lens, and a channel that reports the change
without making it reports a decision the product does not take. A dry run (`execute=False`) still only reports,
which is what a dry run means. Same fail-open contract: any problem here and the turn proceeds to the model.
"""
from __future__ import annotations


def try_map(text: str, sess, *, execute: bool, trace_id: str, pick_ack=None) -> dict | None:
    """Return the finished probe response dict when the map served the turn, else None (fall through).

    `pick_ack` is passed IN by the caller instead of imported here — the dependency-direction ratchet (7.32)
    refused this module reaching into `voice.engine.core`, the same verdict `second_pass.py` got on its second
    day of life (V2-572): what the probe channel owns is the wiring, and the motor's vocabulary stays behind
    the caller's own, already-frozen import."""
    from . import dialog
    try:
        from nucleo import actionmap as _amap
        if not _amap.enabled():
            return None
        _amap_hit = _amap.match(text)
        if _amap_hit is not None and execute:
            from voice.observer import emit as _emit_amap
            if not _amap.execute(_amap_hit, _emit_amap, phrase=text):
                _amap_hit = None      # could not run it (no live loop, undeclared op) → on to the model
        if _amap_hit is None:
            return None
        _desc = _amap.describe(_amap_hit)
        _amap.record_hit(int(_amap_hit.get("id") or 0))
        try:
            from voice import observer as _obs_am
            _obs_am.turn_detail(system="", window=dialog.prune_window(sess.window)[-6:], tools=[],
                                user=text,
                                decision={"action": _desc, "actionmap": _amap_hit.get("id")})
        except Exception:
            pass
        try:  # V2-572 parity with the voice lane's spoken ack: the reply says the action landed
            _ack = pick_ack() if pick_ack is not None else ""
        except Exception:
            _ack = ""
        return {"ok": True, "reply": [_ack] if _ack else [], "action": _desc, "tool_calls": [],
                "tags": [], "actionmap": _amap_hit.get("id"), "trace": trace_id}
    except Exception as _e_am:  # noqa: BLE001
        try:
            from loguru import logger as _log_am
            _log_am.warning(f"actionmap (probe) skipped, fail-open: {_e_am!r}")
        except Exception:
            pass
    return None
