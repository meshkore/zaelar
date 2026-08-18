// ============================================================================
// mobile-surfaces.js — THE CANONICAL LIST of the mobile shell's native surfaces. Same role, same discipline and
// the same reason as app/core/system-surfaces.js on the desktop: main.js MOUNTS from here, so there is never a
// second list to keep in sync. Adding a native mobile surface means adding a line here.
//
// It is a DIFFERENT list from the desktop's, not a subset of it, and the differences are the design:
//
//   · the desktop's 16 surfaces include four things a phone cannot carry — the draggable camera unit, the
//     activity honeycomb behind the canvas, the 35 KB configuration panel and the debug/observability panel.
//     Those are not "not ported yet": a phone is for USING the agent, and each of them exists for setting one up
//     or for auditing one, both of which the operator does at a desk.
//   · the chat's four tabs collapse to one (see ChatSheet.js), the seven-icon eye collapses to a five-control
//     dock (DockBar.js), and N draggable cards collapse to one deck of full-screen cards (Deck.js).
//   · three surfaces are REUSED VERBATIM from the desktop, because they are modal and full-bleed already and a
//     phone changes nothing about them: BootOverlay, LanguageOnboarding, Alert. Reusing them is not laziness —
//     forking a first-run gate is how two shells end up disagreeing about whether onboarding happened. Their CSS
//     moved to app/core/shared-surfaces.css for the same reason.
//   · MemoryMap is the one shareable component deliberately LEFT OUT of F1. The component would import fine; its
//     styling is a ~200-line panel UI (mm-head / mm-modes / graph / three lists) keyed to a wide window, and
//     re-fitting that is its own piece of work, not a line in this list. Declared as an open item in V2-124
//     rather than half-mounted — a memory view that renders as an unstyled column is worse than one more tap.
//
// Fields per entry:
//   id     — stable identifier of the surface
//   comp   — the factory that builds it
//   target — where it mounts: "deck" (inside #zm-deck-wrap, under the dock) | "body" (above everything)
//   phase  — "scaffold" (load-bearing order) | "overlay" (the rest)
//   label  — human-readable purpose
//   shared — true when the component is the DESKTOP's, imported as-is
// ============================================================================

import { Alert } from "../../../app/components/Alert.js?v=2";
import { BootOverlay } from "../../../app/components/BootOverlay.js?v=2";
import { LanguageOnboarding } from "../../../app/components/LanguageOnboarding.js?v=1";
import { CaptionBand } from "./OrbMini.js?v=2";
import { ChatSheet } from "./ChatSheet.js?v=1";
import { DockBar } from "./DockBar.js?v=1";
import { MenuSheet } from "./MenuSheet.js?v=1";
import { SettingsSheet } from "./SettingsSheet.js?v=1";
import { VoiceHeldNotice } from "./VoiceHeldNotice.js?v=1";

export const MOBILE_SURFACES = [
  // ── the bar that owns every control, and the caption band that floats just above it ──
  { id: "dock",     comp: DockBar,     target: "body", phase: "scaffold", label: "Bottom dock (orb · mic · power · chat · menu)", shared: false },
  { id: "captions", comp: CaptionBand, target: "body", phase: "scaffold", label: "Live captions band (above the dock)", shared: false },
  // ── sheets: they slide up from the bottom edge, over the deck ──
  { id: "chat",     comp: ChatSheet,      target: "body", phase: "overlay", label: "Chat (bottom sheet)", shared: false },
  { id: "menu",     comp: MenuSheet,      target: "body", phase: "overlay", label: "Menu: energy · account · voice · settings · memory · feedback", shared: false },
  { id: "settings", comp: SettingsSheet,  target: "body", phase: "overlay", label: "Small settings sheet (language · theme · captions · speaker)", shared: false },
  // ── the voice lock, made visible instead of silently lost (server/livekit_api.py) ──
  { id: "voice-held", comp: VoiceHeldNotice, target: "body", phase: "overlay", label: "«Your voice is on the computer» + take it over", shared: false },
  // ── SHARED WITH THE DESKTOP, imported verbatim (their CSS lives in app/core/shared-surfaces.css) ──
  { id: "alert",           comp: Alert,             target: "body", phase: "overlay", label: "Hard notice banner", shared: true },
  { id: "boot",            comp: BootOverlay,       target: "body", phase: "overlay", label: "Startup veil", shared: true },
  { id: "lang-onboarding", comp: LanguageOnboarding, target: "body", phase: "overlay", label: "First-run language onboarding", shared: true },
];

const _IDS = new Set(MOBILE_SURFACES.map((s) => s.id));
export function isMobileSurface(id) { return _IDS.has(String(id || "")); }
