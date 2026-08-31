"""End-of-turn detector that also considers MEANING, not just silence (V2-095, 2026-08-14).

LiveKit used to decide the turn boundary with silence + energy (`min_delay`/`max_delay` from
`voice/endpointing.py`) and, when enabled, its multilingual ONNX model. Neither checks whether the operator's
sentence **is finished**. Measured consequence in session b70a45d0: an operator dictating a long request
pauses to think, and each pause closed a turn that the next fragment cancelled.

    465s → 626s (161 s):  22 prompts · 18 cancelados · 20 rellenos · CERO respuestas
    …sobre trozos como «del», «del software,», «a», «para que», «Un un superplanning»

Of the session's 89 final transcriptions, the lexical layer in `nucleo/flash/segmenter.py` recognizes **43
as incomplete (48%)** with ZERO false positives on the operator's short commands («pon música», «para»,
«cancélalo», «sí, te autorizo»), which are the ones that truly cannot be held back.

## Why HERE and not in the provider

Because LiveKit sets the upper bound for us. This detector does not decide when the turn closes: it returns a
PROBABILITY that it has ended. Below `unlikely_threshold`, LiveKit waits `max_delay` instead of
`min_delay` — and `max_delay` is a hard cap. A semantic veto can DELAY a turn; it cannot lose it.
Doing it in the provider (discarding the fragment) could lose it if the operator falls silent right there.

## Composition, not replacement

If a previously configured detector exists (LiveKit's `MultilingualModel`), it is preserved and this one only
VETOES: we keep the LOWER of the two probabilities. Two independent signals that it «has not finished yet» are
worth more than one, and ours knows neither prosody nor languages — it knows dangling words.
"""
from __future__ import annotations

import os

from loguru import logger

from . import registry

# Probability returned when the sentence is clearly unfinished. It must remain BELOW the detector's
# `unlikely_threshold` so LiveKit waits: the local model's is around 0.15-0.2.
_INCOMPLETE_P = 0.01
_COMPLETE_P = 0.99
_THRESHOLD = 0.5


class SemanticTurnDetector:
    """Implements LiveKit's `_TurnDetector` (`unlikely_threshold` · `supports_language` ·
    `predict_end_of_turn`), delegating to an inner detector when present."""

    def __init__(self, inner=None):
        self._inner = inner

    @property
    def model(self) -> str:
        return "zaelar-semantic" + (f"+{getattr(self._inner, 'model', '?')}" if self._inner else "")

    @property
    def provider(self) -> str:
        return "zaelar"

    async def unlikely_threshold(self, language=None):
        # If there is an inner detector, respect ITS threshold (our probabilities are 0.01/0.99, so they fall on
        # the correct side of any reasonable threshold). Without one, use our own.
        if self._inner is not None:
            try:
                v = await self._inner.unlikely_threshold(language)
                if v is not None:
                    return v
            except Exception:
                pass
        return _THRESHOLD

    async def supports_language(self, language=None) -> bool:
        # The lexical layer is es/en. Support is declared ALWAYS: if the language is not one of ours, the analysis
        # finds no dangling words and returns «complete» — that is, the previous behavior. Saying we do not support
        # it would also disable the inner detector.
        return True

    async def predict_end_of_turn(self, chat_ctx, *, timeout: float | None = None) -> float:
        text = _last_user_text(chat_ctx)
        ours = _COMPLETE_P
        try:
            from nucleo.flash import segmenter
            incomplete, why = segmenter.looks_incomplete(text)
            if incomplete:
                ours = _INCOMPLETE_P
                # VISIBLE: an erroneous hold must be observable and correctable, not a turn that never arrives and
                # leaves nobody knowing why. Include the specific reason («ends in «del»…»).
                try:
                    from voice.observer import emit
                    emit("vad", "⏸ turno RETENIDO — la frase no ha acabado", text=text[:160], role="system",
                         extra={"cat": "system", "why": why, "detector": "semantic"})
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"turno semántico: análisis fallido, dejo pasar ({e!r})")
            ours = _COMPLETE_P

        if self._inner is None:
            return ours
        try:
            inner = await self._inner.predict_end_of_turn(chat_ctx, timeout=timeout)
        except Exception:
            return ours
        # The LOWER one: whichever of the two says «not yet» wins. Holding too long costs up to `max_delay`;
        # cutting off mid-sentence costs a whole wasted turn and an answer to a half-asked question.
        return min(ours, inner if isinstance(inner, (int, float)) else ours)


def _last_user_text(chat_ctx) -> str:
    """The last message from the OPERATOR in the context that LiveKit passes to the detector. Shape-tolerant: the
    `ChatContext` API has changed shape between versions, and an attribute must not bring down the turn."""
    try:
        items = list(getattr(chat_ctx, "items", None) or getattr(chat_ctx, "messages", None) or [])
    except Exception:
        return ""
    for m in reversed(items):
        try:
            if str(getattr(m, "role", "")) != "user":
                continue
            c = getattr(m, "content", None) or getattr(m, "text_content", None)
            if callable(c):
                c = c()
            if isinstance(c, list):
                c = " ".join(str(x) for x in c if isinstance(x, str))
            if c:
                return str(c)
        except Exception:
            continue
    return ""


@registry.register("semantic")
def build():
    """`turn_provider=semantic` (DEFAULT since 2026-08-14): the lexical layer, with LiveKit's ONNX detector inside
    only when explicitly requested.

    ONNX is **behind an env var and OFF by default** because it cannot work in this architecture, and this is
    measured, not assumed: the job runs in a THREAD (`job_executor_type=THREAD`, INI-012) and `MultilingualModel()`
    requires registering its `InferenceRunner` on the MAIN thread — it fails with «InferenceRunner must be registered on
    the main thread». Trying it in every session only left a noisy log error that looks like a failure but is not one.
    The lexical layer needs no inference runner, so it runs where the model cannot.

    `ZAELAR_TURN_ONNX=1` retries it, for the day inference is registered on the main thread before
    starting the worker (the INI-012 follow-up). If it fails, it falls back to the lexical layer alone — which is
    still infinitely better than silence alone.
    """
    inner = None
    if (os.getenv("ZAELAR_TURN_ONNX") or "").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from livekit.plugins.turn_detector.multilingual import MultilingualModel
            inner = MultilingualModel()
        except Exception as e:  # noqa: BLE001
            logger.info(f"turno semántico: sin modelo ONNX interior ({e!r}) — capa léxica sola")
    return SemanticTurnDetector(inner)
