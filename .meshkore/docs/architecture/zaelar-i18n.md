# Multilingual (i18n) subsystem — V2-089

Zaelar adapts to **any language in the world**. English is the base; Spanish ships preset; every other language
is **generated on the fly** by an LLM the first time an operator speaks it, and topped up on every upgrade. The
UI, the operator↔agent conversation, and (for catalog languages) the voice all follow the operator's language —
while everything the product shows to the **outside world stays English**.

## The three language axes (do NOT conflate them)

1. **Outward / clusters** → **always English** (international image). `nucleo/flash/prompt.py`: text inside
   `[[cluster.send]]` defaults to English; only mirrors the peer's language if the peer wrote in it.
2. **Operator ↔ agent** → the **operator's language** (`ZAELAR_LANGUAGE`), any code. Detected automatically on
   first run; overridable in ⚙.
3. **UI (frontend)** → follows axis 2. This is what the i18n subsystem below delivers.

A fourth, narrower axis is the **voice catalog** (`voice/engine/core/langs.py`): STT recognition + TTS voice +
the brain's spoken reply directive. It ships **es/en only** (each needs a verified native voice/model). It is
DELIBERATELY decoupled from the UI language: `i18n.runtime.active_code()` reads the raw `ZAELAR_LANGUAGE` (any
code) so the UI can be Arabic while STT/TTS fall back to the es/en catalog. They coincide for es/en. Adding full
spoken support for a new language = one `LangSpec` + a native voice (separate, larger task).

## INITIALIZATION vs EXECUTION (the organizing principle)

The subsystem is split so nobody inherits a tangle of "when does this run":

```
i18n/                         self-contained package
├─ bundles/                   DATA (repo, source of truth): en.json = manifest, es.json = preset
├─ runtime.py                 EXECUTION — hot path. Import-cheap, deterministic, NO LLM. Serves UI strings for
│                             the active language, reports state, diffs missing keys. All the running server touches.
├─ store.py                   persistence of GENERATED bundles (<workspace>/i18n/generated/, gitignored)
└─ init/                      INITIALIZATION — occasional, may call an LLM/STT, runs at boot/first-run/switch/upgrade
    ├─ __init__.py            prepare(code) — THE ONE idempotent entry the boot/switch/upgrade path calls
    ├─ ensure.py              ensure_language(code): diff manifest vs generated → decide what to (re)generate
    ├─ generate.py            LLM translation of missing/changed keys (nucleo.memllm "i18n" task, default gpt-4o)
    ├─ detect.py              first-run language detection + lock() — the onboarding sequencing lives here too
    └─ aliases.py             (V2-101) per-language voice-command alias packs for the system surfaces
```

- **Execution** = `i18n.runtime` + the frontend `core/i18n.js` `t()`. Never blocks, never calls an LLM.
- **Initialization** = `i18n.init.*`. Only runs a few times (boot, first-run detect, a language switch, an
  upgrade), behind the "preparing language…" boundary. This is where the LLM and STT live.

The HTTP surface (`server/i18n_api.py`) is thin: `GET /api/i18n/state` (now also reports `chosen: bool`, V2-101 —
whether ANY language has ever been explicitly picked) + `GET /api/i18n/bundle/{code}` hit the runtime;
`POST /api/i18n/ensure/{code}` hits init; `POST /api/i18n/choose/{code}` and `POST /api/i18n/detect-text`
(V2-101) are the onboarding modal's two non-voice escape hatches — a quick-pick chip and typed free text.

## Best of both worlds: preset + generated

- **Preset** (`en`, `es`) ship in the repo as JSON — instant, deterministic, hand-quality. `en.json` is also the
  **manifest**: the canonical set of every UI string key → its English text.
- **Generated** (any other code) are produced by `generate.translate()` via a strong LLM (placeholders,
  punctuation and technical tokens preserved), stored per-language in the workspace, and cached in the browser
  (localStorage) after first fetch so repeat boots paint instantly.

## The ONE idempotent function: first-run AND upgrade

`i18n.init.prepare(code)` → `ensure_language(code)`:

- `runtime.missing_keys(code)` compares the manifest to the generated bundle using a **per-key English snapshot**
  stored in each generated bundle (`src`). A key is "missing" if it's absent OR its English source changed since
  it was translated.
- **First-run** (brand-new language) → all keys missing → translate all.
- **Upgrade** (a release added/changed keys, or shipped a new widget with new words) → only the new/changed keys
  are missing → translate just those.
- Same function, same path. Preset or already-current → instant no-op. `MANIFEST_VERSION` is the coarse
  browser-cache buster.

## First-run auto-detection → first-run ONBOARDING (V2-101, 2026-08-16)

"We're an AI — we should figure out the operator's language." Used to be purely passive (guess silently from
whatever the operator said first, no gate on the UI); is now a deliberate, blocking **ceremony** on a genuinely
first-ever boot — `i18n.init.detect`:

- `should_detect()` is True only while no language has been chosen (no persisted `stt_language`). A manual ⚙
  choice or a prior lock turns it False forever — auto-detection never overrides a deliberate choice. There is
  no separate "first boot" flag; this IS the first-boot signal, both for the modal (frontend, via
  `GET /api/i18n/state`'s `chosen` field) and for the kickoff branch below.
- On first run, `whisper_local` transcribes in **auto mode** (`language=None`) so a non-Latin operator is
  transcribed correctly. `voice/engine/pipeline/agent.py`'s kickoff branch checks `should_detect()` BEFORE
  building its greeting: if true, zaelar's first turn is forced English-only — a brief greeting asking what
  language to use, nothing else (no name, no capabilities) — instead of the normal memory-aware greeting.
  The frontend blocks the whole UI behind `LanguageOnboarding.js` for the same turn, so voice and UI open the
  ceremony together. `_maybe_detect_language`'s `_on_transcript` handler (still off the hot path) then
  classifies the ANSWER; 3 consecutive unclear answers fall back to locking `"en"` rather than leaving a
  first-run operator stuck behind the modal forever. The modal also offers two non-voice escape hatches
  (`POST /api/i18n/choose/{code}` for a quick-pick chip, `POST /api/i18n/detect-text` for typed free text) for
  mic-denied/noisy-room/keyboard-preferring operators.
- `classify(text)`: instant Unicode-script heuristic for non-Latin (ar/zh/ja/ko/ru/el/hi/th/he); a constrained
  LLM classify for Latin scripts.
- `lock(code, onboarding=False)`: persist `ZAELAR_LANGUAGE`, set the memory's canonical language, `prepare(code)`
  (generate the UI bundle if new), emit an SSE `language` event → the frontend `applyLang(code)` flips the whole
  UI live (no reload). Voice realigns on the next reconnect. With `onboarding=True`: emits the SSE event TWICE —
  `phase:"detected"` fires EARLY (before the possibly-slow full bundle generation), carrying an
  already-translated `onboarding.loading` line from a 1-key PRIORITY translate (so the modal never shows a bare
  spinner with no words); `phase:"ready"` fires once the full bundle AND the alias pack (previous section) are
  both done, closing the modal. Also returns `confirm_text` (the bundle's `onboarding.confirmSpoken`, translated
  as part of the normal batch) for the caller to speak via `voice.proactive.notify()` — respects the "never talk
  over the operator" quiet-wait gate rather than a raw `session.say`. For en/es this whole sequence collapses to
  a blink (PRESET, nothing to generate); for anything else it's a real wait, deliberately showing only the one
  generic translated line — no technical detail leaks into what the operator sees.

## Frontend runtime

`frontend/app/core/i18n.js`: `t(key, params?)` reads the reactive `store.lang()` signal, so every `t()` used
inside a `dom.js` function-prop/child re-renders the instant the language changes. Resolution:
active-language bundle → English base → the key itself (English is always a safe net). Bundles are fetched from
the backend and localStorage-cached. `initI18n()` reconciles the UI language with the backend's active language at
boot. All 564 UI keys live in `i18n/bundles/en.json` (+ es.json); the parity test
`tests/browser/unit/i18n/test_bundles.py` guards en/es key/placeholder alignment.

## Multilingual MATCHING vocab (aliases / router / wake-words) — the strategy

Voice-match vocabulary is a **cross-cutting concern with a clear rule**:

- The **LLM router/resolver is the language-agnostic mechanism**. A non-es/en operator's "open the memory map"
  is understood by the brain and routed correctly regardless of language. So the system FUNCTIONS in any language
  out of the box.
- The hardcoded **es/en aliases** (`widgets/system_surfaces.py`, `frontend/app/core/system-surfaces.js`) and
  **regex fast-paths** (`voiceCommands.js`, `nucleo/flash/router.py`, `voice/attention.py`) are ~50 ms **local
  accelerators**, not requirements. For an uncovered language they simply don't fire → the brain handles the
  intent (a touch slower). This is the pre-existing "es/en backstop, LLM is the multilingual mechanism" design.
- **The system-surfaces alias-pack extension point is BUILT (V2-101, 2026-08-16).** `i18n/init/aliases.py`
  (`ensure_aliases(code)`) generates, in ONE batched LLM call, 4-6 natural voice-command words per system
  surface (the 9-10 entries in `widgets/system_surfaces.py`) for any non-preset active language, persisted to
  `i18n/generated/<code>.aliases.json` (sibling to the UI bundle). `widgets/system_surfaces.py::surfaces()`
  consults it ADDITIVELY — the hardcoded es/en list is never replaced, only extended — so the resolver's
  matching logic (`widgets/runtime.py::identify`) needed zero changes, exactly as this section originally
  anticipated. Wired into the **first-run language onboarding** flow (`i18n/init/detect.py::lock(...,
  onboarding=True)`), not into a plain `⚙` language switch — a manual switch stays exactly as cheap as it
  always was; alias-pack generation is scoped to the setup ceremony, not a side effect of every locked language.
- **Deliberately still NOT built: `voice/attention.py`'s hard-interrupt vocabulary and
  `nucleo/flash/router.py`'s `looks_like_*` backstop regex.** These are safety/precision-critical
  deterministic guards with real incident history behind them (the anti-garble identity gates, the
  hard-stop-must-never-be-buried invariant) — auto-translating a regex that decides "does this utterance mean
  STOP RIGHT NOW" via LLM is a materially different, higher-risk effort than translating a widget's voice
  aliases, and deserves its own dedicated initiative with its own testing. Non-preset languages correctly fall
  back to the LLM router for these cases today — just a bit slower, the accepted tradeoff either way.

## Adding a UI string / shipping a widget with new words

Add the key to `i18n/bundles/en.json` (+ the Spanish in `es.json`). That's it: every generated language picks up
the new/changed keys on its next `prepare()` (boot/upgrade). Bump `MANIFEST_VERSION` when the key set changes so
browser caches refresh.
