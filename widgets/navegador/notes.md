# navegador: Context Notes

Web browser inside zaelar. **First `kind:"backed"` widget** (INI-016), introducing the live-backend widget-app
infrastructure designed in `zaelar-modules.md` Widget-apps section.

## Why a Backend, Not an Iframe
Almost no major website allows embedding in an `<iframe>` (X-Frame-Options / CSP `frame-ancestors`): Google,
Wallapop, RAE, shops, and many others. Therefore the REAL browser lives in `owner.py`: a **headless Chromium
(Playwright)** on the server. It navigates for real, photographs the viewport (1280x800), and the widget shows that
capture. Operator clicks/scrolls map back to page coordinates -> Chromium -> new capture.

## Pieces
- `owner.py`: live backend. **Only writer** of `_data/navegador/` (`state.json` + `shot.png`). Lazy startup:
  Chromium launches on the first order. Orders: `open/search/youtube/back/forward/reload/scroll/click/type/press`.
  Governed by `widgets/supervisor.py` (mailbox + restart with backoff + disable after N failures). Emits
  observability `kind:"navegador"` (navigate/screenshot/youtube/click/nav_error...) to `/debug`.
- `data.py`: **read-only** (`view_data`). `apply_action` is a safety net: in a backed widget, the host enqueues into
  the owner's mailbox BEFORE touching data.py (`server_api._route_backed`).
- `widget.js`: address bar + back/forward/reload, viewport (clickable capture with scroll, or **YouTube embed**
  player when `mode==="youtube"`), and initial state with shortcuts.
- `manifest.json`: `kind:"backed"`, `backend.owner`. Navigation (`open/search/youtube/back/forward/reload/scroll`)
  is `safe:true`, so the fast voice layer drives it. `click/type/press` is `safe:false`, so automation inside a
  website (filling forms) escalates to Hermes.

## YouTube
Exception: a capture does not play video/audio, so the owner resolves `videoId` by scraping result HTML with no API
key, and the widget mounts the real embed player (`youtube-nocookie`). `open` detects YouTube URLs.

## Authentication: Sessions With the Operator's Account (INI-016)
Many tasks need the operator's account (creating a Google Cloud API key, buying on Wallapop, reading email). The
headless Chromium starts **without a session**. Solution: its own profile + one manual login, NOT copying cookies
from system Chrome because they are Keychain-encrypted and fragile.

- **Detection** (`agent.py::_looks_like_login`): deterministic (known login URL + password field in the snapshot)
  before letting the model act. The loop **NEVER types invented credentials** (2026-07-10 bug: it typed
  `user@gmail.com` into Google login and spun). There is also a `need_login` action for cases where the model
  detects a login the URL does not reveal.
- **Real window** (`owner.py::_begin_login` -> `_authenticate`): relaunches the SAME Chromium **visible** on the
  login page (`_visible_override`), the card shows "I have logged in", and voice notifies the operator. The operator
  logs in manually, and the session cookies are saved automatically in the **persistent profile**
  (`_data/navegador/profile/`).
- **Return** (`_auth_done`, through the button or the `login_done` voice tool): post-login probe checks whether the
  session stuck or bounced back to login, returns to headless, and automatically resumes paused task(s).
- **Controlled**: one window -> one login at a time (pause+resume other tasks because `stop()` kills their tabs);
  **10 min timeout** without completion -> reminder, never kills the task; **crash/restart** -> durable memory crumb
  (`auth_memory.checkpoint_auth_pending`) -> startup remembers the half-done login.
- **Memory** (`auth_memory.py`, through `memory.write`/`set_state` facade): the SECRET (cookies) NEVER enters
  memory; it lives in the profile, encrypted by the OS. Memory stores only the **fact** of the session
  (`record_session_established`, `slot=navegador.session.<site>` -> supersede) and the recoverable checkpoint.
  Mirrors `widgets/lifecycle.py` (registration) and `nucleo/reset.py` (freeze->record).
- **FlashBrain**: tools `authenticate_web(site)` (open login on request, e.g. "connect me to Wallapop") and
  `login_done` ("I am in"). Operator-only by construction; the cluster reasoner has no tools. Confirmation gate for
  irreversible actions (buy/pay/publish) remains in `nucleo/danger.py`.

## State / Future
- v0.1.0: open website, search Google, play YouTube, click/scroll over the capture, back/forward. Base for vision:
  **drive navigation by voice and automate** (for example, opening Wallapop and searching for a motorcycle under a
  budget/year constraint), based on `click/type/press` actions plus Hermes escalation.
- Chromium stays alive after first use, so reopening is instant. Future: close on inactivity to free RAM; semantic
  navigation ("click the second result") through Hermes reading the DOM.

## V2-571 (2026-09-03) — the task card retired for errands with a sheet
- An errand's browser now renders inside its results sheet's PROCESS tab (`dispatch.sheet_browser`). So:
  `_prepare_web` only emits the `navegador::tN` card `show` when the errand has NO sheet; `tasks._notify` also
  refreshes the sheet's card (the embedded capture must move between phase changes); `_announce_wall` raises the
  SHEET when the task has one; and the owner's finish note stops naming a card that is not on screen.
- `tasks.set_sheet` re-stamps a REUSED tab (`find_continuation`) with the new errand's sheet — a stale stamp
  routes findings and refreshes to the predecessor's box (the V2-434 «sello rancio»). Never blanks a stamp.
- The `browse_web` singleton card and sheetless task cards are untouched.
