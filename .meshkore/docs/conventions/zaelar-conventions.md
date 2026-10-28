---
title: Zaelar Conventions
category: conventions
updated: 2026-07-22
owner: ricart
status: current
---

## Code

- Python 3.11+, async-first (asyncio / LiveKit Agents).
- No type annotations required but preferred on public APIs.
- No comments unless the WHY is non-obvious.
- **No reasoning models on the voice path (hard rule).** The FlashBrain (voice layer) model MUST be non-reasoning.

## Brain & model config (v2 «Colmena»)

- The brain is zaelar's OWN, the `nucleo/` module (default `BRAIN=nucleo`). `active_brain()` lives in
  **`config/v2.py`** (env-first `BRAIN` → store `flags.brain` → default `nucleo`); `direct`/`local` are baselines.
- **Model routing lives in `config/v2.py`, chosen per invocation** — the `fast` section (FlashBrain voice model,
  `FAST_*`, always non-reasoning) and the `code_agent` section (SlowBrain CodeAgent, `CODE_AGENT_*`). `config/
  settings.py` handles ONLY STT/TTS/voice/language — NOT the brain model.

## Modules

- Each top-level package (`frontend/`, `server/`, `voice/`, `nucleo/`, `memory/`, `bus/`, `widgets/`, `config/`, …)
  is a MeshKore module.
- New modules must be declared in `.meshkore/public/cluster.yaml` before creation.

## Frontend — design system (app shell)

The ONE visual language (V2-689, legibility first V2-691): tokens in `frontend/app/core/palette.css` and
`frontend/app/core/components.css` (elevation ladder, status colours, the vivid range per calendar/kind), the widget
header standard (`zaelar-widget-header-standard.md`), and the generator's guidance pointing at the same tokens so a
user-made widget follows the line without being told. Visual changes are agreed before merge.

The app shell (TopBar, panels, modals — everything EXCEPT the orb/eye and the camera unit, which are the
reference look) follows a few explicit rules so no component invents its own. The palette is the existing blue
`--hb-accent` / teal `--hb-accent2`.

- **Icons are SVG, one visual language, ONE shared file.** `frontend/app/lib/icons.js` — `viewBox 0 0 24 24`,
  `stroke="currentColor"`, `stroke-width 2`, round caps/joins (the language Orb.js already used for the eye).
  **No emoji, no Unicode dingbats (◉⌗◷✕▶‹≣⛓🟢🔑🧭 …) as functional UI chrome** — import the matching icon from
  `lib/icons.js` (add one if it's missing; keep the same stroke spec) and drop it in with `raw(ICON)` (or, inside an
  `innerHTML` template string, the bare exported string — it's already valid markup). **Exception: real brand/
  platform marks** (WhatsApp, Telegram…) stay their authentic logo, never re-drawn in this language. Decorative
  glyphs embedded in a prose sentence (a celebratory 🎉, a trailing ✓ in a button LABEL) are acceptable — a
  chrome/button icon (header, toggle, close) is the bar for converting.
- **Two icon-button sizes, not six.** `.ic` (34×34, radius 9 — TopBar's own project controls) and `.hb-icbtn`
  (30×30, radius 9 — the shared utility button for close/refresh/delete/zoom-style controls inside panels and
  modals: StatusPanel, CronPanel, ChatWall, MemoryMap, DebugPanel, VaultModal). Add the `hb-icbtn` class alongside
  a component's own class (e.g. `class="cw-x hb-icbtn"`) so state modifiers (`.danger`, `.on`, `.mm-close`) still
  layer on top. The orb's own `.orbic` (frameless, 22px svg) is a THIRD, deliberate exception — it's the eye, leave
  it alone.
- **Semantic status colors are tokens, not per-component hex.** `--hb-ok` / `--hb-warn` (+ the pre-existing
  `--hb-risk`) — single value across themes, same pattern as `--hb-accent`. Never type a fresh green/amber hex for
  a health dot, a pulse glow, or a latency number; reuse these three. A status **dot** is a plain CSS circle
  (`.st-dot` + a `st-dot-ok/warn/error` modifier), not an emoji glyph (🟢🟡🔴 can't be recolored and renders
  inconsistently per platform/font).
- **One primary-button treatment.** `linear-gradient(135deg, var(--hb-accent), var(--hb-accent2))`, white text —
  every "primary CTA" button (send, save, create, confirm) uses this SAME gradient. No one-off hex mixed into the
  gradient (`#5b86ea`, `#ef6a6f` …) and no flat single-color fallback that only one button used.
  `--hb-update`/`--hb-update2` are the separate, deliberately-different ATTENTION gradient for the Hermes
  update banner (an "action needed" surface, not a primary action).
- **Log/console surfaces stay dark by convention.** `--hb-console-bg/-line/-ink/-muted` — a terminal/log view (the
  Hermes update log today; DebugPanel's own log could adopt these later) reads the same in light or dark app theme,
  same as a real terminal does. Don't theme-follow these; don't hardcode fresh hex for them either — use the tokens.
- **Widget kit** (`hbk-*` in `styles.css §WIDGET KIT`, documented in `widgets/AGENTS.md`): when a widget is
  touched, migrate its hand-rolled card/badge/button CSS to the kit as part of that change.
- **Scope**: these rules govern the app shell (TopBar, StatusPanel, CronPanel, ChatWall, ConfigPanel,
  SettingsModal, WizardModal, VaultModal, MemoryMap, DebugPanel). Widgets adopt the shared icons widget by widget,
  as each is touched, rather than in a big-bang rewrite.

## Test layout (central `tests/` tree, by suite then test type)

Tests live in a **central `tests/` tree** at the root, grouped by SUITE (domain) and then by TYPE — never mixed
with a module's source:

```
tests/
├── memory/
│   ├── unit/          # logic of ONE module, in-process, no async queue or HTTP
│   ├── integration/   # several pieces together (queue+writer, async facade, fs/episodic)
│   └── e2e/           # full flow / HTTP endpoints through the stack
├── agent_headless/    unit/ · e2e/ · harness/
├── voice/ · browser/ · connectors/ · search/ · infrastructure/ · …
└── run_testmap.py     the map: domain → use case → channel (nodes N.M)
```

- **Each module's source stays CLEAN** (code only). A new test goes under `tests/<suite>/<type>/`.
- **`tests/` is a package** (`__init__.py` at every level) → pytest resolves up to the repo root, so absolute imports
  (`from memory import api`) keep working and file names never collide.
- How to run anything — single files, a suite, the wide sweep with `tests/watchdog.py` — is in `tests/README.md`.
  With `ZAELAR_EMBED_BACKEND=hash` memory tests do not depend on Ollama; with `MEM_PROCESSOR=0` ingestion is
  deterministic (heuristic).

## First-party vs external (ours vs imported)

Everything in this repo is **first-party (ours)** — including the **brain** (`nucleo/`, «Colmena») and **memory**
(`memory/`). The clearly-bounded external pieces:

- **SlowBrain CodeAgents**: the Claude Code / Codex CLIs invoked by `nucleo/agentes/` are installed software, not
  our code. The repo holds only our `CodeAgent` interface + adapters (`nucleo/agentes/`).
- **Vendored third-party assets**: the WhatsApp Baileys bridge (`connectors/whatsapp/bridge/`, copied+patched with
  `// ZAELAR-PATCH:` markers + `VENDORED_FROM.md`) and `frontend/vad/` (Silero VAD + ONNX runtime). Isolated in
  their own folders.

Rule of thumb: a feature that depends on a specific external system (a connector, an importer, a CodeAgent backend)
is wired **only** through its boundary module (`connectors/`, `nucleo/agentes/`, …) — never woven into `server/`,
`voice/`, `widgets/`, or `frontend/`.

## Configuration is UI-managed (install once, then everything from the interface)

**Product invariant.** A zaelar user installs the product **once** and from then on manages **everything
from the interface** — they never open a terminal or edit an env/config file. Any capability that needs turning on
or credentials (a connector, an integration, a key) MUST expose that setup as a **guided in-app flow**, not as a
documentation step that says "put X in `.env`".

Concretely:
- **First-run WIZARD.** The entry point of "install once" is a setup wizard (`server/wizard_api.py` +
  `frontend/app/components/WizardModal.js`, 🧭): a **capability detector** (`config/doctor.py`, shared with the CLI
  `make doctor` → `.meshkore/logs/system-report.json`) evaluates the machine (hardware, Ollama+models, `claude`/
  LiveKit/Playwright binaries, which keys are set), and a **coordinated profile** (`config/profiles.py`, `local` |
  `cloud`, `remote`=alias) sets the full default set across all config axes at once (voice engine + `config/v2.py`
  routing + memory embed/rerank/processor) in a single `apply()`. The wizard then resolves gaps (one-click installs
  for project-scoped deps, copy-paste commands for system ones) and collects any missing API keys. It auto-opens
  when config isn't validated (`settings.wizard_done`) and is reopenable from the top bar.
- **Frontend-managed config store.** Per-feature runtime config that the user controls lives in a gitignored JSON
  the UI writes: `config/settings.json` (⚙ panel: STT/TTS/voice/language + **attention gate** `attention_mode`/
  `attention_window` + the `zaelar_profile`/`config_profile`/`wizard_done` markers), `config/connectors.json`
  (connector enable flags + credentials, written by the messaging widget) and `config/v2.json` (model routing —
  FlashBrain fast model + CodeAgent + memory). A small module owns each store (`config/settings.py`,
  `config/connectors.py`, `config/v2.py`) with a **redacted public view** (secrets never returned to the frontend —
  replaced by a `<key>_set: bool`).
- **Credential store, single writer.** Core API keys live in `.meshkore/credentials/zaelar.env` (gitignored, chmod
  600). `config/credentials.py` is the ONLY writer (atomic, hot-applies to `os.environ`, redacted `status()` that
  returns presence only). `server/common.py` loads it AFTER `.env` with `override=True` → the store wins.
- **The store WINS over `.env`.** Env vars remain a **power-user / headless fallback** only: read the store first,
  fall back to the env var when the store says nothing. A normal install never touches `.env`.
- **Hot-apply from the UI.** The control API (e.g. `connectors/messaging/server_api.py`
  `POST /api/messaging/{platform}/connect|disconnect`) writes the store AND starts/stops the subsystem in place
  (on the server loop), so the change takes effect without a restart. QR/auth/state then surface live in the widget
  (the desktop auto-polls `GET /widgets/{id}/data`).
- **Guided setup, domestic-user language.** The widget walks the user through it: if credentials are needed, a form
  with numbered, plain-language steps and a link to where to get them (e.g. Telegram → `my.telegram.org` → API
  development tools → copy `api_id`/`api_hash`); then the QR with device-linking instructions; then connected.
- **Every future connector follows this.** Declare its shape in `config/connectors.py` `_DEFAULTS`, its secrets in
  `_SECRET_KEYS`, add its connect/disconnect handling to the messaging API, and add its guided card to the widget.
  Never ship a connector whose only setup path is editing a file.
- **Secrets vault — native modal + hard rules.** The operator-secrets vault ships a
  **native modal** (`frontend/app/components/VaultModal.js`, NOT a widget): create vault (master passphrase),
  unlock (passphrase OR **passkey** biometric — WebAuthn `prf`, Touch ID/Windows Hello), reveal a secret, and
  manage (enrol/revoke this device, change passphrase). It opens on demand from the brain's SSE `kind:"secret"`
  events (`services/sse.js`) or manually via `window.zaelar.vault()`. Backed by `memory/vault_api.py`
  (`/api/vault/*`, loopback on anything sensitive) and `services/vault.js`. **Redacted** public view: the passphrase
  / private key / passkey PRF are NEVER returned to the frontend — only presence/state (`status()`); the secret
  VALUE is fetched over loopback from `/api/vault/reveal`, never via the event bus. **Voice commands change config**
  too ("modo máxima seguridad", "no me digas secretos por voz", "léemelos por voz", `nucleo/flash/vault_rules.py`):
  recognised deterministically as a config change (not chat) and persisted as **HARD user rules** in `state.security`
  — enforced in code, INVIOLABLE, outside the cap-8 of soft **style** rules (which only guide by prompt). The
  modal is the vault's surface. Full detail: [`zaelar-security.md`](../security/zaelar-security.md).

## Commits

- Commit with a pathspec (`git commit -- <paths>`) after checking `git diff --cached --name-only` is empty — several
  sessions share one checkout and one index. Push after every commit; never
  `pull`/`merge`/`reset`/`checkout` to bring a remote version in.
- AI-authored commits end with a `Co-Authored-By: Claude …` trailer (real practice; see the change protocol §5).
- Never commit: `.env`, `config/settings.json`, `config/connectors.json`, `config/v2.json`, `.venv/`, `logs/`,
  `memory/_data/` (the central memory DB — personal). `~/.hermes/memories/USER.md` (operator profile, if present)
  is likewise never committed.

## Sensitive files

See `admission.never_commit` in `.meshkore/public/cluster.yaml`.
