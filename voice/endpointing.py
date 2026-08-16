#
# endpointing.py — PURE decision logic for the turn layer (no pipecat, no I/O, fully unit-testable).
#
# Born from the 2026-07-05 car sessions (INI-009): the old turn layer closed a turn at the browser VAD's first
# ~1.1s pause (→ one thought chopped into 3 turns, a reply per fragment), and its 800ms barge-in timer could
# NEVER be cancelled in time because the browser's stop signal takes 1100ms of silence to fire (800 < 1100 →
# every backchannel cut the bot). This module holds the redesigned decisions; voice/turn_control.py executes them.
#
import os
import re

# ── Dynamic hold window ───────────────────────────────────────────────────────────────────────────────────────
# After speech pauses, wait THIS long before committing the turn. Longer utterances get a longer hold (a person
# mid-ramble pauses to think; a short command wants a snappy answer). Values in seconds.
HOLD_BASE = float(os.getenv("TURN_HOLD_BASE", "1.2"))
HOLD_MAX = float(os.getenv("TURN_HOLD_MAX", "2.2"))
HOLD_GROWTH = float(os.getenv("TURN_HOLD_GROWTH", "0.15"))    # extra hold per second of speech so far
# If the browser's stop never arrived (data channel drop / tab throttled), commit anyway after this EXTRA wait —
# replaces the old fixed 3s stuck-turn rescue with the same self-healing, now integrated in the hold logic.
NO_STOP_EXTRA = float(os.getenv("TURN_NO_STOP_EXTRA", "1.0"))

# ── Voice-energy thresholds (rms on the rnnoise-filtered mic, same scale as the observer probe) ──────────────
# Measured floor in a moving car after rnnoise: 0.000–0.003. Quiet speech: 0.006–0.01. Normal: 0.02–0.13.
VOICE_RMS_FLOOR = float(os.getenv("VOICE_RMS_FLOOR", "0.006"))   # anything above = voice evidence (keeps turn alive)
BARGE_RMS = float(os.getenv("BARGE_RMS", "0.010"))                # stronger bar to CUT the bot (avoid noise cuts)
BARGE_GAP_MS = float(os.getenv("BARGE_GAP_MS", "250"))            # tolerated silence inside a sustained-voice run
BARGE_GIVEUP_MS = float(os.getenv("BARGE_GIVEUP_MS", "2500"))     # armed this long without sustaining → backchannel, disarm


def hold_secs(utterance_secs: float) -> float:
    """How long a pause must last (from the LAST voice evidence) before the turn commits."""
    return min(HOLD_BASE + HOLD_GROWTH * max(0.0, utterance_secs), HOLD_MAX)


def should_commit(silence_secs: float, utterance_secs: float, browser_stopped: bool) -> bool:
    """Commit the open turn? The browser's stop is corroborating evidence; without it we wait a bit longer
    (its VAD is better than raw energy at hearing quiet speech), but a lost signal can NEVER wedge the turn."""
    h = hold_secs(utterance_secs)
    if browser_stopped:
        return silence_secs >= h
    return silence_secs >= h + NO_STOP_EXTRA


# ── Backchannel gate ─────────────────────────────────────────────────────────────────────────────────────────
# Pure acknowledgements that must NEVER cut the bot nor earn a reply when said while (or right after) it speaks.
# Kept deliberately small and high-precision: anything not clearly a backchannel is treated as real speech.
_BACKCHANNEL_WORDS = {
    "ok", "okay", "okey", "vale", "va", "sí", "si", "no", "ya", "ajá", "aja", "mmm", "hmm", "eh",
    "claro", "perfecto", "genial", "guay", "bien", "bueno", "exacto", "eso", "gracias", "venga",
    "entiendo", "entendido", "ah", "oh", "uy", "madre", "jo", "joder", "yes", "yep", "yeah", "right", "thanks",
    # V2-102: filler/interjections named explicitly by the operator when scoping the turn-completeness judge —
    # cheap, unambiguous, still es/en only ON PURPOSE. Broader other-language coverage is NOT attempted here: an
    # interjection in an uncovered language just costs one `segmenter.judge()` call and gets classified
    # correctly by MEANING — that fallback is the point of this whole feature, not a gap to patch with more
    # hardcoded lists (same "local accelerator, LLM is the real mechanism" pattern as everywhere else in i18n).
    "uh", "uhh", "oops", "wow", "damn", "shit", "fuck", "good",
}
_PUNCT_RE = re.compile(r"[^\wáéíóúüñ ]+", re.UNICODE)


def is_backchannel(text: str) -> bool:
    """True if *text* is a pure short acknowledgement ("ok", "vale vale", "sí sí gracias")."""
    words = _PUNCT_RE.sub(" ", (text or "").lower()).split()
    if not words or len(words) > 3:
        return False
    return all(w in _BACKCHANNEL_WORDS for w in words)


def voiced_run_ms(run_ms: float, gap_ms: float, frame_ms: float) -> float:
    """Accumulate the CONTINUOUS-voice run used by the barge-in: a voiced frame extends the run if the gap since
    the previous voiced frame is small; a long gap restarts it. (A backchannel's short burst never reaches the
    barge threshold; real talking-over does.)"""
    return run_ms + frame_ms if gap_ms <= BARGE_GAP_MS else frame_ms
