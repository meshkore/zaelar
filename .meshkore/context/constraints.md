---
title: Constraints
updated: 2026-09-14
status: stable
---

# Constraints — hard rules

**Always**:
- Brain is zaelar's OWN (`nucleo/`, default `BRAIN=nucleo`); model routing lives ONLY in `config/v2.py` (`fast` + `code_agent` sections); `config/settings.py` handles STT/TTS/voice/language and nothing else.
- Layers stay independent: widgets never touch the voice core; the widget circuit is self-contained.
- New top-level modules are declared in `.meshkore/public/cluster.yaml` before creation.
- Audio bugs start at the AudioProbe RMS meter in `/debug` — never guess STT vs echo vs brain.
- Icons are SVG from `lib/icons.js` (no emoji as UI chrome); status colors are `--hb-ok/--hb-warn/--hb-risk` tokens; primary buttons share one gradient.

**Never**:
- NO reasoning model on the voice path — FlashBrain MUST be non-reasoning (latency hard rule).
- No custom watchdog on the realtime voice path; proactivity comes from the nucleo loop/cron.
- No business logic in `frontend/`; no fresh hex for status colors; no per-component icon-button sizes.
- No external agent or cloud dependency on the default path — local-first, cloud is opt-in.
- Never log or commit secrets; credentials live in the credential store (`config/credentials.py` is its single writer).
