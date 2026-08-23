"""nucleo/turn/ — the decisions a TURN makes, owned once and imported by both channels.

F1 of the 2026-08-23 architecture audit. The turn is implemented TWICE — `voice/engine/llm/providers/nucleo.py`
(`_run_inner`, 2,603 lines in one function) drives voice, `nucleo/flash/probe.py` (`run_turn`, 1,051) drives the
text/probe channel — and the two were stitched together by **21 literal mirror markers** (the annotation that says «this block is duplicated in
the other channel, keep both in sync»). This repo already has a name for what that costs: V2-118…121 (a mechanism UNREACHABLE from the channel
the use cases actually run on), V2-252 (the text channel never relayed a dead provider, eight hours of
measurement lost), V2-256 (one reading of an API answer, done twice, wrong in one copy).

What lives here is the DECISION. What stays in each channel is the DELIVERY — voice speaks and emits, probe
returns a dict — because that difference is real and collapsing it would be the opposite mistake. The rule the
package enforces: **two channels needing the same rule means extract it; a new mirror is a red test** (the
counter is ratcheted in `tests/infrastructure/unit/test_architecture_ratchet.py`).
"""
