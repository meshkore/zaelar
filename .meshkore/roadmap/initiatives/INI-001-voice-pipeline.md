---
id: INI-001
title: Voice Pipeline
status: done
owner: ricart
modules: [voice, brain, server]
updated: 2026-06-30
---

## Goal

Stable, low-latency STT→Hermes→TTS pipeline over WebRTC. Always-on, always-listening.

## Scope

- Turn detection and control (voice/turn_control.py)
- Hermes ACP client (brains/hermes/acp_client.py, brains/hermes/llm_processor.py)
- STT local-first (voice/stt.py)
- Tag protocol for structured responses (voice/tag_protocol.py)
- Brain fallback when Hermes unavailable (voice/llm.py · BRAIN=direct)

## State

Running locally. No prod deploy (destroyed 2026-06-30).
