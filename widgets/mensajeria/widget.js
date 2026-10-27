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
const PLAT = {
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

// LOCAL presentation state (cosmetic, does not touch the store): selected profile, settings panel open, expanded
// messages. Survives re-renders because the module loads once.
let _profile = "simple";
try { _profile = localStorage.getItem("hb-msg-profile") || "simple"; } catch { /* storage blocked: use "simple" */ }
let _settingsOpen = false;
// V2-521 — the visual formula: ONE inbox by default ("everything, no filters" is the deliberate start),
// and a per-platform lens on demand. null = todo. V2-543: the lens is no longer voice-deaf — the server
// pushes the requested view (`data.view = {platform, n, at}`) via the declared `show_view` action, and this
// widget applies it only when the WITNESS COUNTER moves (asking for the same view twice still lands; a plain
// re-show moves nothing and yanks nothing). Header icon clicks call the SAME action, so UI and voice share
// one state instead of diverging.
let _platFilter = null;
let _viewN = 0;                      // last applied view token (module-lived)
let _openMail = null;
// CHAT LIST lens state, per platform and cosmetic only (which rows of the server's list are on screen): the
// kind filter and the name search. The list itself — window, «Cargar más», what the connector sent — is server
// state, so voice and clicks agree on it.
const _chatKind = {};
const _chatQuery = {};   // mailKey() of the single EMAIL item shown in the detail screen (V2-610), or null = list
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
  _openMail = null;           // a mail detail is a screen too: a lens change lands on that lens's LIST
  _newMail = null;            // and so is a message being written: leaving the section leaves it
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
  .hb-msg.full{height:100%;display:flex;flex-direction:column;min-height:0;container-type:inline-size}
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
  .hb-msg .segbtn.active{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216)}

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
  .hb-msg .tpara{font-size:12.5px;color:var(--hb-muted,#6b7b92);font-weight:400}
  .hb-msg .more{display:inline-block;margin-top:4px;font-size:12.5px;color:var(--hb-accent,#3D6FE0);cursor:pointer}
  .hb-msg .more:hover{text-decoration:underline}
  .hb-msg .tacts{display:flex;gap:2px;flex:0 0 auto;opacity:.3;transition:opacity .12s}
  .hb-msg .tacts button{border:0;background:transparent;border-radius:7px;width:26px;height:24px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#5b6b82);line-height:1}
  .hb-msg .tacts button:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}
  /* Action buttons carry inline SVG (never emoji): a glyph font renders each emoji
     differently per machine (the operator read the mute button as a subwoofer). */
  .hb-msg .acts button,.hb-msg .tacts button{display:inline-flex;align-items:center;justify-content:center}
  .hb-msg .acts button svg,.hb-msg .tacts button svg{width:14px;height:14px;display:block}

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
  /* WHERE AM I (2026-10-26): the house + title are lit on the home; inside a section they dim and the
     section's name follows as the current crumb. Outline icons, the same stroke as every action icon. */
  .hb-msg .homebtn{border:0;background:transparent;color:var(--hb-muted-2,#7d8a9c);width:32px;height:32px;
    border-radius:9px;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;margin-right:-4px}
  .hb-msg .homebtn svg{width:18px;height:18px}
  .hb-msg .homebtn:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}
  .hb-msg .homebtn.on{color:var(--hb-accent,#3D6FE0);background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 14%,transparent)}
  .hb-msg .hd .hdtitle{color:var(--hb-muted,#5f6b7c);font-weight:600}
  .hb-msg .hd .hdtitle.on{color:var(--hb-accent,#3D6FE0);font-weight:700}
  .hb-msg .hdsep,.hb-msg .msep{color:var(--hb-muted-2,#9aa7b8);font-size:14px}
  .hb-msg .hd .hdsec{font-size:17px;color:var(--hb-ink,#0d1622)}
  .hb-msg .hd .hdcur{font-size:14px;font-weight:600;color:var(--hb-muted,#5f6b7c)}
  /* The MAIL CLIENT (V2-807 T-01): ONE left rail — Compose, the Inbox opening into the categories the provider
     sorts it by, every other folder — each with the provider's own unread figure; the list beside it. The rail
     reads the card's OWN width (a container query, not the screen's): a narrow card folds it to icons, a phone-
     narrow one to a drawer behind the button that names where he is. */
  .hb-msg.full > .mclient{flex:1 1 auto;min-height:0}
  .hb-msg .mclient{container-type:inline-size;position:relative;min-height:0}
  .hb-msg .mcgrid{display:grid;grid-template-columns:208px minmax(0,1fr);gap:14px;height:100%;min-height:0}
  .hb-msg .mrail{display:flex;flex-direction:column;gap:1px;min-width:0;min-height:0;overflow:auto;
    padding-right:10px;border-right:1px solid var(--hb-line-subtle,#eef1f6)}
  .hb-msg .mpanel{min-width:0;min-height:0;overflow:auto;display:flex;flex-direction:column}
  .hb-msg .mcompose{height:36px;padding:0 14px;gap:8px;flex:0 0 auto;margin:0 0 10px;align-self:flex-start}
  .hb-msg .mcompose svg{width:15px;height:15px}
  .hb-msg .mnav{display:flex;align-items:center;gap:10px;border:0;background:transparent;color:var(--hb-muted,#5b6b82);
    font:inherit;font-size:13.5px;font-weight:600;padding:0 10px;min-height:32px;border-radius:999px;cursor:pointer;
    text-align:left;width:100%;box-sizing:border-box;position:relative;flex:0 0 auto}
  .hb-msg .mnav svg{width:16px;height:16px;flex:0 0 auto}
  .hb-msg .mnav .mnl{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-msg .mnav.sub{padding-left:26px;font-weight:500;font-size:13px;min-height:30px}
  .hb-msg .mnav:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}
  .hb-msg .mnav.on{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 16%,transparent);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .mnav.on .mfn{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#fff)}
  .hb-msg .mfn{font-size:11px;font-weight:700;min-width:16px;height:16px;padding:0 5px;border-radius:999px;flex:0 0 auto;
    display:inline-flex;align-items:center;justify-content:center;background:var(--hb-neutral,#3a4a5c);color:var(--hb-ink,#fff)}
  .hb-msg .mrules{margin-top:10px;padding:8px 6px 0;border-top:1px solid var(--hb-line-subtle,#eef1f6);
    display:flex;flex-direction:column;gap:2px;flex:0 0 auto}
  .hb-msg .mruleshd{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
    color:var(--hb-muted-2,#7d8a9c);padding:0 4px 4px}
  .hb-msg .mrule{display:flex;align-items:flex-start;gap:4px;font-size:12.5px;color:var(--hb-muted,#5b6b82);
    padding:3px 0 3px 4px;line-height:1.35}
  .hb-msg .mrulet{flex:1 1 auto;min-width:0;overflow-wrap:anywhere}
  .hb-msg .mrulex{border:0;background:transparent;color:var(--hb-muted-2,#7d8a9c);width:24px;height:24px;
    border-radius:7px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto}
  .hb-msg .mrulex:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-risk,#e5484d)}
  .hb-msg .mrailsep{height:1px;background:var(--hb-line-subtle,#eef1f6);margin:8px 6px;flex:0 0 auto}
  .hb-msg .mdrawerbtn{display:none;align-items:center;gap:8px;border:1px solid var(--hb-line,#e3e8f0);
    background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);font:inherit;font-size:13.5px;font-weight:600;
    border-radius:999px;padding:0 12px;min-height:34px;cursor:pointer;align-self:flex-start;margin:0 0 8px}
  .hb-msg .mdrawerbtn svg{width:16px;height:16px}
  @container (max-width:600px){
    .hb-msg .mcgrid{grid-template-columns:52px minmax(0,1fr);gap:10px}
    .hb-msg .mrail{padding-right:6px;align-items:center}
    .hb-msg .mnav,.hb-msg .mnav.sub{justify-content:center;padding:0;width:40px;min-height:36px}
    .hb-msg .mnav .mnl,.hb-msg .mcompose .mnl{display:none}
    .hb-msg .mnav .mfn{position:absolute;top:0;right:-4px;min-width:14px;height:14px;font-size:9.5px;padding:0 3px}
    .hb-msg .mcompose{width:40px;padding:0;justify-content:center;align-self:center}
    .hb-msg .mrules{display:none}
  }
  @container (max-width:440px){
    .hb-msg .mcgrid{grid-template-columns:minmax(0,1fr)}
    .hb-msg .mrail{display:none}
    .hb-msg .mdrawerbtn{display:inline-flex}
    .hb-msg .mcgrid.open .mrail{display:flex;position:absolute;z-index:3;top:42px;left:0;bottom:0;width:232px;
      align-items:stretch;padding:8px;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#e3e8f0);
      border-radius:12px;box-shadow:var(--hb-shadow-2,0 12px 32px rgba(0,0,0,.18))}
    .hb-msg .mcgrid.open .mnav{justify-content:flex-start;padding:0 10px;width:100%}
    .hb-msg .mcgrid.open .mnav.sub{padding-left:26px}
    .hb-msg .mcgrid.open .mnav .mnl,.hb-msg .mcgrid.open .mcompose .mnl{display:inline}
    .hb-msg .mcgrid.open .mnav .mfn{position:static}
    .hb-msg .mcgrid.open .mcompose{width:auto;padding:0 14px;align-self:flex-start}
    .hb-msg .mcgrid.open .mrules{display:flex}
  }
  .hb-msg .mlist{max-height:none}
  .hb-msg .mdptr{display:flex;align-items:center;gap:9px;width:100%;box-sizing:border-box;margin:0 0 6px;padding:0 12px;
    min-height:36px;border:1px dashed var(--hb-line-strong,#cfd6e0);border-radius:10px;background:transparent;
    color:var(--hb-ink,#0d1622);font:inherit;font-size:13px;cursor:pointer;text-align:left;flex:0 0 auto}
  .hb-msg .mdptr svg{width:15px;height:15px;color:var(--hb-accent,#3D6FE0);flex:0 0 auto}
  .hb-msg .mdptr .mdptrt{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-msg .mdptr .mdptro{color:var(--hb-accent,#3D6FE0);font-weight:600;flex:0 0 auto}
  .hb-msg .mdptr:hover{border-style:solid;border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .mrow.seen .mfrom{font-weight:500;color:var(--hb-muted,#5f6b7c)}
  .hb-msg .mrow.unseen .msubj{color:var(--hb-ink,#0d1622)}
  .hb-msg .mtag{font-size:11px;color:var(--hb-accent,#3D6FE0);font-weight:600;flex:0 0 auto}
  .hb-msg .mdtag{font-size:11px;font-weight:700;color:var(--hb-risk,#e5484d);flex:0 0 auto}
  .hb-msg .mgroup{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
    color:var(--hb-muted-2,#9aa7b8);padding:14px 2px 4px}
  .hb-msg .mmore{align-self:flex-start;margin:10px 0 2px}
  .hb-msg .mnote{font-size:12.5px;color:var(--hb-muted,#5b6b82);margin:4px 2px 8px}
  /* Navigation bar of a mail screen: ⌂ › Correo › Recibidos › <subject> … ← Recibidos. */
  .hb-msg .mcrumb{gap:6px;min-width:0}
  .hb-msg .mchome{border:0;background:transparent;color:var(--hb-muted-2,#7d8a9c);width:28px;height:28px;border-radius:8px;
    display:inline-flex;align-items:center;justify-content:center;cursor:pointer;flex:0 0 auto}
  .hb-msg .mchome svg{width:16px;height:16px}
  .hb-msg .mchome:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}
  .hb-msg .mcr{border:0;background:transparent;font-size:13px;color:var(--hb-muted,#5b6b82);padding:3px 4px;border-radius:6px;
    cursor:pointer;white-space:nowrap;flex:0 0 auto}
  .hb-msg .mcr:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-msg .mcr.cur{color:var(--hb-ink,#0d1622);cursor:default;font-weight:700;overflow:hidden;text-overflow:ellipsis;
    flex:0 1 auto;min-width:0}
  /* A DRAFT over the whole card: the fields, the text growing into every spare pixel, the buttons pinned below. */
  .hb-msg.full > .thread > .dfoot{flex:0 0 auto}
  .hb-msg .mdform{gap:0;padding:4px 14px 12px}
  .hb-msg .mdf{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--hb-line,#eef1f6);padding:6px 0}
  .hb-msg .mdk{font-size:12.5px;color:var(--hb-muted-2,#9aa7b8);width:56px;flex:0 0 auto}
  .hb-msg .mdin{flex:1;min-width:0;border:0;background:transparent;font:inherit;font-size:14px;color:var(--hb-ink,#0d1622);
    padding:6px 0;outline:none}
  .hb-msg .mdin[readonly]{color:var(--hb-muted,#5b6b82)}
  .hb-msg .mdbody{flex:1 1 auto;min-height:160px;border:0;background:transparent;resize:none;outline:none;font:inherit;
    font-size:14.5px;line-height:1.6;color:var(--hb-ink,#0d1622);padding:12px 0 0}
  .hb-msg .mdfiles{font-size:12.5px;color:var(--hb-muted,#5b6b82)}
  .hb-msg .dfoot{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:12px}
  .hb-msg .mddel:hover:not(:disabled){border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}
  .hb-msg .mdnote{font-size:12px;color:var(--hb-muted,#5b6b82)}
  /* On a narrow CARD (its own width, not the screen's — a narrow card on a wide desktop overflowed) the crumb keeps
     the house, what is open and the way back; the middle steps are the ← button. */
  @container (max-width:560px){
    .hb-msg .mcrumb .mcr:not(.cur),.hb-msg .mcrumb .msep{display:none}
  }
  /* V2-680 retired .mdsubj/.mdmeta/.mdfrom/.mdwhen/.mdbody: the detail screen draws the same LETTER the
     thread does now (.mltr below), so keeping a second set of rules for the same thing is how two
     renderings of one screen start to drift. */

  /* V2-680 — READING A MAIL, shaped like a mail client and not like a chat. The operator, looking at an
     email rendered as a chat bubble: «quita esa barrita roja de la izquierda… quiero ver el asunto, quién
     lo envía, quién está en copia y el texto en el medio… un cuadro bien delimitado… no quiero botones de
     mostrar más, lo quiero todo entero».
     So: a bordered PANE with its own scrollbar (he asked for it explicitly — «un scroll a la derecha») and
     a visible boundary, so he can see how much of it the content occupies; inside it, one bordered letter
     per message with a real envelope header; the body complete, never clamped. The urgency bar is GONE
     here on purpose — urgency belongs to the inbox list, which is where triage happens; inside an open
     letter it was a red stripe on the one thing he had already chosen to read. */
  .hb-msg .mpane{border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;background:var(--hb-bg-soft,#fbfdff);
    padding:12px;display:flex;flex-direction:column;gap:12px}
  /* Deliberately NO overflow:hidden on a letter, and the rendered test caught why: it was here for the
     rounded corners, and a letter taller than the pane got its body CUT — everything still "rendered",
     nothing readable, which is the exact failure this screen exists to end. The only thing clipping can
     do to a tall letter is hide the end of it. The letter keeps its full height (a flex item's default
     min-height:auto already refuses to shrink below its content) and the PANE scrolls past it. */
  .hb-msg .mltr{border:1px solid var(--hb-line,#e3e8f0);border-radius:10px;background:var(--hb-bg,#fff);
    padding:14px 16px}
  .hb-msg .mltr.out{background:var(--hb-hover,#eef3f9)}
  .hb-msg .mltrsubj{font-size:16px;font-weight:700;color:var(--hb-ink,#0d1622);word-break:break-word;
    margin:0 0 9px;line-height:1.3}
  /* The envelope block: a label column and a value column, the shape every mail client uses. */
  .hb-msg .menv{display:grid;grid-template-columns:auto 1fr;gap:3px 10px;align-items:baseline;
    padding-bottom:11px;margin-bottom:12px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-msg .menvk{font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;
    color:var(--hb-muted-2,#9aa7b8);white-space:nowrap}
  .hb-msg .menvv{font-size:13px;color:var(--hb-ink,#0d1622);word-break:break-word;min-width:0}
  .hb-msg .menvv .addr{color:var(--hb-muted,#6b7b92)}
  .hb-msg .mltrbody{font-size:14.5px;line-height:1.65;color:var(--hb-ink,#0d1622);
    white-space:pre-wrap;word-break:break-word}
  .hb-msg .mltrbody a.lnk{color:var(--hb-accent,#3D6FE0);text-decoration:underline}
  .hb-msg .mltr .tacts{opacity:.55;margin-top:12px}
  .hb-msg .mltr:hover .tacts{opacity:1}

  /* Grouped CHAT list + open thread. */
  .hb-msg .chatrow{cursor:pointer;margin:0 -8px;padding-left:8px;padding-right:8px;border-radius:9px}
  .hb-msg .chatrow:hover{background:var(--hb-hover,#eef3f9)}
  .hb-msg .tcount{background:var(--hb-neutral,#3a4a5c);color:#fff;font-size:10.5px;font-weight:700;border-radius:999px;
    min-width:17px;height:17px;padding:0 5px;display:inline-flex;align-items:center;justify-content:center}
  .hb-msg .tprev{font-size:13.5px;color:var(--hb-muted,#5f6b7c);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-msg .thd{display:flex;align-items:center;gap:9px;margin:0 0 10px;padding-bottom:9px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  /* V2-616 F3 — a real button, in the corner, never a bare underlined link: the operator's own words
     ("estas flechas así largas que se subraya... no me gusta nada"). margin-left:auto on the LAST child
     pushes it to the far right while the name (appended first) stays left, same pattern the connector list
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
  /* V2-819 — a send that did not leave says so where he wrote it; his text stays in the box. */
  .hb-msg .composeerr{color:var(--hb-risk,#e5484d);font-size:12.5px;margin:0 0 7px}
  .hb-msg .cxava{width:22px;height:22px;border-radius:50%;object-fit:cover;flex:0 0 auto;margin-right:6px;vertical-align:middle}
  .hb-msg .composebox{flex:1 1 auto;min-width:0;box-sizing:border-box;resize:vertical;min-height:112px;
    font:inherit;font-size:14px;line-height:1.45;color:var(--hb-ink,#0d1622);background:var(--hb-hover,#eef3f9);
    border:1px solid var(--hb-line,#eef1f6);border-radius:10px;padding:9px 11px}
  .hb-msg .composebox:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .thread.plat-whatsapp .composebox:focus{border-color:#16B8A6}
  .hb-msg .thread.plat-telegram .composebox:focus{border-color:#2AABEE}
  .hb-msg .thread.plat-email .composebox:focus{border-color:#D8452D}
  .hb-msg .composeside{display:flex;flex-direction:column;gap:6px;flex:0 0 auto;justify-content:flex-end}
  .hb-msg .composeside .bt{white-space:nowrap}
  .hb-msg .pending{display:flex;flex-direction:column;gap:6px;margin:6px 0}
  .hb-msg .prow{display:flex;flex-direction:column;gap:4px;align-items:flex-start;padding:8px;border-radius:8px;background:var(--surface-2, rgba(127,127,127,.08))}
  .hb-msg .prow .pbody{white-space:pre-wrap;max-height:7.5em;overflow:auto;opacity:.85}
  /* Attachments picked in the card: a row of chips (a thumbnail for a picture), each removable. */
  .hb-msg .attrow{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}
  .hb-msg .attchip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--hb-line,#e3e8f0);
    border-radius:8px;padding:3px 6px;font-size:12px;max-width:220px;background:var(--hb-bg,#fff)}
  .hb-msg .attchip img{width:32px;height:32px;object-fit:cover;border-radius:4px}
  .hb-msg .attchip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-msg .attchip button{border:0;background:transparent;cursor:pointer;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .attbtn{display:inline-flex;align-items:center;padding:5px 9px;color:var(--hb-muted,#6b7b92)}
  .hb-msg .composemain > .attbtn{flex:0 0 auto;align-self:flex-end}
  /* A picture waiting to be sent is a thumbnail above the box, its ✕ in the corner. */
  .hb-msg .attchip.attthumb{position:relative;padding:0;border-radius:10px;overflow:hidden;width:72px;height:72px;max-width:none}
  .hb-msg .attchip.attthumb img{width:72px;height:72px;border-radius:0;display:block}
  .hb-msg .attchip.attthumb button{position:absolute;top:3px;right:3px;width:20px;height:20px;padding:0;border-radius:50%;
    background:rgba(0,0,0,.55);color:#fff;font-size:11px;line-height:20px}
  .hb-msg .attbtn.busy{opacity:.5}
  .hb-msg .cxnewbt{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--hb-muted,#6b7b92)}
  .hb-msg .cxtag svg{vertical-align:-2px}
  /* «Nuevo chat» / «Nuevo grupo» on a platform's chat list. */
  .hb-msg .cxnew{display:flex;gap:6px;margin:0 0 6px}
  .hb-msg .newform{display:flex;flex-direction:column;gap:6px;border:1px solid var(--hb-line,#e3e8f0);
    border-radius:10px;padding:10px;margin:0 0 8px}
  .hb-msg .newform input,.hb-msg .newform textarea{box-sizing:border-box;width:100%;border:1px solid var(--hb-line,#e3e8f0);
    border-radius:8px;padding:6px 10px;font:inherit;font-size:13px;background:var(--hb-bg,#fff);color:var(--hb-ink,#26313d)}
  .hb-msg .newform .row{display:flex;gap:6px;justify-content:flex-end;align-items:center}
  .hb-msg .newerr{color:var(--hb-risk,#e5484d);font-size:12px}
  /* The reply / reply-all selector, ABOVE the box (email only — the other platforms have no second
     recipient to include). A segmented control, the same .seg language the settings panel already uses. */
  .hb-msg .composetop{display:flex;align-items:center;gap:9px;margin-bottom:7px;flex-wrap:wrap}
  .hb-msg .composehint{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8)}
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
  .hb-msg .tbrow.out .tbubble{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);border-bottom-right-radius:4px}
  .hb-msg .tbubble.urg{box-shadow:inset 3px 0 0 var(--hb-risk,#e5484d)}
  /* V2-616 F4 — WhatsApp reads as WhatsApp, Telegram as Telegram, email as email: his own reply's bubble and
     the compose button take the OPEN thread's platform color (.thread.plat-ID, set once in threadView/
     mailDetail) instead of the one generic accent blue every platform shared before. Literal hex, matching
     PLAT[pl].bg exactly — the same identity, not a second palette that can drift from it. */
  .hb-msg .thread.plat-whatsapp .tbrow.out .tbubble,
  .hb-msg .thread.plat-whatsapp .composeside .bt-primary,
  .hb-msg .thread.plat-whatsapp .dfoot .bt-primary{background:#16B8A6}
  .hb-msg .thread.plat-telegram .tbrow.out .tbubble,
  .hb-msg .thread.plat-telegram .composeside .bt-primary,
  .hb-msg .thread.plat-telegram .dfoot .bt-primary{background:#2AABEE}
  .hb-msg .thread.plat-email .tbrow.out .tbubble,
  .hb-msg .thread.plat-email .composeside .bt-primary,
  .hb-msg .thread.plat-email .dfoot .bt-primary{background:#D8452D}
  .hb-msg .compose .bt-primary.pressing{transform:scale(.92);box-shadow:0 0 0 5px rgba(42,171,238,.35);transition:transform .12s,box-shadow .12s}
  .hb-msg .compose .bt-primary.sent{opacity:.85}
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
  .hb-msg .maudio{display:flex;flex-direction:column;align-items:stretch;gap:4px;width:100%;min-width:220px;box-sizing:border-box}
  .hb-msg .mameta{display:flex;align-items:center;gap:8px}
  .hb-msg .mawhen{margin-left:auto;font-size:10.5px;opacity:.6;font-variant-numeric:tabular-nums}
  .hb-msg .tbrow.out .mawhen{color:rgba(255,255,255,.85);opacity:1}
  .hb-msg .tbubble.hasaudio{min-width:240px}
  .hb-msg .mapbtn{flex:0 0 auto;width:32px;height:32px;border-radius:50%;border:0;cursor:pointer;
    background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);font-size:12px;display:flex;align-items:center;justify-content:center}
  .hb-msg .mapbtn:hover{filter:brightness(1.08)}
  .hb-msg .mawave{flex:0 0 auto;width:100%;min-width:0;height:30px;display:flex;align-items:center;gap:2.5px;cursor:pointer;touch-action:none}
  .hb-msg .mabar{flex:1 1 0;min-width:2px;border-radius:2px;background:var(--hb-muted-2,#9aa7b8);opacity:.5}
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

  /* CHAT LIST of a platform: what the real app shows first — every conversation, newest first, a kind filter,
     a name search and «Cargar más». */
  .hb-msg .cxbar{display:flex;flex-direction:column;gap:6px;margin:2px 0 6px}
  .hb-msg .cxchips{display:flex;gap:6px;flex-wrap:wrap}
  .hb-msg .cxchip{border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-muted,#6b7b92);
    border-radius:999px;font-size:12px;padding:3px 10px;cursor:pointer}
  .hb-msg .cxchip.on{background:var(--hb-ink,#26313d);border-color:var(--hb-ink,#26313d);color:var(--hb-bg,#fff)}
  .hb-msg .cxsearch{width:100%;box-sizing:border-box;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;
    padding:6px 10px;font-size:13px;background:var(--hb-bg,#fff);color:var(--hb-ink,#26313d)}
  .hb-msg .cxtag{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);font-weight:400}
  .hb-msg .trow.cxarch{opacity:.6}
  .hb-msg .cxmore{display:block;margin:8px auto 2px;font-size:12.5px;padding:5px 14px}
  .hb-msg .snote{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);margin:4px 0 8px}
  .hb-msg .cxnote{text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:12px;padding:8px 0 2px}

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

  /* The «connect a channel» prompt of an empty card. */
  .hb-msg .wbody{font-size:13.5px;color:var(--hb-muted,#4a5a70);line-height:1.6}
  .hb-msg .wbody b{color:var(--hb-ink,#0d1622)}
  /* Homogeneous buttons (V2-570): one scale for every action of the card, instead of the .btn/.cbtn/.dbtn set
     that had grown three different heights and paddings. */
  .hb-msg .bt{height:38px;padding:0 18px;border-radius:10px;font-size:13.5px;font-weight:600;cursor:pointer;
    display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;
    /* A bare .bt (Save draft, attach) is the quiet button: without these it wore the browser's own light-grey
       face on the dark card, and the attach icon drew black on grey (V2-813, iPhone 14). */
    border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-ink,#0d1622)}
  .hb-msg .bt:hover:not(:disabled){border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .bt:disabled{opacity:.6;cursor:default}
  .hb-msg .bt-primary{border:0;color:var(--canvas,#101216);background:var(--hb-accent,#3D6FE0)}
  .hb-msg .bt-primary:hover:not(:disabled){filter:brightness(1.06)}
  .hb-msg .bt-ghost{border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-muted,#5b6b82)}
  .hb-msg .bt-ghost:hover:not(:disabled){border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  /* The grid of channel icons (the «connect a channel» prompt): compact with 3 connectors or 20. */
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
  d.title = p.label + (on ? tt("dot_connected", null, ": conectado") : tt("dot_disconnected", null, ": no conectado"));
  return d;
}

function platformChip(platform){
  const p=PLAT[platform]||{label:platform||"?",bg:"var(--hb-muted,#6b7b92)"};
  const c=el("span","pchip",(p.label||"?")[0]); c.style.background=p.bg; c.title=p.label;
  return c;
}

// Real brand icon for the header connection state. `on` only changes opacity (dimmed = disconnected); brand color
// always remains, so the app stays recognizable even when unlinked.
// Action icons are inline SVG (same self-contained pattern as BRAND_SVG above):
// the row of per-message buttons used to be emoji text, and one emoji font drew
// the mute glyph as something the operator read as a subwoofer (live report,
// 2026-09-18: "an okay flag, then an x, then a subwoofer"). Stroke style matches
// the app icon language (24px grid, currentColor). Same five actions, same order.
const ACTION_SVG = {
  home:    [["path", {d: "M3 10.5 12 3l9 7.5"}], ["path", {d: "M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"}]],
  pen:     [["path", {d: "M12 20h9"}], ["path", {d: "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"}]],
  check:   [["path", {d: "M20 6 9 17l-5-5"}]],
  close:   [["path", {d: "M18 6 6 18"}], ["path", {d: "m6 6 12 12"}]],
  archive: [["rect", {x: "2", y: "3", width: "20", height: "5", rx: "1"}],
            ["path", {d: "M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"}],
            ["path", {d: "M10 12h4"}]],
  trash:   [["path", {d: "M3 6h18"}],
            ["path", {d: "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"}],
            ["path", {d: "M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"}],
            ["path", {d: "M10 11v6"}], ["path", {d: "M14 11v6"}]],
  mute:    [["path", {d: "M11 5 6 9H2v6h4l5 4V5z"}],
            ["path", {d: "m22 9-6 6"}], ["path", {d: "m16 9 6 6"}]],
  // Composing and the chat list — same 24px stroke language.
  clip:    [["path", {d: "m21.4 11.6-8.5 8.5a5.5 5.5 0 0 1-7.8-7.8l8.5-8.5a3.7 3.7 0 0 1 5.2 5.2l-8.5 8.5a1.8 1.8 0 0 1-2.6-2.6l7.8-7.8"}]],
  pencil:  [["path", {d: "M12 20h9"}], ["path", {d: "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"}]],
  users:   [["path", {d: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"}], ["circle", {cx: "9", cy: "7", r: "4"}],
            ["path", {d: "M22 21v-2a4 4 0 0 0-3-3.9"}], ["path", {d: "M16 3.1a4 4 0 0 1 0 7.8"}]],
  image:   [["rect", {x: "3", y: "3", width: "18", height: "18", rx: "2"}], ["circle", {cx: "9", cy: "9", r: "2"}],
            ["path", {d: "m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"}]],
  video:   [["path", {d: "m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 11"}],
            ["rect", {x: "2", y: "6", width: "14", height: "12", rx: "2"}]],
  mic:     [["path", {d: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"}], ["path", {d: "M19 10v2a7 7 0 0 1-14 0v-2"}],
            ["path", {d: "M12 19v3"}]],
  file:    [["path", {d: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"}], ["path", {d: "M14 2v4a2 2 0 0 0 2 2h4"}]],
  // The mail rail: one icon per folder role and per provider category (V2-807 T-01).
  inbox:   [["path", {d: "M22 12h-6l-2 3h-4l-2-3H2"}],
            ["path", {d: "M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z"}]],
  star:    [["path", {d: "m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.2L5.8 21 7 14.2 2 9.3l6.9-1Z"}]],
  send:    [["path", {d: "m22 2-7 20-4-9-9-4Z"}], ["path", {d: "M22 2 11 13"}]],
  mail:    [["rect", {x: "2", y: "4", width: "20", height: "16", rx: "2"}], ["path", {d: "m22 7-10 6L2 7"}]],
  alert:   [["circle", {cx: "12", cy: "12", r: "10"}], ["path", {d: "M12 8v4"}], ["path", {d: "M12 16h.01"}]],
  tag:     [["path", {d: "M12.6 2.6A2 2 0 0 0 11.2 2H4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 .6 1.4l8.7 8.7a2.4 2.4 0 0 0 3.4 0l6.6-6.6a2.4 2.4 0 0 0 0-3.4Z"}],
            ["circle", {cx: "7.5", cy: "7.5", r: "1"}]],
  info:    [["circle", {cx: "12", cy: "12", r: "10"}], ["path", {d: "M12 16v-4"}], ["path", {d: "M12 8h.01"}]],
  chat:    [["path", {d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"}]],
  menu:    [["path", {d: "M4 6h16"}], ["path", {d: "M4 12h16"}], ["path", {d: "M4 18h16"}]],
  bellOff: [["path", {d: "M8.7 3A6 6 0 0 1 18 8a21.3 21.3 0 0 0 .6 5"}], ["path", {d: "M17 17H3s3-2 3-9a4.7 4.7 0 0 1 .3-1.7"}],
            ["path", {d: "M10.3 21a1.9 1.9 0 0 0 3.4 0"}], ["path", {d: "m2 2 20 20"}]],
};
function actionIcon(name){
  const svg=document.createElementNS(SVG_NS,"svg");
  svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("width","14"); svg.setAttribute("height","14");
  svg.setAttribute("fill","none"); svg.setAttribute("stroke","currentColor");
  svg.setAttribute("stroke-width","2"); svg.setAttribute("stroke-linecap","round");
  svg.setAttribute("stroke-linejoin","round"); svg.setAttribute("aria-hidden","true");
  for(const [tag, attrs] of (ACTION_SVG[name]||[])){
    const s=document.createElementNS(SVG_NS,tag);
    for(const k of Object.keys(attrs)) s.setAttribute(k,attrs[k]);
    svg.appendChild(s);
  }
  return svg;
}
function iconButton(name, title, cls){
  const b=document.createElement("button");
  b.type="button"; if(cls)b.className=cls;
  b.title=title; b.setAttribute("aria-label",title);
  b.appendChild(actionIcon(name));
  return b;
}
// Busy feedback that keeps the icon: disabling + dimming blocks a second press
// without wiping the button's SVG (the old textContent="…" replaced the glyph).
function markBusy(btn){ btn.disabled=true; btn.style.opacity=".45"; }

function brandIcon(platform, on){
  const p=PLAT[platform]||{label:platform||"?",bg:"var(--hb-muted,#6b7b92)"};
  const spec=BRAND_SVG[platform];
  const wrap=el("span","picon"+(on?" on":""));
  wrap.title=p.label+(on?tt("dot_connected", null, ": conectado"):tt("dot_disconnected", null, ": no conectado"));
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
function mediaLabel(kind){
  switch(String(kind || "")){
    case "image":    return tt("media_image", null, "📷 Foto");
    case "video":    return tt("media_video", null, "🎥 Vídeo");
    case "audio":    return tt("media_audio", null, "🎵 Audio");
    case "ptt":      return tt("media_ptt", null, "🎤 Nota de voz");
    case "document": return tt("media_document", null, "📄 Documento");
    default:         return "";
  }
}
const PLACEHOLDER_RE = /^\[(image|video|audio|ptt|document) received\]$/;

// V2-622 — a bare media placeholder ("[audio received]", or an empty body with a mediaType) becomes a label
// like "🎵 Audio" purely so something reads where the caption would be. Once a real media block actually
// renders below it, that label is pure noise — the player/thumbnail/link already say what it is. Only a
// REAL caption the sender actually typed still needs the text line.
function isBareMediaLabel(body){
  const b = cleanBody(body);
  return !b || PLACEHOLDER_RE.test(b);
}

// A body that is really HTML (stored before the connector learned to read a «plain» part that is markup) is shown as
// the text it carries. DOMParser builds an INERT document: no script runs and nothing is fetched (V2-813).
const _BLOCK_TAGS = "br,p,div,tr,li,h1,h2,h3,h4,table,blockquote";
function markupText(b){
  const s = (b || "").trimStart();
  if(!s.startsWith("<")) return b;
  let doc;
  try { doc = new DOMParser().parseFromString(s, "text/html"); } catch(_) { return b; }
  doc.querySelectorAll("style,script,head,title").forEach(e => e.remove());
  doc.querySelectorAll(_BLOCK_TAGS).forEach(e => e.after(doc.createTextNode("\n")));
  const t = (doc.body ? doc.body.textContent : "").split("\n").map(l => l.replace(/\s+/g, " ").trim())
    .filter((l, i, a) => l || (i && a[i - 1])).join("\n").trim();
  return t && t.length < 0.6 * s.length ? t : b;
}

function displayBody(body, mediaType){
  const b = cleanBody(body);
  const m = b.match(PLACEHOLDER_RE);
  if(m) return mediaLabel(m[1]) || b;
  if(!b && mediaType) return mediaLabel(mediaType) || "";
  return b;
}

function fmtWhen(ts){
  const t = Number(ts||0);
  if(!t) return "";
  const d = new Date(t*1000), now = new Date();
  const hm = d.toLocaleTimeString(_LANG, {hour:"2-digit", minute:"2-digit"});
  if(d.toDateString() === now.toDateString()) return hm;
  return d.toLocaleDateString(_LANG, {day:"numeric", month:"short"}) + " " + hm;
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

// V2-819 (approved design, 2026-10-27) — the waveform runs across the TOP of the bubble, as wide as the bubble and
// scrubbable; below it, one meta line: play, the duration, and the message's date and time (`when`, when the caller
// hands it over so the bubble does not print it twice).
function audioPlayer(url, when){
  const wrap = el("div","maudio");
  const btn = document.createElement("button");
  btn.type="button"; btn.className="mapbtn"; btn.textContent="▶"; btn.title=tt("play", null, "Reproducir");
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
  const meta = el("div","mameta");
  meta.append(btn, time);
  if(when) meta.append(el("span","mawhen", when));
  wrap.append(wave, meta, au);

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
  au.addEventListener("play", ()=>{ btn.textContent="⏸"; btn.title=tt("pause", null, "Pausar"); });
  au.addEventListener("pause", ()=>{ btn.textContent="▶"; btn.title=tt("play", null, "Reproducir"); });
  au.addEventListener("ended", ()=>{ btn.textContent="▶"; btn.title=tt("play", null, "Reproducir"); });
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

function mediaBlock(it, when){
  const list = it.media || [];
  if(!list.length){
    // Downloaded once and later removed from this device by the media window: say where it still is.
    return it.mediaGone ? el("span","mdoc",tt("media_gone", null, "Ya no está en este dispositivo — sigue en tu móvil")) : null;
  }
  const w = el("div","mediaw");
  list.forEach(u=>{
    const url = String((u&&u.url)||"");
    if(!url.startsWith("/widgets/")) return;             // our own asset route only, never an arbitrary origin
    const t = (u&&u.type) || it.mediaType || "";
    if(t==="image"){
      const a=document.createElement("a"); a.href=url; a.target="_blank"; a.rel="noopener";
      const img=document.createElement("img"); img.className="matt"; img.src=url;
      img.loading="lazy"; img.decoding="async"; img.alt=(u&&u.name)||tt("image_alt", null, "imagen");
      img.onerror=()=>{ a.replaceWith(el("span","mdoc",tt("image_unavailable", null, "📷 (no disponible)"))); };
      a.appendChild(img); w.appendChild(a);
    } else if(t==="video"){
      const v=document.createElement("video"); v.className="mvid"; v.controls=true; v.preload="metadata"; v.src=url;
      w.appendChild(v);
    } else if(t==="audio"||t==="ptt"){
      // The bubble's date and time go on the player's own meta line — only for the first clip, and the caller
      // learns it (`usedWhen`) so the bubble does not print them a second time.
      w.appendChild(audioPlayer(url, w.usedWhen ? "" : (when || "")));
      if(when) w.usedWhen = true;
    } else {
      const a=document.createElement("a"); a.className="mdoc"; a.href=url; a.target="_blank"; a.rel="noopener";
      a.textContent="📄 "+((u&&u.name)||tt("document_alt", null, "documento"));
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

// Settings panel: simple/complete profile + connected platforms + muted channels. Replaces the old fixed footer
// (always-visible "connected"/"unlink" chips) with something that does not distract unless the user asks for it.
function settingsPanel(platforms, data, ctx, rerender){
  const wrap = el("div","settings");

  wrap.appendChild(el("div","stitle",tt("profile", null, "Perfil")));
  const seg = el("div","seg");
  [["simple",tt("profile_simple", null, "Simple")], ["completo",tt("profile_full", null, "Completo")]].forEach(([key,label])=>{
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
    wrap.appendChild(el("div","stitle",tt("autoresponder", null, "Autorespondedor")));
    const box = el("div","conns");
    autoOn.forEach(p=>{
      const cfg = auto[p] || {};
      const chip = el("span","ok");
      const win = cfg.hours ? (" · " + cfg.hours) : "";
      chip.append(document.createTextNode("🤖 " + ((PLAT[p]||{}).label||p) + win + " — «" +
                                          String(cfg.text||"").slice(0,80) + "»"));
      const off = el("span","lk",tt("autoresp_remove", null, "quitar"));
      off.onclick = ()=>{ off.textContent="…"; ctx.action("clear_autoresponder", {platform: p}); };
      chip.append(document.createTextNode(" · "), off);
      box.appendChild(chip);
    });
    wrap.appendChild(box);
  }

  // How long downloaded media stays on this device (widgets/mensajeria/media.py). Older pictures, videos and
  // voice notes leave this device and stay on the phone; the message keeps saying what was there.
  wrap.appendChild(el("div","stitle",tt("media_keep", null, "Multimedia en este dispositivo")));
  const mseg = el("div","seg");
  const cur = Number(data.media_days == null ? 14 : data.media_days);
  [[7,tt("media_7", null, "7 días")],[14,tt("media_14", null, "14 días")],[30,tt("media_30", null, "30 días")],
   [90,tt("media_90", null, "90 días")],[0,tt("media_always", null, "Siempre")]].forEach(([d,label])=>{
    const b = el("button","segbtn"+(cur===d?" active":""), label);
    b.onclick=()=>{ if(cur!==d) ctx.action("set_media_days", {days: d}); };
    mseg.appendChild(b);
  });
  wrap.appendChild(mseg);
  wrap.appendChild(el("div","snote",tt("media_keep_hint", null, "Lo más antiguo se borra de aquí; sigue en tu móvil.")));

  const muted = data.muted_channels||[];
  if(muted.length){
    wrap.appendChild(el("div","stitle",tt("muted", null, "Silenciados")));
    const row = el("div","conns");
    muted.forEach(m=>{
      const chip=el("span","ok"); chip.append(document.createTextNode("🔇 "+m.group));
      const lk=el("span","lk",tt("unhide", null, "reactivar"));
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
    if(mine) from.appendChild(el("span","tag",tt("for_you", null, "para ti")));
    if(urg.urgent) from.appendChild(el("span","tag",tt("urgent", null, "urgente")));
    body.appendChild(from);
    const media = mediaBlock(it);
    if(!(media && isBareMediaLabel(it.body))){
      const msgEl = el("div","msg"); linkify(msgEl, displayBody(it.body, it.mediaType)); body.appendChild(msgEl);
    }
    if(media) body.appendChild(media);
    if(it.motivo) body.appendChild(el("div","why", it.motivo));
    row.appendChild(body);

    const acts = el("div","acts");
    const read=iconButton("check",tt("mark_read", null, "Marcar como leído")); read.onclick=()=>ctx.action("read",{n:it.n});
    const dis=iconButton("close",tt("dismiss", null, "Descartar (no marcar leído)")); dis.onclick=()=>ctx.action("dismiss",{n:it.n});
    const mute=iconButton("mute",tt("mute_channel_long", null, "Silenciar este canal (no volverán a salir sus mensajes)"),"mute");
    mute.onclick=()=>{ markBusy(mute); ctx.action("hide",{n:it.n}); };
    acts.append(read,dis,mute); row.appendChild(acts);
    list.appendChild(row);
  });
  return list;
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
const _draftFiles = {};   // key -> [{name,url,type,original}] attached in the card, not yet sent
const _newForm = {};      // platform -> "chat" | "group" | null — the «Nuevo» form open on that platform's list
const _draftLocal = {};   // key -> text not yet round-tripped to the server (keystroke buffer, per screen)
let _draftTimer = null;
// V2-819 — a send from his own hand is answered. `_sending[key]` is the order on its way ({ref, text}): the box keeps
// his text, locked, until the outbox row `ref` (data.outbox) says «sent»; a refusal or a failure unlocks it with the
// reason in `_sendNote[key]`. Before, the box was emptied the moment the order was QUEUED, and nothing that happened
// after that ever reached the card — a send that never left looked exactly like one that did.
const _sending = {};
const _sendNote = {};
function _newRef(){ return "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
// The words for why a send did not leave: the server's code mapped to his language, its own sentence otherwise.
function _sendFailText(res, platform){
  const label = (PLAT[platform] || {}).label || platform || "";
  const code = res && (res.error || res.state);
  if(!res) return tt("send_offline", null, "El agente no ha contestado: no se ha enviado nada.");
  if(code === "not_connected") return tt("send_not_connected", {platform: label}, `${label} no está conectado, así que no se ha enviado.`);
  if(code === "empty") return tt("send_empty", null, "No hay nada escrito que enviar.");
  if(code === "no_target") return tt("send_no_target", null, "No sé a qué conversación va: ábrela y vuelve a enviarlo.");
  if(code === "unconfirmed") return tt("send_unconfirmed", {platform: label}, `${label} todavía no ha confirmado el envío: puede que no haya salido.`);
  const why = String((res && (res.reason || res.message)) || "").trim();
  return tt("not_sent", null, "No se ha enviado") + (why ? ": " + why : "");
}

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

// ATTACHING, the way every messaging app does it: the clip opens the file picker, each file is uploaded by the canvas
// (`ctx.upload` — this widget never touches the network) and shows as a chip; the chips' NAMES travel in the
// action that sends. `files` is the list being edited; `onChange` re-syncs whatever owns it.
function attachControls(ctx, files, onChange){
  const row = el("div","attrow");
  const paint = ()=>{
    row.replaceChildren();
    files.forEach((f, i)=>{
      const pic = f.type === "image" && String(f.url||"").startsWith("/widgets/");
      const chip = el("span","attchip" + (pic ? " attthumb" : ""));
      if(pic){
        const img = document.createElement("img"); img.src = f.url; img.alt = f.original || f.name; chip.appendChild(img);
        chip.title = f.original || f.name;
      } else {
        chip.appendChild(actionIcon(f.type === "video" ? "video" : (f.type === "audio" ? "mic" : "file")));
        chip.appendChild(el("span", null, f.original || f.name));
      }
      const x = el("button", null, "✕"); x.title = tt("attach_remove", null, "Quitar");
      x.onclick = ()=>{ files.splice(i, 1); paint(); onChange(); };
      chip.appendChild(x);
      row.appendChild(chip);
    });
    row.style.display = files.length ? "" : "none";
  };
  const input = document.createElement("input");
  input.type = "file"; input.multiple = true; input.style.display = "none";
  const btn = el("button","bt attbtn"); btn.appendChild(actionIcon("clip"));
  btn.title = tt("attach", null, "Adjuntar foto, vídeo o archivo"); btn.setAttribute("aria-label", btn.title);
  btn.onclick = ()=> input.click();
  input.onchange = async ()=>{
    const picked = Array.from(input.files || []);
    input.value = "";
    if(!picked.length || typeof ctx.upload !== "function") return;
    btn.disabled = true; btn.classList.add("busy");
    for(const file of picked){
      const r = await ctx.upload(file);
      if(r && r.name) files.push({name: r.name, url: r.url, type: r.type, original: r.original || file.name});
    }
    btn.disabled = false; btn.classList.remove("busy");
    paint(); onChange();
  };
  paint();
  return {row, btn, input};
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
  box.placeholder = tt("compose_ph", null, "Escribe tu respuesta… (o dila por voz y aparecerá aquí)");
  box.rows = 5;                       // the operator's own minimum — a reply is written, not tweeted
  box.value = (key in _draftLocal) ? _draftLocal[key] : serverText;
  box.dataset.keep = "compose:" + key;      // V2-819: focus and caret survive a repaint (see _captureWhere)

  // Reply / reply-all, above the box. Only for a mail whose original really had other recipients.
  if(others.length){
    const top = el("div","composetop");
    const seg = el("div","seg");
    [["one",tt("reply", null, "Responder")], ["all",tt("reply_all", null, "Responder a todos")]].forEach(([id, label])=>{
      const b = el("button","segbtn"+(((id==="all")===replyAll)?" active":""), label);
      b.onclick = ()=>{ _replyAll[key] = (id === "all"); rerender(); };
      seg.appendChild(b);
    });
    top.appendChild(seg);
    // What reply-all actually ADDS, named out loud: the promise is only worth making if he can see it.
    top.appendChild(el("span","composehint", replyAll
      ? (tt("cc_", null, "copia a ") + others.slice(0,3).join(", ") + (others.length > 3 ? tt("and_n_more", {n:others.length-3}, ` y ${others.length-3} más`) : ""))
      : (others.length === 1 ? tt("one_more_recipient", null, "1 destinatario más en el original")
                             : tt("n_more_recipients", {n:others.length}, `${others.length} destinatarios más en el original`))));
    wrap.appendChild(top);
  }

  const main = el("div","composemain");
  const side = el("div","composeside");
  const send = el("button","bt bt-primary",tt("send", null, "Enviar ➤"));
  const save = el("button","bt",tt("save_draft", null, "Guardar borrador"));
  save.title = tt("save_draft_hint", null, "Guardar lo escrito sin enviarlo (también se guarda solo al dejar de escribir)");
  if(!(key in _draftFiles)){
    const saved = (stored && Array.isArray(stored.files)) ? stored.files : [];
    _draftFiles[key] = saved.map(n=>({name: n, url: "/widgets/mensajeria/asset/" + n, original: String(n).split("_").slice(2).join("_") || n,
                                      type: /\.(jpe?g|png|webp|gif|heic)$/i.test(n) ? "image" : "document"}));
  }
  const files = _draftFiles[key];
  const syncBtn = () => { send.disabled = !!_sending[key] || (!box.value.trim() && !files.length); };
  // V2-819 — the order on its way settles from the state: its outbox row says sent (the box empties), or failed /
  // unconfirmed (his text comes back, unlocked, with the reason).
  const going = _sending[key];
  if(going){
    const row = (data.outbox || []).find(r => r && r.ref === going.ref);
    if(row && row.state === "sent"){
      delete _sending[key]; delete _draftLocal[key]; _draftFiles[key] = []; files.length = 0;
      box.value = "";
    } else if(row && row.state !== "queued"){
      delete _sending[key]; _draftLocal[key] = going.text; box.value = going.text;
      _sendNote[key] = _sendFailText(row, row.platform);
    } else {
      box.value = going.text; box.readOnly = true;
      send.textContent = tt("sending", null, "Enviando…");
    }
  }
  syncBtn();

  const payload = () => ({...targetPayload, reply_all: replyAll, files: files.map(f=>f.name)});
  const att = attachControls(ctx, files, ()=>{ syncBtn(); ctx.action("draft", {...payload(), text: box.value}); });
  box.addEventListener("input", () => {
    _draftLocal[key] = box.value;
    if(_sendNote[key]){ delete _sendNote[key]; const n = wrap.querySelector(".composeerr"); if(n) n.remove(); }
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
    save.textContent = tt("saved", null, "Guardado ✓");
    setTimeout(()=>{ try{ save.textContent = tt("save_draft", null, "Guardar borrador"); }catch(_){} }, 1600);
  };
  send.onclick = async () => {
    const text = box.value;
    if(_sending[key] || (!text.trim() && !files.length)) return;
    clearTimeout(_draftTimer);
    // ONE order, carrying what is in the box and naming the conversation it is for. It used to be two (`draft`,
    // then a bare `send_draft {}` that sent «the most recent draft», whichever conversation that was), and the box
    // was emptied before anything was known. Now the box keeps his text until the outbox row says it left.
    const ref = _newRef();
    _sending[key] = {ref, text};
    delete _sendNote[key];
    const chat = activeChat ? {platform: activeChat.platform, chatId: activeChat.chatId} : null;
    rerender();
    const res = await ctx.action("send_draft", {...targetPayload, ...(chat ? {chat} : {}), ref, box_key: key, text,
                                                reply_all: replyAll, files: files.map(f=>f.name)});
    if(!res || res.ok === false || (res.error && !res.ok)){
      delete _sending[key];
      _draftLocal[key] = text;
      _sendNote[key] = _sendFailText(res, (chat || mailItem || {}).platform || (mailItem ? "email" : ""));
      rerender();
    }
  };
  side.append(send, save);
  // V2-819 (approved design, 2026-10-27): the clip sits BESIDE the text on the same row, and what he attaches waits
  // ABOVE the box — a picture as a thumbnail — before it is sent.
  main.append(att.btn, att.input, box, side);
  if(_sendNote[key]) wrap.appendChild(el("div","composeerr", _sendNote[key]));
  wrap.appendChild(att.row);
  wrap.appendChild(main);
  const c = data.composing;
  if(c && activeChat && c.platform === activeChat.platform && String(c.chatId) === String(activeChat.chatId))
    _playCompose(c, box, send);
  return wrap;
}

// SEEN BEING SENT (data.py `_composing`): a message he ordered by voice is typed into this box and the send button
// is pressed at the moment the engine releases the queued order. Nothing here sends — the order is already in the
// queue — so the button is only ever pressed for show, and a rerender mid-way simply picks the typing up again.
// The clock is the server's, re-anchored on each render (`elapsed_s`/`left_s`), so a skewed browser clock
// cannot make the press land before or after the real send.
function _playCompose(c, box, send){
  const text = String(c.text || "");
  const now0 = Date.now();
  const t0 = now0 - Number(c.elapsed_s || 0) * 1000;
  const t1 = now0 + Number(c.left_s || 0) * 1000;
  const typeEnd = t0 + Math.max(300, (t1 - t0) - 600);     // a beat with the text complete before the press
  box.readOnly = true;
  const done = () => {
    box.value = ""; box.readOnly = false;
    send.classList.remove("pressing"); send.classList.add("sent");
    send.textContent = tt("sent", null, "Enviado ✓"); send.disabled = true;
  };
  const tick = () => {
    if(!box.isConnected) return;
    const now = Date.now();
    if(now >= t1) return done();
    const f = Math.max(0, Math.min(1, (now - t0) / Math.max(1, typeEnd - t0)));
    box.value = text.slice(0, Math.round(f * text.length));
    send.disabled = !box.value.trim();
    send.classList.toggle("pressing", now >= t1 - 250);
    requestAnimationFrame(tick);
  };
  tick();
}

function messageActions(it, ctx){
  const acts = el("div","tacts");
  const read=iconButton("check",tt("mark_read", null, "Marcar como leído")); read.onclick=()=>ctx.action("read",{n:it.n});
  const dis=iconButton("close",tt("dismiss", null, "Descartar (no marcar leído)")); dis.onclick=()=>ctx.action("dismiss",{n:it.n});
  acts.append(read,dis);
  if(it.platform==="email"){
    // Email-only affordances (V2-543): they act on the REAL mailbox, which is the whole point of the widget
    // being a substitute — other platforms have no archive/delete API and get no fake buttons.
    const arc=iconButton("archive",tt("archive", null, "Archivar en tu buzón real"));
    arc.onclick=()=>{ markBusy(arc); ctx.action("archive",{n:it.n}); };
    const del=iconButton("trash",tt("trash", null, "Borrar en tu buzón real (pide confirmación)"));
    del.onclick=()=>ctx.action("trash",{n:it.n});
    acts.append(arc,del);
  }
  const mute=iconButton("mute",tt("mute_channel", null, "Silenciar este canal"));
  mute.onclick=()=>{ markBusy(mute); ctx.action("hide",{n:it.n}); };
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
  row.dataset.rowKey = key;
  const stack = el("div","tbstack");
  const bubble = el("div","tbubble"+(urgente && !outgoing?" urg":""));
  if(isGroup && !outgoing) bubble.appendChild(el("div","tbfrom", it.from!=null?it.from:"?"));

  const when = fmtWhen(it.ts);
  const media = mediaBlock(it, when);
  const bareLabel = media && isBareMediaLabel(it.body);
  const {title, rest: _rest} = splitBody(displayBody(it.body, it.mediaType));
  const rest = markupText(_rest);
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
    const more = el("span","more", expanded ? tt("show_less", null, "mostrar menos") : tt("show_more", null, "mostrar más"));
    more.onclick=()=>{ expanded ? _expanded.delete(key) : _expanded.add(key); rerender(); };
    bubble.appendChild(more);
  }
  if(when && !(media && media.usedWhen)) bubble.appendChild(el("span","tbwhen", when));
  if(media && media.usedWhen) bubble.classList.add("hasaudio");
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
  row.title = tt("open", null, "Abrir");
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
  const subj = (it.subject || "").trim() || displayBody(it.body, it.mediaType).split("\n")[0] || tt("no_subject", null, "(sin asunto)");
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
// ── READING A MAIL (V2-680) ───────────────────────────────────────────────────────────────────────────
// One letter, shaped like a mail client: subject, the envelope (who wrote it, who it went to, who was
// copied, when) and the body WHOLE. `full` says whether the body may be cut — it never may here; the
// argument exists so the preview shapes elsewhere keep their own behaviour.
//
// Everything is DERIVED from what the message actually carries. An address we do not have is a row that
// is not drawn, never an invented one and never an empty label: "Cc: —" states something false about the
// original mail, and the operator reads this pane to know who was on it.
function mailEnvelope(it, meta){
  const env = el("div","menv");
  const row = (k, node)=>{ env.appendChild(el("div","menvk", k)); env.appendChild(node); };
  const val = (text, addr)=>{
    const v = el("div","menvv", text);
    if(addr && addr !== text) v.appendChild(el("span","addr", " · " + addr));
    return v;
  };
  const outgoing = it.dir === "out";
  // The sender. On his OWN reply the thread stores our label, and the person it went TO is the
  // conversation itself — which is the only place that identity survives once the item is answered.
  const who = outgoing ? tt("you", null, "Tú") : (it.who || it.from || "?");
  row(tt("from", null, "De"), val(who, outgoing ? "" : (it.senderId || "")));
  const other = (meta && meta.chatId) || it.senderId || "";
  if(outgoing && other) row(tt("to", null, "Para"), val(other, ""));
  else if(!outgoing) row(tt("to", null, "Para"), val(tt("you", null, "Tú"), ""));
  const cc = (it.recipients || []).filter(a => typeof a === "string" && a.trim());
  if(cc.length) row(tt("cc", null, "Copia"), val(cc.join(", "), ""));
  const when = fmtWhen(it.ts);
  if(when) row(tt("date", null, "Fecha"), val(when, ""));
  return env;
}

// The connector folds the subject into the body as a leading "[Asunto: X]" line (mailbox.parse_message), so
// a screen that ALSO shows the subject in its own field prints it twice — visible in the very first render
// of this pane. Stripping it is exact and not a guess: that marker is ours, written by our own parser, and
// only the FIRST line is ever touched.
const _SUBJECT_MARKER = /^\s*\[Asunto:([^\]\n]*)\]\n?/;

function stripSubjectLine(text){
  return String(text == null ? "" : text).replace(_SUBJECT_MARKER, "");
}

function mailLetter(it, ctx, meta){
  const wrap = el("div","mltr"+(it.dir === "out" ? " out" : ""));
  const media = mediaBlock(it);
  const raw = displayBody(it.body, it.mediaType);
  const marked = _SUBJECT_MARKER.exec(raw);
  const {title, rest} = splitBody(stripSubjectLine(raw));
  // The stored subject wins; the marker line is the fallback for a message ingested before the field
  // existed, and a plain first-line title is the last resort for a body with neither.
  const subject = (it.subject || "").trim() || (marked ? marked[1].trim() : "") || title || "";
  if(subject) wrap.appendChild(el("div","mltrsubj", subject));
  wrap.appendChild(mailEnvelope(it, meta));
  if(!(media && isBareMediaLabel(it.body))){
    const body = el("div","mltrbody");
    // NO clamp and NO «mostrar más», at any length — his rule: «lo quiero todo entero». The pane around
    // this scrolls, which is what makes showing everything affordable.
    // `rest` is the body once splitBody has lifted the "[Asunto: X]" line off it; `title` is the fallback
    // for a message that is nothing BUT that line.
    linkify(body, markupText(rest || title));   // the «[Asunto]» line is lifted first, then the markup
    wrap.appendChild(body);
  }
  if(media) wrap.appendChild(media);
  if(it.dir !== "out" && it.n != null) wrap.appendChild(messageActions(it, ctx));
  return wrap;
}

function mailDetail(it, data, ctx, closeMail, rerender){
  const wrap = el("div","thread plat-email");
  const hd = el("div","thd");
  const back = el("button","back",tt("back_inbox", null, "← Bandeja")); back.onclick=()=>{ ctx.top(); closeMail(); };
  hd.appendChild(back);
  wrap.appendChild(hd);

  // V2-680 — the SAME letter shape the thread uses, inside the same bordered pane, so «open this mail»
  // and «open this conversation» are not two different-looking screens for the same act of reading.
  const pane = el("div","mdet mpane");
  pane.appendChild(mailLetter({...it, who: it.from}, ctx, {chatId: it.chatId}));
  wrap.appendChild(pane);

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
  if(n <= 48) return tt("last_f", null, "últimas ") + Math.round(n) + " h";
  return tt("last_m", null, "últimos ") + Math.round(n/24) + tt("_days", null, " días");
}

function criteriaBar(platform, crit, ctx, rerender){
  const bar = el("div","critbar");
  bar.appendChild(el("span","critlbl",tt("activity_", null, "Actividad · ") + fmtWindow(crit.window_h)));
  if(platform === "telegram" || platform === "email"){
    const fetchBtn = el("button","bt bt-ghost critfetch",tt("fetch_connector", null, "⟳ Traer del conector"));
    fetchBtn.title = tt("fetch_connector_hint", null, "Pedirle al conector las conversaciones con actividad en ese período");
    fetchBtn.onclick = ()=>{ fetchBtn.textContent = tt("fetch_asked", null, "⟳ Pedido…"); fetchBtn.disabled = true;
      ctx.action("fetch_now", {platform: platform, since_hours: crit.window_h}); };
    bar.appendChild(fetchBtn);
  }
  const off = el("button","critoff","✕");
  off.title = tt("clear_criteria", null, "Quitar el criterio (volver a la vista de pendientes)");
  off.onclick = ()=> ctx.action("show_view", {platform: platform, window_h: 0});
  bar.appendChild(off);
  return bar;
}

function activityList(rows, ctx){
  const wrap = el("div","tl");
  rows.forEach(c=>{
    const row = el("div","trow chatrow");
    row.title = tt("open_chat", null, "Abrir conversación");
    const lead = el("span","tlead");
    lead.style.background = c.unread ? "var(--hb-accent,#3D6FE0)" : "transparent";
    row.appendChild(lead);
    const main = el("div","tmain");
    const head = el("div","thead");
    head.appendChild(platformChip(c.platform));
    head.appendChild(el("span","tfrom", c.name));
    if(c.unread) head.appendChild(el("span","tcount", String(c.unread)));
    if(c.isGroup) head.appendChild(el("span","tpara",tt("group", null, "· grupo")));
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

const KIND_FILTERS = {
  whatsapp: ["all", "unread", "person", "group"],
  telegram: ["all", "unread", "person", "group", "channel"],
};

function chatRowMatches(r, kind, q){
  if(kind === "unread" && !(r.unread || r.pending)) return false;
  if(kind === "person" || kind === "group" || kind === "channel"){ if((r.kind || "person") !== kind) return false; }
  if(q){
    const hay = ((r.name || "") + " " + (r.preview || "")).toLowerCase();
    if(!hay.includes(q)) return false;
  }
  return true;
}

function platformChatRows(platform, rows, ctx){
  const wrap = el("div","tl");
  rows.forEach(c=>{
    const row = el("div","trow chatrow" + (c.archived ? " cxarch" : ""));
    row.title = tt("open_chat", null, "Abrir conversación");
    const lead = el("span","tlead");
    lead.style.background = c.urgent ? "var(--hb-risk,#e5484d)"
      : ((c.forMe || c.unread) ? "var(--hb-accent,#3D6FE0)" : "transparent");
    row.appendChild(lead);
    const main = el("div","tmain");
    const head = el("div","thead");
    if(c.photo && String(c.photo).match(/^(\/widgets\/|data:image\/)/)){
      const ph = document.createElement("img"); ph.className = "cxava"; ph.src = c.photo; ph.alt = ""; head.appendChild(ph);
    }
    head.appendChild(el("span","tfrom", c.name));
    const count = c.unread || c.pending || 0;
    if(count) head.appendChild(el("span","tcount", String(count)));
    if(c.kind === "group") head.appendChild(el("span","tpara", c.forum ? tt("forum", null, "· grupo con temas") : tt("group", null, "· grupo")));
    if(c.kind === "channel") head.appendChild(el("span","tpara", tt("channel", null, "· canal")));
    if(c.forMe) head.appendChild(el("span","tpara",tt("dot_for_you", null, "· para ti")));
    if(c.muted){ const m = el("span","cxtag"); m.appendChild(actionIcon("bellOff")); m.title = tt("muted_chat", null, "Silenciado"); head.appendChild(m); }
    if(c.archived) head.appendChild(el("span","cxtag",tt("archived", null, "archivado")));
    const when = fmtWhen(c.ts);
    if(when) head.appendChild(el("span","twhen", when));
    main.appendChild(head);
    const mine = c.fromMe ? tt("you_prefix", null, "Tú: ") : "";
    main.appendChild(el("div","tprev", mine + displayBody(c.preview, c.mediaType)));
    row.appendChild(main);
    row.onclick = ()=> { ctx.top(); ctx.action("open", {platform: platform, chatId: c.chatId}); };
    wrap.appendChild(row);
  });
  return wrap;
}

// «Nuevo chat» / «Nuevo grupo»: the same doors the voice uses (`send_to`, `create_group`), with the same
// resolution of who is who — an unknown or ambiguous name comes back as the action's own sentence, shown here.
function newForm(platform, mode, ctx, close){
  const f = el("div","newform");
  const err = el("div","newerr");
  const files = [];
  const name = document.createElement("input");
  const who = document.createElement("input");
  const text = document.createElement("textarea"); text.rows = 3;
  if(mode === "group"){
    name.placeholder = tt("group_name", null, "Nombre del grupo");
    who.placeholder = tt("group_members", null, "Personas (separadas por comas)");
    text.placeholder = tt("group_first", null, "Primer mensaje (opcional)");
    f.append(name, who, text);
  } else {
    who.placeholder = tt("new_to", null, "Para: nombre del contacto");
    text.placeholder = tt("new_text", null, "Mensaje");
    f.append(who, text);
  }
  const att = attachControls(ctx, files, ()=>{});
  const go = el("button","bt bt-primary", mode === "group" ? tt("group_create", null, "Crear grupo") : tt("send", null, "Enviar ➤"));
  const cancel = el("button","bt", tt("cancel", null, "Cancelar"));
  cancel.onclick = close;
  go.onclick = async ()=>{
    err.textContent = ""; go.disabled = true;
    const names = files.map(x=>x.name);
    const res = mode === "group"
      ? await ctx.action("create_group", {platform, name: name.value.trim(),
          members: who.value.split(",").map(x=>x.trim()).filter(Boolean), text: text.value.trim(), files: names})
      : await ctx.action("send_to", {contact: who.value.trim(), channel: platform, text: text.value.trim(), files: names});
    go.disabled = false;
    if(res && res.ok === false){ err.textContent = res.message || res.error || tt("new_failed", null, "No se ha podido"); return; }
    close();
  };
  const row = el("div","row"); row.append(err, att.btn, att.input, cancel, go);
  f.append(att.row, row);
  return f;
}

// The first screen of a platform, like its own app: the conversations, not only what is unread.
function platformChats(platform, v, ctx){
  const box = el("div","cxwrap");
  const nb = el("div","cxnew");
  const formSlot = el("div");
  const openForm = (mode)=>{
    _newForm[platform] = _newForm[platform] === mode ? null : mode;
    formSlot.replaceChildren();
    if(_newForm[platform]) formSlot.appendChild(newForm(platform, mode, ctx, ()=>{ _newForm[platform] = null; formSlot.replaceChildren(); }));
  };
  const iconBtn = (icon, label)=>{ const b = el("button","bt cxnewbt"); b.append(actionIcon(icon), el("span", null, label)); return b; };
  const nc = iconBtn("pencil", tt("new_chat", null, "Nuevo chat")); nc.onclick = ()=> openForm("chat");
  const ng = iconBtn("users", tt("new_group", null, "Nuevo grupo")); ng.onclick = ()=> openForm("group");
  nb.append(nc, ng);
  box.append(nb, formSlot);
  if(_newForm[platform]) formSlot.appendChild(newForm(platform, _newForm[platform], ctx, ()=>{ _newForm[platform] = null; formSlot.replaceChildren(); }));
  const bar = el("div","cxbar");
  const chips = el("div","cxchips");
  const kind = _chatKind[platform] || "all";
  const labels = {all: tt("kind_all", null, "Todos"), unread: tt("kind_unread", null, "No leídos"),
                  person: tt("kind_person", null, "Personas"), group: tt("kind_group", null, "Grupos"),
                  channel: tt("kind_channel", null, "Canales")};
  const listBox = el("div","cxlist");
  const fill = ()=>{
    const k = _chatKind[platform] || "all";
    const q = (_chatQuery[platform] || "").trim().toLowerCase();
    const rows = (v.rows || []).filter(r=> chatRowMatches(r, k, q));
    listBox.replaceChildren();
    if(rows.length) listBox.appendChild(platformChatRows(platform, rows, ctx));
    else if(v.loading || !v.asked) listBox.appendChild(el("div","empty",tt("chats_loading", null, "Cargando tus chats…")));
    else listBox.appendChild(el("div","empty", (q || k !== "all")
      ? tt("chats_none_match", null, "Ningún chat de los cargados coincide")
      : tt("chats_none", null, "No hay chats todavía")));
  };
  (KIND_FILTERS[platform] || KIND_FILTERS.whatsapp).forEach(k=>{
    const b = el("button","cxchip" + (k === kind ? " on" : ""), labels[k]);
    b.onclick = ()=>{ _chatKind[platform] = k; chips.querySelectorAll(".cxchip").forEach(x=>x.classList.remove("on"));
      b.classList.add("on"); fill(); };
    chips.appendChild(b);
  });
  bar.appendChild(chips);
  const search = el("input","cxsearch");
  search.type = "search";
  search.placeholder = tt("chats_search", null, "Buscar un chat");
  search.value = _chatQuery[platform] || "";
  search.dataset.keep = "chatsearch:" + platform;
  search.oninput = ()=>{ _chatQuery[platform] = search.value; fill(); };
  bar.appendChild(search);
  box.appendChild(bar);
  box.appendChild(listBox);
  fill();
  if(v.error) box.appendChild(el("div","cxnote", tt("chats_error", null, "La app no me ha dado más chats: ") + v.error));
  if(v.more){
    const more = el("button","bt bt-ghost cxmore", v.loading ? tt("chats_loading_more", null, "Cargando…") : tt("chats_more", null, "Cargar más"));
    more.disabled = !!v.loading;
    more.onclick = ()=>{ more.disabled = true; more.textContent = tt("chats_loading_more", null, "Cargando…");
      ctx.action("chats_more", {platform: platform}); };
    box.appendChild(more);
  } else if((v.rows || []).length){
    box.appendChild(el("div","cxnote", platform === "whatsapp"
      ? tt("chats_end_whatsapp", null, "Son todos los chats que WhatsApp ha pasado a este dispositivo")
      : tt("chats_end", null, "No hay más chats")));
  }
  return box;
}

function chatList(chats, ctx){
  const wrap = el("div","tl");
  chats.forEach(c=>{
    const row = el("div","trow chatrow");
    row.title = tt("open_chat", null, "Abrir conversación");
    const lead = el("span","tlead");
    lead.style.background = c.urgencia === "alta" ? "var(--hb-risk,#e5484d)"
      : (c.dirigido_a_mi ? "var(--hb-accent,#3D6FE0)" : "transparent");
    row.appendChild(lead);

    const main = el("div","tmain");
    const head = el("div","thead");
    head.appendChild(platformChip(c.platform));
    head.appendChild(el("span","tfrom", c.name));
    if(c.count > 1) head.appendChild(el("span","tcount", String(c.count)));
    if(c.dirigido_a_mi) head.appendChild(el("span","tpara",tt("dot_for_you", null, "· para ti")));
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
    const read=iconButton("check",tt("read_whole_chat", null, "Marcar todo el chat como leído"));
    read.onclick=(ev)=>{ ev.stopPropagation(); ctx.action("readchat",{n:c.n}); };
    const mute=iconButton("mute",tt("mute_channel", null, "Silenciar este canal"));
    mute.onclick=(ev)=>{ ev.stopPropagation(); markBusy(mute); ctx.action("hide",{n:c.n}); };
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
    box.appendChild(el("span","tsl",tt("chat_start", null, "· principio de la conversación ·")));
    return box;
  }
  box.appendChild(el("span","tsl",tt("stored_start", null, "· aquí empieza lo que tengo guardado ·")));
  if(meta && meta.can_load_more){
    const b = el("button","tsbtn",tt("load_older", null, "Cargar anteriores"));
    b.onclick=()=>{ b.disabled=true; b.textContent=tt("loading_older", null, "Pidiéndolos…"); ctx.action("load_more",{}); };
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
  // V2-819 — a one-to-one chat is named by the server's ONE resolver (`names.py`: his contact first, then the
  // platform's own display name), so the header says what the list says; a group keeps its subject.
  const resolved = meta && !meta.isGroup ? meta.name : "";
  const name = resolved || (inbound.find(it=>it.group)||{}).group || (inbound.find(it=>it.from)||{}).from
    || (PLAT[active.platform]||{}).label || tt("chat", null, "Chat");
  if(meta && meta.photo && String(meta.photo).match(/^(\/widgets\/|data:image\/)/)){
    const ph = document.createElement("img"); ph.className = "cxava"; ph.src = meta.photo; ph.alt = ""; hd.appendChild(ph);
  }
  hd.appendChild(el("b","thdname", name));
  // V2-616 F2/F3 — the operator: the name goes on the LEFT, "volver" moves to the far RIGHT as a real
  // button, never a bare underlined link (`margin-left:auto` on the LAST child, same pattern the connectors
  // list already used). And it resets the outer scroller (ctx.top()) — this IS a screen change (thread ->
  // chat list), and skipping it is the same stale-scrollTop bug the "open" click just below it fixes.
  const back = el("button","back",tt("back", null, "← Volver"));
  back.onclick=()=>{ ctx.top(); ctx.action("close"); };
  hd.appendChild(back);
  wrap.appendChild(hd);

  wrap.appendChild(threadStart(meta, ctx));
  const isGroup = !!(meta && meta.isGroup);
  // V2-680 — EMAIL is read like a mail client, not like a chat. A bubble timeline is the right shape for
  // WhatsApp and Telegram (short turns, one line each) and the wrong one for a letter: it clamped a
  // three-page mail to three lines behind a «mostrar más», hid the subject, showed neither the recipients
  // nor who was copied, and put an urgency stripe down the side of the one thing he had opened on purpose.
  const list = el("div","tl" + (active.platform === "email" ? " mpane" : ""));
  // V2-819 — this scroller is THIS conversation's: a repaint keeps him where he was in it, and a chat (not a mail,
  // whose latest letter is read from its top) opens on its latest message, the way every messaging app does.
  list.dataset.scrollKey = "thread:" + active.platform + ":" + active.chatId;
  if(active.platform !== "email") list.dataset.open = "bottom";
  if(active.platform === "email"){
    const who = {chatId: active.chatId};
    items.forEach(it=> list.appendChild(mailLetter(it, ctx, who)));
  } else {
    items.forEach(it=> list.appendChild(messageRow(it, ctx, rerender, isGroup)));
  }
  wrap.appendChild(list);
  // V2-611 — reply to the CONVERSATION, not a specific past message: `{}` lets the server resolve the
  // target from `active_chat` itself (`_resolve_target`), which is what «responderle» means for a thread.
  wrap.appendChild(composeBar(ctx, data, {}, active, rerender));
  return wrap;
}

// Loader + human-readable connection state.
// Nothing connected yet: the card says so and offers each channel — linking one is the ⚙ Conectores
// section's job (2026-10-04), the same place «conecta mi WhatsApp» opens by voice.
function connectPrompt(platforms, ctx){
  const box=el("div","wiz");
  box.appendChild(el("div","wbody",tt("connect_prompt", null, "Conecta un canal para ver aquí tus mensajes.")));
  box.appendChild(iconGrid(ORDER.map(pl=>({key:pl, icon:brandIcon(pl, false), label:(PLAT[pl]||{}).label||pl,
    onClick:()=>ctx.openConnector(pl)}))));
  return box;
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
let _T = null, _LANG = "en";   // instance language (ctx.lang) — dates never follow the browser locale
// V2-800 — a NEW message held for his word, and a send scheduled for later, are ROWS of this card: each one shown
// once, here, with the one control it needs. A held draft opens no conversation (there is none yet), so without
// this strip «ya está escrito, revísalo» pointed at nothing he could see.
function pendingStrip(data, ctx){
  const held = Object.values(data.drafts || {}).filter(d => d && d.target && d.target.new);
  const later = (data.sent || []).filter(r => r && r.scheduled_for);
  if(!held.length && !later.length) return null;
  const box = el("div","pending");
  // A held draft is one line that opens its own screen (V2-807 T-02): the draft has ONE face, and it is never its
  // body painted over a list.
  held.forEach(d => {
    const t = d.target || {};
    const row = el("div","prow");
    row.append(el("b",null,tt("held_to", {to: t.name || t.to}, `Borrador para ${t.name || t.to}`)));
    const open = el("button","bt",tt("open_draft", null, "Abrir"));
    open.onclick = () => { markBusy(open); ctx.action("open_draft", {key: d.key}); };
    row.append(open);
    box.append(row);
  });
  later.forEach(r => {
    const row = el("div","prow");
    const when = new Date(Number(r.scheduled_for) * 1000).toLocaleString(_LANG, {weekday:"short", hour:"2-digit", minute:"2-digit"});
    row.append(el("b",null,tt("scheduled_to", {to: r.name, when}, `Programado · ${r.name} · ${when}`)));
    row.append(el("div","pbody",String(r.body || "")));
    const cancel = el("button","bt",tt("cancel_send", null, "Cancelar envío"));
    cancel.onclick = () => { markBusy(cancel); ctx.action("cancel_send", {ref: r.id}); };
    row.append(cancel);
    box.append(row);
  });
  return box;
}

// ── THE EMAIL SECTION, A MAIL CLIENT (mailbox.py) ─────────────────────────────────────────────────────────
// The operator, 2026-10-26: the home holds only what is addressed to him; the mail section is his mailbox —
// the Inbox first, every folder the account syncs, a draft opened over the whole card with everything needed
// to finish it, and a way back one level at a time. Gmail is the reference. All of it is SERVER state
// (`data.mailbox`), so a tap and a voice order land on the same screen; a tap repaints from the action's own
// answer instead of waiting for the store's notice.
const FOLDER_FB = {inbox:"Recibidos", flagged:"Destacados", drafts:"Borradores", sent:"Enviados",
                   archive:"Archivo", all:"Todos", junk:"Spam", trash:"Papelera"};
let _newMail = null;      // a message being written that is not a draft yet (Redactar / Responder): {to, subject, text}

function folderLabel(f){
  // A role this card has no word for keeps the server's own name — an empty row in the rail is worse than English.
  return f && f.role ? tt("folder_"+f.role, null, FOLDER_FB[f.role] || f.label || "") : ((f && f.label) || "");
}

function mailAct(ctx, data, rerender){
  return (name, payload) => Promise.resolve(ctx.action(name, payload)).then(r => {
    if(r && r.mailbox){ Object.assign(data, r); rerender(); }
    return r;
  });
}

function mailDrafts(data){
  return Object.values(data.drafts || {}).filter(d => d && d.target && (d.target.platform || "email") === "email")
    .sort((a, b) => (b.at || 0) - (a.at || 0));
}

function mailFolderList(mb){
  const folders = (mb.folders && mb.folders.length) ? mb.folders.slice() : [{name:"INBOX", role:"inbox", label:"INBOX"}];
  // The card's own drafts always have a home, even on a server that names no Drafts folder.
  if(!folders.some(f => f.role === "drafts")) folders.splice(1, 0, {name:"@drafts", role:"drafts", label:""});
  return folders;
}

// Navigation bar of every mail screen: Home › Correo › <folder> [› <what is open>] and «← <folder>» on the right.
function mailCrumb(mb, ctx, act, current){
  const bar = el("div","thd mcrumb");
  const home = iconButton("home", tt("home", null, "Inicio"), "mchome");
  home.onclick = () => { selectPlatform(null); ctx.top && ctx.top(); act("show_view", {platform:"all"}); };
  bar.appendChild(home);
  // One level up is the list this screen was opened from: a draft's own `back_to`, else the list on screen.
  const up = mailWhere(mb.draft && mb.back_to ? {...mb, ...mb.back_to} : mb);
  const parts = [[tt("mail_section", null, "Correo"), () => act("mail_folder", {folder:"inbox"})],
                 [up, current ? () => act("mail_back", {}) : null]];
  if(current) parts.push([current, null]);
  parts.forEach(([label, go], i) => {
    if(i) bar.appendChild(el("span","msep","›"));
    const c = el(go ? "button" : "b", go ? "mcr" : "mcr cur", label);
    if(go) c.onclick = go;
    bar.appendChild(c);
  });
  if(current){
    const back = el("button","back", "← " + up);
    back.onclick = () => act("mail_back", {});
    bar.appendChild(back);
  }
  return bar;
}

// The provider's categories of the Inbox, named in his language; a key no bundle names shows as the provider sent it.
const CAT_FB = {primary:"Principal", social:"Social", promotions:"Promociones", updates:"Notificaciones", forums:"Foros"};
const CAT_ICON = {primary:"inbox", social:"users", promotions:"tag", updates:"info", forums:"chat"};
const ROLE_ICON = {inbox:"inbox", flagged:"star", drafts:"file", sent:"send", archive:"archive", all:"mail",
                   junk:"alert", trash:"trash"};
// Where unread is noise (what he sent, his drafts, the bin, «all mail»), no figure is shown — as Gmail does.
const NO_COUNT = new Set(["sent", "drafts", "trash", "all", "flagged", "archive"]);
let _railOpen = false;    // the drawer, on a card too narrow for the rail

function catLabel(key){ return tt("cat_" + key, null, CAT_FB[key] || key); }

// Where he is inside the mail section, in one name: the category of the Inbox, or the folder.
function mailWhere(mb){
  if(String(mb.folder).toUpperCase() === "INBOX" && mb.category) return catLabel(mb.category);
  return folderLabel(mailFolderList(mb).find(f => f.name === mb.folder) || {role:"inbox"});
}

function railEntry(icon, label, n, on, go, cls, rerender){
  const b = el("button", "mnav" + (on ? " on" : "") + (cls ? " " + cls : ""));
  b.type = "button"; b.title = label;
  b.setAttribute("aria-label", n ? `${label} (${n})` : label);
  if(on) b.setAttribute("aria-current", "page");
  b.append(actionIcon(icon), el("span", "mnl", label));
  if(n) b.appendChild(el("span", "mfn", String(n)));      // the provider's real number, never rounded
  // A tap in the drawer closes it at once; the list follows when the action answers.
  b.onclick = () => { const was = _railOpen; _railOpen = false; go(); if(was && rerender) rerender(); };
  return b;
}

// ONE left rail (V2-807 T-01, the operator's design): Compose; the Inbox and, under it, every category the provider
// sorts it by; then every other folder the server declares. Each with the PROVIDER's unread figure — an Inbox that
// is sorted counts its first category, the way Gmail's own badge does.
function mailRail(mb, data, ctx, act, rerender){
  const rail = el("nav", "mrail");
  rail.setAttribute("aria-label", tt("mail_section", null, "Correo"));
  const compose = el("button", "bt bt-primary mcompose");
  compose.title = tt("compose", null, "Redactar");
  compose.append(actionIcon("pen"), el("span", "mnl", tt("compose", null, "Redactar")));
  compose.onclick = () => { _railOpen = false; _newMail = {to:"", subject:"", text:""}; rerender(); };
  rail.appendChild(compose);
  const counts = mb.counts || {};
  const cats = mb.categories || [];
  const inInbox = String(mb.folder).toUpperCase() === "INBOX";
  const drafts = mailDrafts(data).length;
  mailFolderList(mb).forEach((f, i) => {
    const label = folderLabel(f);
    if(f.role === "inbox"){
      const n = cats.length ? (cats[0].unread || 0) : (counts[f.name] || 0);
      rail.appendChild(railEntry("inbox", label, n, inInbox && !cats.length, () => act("mail_folder", {folder: f.name}),
                                 "", rerender));
      cats.forEach(c => rail.appendChild(railEntry(CAT_ICON[c.key] || "tag", catLabel(c.key), c.unread || 0,
        inInbox && mb.category === c.key, () => act("mail_folder", {folder: f.name, category: c.key}), "sub", rerender)));
      return;
    }
    if(i && !f.role && (mailFolderList(mb)[i - 1] || {}).role) rail.appendChild(el("div", "mrailsep"));
    const n = f.role === "drafts" ? drafts : (NO_COUNT.has(f.role) ? 0 : (counts[f.name] || 0));
    rail.appendChild(railEntry(ROLE_ICON[f.role] || "tag", label, n, f.name === mb.folder,
                               () => act("mail_folder", {folder: f.name}), "", rerender));
  });
  // His criteria over the categories (V2-807 T-03): rows of his rules, in his words, each removable here too.
  const mine = mb.rules || [];
  if(mine.length){
    const box = el("div", "mrules");
    box.appendChild(el("div", "mruleshd", tt("mail_rules", null, "Tus criterios")));
    mine.forEach(r => {
      const row = el("div", "mrule");
      row.appendChild(el("span", "mrulet", r.text));
      const x = iconButton("close", tt("rule_forget", null, "Quitar este criterio"), "mrulex");
      x.onclick = () => { markBusy(x); act("mail_sort", {forget: r.id}); };
      row.appendChild(x);
      box.appendChild(row);
    });
    rail.appendChild(box);
  }
  return rail;
}

function folderRow(r, mb, act){
  const row = el("div","mrow" + (r.seen ? " seen" : " unseen"));
  const lead = el("span","tlead");
  if(!r.seen) lead.style.background = "var(--hb-accent,#3D6FE0)";
  row.appendChild(lead);
  const main = el("div","mmain");
  const line1 = el("div","mline1");
  const sent = mb.role === "sent" || mb.role === "drafts";
  line1.appendChild(el("span","mfrom", sent ? (tt("to", null, "Para") + ": " + (r.to || "?")) : (r.fromName || r.from || "?")));
  if(r.pending) line1.appendChild(el("span","mtag", tt("for_you", null, "para ti")));
  const when = fmtWhen(r.ts);
  if(when) line1.appendChild(el("span","mwhen", when));
  main.appendChild(line1);
  main.appendChild(el("div","msubj", (r.subject || "").trim() || tt("no_subject", null, "(sin asunto)")));
  row.appendChild(main);
  row.onclick = () => act("mail_open", {uid: r.uid, folder: mb.folder});
  return row;
}

function draftRow(d, act){
  const t = d.target || {};
  const row = el("div","mrow mdraftrow");
  row.appendChild(el("span","tlead"));
  const main = el("div","mmain");
  const line1 = el("div","mline1");
  line1.appendChild(el("span","mdtag", tt("draft_tag", null, "Borrador")));
  line1.appendChild(el("span","mfrom", t.name || t.to || t.chatId || "?"));
  const when = fmtWhen(d.at);
  if(when) line1.appendChild(el("span","mwhen", when));
  main.appendChild(line1);
  const subj = (t.subject || "").trim();
  main.appendChild(el("div","msubj", (subj ? subj + " — " : "") + String(d.text || "").replace(/\s+/g, " ")));
  row.appendChild(main);
  row.onclick = () => act("open_draft", {key: d.key});
  return row;
}

// A draft has ONE face — its own screen (V2-807 T-02). On any other list it is one line that opens it: never its
// body, never a Send button. Several drafts point at the Drafts entry instead.
function draftPointer(mb, data, act){
  const mine = mailDrafts(data);
  if(!mine.length || mb.role === "drafts") return null;
  const t = mine[0].target || {};
  const one = mine.length === 1;
  const b = el("button","mdptr");
  b.type = "button";
  b.append(actionIcon("pen"), el("span", "mdptrt", one
    ? tt("held_to", {to: t.name || t.to}, `Borrador para ${t.name || t.to}`)
    : tt("n_drafts", {n: mine.length}, `${mine.length} borradores a medias`)),
    el("span", "mdptro", tt("open_draft", null, "Abrir")));
  b.onclick = () => one ? act("open_draft", {key: mine[0].key}) : act("mail_folder", {folder: "drafts"});
  return b;
}

function mailList(mb, data, ctx, act){
  const wrap = el("div","tl mlist");
  const ptr = draftPointer(mb, data, act);
  if(ptr) wrap.appendChild(ptr);
  if(mb.role === "drafts"){
    const mine = mailDrafts(data);
    mine.forEach(d => wrap.appendChild(draftRow(d, act)));
    const later = (data.sent || []).filter(r => r && r.scheduled_for && r.platform === "email");
    if(later.length){
      const ps = pendingStrip({drafts:{}, sent: later}, ctx);
      if(ps) wrap.appendChild(ps);
    }
    if(mb.folder === "@drafts"){
      if(!mine.length && !later.length) wrap.appendChild(el("div","empty", tt("no_drafts", null, "No hay borradores")));
      return wrap;
    }
    if(mine.length && mb.rows.length) wrap.appendChild(el("div","mgroup", tt("in_mailbox", null, "En tu buzón")));
  }
  mb.rows.forEach(r => wrap.appendChild(folderRow(r, mb, act)));
  if(!mb.rows.length && !(mb.role === "drafts" && mailDrafts(data).length)){
    wrap.appendChild(el("div","empty", mb.loading || !mb.asked ? tt("loading", null, "Cargando…")
      : (mb.error ? tt("folder_error", null, "No he podido leer esta carpeta del buzón.")
                  : tt("folder_empty", null, "Esta carpeta está vacía"))));
  }
  if(mb.more || (mb.loading && mb.rows.length)){
    const more = el("button","bt bt-ghost mmore", mb.loading ? tt("loading", null, "Cargando…") : tt("load_more", null, "Cargar más"));
    more.disabled = !!mb.loading;
    more.onclick = () => { markBusy(more); act("mail_more", {}); };
    wrap.appendChild(more);
  }
  return wrap;
}

// One message of a folder, the whole card. A mail the home also holds is the SAME screen it always was
// (reply, archive, mark unread…); anything else is read from the mailbox and answered with «Responder».
function mailMessage(mb, data, ctx, act, rerender){
  const o = mb.open || {};
  const item = String(mb.folder).toUpperCase() === "INBOX"
    ? (data.items || []).find(it => it.platform === "email" && String(it.messageId) === String(o.uid)) : null;
  const m = o.msg || {};
  const subject = (item ? item.subject : m.subject) || tt("no_subject", null, "(sin asunto)");
  const wrap = el("div","thread plat-email");
  wrap.appendChild(mailCrumb(mb, ctx, act, subject));
  if(item){
    const d = mailDetail(item, data, ctx, () => act("mail_back", {}), rerender);
    d.querySelector(".thd") && d.querySelector(".thd").remove();
    while(d.firstChild) wrap.appendChild(d.firstChild);
    return wrap;
  }
  const pane = el("div","mdet mpane");
  if(!o.msg){
    pane.appendChild(el("div","empty", o.loading ? tt("loading", null, "Cargando…") : tt("mail_unreadable", null, "No he podido abrir este correo.")));
  } else if(m.error){
    pane.appendChild(el("div","empty", tt("mail_unreadable", null, "No he podido abrir este correo.")));
  } else {
    const ltr = el("div","mltr");
    ltr.appendChild(el("div","mltrsubj", subject));
    const env = el("div","menv");
    const row = (k, v) => { if(v){ env.appendChild(el("div","menvk", k)); env.appendChild(el("div","menvv", v)); } };
    row(tt("from", null, "De"), m.fromName && m.fromName !== m.from ? `${m.fromName} · ${m.from}` : m.from);
    row(tt("to", null, "Para"), m.to);
    row(tt("cc", null, "Copia"), m.cc);
    row(tt("date", null, "Fecha"), fmtWhen(m.ts));
    ltr.appendChild(env);
    const body = el("div","mltrbody");
    linkify(body, markupText(m.body || ""));
    ltr.appendChild(body);
    pane.appendChild(ltr);
  }
  wrap.appendChild(pane);
  if(o.msg && !m.error && mb.role !== "sent" && mb.role !== "drafts"){
    const foot = el("div","dfoot");
    const reply = el("button","bt bt-primary", tt("reply", null, "Responder"));
    reply.onclick = () => {
      const subj = String(m.subject || "");
      _newMail = {to: m.from || "", subject: /^re:/i.test(subj) ? subj : (subj ? "Re: " + subj : ""), text: ""};
      rerender();
    };
    foot.appendChild(reply);
    wrap.appendChild(foot);
  }
  return wrap;
}

// A DRAFT over the whole card: recipient, subject, text, and Send · Save · Discard. `d` is one of the card's
// drafts (`data.drafts[key]`) or, for a message not saved yet, `_newMail`.
function draftEditor(d, key, mb, data, ctx, act, rerender){
  const t = (d && d.target) || {};
  const fresh = !key;
  const isNew = fresh || !!t.new;
  const email = fresh || (t.platform || "email") === "email";
  const wrap = el("div","thread plat-" + (t.platform || "email") + " mdraft");
  const title = fresh ? tt("new_mail", null, "Nuevo correo") : tt("draft_tag", null, "Borrador");
  const leave = () => { if(fresh){ _newMail = null; rerender(); } else act("mail_back", {}); };
  if(email) wrap.appendChild(mailCrumb(mb, ctx, act, title));
  else {
    const hd = el("div","thd");
    hd.appendChild(el("b","thdname", title + " · " + ((PLAT[t.platform] || {}).label || t.platform)));
    const back = el("button","back", tt("back", null, "← Volver")); back.onclick = leave;
    hd.appendChild(back);
    wrap.appendChild(hd);
  }
  if(fresh){   // the crumb's «←» goes one level up: for a message not saved yet that is simply closing it
    const b = wrap.querySelector(".mcrumb .back"); if(b) b.onclick = leave;
  }
  const pane = el("div","mdet mpane mdform");
  const field = (label, node) => { const f = el("label","mdf"); f.appendChild(el("span","mdk", label)); f.appendChild(node); pane.appendChild(f); return node; };
  const toIn = field(tt("to", null, "Para"), el("input","mdin"));
  // A new message's recipient is editable (re-resolved on save); a reply goes where the conversation is.
  toIn.value = fresh ? (d.to || "") : isNew ? (t.to || t.name || "")
    : (t.name && t.senderId && t.name !== t.senderId ? `${t.name} <${t.senderId}>` : (t.senderId || t.chatId || t.name || ""));
  toIn.readOnly = !isNew;
  let subjIn = null;
  if(email){
    subjIn = field(tt("subject", null, "Asunto"), el("input","mdin"));
    subjIn.value = fresh ? (d.subject || "") : (t.subject || "");
    subjIn.readOnly = !isNew;
  }
  const box = el("textarea","mdbody");
  box.value = d.text || "";
  // V2-819 — the focused field keeps focus and caret through a repaint; a saved draft's fields have no buffer of
  // their own (a new one has `_newMail`), so theirs keep the typed value too.
  const tag = "draft:" + (key || "new") + ":";
  [[toIn, "to"], [subjIn, "subject"], [box, "body"]].forEach(([n, f]) => { if(!n) return;
    n.dataset.keep = tag + f; if(!fresh) n.dataset.keepValue = "1"; });
  box.placeholder = tt("draft_ph", null, "Escribe el mensaje…");
  pane.appendChild(box);
  if(!fresh && (d.files || []).length) pane.appendChild(el("div","mdfiles", "📎 " + d.files.join(", ")));
  wrap.appendChild(pane);
  // Every button is ONE order, and the outcome comes back through the state (`mb.note`): this card's taps are
  // queued to its owner and answered with nothing, so a screen that waited for the answer waited forever.
  const note = el("span","mdnote", noteText(mb.note));
  const values = () => ({text: box.value, ...(isNew ? {to: toIn.value.trim()} : {}),
                         ...(subjIn && isNew ? {subject: subjIn.value} : {})});
  if(fresh){   // what he types survives the repaints that arrive while the order is on its way
    const keepTyped = () => Object.assign(_newMail, {to: toIn.value, subject: subjIn ? subjIn.value : "", text: box.value});
    [toIn, subjIn, box].forEach(n => n && n.addEventListener("input", keepTyped));
  }
  const order = (send, btn) => {
    if(!box.value.trim()){ note.textContent = tt("empty_draft", null, "El mensaje está vacío"); return; }
    if(isNew && !toIn.value.trim()){ note.textContent = tt("no_recipient", null, "Falta el destinatario"); return; }
    markBusy(btn);
    note.textContent = send ? tt("sending", null, "Enviando…") : tt("saving", null, "Guardando…");
    if(fresh) _newMail.pending = Date.now();
    if(!send && !fresh) act("save_draft", {key, ...values()});
    else act("compose", {...(fresh ? {channel: "email"} : {key}), ...values(), ...(send ? {send: true} : {})});
  };
  const foot = el("div","dfoot");
  const send = el("button","bt bt-primary", tt("send", null, "Enviar"));
  send.onclick = () => order(true, send);
  const save = el("button","bt bt-ghost", tt("save_draft", null, "Guardar borrador"));
  save.onclick = () => order(false, save);
  const discard = el("button","bt bt-ghost mddel", tt("discard", null, "Descartar"));
  discard.onclick = () => { if(fresh) leave(); else { markBusy(discard); act("discard_draft", {key}); } };
  foot.append(send, save, discard, note);
  wrap.appendChild(foot);
  return wrap;
}

// The last outcome of the draft screen, said in his language: saved, sent, or why not.
function noteText(n){
  if(!n || !n.key) return "";
  const fb = {saved:"Guardado ✓", sent:"Enviado ✓", not_saved:"No se ha guardado", not_sent:"No se ha enviado"};
  const head = tt(n.key === "sent" ? "sent_ok" : n.key, null, fb[n.key] || "");
  return n.text && /^not_/.test(n.key) ? `${head}: ${n.text}` : head;
}

function mailClient(data, ctx, rerender){
  const mb = data.mailbox || {folders:[], folder:"INBOX", role:"inbox", rows:[]};
  const act = mailAct(ctx, data, rerender);
  const box = el("div","mclient");
  const grid = el("div","mcgrid" + (_railOpen ? " open" : ""));
  const pane = el("div","mpanel");
  // On a card too narrow for the rail, this button names where he is and opens the rail as a drawer.
  const drawer = el("button","mdrawerbtn");
  drawer.type = "button";
  drawer.setAttribute("aria-expanded", _railOpen ? "true" : "false");
  drawer.append(actionIcon("menu"), el("span", null, mailWhere(mb)));
  drawer.onclick = () => { _railOpen = !_railOpen; rerender(); };
  pane.appendChild(drawer);
  grid.append(mailRail(mb, data, ctx, act, rerender), pane);
  box.appendChild(grid);
  const its = (data.items || []).filter(it => it.platform === "email");
  if(mb.role === "inbox" && !mb.category && !(mb.rows || []).length && its.length){
    // The Inbox page has not arrived (or the mailbox could not be listed): the mail the card already holds IS
    // Inbox mail, shown at once instead of an empty box — and said, when the mailbox failed. Not on a category:
    // the held mail is every category mixed, the very thing a category view exists to separate.
    if(mb.error) pane.appendChild(el("div","mnote", tt("folder_error", null, "No he podido leer esta carpeta del buzón.")));
    pane.appendChild(emailList(its, ctx, n => { _openMail = n; rerender(); }));
    return box;
  }
  if(mb.note && mb.note.key === "sent") pane.appendChild(el("div","mnote", noteText(mb.note)));
  pane.appendChild(mailList(mb, data, ctx, act));
  return box;
}

function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.mensajeria."+key, params); if(s && s!=="widgets.mensajeria."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

// ── WHERE HE IS survives a repaint (V2-819) ─────────────────────────────────────────────────────────────────
// The host repaints this card on EVERY store write (desktop.js `refreshData`), and this card writes the store
// itself while he types: the composer's autosave (`draft`, half a second after the last key). Each repaint rebuilt
// the card from nothing, so the thread's list came back scrolled to its top and the box he was typing in lost its
// focus — measured by the operator in a WhatsApp chat: he scrolled to the latest message, started writing, and
// the conversation jumped up under his hands. The class is «a repaint moves him», so it is fixed at the one door
// every repaint goes through, not in the composer:
//   · a scroller says what it is (`data-scroll-key`) and how it OPENS (`data-open="bottom"`: a chat opens on its
//     latest message); a repaint of the SAME scroller keeps him where he was — on the bottom if he was there
//     (new messages then stay in view), else on the same row (`data-row-key`) at the same offset;
//   · a text field that should keep its focus says so (`data-keep`): the focused one gets focus and caret back.
//     Its VALUE is each field's own buffer's job (`_draftLocal`, `_chatQuery`, `_newMail`), never restored here —
//     except where a field has no buffer of its own (`data-keep-value`).
const _PIN_PX = 24;

function _captureWhere(root){
  const w = {focus: null, scroll: {}};
  try{
    const a = document.activeElement;
    if(a && root.contains(a) && a.dataset && a.dataset.keep){
      w.focus = {key: a.dataset.keep, s: a.selectionStart, e: a.selectionEnd, top: a.scrollTop,
                  value: a.dataset.keepValue != null ? a.value : null};
    }
    root.querySelectorAll("[data-scroll-key]").forEach(sc => {
      const atBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight <= _PIN_PX;
      let anchor = null;
      if(!atBottom){
        const top = sc.getBoundingClientRect().top;
        for(const r of sc.querySelectorAll("[data-row-key]")){
          const b = r.getBoundingClientRect();
          if(b.bottom > top){ anchor = {key: r.dataset.rowKey, off: b.top - top}; break; }
        }
      }
      w.scroll[sc.dataset.scrollKey] = {top: sc.scrollTop, atBottom, anchor};
    });
  }catch(_){ /* a capture that fails leaves the repaint as it always was */ }
  return w;
}

// A scroller that opened (or stayed) on its bottom follows what grows under it — a picture that finishes loading,
// a voice note whose length arrives — until HE scrolls away from the bottom.
function _followBottom(sc){
  sc.__hbPinned = true;
  sc.scrollTop = sc.scrollHeight;
  if(sc.__hbFollow) return;
  sc.__hbFollow = true;
  sc.addEventListener("scroll", () => {
    if(sc.__hbPinning) return;
    sc.__hbPinned = sc.scrollHeight - sc.scrollTop - sc.clientHeight <= _PIN_PX;
  }, {passive: true});
  const repin = () => { if(sc.__hbPinned){ sc.__hbPinning = true; sc.scrollTop = sc.scrollHeight;
    requestAnimationFrame(() => { sc.__hbPinning = false; }); } };
  sc.addEventListener("load", repin, true);
  sc.addEventListener("loadedmetadata", repin, true);
  requestAnimationFrame(repin);            // a card painted before its first layout has no height to scroll yet
}

function _restoreWhere(root, w){
  try{
    root.querySelectorAll("[data-scroll-key]").forEach(sc => {
      const was = w.scroll[sc.dataset.scrollKey];
      if(was ? was.atBottom : sc.dataset.open === "bottom"){ _followBottom(sc); return; }
      if(!was) return;
      if(was.anchor){
        const r = Array.from(sc.querySelectorAll("[data-row-key]")).find(x => x.dataset.rowKey === was.anchor.key);
        if(r){ sc.scrollTop += (r.getBoundingClientRect().top - sc.getBoundingClientRect().top) - was.anchor.off; return; }
      }
      sc.scrollTop = was.top;
    });
    if(w.focus){
      const f = Array.from(root.querySelectorAll("[data-keep]")).find(x => x.dataset.keep === w.focus.key);
      if(f){
        if(w.focus.value != null && f.value !== w.focus.value) f.value = w.focus.value;
        f.focus({preventScroll: true});
        try{ if(w.focus.s != null) f.setSelectionRange(Math.min(w.focus.s, f.value.length), Math.min(w.focus.e, f.value.length)); }catch(_){}
        f.scrollTop = w.focus.top || 0;
      }
    }
  }catch(_){ /* never let bookkeeping break the card */ }
}

export function render(root, data, ctx){
  const where = _captureWhere(root);
  _paint(root, data, ctx);
  _restoreWhere(root, where);
}

function _paint(root, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  _LANG = (ctx && ctx.lang) || "en";
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

  // V2-622 — an open thread/mail already carries its OWN header (platform + contact/subject + "← Volver");
  // the dashboard header below (inbox count, every platform dot, connectors/settings/clear) stacked ABOVE
  // that is not a second control surface, it is dead weight — on a hard refresh, with nothing to scroll past
  // to hide it, it read as two headers glued together (operator screenshot, 2026-09-08). Checked here, before
  // the dashboard header is even built, so it never gets appended for these two screens.
  const showChannels = connectedCount===0;
  const fItems = _platFilter ? items.filter(it=>it.platform===_platFilter) : items.filter(it=>it.highlight);
  const activeChat = !showChannels ? (data.active_chat || null) : null;
  if(activeChat){
    // V2-680 — a reading screen owns the card: header fixed, messages scrolling in the middle, reply box
    // pinned at the bottom. See the `.full` block in the stylesheet for why only these two screens opt in.
    root.classList.add("full");
    root.appendChild(threadView(activeChat, data.active_items||[], data, ctx, rerender, data.thread_meta||null));
    return;
  }
  // The mail section's own full-card screens (mailbox.py): a draft being finished, then one message open.
  const mb = data.mailbox || null;
  const draftKey = (mb && mb.draft && (data.drafts || {})[mb.draft]) ? mb.draft : null;
  // A new message whose Save/Send is on its way settles from the state: saved → the draft it became (or, sent,
  // the folder); refused → the same screen with his text and the reason.
  const pn = mb && mb.note;
  if(_newMail && _newMail.pending && pn && pn.at * 1000 >= _newMail.pending - 1500){
    if(pn.key === "saved" || pn.key === "sent") _newMail = null; else _newMail.pending = null;
  }
  if(!showChannels && (_newMail || draftKey)){
    root.classList.add("full");
    root.appendChild(draftEditor(_newMail || data.drafts[draftKey], _newMail ? null : draftKey,
      mb || {folders:[], folder:"INBOX", role:"inbox", rows:[]}, data, ctx, mailAct(ctx, data, rerender), rerender));
    return;
  }
  if(!showChannels && _platFilter==="email" && mb && mb.open){
    root.classList.add("full");
    root.appendChild(mailMessage(mb, data, ctx, mailAct(ctx, data, rerender), rerender));
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
  // WHERE AM I (the operator, 2026-10-26: «ahora mismo no sé si estoy en la home o en alguno de los apartados»).
  // A house at the left of the title, lit together with the title while the home is on screen; inside a channel
  // the house and «Mensajes» dim and the channel's name follows them as the current section — the same
  // breadcrumb every other screen of this card carries.
  const home = !_platFilter;
  const homeBtn = iconButton("home", tt("home", null, "Inicio"), "homebtn" + (home ? " on" : ""));
  homeBtn.onclick=()=>{ selectPlatform(null); ctx.top(); ctx.action("show_view",{platform:"all"}); rerender(); };
  hd.appendChild(homeBtn);
  // V2-616 — this title used to repeat the CATALOG name ("Mensajería"), which the outer card chrome
  // already says (V2-082's header). What this line actually names is the SCREEN underneath it — the
  // unified inbox — so it reads "Mensajes" now, the operator's own suggestion. The click behavior is
  // unchanged: from V2-610, the way BACK to the dashboard, always, from any screen (a platform lens, a
  // wizard, the connectors list, an open thread or mail).
  const title=el("b","hdtitle",tt("title", null, "Mensajes")); title.title=tt("title_hint", null, "Ver la bandeja unificada de todos tus canales");
  title.onclick=()=>{ selectPlatform(null); ctx.top(); ctx.action("show_view",{platform:"all"}); rerender(); };
  if(home) title.classList.add("on");
  hd.append(title);
  if(home){
    // «para ti» counts what the home shows — what is addressed to him — not every unread the channels hold.
    const mine = items.filter(it=>it.highlight).length;
    hd.append(el("span","sub", mine ? tt("n_for_you", {n: mine}, `${mine} para ti`)
      : (connectedCount ? tt("up_to_date", null, "al día") : tt("not_connected", null, "sin conectar"))));
  } else {
    hd.append(el("span","hdsep","›"),
              el("b","hdsec", _platFilter === "email" ? tt("mail_section", null, "Correo") : (PLAT[_platFilter]||{}).label || _platFilter));
    // In the mail section the header says the one thing left: which entry of the rail is on screen.
    if(_platFilter === "email" && data.mailbox) hd.append(el("span","hdsep","›"), el("span","hdcur", mailWhere(data.mailbox)));
  }
  const dots=el("div","dots");
  // V2-521: every channel is VISIBLE up here — connected bright, unconnected dimmed (the operator's ask:
  // seeing the catalogue at a glance). A bright icon toggles that platform's lens; a dimmed one opens that
  // connector's own wizard screen — the same door the voice takes (V2-570).
  ORDER.forEach(pl=>{
    const on=(platforms[pl]||{}).status==="connected";
    const ic=brandIcon(pl, on);
    ic.style.cursor="pointer";
    if(on){
      ic.title=(PLAT[pl]||{}).label+(_platFilter===pl?tt("dot_clear_filter", null, ": quitar filtro"):tt("dot_only_channel", null, ": ver solo este canal"));
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
      ic.title=(PLAT[pl]||{}).label+tt("dot_connect", null, ": sin conectar — toca para conectarlo");
      ic.onclick=()=>ctx.openConnector(pl);     // ⚙ Conectores, on that channel
    }
    dots.appendChild(ic);
  });
  hd.appendChild(dots);
  // V2-616 — the operator: the platform icons and the settings/connectors icons "no pueden estar al mismo
  // nivel ni pegados a lo que son secciones o diferentes plataformas". `.hdactions` is a second cluster with
  // its own divider, so it reads as a DIFFERENT kind of control from the row of channel icons beside it.
  const actions=el("div","hdactions");
  const connBtn=el("button","connbtn","🔌"); connBtn.title=tt("channels_btn", null, "Canales / conectores");
  connBtn.onclick=()=>ctx.openConnector(_platFilter || "");
  actions.appendChild(connBtn);
  const gear=el("button","gear"+(_settingsOpen?" active":""),"⚙"); gear.title=tt("settings", null, "Ajustes");
  gear.onclick=()=>{ _settingsOpen=!_settingsOpen; rerender(); };
  actions.appendChild(gear);
  if(items.length){
    const clr=el("button","clr",tt("clear", null, "Limpiar")); clr.title=tt("mark_all_read", null, "Marcar todo como leído");
    clr.onclick=()=>ctx.action("clear"); actions.appendChild(clr);
  }
  hd.appendChild(actions);
  root.appendChild(hd);
  // V2-800: what waits for his word, and what leaves later — inside its OWN channel, never on the home (the
  // operator: the home holds only the messages addressed to him). Email's live in the mail section's Drafts.
  const pend = (_platFilter && _platFilter !== "email") ? pendingStrip({
    drafts: Object.fromEntries(Object.entries(data.drafts || {}).filter(([, d]) => d && d.target && d.target.platform === _platFilter)),
    sent: (data.sent || []).filter(r => r && r.platform === _platFilter)}, ctx) : null;
  if(pend) root.appendChild(pend);

  if(_settingsOpen) root.appendChild(settingsPanel(platforms, data, ctx, rerender));

  // CHANNELS area: onboarding when nothing is connected, or when the user opens it from the header connector
  // button, or when the brain pushed a `connect_focus`. Messaging starts EMPTY; do not dump every connection
  // form by default (V2-051 product decision, unchanged).
  if(showChannels){
    root.appendChild(connectPrompt(platforms, ctx));
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
    ? tt("nothing_from_", null, "Nada de ")+((PLAT[_platFilter]||{}).label||_platFilter)+tt("_to_handle", null, " que atender ✓")
    : (hidden ? tt("nothing_for_you", null, "Nada dirigido a ti ✓") : tt("nothing_now", null, "Nada que atender ahora ✓"));
  // V2-624 — the ACTIVITY view wins the lens when its platform has a criterion set: it is a different
  // question («qué se ha movido») than the pending inbox («qué me espera»), and the operator set it
  // explicitly. Applies in BOTH profiles — it is a lens-level view, not a density preference.
  const crit = _platFilter ? (data.lens_criteria || {})[_platFilter] : null;
  if(crit){
    root.appendChild(criteriaBar(_platFilter, crit, ctx, rerender));
    const rows = (data.activity_chats || []).filter(r=> r.platform === _platFilter);
    if(rows.length) root.appendChild(activityList(rows, ctx));
    else root.appendChild(el("div","empty",
      tt("no_activity", null, "Sin conversaciones guardadas con actividad en ese período") +
      ((_platFilter === "telegram" || _platFilter === "email")
        ? tt("no_activity_hint", null, " — «Traer del conector» las pide de verdad") : "")));
    return;
  }
  if(_platFilter==="email"){
    // The mail section is a MAIL CLIENT (mailbox.py): the rail and the list fill the card and scroll each on its
    // own, whatever the density profile, the same way a thread is a thread in both.
    root.classList.add("full");
    root.appendChild(mailClient(data, ctx, rerender));
    return;
  }
  if(_profile==="completo"){
    if(fItems.length) root.appendChild(richList(fItems, ctx));
    else root.appendChild(el("div","empty",emptyMsg));
    if(hidden) root.appendChild(restNote(hidden));
    return;
  }

  const lensList = _platFilter ? (data.chat_list || {})[_platFilter] : null;
  if(lensList){
    root.appendChild(platformChats(_platFilter, lensList, ctx));
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
  d.textContent = n===1 ? tt("one_more_msg", null, "1 mensaje más en sus canales") : n+tt("n_more_msgs", null, " mensajes más en sus canales");
  return d;
}
