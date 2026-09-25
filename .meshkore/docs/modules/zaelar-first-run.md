# The first run — what happens between opening Zaelar and it speaking your language

*Mechanism, public. The product decisions behind it live in the operator's private workspace; what is
described here is what the code does, which is what somebody self-hosting needs.*

A brand-new install has no language, no voice, no memory and no idea where to put a file. This document is
the whole ceremony in order, what gates each step, and the two rules that shaped it.

## The two rules

1. **Nothing speaks before a language is chosen** (2026-09-11, V2-672). The engine used to greet in English
   and ask, out loud, which language you wanted — so the one sentence a person might not understand was the
   one asking which language they understand. The voice session still starts (the microphone has to be live
   to hear a spoken answer); it simply says nothing until a language exists.
2. **Nobody is asked what the deployment already knows** (V2-671). Whether this process runs on somebody's
   laptop or on a hosted Machine is readable (`config/profiles.deployment()`); which providers it uses comes
   from the canonical model table (`config/models.default.json`). Neither is a question for a person who has
   not even chosen a language yet.

## The sequence

```
boot ─► voice session starts, SILENT ─► language picker (blocking) ─► lock
                                                                      │
                        ┌─────────────────────────────────────────────┤
                        ▼                                             ▼
              bundle + alias pack generate            step two: where your files go
              (instant for en/es)                     (self-host only · skippable)
                        └─────────────────┬───────────────────────────┘
                                          ▼
                              the veil lifts, and it greets you
                                     in your language
```

### 1 · The gate

`i18n/init/detect.should_detect()` is True only while `stt_language` is empty in `config/settings.json`. It
is what the frontend asks through `GET /api/i18n/state` (`chosen: false`) and what the voice pipeline asks
before deciding whether to greet. One fact, one place — which is also why a factory reset has to clear that
key for the ceremony to run again (`config/settings.factory_reset`).

### 2 · The picker

`frontend/app/components/LanguageOnboarding.js`, over `i18n/catalog.py`. It carries **no words of ours**: a
mark of a person speaking says what the screen is for, and each row is a flag plus the language's own native
name — the only label its speaker is guaranteed to read. Forty languages; the two the repo SHIPS (`en`, `es`,
= `i18n.runtime.PRESET`) are pinned on top, because choosing one of those is instant and everything else pays
a generation. Typing filters the rows. A spoken answer also works: the microphone is live and the server
classifies it like any turn.

### 3 · The lock

`i18n/init/detect.lock(code, onboarding=True)` persists the language through `config.settings.update()` — the
ONE seam, which is also what realigns the TTS voice (below) — sets the memory's canonical language, emits an
SSE `language/detected` event carrying a handful of ALREADY-TRANSLATED strings (`_priority_translate`), then
generates the full UI bundle and, for a non-preset language, the widget alias pack.

### 4 · Step two: where your files go

Self-host only (`GET /api/library/base` → `can_choose`); a hosted Machine's Volume is the storage and is
never asked. It runs *while* the bundle generates, so the wait is spent on a question instead of a spinner,
and its words arrive already translated with the event above.

The validator is the interesting part. `library/paths.resolve()` refuses absolute paths on purpose —
everything reaching it comes from magnet payloads, model output and query strings. This step needs to ACCEPT
one, so it is a **second door with a different provenance** (a person, on their own machine, once) and its own
`library/paths.check_base()`, which refuses rather than repairs:

| refused | reason |
|---|---|
| a relative path | `not_absolute` — never silently reinterpreted as relative to something |
| a folder that does not exist | `missing` — "I'll create it for you" turns a typo into a tree nobody meant |
| the filesystem root, or `$HOME` itself | both are "the whole machine" |
| a system directory | checked on the RESOLVED path, so a symlink cannot smuggle one past |
| a folder this process cannot write to | `not_writable` |

`library/folder_dialog.py` opens the OS picker where one can be drawn (macOS `osascript`, Linux
`zenity`/`kdialog`, Windows `FolderBrowserDialog`) and answers `unavailable` where it cannot — headless, a
container, SSH. The typed path goes through the same validator, so nothing depends on which door was used.
The step is skippable, the choice is undoable (an empty value restores the default), and `base()`
re-validates on every read: an unplugged disk falls back to the workspace instead of writing into nowhere.

**The veil is held BEFORE the language POST, not after it (V2-772).** For a preset language (en/es) the engine
has nothing to generate, so its `ready` lands while the click's POST is still in flight. Held only after the
POST, the close was already scheduled and the folder step flashed for a second and went — the operator, after a
reset: *«la ha mostrado durante un segundo y ha pasado de ella directamente al escritorio»*. The delayed close
also re-checks the holds when it fires.

### 5 · The voice

`config/settings.update()` realigns `assistant_voice` whenever the language moves and the current voice is
not right for it, for whichever TTS provider is live:

- **Kokoro** — the language catalog's native voices (`voice/engine/core/langs.py`).
- **ElevenLabs** — `voice/engine/speech/elevenlabs_voices.py`: the account's own voices plus the Voice
  Library filtered to that language (`/v1/shared-voices?language=…`), natives first, multilingual ones kept
  last so a language with no native voice can still speak. Cached on disk with a 7-day TTL; the network is
  never touched on a turn.
- **Cartesia** — genuinely multilingual: one voice speaks every catalog language, so nothing is realigned.

The question asked is `voices.voice_is_aligned(provider, voice, lang)`, which is **not** "is it in the list":
the ElevenLabs list deliberately keeps fallbacks, so a Castilian voice IS in the English list and a
membership check would find it and change nothing — which is exactly the defect this replaced.

**One pinned default per shipped variant (V2-772).** The ElevenLabs default used to be «the first native voice
with the region's accent» in the API's own order — the account list as returned, then the Voice Library sorted
by *trending*, re-fetched weekly — so it moved, and a library voice that stopped trending was dropped and
replaced. It is now a table, `elevenlabs_voices._PINNED`, chosen against the live library (2026-09-25) as one
coherent set: middle-aged male, CONVERSATIONAL use case, native to the variant, each synthesis-tested.

| Variant | Voice | Id | Source |
|---|---|---|---|
| en-US | Eric — «Smooth, Trustworthy» | `cjVigY5qzO86Huf0OWal` | premade (every account) |
| en-GB | George — «Warm, Captivating» | `JBFqnCBsd6RMkjVDRZzb` | premade (every account) |
| es-ES | Martin Osborne — «Round and Polished», dialogue | `LlZr3QuzbW4WrPjgATHG` | Voice Library |
| es-419 | Mauricio — «Neutral Spanish, calm and conversational» | `94zOad0g7T7K4oa7zhDq` | Voice Library |

A bare code (`en`, `es`) means its first variant. The pinned rows are always first in `for_language()`, so a
pinned voice is never «not on today's list». The accent-preference rule stays as the fallback for a language
without a pin. Changing a default is editing this table; the operator's own choice in the ⚙ always wins.

**The prewarmed TTS is re-pointed when the session starts.** The TTS is built in `prewarm`, in the idle worker,
before any language exists, and the session reuses it. Measured on a factory reset: worker built 21:29:38,
language locked 21:29:55, job 21:29:57 — no session existed at lock time for `live_tts.apply_voice` to reach, so
that session spoke with the voice of an older state (heard as «random»). `agent.py` now calls
`live_tts.apply_current()` right after `attach`.

**The ⚙ says what each voice is**: `voices.describe_voice()` → «Eric · English (US) ♂», with the variant's
native name from the picker catalog. A bare «Elena» hid that she is Peruvian.

### 6 · The greeting

`onboarding.confirmSpoken`, in the chosen language, spoken by `server/i18n_api.py` after the lock. On a
normal (non-first) start the kickoff is the memory-aware greeting in `voice/engine/pipeline/agent.py`.

## What any reset puts back (V2-772)

*«Después de un reset o una inicialización de cero, el agente empieza arrancado: el orbe escuchando, el
micrófono activo, el altavoz activo y el word activation desactivado… aunque estuviera antes diferente.»*
Three places hold those switches, and every reset — not only «start from zero» — resets all three:

| Switch | Lives in | Reset by |
|---|---|---|
| ⏻ power | `sys_kv` `run:state` | `scripts/reset-memory.sh` step 5b, every run |
| attention mode / window (wake word) | `config/settings.json` | `config.settings.reset_switches()` (key dropped → default `always`) |
| mic/speaker mute, orb dock, layout | the browser's `localStorage` | `first-run.js::takeoverOnReset` — the reset bumps a wipe epoch; each shell sweeps our namespace once per epoch and reloads |

After the language is chosen the engine emits `run start` with `src: "language"` and the shells unmute. The bus
payload is FLAT (`observer.emit` merges `extra` into the event): the reader looked for `d.extra.src`, never
found it, and the mic and speaker stayed muted until clicked by hand. `sse.js::field()` reads the flat field.

## What is NOT part of the first run

- **Choosing a profile.** Retired (V2-671). The panel is still reachable from the TopBar's 🧭 for someone who
  deliberately wants to move their models onto their own machine.
- **Credentials.** They live in the ⚙, under the connector that needs them, at the moment it is connected —
  not in front of somebody who has not seen the product yet.

## Tests

| node | what |
|---|---|
| 8.5 | the deployment picks the profile; the bare-boot voice stack matches the model table |
| 8.6 | nothing speaks before a language is chosen; the catalog; the voice follows the language |
| 8.7 | where the agent's files live — the validator, the endpoints, the cloud refusal |
| 4.162 | the picker and the folder step, RENDERED |
