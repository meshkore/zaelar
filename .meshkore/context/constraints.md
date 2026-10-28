---
title: Constraints
updated: 2026-10-25
status: stable
---

# Constraints — hard rules

**Always**:
- Any user, any request, any language: a change bounds a CONSEQUENCE, never a judgement; the class is fixed, never
  the case; what depends on the speaker lives in data (`context/principles.md` — read before any engine change).
- Brain is zaelar's OWN (`nucleo/`, default `BRAIN=nucleo`); model routing lives ONLY in `config/v2.py` (`fast` + `code_agent` sections); `config/settings.py` handles STT/TTS/voice/language and nothing else.
- Layers stay independent: widgets never touch the voice core; the widget circuit is self-contained.
- ONE agent is open on SEVERAL screens at once (the operator's computer and phone, one conversation). Every widget —
  native, generated or the user's own — declares `"screens"`: `shared` (a reflection of data, open anywhere) or
  `single` (takes the device's sound or picture: lives on one screen, and asking for it from another screen moves it);
  `runtime.output` ⇒ `single`. A widget is not done until it passes the two-screen test, automatic and manual:
  `.meshkore/docs/ops/zaelar-two-screen-test.md`.
- New top-level modules are declared in `.meshkore/public/cluster.yaml` before creation.
- Audio bugs start at the AudioProbe RMS meter in `/debug` — never guess STT vs echo vs brain.
- Icons are SVG from `lib/icons.js` (no emoji as UI chrome); status colors are `--hb-ok/--hb-warn/--hb-risk` tokens; primary buttons share one gradient.

**Never**:
- NO reasoning model on the voice path — FlashBrain MUST be non-reasoning (latency hard rule).
- No custom watchdog on the realtime voice path; proactivity comes from the nucleo loop/cron.
- No business logic in `frontend/`; no fresh hex for status colors; no per-component icon-button sizes.
- No external agent or cloud dependency on the default path — local-first, cloud is opt-in.
- Never log or commit secrets; credentials live in the credential store (`config/credentials.py` is its single writer).
