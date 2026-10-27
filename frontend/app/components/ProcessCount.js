// ============================================================================
// ProcessCount.js — the live count of RUNNING PROCESSES, the same number on every screen (V2-822).
//
// The operator (2026-10-27): «a live, interactive counter of running processes, on mobile and desktop, the same
// number on both, read from the engine; tapping it goes to the processes view». Born on the desktop's bar (V2-666:
// a bare number with a small pulsing bar — never a circle-plus-number badge, which reads as a notification rather
// than a gauge of work in progress), it is now ONE component both shells mount:
//   · the desktop's bar (WidgetRail) — a button of its own; a tap opens the chat on «Procesos ▸ En curso»;
//   · the phone's dock (DockBar) — riding the ☰ button, whose menu is the phone's processes view.
//
// ONE SOURCE. The number is `store.liveProcessCount()`: his live commissions from the engine's board (the rows the
// processes panel lists), moved by the SSE `task` events and re-read from the board when a process starts or ends.
// No screen polls and none keeps its own count, so the phone and the desktop cannot disagree.
//
// THREE FACES (V2-747): running (accent, the bar pulses), STOPPING (amber, blinking — the ⏻ was pressed and a turn is
// still in flight) and HELD (amber, still — the switch is off and the work is frozen, not gone). Hidden at zero: an
// idle «0» is dead chrome. Its CSS is in core/shared-surfaces.css (`.pcount`), on design tokens.
// ============================================================================

import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";

// `as`: "button" (a control of its own, `onOpen` on tap) or "span" (it rides a control that already opens the
// processes view). `cls`: the shell's own placement class.
export function ProcessCount({ as = "button", onOpen = null, cls = "" } = {}) {
  const el = document.createElement(as);
  el.className = "pcount" + (cls ? " " + cls : "");
  if (as === "button") el.type = "button";
  const n = document.createElement("span"); n.className = "pcount-n";
  const bar = document.createElement("span"); bar.className = "pcount-bar";
  bar.appendChild(document.createElement("i"));
  el.append(n, bar);
  if (as === "button" && onOpen) el.addEventListener("click", (e) => { e.stopPropagation(); onOpen(); });
  createEffect(() => {
    const k = store.liveProcessCount();
    const stopping = !!store.pausing(), off = !store.agentLive();
    el.classList.toggle("on", k > 0);
    el.classList.toggle("pausing", k > 0 && stopping);
    el.classList.toggle("held", k > 0 && off && !stopping);
    el.dataset.n = String(k);
    n.textContent = k > 0 ? String(k) : "";
    const title = k > 0 ? t(stopping ? "rail.processesStopping" : off ? "rail.processesHeld" : "rail.processes", { n: k }) : "";
    el.title = title;
    if (as === "button") el.setAttribute("aria-label", title);
  });
  return el;
}
