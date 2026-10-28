// js/state.js — Shared state and constants of the messaging card: platforms, brand marks, the presentation state every part reads and
// writes (`S`, one object because an ES import is a read-only binding), the per-conversation compose buffers, and `tt`.
// Moved verbatim out of widget.js (refactor2710-12).

export const S = {};

export const URG = {
  alta:  {dot: "var(--hb-risk,#e5484d)",   urgent: true},
  media: {dot: "var(--hb-accent,#3D6FE0)"},
  baja:  {dot: "var(--hb-muted-2,#9aa7b8)"},
};

// One definition per platform: label, badge color, whether credentials are needed (guided setup), and instructions
// (credentials guide + QR scan steps). Adding a platform means adding one entry here.
// V2-616 F4 — `bg` is each platform's own identity (the operator: "que el WhatsApp se parezca al WhatsApp,
// el Telegram al Telegram y el Gmail al Gmail"), not just the header dot's tint: telegram and email used to
// share the SAME generic --hb-accent blue, indistinguishable from each other at a glance. Literal hex here
// (not a shared theme var) on purpose — this widget's own brand identity, self-contained, and never coupled
// to the app's global palette (which a concurrent redesign of its own was mid-flight on the same day).
export const PLAT = {
  whatsapp: {
    label: "WhatsApp", bg: "#16B8A6", requiresCreds: false,
    qrKey: "qr_whatsapp",
  },
  telegram: {
    label: "Telegram", bg: "#2AABEE", requiresCreds: true,
    credLink: "https://my.telegram.org",
    qrKey: "qr_telegram",
  },
  email: {label: "Email", bg: "#D8452D", requiresCreds: true},
};
export const ORDER = ["whatsapp", "telegram", "email"];

// Real brand logos (official simple-icons.org outline, CC0), inline as <path> so the widget stays self-contained
// with no network/CDN from widget.js. Colored through currentColor + var(--hb-accent*) to keep the same palette as
// the rest of the widget (message chips, status dots).
export const SVG_NS = "http://www.w3.org/2000/svg";
export const BRAND_SVG = {
  whatsapp: {
    viewBox: "0 0 24 24",
    path: "M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z",
  },
  telegram: {
    viewBox: "0 0 24 24",
    path: "M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z",
  },
  // Email is the ONE channel that is not a brand: the same connector serves Gmail, Outlook/Hotmail and any
  // IMAP host, so it wears an envelope. Painting a Gmail logo here would be a lie for an Outlook account —
  // and the letter "E" the fallback used to draw read as a glyph nobody recognises next to two real logos.
  email: {
    viewBox: "0 0 24 24",
    path: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4.24-7.47 4.67a1 1 0 0 1-1.06 0L4 8.24V6.4l8 5 8-5v1.84z",
  },
};

// LOCAL presentation state (cosmetic, does not touch the store): selected profile, settings panel open, expanded
// messages. Survives re-renders because the module loads once.
S.profile = "simple";
try { S.profile = localStorage.getItem("hb-msg-profile") || "simple"; } catch { /* storage blocked: use "simple" */ }
S.settingsOpen = false;
// V2-521 — the visual formula: ONE inbox by default ("everything, no filters" is the deliberate start),
// and a per-platform lens on demand. null = todo. V2-543: the lens is no longer voice-deaf — the server
// pushes the requested view (`data.view = {platform, n, at}`) via the declared `show_view` action, and this
// widget applies it only when the WITNESS COUNTER moves (asking for the same view twice still lands; a plain
// re-show moves nothing and yanks nothing). Header icon clicks call the SAME action, so UI and voice share
// one state instead of diverging.
S.platFilter = null;
S.viewN = 0;                      // last applied view token (module-lived)
S.openMail = null;
// CHAT LIST lens state, per platform and cosmetic only (which rows of the server's list are on screen): the
// kind filter and the name search. The list itself — window, «Cargar más», what the connector sent — is server
// state, so voice and clicks agree on it.
export const _chatKind = {};
export const _chatQuery = {};   // mailKey() of the single EMAIL item shown in the detail screen (V2-610), or null = list
export const _expanded = new Set();   // message keys with the body expanded

// ONE DOOR for «the widget is now on channel X» (V2-626). Choosing a channel is a single STATE TRANSITION,
// not an assignment to `S.platFilter`: whoever asks — a tap on a header dot, the title, or an order the brain
// pushed — everything BELOW the header follows automatically. This is pure state mechanics; it has nothing to
// do with which caller triggered it, so no caller gets to know only a subset of it.
// Before this, each entry point had to REMEMBER to clear the connectors screen, an open mail and a pending
// disconnect confirmation. The click path learned it in V2-610; the voice path never did, so «enséñame el
// correo» lit the email dot and left WhatsApp's connector screen sitting underneath it (operator screenshot,
// 2026-09-09). A rule every caller has to remember is not a rule — it is a bug waiting for the next caller.
export function selectPlatform(pl){
  S.platFilter = (pl && PLAT[pl]) ? pl : null;   // unknown/absent = the unified main list
  S.openMail = null;           // a mail detail is a screen too: a lens change lands on that lens's LIST
  S.newMail = null;            // and so is a message being written: leaving the section leaves it
}

// Single message row: borderless vertical timeline, used inside an open thread in simple profile.
// V2-610 — the row of check/close/archive/trash/mute buttons, extracted so the flat list AND the new email detail screen
// wire the SAME five actions instead of two copies that drift (the row's copy predates this; the detail
// screen is what forced the split). `actionable` stays the caller's call: a row of buttons on a message
// that cannot be acted on (an outgoing message, or history with no `n`) would be a lie about what pressing
// them does (V2-546's own reasoning, unchanged).
// ── COMPOSE BAR (V2-611) ─────────────────────────────────────────────────────────────────────────────────
// Operator's spec, verbatim in spirit: dictate or type a reply, see it in a real box before it goes
// anywhere, then send it — by the button or by a later voice order. `draft` is the round-trip that keeps
// voice dictation and the visible box in sync (whichever wrote it last is what the box shows); `send_draft`
// is the one deliberate act that actually queues a real send, on the SAME text the box displays — never a
// value cached from an earlier keystroke, so an edit made after dictation is what actually goes out.
export const _draftFiles = {};   // key -> [{name,url,type,original}] attached in the card, not yet sent
export const _newForm = {};      // platform -> "chat" | "group" | null — the «Nuevo» form open on that platform's list
export const _draftLocal = {};   // key -> text not yet round-tripped to the server (keystroke buffer, per screen)
S.draftTimer = null;
// V2-819 — a send from his own hand is answered. `_sending[key]` is the order on its way ({ref, text}): the box keeps
// his text, locked, until the outbox row `ref` (data.outbox) says «sent»; a refusal or a failure unlocks it with the
// reason in `_sendNote[key]`. Before, the box was emptied the moment the order was QUEUED, and nothing that happened
// after that ever reached the card — a send that never left looked exactly like one that did.
export const _sending = {};
export const _sendNote = {};
// `targetPayload` addresses WHAT the reply goes to: `{}` for an open THREAD (the server resolves it from
// `active_chat` itself, V2-611's `_resolve_target`), or `{n, messageId}` for a single EMAIL. `activeChat` is
// `data.active_chat`, used only to match an incoming draft against the right screen.
// V2-680 — reply-ALL is remembered per conversation, module-lived like `_draftLocal`: it is a property of
// the reply being written, not of the widget, so switching mails must not carry one mail's choice onto the
// next. It is only ever offered when the ORIGINAL actually had other recipients (see `_otherRecipients`).
export const _replyAll = {};

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
S.T = null; S.LANG = "en";   // instance language (ctx.lang) — dates never follow the browser locale
S.newMail = null;      // a message being written that is not a draft yet (Redactar / Responder): {to, subject, text}

S.railOpen = false;    // the drawer, on a card too narrow for the rail

export function tt(key, params, fb){
  try{
    if(S.T){ const s=S.T("widgets.mensajeria."+key, params); if(s && s!=="widgets.mensajeria."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}
