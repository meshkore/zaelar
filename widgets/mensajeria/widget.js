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
const PLAT = {
  whatsapp: {
    label: "WhatsApp", bg: "var(--hb-accent2,#16B8A6)", requiresCreds: false,
    qrSteps: ["Abre WhatsApp en tu móvil → ", "Ajustes → Dispositivos vinculados", " → ", "Vincular un dispositivo", " y escanea este código."],
  },
  telegram: {
    label: "Telegram", bg: "var(--hb-accent,#3D6FE0)", requiresCreds: true,
    credLink: "https://my.telegram.org",
    qrSteps: ["Abre Telegram en tu móvil → ", "Ajustes → Dispositivos", " → ", "Vincular dispositivo de escritorio", " y escanea este código."],
  },
  email: {label: "Email", bg: "var(--hb-accent,#3D6FE0)", requiresCreds: true},
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
                         ["yahoo","Yahoo"], ["otro","Otro (IMAP/SMTP)"]];
const _busy = {};   // platform -> true while a connection is in progress, for button feedback
// Which field of a connect form to land on after a refusal (V2-559). Module-lived like _busy: the card is
// rebuilt on every render, so the intent has to outlive the DOM node it applies to.
const _focusField = {};

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
const _expanded = new Set();   // message keys with the body expanded

function injectStyles(){
  if(document.getElementById("hb-msg-css"))return;
  const s=document.createElement("style"); s.id="hb-msg-css"; s.textContent=`
  .hb-msg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(480px,92vw)}
  .hb-msg .hd{display:flex;align-items:center;gap:8px;margin:0 0 10px}
  .hb-msg .hd b{font-size:17px} .hb-msg .hd .sub{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-msg .dots{display:flex;gap:6px;margin-left:auto}
  .hb-msg .picon{display:inline-flex;align-items:center;justify-content:center;opacity:.4;flex:0 0 auto}
  .hb-msg .picon.on{opacity:1}
  .hb-msg .picon.filt{box-shadow:0 2px 0 currentColor;border-radius:2px}
  .hb-msg .pdot{width:18px;height:18px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
    font-size:9.5px;font-weight:700;color:#fff;background:var(--hb-neutral,#3a4a5c);opacity:.5;flex:0 0 auto}
  .hb-msg .pdot.on{opacity:1;background:var(--hb-accent2,#16B8A6)}
  .hb-msg .gear{border:0;background:transparent;color:var(--hb-muted,#3a4757);cursor:pointer;font-size:15px;
    width:26px;height:26px;border-radius:8px;line-height:1}
  .hb-msg .gear:hover,.hb-msg .gear.active{background:var(--hb-hover,#eef3f9);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .clr{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:8px;padding:4px 9px;font-size:12px;cursor:pointer;color:var(--hb-muted,#3a4757)}
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
  .hb-msg .ttitle{font-size:14px;font-weight:600;color:var(--hb-ink,#0d1622);margin:2px 0 3px}
  .hb-msg .tbody{font-size:14px;line-height:1.5;color:var(--hb-ink,#0d1622);white-space:pre-wrap;word-break:break-word}
  .hb-msg .tbody.sub{color:var(--hb-muted,#5f6b7c)}
  .hb-msg .tbody.clamp{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .hb-msg .tbody a.lnk{color:var(--hb-accent,#3D6FE0);text-decoration:underline}
  .hb-msg .more{display:inline-block;margin-top:4px;font-size:12.5px;color:var(--hb-accent,#3D6FE0);cursor:pointer}
  .hb-msg .more:hover{text-decoration:underline}
  .hb-msg .tacts{display:flex;gap:2px;flex:0 0 auto;opacity:.3;transition:opacity .12s}
  .hb-msg .tacts button{border:0;background:transparent;border-radius:7px;width:26px;height:24px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#5b6b82);line-height:1}
  .hb-msg .tacts button:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}

  /* Grouped CHAT list + open thread. */
  .hb-msg .chatrow{cursor:pointer;margin:0 -8px;padding-left:8px;padding-right:8px;border-radius:9px}
  .hb-msg .chatrow:hover{background:var(--hb-hover,#eef3f9)}
  .hb-msg .tcount{background:var(--hb-neutral,#3a4a5c);color:#fff;font-size:10.5px;font-weight:700;border-radius:999px;
    min-width:17px;height:17px;padding:0 5px;display:inline-flex;align-items:center;justify-content:center}
  .hb-msg .tprev{font-size:13.5px;color:var(--hb-muted,#5f6b7c);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-msg .thd{display:flex;align-items:center;gap:9px;margin:0 0 10px;padding-bottom:9px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-msg .thd .back{border:0;background:transparent;color:var(--hb-accent,#3D6FE0);cursor:pointer;font-size:13px;padding:3px 2px}
  .hb-msg .thd .back:hover{text-decoration:underline}
  .hb-msg .thdname{font-size:15px}
  /* V2-546 — the operator's OWN messages in the thread, and the boundary of what we hold. An outgoing row is
     indented and quieter: it is context he already knows, and giving it the same weight as an incoming
     message would make a conversation unreadable at a glance.
     NOTE: this whole block is inside a JS template literal, so a backtick here ENDS it — write prose here
     without one, ever (it broke this exact widget once already). */
  .hb-msg .trow.tout{padding-left:26px;opacity:.78}
  .hb-msg .tfrom.tme{color:var(--hb-accent,#3D6FE0)}
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
  .hb-msg .mediaw audio.maud{width:230px;height:32px}
  .hb-msg .mediaw a.mdoc,.hb-msg .mediaw span.mdoc{font-size:12.5px;color:var(--hb-accent,#3D6FE0);text-decoration:none;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:4px 9px}
  .hb-msg .mediaw a.mdoc:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .twhen{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-left:auto;flex:0 0 auto}

  .hb-msg .empty{text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:13px;padding:22px 0}

  /* NARROW SCREENS (V2-559). MEASURED FIRST, and the measurement removed most of what was written here:
     rendered at 375px in six states (connect panel with three failures, both wizards, the QR, the chat list
     and an open thread), NOTHING was clipped and nothing left the viewport — the min(480px,92vw) width was
     already doing the job, and the wrap rules drafted for the channel row only made every row twice as tall
     for a defect that does not exist (the long statuses and the action button never co-occur).
     What is left is the part that IS an improvement on a phone: let the CONTAINER decide the width instead of
     reserving 8vw of it (the mobile deck already pads its card), and let a received photo use the whole card
     instead of a 220px thumbnail taken from the desktop. */
  @media (max-width: 430px){
    .hb-msg{width:auto;max-width:100%}
    .hb-msg .mediaw .matt,.hb-msg .mediaw video.mvid{max-width:100%;max-height:none}
    .hb-msg .mediaw audio.maud{width:100%}
  }
  .hb-msg .linkcard{border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;padding:13px 14px;margin-bottom:10px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .linkcard .ch{display:flex;align-items:center;gap:8px;margin-bottom:9px}
  .hb-msg .linkcard .ch b{font-size:14px}
  .hb-msg label.f{display:block;font-size:12px;color:var(--hb-muted,#5b6b82);margin:6px 0 3px}
  .hb-msg input.f,.hb-msg select.f{width:100%;box-sizing:border-box;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:8px 10px;font-size:13px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hb-msg input.f:focus,.hb-msg select.f:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .err{color:var(--hb-risk,#e5484d);font-size:12px;margin-top:8px}
  .hb-msg .errfield{border-color:var(--hb-risk,#e5484d)!important}

  /* Guided connect wizard (V2-559, redesigned V2-570). The operator asked for an ASSISTANT: one step
     visible at a time, real margins, and a breadcrumb back to the connector list — a stack of three boxes
     read as optional; one box with "Paso 2 de 3" reads as a path. */
  .hb-msg .wstep{border:1px solid var(--hb-line,#e3e8f0);border-radius:11px;padding:11px 12px 12px;background:var(--hb-bg,#fff);margin:2px 0 12px}
  .hb-msg .wstep.done{border-color:var(--hb-accent2,#16B8A6)}
  .hb-msg .whead{display:flex;align-items:center;gap:9px;margin-bottom:9px}
  .hb-msg .wnum{width:22px;height:22px;flex:0 0 auto;border-radius:50%;display:inline-flex;align-items:center;
    justify-content:center;font-size:11.5px;font-weight:700;color:#fff;background:var(--hb-neutral,#3a4a5c)}
  .hb-msg .wstep.done .wnum{background:var(--hb-accent2,#16B8A6)}
  .hb-msg .wtitle{font-size:14px;font-weight:700;color:var(--hb-ink,#0d1622)}
  .hb-msg .wcount{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin:0 0 8px}
  .hb-msg .wbody{font-size:12.5px;color:var(--hb-muted,#4a5a70);line-height:1.55}
  .hb-msg .wbody b{color:var(--hb-ink,#0d1622)}
  .hb-msg .wlink{display:inline-flex;align-items:center;gap:6px;margin-top:9px;border:1px solid var(--hb-accent,#3D6FE0);
    color:var(--hb-accent,#3D6FE0);border-radius:9px;padding:7px 12px;font-size:12.5px;font-weight:600;
    text-decoration:none;background:transparent}
  .hb-msg .wlink:hover{background:var(--hb-accent,#3D6FE0);color:#fff}
  .hb-msg .wtip{margin-top:8px;font-size:12px;color:var(--hb-muted,#5b6b82);background:var(--hb-bg-soft,#fbfdff);
    border:1px solid var(--hb-line,#eef1f6);border-radius:8px;padding:7px 9px;line-height:1.5}
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
  .hb-msg .errcard{border:1px solid var(--hb-risk,#e5484d);border-radius:10px;padding:11px 12px;margin-bottom:12px;background:color-mix(in srgb,var(--hb-risk,#e5484d) 8%,transparent)}
  .hb-msg .errcard .et{font-size:12.5px;color:var(--hb-ink,#0d1622);line-height:1.5;margin-bottom:9px}
  .hb-msg .errcard .et b{color:var(--hb-risk,#e5484d)}
  /* Breadcrumb (V2-570): back to the connector list + which connector we are on. */
  .hb-msg .crumb{display:flex;align-items:center;gap:6px;margin:2px 0 14px;font-size:12.5px}
  .hb-msg .crumb .back{cursor:pointer;color:var(--hb-accent,#3D6FE0);font-weight:600}
  .hb-msg .crumb .back:hover{text-decoration:underline}
  .hb-msg .crumb .sep{color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .crumb .cur{color:var(--hb-ink,#0d1622);font-weight:700}
  /* Homogeneous buttons (V2-570): one scale for every wizard/list/status action, instead of the
     .btn/.cbtn/.dbtn set that had grown three different heights and paddings. */
  .hb-msg .bt{height:36px;padding:0 16px;border-radius:9px;font-size:13px;font-weight:600;cursor:pointer;
    display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box}
  .hb-msg .bt:disabled{opacity:.6;cursor:default}
  .hb-msg .bt-primary{border:0;color:#fff;background:var(--hb-accent,#3D6FE0)}
  .hb-msg .bt-primary:hover:not(:disabled){filter:brightness(1.06)}
  .hb-msg .bt-ghost{border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-muted,#5b6b82)}
  .hb-msg .bt-ghost:hover:not(:disabled){border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .bt-danger{border:0;color:#fff;background:var(--hb-risk,#e5484d)}
  .hb-msg .wfoot{display:flex;gap:8px;margin-top:4px}
  .hb-msg .wfoot .bt-primary{flex:1 1 auto}
  /* Connector LIST screen (V2-570): a grid of icon boxes replaces the stacked rows, so the list stays
     compact and scannable with 3 connectors today or 20 tomorrow — the operator's own worry about having
     to scroll past a long vertical list to reach the wizard. */
  .hb-msg .chanhead{display:flex;align-items:center;gap:8px;margin:2px 0 14px}
  .hb-msg .chanhead b{font-size:14px} .hb-msg .chanhead .back{margin-left:auto;font-size:12px;color:var(--hb-accent,#3D6FE0);cursor:pointer}
  .hb-msg .chanhead .hint{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-msg .igrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:10px}
  .hb-msg .ibox{display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px 8px;
    border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;background:var(--hb-bg,#fff);cursor:pointer;
    font:inherit;color:inherit}
  .hb-msg .ibox:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .ibox.sel{border-color:var(--hb-accent,#3D6FE0);background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 6%,transparent)}
  .hb-msg .ibox.conn{border-color:var(--hb-accent2,#16B8A6)}
  .hb-msg .ibox.conn .isub{color:var(--hb-accent2,#16B8A6);font-weight:600}
  .hb-msg .ibox .iicon{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .ibox .iicon .picon{opacity:1}
  .hb-msg .ibox .iicon svg{width:22px;height:22px}
  .hb-msg .ibox .ilabel{font-size:12.5px;font-weight:600;color:var(--hb-ink,#0d1622);text-align:center}
  .hb-msg .ibox .isub{font-size:10.5px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .ibox .iavatar{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;
    font-size:15px;font-weight:700;color:#fff;background:var(--hb-accent,#3D6FE0)}
  /* Connected-status screen + disconnect confirmation (unscoped, no longer nested under a removed .chan row). */
  .hb-msg .cfm{margin-top:10px;font-size:12.5px;color:var(--hb-ink,#0d1622)}
  .hb-msg .cfm .row{display:flex;gap:8px;margin-top:8px}
  .hb-msg .connbtn{border:0;background:transparent;color:var(--hb-muted,#3a4757);cursor:pointer;font-size:15px;width:26px;height:26px;border-radius:8px;line-height:1}
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
      // User-gesture playback only (controls, preload=none, never autoplay): a received voice note is passive
      // content like the QR image, not agent production — the ⏻ producer contract governs what the AGENT plays.
      const au=document.createElement("audio"); au.className="maud"; au.controls=true; au.preload="none"; au.src=url;
      w.appendChild(au);
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
  yahoo:   {steps:"Genera una contraseña de app en la seguridad de tu cuenta.",
            url:"https://login.yahoo.com/account/security", lbl:"Abrir seguridad de Yahoo", tip:""},
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
  telegram: [{title:"Entra en my.telegram.org"}, {title:"Crea la aplicación"}, {title:"Pega aquí los dos datos"}],
  email:    [{title:"Elige tu proveedor de correo"}, {title:"Crea la contraseña de aplicación"}, {title:"Pega aquí tus datos"}],
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
    const msgEl = el("div","msg"); linkify(msgEl, displayBody(it.body, it.mediaType)); body.appendChild(msgEl);
    const media = mediaBlock(it);
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
function messageRow(it, ctx, rerender){
  const mine = !!it.dirigido_a_mi;
  const urgente = it.urgencia === "alta";
  const key = String(it.messageId != null ? it.messageId : it.n);
  // V2-546 — «out» is what the OPERATOR wrote, here or in his own app; it is context, never something to act
  // on. And a row with no `n` is history: it is no longer in the inbox, so there is nothing left to mark read
  // or dismiss and offering the buttons would be a lie about what pressing them does.
  const outgoing = it.dir === "out";
  const actionable = !outgoing && it.n != null;

  const row = el("div","trow"+(outgoing?" tout":""));
  const lead = el("span","tlead");
  lead.style.background = urgente ? "var(--hb-risk,#e5484d)" : (mine ? "var(--hb-accent,#3D6FE0)" : "transparent");
  row.appendChild(lead);

  const main = el("div","tmain");
  const head = el("div","thead");
  head.appendChild(el("span","tfrom"+(outgoing?" tme":""), outgoing ? "Tú" : (it.from!=null?it.from:"?")));
  if(mine && !outgoing) head.appendChild(el("span","tpara","· para ti"));
  const when = fmtWhen(it.ts);
  if(when) head.appendChild(el("span","twhen", when));
  main.appendChild(head);

  const {title, rest} = splitBody(displayBody(it.body, it.mediaType));
  const isLong = rest.length > 220 || rest.split("\n").length > 4;
  const expanded = _expanded.has(key);
  if(title) main.appendChild(el("div","ttitle", title));
  const bodyEl = el("div","tbody"+(title?" sub":"")+(isLong && !expanded ? " clamp" : ""));
  linkify(bodyEl, rest);
  main.appendChild(bodyEl);
  const media = mediaBlock(it);
  if(media) main.appendChild(media);

  if(isLong){
    const more = el("span","more", expanded ? "mostrar menos" : "mostrar más");
    more.onclick=()=>{ expanded ? _expanded.delete(key) : _expanded.add(key); rerender(); };
    main.appendChild(more);
  }
  row.appendChild(main);

  if(!actionable) return row;       // history (or our own message): nothing left to do to it
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
  row.appendChild(acts);
  return row;
}

// CHAT list (simple profile, default): one item per conversation instead of per message. Shows name, pending
// count, and the last message as preview. Click, or [[msg.open:N]] by voice, enters the full thread.
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
    row.onclick = ()=> ctx.action("open", {n:c.n});

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

function threadView(active, items, ctx, rerender, meta){
  const wrap = el("div","thread");
  const hd = el("div","thd");
  const back = el("button","back","← volver"); back.onclick=()=>ctx.action("close");
  hd.appendChild(back);
  hd.appendChild(platformChip(active.platform));
  // The chat's name comes from an INBOUND message: with outbound ones in the thread (V2-546) the first row can
  // be the operator's own, and naming the conversation after himself is how a thread stops being recognisable.
  const inbound = items.filter(it=> it.dir !== "out");
  const name = (inbound.find(it=>it.group)||{}).group || (inbound.find(it=>it.from)||{}).from
    || (PLAT[active.platform]||{}).label || "Chat";
  hd.appendChild(el("b","thdname", name));
  wrap.appendChild(hd);

  wrap.appendChild(threadStart(meta, ctx));
  const list = el("div","tl");
  items.forEach(it=> list.appendChild(messageRow(it, ctx, rerender)));
  wrap.appendChild(list);
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
    back.onclick=()=>{ _screen=null; rerender(); };
    head.appendChild(back);
  }
  wrap.appendChild(head);

  wrap.appendChild(iconGrid(ORDER.filter(pl=>PLAT[pl]).map(pl=>{
    const p=PLAT[pl];
    const pd=platforms[pl]||{status:"off"};
    const st=pd.status||"off";
    const connected = st==="connected";
    return {
      key:pl, icon:brandIcon(pl, connected), label:p.label, sub:statusLabel(pd), cls:(connected?"conn":""),
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
  if(st!=="off"&&st!=="no_creds"&&st!=="error") _busy[platform]=false;   // engine advanced -> clear local "connecting"

  const crumb=el("div","crumb");
  const back=el("span","back","‹ Conectores");
  back.onclick=()=>{ _screen={view:"list"}; rerender(); };
  crumb.append(back, el("span","sep","/"), el("span","cur", p.label));
  wrap.appendChild(crumb);

  // CONNECTED: a status screen, not a wizard. The draft is NOT cleared on entry into this screen — only once
  // the platform actually reports connected, so a refused connection never loses what the user typed.
  if(st==="connected"){
    _focusField[platform]=null;
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
      y.onclick=()=>{ _confirmDisconnect=null; _busy[platform]=false; ctx.action("disconnect",{platform, forget:true}); };
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
  if(st==="error"){ wrap.appendChild(errorCard(platform, pd.detail, ctx, rerender)); }

  const steps = WIZARD_STEPS[platform] || [{title:"Conectar "+p.label}];
  const total = steps.length;
  let step = Math.min(Math.max(_wizStep[platform]||1, 1), total);
  _wizStep[platform] = step;

  const refs = {};
  const box = stepBox(step, steps[step-1].title, false);
  if(total>1) box.appendChild(el("div","wcount", `Paso ${step} de ${total}`));

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
    if(step>1){ _wizStep[platform]=step-1; rerender(); }
    else { _screen={view:"list"}; rerender(); }
  };
  foot.appendChild(backBtn);

  const isLast = step===total;
  const nextBtn = el("button","bt bt-primary", isLast ? (_busy[platform]?"Conectando…":"Conectar "+p.label) : "Continuar");
  nextBtn.disabled = isLast && !!_busy[platform];
  nextBtn.onclick=()=>{
    if(!isLast){ _wizStep[platform]=step+1; rerender(); return; }
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
      _busy[platform]=true; ctx.action("connect", payload); rerender();
      // The draft is NOT cleared here (V2-559/V2-570): a refused connection comes back to this same step, and
      // wiping it meant retyping the address and the 16 letters from scratch. It is cleared once CONNECTED.
    } else if(platform==="telegram"){
      const api_id=(refs.id.value||"").trim(), api_hash=(refs.hash.value||"").trim();
      if(!/^\d+$/.test(api_id) || !api_hash){ fail("Necesito el api_id (solo números) y el api_hash."); return; }
      _busy[platform]=true; ctx.action("connect", {platform, api_id, api_hash}); rerender();
    } else {
      _busy[platform]=true; ctx.action("connect", {platform}); rerender();
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

  // A pushed VIEW (V2-543) applies only when its witness counter moves: «vuelve a la lista principal» /
  // «solo el WhatsApp» land even when repeated, and a plain repaint never yanks the operator's own choice.
  const pushed = data.view || null;
  if(pushed && Number(pushed.n||0) > 0 && Number(pushed.n) !== _viewN){
    _viewN = Number(pushed.n);
    _platFilter = (pushed.platform && PLAT[pushed.platform]) ? pushed.platform : null;
  }

  // Header: title + counter, connected icons only, connectors, settings, clear.
  const hd=el("div","hd");
  hd.append(el("b",null,"Mensajería"),
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
      ic.onclick=()=>{ const next=(_platFilter===pl ? "all" : pl); _platFilter=(_platFilter===pl ? null : pl);
        ctx.action("show_view",{platform:next}); rerender(); };
    } else {
      ic.title=(PLAT[pl]||{}).label+": sin conectar — toca para conectarlo";
      ic.onclick=()=>{ _screen={view:"wizard", platform:pl}; if(!_wizStep[pl]) _wizStep[pl]=1; rerender(); };
    }
    dots.appendChild(ic);
  });
  hd.appendChild(dots);
  const connBtn=el("button","connbtn"+(_screen?" active":""),"🔌"); connBtn.title="Canales / conectores";
  connBtn.onclick=()=>{ _screen = _screen ? null : {view:"list"}; if(!_screen) _confirmDisconnect=null; rerender(); };
  hd.appendChild(connBtn);
  const gear=el("button","gear"+(_settingsOpen?" active":""),"⚙"); gear.title="Ajustes";
  gear.onclick=()=>{ _settingsOpen=!_settingsOpen; rerender(); };
  hd.appendChild(gear);
  if(items.length && !_screen){
    const clr=el("button","clr","Limpiar"); clr.title="Marcar todo como leído";
    clr.onclick=()=>ctx.action("clear"); hd.appendChild(clr);
  }
  root.appendChild(hd);

  if(_settingsOpen) root.appendChild(settingsPanel(platforms, data, ctx, rerender));

  // CHANNELS area: onboarding when nothing is connected, or when the user opens it from the header connector
  // button, or when the brain pushed a `connect_focus`. Messaging starts EMPTY; do not dump every connection
  // form by default (V2-051 product decision, unchanged).
  const showChannels = !!_screen || connectedCount===0;
  if(showChannels){
    const scr = _screen || {view:"list"};
    if(scr.view==="wizard" && scr.platform && PLAT[scr.platform]){
      root.appendChild(renderWizardScreen(scr.platform, platforms, ctx, rerender));
    } else {
      root.appendChild(renderListScreen(platforms, ctx, rerender, connectedCount));
    }
    return;
  }

  // MESSAGES view, reached whenever at least one channel is connected. The lens (V2-521) narrows every
  // shape below to one platform; an open thread wins over it (it already IS one conversation).
  const fItems = _platFilter ? items.filter(it=>it.platform===_platFilter) : items;
  const emptyMsg = _platFilter
    ? "Nada de "+((PLAT[_platFilter]||{}).label||_platFilter)+" que atender ✓"
    : "Nada que atender ahora ✓";
  // AN OPEN THREAD WINS OVER EVERY LIST SHAPE (V2-544). It used to win over the lens but NOT over the
  // «completo» profile, which returned first: with that profile selected, `open` set `active_chat` in the
  // store and the card kept painting the same flat list — the operator asks to open a message, everything
  // downstream works, and the screen does not move. The profile is a density preference for a LIST; opening a
  // chat is a navigation the agent (or a click) just performed, and it must be visible in both.
  const activeChat = data.active_chat || null;
  if(activeChat){
    root.appendChild(threadView(activeChat, data.active_items||[], ctx, rerender, data.thread_meta||null));
    return;
  }
  if(_profile==="completo"){
    if(fItems.length) root.appendChild(richList(fItems, ctx));
    else root.appendChild(el("div","empty",emptyMsg));
    return;
  }
  if(_platFilter==="email"){
    // Email's NATURAL shape (the operator's spec): a flat list of mails, each expandable in place to read
    // its content — not conversations. messageRow already carries the clamp/«mostrar más» machinery.
    const list = el("div","tl");
    fItems.forEach(it=> list.appendChild(messageRow(it, ctx, rerender)));
    root.appendChild(fItems.length ? list : el("div","empty",emptyMsg));
    return;
  }
  const chats = (data.chats || []).filter(c=>!_platFilter || c.platform===_platFilter);
  if(chats.length) root.appendChild(chatList(chats, ctx));
  else root.appendChild(el("div","empty",emptyMsg));
}
