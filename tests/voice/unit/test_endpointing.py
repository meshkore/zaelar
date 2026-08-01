#
# test_endpointing.py — the turn-layer redesign (INI-009) validated against the REAL car session 20260705-202813.
#
# Every scenario below reproduces a failure the operator hit live, with the actual timings from the session log,
# and asserts the redesigned logic fixes it. Run: .venv/bin/python -m pytest tests/voice/unit/test_endpointing.py -q
#
from voice.endpointing import (
    hold_secs,
    is_backchannel,
    should_commit,
    voiced_run_ms,
    BARGE_GAP_MS,
    HOLD_BASE,
    HOLD_MAX,
    NO_STOP_EXTRA,
)


# ── Chop / fragmentation (the "responde a cada trozo" bug) ───────────────────────────────────────────────────
def test_fragment_pause_does_not_commit():
    """Session 20:28 +88s: 'esos registros estamos guardando' → 0.7s pause → 'todos los eventos…'. The old layer
    committed at the browser stop and the brain replied to the fragment. The new hold must ride over that pause."""
    # after ~3s of speech, a 0.7s (even 1.2s) pause must NOT commit
    assert not should_commit(silence_secs=0.7, utterance_secs=3.0, browser_stopped=True)
    assert not should_commit(silence_secs=1.2, utterance_secs=3.0, browser_stopped=True)
    # but a real end-of-thought pause does
    assert should_commit(silence_secs=1.7, utterance_secs=3.0, browser_stopped=True)


def test_short_command_commits_fast():
    """'Enséñame la agenda' (~1s of speech) must commit right after HOLD_BASE — snappy commands stay snappy."""
    h = hold_secs(1.0)
    assert h <= HOLD_BASE + 0.2
    assert should_commit(silence_secs=h + 0.05, utterance_secs=1.0, browser_stopped=True)


def test_long_ramble_gets_more_patience():
    """Dictating a long thought (10s+) earns the max hold — pauses to think don't chop it."""
    assert hold_secs(10.0) == HOLD_MAX
    assert not should_commit(silence_secs=HOLD_MAX - 0.3, utterance_secs=10.0, browser_stopped=True)


def test_lost_browser_stop_still_commits():
    """Sessions 20:08/20:14: data channel died mid-session → stop never arrived → (old) turn wedged for 27s+.
    The new layer commits anyway after hold + NO_STOP_EXTRA — self-healing is built into the same rule."""
    utter, h = 2.0, hold_secs(2.0)
    assert not should_commit(silence_secs=h + 0.1, utterance_secs=utter, browser_stopped=False)
    assert should_commit(silence_secs=h + NO_STOP_EXTRA + 0.1, utterance_secs=utter, browser_stopped=False)


# ── Backchannel gate (the "me corta cuando digo ok/gracias" bug) ─────────────────────────────────────────────
def test_backchannels_detected():
    # session 20:28 +113s: "Gracias." cut the bot AND got a reply — must be gated now
    for t in ("Gracias.", "ok", "Vale, vale", "sí sí", "ajá", "perfecto", "OK vale", "Entendido."):
        assert is_backchannel(t), t


def test_real_speech_is_not_backchannel():
    for t in ("en la balanza", "enséñame la agenda", "vale pues enséñame la agenda", "no me oyes bien",
              "perfecto cierra la agenda", "gracias por la búsqueda del velero"):
        assert not is_backchannel(t), t


# ── Barge-in by REAL sustained voice (the dead-800ms-timer bug) ──────────────────────────────────────────────
def test_gracias_burst_never_reaches_barge_threshold():
    """'Gracias' ≈ 600ms of actual voice. Old design: a blind 800ms timer that the browser's stop (1100ms
    redemption) could never cancel in time → EVERY backchannel fired the barge-in. New design: accumulate real
    voiced frames — 600ms of voice can't reach the 800ms bar."""
    run = 0.0
    for _ in range(30):                     # 30 × 20ms = 600ms of continuous voice
        run = voiced_run_ms(run, gap_ms=20, frame_ms=20)
    assert run < 800


def test_talking_over_fires():
    """Real talking-over (1s+ continuous voice, small natural gaps) must reach the bar and cut the bot."""
    run = 0.0
    for _ in range(50):                     # 1000ms with tolerated micro-gaps
        run = voiced_run_ms(run, gap_ms=BARGE_GAP_MS - 50, frame_ms=20)
    assert run >= 800


def test_long_gap_resets_the_run():
    run = voiced_run_ms(700, gap_ms=BARGE_GAP_MS + 200, frame_ms=20)
    assert run == 20                        # a real pause restarts the count — noise bursts can't accumulate


if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ✓ {name}")
            except AssertionError as e:
                fails += 1; print(f"  ✗ {name}: {e}")
    sys.exit(1 if fails else 0)
