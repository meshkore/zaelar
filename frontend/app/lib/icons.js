// Shared icon library — app-shell CHROME icons (TopBar, panels, modals), all drawn in the SAME visual language
// already established by Orb.js: viewBox 0 0 24 24, stroke="currentColor", stroke-width 2, round caps/joins.
// One icon = one string constant here, reused wherever that concept appears, instead of every component picking
// its own emoji/Unicode glyph (2026-07-22 frontend style pass — see zaelar-conventions.md §Frontend).
// Brand/platform marks (WhatsApp, Telegram…) are NOT here — those stay their real, authentic brand glyphs.
const S = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';

export const CLOSE_ICON = `<svg ${S}><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`;
export const REFRESH_ICON = `<svg ${S}><path d="M3 12a9 9 0 0 1 15.3-6.4L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.3 6.4L3 16"/><path d="M3 21v-5h5"/></svg>`;
export const TRASH_ICON = `<svg ${S}><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>`;
export const GEAR_ICON = `<svg ${S}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
export const COMPASS_ICON = `<svg ${S}><circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.264 1.264L7.76 16.24l1.804-5.411a2 2 0 0 1 1.264-1.264z"/></svg>`;
export const DOCS_ICON = `<svg ${S}><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5z"/><path d="M14 2v6h6"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>`;
export const BUG_ICON = `<svg ${S}><path d="m8 2 1.88 1.88"/><path d="M14.12 3.88 16 2"/><path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6"/><path d="M12 20v-9"/><path d="M6.53 9C4.6 8.8 3 7.1 3 5"/><path d="M6 13H2"/><path d="M6.53 17c-1.93.2-3.53 1.9-3.53 4"/><path d="M17.47 9c1.93-.2 3.53-1.9 3.53-4"/><path d="M18 13h4"/><path d="M17.47 17c1.93.2 3.53 1.9 3.53 4"/></svg>`;
export const KEY_ICON = `<svg ${S}><path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/><path d="m21.2 2.8-8.5 8.5"/><circle cx="7.5" cy="15.5" r="5.5"/></svg>`;
export const LOCK_ICON = `<svg ${S}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`;
export const PIN_ICON = `<svg ${S}><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>`;
export const CHEVRON_LEFT_ICON = `<svg ${S}><path d="m15 18-6-6 6-6"/></svg>`;
export const CHEVRON_RIGHT_ICON = `<svg ${S}><path d="m9 18 6-6-6-6"/></svg>`;
export const PLAY_ICON = `<svg ${S} fill="currentColor" stroke="none"><path d="M6 4v16l14-8z"/></svg>`;
export const ZOOM_IN_ICON = `<svg ${S}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/></svg>`;
export const ZOOM_OUT_ICON = `<svg ${S}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M8 11h6"/></svg>`;
export const FIT_ICON = `<svg ${S}><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>`;
export const LIST_ICON = `<svg ${S}><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>`;
export const LINK_ICON = `<svg ${S}><path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><path d="M8 12h8"/></svg>`;
export const VOLUME_X_ICON = `<svg ${S}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>`;
export const ACTIVITY_ICON = `<svg ${S}><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>`;
export const CLOCK_ICON = `<svg ${S}><circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 2"/></svg>`;
export const BRAIN_ICON = `<svg ${S}><path d="M12 4.5a3 3 0 0 0-3 3 3 3 0 0 0-1.3 5.7A3 3 0 0 0 8 16.5a3 3 0 0 0 4 2.6"/><path d="M12 4.5a3 3 0 0 1 3 3 3 3 0 0 1 1.3 5.7A3 3 0 0 1 16 16.5a3 3 0 0 1-4 2.6"/><path d="M12 4.5v15"/></svg>`;
export const CPU_ICON = `<svg ${S}><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v2"/><path d="M15 2v2"/><path d="M9 20v2"/><path d="M15 20v2"/><path d="M20 9h2"/><path d="M20 15h2"/><path d="M2 9h2"/><path d="M2 15h2"/></svg>`;
export const DATABASE_ICON = `<svg ${S}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/></svg>`;
export const MIC_ICON = `<svg ${S}><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><path d="M12 18v4"/><path d="M8 22h8"/></svg>`;
export const SEARCH_ICON = `<svg ${S}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;
export const MUSIC_ICON = `<svg ${S}><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;
export const SERVER_ICON = `<svg ${S}><rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01"/><path d="M6 17h.01"/></svg>`;
