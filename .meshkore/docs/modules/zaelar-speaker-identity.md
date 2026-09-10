# Speaker identity — knowing WHO is talking (V2-651)

**Status: F0 only — SHADOW MEASUREMENT. Nothing is gated, no memory is written, no prompt changes.**
This document describes the MECHANISM. What the product does with it (account policy, privacy of the
commercial offering) is not described here — see the workspace root's private context.

## Why it exists

The mic is always open and the room is not the operator. Three failures follow from having no idea who
is speaking, and all three were measured on a real session (2026-09-10, `0f9d2a13`, with a TV on):

1. **Identity theft by accident.** A third party saying *"no, I'm not Ricard, I'm Joan"* reaches the same
   write path as the operator. Today's protection (`nucleo/memory_agent/gates.py::_plausibility_demote`,
   V2-033) is a PLAUSIBILITY guard keyed on a value contradiction, not on who spoke — so it holds when a
   name is already established and **fails in two cases**: an empty profile (the guard returns early —
   "no conflict in an empty profile") and an explicit correction (`ingest.py`'s `_is_corr` bypasses it by
   design). A speaker label is the missing discriminator.
2. **The room drives the agent.** Room speech carrying a command reaches the canvas fast-paths (the class
   V2-647 closed on the client side).
3. **A TV is a human voice.** Energy gates and noise suppression cannot separate it — only a voiceprint can.

## Architecture: the BROWSER carries the cost

Operator directive (2026-09-10). The fingerprint is computed **client-side**; only a tiny verdict (a label
plus scores) would ever cross to the backend, never the audio to analyze. In a cloud deployment the backend
runs on the server and the browser on the person's own laptop, so this keeps the per-session CPU off the
server; in a local self-host run it is one machine and the split costs nothing either way.

```
mic ──► AnalyserNode (audio.js, already owned by the visualiser)
          └─► SpeakerID.tick()            ← rAF, browser
                ├─ energy Segmenter        (the LiveKit engine gives the client no VAD signal)
                ├─ frameFeatures()         pitch · spectral centroid · rms
                ├─ snapshot() per segment  median pitch, mean centroid/rms
                └─ classify() vs profiles  {operator, known:<id>, …}
                      └─► onUtterance ──► api.clientLog("🎙️ speaker", …) ──► observability
```

## Files

| File | Role |
|---|---|
| `frontend/app/lib/speaker-id.js` | Pure DSP core + the `SpeakerID` AnalyserNode adapter |
| `frontend/app/services/session-lk.js` | `_startSpeakerShadow()` / `_stopSpeakerShadow()`, the rAF, the log |
| `tests/browser/unit/voice/test_speaker_id_shadow.{mjs,py}` | Node **4.150**, 8 groups |

The pure half (`rmsOf`, `pitchOf`, `centroidOf`, `frameFeatures`, `snapshot`, `buildProfile`, `matchScore`,
`distancesTo`, `classify`, `Segmenter`) uses no browser globals, so it is driven directly from Node with
synthetic frames; the adapter is driven through a fake AnalyserNode. Nothing in the test needs a browser.

`frontend/app/lib/speaker-gate.js` is the ORPHANED predecessor (2026, Pipecat path): still imported by the
legacy `session.js`, dead on the LiveKit engine, where `session-lk.js::getGate()` returns `null`. Its own
header planned this upgrade. It was left in place rather than deleted — the legacy path still imports it.

## Multi-profile from the start

`classify(snapshot, profiles)` scores against a MAP, not a single profile. The operator is one entry today;
household voices become entries under `known:<id>` when F2 adds them, and an ONNX embedding
(CAM++ via onnxruntime-web) replaces `frameFeatures`/`matchScore` behind the same interface without the
callers changing. That shape is deliberate: it is what an embedding classifier needs anyway.

## Reading the shadow log

Rows arrive as observability `client` events labelled `🎙️ speaker`, one per speech segment:

| Field | Meaning |
|---|---|
| `label` | `enroll` · `operator` · `other` · `known:<id>` |
| `op_score` | the coarse VOTE against the operator's profile (0, ⅓, ⅔ or 1) |
| `d_mean`, `d_pitch`, `d_centroid` | **continuous** z-distances (0 = dead on the profile, 1 = one σ out) |
| `rms_ratio` | loudness vs the enrolled level (≪ 1 = far from the mic) |
| `pitch`, `centroid`, `rms` | the raw snapshot, for offline analysis |

Two more rows exist so that *silence in the log* is itself readable — added after a measured failure
(2026-09-10: real voice sessions with the mic open produced ZERO verdicts and nothing said why):

| Row | Says |
|---|---|
| `🎙️ speaker: armado` | the shadow started. **Its ABSENCE means the browser tab is running an older build** — the ES module is cached per page load, so a hard reload is required after any change here |
| `⚠️ speaker: no arrancó` | arming threw. Previously swallowed by a silent `catch`, which is how a module is born dead and nobody notices |
| `🎙️ speaker: nivel` | one-shot ~25 s in: the loudest frame seen vs the segmenter's start floor. If `peak_rms` < `start_floor`, no segment can ever open on that mic and the calibration — not the code — is what needs changing |

So: no `armado` row → stale tab. `armado` but no verdicts → check the `nivel` row.

**Use `d_mean`, not `op_score`, to choose a threshold.** `matchScore` is a three-criteria vote, so it can
only return four values — measured across 60 distinct synthetic voices it produced exactly THREE. That is
enough to classify and useless to threshold against, and choosing F1's threshold from real sessions is the
entire purpose of this phase.

## Two things that must never happen, and how they are prevented

- **The agent's own voice must never be enrolled as the operator.** TTS comes out of the speakers and back
  into the mic; echo cancellation attenuates it and does not remove it. `SpeakerID.suppressed()` (wired to
  `store.botSpeaking()`) discards anything in flight and fingerprints nothing while zaelar talks.
- **The shadow must never change behaviour.** It writes no memory, gates no turn, sends no data channel
  message, and touches no prompt. It is killable with `?nospk=1` or `localStorage.zaelar_spk_shadow=0`.

## Measured cost

`pitchOf` (autocorrelation over 70–400 Hz on a 2048-sample frame) measured **0.91 ms/frame**; throttled to
every other rAF frame and only on speech, that is ~27 ms/s ≈ **2.7% of one core**, and only while somebody
is talking. Silence costs an RMS pass. It runs on the main thread — within a 16 ms frame budget, but an
AudioWorklet is the escape hatch if an embedding model later makes this heavier.

## Known limits (measured, not assumed)

- **A continuously talking TV breaks silence-based segmentation.** The segmenter closes a segment on a
  silence hangover; a TV that never stops means boundaries need not align with speaker changes.
- **One STT utterance can contain TWO speakers.** Measured verbatim in the session above: *"a nivel, no
  solamente en España, televidentes, en el Se está oyendo la tele al mismo tiempo, de ruido de fondo"* —
  TV text and the operator's own sentence fused into a single transcript. A per-utterance label cannot
  express that; overlapping speech is the known hard case of any single-track approach.
- **The profile is not persisted.** Every page load re-enrolls, so a session's numbers are relative to that
  session's enrollment. Persistence arrives with F2's voices file.
- **Auto-enrollment trusts whoever speaks first.** Acceptable while measuring; F2 replaces it with
  enrollment gated on DIRECTED turns or an explicit one-time ceremony.
- **Far-field and short utterances degrade any speaker verification**, which is exactly why the hard
  voice-lock is opt-in and last (F3), never a default.

## The interaction that matters most for F1

`voice/attention.py::evaluate_content` short-circuits inside the active conversation window — *within the
window the turn is directed, full stop* (V2-531, deliberate: it stopped the gate going deaf mid-dialogue).
Measured consequence with a TV on: room lines were judged `👂 dirigido a zaelar` and answered. So a speaker
check must be consulted **before** that shortcut, or a perfect voiceprint would still change nothing. That
ordering is an F1 decision, not something F0 touches.

## Not built

F1 identity shield (operator-voice-only writes to identity slots and `state`), F2 the known-voices file and
the presence line, F3 the opt-in voice-lock. The phase plan lives in the initiative (not published).
