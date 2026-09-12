// Messaging widget client render. Contract: render(el, data, ctx).
// data = GET /widgets/mensajeria/data. No polling: the host (desktop.js) re-renders only when store.py emits the
//   SSE notice that this widget changed; QR, status, and messages refresh by themselves without timers.
//   data.platforms = { whatsapp:{status,qr}, telegram:{status,qr} }   data.items = [{n,platform,from,group,isGroup,body,urgencia,dirigido_a_mi,motivo}]
// ctx.action(name,payload) -> store mutation (read/dismiss/clear). Connector CONNECTION uses the messaging API
//   (same-origin fetch /api/messaging/*), so no .env editing; the user connects from here.
// SECURITY: bodies are UNTRUSTED (WhatsApp/Telegram). Always use textContent/createTextNode, never innerHTML
//   (anti-XSS), including when linking detected URLs inside a body (see `linkify`).
//
// PROFILE (2026-07-08): "simple" (default, minimal/timeline, no per-message borders) vs "completo" (original
// design, bordered cards + color badges). LOCAL preference (localStorage, cosmetic only); does not touch the store
// contract or pass through Hermes. Settings replaces the old footer with "connected" chips.

const URG = {
  alta:  {dot: "var(--hb-risk,#e5484d)",   lb: "urgente"},
  media: {dot: "var(--hb-accent,#3D6FE0)", lb: ""},
  baja:  {dot: "var(--hb-muted-2,#9aa7b8)",lb: ""},
};

// One definition per platform: label, badge color, whether credentials are needed (guided setup), and instructions
// (credentials guide + QR scan steps). Adding a platform means adding one entry here.
// V2-616 F4 — `bg` is each platform's own identity (the operator: "que el WhatsApp se parezca al WhatsApp,
// el Telegram al Telegram y el Gmail al Gmail"), not just the header dot's tint: telegram and email used to
// share the SAME generic --hb-accent blue, indistinguishable from each other at a glance. Literal hex here
// (not a shared theme var) on purpose — this widget's own brand identity, self-contained, and never coupled
// to the app's global palette (which a concurrent redesign of its own was mid-flight on the same day).
const PLAT = {
  whatsapp: {
    label: "WhatsApp", bg: "#16B8A6", requiresCreds: false,
    qrSteps: ["Abre WhatsApp en tu móvil → ", "Ajustes → Dispositivos vinculados", " → ", "Vincular un dispositivo", " y escanea este código."],
  },
  telegram: {
    label: "Telegram", bg: "#2AABEE", requiresCreds: true,
    credLink: "https://my.telegram.org",
    qrSteps: ["Abre Telegram en tu móvil → ", "Ajustes → Dispositivos", " → ", "Vincular dispositivo de escritorio", " y escanea este código."],
  },
  email: {label: "Email", bg: "#D8452D", requiresCreds: true},
};
const ORDER = ["whatsapp", "telegram", "email"];

// Real brand logos (official simple-icons.org outline, CC0), inline as <path> so the widget stays self-contained
// with no network/CDN from widget.js. Colored through currentColor + var(--hb-accent*) to keep the same palette as
// the rest of the widget (message chips, status dots).
const SVG_NS = "http://www.w3.org/2000/svg";
const BRAND_SVG = {
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

// Credential draft that survives re-renders, so user input is not wiped while typing.
const _draft = {telegram: {api_id: "", api_hash: ""},
                email: {email_address: "", email_password: "", provider: "gmail", imap_host: "", smtp_host: ""}};
// Email providers with server-side host presets; "otro" asks for IMAP/SMTP manually.
const EMAIL_PROVIDERS = [["gmail","Gmail"], ["outlook","Outlook / Hotmail"], ["icloud","iCloud"],
                         ["otro","Otro (IMAP/SMTP)"]];
const _busy = {};   // platform -> true while a connection is in progress, for button feedback
// Which field of a connect form to land on after a refusal (V2-559). Module-lived like _busy: the card is
// rebuilt on every render, so the intent has to outlive the DOM node it applies to.
const _focusField = {};
// An error banner is TRANSIENT (operator's rule): it belongs to a connect attempt made in THIS page
// session, never to a failure stored days ago. The store keeps status "error" durably (the brain reads it
// as "not connected"), but a fresh open starts clean — only a platform in `_attempted` may show the banner.
const _attempted = {};

// LOCAL presentation state (cosmetic, does not touch the store): selected profile, settings panel open, expanded
// messages. Survives re-renders because the module loads once.
let _profile = "simple";
try { _profile = localStorage.getItem("hb-msg-profile") || "simple"; } catch { /* storage blocked: use "simple" */ }
let _settingsOpen = false;
// V2-570 — the CHANNELS AREA has TWO screens (the operator's redesign): a LIST of every connector (icon
// grid) and, one level in, a WIZARD scoped to a single connector. `_screen` is null when the area is closed
// (messages view showing); {view:"list"} or {view:"wizard", platform} otherwise. Replaces the old flat
// `_connectorsOpen`/`_expandConnect` pair — there was never a third state, just two screens that used to be
// drawn on top of each other.
let _screen = null;
// Per-platform wizard progress (module-lived like _busy/_draft): which step is showing right now. Reset to 1
// implicitly whenever a platform's wizard is entered fresh (see `_enterWizard`).
const _wizStep = {};
// V2-520 — the last `connect_focus` request already honoured. The brain asking to connect a channel is the
// ONLY way into this panel from outside (it is local state the header button owns), and the request travels
// in the DATA with a timestamp. Remembering which one we acted on is what lets the operator close the panel
// again: without it, the next repaint — a new message arriving — would re-open it forever.
let _focusDone = 0;
// V2-521 — the visual formula: ONE inbox by default ("everything, no filters" is the deliberate start),
// and a per-platform lens on demand. null = todo. V2-543: the lens is no longer voice-deaf — the server
// pushes the requested view (`data.view = {platform, n, at}`) via the declared `show_view` action, and this
// widget applies it only when the WITNESS COUNTER moves (asking for the same view twice still lands; a plain
// re-show moves nothing and yanks nothing). Header icon clicks call the SAME action, so UI and voice share
// one state instead of diverging.
let _platFilter = null;
let _viewN = 0;                      // last applied view token (module-lived, like _focusDone)
let _confirmDisconnect = null;       // platform with a pending disconnect confirmation
let _openMail = null;   // mailKey() of the single EMAIL item shown in the detail screen (V2-610), or null = list
const _expanded = new Set();   // message keys with the body expanded

// ONE DOOR for «the widget is now on channel X» (V2-626). Choosing a channel is a single STATE TRANSITION,
// not an assignment to `_platFilter`: whoever asks — a tap on a header dot, the title, or an order the brain
// pushed — everything BELOW the header follows automatically. This is pure state mechanics; it has nothing to
// do with which caller triggered it, so no caller gets to know only a subset of it.
// Before this, each entry point had to REMEMBER to clear the connectors screen, an open mail and a pending
// disconnect confirmation. The click path learned it in V2-610; the voice path never did, so «enséñame el
// correo» lit the email dot and left WhatsApp's connector screen sitting underneath it (operator screenshot,
// 2026-09-09). A rule every caller has to remember is not a rule — it is a bug waiting for the next caller.
function selectPlatform(pl){
  _platFilter = (pl && PLAT[pl]) ? pl : null;   // unknown/absent = the unified main list
  _screen = null;             // Conectores/wizard is a SETUP screen; naming a channel leaves it
  _openMail = null;           // a mail detail is a screen too: a lens change lands on that lens's LIST
  _confirmDisconnect = null;  // a pending confirmation never outlives the screen that asked for it
}

function injectStyles(){
  if(document.getElementById("hb-msg-css"))return;
  const s=document.createElement("style"); s.id="hb-msg-css"; s.textContent=`
  /* Fluid width, ANCHORED to the parent card (V2-615, same fix as youtube's V2-597): the old
     width:min(480px,92vw) capped the readable column at 480px FOREVER, even on a card the operator had
     deliberately dragged much wider to read a long line (a tracking URL, a long subject) — the card grew,
     the text column inside it did not. The CARD decides the width now; box-sizing keeps padding from
     overflowing it. */
  .hb-msg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:100%;box-sizing:border-box}
  /* V2-680 — a READING screen (an open mail, an open thread) takes the whole card and scrolls INSIDE it,
     the way any mail client does: the message body gets every spare pixel and the reply box is pinned to
     the bottom edge where it can always be reached. The operator's report was that a three-page mail was
     shown through a keyhole while the card around it sat mostly empty.
     Only these two screens opt in (the .full class): the dashboard and the connector wizard are stacks of
     boxes that legitimately scroll as one page, and giving them a fixed height would only pin their own
     headers against a short card.
     NOTE — this deliberately does NOT disable the host's own scroller the way the video and agenda widgets
     do. Measured on the real card chrome: with the height chain in place the widget is exactly the card's
     height and the host never scrolls, so the rule would change nothing; and in the one case it COULD
     change something — the height failing to resolve — it would clip the mail with no scrollbar at all,
     which is strictly worse than a card that scrolls. */
  .hb-msg.full{height:100%;display:flex;flex-direction:column;min-height:0}
  .hb-msg.full > .thread{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
  .hb-msg.full > .thread > .thd{flex:0 0 auto}
  /* The body is the ONE part that grows and scrolls; everything else keeps its natural height. */
  .hb-msg.full > .thread > .mdet,
  .hb-msg.full > .thread > .tl{flex:1 1 auto;min-height:0;overflow:auto;max-height:none}
  .hb-msg.full > .thread > .compose{flex:0 0 auto}
  /* V2-611 redesign — the header is its OWN band, visually separated from the content below it (the
     operator's ask: "que se delimiten mejor las secciones"), and every icon in it is a real, bigger button
     with its own hover/click target — not a bare glyph floating in the row. */
  .hb-msg .hd{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 0 14px;padding:2px 2px 14px;
    border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-msg .hd b{font-size:17px} .hb-msg .hd .sub{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-msg .hdtitle{cursor:pointer;border-radius:8px;padding:4px 7px;margin:-4px -7px}
  .hb-msg .hdtitle:hover{background:var(--hb-hover,#eef3f9)}
  .hb-msg .dots{display:flex;gap:4px;margin-left:auto}
  /* V2-616 — a second cluster (connectors ⚙/🔌/Limpiar), set apart from the channel dots by a divider and
     its own left padding rather than sharing the plain .hd gap every other pair of icons uses. */
  .hb-msg .hdactions{display:flex;align-items:center;gap:4px;padding-left:10px;margin-left:6px;
    border-left:1px solid var(--hb-line,#e3e8f0)}
  .hb-msg .picon{display:inline-flex;align-items:center;justify-content:center;opacity:.4;flex:0 0 auto;
    width:34px;height:34px;border-radius:10px;cursor:pointer}
  .hb-msg .picon svg{width:20px;height:20px}
  .hb-msg .picon:hover{background:var(--hb-hover,#eef3f9);opacity:.7}
  .hb-msg .picon.on{opacity:1}
  .hb-msg .picon.on:hover{opacity:1;background:var(--hb-hover,#eef3f9)}
  .hb-msg .picon.filt{background:var(--hb-hover,#eef3f9);box-shadow:inset 0 0 0 1.5px currentColor}
  .hb-msg .pdot{width:18px;height:18px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
    font-size:9.5px;font-weight:700;color:#fff;background:var(--hb-neutral,#3a4a5c);opacity:.5;flex:0 0 auto}
  .hb-msg .pdot.on{opacity:1;background:var(--hb-accent2,#16B8A6)}
  .hb-msg .gear{border:0;background:transparent;color:var(--hb-muted,#3a4757);cursor:pointer;font-size:17px;
    width:34px;height:34px;border-radius:10px;line-height:1}
  .hb-msg .gear:hover,.hb-msg .gear.active{background:var(--hb-hover,#eef3f9);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .clr{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:8px;padding:6px 11px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-msg .clr:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}

  /* Settings. */
  .hb-msg .settings{border:1px solid var(--hb-line,#eef1f6);border-radius:11px;padding:11px 12px;margin-bottom:11px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .stitle{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--hb-muted-2,#9aa7b8);margin:9px 0 6px}
  .hb-msg .stitle:first-child{margin-top:0}
  .hb-msg .seg{display:inline-flex;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;overflow:hidden}
  .hb-msg .segbtn{border:0;background:var(--hb-bg,#fff);color:var(--hb-muted,#5b6b82);font-size:12px;padding:6px 13px;cursor:pointer}
  .hb-msg .segbtn+.segbtn{border-left:1px solid var(--hb-line,#e3e8f0)}
  .hb-msg .segbtn.active{background:var(--hb-accent,#3D6FE0);color:#fff}

  /* COMPLETE profile (original). */
  .hb-msg .list{display:flex;flex-direction:column;gap:7px;max-height:52vh;overflow:auto}
  .hb-msg .row{display:flex;gap:9px;align-items:flex-start;padding:9px 10px;border:1px solid var(--hb-line,#eef1f6);border-radius:11px;background:var(--hb-bg,#fff)}
  .hb-msg .row.mine{background:var(--hb-warn-bg,#fff7e8);border-color:var(--hb-warn-border,#f2dca6)}
  .hb-msg .dot{width:8px;height:8px;border-radius:50%;margin-top:5px;flex:0 0 auto}
  .hb-msg .body{flex:1;min-width:0}
  .hb-msg .from{font-size:13px;font-weight:600;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .hb-msg .from .grp{font-weight:400;color:var(--hb-muted-2,#7d8a9c);font-size:11px}
  .hb-msg .badge{font-size:10px;font-weight:700;color:#fff;border-radius:6px;padding:1px 6px;letter-spacing:.02em}
  .hb-msg .from .tag{font-size:10px;font-weight:600;color:var(--hb-warn-ink,#9a6a00);background:var(--hb-warn-bg,#fff3d6);border:1px solid var(--hb-warn-border,#f2dca6);border-radius:6px;padding:0 5px}
  .hb-msg .msg{font-size:13px;color:var(--hb-ink,#0d1622);margin-top:2px;white-space:pre-wrap;word-break:break-word}
  .hb-msg .why{font-size:11px;color:var(--hb-muted,#6b7b92);margin-top:3px;font-style:italic}
  .hb-msg .acts{display:flex;flex-direction:column;gap:4px;flex:0 0 auto}
  .hb-msg .acts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:8px;width:30px;height:26px;font-size:13px;cursor:pointer;color:var(--hb-muted,#3a4757);line-height:1}
  .hb-msg .acts button:hover{border-color:var(--hb-accent2,#16B8A6);color:#0f766e}
  .hb-msg .acts .mute{font-size:11px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .acts .mute:hover{border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}

  /* SIMPLE profile: minimal timeline, Claude Code / VS Code style. */
  .hb-msg .tl{display:flex;flex-direction:column;max-height:56vh;overflow:auto}
  .hb-msg .trow{display:flex;gap:10px;align-items:flex-start;padding:11px 2px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-msg .trow:last-child{border-bottom:0}
  .hb-msg .trow:hover .tacts{opacity:1}
  .hb-msg .tlead{width:7px;height:7px;border-radius:50%;margin-top:8px;flex:0 0 auto;background:transparent}
  .hb-msg .tmain{flex:1;min-width:0}
  .hb-msg .thead{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:3px}
  .hb-msg .pchip{width:19px;height:19px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
    font-size:10px;font-weight:700;color:#fff;flex:0 0 auto}
  .hb-msg .tfrom{font-size:14.5px;font-weight:600;color:var(--hb-ink,#0d1622)}
  .hb-msg .tgrp,.hb-msg .tpara{font-size:12.5px;color:var(--hb-muted,#6b7b92);font-weight:400}
  .hb-msg .more{display:inline-block;margin-top:4px;font-size:12.5px;color:var(--hb-accent,#3D6FE0);cursor:pointer}
  .hb-msg .more:hover{text-decoration:underline}
  .hb-msg .tacts{display:flex;gap:2px;flex:0 0 auto;opacity:.3;transition:opacity .12s}
  .hb-msg .tacts button{border:0;background:transparent;border-radius:7px;width:26px;height:24px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#5b6b82);line-height:1}
  .hb-msg .tacts button:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}

  /* EMAIL default view (V2-610): a Gmail-style compact row — sender + subject in two lines, no body — and
     its detail screen. Reuses .tlead/.thd/.tacts from the shapes above so urgency, the back-crumb and the
     action buttons stay visually consistent across every screen of this widget. */
  .hb-msg .mrow{display:flex;gap:10px;align-items:flex-start;padding:10px 2px;border-bottom:1px solid var(--hb-line,#eef1f6);cursor:pointer}
  .hb-msg .mrow:last-child{border-bottom:0}
  .hb-msg .mrow:hover{background:var(--hb-hover,#eef3f9)}
  .hb-msg .mrow:hover .tacts{opacity:1}
  .hb-msg .mmain{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}
  .hb-msg .mline1{display:flex;align-items:baseline;gap:8px}
  .hb-msg .mfrom{font-size:14.5px;font-weight:600;color:var(--hb-ink,#0d1622);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60%}
  .hb-msg .mwhen{margin-left:auto;font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);flex:0 0 auto}
  .hb-msg .msubj{font-size:13.5px;color:var(--hb-muted,#5f6b7c);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-msg .mdet{padding:2px 2px 10px}
  .hb-msg .mdsubj{font-size:17px;font-weight:700;color:var(--hb-ink,#0d1622);margin-bottom:6px;word-break:break-word}
  .hb-msg .mdmeta{display:flex;align-items:baseline;gap:8px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-msg .mdfrom{font-size:14px;font-weight:600;color:var(--hb-ink,#0d1622)}
  .hb-msg .mdwhen{font-size:12px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .mdbody{font-size:14px;line-height:1.6;color:var(--hb-ink,#0d1622);white-space:pre-wrap;word-break:break-word}
  .hb-msg .mdbody a.lnk{color:var(--hb-accent,#3D6FE0);text-decoration:underline}

  /* Grouped CHAT list + open thread. */
  .hb-msg .chatrow{cursor:pointer;margin:0 -8px;padding-left:8px;padding-right:8px;border-radius:9px}
  .hb-msg .chatrow:hover{background:var(--hb-hover,#eef3f9)}
  .hb-msg .tcount{background:var(--hb-neutral,#3a4a5c);color:#fff;font-size:10.5px;font-weight:700;border-radius:999px;
    min-width:17px;height:17px;padding:0 5px;display:inline-flex;align-items:center;justify-content:center}
  .hb-msg .tprev{font-size:13.5px;color:var(--hb-muted,#5f6b7c);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-msg .thd{display:flex;align-items:center;gap:9px;margin:0 0 10px;padding-bottom:9px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  /* V2-616 F3 — a real button, in the corner, never a bare underlined link: the operator's own words
     ("estas flechas así largas que se subraya... no me gusta nada"). margin-left:auto on the LAST child
     pushes it to the far right while the name (appended first) stays left, same pattern .chanhead already
     used for its own back link — now sharing the SAME visual language instead of two different ones. */
  .hb-msg .thd .back{margin-left:auto;flex:0 0 auto;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);cursor:pointer;font-size:12.5px;font-weight:600;padding:6px 12px;border-radius:8px}
  .hb-msg .thd .back:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0);background:var(--hb-hover,#eef3f9)}
  .hb-msg .thdname{font-size:15px}
  /* COMPOSE BAR (V2-611): dictate or type, see it, then send — by button or by a later voice order.
     .bt/.bt-primary etc. are already declared below (the wizard's own buttons) — reused as-is. */
  .hb-msg .compose{margin-top:12px;padding-top:10px;border-top:1px solid var(--hb-line,#eef1f6)}
  /* V2-680 — the box is at least FIVE rows (the operator's own minimum: a reply is written, not tweeted),
     and the send button sits to its RIGHT rather than on a row underneath, so growing the box never pushes
     the button off the bottom of the card. */
  .hb-msg .composemain{display:flex;gap:9px;align-items:stretch}
  .hb-msg .composebox{flex:1 1 auto;min-width:0;box-sizing:border-box;resize:vertical;min-height:112px;
    font:inherit;font-size:14px;line-height:1.45;color:var(--hb-ink,#0d1622);background:var(--hb-hover,#eef3f9);
    border:1px solid var(--hb-line,#eef1f6);border-radius:10px;padding:9px 11px}
  .hb-msg .composebox:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .thread.plat-whatsapp .composebox:focus{border-color:#16B8A6}
  .hb-msg .thread.plat-telegram .composebox:focus{border-color:#2AABEE}
  .hb-msg .thread.plat-email .composebox:focus{border-color:#D8452D}
  .hb-msg .composeside{display:flex;flex-direction:column;gap:6px;flex:0 0 auto;justify-content:flex-end}
  .hb-msg .composeside .bt{white-space:nowrap}
  .hb-msg .composerow{display:flex;justify-content:flex-end;margin-top:6px}
  /* The reply / reply-all selector, ABOVE the box (email only — the other platforms have no second
     recipient to include). A segmented control, the same .seg language the settings panel already uses. */
  .hb-msg .composetop{display:flex;align-items:center;gap:9px;margin-bottom:7px;flex-wrap:wrap}
  .hb-msg .composehint{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .composesaved{font-size:11.5px;color:var(--hb-accent2,#16B8A6);font-weight:600}
  /* V2-616 — the open thread as LEFT/RIGHT bubbles, not an indented copy of the same row (V2-546's old
     shape). His report, verbatim in spirit: in a 1:1 chat the sender's name on every line is noise (the
     header above already names who this is), and his own replies need to read apart from theirs at a
     glance, the ordinary chat convention. isGroup (V2-616, thread.py) is the only reason a bubble still
     carries a name — a group has no single "who this is" for the header to say once.
     NOTE: this whole block is inside a JS template literal, so a backtick here ENDS it — write prose here
     without one, ever (it broke this exact widget once already). */
  .hb-msg .tbrow{display:flex;padding:3px 2px;justify-content:flex-start}
  .hb-msg .tbrow.out{justify-content:flex-end}
  .hb-msg .tbrow:hover .tacts{opacity:1}
  .hb-msg .tbstack{display:flex;flex-direction:column;max-width:78%;gap:3px}
  .hb-msg .tbrow:not(.out) .tbstack{align-items:flex-start}
  .hb-msg .tbrow.out .tbstack{align-items:flex-end}
  .hb-msg .tbubble{padding:8px 12px;border-radius:16px;background:var(--hb-bubble,#eef1f6);color:var(--hb-ink,#0d1622)}
  .hb-msg .tbrow:not(.out) .tbubble{border-bottom-left-radius:4px}
  .hb-msg .tbrow.out .tbubble{background:var(--hb-accent,#3D6FE0);color:#fff;border-bottom-right-radius:4px}
  .hb-msg .tbubble.urg{box-shadow:inset 3px 0 0 var(--hb-risk,#e5484d)}
  /* V2-616 F4 — WhatsApp reads as WhatsApp, Telegram as Telegram, email as email: his own reply's bubble and
     the compose button take the OPEN thread's platform color (.thread.plat-ID, set once in threadView/
     mailDetail) instead of the one generic accent blue every platform shared before. Literal hex, matching
     PLAT[pl].bg exactly — the same identity, not a second palette that can drift from it. */
  .hb-msg .thread.plat-whatsapp .tbrow.out .tbubble,
  .hb-msg .thread.plat-whatsapp .composerow .bt-primary{background:#16B8A6}
  .hb-msg .thread.plat-telegram .tbrow.out .tbubble,
  .hb-msg .thread.plat-telegram .composerow .bt-primary{background:#2AABEE}
  .hb-msg .thread.plat-email .tbrow.out .tbubble,
  .hb-msg .thread.plat-email .composerow .bt-primary{background:#D8452D}
  .hb-msg .tbfrom{font-size:12px;font-weight:700;margin-bottom:2px;color:var(--hb-accent,#3D6FE0)}
  .hb-msg .tbtitle{font-size:14px;font-weight:600;margin:0 0 3px}
  .hb-msg .tbbody{font-size:14px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
  .hb-msg .tbbody.clamp{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .hb-msg .tbbody a.lnk{color:inherit;text-decoration:underline}
  .hb-msg .tbrow.out .more{color:#fff}
  .hb-msg .tbwhen{display:block;margin-top:3px;font-size:10.5px;text-align:right;opacity:.6}
  .hb-msg .tbrow.out .tbwhen{color:rgba(255,255,255,.85)}
  .hb-msg .tstart{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;
                  padding:8px 2px 12px}
  .hb-msg .tsl{font-size:11.5px;color:var(--hb-muted,#7b879c)}
  .hb-msg .tsbtn{border:1px solid var(--hb-line,#eef1f6);background:transparent;color:var(--hb-accent,#3D6FE0);
                 border-radius:999px;padding:3px 11px;font-size:11.5px;cursor:pointer}
  .hb-msg .tsbtn:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .tsbtn:disabled{color:var(--hb-muted,#7b879c);cursor:default;border-color:var(--hb-line,#eef1f6)}

  /* Media previews (V2-543): same-origin asset route only, elements not requests (isolation contract). */
  .hb-msg .mediaw{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
  .hb-msg .mediaw .matt{max-width:220px;max-height:170px;border-radius:10px;border:1px solid var(--hb-line,#e3e8f0);display:block}
  .hb-msg .mediaw video.mvid{max-width:260px;max-height:200px;border-radius:10px;background:#000}
  /* V2-616 F5 — the custom player: wide, FIXED width whatever the clip's length (fixed bar COUNT, not one
     derived from duration), a real drag-to-seek surface instead of the tiny native scrubber. */
  .hb-msg .maudio{display:flex;align-items:center;gap:8px;width:100%;min-width:220px;box-sizing:border-box}
  .hb-msg .mapbtn{flex:0 0 auto;width:32px;height:32px;border-radius:50%;border:0;cursor:pointer;
    background:var(--hb-accent,#3D6FE0);color:#fff;font-size:12px;display:flex;align-items:center;justify-content:center}
  .hb-msg .mapbtn:hover{filter:brightness(1.08)}
  .hb-msg .mawave{flex:1 1 auto;min-width:0;height:30px;display:flex;align-items:center;gap:2.5px;cursor:pointer;touch-action:none}
  .hb-msg .mabar{flex:1 1 0;min-width:2px;max-width:4px;border-radius:2px;background:var(--hb-muted-2,#9aa7b8);opacity:.5}
  .hb-msg .mabar.played{background:var(--hb-accent,#3D6FE0);opacity:1}
  .hb-msg .matime{flex:0 0 auto;font-size:11px;color:var(--hb-muted-2,#9aa7b8);font-variant-numeric:tabular-nums}
  .hb-msg .tbrow.out .mapbtn{background:rgba(255,255,255,.28)}
  .hb-msg .tbrow.out .mabar{background:rgba(255,255,255,.4)}
  .hb-msg .tbrow.out .mabar.played{background:#fff;opacity:.95}
  .hb-msg .tbrow.out .matime{color:rgba(255,255,255,.85)}
  .hb-msg .thread.plat-whatsapp .mapbtn,.hb-msg .thread.plat-whatsapp .mabar.played{background:#16B8A6}
  .hb-msg .thread.plat-telegram .mapbtn,.hb-msg .thread.plat-telegram .mabar.played{background:#2AABEE}
  .hb-msg .thread.plat-email .mapbtn,.hb-msg .thread.plat-email .mabar.played{background:#D8452D}
  .hb-msg .thread.plat-whatsapp .tbrow.out .mabar.played,
  .hb-msg .thread.plat-telegram .tbrow.out .mabar.played,
  .hb-msg .thread.plat-email .tbrow.out .mabar.played{background:#fff}
  .hb-msg .mediaw a.mdoc,.hb-msg .mediaw span.mdoc{font-size:12.5px;color:var(--hb-accent,#3D6FE0);text-decoration:none;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:4px 9px}
  .hb-msg .mediaw a.mdoc:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .twhen{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-left:auto;flex:0 0 auto}

  .hb-msg .empty{text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:13px;padding:22px 0}
  .hb-msg .rest{text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:11px;opacity:.75;padding:8px 0 2px}

  /* ACTIVITY criterion bar (V2-624): the per-platform view criterion the operator set, always visible with
     its own off switch — a lens in a mode he cannot see is a lens that lies. */
  .hb-msg .critbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:2px 0 8px;
    padding:6px 10px;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;
    background:var(--hb-hover,#eef3f9)}
  .hb-msg .critlbl{font-size:12px;font-weight:600;color:var(--hb-ink,#26313d)}
  .hb-msg .critfetch{margin-left:auto;font-size:12px;padding:3px 8px}
  .hb-msg .critoff{flex:0 0 auto;border:0;background:transparent;cursor:pointer;font-size:13px;
    color:var(--hb-muted-2,#9aa7b8);padding:2px 4px}
  .hb-msg .critoff:hover{color:var(--hb-risk,#e5484d)}

  /* NARROW SCREENS (V2-559). MEASURED FIRST, and the measurement removed most of what was written here:
     rendered at 375px in six states (connect panel with three failures, both wizards, the QR, the chat list
     and an open thread), NOTHING was clipped and nothing left the viewport, and the wrap rules drafted for the
     channel row only made every row twice as tall for a defect that does not exist (the long statuses and the
     action button never co-occur). What is left is the part that IS an improvement on a phone: let a received
     photo use the whole card instead of a 220px thumbnail taken from the desktop (the root's own width is
     fluid now, V2-615, so it needs no override here). */
  @media (max-width: 430px){
    .hb-msg .mediaw .matt,.hb-msg .mediaw video.mvid{max-width:100%;max-height:none}
  }
  .hb-msg .linkcard{border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;padding:13px 14px;margin-bottom:10px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .linkcard .ch{display:flex;align-items:center;gap:8px;margin-bottom:9px}
  .hb-msg .linkcard .ch b{font-size:14px}
  .hb-msg label.f{display:block;font-size:12.5px;font-weight:600;color:var(--hb-muted,#5b6b82);margin:10px 0 4px}
  .hb-msg input.f,.hb-msg select.f{width:100%;box-sizing:border-box;border:1px solid var(--hb-line,#e3e8f0);border-radius:9px;padding:10px 12px;font-size:14px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hb-msg input.f:focus,.hb-msg select.f:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .err{color:var(--hb-risk,#e5484d);font-size:12.5px;margin-top:8px}
  .hb-msg .errfield{border-color:var(--hb-risk,#e5484d)!important}

  /* Guided connect wizard (V2-559, redesigned V2-570). The operator asked for an ASSISTANT: one step
     visible at a time, real margins, and a breadcrumb back to the connector list — a stack of three boxes
     read as optional; one box with "Paso 2 de 3" reads as a path. */
  .hb-msg .wstep{border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;padding:15px 16px 16px;background:var(--hb-bg,#fff);margin:2px 0 14px}
  .hb-msg .wstep.done{border-color:var(--hb-accent2,#16B8A6)}
  .hb-msg .whead{display:flex;align-items:center;gap:10px;margin-bottom:12px}
  .hb-msg .wnum{width:25px;height:25px;flex:0 0 auto;border-radius:50%;display:inline-flex;align-items:center;
    justify-content:center;font-size:12.5px;font-weight:700;color:#fff;background:var(--hb-neutral,#3a4a5c)}
  .hb-msg .wstep.done .wnum{background:var(--hb-accent2,#16B8A6)}
  .hb-msg .wtitle{font-size:15px;font-weight:700;color:var(--hb-ink,#0d1622)}
  .hb-msg .whead .wcount{margin-left:auto;flex:0 0 auto}
  .hb-msg .wcount{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .wbody{font-size:13.5px;color:var(--hb-muted,#4a5a70);line-height:1.6}
  .hb-msg .wbody b{color:var(--hb-ink,#0d1622)}
  .hb-msg .wlink{display:inline-flex;align-items:center;gap:6px;margin-top:11px;border:1px solid var(--hb-accent,#3D6FE0);
    color:var(--hb-accent,#3D6FE0);border-radius:9px;padding:9px 14px;font-size:13px;font-weight:600;
    text-decoration:none;background:transparent}
  .hb-msg .wlink:hover{background:var(--hb-accent,#3D6FE0);color:#fff}
  .hb-msg .wtip{margin-top:10px;font-size:12.5px;color:var(--hb-muted,#5b6b82);background:var(--hb-bg-soft,#fbfdff);
    border:1px solid var(--hb-line,#eef1f6);border-radius:9px;padding:9px 11px;line-height:1.55}
  .hb-msg .wtip b{color:var(--hb-ink,#0d1622)}
  .hb-msg .wstep label.f:first-of-type{margin-top:0}
  .hb-msg .qr-wrap{text-align:center;padding:4px 0}
  .hb-msg .qr-wrap img{width:220px;max-width:78vw;border-radius:12px;border:1px solid var(--hb-line,#e3e8f0);background:#fff;padding:8px}
  .hb-msg .qr-wrap .cap{font-size:12.5px;color:var(--hb-muted,#3a4757);margin-top:9px;line-height:1.55}
  .hb-msg .qr-wrap .cap b{color:var(--hb-ink,#0d1622)}
  .hb-msg .waiting{color:var(--hb-muted-2,#7d8a9c);font-size:12.5px;padding:6px 0;text-align:center}
  /* Loader (spinner) + connection detail. */
  .hb-msg .spin{display:inline-block;width:15px;height:15px;border-radius:50%;vertical-align:-2px;margin-right:7px;
    border:2px solid var(--hb-line,#e3e8f0);border-top-color:var(--hb-accent,#3D6FE0);animation:hbspin .7s linear infinite}
  @keyframes hbspin{to{transform:rotate(360deg)}}
  .hb-msg .waitbox{display:flex;flex-direction:column;align-items:center;gap:6px;padding:10px 0;text-align:center}
  .hb-msg .waitbox .lbl{font-size:13px;color:var(--hb-ink,#0d1622);font-weight:600}
  .hb-msg .waitbox .det{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.5;max-width:320px}
  /* Connection error card. */
  .hb-msg .errcard{border:1px solid var(--hb-risk,#e5484d);border-radius:11px;padding:12px 14px;margin-bottom:14px;background:color-mix(in srgb,var(--hb-risk,#e5484d) 8%,transparent)}
  .hb-msg .errcard .et{font-size:13px;color:var(--hb-ink,#0d1622);line-height:1.55;margin-bottom:10px}
  .hb-msg .errcard .et b{color:var(--hb-risk,#e5484d)}
  /* Breadcrumb (V2-570): back to the connector list + which connector we are on. */
  .hb-msg .crumb{display:flex;align-items:center;gap:7px;margin:2px 0 16px;font-size:13px}
  .hb-msg .crumb .back{cursor:pointer;color:var(--hb-accent,#3D6FE0);font-weight:600}
  .hb-msg .crumb .back:hover{text-decoration:underline}
  .hb-msg .crumb .sep{color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .crumb .cur{color:var(--hb-ink,#0d1622);font-weight:700}
  /* Homogeneous buttons (V2-570): one scale for every wizard/list/status action, instead of the
     .btn/.cbtn/.dbtn set that had grown three different heights and paddings. */
  .hb-msg .bt{height:38px;padding:0 18px;border-radius:10px;font-size:13.5px;font-weight:600;cursor:pointer;
    display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box}
  .hb-msg .bt:disabled{opacity:.6;cursor:default}
  .hb-msg .bt-primary{border:0;color:#fff;background:var(--hb-accent,#3D6FE0)}
  .hb-msg .bt-primary:hover:not(:disabled){filter:brightness(1.06)}
  .hb-msg .bt-ghost{border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-muted,#5b6b82)}
  .hb-msg .bt-ghost:hover:not(:disabled){border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .bt-danger{border:0;color:#fff;background:var(--hb-risk,#e5484d)}
  .hb-msg .wfoot{display:flex;gap:9px;margin-top:10px}
  .hb-msg .wfoot .bt-primary{flex:1 1 auto}
  /* Connector LIST screen (V2-570): a grid of icon boxes replaces the stacked rows, so the list stays
     compact and scannable with 3 connectors today or 20 tomorrow — the operator's own worry about having
     to scroll past a long vertical list to reach the wizard. */
  .hb-msg .chanhead{display:flex;align-items:center;gap:8px;margin:2px 0 16px}
  .hb-msg .chanhead b{font-size:14.5px}
  /* V2-616 F3 — the SAME back-button chip as .thd, not a second visual language for the same affordance.
     display:inline-flex because this one is a <span> (not a <button>): padding/border on a plain inline
     element does not box properly. */
  .hb-msg .chanhead .back{display:inline-flex;align-items:center;margin-left:auto;flex:0 0 auto;
    border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);cursor:pointer;font-size:12.5px;font-weight:600;padding:6px 12px;border-radius:8px}
  .hb-msg .chanhead .back:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0);background:var(--hb-hover,#eef3f9)}
  .hb-msg .chanhead .hint{font-size:12.5px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-msg .igrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:12px}
  .hb-msg .ibox{display:flex;flex-direction:column;align-items:center;gap:7px;padding:16px 10px;
    border:1px solid var(--hb-line,#e3e8f0);border-radius:13px;background:var(--hb-bg,#fff);cursor:pointer;
    font:inherit;color:inherit}
  .hb-msg .ibox:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .ibox.sel{border-color:var(--hb-accent,#3D6FE0);background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 6%,transparent)}
  .hb-msg .ibox.conn{border-color:var(--hb-accent2,#16B8A6)}
  .hb-msg .ibox.conn .isub{color:var(--hb-accent2,#16B8A6);font-weight:600}
  .hb-msg .ibox .iicon{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .ibox .iicon .picon{opacity:1}
  .hb-msg .ibox .iicon svg{width:24px;height:24px}
  .hb-msg .ibox .ilabel{font-size:13px;font-weight:600;color:var(--hb-ink,#0d1622);text-align:center}
  .hb-msg .ibox .isub{font-size:11px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .ibox .iavatar{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;
    font-size:16px;font-weight:700;color:#fff;background:var(--hb-accent,#3D6FE0)}
  /* Connected-status screen + disconnect confirmation (unscoped, no longer nested under a removed .chan row). */
  .hb-msg .cfm{margin-top:10px;font-size:12.5px;color:var(--hb-ink,#0d1622)}
  .hb-msg .cfm .row{display:flex;gap:8px;margin-top:8px}
  .hb-msg .connbtn{border:0;background:transparent;color:var(--hb-muted,#3a4757);cursor:pointer;font-size:17px;width:34px;height:34px;border-radius:10px;line-height:1}
  .hb-msg .connbtn:hover,.hb-msg .connbtn.active{background:var(--hb-hover,#eef3f9);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .conns{display:flex;flex-wrap:wrap;gap:6px}
  .hb-msg .conns .ok{font-size:11px;color:var(--hb-muted,#5b6b82);display:flex;align-items:center;gap:5px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:3px 9px}
  .hb-msg .conns .ok .lk{color:var(--hb-muted-2,#9aa7b8);cursor:pointer;text-decoration:underline}
  .hb-msg .conns .ok .lk:hover{color:var(--hb-risk,#e5484d)}
  `; document.head.appendChild(s);
}

function el(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }

function badge(platform){
  const p=PLAT[platform]||{label:platform||"?",bg:"var(--hb-muted,#6b7b92)"};
  const b=el("span","badge",p.label); b.style.background=p.bg; return b;
}

// Small circle with the platform initial, used in the header (connection state, "on"=green) and in each simple
// profile row (fixed brand color, informational rather than state).
function miniDot(platform, on){
  const p=PLAT[platform]||{label:"?"};
  const d=el("span","pdot"+(on?" on":""), p.label[0]);
  d.title = p.label + (on ? ": conectado" : ": no conectado");
  return d;
}

function platformChip(platform){
  const p=PLAT[platform]||{label:platform||"?",bg:"var(--hb-muted,#6b7b92)"};
  const c=el("span","pchip",(p.label||"?")[0]); c.style.background=p.bg; c.title=p.label;
  return c;
}

// Real brand icon for the header connection state. `on` only changes opacity (dimmed = disconnected); brand color
// always remains, so the app stays recognizable even when unlinked.
function brandIcon(platform, on){
  const p=PLAT[platform]||{label:platform||"?",bg:"var(--hb-muted,#6b7b92)"};
  const spec=BRAND_SVG[platform];
  const wrap=el("span","picon"+(on?" on":""));
  wrap.title=p.label+(on?": conectado":": no conectado");
  wrap.style.color=p.bg;
  if(spec){
    const svg=document.createElementNS(SVG_NS,"svg");
    svg.setAttribute("viewBox",spec.viewBox); svg.setAttribute("width","17"); svg.setAttribute("height","17");
    svg.setAttribute("aria-hidden","true");
    const path=document.createElementNS(SVG_NS,"path");
    path.setAttribute("d",spec.path); path.setAttribute("fill","currentColor");
    svg.appendChild(path); wrap.appendChild(svg);
  } else {
    wrap.appendChild(document.createTextNode((p.label||"?")[0]));
  }
  return wrap;
}

// One box in an icon grid (V2-570): the connector list AND the email-provider picker are both "choose one of
// several, shown as an icon with a label", so they share this renderer instead of one being a grid and the
// other a dropdown. `it.cls` names the extra state class ("sel" = chosen in a picker, "conn" = connected in
// the connector list) — the two never mean the same thing, so they get their own visual language.
function iconGrid(items){
  const grid=el("div","igrid");
  items.forEach(it=>{
    const box=document.createElement("button");
    box.type="button";
    box.className="ibox"+(it.cls?(" "+it.cls):"");
    const holder=el("span","iicon"); holder.appendChild(it.icon); box.appendChild(holder);
    box.appendChild(el("span","ilabel", it.label));
    if(it.sub) box.appendChild(el("span","isub", it.sub));
    if(it.onClick) box.onclick=it.onClick;
    grid.appendChild(box);
  });
  return grid;
}

// No brand icon exists for a specific email PROVIDER (Gmail/Outlook/iCloud/Yahoo) the way one does for the
// whole email channel — an avatar with the provider's initial is honest about that instead of pretending.
function providerAvatar(label){ return el("span","iavatar", (label||"?")[0]); }

// Split a short message title from the rest of the body when they are joined by a blank line, a common pattern in
// triaged messages. If the pattern does not fit, everything is body text with no title.
function splitBody(body){
  const idx = body.indexOf("\n\n");
  if(idx > 0 && idx <= 100){
    const title = body.slice(0, idx).trim();
    const rest = body.slice(idx + 2).trim();
    if(title && !title.includes("\n") && rest) return {title, rest};
  }
  return {title: "", rest: body};
}

// Minimal incoming-text cleanup: collapse excessive line breaks (3+) so huge gaps do not appear. Never touches
// emojis/links/content, only spacing.
function cleanBody(text){
  return String(text==null?"":text).replace(/\n{3,}/g, "\n\n").trim();
}

// ── Media (V2-543) ──────────────────────────────────────────────────────────
// The bridge/connectors store `[<type> received]` as an internal English placeholder; on screen it becomes a
// human label. The bytes themselves are served by the widget's own asset route — an <img>/<audio>/<video>
// element with a same-origin src is NOT a fetch (isolation contract, same reading as navegador/imagenes).
const MEDIA_LABEL = {image:"📷 Foto", video:"🎥 Vídeo", audio:"🎵 Audio", ptt:"🎤 Nota de voz", document:"📄 Documento"};
const PLACEHOLDER_RE = /^\[(image|video|audio|ptt|document) received\]$/;

// V2-622 — a bare media placeholder ("[audio received]", or an empty body with a mediaType) becomes a label
// like "🎵 Audio" purely so something reads where the caption would be. Once a real media block actually
// renders below it, that label is pure noise — the player/thumbnail/link already say what it is. Only a
// REAL caption the sender actually typed still needs the text line.
function isBareMediaLabel(body){
  const b = cleanBody(body);
  return !b || PLACEHOLDER_RE.test(b);
}

function displayBody(body, mediaType){
  const b = cleanBody(body);
  const m = b.match(PLACEHOLDER_RE);
  if(m) return MEDIA_LABEL[m[1]] || b;
  if(!b && mediaType) return MEDIA_LABEL[mediaType] || "";
  return b;
}

function fmtWhen(ts){
  const t = Number(ts||0);
  if(!t) return "";
  const d = new Date(t*1000), now = new Date();
  const hm = d.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"});
  if(d.toDateString() === now.toDateString()) return hm;
  return d.toLocaleDateString([], {day:"numeric", month:"short"}) + " " + hm;
}

// V2-616 F5 — a real seek control, wide, FIXED width regardless of the clip's length. The operator: WhatsApp's
// native <audio controls> lets him play/pause but not drag to a point ("no puedo avanzar hasta cierto punto"),
// and he wants it wider and shaped like a waveform, with the SAME width whether the clip is one minute or two
// hours long.
//
// The bars are DECORATIVE, not real amplitude — worth saying plainly, because a fake waveform that LOOKS
// measured is exactly the kind of "true sentence about the wrong mechanism" this codebase treats as the worst
// failure shape. A real one needs the file's raw samples (Web Audio's decodeAudioData), and getting those
// requires fetching the bytes ourselves — `fetch()`/`XMLHttpRequest` are BANNED sinks in widget.js on purpose
// (widgets/validator.py, the "no network from the client" boundary V2-557 drew): the <audio> element loads
// its own `src` through the browser's OWN media pipeline, never through code we could point anywhere else.
// A FIXED bar count (not one derived from duration) is what keeps the width constant on its own — no decode
// needed for that part at all.
const _WAVE_BARS = 28;

function _waveBarHeight(seed, i){
  // A small, deterministic, non-cryptographic hash: same seed+index always draws the same bar, so the shape
  // does not jitter on re-render, and two different clips still look visually distinct from each other.
  let h = 0;
  const s = seed + "#" + i;
  for(let k=0; k<s.length; k++) h = (h*31 + s.charCodeAt(k)) >>> 0;
  return 24 + (h % 76); // 24-99, as a percentage of the wave's own height
}

function audioPlayer(url){
  const wrap = el("div","maudio");
  const btn = document.createElement("button");
  btn.type="button"; btn.className="mapbtn"; btn.textContent="▶"; btn.title="Reproducir";
  const wave = el("div","mawave");
  const bars = [];
  for(let i=0; i<_WAVE_BARS; i++){
    const bar = el("span","mabar");
    bar.style.height = _waveBarHeight(url, i) + "%";
    bars.push(bar);
    wave.appendChild(bar);
  }
  const time = el("span","matime","0:00");
  // preload="metadata": duration has to be known for the bar to mean anything and for a drag BEFORE the first
  // play to compute a real target time — it fetches only the file's header, never the audio itself (that
  // still waits for the operator's own play/seek, same "never autoplay" contract the old native player had).
  const au = document.createElement("audio");
  au.className="maud"; au.preload="metadata"; au.src=url; au.style.display="none";
  wrap.append(btn, wave, time, au);

  const fmt = (s)=>{ s = Math.max(0, Math.floor(s || 0)); return Math.floor(s/60)+":"+String(s%60).padStart(2,"0"); };
  const refresh = ()=>{
    const d = au.duration;
    const known = isFinite(d) && d > 0;
    time.textContent = known ? (fmt(au.currentTime)+" / "+fmt(d)) : fmt(au.currentTime);
    const played = known ? Math.round((au.currentTime/d) * bars.length) : 0;
    bars.forEach((b,i)=> b.classList.toggle("played", i < played));
  };
  au.addEventListener("timeupdate", refresh);
  au.addEventListener("loadedmetadata", refresh);
  au.addEventListener("play", ()=>{ btn.textContent="⏸"; btn.title="Pausar"; });
  au.addEventListener("pause", ()=>{ btn.textContent="▶"; btn.title="Reproducir"; });
  au.addEventListener("ended", ()=>{ btn.textContent="▶"; btn.title="Reproducir"; });
  btn.onclick = ()=>{ if(au.paused) au.play().catch(()=>{}); else au.pause(); };

  const seekTo = (clientX)=>{
    const d = au.duration;
    if(!isFinite(d) || d <= 0) return;         // duration not known yet — nothing to seek INTO
    const r = wave.getBoundingClientRect();
    if(!r.width) return;
    const frac = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
    au.currentTime = frac * d;
    refresh();
  };
  let dragging = false;
  wave.addEventListener("pointerdown", (e)=>{ dragging=true; try{ wave.setPointerCapture(e.pointerId); }catch{} seekTo(e.clientX); });
  wave.addEventListener("pointermove", (e)=>{ if(dragging) seekTo(e.clientX); });
  const stopDrag = (e)=>{ dragging=false; try{ wave.releasePointerCapture(e.pointerId); }catch{} };
  wave.addEventListener("pointerup", stopDrag);
  wave.addEventListener("pointercancel", stopDrag);

  refresh();
  return wrap;
}

function mediaBlock(it){
  const list = it.media || [];
  if(!list.length) return null;
  const w = el("div","mediaw");
  list.forEach(u=>{
    const url = String((u&&u.url)||"");
    if(!url.startsWith("/widgets/")) return;             // our own asset route only, never an arbitrary origin
    const t = (u&&u.type) || it.mediaType || "";
    if(t==="image"){
      const a=document.createElement("a"); a.href=url; a.target="_blank"; a.rel="noopener";
      const img=document.createElement("img"); img.className="matt"; img.src=url;
      img.loading="lazy"; img.decoding="async"; img.alt=(u&&u.name)||"imagen";
      img.onerror=()=>{ a.replaceWith(el("span","mdoc","📷 (no disponible)")); };
      a.appendChild(img); w.appendChild(a);
    } else if(t==="video"){
      const v=document.createElement("video"); v.className="mvid"; v.controls=true; v.preload="metadata"; v.src=url;
      w.appendChild(v);
    } else if(t==="audio"||t==="ptt"){
      w.appendChild(audioPlayer(url));
    } else {
      const a=document.createElement("a"); a.className="mdoc"; a.href=url; a.target="_blank"; a.rel="noopener";
      a.textContent="📄 "+((u&&u.name)||"documento");
      w.appendChild(a);
    }
  });
  return w.childNodes.length ? w : null;
}

const URL_RE = /(https?:\/\/[^\s]+)/g;

// Build the message body as text nodes plus <a> for each detected URL. No innerHTML because bodies come from
// third parties and are untrusted. Normal text remains a plain TextNode.
function linkify(container, text){
  const t = String(text==null ? "" : text);
  let last = 0, m;
  URL_RE.lastIndex = 0;
  while((m = URL_RE.exec(t))){
    if(m.index > last) container.appendChild(document.createTextNode(t.slice(last, m.index)));
    let url = m[0];
    const trail = url.match(/[),.;:!?]+$/);
    let trailStr = "";
    if(trail){ trailStr = trail[0]; url = url.slice(0, -trailStr.length); }
    const a = document.createElement("a");
    a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.className = "lnk";
    a.textContent = url;
    container.appendChild(a);
    if(trailStr) container.appendChild(document.createTextNode(trailStr));
    last = m.index + m[0].length;
  }
  if(last < t.length) container.appendChild(document.createTextNode(t.slice(last)));
}

// Connect/disconnect without touching .env. The widget can only talk through ctx.action (isolation contract: no
// network/fetch from the client), which queues the order in the store; the server supervisor drains it and performs
// the real connect. QR/status appear by themselves on the canvas: store.py emits the SSE notice as soon as the
// supervisor saves the new state, and desktop.js repaints this same card once (never polling, never a separate
// window).

// One numbered box shell, reused for whichever step is CURRENTLY showing (V2-570: only one step renders at a
// time, so this used to wrap three stacked boxes and now wraps exactly one).
function stepBox(n, title, done){
  const box=el("div","wstep"+(done?" done":""));
  const head=el("div","whead"); head.append(el("span","wnum",String(n)), el("span","wtitle",title));
  box.appendChild(head);
  return box;
}

// Per-provider guidance (V2-521): the generic app-password sentence never said WHERE to get one. One line + the
// exact page, switching with the dropdown — the operator asked to be told the process, the token, whatever the
// provider needs, right here.
const EMAIL_GUIDE={
  gmail:   {steps:"Activa la verificación en 2 pasos y entra en la página de contraseñas de aplicación.",
            url:"https://myaccount.google.com/apppasswords", lbl:"Abrir contraseñas de aplicación de Google",
            tip:"Google te la enseña en 4 bloques de 4 letras. Cópiala entera — da igual si trae espacios, "
               +"los quito yo. Lo que NO va aquí es el enlace de la página."},
  outlook: {steps:"Con la verificación en 2 pasos activada, crea una contraseña de aplicación.",
            url:"https://account.live.com/proofs/AppPassword", lbl:"Abrir contraseñas de aplicación de Microsoft",
            tip:"Cópiala tal cual te la muestre. Es una contraseña, no el enlace de la página."},
  icloud:  {steps:"Genera una contraseña específica de app desde tu cuenta de Apple.",
            url:"https://appleid.apple.com/account/manage", lbl:"Abrir appleid.apple.com",
            tip:"Apple la muestra como xxxx-xxxx-xxxx-xxxx. Cópiala con los guiones."},
  otro:    {steps:"Usa la contraseña (o contraseña de app) que te dé tu proveedor de correo.",
            url:"", lbl:"", tip:"Necesitaré además sus servidores IMAP y SMTP, abajo."},
};

// ── Email wizard steps (V2-570) ──────────────────────────────────────────────────────────────────────────
// THREE steps, one visible at a time. Step 1 is the box the operator asked for literally: "put the mail
// providers in a box with an icon in the middle so the user sees all those available" — an icon grid instead
// of a <select>, since a dropdown hides the other options until opened.
function emailStep1Body(d, rerender){
  const wrap=el("div");
  wrap.appendChild(el("div","wbody","Elige el proveedor de tu cuenta de correo."));
  wrap.appendChild(iconGrid(EMAIL_PROVIDERS.map(([v,lab])=>({
    key:v, icon:providerAvatar(lab), label:lab, cls:(d.provider===v?"sel":""),
    onClick:()=>{ d.provider=v; rerender(); },
  }))));
  return wrap;
}

function emailStep2Body(d){
  const wrap=el("div");
  const g=EMAIL_GUIDE[d.provider]||EMAIL_GUIDE.otro;
  wrap.appendChild(el("div","wbody", g.steps));
  if(g.url){
    const link=document.createElement("a"); link.className="wlink"; link.href=g.url;
    link.target="_blank"; link.rel="noopener"; link.textContent=g.lbl+" ↗";
    wrap.appendChild(link);
  }
  if(g.tip) wrap.appendChild(el("div","wtip", g.tip));
  return wrap;
}

// What this step does NOT do: judge the shape of the password. That rule lives in ONE place
// (`connectors/email/credentials.py`) and reaches here as the connection's own error, so the wizard and the
// connector can never drift apart on what a valid app password looks like. Here we only check what is
// unambiguous locally (empty fields, an address that is not one) and strip the spaces the provider prints.
function emailStep3Body(d, refs){
  const wrap=el("div");
  const addrL=el("label","f","Correo"); const addr=document.createElement("input");
  addr.className="f"; addr.type="email"; addr.placeholder="tucuenta@gmail.com"; addr.autocomplete="off";
  addr.value=d.email_address||""; addr.oninput=()=>{d.email_address=addr.value; addr.classList.remove("errfield");};
  const pwL=el("label","f","Contraseña de aplicación"); const pw=document.createElement("input");
  pw.className="f"; pw.type="password"; pw.placeholder="pega aquí la contraseña, no el enlace"; pw.autocomplete="off";
  // The provider PRINTS the password in groups; those spaces are presentation and IMAP AUTH does not want them.
  pw.value=d.email_password||"";
  pw.oninput=()=>{ const clean=pw.value.replace(/\s+/g,""); if(clean!==pw.value) pw.value=clean;
                   d.email_password=clean; pw.classList.remove("errfield"); };
  wrap.append(addrL, addr, pwL, pw);
  refs.addr=addr; refs.pw=pw;

  if(d.provider==="otro"){
    const imapL=el("label","f","Servidor IMAP"); const imap=document.createElement("input");
    imap.className="f"; imap.type="text"; imap.placeholder="imap.tudominio.com";
    imap.value=d.imap_host||""; imap.oninput=()=>{d.imap_host=imap.value;};
    const smtpL=el("label","f","Servidor SMTP"); const smtp=document.createElement("input");
    smtp.className="f"; smtp.type="text"; smtp.placeholder="smtp.tudominio.com";
    smtp.value=d.smtp_host||""; smtp.oninput=()=>{d.smtp_host=smtp.value;};
    wrap.append(imapL, imap, smtpL, smtp);
    refs.imap=imap; refs.smtp=smtp;
  }
  return wrap;
}

// ── Telegram wizard steps (same shape as email, three steps → one at a time) ────────────────────────────
function telegramStep1Body(){
  const wrap=el("div");
  wrap.appendChild(el("div","wbody","Inicia sesión con tu número: te llega un código dentro de la propia app de Telegram."));
  const link=document.createElement("a"); link.className="wlink"; link.href=PLAT.telegram.credLink;
  link.target="_blank"; link.rel="noopener"; link.textContent="Abrir my.telegram.org ↗";
  wrap.appendChild(link);
  return wrap;
}

function telegramStep2Body(){
  const wrap=el("div");
  const b=el("div","wbody");
  b.append(document.createTextNode("Entra en "), el("b",null,"API development tools"),
           document.createTextNode(" y rellena el formulario ("), el("b",null,"App title: Zaelar"),
           document.createTextNode(", "), el("b",null,"Short name: Zaelar"),
           document.createTextNode(", el resto en blanco). Pulsa "), el("b",null,"Create application"),
           document.createTextNode("."));
  wrap.appendChild(b);
  return wrap;
}

function telegramStep3Body(refs){
  const wrap=el("div");
  wrap.appendChild(el("div","wtip","El api_id es un número corto y el api_hash una cadena larga de letras y números."));
  const d=_draft.telegram;
  const idL=el("label","f","api_id"); const idI=document.createElement("input");
  idI.className="f"; idI.type="text"; idI.inputMode="numeric"; idI.placeholder="p.ej. 12345678";
  idI.value=d.api_id||""; idI.oninput=()=>{d.api_id=idI.value;};
  const hL=el("label","f","api_hash"); const hI=document.createElement("input");
  hI.className="f"; hI.type="text"; hI.placeholder="cadena larga de letras y números";
  hI.value=d.api_hash||""; hI.oninput=()=>{d.api_hash=hI.value;};
  wrap.append(idL, idI, hL, hI);
  refs.id=idI; refs.hash=hI;
  return wrap;
}

// WhatsApp needs no credentials — a single step; the QR that follows is a LIVE STATE layered on the wizard
// screen (see renderWizardScreen's `status==="connecting"` branch), not something the user fills in.
function whatsappStepBody(platform){
  const wrap=el("div");
  wrap.appendChild(el("div","wbody","Pulsa Conectar para vincular tu "+PLAT[platform].label+" con un código QR (como WhatsApp Web)."));
  return wrap;
}

const WIZARD_STEPS = {
  telegram: [{title:"Entra en my.telegram.org"}, {title:"Crea la aplicación", next:"Ya la he creado — continuar"},
             {title:"Pega aquí los dos datos"}],
  email:    [{title:"Elige tu proveedor de correo"},
             {title:"Crea la contraseña de aplicación", next:"Ya la tengo — continuar"},
             {title:"Pega aquí tus datos"}],
};

// Card: credentials form (Telegram), guided for a non-technical user. Kept as the settings/muted-channels
// path does not need it; message list rows never render a connector form inline any more (V2-570 moved every
// connect flow to the wizard screen).

// Card: QR to scan, with device-linking guide.
function qrCard(platform, pd){
  const p=PLAT[platform];
  const card=el("div","linkcard");
  const ch=el("div","ch"); ch.append(badge(platform), el("b",null,"Vincular "+p.label)); card.appendChild(ch);
  const qr=(pd&&typeof pd.qr==="string"&&pd.qr.startsWith("data:image/"))?pd.qr:null;
  if(qr){
    const w=el("div","qr-wrap");
    const img=document.createElement("img"); img.alt="Código QR de "+p.label; img.src=qr; w.appendChild(img);
    if(p.qrSteps&&p.qrSteps.length){
      const cap=el("div","cap");
      p.qrSteps.forEach((t,i)=> cap.append(i%2 ? el("b",null,t) : document.createTextNode(t)));
      w.appendChild(cap);
    }
    card.appendChild(w);
  } else {
    card.appendChild(el("div","waiting","Generando el código QR de "+p.label+"…"));
  }
  return card;
}

// Settings panel: simple/complete profile + connected platforms + muted channels. Replaces the old fixed footer
// (always-visible "connected"/"unlink" chips) with something that does not distract unless the user asks for it.
function settingsPanel(platforms, data, ctx, rerender){
  const wrap = el("div","settings");

  wrap.appendChild(el("div","stitle","Perfil"));
  const seg = el("div","seg");
  [["simple","Simple"], ["completo","Completo"]].forEach(([key,label])=>{
    const b = el("button","segbtn"+(_profile===key?" active":""), label);
    b.onclick=()=>{
      if(_profile===key) return;
      _profile=key;
      try{ localStorage.setItem("hb-msg-profile", key); }catch{ /* storage blocked: only affects this session */ }
      rerender();
    };
    seg.appendChild(b);
  });
  wrap.appendChild(seg);

  // Connect/disconnect lives in the CHANNELS panel from the header button, with credential-deletion confirmation.
  // Settings only contains profile + muted channels, to avoid two different disconnection paths.

  // V2-624 — the autoresponder's state, VISIBLE: something that answers people in the operator's name while
  // he is away must never be a mode he has to remember. Configured by voice (set_autoresponder); this panel
  // shows it and offers the off switch.
  const auto = data.autoresponder || {};
  const autoOn = Object.keys(auto).filter(p=> (auto[p]||{}).enabled);
  if(autoOn.length){
    wrap.appendChild(el("div","stitle","Autorespondedor"));
    const box = el("div","conns");
    autoOn.forEach(p=>{
      const cfg = auto[p] || {};
      const chip = el("span","ok");
      const win = cfg.hours ? (" · " + cfg.hours) : "";
      chip.append(document.createTextNode("🤖 " + ((PLAT[p]||{}).label||p) + win + " — «" +
                                          String(cfg.text||"").slice(0,80) + "»"));
      const off = el("span","lk","quitar");
      off.onclick = ()=>{ off.textContent="…"; ctx.action("clear_autoresponder", {platform: p}); };
      chip.append(document.createTextNode(" · "), off);
      box.appendChild(chip);
    });
    wrap.appendChild(box);
  }

  const muted = data.muted_channels||[];
  if(muted.length){
    wrap.appendChild(el("div","stitle","Silenciados"));
    const row = el("div","conns");
    muted.forEach(m=>{
      const chip=el("span","ok"); chip.append(document.createTextNode("🔇 "+m.group));
      const lk=el("span","lk","reactivar");
      // ZAELAR-FIX (2026-07-08): previously chatId:null was sent, so unhide never reactivated anything because
      // data.py requires chat_id is not None. m.chatId comes from view_data itself and must be sent back.
      lk.onclick=()=>{ lk.textContent="…"; ctx.action("unhide", {platform:m.platform, chatId:m.chatId}); };
      chip.append(document.createTextNode(" · "), lk);
      row.appendChild(chip);
    });
    wrap.appendChild(row);
  }

  return wrap;
}

// COMPLETE profile list: original design with bordered cards and color badges.
function richList(items, ctx){
  const list=el("div","list");
  items.forEach(it=>{
    const urg = URG[it.urgencia]||URG.media;
    const mine = !!it.dirigido_a_mi;
    const row = el("div","row"+(mine?" mine":""));
    const dot = el("span","dot"); dot.style.background=urg.dot; row.appendChild(dot);

    const body = el("div","body");
    const from = el("div","from");
    from.appendChild(badge(it.platform));
    from.appendChild(el("span",null, it.from!=null?it.from:"?"));
    if(it.isGroup && it.group && it.group!==it.from) from.appendChild(el("span","grp","· "+it.group));
    if(mine) from.appendChild(el("span","tag","para ti"));
    if(urg.lb) from.appendChild(el("span","tag",urg.lb));
    body.appendChild(from);
    const media = mediaBlock(it);
    if(!(media && isBareMediaLabel(it.body))){
      const msgEl = el("div","msg"); linkify(msgEl, displayBody(it.body, it.mediaType)); body.appendChild(msgEl);
    }
    if(media) body.appendChild(media);
    if(it.motivo) body.appendChild(el("div","why", it.motivo));
    row.appendChild(body);

    const acts = el("div","acts");
    const read=el("button",null,"✓"); read.title="Marcar como leído"; read.onclick=()=>ctx.action("read",{n:it.n});
    const dis=el("button",null,"✕"); dis.title="Descartar (no marcar leído)"; dis.onclick=()=>ctx.action("dismiss",{n:it.n});
    const mute=el("button","mute","🔇"); mute.title="Silenciar este canal (no volverán a salir sus mensajes)";
    mute.onclick=()=>{ mute.textContent="…"; ctx.action("hide",{n:it.n}); };
    acts.append(read,dis,mute); row.appendChild(acts);
    list.appendChild(row);
  });
  return list;
}

// Single message row: borderless vertical timeline, used inside an open thread in simple profile.
// V2-610 — the row of ✓/✕/🗄/🗑/🔇 buttons, extracted so the flat list AND the new email detail screen
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
const _draftLocal = {};   // key -> text not yet round-tripped to the server (keystroke buffer, per screen)
let _draftTimer = null;

function _composeKey(targetPayload, activeChat){
  if(targetPayload && (targetPayload.messageId != null || targetPayload.n != null))
    return "m:" + (targetPayload.messageId != null ? targetPayload.messageId : targetPayload.n);
  if(activeChat) return "c:" + activeChat.platform + ":" + activeChat.chatId;
  return "?";
}

function _draftMatches(draft, targetPayload, activeChat){
  if(!draft || !draft.target) return false;
  const t = draft.target;
  if(targetPayload && (targetPayload.messageId != null || targetPayload.n != null))
    return (targetPayload.messageId != null && t.messageId === targetPayload.messageId) ||
           (targetPayload.n != null && t.n === targetPayload.n);
  if(activeChat) return t.platform === activeChat.platform && String(t.chatId) === String(activeChat.chatId);
  return false;
}

// `targetPayload` addresses WHAT the reply goes to: `{}` for an open THREAD (the server resolves it from
// `active_chat` itself, V2-611's `_resolve_target`), or `{n, messageId}` for a single EMAIL. `activeChat` is
// `data.active_chat`, used only to match an incoming draft against the right screen.
// V2-680 — reply-ALL is remembered per conversation, module-lived like `_draftLocal`: it is a property of
// the reply being written, not of the widget, so switching mails must not carry one mail's choice onto the
// next. It is only ever offered when the ORIGINAL actually had other recipients (see `_otherRecipients`).
const _replyAll = {};

// The other people the original went to. It comes from the connector (`mailbox.parse_message`), which is
// the only layer that can see To/Cc and knows our own address to strip. An older stored item — ingested
// before this field existed — carries nothing, and then the choice is simply not offered: a reply-all that
// silently reaches nobody extra is exactly the lie this widget must not tell.
function _otherRecipients(it){
  const r = (it && it.recipients) || [];
  return Array.isArray(r) ? r.filter(a => typeof a === "string" && a.trim()) : [];
}

function composeBar(ctx, data, targetPayload, activeChat, rerender, mailItem){
  const key = _composeKey(targetPayload, activeChat);
  const wrap = el("div","compose");

  // The draft for THIS conversation, out of the per-conversation map (V2-680). `data.draft` stays the
  // fallback: it is the most recent one, which an older engine is all that ever answers with.
  const stored = (data.drafts || {})[key];
  const matches = _draftMatches(data.draft, targetPayload, activeChat);
  const serverText = stored ? String(stored.text || "") : (matches ? String(data.draft.text || "") : "");

  const others = _otherRecipients(mailItem);
  if(others.length && !(key in _replyAll) && stored && stored.reply_all) _replyAll[key] = true;
  const replyAll = others.length ? !!_replyAll[key] : false;

  const box = document.createElement("textarea");
  box.className = "composebox";
  box.placeholder = "Escribe tu respuesta… (o dila por voz y aparecerá aquí)";
  box.rows = 5;                       // the operator's own minimum — a reply is written, not tweeted
  box.value = (key in _draftLocal) ? _draftLocal[key] : serverText;

  // Reply / reply-all, above the box. Only for a mail whose original really had other recipients.
  if(others.length){
    const top = el("div","composetop");
    const seg = el("div","seg");
    [["one","Responder"], ["all","Responder a todos"]].forEach(([id, label])=>{
      const b = el("button","segbtn"+(((id==="all")===replyAll)?" active":""), label);
      b.onclick = ()=>{ _replyAll[key] = (id === "all"); rerender(); };
      seg.appendChild(b);
    });
    top.appendChild(seg);
    // What reply-all actually ADDS, named out loud: the promise is only worth making if he can see it.
    top.appendChild(el("span","composehint", replyAll
      ? ("copia a " + others.slice(0,3).join(", ") + (others.length > 3 ? ` y ${others.length-3} más` : ""))
      : (others.length === 1 ? "1 destinatario más en el original"
                             : `${others.length} destinatarios más en el original`)));
    wrap.appendChild(top);
  }

  const main = el("div","composemain");
  const side = el("div","composeside");
  const send = el("button","bt bt-primary","Enviar ➤");
  const save = el("button","bt","Guardar borrador");
  save.title = "Guardar lo escrito sin enviarlo (también se guarda solo al dejar de escribir)";
  const syncBtn = () => { send.disabled = !box.value.trim(); };
  syncBtn();

  const payload = () => ({...targetPayload, reply_all: replyAll});
  box.addEventListener("input", () => {
    _draftLocal[key] = box.value;
    syncBtn();
    clearTimeout(_draftTimer);
    _draftTimer = setTimeout(() => { ctx.action("draft", {...payload(), text: box.value}); }, 500);
  });
  // Saving explicitly is the SAME write the autosave does, just now instead of in half a second — so the
  // two can never disagree about what is stored. It says so on screen, because a save nobody can see is
  // indistinguishable from a button that does nothing.
  save.onclick = async () => {
    clearTimeout(_draftTimer);
    _draftLocal[key] = box.value;
    await ctx.action("draft", {...payload(), text: box.value});
    save.textContent = "Guardado ✓";
    setTimeout(()=>{ try{ save.textContent = "Guardar borrador"; }catch(_){} }, 1600);
  };
  send.onclick = async () => {
    const text = box.value;
    if(!text.trim()) return;
    clearTimeout(_draftTimer);
    send.disabled = true;
    delete _draftLocal[key];
    // The box's CURRENT value is what gets sent — never a value cached from an earlier keystroke or from
    // voice dictation alone: an edit made by hand after dictating is the operator's real final word.
    await ctx.action("draft", {...payload(), text});
    // The send NAMES its conversation (V2-680): with a draft per conversation, a bare send_draft would
    // reach for the most recently TOUCHED one, which is not necessarily the screen this button is on.
    await ctx.action("send_draft", {...targetPayload});
    rerender();
  };
  side.append(send, save);
  main.append(box, side);
  wrap.appendChild(main);
  return wrap;
}

function messageActions(it, ctx){
  const acts = el("div","tacts");
  const read=el("button",null,"✓"); read.title="Marcar como leído"; read.onclick=()=>ctx.action("read",{n:it.n});
  const dis=el("button",null,"✕"); dis.title="Descartar (no marcar leído)"; dis.onclick=()=>ctx.action("dismiss",{n:it.n});
  acts.append(read,dis);
  if(it.platform==="email"){
    // Email-only affordances (V2-543): they act on the REAL mailbox, which is the whole point of the widget
    // being a substitute — other platforms have no archive/delete API and get no fake buttons.
    const arc=el("button",null,"🗄"); arc.title="Archivar en tu buzón real";
    arc.onclick=()=>{ arc.textContent="…"; ctx.action("archive",{n:it.n}); };
    const del=el("button",null,"🗑"); del.title="Borrar en tu buzón real (pide confirmación)";
    del.onclick=()=>ctx.action("trash",{n:it.n});
    acts.append(arc,del);
  }
  const mute=el("button",null,"🔇"); mute.title="Silenciar este canal";
  mute.onclick=()=>{ mute.textContent="…"; ctx.action("hide",{n:it.n}); };
  acts.append(mute);
  return acts;
}

// V2-616 — a bubble timeline, not a repeated-name log. His report: in a 1:1 chat the sender's name on
// EVERY line is noise (the header above the list already names who this is), and his OWN replies need to
// stand apart from theirs at a glance — the classic left/right convention, not an indented quieter copy of
// the same row shape. `isGroup` is the ONLY thing that still earns a per-bubble name: a group has no single
// "who this is" to put in the header, so each inbound bubble still has to say which member sent it.
function messageRow(it, ctx, rerender, isGroup){
  const urgente = it.urgencia === "alta";
  const key = String(it.messageId != null ? it.messageId : it.n);
  // V2-546 — «out» is what the OPERATOR wrote, here or in his own app; it is context, never something to act
  // on. And a row with no `n` is history: it is no longer in the inbox, so there is nothing left to mark read
  // or dismiss and offering the buttons would be a lie about what pressing them does.
  const outgoing = it.dir === "out";
  const actionable = !outgoing && it.n != null;

  const row = el("div","tbrow"+(outgoing?" out":""));
  const stack = el("div","tbstack");
  const bubble = el("div","tbubble"+(urgente && !outgoing?" urg":""));
  if(isGroup && !outgoing) bubble.appendChild(el("div","tbfrom", it.from!=null?it.from:"?"));

  const media = mediaBlock(it);
  const bareLabel = media && isBareMediaLabel(it.body);
  const {title, rest} = splitBody(displayBody(it.body, it.mediaType));
  const isLong = rest.length > 220 || rest.split("\n").length > 4;
  const expanded = _expanded.has(key);
  if(!bareLabel){
    if(title) bubble.appendChild(el("div","tbtitle", title));
    const bodyEl = el("div","tbbody"+(isLong && !expanded ? " clamp" : ""));
    linkify(bodyEl, rest);
    bubble.appendChild(bodyEl);
  }
  if(media) bubble.appendChild(media);

  if(isLong){
    const more = el("span","more", expanded ? "mostrar menos" : "mostrar más");
    more.onclick=()=>{ expanded ? _expanded.delete(key) : _expanded.add(key); rerender(); };
    bubble.appendChild(more);
  }
  const when = fmtWhen(it.ts);
  if(when) bubble.appendChild(el("span","tbwhen", when));
  stack.appendChild(bubble);

  if(actionable) stack.appendChild(messageActions(it, ctx));
  row.appendChild(stack);
  return row;
}

// ── EMAIL default view (V2-610) ─────────────────────────────────────────────────────────────────────────
// Operator's spec, verbatim in spirit: «un formato que se vea parecido a Gmail — la fecha y hora y el
// asunto, y si cabe quién lo envía, en dos líneas; si pido abrir el asunto pasa a una segunda pantalla con
// el detalle». A classic mail client's list shows subject/sender/time and NOTHING of the body; the body is
// what the second screen is for. `messageRow`'s inline clamp+«mostrar más» is the wrong shape for that —
// it is what threads (WhatsApp/Telegram) already use and stays theirs.
//
// This is the hardcoded DEFAULT, not a setting: the operator asked for it four times by voice in one
// session and the widget kept re-rendering the SAME expanded shape because no action existed to change it
// (`show_view` only ever moved the LENS, never the density) — the fix is to make the classic shape the one
// that ships, not to add a toggle nobody would find. His own words close the door on a toggle: «si un día
// el usuario decide hacer un fork del widget y cambiarlo, que lo haga».
function emailRow(it, ctx, openMail){
  const urgente = it.urgencia === "alta";
  const row = el("div","mrow");
  row.title = "Abrir";
  const lead = el("span","tlead");
  lead.style.background = urgente ? "var(--hb-risk,#e5484d)" : "var(--hb-accent,#3D6FE0)";
  row.appendChild(lead);

  const main = el("div","mmain");
  const line1 = el("div","mline1");
  line1.appendChild(el("span","mfrom", it.from!=null ? it.from : "?"));
  const when = fmtWhen(it.ts);
  if(when) line1.appendChild(el("span","mwhen", when));
  main.appendChild(line1);
  // `subject` is a first-class field on the item (mailbox.py/service.py) — reading it directly is more
  // reliable than parsing it back out of `body`, which only carries "[Asunto: X]\n…" on a LIVE arrival and
  // nothing at all on history (V2-546's `load_more` already folds subject into body there for that reason).
  const subj = (it.subject || "").trim() || displayBody(it.body, it.mediaType).split("\n")[0] || "(sin asunto)";
  main.appendChild(el("div","msubj", subj));
  row.appendChild(main);

  row.onclick=()=>{ ctx.top(); openMail(mailKey(it)); };
  return row;
}

// `n` is POSITIONAL and gets REUSED the moment an earlier item leaves the list (`_renumber` in data.py
// reassigns 1..len by order on every save) — `_openMail` holding a bare `n` across a repaint would resolve
// to whatever mail inherited that number next, and silently show the WRONG one instead of falling back to
// the list. `messageId` is the STABLE identity every item already carries for exactly this reason (`_key()`
// in data.py, and the same fallback `_expanded`'s own key already uses a few lines above).
function mailKey(it){ return it.messageId != null ? it.messageId : it.n; }

function emailList(items, ctx, openMail){
  const wrap = el("div","tl");
  items.forEach(it=> wrap.appendChild(emailRow(it, ctx, openMail)));
  return wrap;
}

// The SECOND screen (V2-610): full subject, sender, timestamp and body — everything the compact row leaves
// out. Reuses `messageActions` so read/dismiss/archive/trash/mute stay the SAME five buttons the row itself
// used to carry, wired to the same `n` (unambiguous: read/dismiss/archive/trash/hide all resolve by the
// item's own `n` against the flat renumbered list, never against a chat grouping — see data.py).
function mailDetail(it, data, ctx, closeMail, rerender){
  const wrap = el("div","thread plat-email");
  const hd = el("div","thd");
  const back = el("button","back","← Bandeja"); back.onclick=()=>{ ctx.top(); closeMail(); };
  hd.appendChild(back);
  wrap.appendChild(hd);

  const card = el("div","mdet");
  card.appendChild(el("div","mdsubj", (it.subject || "").trim() || "(sin asunto)"));
  const meta = el("div","mdmeta");
  meta.appendChild(el("span","mdfrom", it.from!=null ? it.from : "?"));
  const when = fmtWhen(it.ts);
  if(when) meta.appendChild(el("span","mdwhen", when));
  card.appendChild(meta);

  const media = mediaBlock(it);
  if(!(media && isBareMediaLabel(it.body))){
    const {title, rest} = splitBody(displayBody(it.body, it.mediaType));
    const bodyEl = el("div","mdbody");
    linkify(bodyEl, title ? (rest || title) : rest);
    card.appendChild(bodyEl);
  }
  if(media) card.appendChild(media);
  wrap.appendChild(card);

  if(!(it.dir === "out") && it.n != null) wrap.appendChild(messageActions(it, ctx));
  // V2-611 — reply to THIS mail specifically: `n`+`messageId` address it unambiguously, the same identity
  // read/dismiss/archive/trash already use (never the chat-grouping numbering, which the flat email list
  // does not have). Outgoing mail (his own, echoed into the thread) has nothing to reply TO.
  if(it.dir !== "out") wrap.appendChild(composeBar(ctx, data, {n: it.n, messageId: it.messageId}, null, rerender, it));
  return wrap;
}

// CHAT list (simple profile, default): one item per conversation instead of per message. Shows name, pending
// count, and the last message as preview. Click, or [[msg.open:N]] by voice, enters the full thread.
// ── ACTIVITY view (V2-624) ──────────────────────────────────────────────────
// A lens whose platform carries a view CRITERION («conversaciones con actividad en las últimas 72 h») lists
// CONVERSATIONS from the thread store — movement includes what he already read and what he himself sent —
// instead of the pending inbox. The criterion is per-platform STATE the operator set, so it is VISIBLE (a bar
// with a ✕), never a silent mode; without one, the lens stays byte-for-byte the classic pending view.
function fmtWindow(h){
  const n = Number(h||0);
  if(n <= 48) return "últimas " + Math.round(n) + " h";
  return "últimos " + Math.round(n/24) + " días";
}

function criteriaBar(platform, crit, ctx, rerender){
  const bar = el("div","critbar");
  bar.appendChild(el("span","critlbl","Actividad · " + fmtWindow(crit.window_h)));
  if(platform === "telegram" || platform === "email"){
    const fetchBtn = el("button","bt bt-ghost critfetch","⟳ Traer del conector");
    fetchBtn.title = "Pedirle al conector las conversaciones con actividad en ese período";
    fetchBtn.onclick = ()=>{ fetchBtn.textContent = "⟳ Pedido…"; fetchBtn.disabled = true;
      ctx.action("fetch_now", {platform: platform, since_hours: crit.window_h}); };
    bar.appendChild(fetchBtn);
  }
  const off = el("button","critoff","✕");
  off.title = "Quitar el criterio (volver a la vista de pendientes)";
  off.onclick = ()=> ctx.action("show_view", {platform: platform, window_h: 0});
  bar.appendChild(off);
  return bar;
}

function activityList(rows, ctx){
  const wrap = el("div","tl");
  rows.forEach(c=>{
    const row = el("div","trow chatrow");
    row.title = "Abrir conversación";
    const lead = el("span","tlead");
    lead.style.background = c.unread ? "var(--hb-accent,#3D6FE0)" : "transparent";
    row.appendChild(lead);
    const main = el("div","tmain");
    const head = el("div","thead");
    head.appendChild(platformChip(c.platform));
    head.appendChild(el("span","tfrom", c.name));
    if(c.unread) head.appendChild(el("span","tcount", String(c.unread)));
    if(c.isGroup) head.appendChild(el("span","tpara","· grupo"));
    const when = fmtWhen(c.lastTs);
    if(when) head.appendChild(el("span","twhen", when));
    main.appendChild(head);
    const who = c.lastFrom ? c.lastFrom + ": " : "";
    main.appendChild(el("div","tprev", who + displayBody(c.lastBody, c.lastMediaType)));
    row.appendChild(main);
    row.onclick = ()=> { ctx.top(); ctx.action("open", {platform: c.platform, chatId: c.chatId}); };
    wrap.appendChild(row);
  });
  return wrap;
}

function chatList(chats, ctx){
  const wrap = el("div","tl");
  chats.forEach(c=>{
    const row = el("div","trow chatrow");
    row.title = "Abrir conversación";
    const lead = el("span","tlead");
    lead.style.background = c.urgencia === "alta" ? "var(--hb-risk,#e5484d)"
      : (c.dirigido_a_mi ? "var(--hb-accent,#3D6FE0)" : "transparent");
    row.appendChild(lead);

    const main = el("div","tmain");
    const head = el("div","thead");
    head.appendChild(platformChip(c.platform));
    head.appendChild(el("span","tfrom", c.name));
    if(c.count > 1) head.appendChild(el("span","tcount", String(c.count)));
    if(c.dirigido_a_mi) head.appendChild(el("span","tpara","· para ti"));
    const when = fmtWhen(c.lastTs);
    if(when) head.appendChild(el("span","twhen", when));
    main.appendChild(head);

    const {title, rest} = splitBody(displayBody(c.lastBody, c.lastMediaType));
    main.appendChild(el("div","tprev", title ? (title+" — "+rest) : rest));
    row.appendChild(main);
    // V2-616 F2 — opening a thread swaps the whole screen (a chat list row for the thread's own header +
    // messages), so the outer card scroller has to go back to the top. Without this, a chat list left
    // scrolled down handed the fresh thread a stale scrollTop: its own header rendered scrolled PAST the
    // visible area on first paint, reported live as "se ha metido como por debajo el header del otro" — his
    // own scroll gesture only fixed it by accident, forcing the browser to reflow.
    row.onclick = ()=> { ctx.top(); ctx.action("open", {n:c.n}); };

    const acts = el("div","tacts");
    const read=el("button",null,"✓"); read.title="Marcar todo el chat como leído";
    read.onclick=(ev)=>{ ev.stopPropagation(); ctx.action("readchat",{n:c.n}); };
    const mute=el("button",null,"🔇"); mute.title="Silenciar este canal";
    mute.onclick=(ev)=>{ ev.stopPropagation(); mute.textContent="…"; ctx.action("hide",{n:c.n}); };
    acts.append(read,mute);
    row.appendChild(acts);

    wrap.appendChild(row);
  });
  return wrap;
}

// Open thread: header (back + platform + name) and its messages one by one. `close` returns to the chat list,
// is also addressable by voice ([[msg.close]]), and converges on the same ctx.action.
// V2-546 — the boundary of what we hold. Our copy of a conversation starts somewhere, and saying where is the
// difference between a scrollback and a lie: without this line the oldest message we have LOOKS like the start
// of the conversation. Offers to go further only where the platform can actually serve it.
function threadStart(meta, ctx){
  const box = el("div","tstart");
  if(meta && meta.complete){
    box.appendChild(el("span","tsl","· principio de la conversación ·"));
    return box;
  }
  box.appendChild(el("span","tsl","· aquí empieza lo que tengo guardado ·"));
  if(meta && meta.can_load_more){
    const b = el("button","tsbtn","Cargar anteriores");
    b.onclick=()=>{ b.disabled=true; b.textContent="Pidiéndolos…"; ctx.action("load_more",{}); };
    box.appendChild(b);
  }
  return box;
}

function threadView(active, items, data, ctx, rerender, meta){
  const wrap = el("div","thread"+(" plat-"+active.platform));
  const hd = el("div","thd");
  hd.appendChild(platformChip(active.platform));
  // The chat's name comes from an INBOUND message: with outbound ones in the thread (V2-546) the first row can
  // be the operator's own, and naming the conversation after himself is how a thread stops being recognisable.
  const inbound = items.filter(it=> it.dir !== "out");
  const name = (inbound.find(it=>it.group)||{}).group || (inbound.find(it=>it.from)||{}).from
    || (PLAT[active.platform]||{}).label || "Chat";
  hd.appendChild(el("b","thdname", name));
  // V2-616 F2/F3 — the operator: the name goes on the LEFT, "volver" moves to the far RIGHT as a real
  // button, never a bare underlined link (`margin-left:auto` on the LAST child, same pattern the connectors
  // list already used). And it resets the outer scroller (ctx.top()) — this IS a screen change (thread ->
  // chat list), and skipping it is the same stale-scrollTop bug the "open" click just below it fixes.
  const back = el("button","back","← Volver");
  back.onclick=()=>{ ctx.top(); ctx.action("close"); };
  hd.appendChild(back);
  wrap.appendChild(hd);

  wrap.appendChild(threadStart(meta, ctx));
  const isGroup = !!(meta && meta.isGroup);
  const list = el("div","tl");
  items.forEach(it=> list.appendChild(messageRow(it, ctx, rerender, isGroup)));
  wrap.appendChild(list);
  // V2-611 — reply to the CONVERSATION, not a specific past message: `{}` lets the server resolve the
  // target from `active_chat` itself (`_resolve_target`), which is what «responderle» means for a thread.
  wrap.appendChild(composeBar(ctx, data, {}, active, rerender));
  return wrap;
}

// Loader + human-readable connection state.
const _ST_LABEL = {off:"Sin conectar", no_creds:"Sin conectar", starting:"Conectando…",
                   connecting:"Esperando escaneo del QR…", connected:"Conectado", error:"No se pudo conectar"};

function statusLabel(pd){ return _ST_LABEL[(pd&&pd.status)||"off"] || (pd&&pd.status) || ""; }

function spinner(){ const s=document.createElement("span"); s.className="spin"; return s; }

function waitBox(label, detail){
  const w=el("div","waitbox");
  const l=el("div","lbl"); l.append(spinner(), document.createTextNode(label||"Conectando…")); w.appendChild(l);
  if(detail) w.appendChild(el("div","det", detail));
  return w;
}

function errorCard(pl, detail, ctx, rerender){
  const c=el("div","errcard");
  const t=el("div","et"); t.append(el("b",null,"No se pudo conectar. "), document.createTextNode(detail||"Revisa los datos e inténtalo otra vez.")); c.appendChild(t);
  const b=el("button","bt bt-ghost","Corregir y reintentar");
  // V2-559/V2-570: the wizard screen is already showing the LAST step (that is where a submit happens from),
  // so there is nothing to "expand" any more — retry only needs to clear the busy flag and put the cursor
  // back on the field to fix.
  b.onclick=()=>{ _busy[pl]=false; _focusField[pl]="pw"; rerender(); };
  c.appendChild(b);
  return c;
}

// ── LIST screen: every connector as an icon box (V2-570) ────────────────────────────────────────────────
function renderListScreen(platforms, ctx, rerender, connectedCount){
  const wrap=el("div");
  const head=el("div","chanhead");
  head.appendChild(el("b",null, connectedCount ? "Conectores" : "Canales disponibles"));
  head.appendChild(el("span","hint", connectedCount ? "" : "Conecta un canal para empezar — por voz o con un toque."));
  if(connectedCount){
    const back=el("span","back","← Mensajes");
    back.onclick=()=>{ _screen=null; ctx.top(); rerender(); };
    head.appendChild(back);
  }
  wrap.appendChild(head);

  wrap.appendChild(iconGrid(ORDER.filter(pl=>PLAT[pl]).map(pl=>{
    const p=PLAT[pl];
    const pd=platforms[pl]||{status:"off"};
    const st=pd.status||"off";
    const connected = st==="connected";
    // A stale failure from a past session is not this list's news: without an attempt in this page
    // session, an errored platform simply reads as not connected (the wizard opens clean too).
    const sub = (st==="error" && !_attempted[pl]) ? _ST_LABEL.off : statusLabel(pd);
    return {
      key:pl, icon:brandIcon(pl, connected), label:p.label, sub, cls:(connected?"conn":""),
      onClick:()=>{ _screen={view:"wizard", platform:pl}; if(!_wizStep[pl]) _wizStep[pl]=1; rerender(); },
    };
  })));
  return wrap;
}

// ── WIZARD screen: a single connector, one step at a time (V2-570) ──────────────────────────────────────
function renderWizardScreen(platform, platforms, ctx, rerender){
  const wrap=el("div");
  const p=PLAT[platform];
  const pd=platforms[platform]||{status:"off"};
  const st=pd.status||"off";
  // The engine answered: any state past the local "connecting" clears busy — INCLUDING "error" (a refusal
  // ENDS the attempt; leaving busy up kept the primary button disabled on «Conectando…» while the banner
  // asked the operator to retry, seen rendering V2-582's screens).
  if(st!=="off"&&st!=="no_creds") _busy[platform]=false;

  const crumb=el("div","crumb");
  const back=el("span","back","‹ Conectores");
  back.onclick=()=>{ _screen={view:"list"}; ctx.top(); rerender(); };
  crumb.append(back, el("span","sep","/"), el("span","cur", p.label));
  wrap.appendChild(crumb);

  // CONNECTED: a status screen, not a wizard. The draft is NOT cleared on entry into this screen — only once
  // the platform actually reports connected, so a refused connection never loses what the user typed.
  if(st==="connected"){
    _focusField[platform]=null;
    _attempted[platform]=false;
    if(platform==="email") _draft.email={email_address:"", email_password:"", provider:_draft.email.provider, imap_host:"", smtp_host:""};
    if(platform==="telegram") _draft.telegram={api_id:"", api_hash:""};
    const card=el("div","linkcard");
    const ch=el("div","ch"); ch.append(brandIcon(platform,true), el("b",null,p.label)); card.appendChild(ch);
    card.appendChild(el("div","wbody","Conectado. Tus mensajes llegan aquí automáticamente."));
    if(_confirmDisconnect===platform){
      const cfm=el("div","cfm");
      cfm.appendChild(document.createTextNode(`¿Eliminar las credenciales de ${p.label}? Tendrás que volver a conectarlo.`));
      const row=el("div","row");
      const y=el("button","bt bt-danger","Sí, desconectar");
      y.onclick=()=>{ _confirmDisconnect=null; _busy[platform]=false; _attempted[platform]=false;
                      ctx.action("disconnect",{platform, forget:true}); };
      const n=el("button","bt bt-ghost","Cancelar"); n.onclick=()=>{ _confirmDisconnect=null; rerender(); };
      row.append(y,n); cfm.appendChild(row); card.appendChild(cfm);
    } else {
      const d=el("button","bt bt-ghost","Desconectar");
      d.onclick=()=>{ _confirmDisconnect=platform; rerender(); };
      card.appendChild(d);
    }
    wrap.appendChild(card);
    return wrap;
  }

  // Live states pre-empt the step form entirely — there is nothing to fill in while these are showing.
  if(_busy[platform] && (st==="off"||st==="no_creds")){
    wrap.appendChild(waitBox("Conectando…", "Un momento, contactando con el servicio…"));
    return wrap;
  }
  if(st==="starting"){ wrap.appendChild(waitBox("Conectando…", pd.detail||"")); return wrap; }
  if(st==="connecting"){ wrap.appendChild(qrCard(platform, pd)); return wrap; }
  // The banner only accompanies an attempt made in THIS page session (operator's rule): a stored "error"
  // from another day opens as a clean wizard — the failure already expired with its attempt.
  if(st==="error" && _attempted[platform]){ wrap.appendChild(errorCard(platform, pd.detail, ctx, rerender)); }

  const steps = WIZARD_STEPS[platform] || [{title:"Conectar "+p.label}];
  const total = steps.length;
  let step = Math.min(Math.max(_wizStep[platform]||1, 1), total);
  _wizStep[platform] = step;

  const refs = {};
  const box = stepBox(step, steps[step-1].title, false);
  // «Paso N de 3» lives IN the header row, right-aligned: under the title it read as body text and pushed
  // the real content down; next to it, it is the wayfinding it was meant to be.
  if(total>1) box.querySelector(".whead").appendChild(el("span","wcount", `Paso ${step} de ${total}`));

  let content;
  if(platform==="email"){
    const d=_draft.email;
    content = step===1 ? emailStep1Body(d, rerender) : step===2 ? emailStep2Body(d) : emailStep3Body(d, refs);
  } else if(platform==="telegram"){
    content = step===1 ? telegramStep1Body() : step===2 ? telegramStep2Body() : telegramStep3Body(refs);
  } else {
    content = whatsappStepBody(platform);
  }
  box.appendChild(content);
  wrap.appendChild(box);

  const err = el("div","err"); err.style.display="none";
  const fail=(msg, field)=>{ err.textContent=msg; err.style.display="block";
    if(field){ field.classList.add("errfield"); try{ field.focus(); }catch{ /* detached */ } } };

  // Coming back from a failure: land ON the field to fix (only ever set on the LAST step, where submission
  // happens), not at the top of the screen.
  if(_focusField[platform]){
    const target = refs[_focusField[platform]];
    _focusField[platform]=null;
    if(target){ setTimeout(()=>{ try{ target.focus(); target.scrollIntoView({block:"center"}); }catch{ /* detached */ } }, 0); }
  }

  const foot = el("div","wfoot");
  const backBtn = el("button","bt bt-ghost", "Atrás");
  backBtn.onclick=()=>{
    ctx.top();
    if(step>1){ _wizStep[platform]=step-1; rerender(); }
    else { _screen={view:"list"}; rerender(); }
  };
  foot.appendChild(backBtn);

  const isLast = step===total;
  // A step whose work happens OUTSIDE (create the password at the provider) labels its own advance
  // («Ya la tengo — continuar»): a bare "Continuar" reads as skippable, and skipping it is the incident.
  const nextBtn = el("button","bt bt-primary", isLast ? (_busy[platform]?"Conectando…":"Conectar "+p.label)
                                                      : (steps[step-1].next || "Continuar"));
  nextBtn.disabled = isLast && !!_busy[platform];
  nextBtn.onclick=()=>{
    if(!isLast){ _wizStep[platform]=step+1; ctx.top(); rerender(); return; }
    if(platform==="email"){
      const d=_draft.email;
      const email_address=(refs.addr.value||"").trim();
      const email_password=(refs.pw.value||"").replace(/\s+/g,"");
      if(!/.+@.+\..+/.test(email_address)) return fail("Necesito tu dirección de correo completa.", refs.addr);
      if(!email_password) return fail("Falta la contraseña de aplicación del paso 2.", refs.pw);
      const payload={platform, email_address, email_password, provider:d.provider};
      if(d.provider==="otro"){
        if(!refs.imap.value.trim()) return fail("Para «Otro» necesito el servidor IMAP.", refs.imap);
        if(!refs.smtp.value.trim()) return fail("Para «Otro» necesito el servidor SMTP.", refs.smtp);
        payload.imap_host=refs.imap.value.trim(); payload.smtp_host=refs.smtp.value.trim();
      }
      _busy[platform]=true; _attempted[platform]=true; ctx.action("connect", payload); rerender();
      // The draft is NOT cleared here (V2-559/V2-570): a refused connection comes back to this same step, and
      // wiping it meant retyping the address and the 16 letters from scratch. It is cleared once CONNECTED.
    } else if(platform==="telegram"){
      const api_id=(refs.id.value||"").trim(), api_hash=(refs.hash.value||"").trim();
      if(!/^\d+$/.test(api_id) || !api_hash){ fail("Necesito el api_id (solo números) y el api_hash."); return; }
      _busy[platform]=true; _attempted[platform]=true; ctx.action("connect", {platform, api_id, api_hash}); rerender();
    } else {
      _busy[platform]=true; _attempted[platform]=true; ctx.action("connect", {platform}); rerender();
    }
  };
  foot.appendChild(nextBtn);

  wrap.appendChild(err);
  wrap.appendChild(foot);
  return wrap;
}

export function render(root, data, ctx){
  injectStyles();
  root.className="hb-msg";
  root.textContent="";

  const platforms=data.platforms||{};
  const items=data.items||[];
  const rerender=()=>render(root, data, ctx);
  const connectedCount = ORDER.filter(pl=>(platforms[pl]||{}).status==="connected").length;

  // A pushed VIEW (V2-543) applies only when its witness counter moves: «vuelve a la lista principal» /
  // «solo el WhatsApp» land even when repeated, and a plain repaint never yanks the operator's own choice.
  // V2-626 — it goes through the SAME door as a click, so the body follows the header by itself; and it is
  // resolved BEFORE `connect_focus` on purpose, so that when one payload carries both, the more specific
  // request (open THIS connector's wizard) is the one left standing.
  const pushed = data.view || null;
  if(pushed && Number(pushed.n||0) > 0 && Number(pushed.n) !== _viewN){
    _viewN = Number(pushed.n);
    selectPlatform(pushed.platform);
  }

  // The brain was asked to connect a channel (V2-520, redesigned V2-570): jump straight into that
  // connector's OWN screen — never the list — so "connect my email" lands on the Gmail/Outlook/… wizard
  // directly instead of a panel the operator still has to click through. Honoured once per request.
  const focus = data.connect_focus || null;
  if(focus && Number(focus.ts||0) > _focusDone){
    _focusDone = Number(focus.ts||0);
    if(focus.platform && PLAT[focus.platform]){
      _screen = {view:"wizard", platform:focus.platform};
      if(!_wizStep[focus.platform]) _wizStep[focus.platform]=1;
    } else {
      _screen = {view:"list"};
    }
  }

  // V2-622 — an open thread/mail already carries its OWN header (platform + contact/subject + "← Volver");
  // the dashboard header below (inbox count, every platform dot, connectors/settings/clear) stacked ABOVE
  // that is not a second control surface, it is dead weight — on a hard refresh, with nothing to scroll past
  // to hide it, it read as two headers glued together (operator screenshot, 2026-09-08). Checked here, before
  // the dashboard header is even built, so it never gets appended for these two screens.
  const showChannels = !!_screen || connectedCount===0;
  const fItems = _platFilter ? items.filter(it=>it.platform===_platFilter) : items.filter(it=>it.highlight);
  const activeChat = !showChannels ? (data.active_chat || null) : null;
  if(activeChat){
    // V2-680 — a reading screen owns the card: header fixed, messages scrolling in the middle, reply box
    // pinned at the bottom. See the `.full` block in the stylesheet for why only these two screens opt in.
    root.classList.add("full");
    root.appendChild(threadView(activeChat, data.active_items||[], data, ctx, rerender, data.thread_meta||null));
    return;
  }
  const openMailItem = (!showChannels && _platFilter==="email" && _openMail!=null)
    ? (fItems.find(x=>mailKey(x)===_openMail) || items.find(x=>mailKey(x)===_openMail))
    : null;
  if(openMailItem){
    root.classList.add("full");
    root.appendChild(mailDetail(openMailItem, data, ctx, ()=>{ _openMail=null; rerender(); }, rerender));
    return;
  }

  // Header: title + counter, connected icons only, connectors, settings, clear.
  const hd=el("div","hd");
  // V2-616 — this title used to repeat the CATALOG name ("Mensajería"), which the outer card chrome
  // already says (V2-082's header). What this line actually names is the SCREEN underneath it — the
  // unified inbox — so it reads "Mensajes" now, the operator's own suggestion. The click behavior is
  // unchanged: from V2-610, the way BACK to the dashboard, always, from any screen (a platform lens, a
  // wizard, the connectors list, an open thread or mail).
  const title=el("b","hdtitle","Mensajes"); title.title="Ver la bandeja unificada de todos tus canales";
  title.onclick=()=>{ selectPlatform(null); ctx.top(); ctx.action("show_view",{platform:"all"}); rerender(); };
  hd.append(title,
            el("span","sub", items.length ? `${items.length} para ti` : (connectedCount ? "al día" : "sin conectar")));
  const dots=el("div","dots");
  // V2-521: every channel is VISIBLE up here — connected bright, unconnected dimmed (the operator's ask:
  // seeing the catalogue at a glance). A bright icon toggles that platform's lens; a dimmed one opens that
  // connector's own wizard screen — the same door the voice takes (V2-570).
  ORDER.forEach(pl=>{
    const on=(platforms[pl]||{}).status==="connected";
    const ic=brandIcon(pl, on);
    ic.style.cursor="pointer";
    if(on){
      ic.title=(PLAT[pl]||{}).label+(_platFilter===pl?": quitar filtro":": ver solo este canal");
      if(_platFilter===pl) ic.classList.add("filt");
      // Same door as the voice (V2-543): apply locally for an instant repaint AND stamp the server view, so
      // the next voice order and the next SSE repaint agree with what the click just did.
      // V2-610 — a click here is a NAVIGATION order («llévame a WhatsApp»), and a navigation order must
      // leave wherever it was, not just change what the list underneath would show. Before this, clicking
      // a platform icon while the Conectores screen was open changed `_platFilter` and called `show_view`
      // but never cleared `_screen`, so `showChannels` stayed true and the click was invisible — the
      // operator kept seeing Conectores no matter which platform he tapped (reported live 2026-09-07).
      ic.onclick=()=>{ const next=(_platFilter===pl ? "all" : pl); selectPlatform(_platFilter===pl ? null : pl);
        ctx.top(); ctx.action("show_view",{platform:next}); rerender(); };
    } else {
      ic.title=(PLAT[pl]||{}).label+": sin conectar — toca para conectarlo";
      ic.onclick=()=>{ _screen={view:"wizard", platform:pl}; if(!_wizStep[pl]) _wizStep[pl]=1; ctx.top(); rerender(); };
    }
    dots.appendChild(ic);
  });
  hd.appendChild(dots);
  // V2-616 — the operator: the platform icons and the settings/connectors icons "no pueden estar al mismo
  // nivel ni pegados a lo que son secciones o diferentes plataformas". `.hdactions` is a second cluster with
  // its own divider, so it reads as a DIFFERENT kind of control from the row of channel icons beside it.
  const actions=el("div","hdactions");
  const connBtn=el("button","connbtn"+(_screen?" active":""),"🔌"); connBtn.title="Canales / conectores";
  connBtn.onclick=()=>{ _screen = _screen ? null : {view:"list"}; if(!_screen) _confirmDisconnect=null; ctx.top(); rerender(); };
  actions.appendChild(connBtn);
  const gear=el("button","gear"+(_settingsOpen?" active":""),"⚙"); gear.title="Ajustes";
  gear.onclick=()=>{ _settingsOpen=!_settingsOpen; rerender(); };
  actions.appendChild(gear);
  if(items.length && !_screen){
    const clr=el("button","clr","Limpiar"); clr.title="Marcar todo como leído";
    clr.onclick=()=>ctx.action("clear"); actions.appendChild(clr);
  }
  hd.appendChild(actions);
  root.appendChild(hd);

  if(_settingsOpen) root.appendChild(settingsPanel(platforms, data, ctx, rerender));

  // CHANNELS area: onboarding when nothing is connected, or when the user opens it from the header connector
  // button, or when the brain pushed a `connect_focus`. Messaging starts EMPTY; do not dump every connection
  // form by default (V2-051 product decision, unchanged).
  if(showChannels){
    const scr = _screen || {view:"list"};
    if(scr.view==="wizard" && scr.platform && PLAT[scr.platform]){
      root.appendChild(renderWizardScreen(scr.platform, platforms, ctx, rerender));
    } else {
      root.appendChild(renderListScreen(platforms, ctx, rerender, connectedCount));
    }
    return;
  }

  // MESSAGES view, reached whenever at least one channel is connected (an open thread/mail already
  // returned above, before the dashboard header — see V2-622 near the top of this function). The lens
  // (V2-521) narrows every shape below to one platform.
  // V2-607 — TWO SHAPES, on purpose. With a lens on, this is that channel's own section: EVERYTHING unread it
  // has brought, nothing filtered. With no lens, this is the summary, and it shows only what meets the criterion
  // he set (`highlight`, default = addressed to him) — the rest is not gone, it is one tap away in its channel.
  const hidden = _platFilter ? 0 : items.length - fItems.length;
  const emptyMsg = _platFilter
    ? "Nada de "+((PLAT[_platFilter]||{}).label||_platFilter)+" que atender ✓"
    : (hidden ? "Nada dirigido a ti ✓" : "Nada que atender ahora ✓");
  // V2-624 — the ACTIVITY view wins the lens when its platform has a criterion set: it is a different
  // question («qué se ha movido») than the pending inbox («qué me espera»), and the operator set it
  // explicitly. Applies in BOTH profiles — it is a lens-level view, not a density preference.
  const crit = _platFilter ? (data.lens_criteria || {})[_platFilter] : null;
  if(crit){
    root.appendChild(criteriaBar(_platFilter, crit, ctx, rerender));
    const rows = (data.activity_chats || []).filter(r=> r.platform === _platFilter);
    if(rows.length) root.appendChild(activityList(rows, ctx));
    else root.appendChild(el("div","empty",
      "Sin conversaciones guardadas con actividad en ese período" +
      ((_platFilter === "telegram" || _platFilter === "email")
        ? " — «Traer del conector» las pide de verdad" : "")));
    return;
  }
  if(_profile==="completo"){
    if(fItems.length) root.appendChild(richList(fItems, ctx));
    else root.appendChild(el("div","empty",emptyMsg));
    if(hidden) root.appendChild(restNote(hidden));
    return;
  }
  if(_platFilter==="email"){
    // Email's NATURAL shape (the operator's spec, V2-610): a Gmail-style list — sender, subject, time, NO
    // body — and opening one moves to `mailDetail`, a second screen, never an inline expand. This is the
    // shape that SHIPS; a settings toggle for it was deliberately not built (the operator's own words: if
    // someone wants the old inline-expand shape, fork the widget).
    root.appendChild(fItems.length ? emailList(fItems, ctx, n=>{ _openMail=n; rerender(); })
                                    : el("div","empty",emptyMsg));
    return;
  }

  const chats = (data.chats || []).filter(c=> _platFilter ? c.platform===_platFilter : c.highlight);
  if(chats.length) root.appendChild(chatList(chats, ctx));
  else root.appendChild(el("div","empty",emptyMsg));
  if(hidden) root.appendChild(restNote(hidden));
}

// What the summary is NOT showing, said out loud. A filtered list that looks identical to an empty one is how
// the operator ends up believing a connector is broken — the failure V2-606 came from (V2-607).
function restNote(n){
  const d = el("div","rest");
  d.textContent = n===1 ? "1 mensaje más en sus canales" : n+" mensajes más en sus canales";
  return d;
}
