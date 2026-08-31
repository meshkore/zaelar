"""Importing this package registers every LLM provider (import side effects).

Standard model providers + zaelar's brains. After the burial of Hermes (V2-009), the in-house brain is **nucleo**
(zaelar v2 «Colmena» FlashBrain — proprietary code, without Hermes; EPIC-v2-colmena, default with BRAIN=nucleo). Two
additional baselines without memory/tools remain: `direct` (a bare OpenAI-compatible call) and `local` (Ollama on-
machine). The nucleo provider wraps zaelar's brain contract (voice/tag_protocol, speech, brain_notes).
"""
# `glm` (Z.AI) WAS RETIRED on 2026-08-30: Z.AI is ONLY for the Brain Worker, within Claude Code —
# operator policy. It was also a reasoner offered as a VOICE brain, which already violated the hard rule
# that «the voice brain does not reason». Its catalog lives in `nucleo/workers/providers.py::KNOWN`.
from . import aimlapi, claude, direct, gemini, local, nucleo, openai  # noqa: F401
