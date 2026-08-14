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
