"""Importing this package registers every LLM provider (import side effects).

Standard model providers + zaelar's brains. Tras el entierro de Hermes (V2-009) el cerebro propio es **nucleo**
(zaelar v2 «Colmena» FlashBrain — código propio, sin Hermes; EPIC-v2-colmena, default con BRAIN=nucleo). Quedan
además dos baselines sin memoria/tools: `direct` (una llamada OpenAI-compatible pelada) y `local` (Ollama on-
machine). El provider nucleo envuelve el contrato de brain de zaelar (voice/tag_protocol, speech, brain_notes).
"""
# `glm` (Z.AI) SE RETIRÓ el 2026-08-30: Z.AI es SOLO del Brain Worker, dentro de Claude Code —
# norma del operador. Además era un razonador ofrecido como cerebro de VOZ, que ya violaba la regla
# dura de «el cerebro de voz no razona». Su catálogo vive en `nucleo/workers/providers.py::KNOWN`.
from . import aimlapi, claude, direct, gemini, local, nucleo, openai  # noqa: F401
