# Agenda widget — notes

## Session 2026-07-07: Dentist appointment request
- User asked to add dentist appointment for tomorrow (Wed Jul 8) at 17:00
- Brain said it would start the task, but the widget had no `add_meeting` action; the appointment was NOT created
- Added `add_meeting` action to `data.py:apply_action`; supports title, date, startTime, endTime
- Still pending: actually add the appointment for the user

## Session 2026-07-13: Time horizon (day tabs + Week view)
- The operator wanted to see beyond today (week / upcoming days / view switching), not only the current day.
- `data.py:view_data` now exposes `days` = TODAY..TODAY+6 precomputed (`_horizon`; `plan_day` is pure/cheap) plus `todayIndex`; top-level `plan`/`active`/`warnings`/`coaching` remain today's values for compatibility.
- `widget.js`: tab bar (`agtab`, `ag*` prefix to avoid collisions with bare `styles.css` rules): one day per tab plus a "Semana" tab with a clickable per-day overview of meetings. Switching is client-side without another request, using the already-fetched days; selection lives in `el._agSel`.
- Preserved intact: TODAY view (Now card + countdown + done/not_now/snooze/drop actions + replan) only on Today; countdown/active only for today. Other days show their timeline + summary with no live actions.
- No contract changes: same id, same manifest actions. The data API and memory were not touched.

## Session 2026-07-13: Full MONTH view (day/month selector)
- The operator wanted a selector/tab to switch between day view and full MONTH view; the intent was to see the whole month at a glance, not only today.
- Added a "Mes" tab alongside the day tabs + "Semana" -> `renderMonth`: month calendar (7-column Mon-Sun grid) with each day's meetings, current month plus previous/next navigation (‹ ›) client-side with no extra request. Today is highlighted; a day inside the horizon (Today..+6) is clickable and jumps to its day tab.
- `data.py:view_data` now exposes `meetings` (raw dated meetings) so the whole month can be rendered client-side; the `days` horizon only reaches +6. Classes are prefixed with `ag*` (agmonth/aggrid/agcell/agev...) to avoid collisions with bare `styles.css` rules; meeting titles use textContent.
- Preserved intact: Day view (Now + countdown + actions + replan) and Week view; same id, same actions, no data API or memory changes.

## Session 2026-07-22: "Review company obligations" marked done
- The real store (`widgets/_data/agenda/state.json`) already had `t_empresa` at `status:"done"`; the planner already excludes `done` tasks from `currentPlan.blocks`, and `ref_index()` already excludes them from voice references. The widget reflects the change without touching code: no concrete task is hardcoded, the `done` state already governs the view. `widget.js`/`data.py`/`manifest.json` were not edited.

## Session 2026-07-22: Tomorrow's medical appointment (Jul 23, 09:00) cancelled
- The operator asked to cancel tomorrow's medical appointment in the real system (contact the center to cancel it) and reflect that in the agenda. The real cancellation is outside this code agent's scope; a separate worker with browser/phone access would do it. This code path only touches the agenda.
- An action to remove an existing meeting was missing (`add_meeting` existed without a counterpart); added `cancel_meeting` (title + optional date) to `data.py:apply_action` and declared it in `manifest.json` (`actions`/`usage`).
- Applied the effect: removed the two duplicated "médico"/"Médico" appointments from the store (`widgets/_data/agenda/state.json`) for 2026-07-23 09:00; the duplicate was detected along the way. The "Dentista" appointment (2026-07-23 17:00) was NOT touched because it is a different appointment.

## Session 2026-07-23: Repeated request to "execute the real task" remains outside this agent's scope
- The user again asked to ensure the cancellation is completed in the real world and reflected in the widget. Confirmed: the real counterpart (calling/contacting the medical center to cancel the appointment) is NOT reachable by a code agent restricted to `widgets/agenda/` without Bash or browser access. That is a worker task through the `hbweb`/phone bridge (V2-036/V2-061), not something this widget can do.
- Widget side: already complete from the previous session. `cancel_meeting` exists in `data.py:apply_action`, is declared in `manifest.json`, and the medical appointment for 2026-07-23 09:00 is no longer in the store. No additional code change is needed or made here. If the operator wants the real cancellation to be triggered automatically, that requires escalation to a worker (`escalate_to_slowbrain`) using `hbweb`/real contact, followed by `widget_data:agenda action=cancel_meeting` to reflect it; this code agent cannot invoke that by itself.

## Session 2026-07-23 (2): Third repeated request, no change, same boundary
- The request to "execute the real action" (contact the medical center) was repeated from this agent. Without the required tools (no Bash, no browser, restricted to `widgets/agenda/`) it remains impossible to execute here; this is the same limitation as the two previous sessions that day. `data.py`/`widget.js`/`manifest.json` were not touched; they are already complete because `cancel_meeting` covers the widget side. The store was not touched either; it lives outside `widgets/agenda/` and already reflects the cancelled appointment. Repeating this request to this agent will not complete it; a real worker must be launched (`escalate_to_slowbrain` -> `hbweb`/phone) and then call `widget_data:agenda action=cancel_meeting`. FlashBrain/the operator decides that, not this code agent.

## Session 2026-07-31: Fourth repeated request, now BOOK an appointment tomorrow at 17:00, no change, same boundary
- The request was to book an appointment "in the real system" for tomorrow (2026-08-01) at 17:00 and reflect it in the agenda, because the system only modified a local widget without executing the real action. Same boundary as the three previous sessions (those were cancellations, this is a booking; both are real-world commitments): executing the real commitment (booking on the site's web/phone channel) is unreachable for this code agent restricted to `widgets/agenda/` without Bash, browser, or widget-side network.
- Widget side is already complete and correct: `add_meeting` exists in `data.py:apply_action`, is declared in `manifest.json`, and correctly normalizes speech. `_resolve_date` maps a tomorrow utterance to +1d (2026-08-01), `_resolve_time` maps a five-in-the-evening utterance to 17:00 (default 17:00, 1-7 without meridiem -> afternoon), and the default end time is 18:00. That is the reflection primitive, not the real action.
- For the real booking to happen and be reflected: FlashBrain must escalate to a worker (`escalate_to_slowbrain` -> `hbweb`/phone, V2-061) that performs the real booking and then calls `widget_data:agenda action=add_meeting`. FlashBrain/the operator decides that, not this code agent. `data.py`/`widget.js`/`manifest.json` were not touched; they are already complete. The store was not touched either because it is outside `widgets/agenda/`, and mutating it would be exactly the "only modified a local widget" failure the operator rejected. Repeating this request to this agent will not complete it.

## Session 2026-07-31 (fifth repeated request): "real appointment tomorrow 17:00 in Ricart's agenda", no code change
- Widget side is already complete (verified): `add_meeting` exists and normalizes speech correctly (tomorrow -> 2026-08-01, five in the evening -> 17:00, default end 18:00). The widget already reflects any appointment through `data.meetings` (`renderMonth`/`renderWeek`). There is nothing to edit in `data.py`/`widget.js`/`manifest.json`.
- A "REAL appointment" remains unreachable for this agent: it is scoped to `widgets/agenda/` with no Bash/browser/network, the store lives outside that scope (`widgets/_data/agenda/state.json`), and the operator already rejected a local write in the previous session because it would only modify a widget, not execute the real action. Also, the request does not specify which service/center to book with, so there is nothing concrete to reserve.
- Real path, decided by FlashBrain rather than this agent: escalate a worker (`escalate_to_slowbrain` -> `hbweb`/phone, V2-061) that books on the real site and then reflects it with `widget_data:agenda action=add_meeting`. If the operator only wants it in the local agenda, FlashBrain can call `add_meeting`, which is also outside this code agent. In no case is this a widget code edit.

## Session 2026-09-09 (V2-639): the agenda answers to the voice
- Measured live: four requests for the MONTH view all landed on today — the model sent `show_day {view: 'month'}` and `apply_action` only read `day`/`date`. `show_day` now reads `day|date|view|mode|vista` (the V2-341 rule: the model's natural alias must not cost the fact).
- New vocabulary (the clear_all lesson — a frequent intention with no declared action cannot be gotten right): `move_meeting` (title + newDate/newTime; the end keeps the duration and the reminder MOVES with the appointment), `set_reminder` with a date and no title puts reminders on EVERY meeting of that day, `add_task` adds a plain task (optional fixed startTime). `add_meeting` accepts `notes` (place, who with…), capped at 500 chars.
- `prompt_digest()` (the `refs.prompt_digest` seam): upcoming meetings with date · hour · title · reminder · notes, so «what is that dentist item?» and «what do I have tomorrow?» are answerable while the card is open — `coach_context` only ever carried TODAY. `ref_index` also exposes future meetings (`field: title`), and the manifest declares `ref: "title"` on set_reminder/cancel_meeting/move_meeting so a spoken reference resolves.
- Multilingual: `_resolve_date`/`_resolve_time` understand English (tomorrow, weekdays, morning/afternoon); `planner.plan_day(lang=...)` localizes its invented labels (Lunch/Break/summary/warnings); `_horizon` labels follow the active language; `widget.js` chrome goes through `ctx.t` (`widgets.agenda.*` in both bundles, i18n MANIFEST_VERSION 5→6) with month/weekday names via `Intl.DateTimeFormat(ctx.lang)`; a meeting's notes are a tooltip on its month cell and day block.
- Seed packs v7: deterministic view phrases («enséñame la agenda de hoy/mañana», «pon la agenda en vista mensual/semanal», EN mirrors) → `widget_data agenda show_day` with a fixed payload; `show_day` is a view op so the card opens too.
- Tests: `tests/browser/unit/agenda/test_the_agenda_answers_to_the_voice.py` (19) + `test_the_agenda_dresses_in_the_operators_language.py` (6 rendered), node 4.140. Six disarms, mutations asserted, all red.

## Session 2026-09-09 (V2-643): the agenda looks like a calendar
- Operator's report with two screenshots of the week view: the card opened tiny with the bottom words cut, the "week" was a list of days rather than columns, the three 15px connector icons in the header were unreadable and dropped an explanatory paragraph over the content. His spec: Google/Apple Calendar shapes, «cada uno de los días de la semana con los ítems dentro de cada columna», colours and intensities, a symbol for an active reminder, and whether a meeting is confirmed by the other side / how many people are coming.
- **Measured first**: `manifest.json` declared NO `size`, so the card opened at the default 400×340 tile (same class as V2-630 musica / V2-597 youtube). Now `size` 920×640, `min` 420×380.
- **Data**: a meeting carries `attendees` (names or a bare count), `status` (confirmed|pending, parsed from speech — note `_PENDING_RE` runs FIRST because «sin confirmar» contains the confirm stem, and word boundaries because «si» lives inside «sigue»), `location`, `category` and `allDay`. `update_meeting` is the one door for editing them and touches only the keys present in the payload. Default: a meeting WITH attendees is born `pending` (awaiting their answer), one without is `confirmed` — the convention every calendar uses.
- **`planner.plan_day` skips all-day meetings**: they have no hours and belong to the calendar's all-day band; reading `mt["startTime"]` on one raised a KeyError that took the whole plan down (found by the new test the day all-day events shipped).
- **Widget rewritten**: toolbar (brand · range title · ‹ Hoy ›), a defined view band with the active view as an INVERTED chip (V2-636 language), and four classic views — Day (hour grid + the coach rail that has always been here), Week (7 Mon–Sun columns over the grid, overlapping events packed side by side), Month (7×N navigable grid), List (the Schedule view). Chip hue comes from the dictated category or the planner's block kind — never from sniffing the title (V2-095) — and its INTENSITY from status: confirmed solid, pending dashed, a planned task block soft. Badges: bell when a reminder exists, 👥N for attendees. Clicking an event opens a detail panel whose actions all map to declared data-ops (confirm, remind 2h before, cancel with a two-step ask). Connectors moved to their own panel, one labelled row per provider.
- **The card FILLS its frame** (`:has(> .hb-agenda)` on `.hb-scroll`, the V2-636 rule) and the grid scrolls inside it — nothing can be clipped at any card size.
- i18n rebuilt: 38 `widgets.agenda.*` keys in both bundles, month/weekday names via `Intl.DateTimeFormat(ctx.lang)`; i18n MANIFEST_VERSION 6→7.
- Tests: `test_the_agenda_looks_like_a_calendar.py` (17 rendered, node 4.142), V2-540's `test_agenda_render.py` rewritten to the new DOM keeping every behavioural claim, the XSS fixture repointed at the surface that now renders (meetings), +8 data cases. Ten disarms, mutations asserted, all red — one (D8) came back green and exposed a real gap: nothing measured the NEGATED confirmation, which is the case that decides the parser's order.

## 2026-09-12 (V2-679): Google Calendar sync — a real connector, not just the header placeholder
- Operator's directive: put the three calendar-provider icons already in the header to work, keep only Google
  active (iCloud/CalDAV stay visible and INERT, per the shelf pattern already used elsewhere in this codebase
  — showing what we do NOT have on purpose, INI-027), add the "conectores" button like messaging/video/photos
  have, and build a REAL Google Calendar connector: OAuth, and once connected it becomes the SOLE source of
  truth for meetings — several Google calendars merge into one view with a chosen default for new writes, and
  sync has to be "lo más rápido posible" (his own acceptance test: dictate an appointment by voice, see it in
  the real Google Calendar within seconds; add one on the phone, ask Zaelar to confirm it moments later).
- **The scaffolding for exactly this already existed and was waiting**: `widgets/agenda/data.py::calendars()`
  (V2-540) already read `connectors.registry.descriptors()` filtered to `family in ("agenda","calendar")`
  against a hardcoded `_CALENDARS` tuple keyed `("google","icloud","caldav")`, and
  `connectors/catalog/google-calendar.json` already existed as a `"state": "planned"` wishlist entry. Building
  the connector meant: register it under registry id **"google"** (not "google-calendar" — matching the
  existing placeholder's key so the real row REPLACES it instead of standing beside it as a duplicate, the
  measured T2 trap from the V2-557 workflow doc) and flip the catalog entry's `state` to `"built"`.
- **`connectors/calendar/`** — the same 5-layer family shape as `connectors/video/`(V2-597)/`photos/`(V2-564):
  `providers.py` (ONE provider, ONE tier — unlike video's parked write tier, this had to ship read+write from
  day one since voice-driven writes ARE the acceptance test; scope
  `https://www.googleapis.com/auth/calendar`), `oauth.py` (PKCE, copied byte-for-byte from video/oauth.py —
  same class of problem, deliberate copy not reinvention — including the origin-derived redirect_uri, video's
  MORE recent fix, not photos' older hardcoded one), `google_calendar.py` (the API client: `singleEvents=true`
  on every list call means Google expands recurring events into individual instances SERVER-SIDE — zero RRULE
  parsing anywhere in this connector; incremental sync via `syncToken`, `410` → fall back to a full pull with
  a ±120/400-day window), `service.py` (fail-safe facade, MECHANICAL only — dedup/twin-settlement/reminder
  policy deliberately stay in the widget, never taught to the connector, so a future second provider needs no
  agenda-specific code), `server_api.py` (`/api/calendar/*`, mirrors `/api/video/*` exactly including the
  "push the widget's store right after the callback so the operator never has to press comprobar" pattern).
- **`widgets/agenda/gcal.py`** (new file) — ALL of the agenda-specific Google glue (`commit_meeting`,
  `patch_google`, `delete_google`, `ui_action`, `tick`, `on_calendar_connected`, plus `calendars()`/
  `_CALENDARS` moved here too) lives in its OWN module, extracted the same day it was written rather than
  after the fact: `data.py` sat EXACTLY on its 900-line ceiling before this feature (the same newborn-file
  ratchet documented in V2-604/V2-611/etc.), so every line of new logic had a choice — go in `gcal.py`, or
  push `data.py` over the ceiling. `data.py` keeps only thin call sites (`gcal.commit_meeting(db, _new)` etc.)
  and two one-line re-exports (`tick`/`on_calendar_connected`) that the scheduler and the OAuth callback need
  to find at their conventional address. Same shape as `widgets/youtube/account.py` delegating
  `connect_account`/`disconnect_account` out of `data.py` — confirmed as the RIGHT precedent (not messaging's
  UI-only, mailbox-routed connect/disconnect, which only applies to `"kind":"backed"` widgets) by reading how
  `widgets/validator.py::_validate_actions_sync` actually gates a PASSIVE widget's `apply_action`.
- **Local-only mode is completely unchanged**: every write action (`add_meeting`/`cancel_meeting`/
  `move_meeting`/`update_meeting`) keeps its ENTIRE existing dedup/twin-settlement/reminder logic untouched —
  the Google glue is a THIN layer bolted onto the existing append/mutate points (`gcal.commit_meeting` wraps
  the append, `gcal.patch_google`/`delete_google` mirror an edit/cancel onto a meeting whose `source ==
  "google"`). A meeting with no `source` field behaves exactly as it did before this feature existed.
- **Once connected**: `add_meeting` creates the event on Google FIRST (via the default calendar) and stores
  the Google-enriched dict (carrying `googleId`/`googleCalendarId`/`source`) instead of the plain local one —
  best-effort: a Google failure OR a raised exception (two different risks, both tested) still keeps the
  LOCAL write, the same "a side-effect failure must never lose the write" rule `_schedule_reminder` already
  follows. `cancel_meeting`/`move_meeting`/`update_meeting` mirror onto Google only for `source == "google"`
  meetings — a purely local meeting never touches the network on edit.
- **Background sync** (`manifest.json`: `"background": {"every": "10s"}`) — a DELIBERATE departure from the
  video connector's on-demand-only precedent (V2-597: "the operator's standing rule is absolute control — the
  suggestions band fills when ASKED, never on a timer"). That rule fits a read-only suggestions feed; it does
  not fit a calendar whose whole point is "diez segundos y ya está en mi agenda" — a connector that only
  refreshes when the card happens to be open would miss exactly the phone-then-ask-Zaelar case he described.
  Cheap in the steady state: `service.sync` costs one empty round-trip per selected calendar when nothing
  changed, thanks to `syncToken`. A freshly-synced timed event gets Zaelar's own SPOKEN reminder (~2h before,
  the same policy a locally-dictated appointment gets) — Google's own notification is a different, silent
  channel this product does not rely on.
- **`on_calendar_connected()`** (called from the OAuth callback, mirroring video's `_refresh_card` pattern) —
  an immediate sync so existing Google appointments show up without waiting for the first tick, PLUS a
  one-time best-effort migration of pre-existing LOCAL future meetings up to Google, using the SAME
  `_titles_overlap` rule the write path already uses for dedup so a local meeting that already looks like one
  Google just handed back is never pushed twice. Past meetings are never migrated (history, not a live
  obligation). This is the direct answer to "no quiero divergencias… si tienes que duplicar los datos, busca
  la mejor forma de hacerlo."
- **Multiple calendars merge, one default for writes**: `db["google"]` caches the account's full calendar list
  (refreshed every tick) plus a chosen `defaultCalendarId` (a `set_default_calendar` UI-only action from the
  panel's radio picker — never voice, it is a preference not an intention). Every SELECTED Google calendar
  (mirroring what the operator already sees as "shown" in Google's own UI) syncs into the SAME merged
  `meetings` list, tagged with `calendarColor`/`googleCalendarId` for display.
- **Widget UI** (`widget.js::renderCalendars`, extended, not rebuilt): only Google gets a real connect button
  ("Conectar Google Calendar") or, honestly, a note pointing at ⚙ → Conectores when no OAuth app is registered
  yet (`status: "unconfigured"`, distinct from `"unavailable"` = not built at all) — iCloud/CalDAV get NO
  click handler, matching the operator's own ask ("deja los iconos puestos… no nos vamos a preocupar de
  nada"). Connected state adds the default-calendar radio picker + a "Desconectar" button. Deliberately did
  **NOT** add a second row of bare brand icons into the toolbar (`.agbar`) — this file's own CLAUDE.md
  decision log already records that exact attempt being reverted once for being "too small and cramped"
  (V2-643) — the existing 🔌-style "Calendarios" button already IS the connectors door messaging/video/photos
  each have their own version of; it now does real work instead of only showing three permanently-off rows.
- **⚙ Settings wiring** (the T3 trap from V2-597's own postmortem — "the registry rows existed and nobody
  rendered them, so there was nowhere to paste the client_id" — checked against explicitly, not assumed
  fixed): `ConfigPanel.js` fams list gains `["agenda", fam_calendar]`, the generic photos/video OAuth card
  condition extends to `fam === "agenda"`, `cxAct`'s dispatcher branches on the disconnect button's new
  `data-fam` attribute (an id collision risk otherwise — the provider id "google" is generic and could belong
  to more than one family later) and on a new `calendar-connect` act; `api.js` gains
  `calendarConnect`/`calendarDisconnect`; `i18n` gains `config.cx.fam_calendar` in EN+ES (app-shell chrome, so
  a missing key would show the raw key string — unlike the widget's own `tt()` fallback, this one is not
  forgiving) — MANIFEST_VERSION 9→10.
- **The write-through/patch/delete branches are UI-only** (`connect`/`disconnect`/`set_default_calendar`,
  declared in `manifest.json` per the youtube/account.py precedent — `widgets/validator.py` requires every
  `apply_action` branch to be declared for a PASSIVE widget, unlike messaging's `"kind":"backed"` exemption).
  `connect`/`disconnect` are voice-reachable as an INTENT door only (V2-520: no credential ever crosses a
  data-op) and return the connector's result directly, never `view_data()`.
- **Known limitation, named rather than solved**: the widget-action dispatcher (`apply_action`) has no HTTP
  request to read an `Origin`/`Host` header from, so `connect`'s OAuth redirect always resolves to the
  loopback default — correct for the self-hosted engine this was built and verified against (the operator's
  own stated test), but a cloud deployment would need the same per-request origin video's dedicated
  `/api/video/connect` ROUTE derives, which is a route-level concern this shared widget endpoint does not
  have. Also open: a `patch_google`/`delete_google` failure leaves the local edit standing with no automatic
  self-heal on the next sync (a real divergence risk, smaller than the one this build closes, not solved
  here); no recurrence EDITING (only whole-instance create/cancel/move — recurrence series management was out
  of scope, "que lo hagamos de la manera más simple posible" per the operator).
- Tests: `tests/connectors/unit/calendar/test_google_calendar_connector.py` (22 cases — provider registry,
  OAuth PKCE, event↔meeting normalization in both directions incl. all-day exclusive-end and attendee/self
  status, `list_events` pagination + 410 handling, the facade's `_prepared` failure ladder, `sync`'s merge of
  new/changed/deleted plus its 410 fallback, `create_event`/`patch_event`/`delete_event`), node 5.23.
  `tests/browser/unit/agenda/test_google_calendar_sync.py` (16 cases — the write-through/patch/delete
  contract, background tick incl. reminder scheduling for a fresh sync, `on_calendar_connected`'s migration
  and its two guards against duplicating/migrating-the-past), added to node 4.6. `test_show_day_is_an_action_
  not_a_promise.py`'s pre-existing "all three calendars are unbuilt" assertion updated to the new, correct
  reality (google now genuinely "unconfigured", not "unavailable"). Disarmed: the 410-fallback branch and the
  raised-exception safety net both verified red on a targeted mutation. `make test-widgets` 15/15, full
  `tests/browser/unit/` sweep (1877 relevant cases) green, `tests/infrastructure/unit/` 941/941 green
  including the architecture ratchet (data.py landed at exactly 900 LOC, same ceiling it started this feature
  at) and the testmap-completeness ratchet.
- **NOT verified live** — needs a real Google OAuth client registered (the `builtin_client_id` field is
  empty, exactly like video's own INI-032 status; the operator's own acceptance test — dictate an appointment,
  watch it appear in the real Google Calendar on another machine — needs that alta done first) plus an engine
  restart and a page reload.

## 2026-09-12 (V2-679, 2ª vuelta) — los conectores TOMAN la pantalla, como en mensajería

El operador, con una captura del primer intento: «esto no funciona igual como en los mensajes. He dicho que
hay un icono, un botón para conectores y luego a la izquierda los tres iconos… si se clica en conectores,
todo el espacio central de contenido lo centramos en los conectores, igual que en mensajería. Y se desactiva
el foco o el botón activo de día, semana, mes y lista… el botón de conectar a Google Calendar lo que hace es
inicia un wizard con las instrucciones en la zona central del widget… también tiene que tener una barrita de
navegación para volver atrás… Ahora este botón de conectar a Google Calendar ni siquiera funciona.»

- **Los tres iconos en el subheader** (`renderProviderIcons`), a la izquierda del botón **Conectores**, con
  el mismo reparto que la cabecera de mensajería: Google vivo (su icono es la puerta a su pantalla), iCloud y
  CalDAV **atenuados y `disabled`**, con su tooltip diciendo que aún no están. Objetivos de 26 px, no la tira
  de 15 px que V2-643 ya revirtió una vez por ilegible.
- **El área de contenido ENTERA pasa a los conectores** (`S.screen` = `null` | `"list"` | `"wizard"`, la misma
  máquina de tres estados que mensajería tiene desde V2-570), en vez del panel flotante `agveil`/`agpanel` de
  la primera vuelta. Mientras esa pantalla manda, **ninguna vista está activa y ninguna se puede pulsar**
  (`t.disabled = !!S.screen`) — la vista elegida sobrevive debajo y vuelve al cerrar. Una vista empujada por
  voz **sale** de la pantalla de conectores (la lección de V2-626: una orden de navegación no puede quedar
  renderizada debajo de una pantalla de configuración).
- **«Conectar Google Calendar» ya no dispara el handshake: abre el WIZARD** — tres pasos de instrucciones
  (proyecto de Google Cloud + API de Calendar · ID de cliente OAuth de escritorio · pegarlo en ⚙ → Conectores)
  con sus enlaces reales a las páginas de Google, migas de pan y **Atrás en cada paso** (desde el paso 1
  vuelve a la lista, nunca fuera del widget). Solo el ÚLTIMO paso habla con nadie.
- **Y ahí estaba el «ni siquiera funciona»**: la ventana de Google se abría con `window.open` **después** de
  `await ctx.action("connect")`, o sea fuera del gesto del usuario — y eso lo bloquea **en silencio** cualquier
  navegador actual. Ahora la ventana se abre EN BLANCO dentro del propio clic y se navega cuando llega la URL;
  si el conector rechaza, se cierra y **se dice por qué** (su propia frase: «sin app OAuth registrada…»), en
  vez de dejar el botón como si no hiciera nada. El test que lo cubre es de ORDEN, no de existencia de la
  llamada — es la única forma de verlo.
- La pantalla de una cuenta CONECTADA (elegir el calendario por defecto, desconectar) es la misma de antes,
  solo que vive en la lista en vez de en un modal.
- Tests: `tests/browser/unit/agenda/test_the_connectors_take_the_screen.py`, nodo **4.163**, 16 casos
  RENDERIZADOS; ocho desarmes, cada mutación comprobada antes de medir, los ocho en rojo. De paso quedó
  arreglado un fallo que ya venía roto: el texto de reserva de `cal_soon` decía «próximamente» mientras el
  bundle dice «aún no disponible», y `test_the_panel_tells_the_TRUTH_that_none_is_built_yet` llevaba fallando
  por esa discrepancia; las claves nuevas del asistente están en los dos bundles (`MANIFEST_VERSION` 10 → 11).
- **NO verificado en vivo** — sigue necesitando el alta del cliente OAuth de Google y una recarga de página.

## 2026-09-17 — V2-718: la agenda sabe INVITAR, y qué invitación necesita permiso

Su encargo con Ivan había salido bien de punta a punta —negociado por Telegram, hora acordada, enlace de
Meet creado, cita escrita y sincronizada con Google— y el último mensaje de Ivan era «can you send me a
calendar invite to: ivan@charms.dev». No pasó nada: **la agenda podía crear una cita, editarla, responder a
la invitación de otro y borrarla, y no tenía forma de invitar a nadie a la suya.**

### La trampa que hacía imposible resolverlo aunque el verbo hubiera existido

`sendUpdates` **no aparecía en todo el repo**. El valor por defecto de la API de Google es `none`, así que
añadir a alguien a `attendees` devuelve 200, lo pone en el evento y **no le manda nada**. Es exactamente la
misma clase de fallo silencioso que `conferenceDataVersion` —documentado una función más abajo en el mismo
fichero— una llamada más allá: un parámetro ausente, un 200, y una funcionalidad que no ocurrió.

### Dos peldaños de UNA escalera, y los elige la CITA, nunca el destinatario

1. **La cita vive en un calendario nuestro** → se añade al invitado ahí y lo manda el calendario
   (`connectors/calendar/service.invite`, con `sendUpdates=all`). Lo que recibe es una invitación iCalendar
   de verdad, que su propio calendario enseña con Aceptar/Rechazar **sea Gmail, iCloud u Outlook**, y su
   respuesta vuelve al evento. Es siempre el mejor peldaño cuando existe: la cita y la invitación son el
   mismo objeto.
2. **No hay calendario detrás** → la construimos nosotros (`connectors/calendar/ics.py`) y la mandamos por
   correo como parte `text/calendar; method=REQUEST` más un `invite.ics` adjunto
   (`mailbox.send_invitation`), que es el estándar que lee cualquier cliente.

⚠️ **El peldaño lo decide la cita, no la dirección.** «Esta parece de Apple» es una afirmación sobre el
correo de otra persona que no se puede saber, y sería falsa la primera vez que una empresa aloja su dominio
en Google. Y un calendario que RECHAZA no cae al segundo peldaño: pondría una segunda copia desvinculada en
el calendario del invitado cuya respuesta no vería nadie.

### Qué necesita permiso y qué no (V2-712 llevado a su sitio)

El criterio es suyo, literal: «esto que no nos hace ningún daño no necesita permiso; añadir a otra persona,
cambiar de hora o hacer otras cosas sí». La regla única de consentimiento ya existía y ya era dato
declarado — lo que no podía hacer era distinguir estos dos casos, porque **la diferencia no está en el
verbo, ni en las claves del payload, ni en las palabras de la petición**: está en si la llamada se queda
dentro de un compromiso ya adquirido con quien ya estaba dentro. Eso solo lo sabe el widget que tiene la
lista de invitados, así que ahora puede decirlo (`data.py::consent_scope`, leído por
`nucleo/flash/frontend._policy_key`) y la respuesta es una CLASE de genesis que el operador puede cambiar
hablando.

- `calendar.invite_agreed` → **allow**: la persona con la que se acordó la reunión, en una dirección que
  ella misma escribió en la conversación.
- `calendar.invite_new_party` → **ask**: cualquier otro.
- `calendar.reschedule_committed` → **ask**: mover una hora que otro ya tiene bloqueada.

«Quién ya estaba dentro» sale de dos datos: los contactos que el título de la cita nombra (resueltos con el
matcher de la casa, y **solo si son inequívocos**) y las direcciones que esas personas nos han escrito
(archivo de mensajería, solo entrantes).

⚠️ Recorrer el directorio buscando cualquier nombre que sea subcadena del título es exactamente cómo
«Meeting with Ivan Mikushin» adoptó en silencio a otro contacto llamado solo «Ivan» — y adoptar a la persona
equivocada aquí es el daño que toda esta pregunta existe para evitar. Dos contactos que encajan son DUDA, y
la duda no es pertenencia.

⚠️ Y el límite, dicho en vez de escondido: una cita cuyo título no nombra a nadie («café», «reunión») no
produce partes, así que todo invitado se lee como nuevo y la invitación pregunta. Esa es la dirección segura.

### Un test unitario tocó un artefacto vivo, otra vez

`consent.set_class` PERSISTE —es su razón de ser— y escribe en `<workspace>/config/consent.json`, que en la
máquina del operador son sus reglas reales. La primera corrida de
`test_what_needs_permission_and_what_does_not.py` le metió dos clases de calendario en su config y hubo que
sacarlas a mano. El fichero de overrides vive en `tmp_path` desde entonces.
