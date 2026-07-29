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

## Frontend — design system (app shell, 2026-07-22 pass)

The operator flagged the app shell (TopBar, panels, modals — everything EXCEPT the orb/eye and the camera unit,
which were already the reference look) as visually inconsistent: three different icon techniques, six icon-button
sizes, ad hoc status colors, a theme-blind update banner. Fixed by converging on a few explicit rules instead of
each component inventing its own — no new palette (the operator kept the existing blue `--hb-accent` /
teal `--hb-accent2`; only the EXECUTION was fixed).

- **Icons are SVG, one visual language, ONE shared file.** `frontend/app/lib/icons.js` — `viewBox 0 0 24 24`,
  `stroke="currentColor"`, `stroke-width 2`, round caps/joins (the language Orb.js already used for the eye).
  **No emoji, no Unicode dingbats (◉⌗◷✕▶‹≣⛓🟢🔑🧭 …) as functional UI chrome** — import the matching icon from
  `lib/icons.js` (add one if it's missing; keep the same stroke spec) and drop it in with `raw(ICON)` (or, inside an
  `innerHTML` template string, the bare exported string — it's already valid markup). **Exception: real brand/
  platform marks** (WhatsApp, Telegram…) stay their authentic logo, never re-drawn in this language. Decorative
  glyphs embedded in a prose sentence (a celebratory 🎉, a trailing ✓ in a button LABEL) are lower-value and were
  left as-is in the first pass — a chrome/button icon (header, toggle, close) is the bar for converting.
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
- **Widget kit (`hbk-*` in `styles.css §WIDGET KIT`, documented in `widgets/AGENTS.md`) is under-adopted** (~1 of 17
  widgets uses it) — a cheap follow-up is migrating a widget's hand-rolled card/badge/button CSS to it when that
  widget is touched anyway, not a dedicated sweep.
- **Scope of the 2026-07-22 pass**: app shell only (TopBar, StatusPanel, CronPanel, ChatWall, ConfigPanel,
  SettingsModal, WizardModal, VaultModal, MemoryMap, DebugPanel). The 17 individual widgets' own `widget.js` icons
  were NOT touched — a deliberate phase 2, do widget-by-widget as each is touched rather than a big-bang rewrite.

## Test layout (central `tests/` tree, by test type then module)

Los tests viven en un **árbol central `tests/`** en la raíz, separados por TIPO y luego por módulo — nunca mezclados
con el `source` del módulo (fue el desorden que corregimos: `memory/` tenía 14 `test_*.py` revueltos con el código):

```
tests/
├── unit/          # lógica de UN módulo, in-process, sin cola async ni HTTP
│   └── memory/    test_db.py test_state.py test_writer.py test_retriever.py …
├── integration/   # varias piezas juntas (cola+writer, fachada async, fs/episódica)
│   └── memory/    test_api.py test_writer_queue.py test_episodic.py …
└── e2e/           # flujo completo / endpoints HTTP a través del stack
    └── memory/    test_server_api.py
```

- **El source de cada módulo queda LIMPIO** (solo `.py` de código). Los tests espejan la estructura de módulos
  dentro de `tests/<tipo>/<módulo>/`.
- **`tests/` es un paquete** (`__init__.py` en cada nivel) → pytest sube hasta la raíz del repo, así los imports
  absolutos (`from memory import api`) siguen funcionando y no hay choques de nombres de fichero.
- Correr: `.venv/bin/pytest tests/` (todo) · `pytest tests/unit` (rápidos) · `pytest tests/e2e` (stack). Con
  `ZAELAR_EMBED_BACKEND=hash` los tests de memoria no dependen de Ollama; con `MEM_PROCESSOR=0` la ingesta es
  determinista (heurística).
- **Estado (2026-07-10):** `memory/` es el **piloto** de esta convención (V2-013). El resto del repo aún **co-loca**
  sus `test_*.py` con el source (`nucleo/`, `voice/`, `widgets/`, `connectors/`, `bus/`, `config/`); se migran a
  `tests/` en tandas verificadas. Un módulo nuevo nace ya con sus tests en `tests/<tipo>/<módulo>/`.

## First-party vs external (ours vs imported)

Everything in this repo is **first-party (ours)** — including, since v2 «Colmena» (V2-009), the **brain** (`nucleo/`)
and **memory** (`memory/`): zaelar no longer depends on an external agent. The clearly-bounded external pieces:

- **SlowBrain CodeAgents**: the Claude Code / Codex CLIs invoked by `nucleo/agentes/` are installed software, not
  our code. The repo holds only our `CodeAgent` interface + adapters (`nucleo/agentes/`).
- **Vendored third-party assets**: the WhatsApp Baileys bridge (`connectors/whatsapp/bridge/`, copied+patched with
  `// ZAELAR-PATCH:` markers + `VENDORED_FROM.md`) and `frontend/vad/` (Silero VAD + ONNX runtime). Isolated in
  their own folders.

Rule of thumb: a feature that depends on a specific external system (a connector, an importer, a CodeAgent backend)
is wired **only** through its boundary module (`connectors/`, `nucleo/agentes/`, …) — never woven into `server/`,
`voice/`, `widgets/`, or `frontend/`.

## Configuration is UI-managed (install once, then everything from the interface)

**Product invariant (INI-015).** A zaelar user installs the product **once** and from then on manages **everything
from the interface** — they never open a terminal or edit an env/config file. Any capability that needs turning on
or credentials (a connector, an integration, a key) MUST expose that setup as a **guided in-app flow**, not as a
documentation step that says "put X in `.env`".

Concretely:
- **First-run WIZARD (V2-040).** The entry point of "install once" is a setup wizard (`server/wizard_api.py` +
  `frontend/app/components/WizardModal.js`, 🧭): a **capability detector** (`config/doctor.py`, shared with the CLI
  `make doctor` → `.meshkore/logs/system-report.json`) evaluates the machine (hardware, Ollama+models, `claude`/
  LiveKit/Playwright binaries, which keys are set), and a **coordinated profile** (`config/profiles.py`, `local` |
  `cloud`, `remote`=alias) sets the full default set across all config axes at once (voice engine + `config/v2.py`
  routing + memory embed/rerank/processor) in a single `apply()`. The wizard then resolves gaps (one-click installs
  for project-scoped deps, copy-paste commands for system ones) and collects any missing API keys. It auto-opens
  when config isn't validated (`settings.wizard_done`) and is reopenable from the top bar.
- **Frontend-managed config store.** Per-feature runtime config that the user controls lives in a gitignored JSON
  the UI writes: `config/settings.json` (⚙ panel: STT/TTS/voice/language + **attention gate** `attention_mode`/
  `attention_window`, V2-015 + the `zaelar_profile`/`config_profile`/`wizard_done` markers), `config/connectors.json`
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
- **Secrets vault — native modal + hard rules (V2-060, BUILT 2026-07-21).** The operator-secrets vault ships a
  **native modal** (`frontend/app/components/VaultModal.js`, NOT a widget): create vault (master passphrase),
  unlock (passphrase OR **passkey** biometric — WebAuthn `prf`, Touch ID/Windows Hello), reveal a secret, and
  manage (enrol/revoke this device, change passphrase). It opens on demand from the brain's SSE `kind:"secret"`
  events (`services/sse.js`) or manually via `window.zaelar.vault()`. Backed by `memory/vault_api.py`
  (`/api/vault/*`, loopback on anything sensitive) and `services/vault.js`. **Redacted** public view: the passphrase
  / private key / passkey PRF are NEVER returned to the frontend — only presence/state (`status()`); the secret
  VALUE is fetched over loopback from `/api/vault/reveal`, never via the event bus. **Voice commands change config**
  too ("modo máxima seguridad", "no me digas secretos por voz", "léemelos por voz", `nucleo/flash/vault_rules.py`):
  recognised deterministically as a config change (not chat) and persisted as **HARD user rules** in `state.security`
  — enforced in code, INVIOLABLE, outside the cap-8 of soft **style** rules (V2-046, which only guide by prompt).
  *Pending (F4): a dedicated Security tab inside the ⚙ full-screen area (today the modal is the surface); strict
  in-browser zero-knowledge decrypt.* Full detail:
  `.meshkore/roadmap/initiatives/V2-060-boveda-secretos-cifrados.md` + `zaelar-security.md`.

## Commits

- No push to origin without explicit operator (Ricart) approval.
- AI-authored commits end with a `Co-Authored-By: Claude …` trailer (real practice; see the change protocol §5).
- Never commit: `.env`, `config/settings.json`, `config/connectors.json`, `config/v2.json`, `.venv/`, `logs/`,
  `memory/_data/` (the central memory DB — personal). `~/.hermes/memories/USER.md` (operator profile, if present)
  is likewise never committed.

## Sensitive files

See `admission.never_commit` in `.meshkore/public/cluster.yaml`.
