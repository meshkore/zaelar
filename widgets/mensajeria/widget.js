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

// LOCAL presentation state (cosmetic, does not touch the store): selected profile, settings panel open, expanded
// messages. Survives re-renders because the module loads once.
let _profile = "simple";
try { _profile = localStorage.getItem("hb-msg-profile") || "simple"; } catch { /* storage blocked: use "simple" */ }
let _settingsOpen = false;
let _connectorsOpen = false;         // "Available channels" panel opened from the header
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
const _expandConnect = new Set();    // channels whose connection form is expanded in the panel
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

  /* Media previews (V2-543): same-origin asset route only, elements not requests (isolation contract). */
  .hb-msg .mediaw{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
  .hb-msg .mediaw .matt{max-width:220px;max-height:170px;border-radius:10px;border:1px solid var(--hb-line,#e3e8f0);display:block}
  .hb-msg .mediaw video.mvid{max-width:260px;max-height:200px;border-radius:10px;background:#000}
  .hb-msg .mediaw audio.maud{width:230px;height:32px}
  .hb-msg .mediaw a.mdoc,.hb-msg .mediaw span.mdoc{font-size:12.5px;color:var(--hb-accent,#3D6FE0);text-decoration:none;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:4px 9px}
  .hb-msg .mediaw a.mdoc:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .twhen{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-left:auto;flex:0 0 auto}

  .hb-msg .empty{text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:13px;padding:22px 0}
  .hb-msg .linkcard{border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;padding:13px 14px;margin-bottom:10px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .linkcard .ch{display:flex;align-items:center;gap:8px;margin-bottom:9px}
  .hb-msg .linkcard .ch b{font-size:14px}
  .hb-msg .steps{margin:0 0 10px;padding-left:20px;font-size:12.5px;color:var(--hb-muted,#4a5a70);line-height:1.6}
  .hb-msg .steps li{margin:2px 0} .hb-msg .steps b{color:var(--hb-ink,#0d1622)}
  .hb-msg .steps a{color:var(--hb-accent,#3D6FE0);text-decoration:none;font-weight:600}
  .hb-msg label.f{display:block;font-size:12px;color:var(--hb-muted,#5b6b82);margin:6px 0 3px}
  .hb-msg input.f,.hb-msg select.f{width:100%;box-sizing:border-box;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:8px 10px;font-size:13px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hb-msg input.f:focus,.hb-msg select.f:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .btn{margin-top:11px;width:100%;border:0;border-radius:9px;padding:10px;font-size:13.5px;font-weight:600;cursor:pointer;color:#fff;background:var(--hb-accent,#3D6FE0)}
  .hb-msg .btn:hover{filter:brightness(1.06)} .hb-msg .btn:disabled{opacity:.6;cursor:default}
  .hb-msg .err{color:var(--hb-risk,#e5484d);font-size:12px;margin-top:8px}
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
  .hb-msg .errcard{border:1px solid var(--hb-risk,#e5484d);border-radius:10px;padding:11px 12px;margin-top:8px;background:color-mix(in srgb,var(--hb-risk,#e5484d) 8%,transparent)}
  .hb-msg .errcard .et{font-size:12.5px;color:var(--hb-ink,#0d1622);line-height:1.5;margin-bottom:9px}
  .hb-msg .errcard .et b{color:var(--hb-risk,#e5484d)}
  /* Channels / connectors panel. */
  .hb-msg .chanhead{display:flex;align-items:center;gap:8px;margin:2px 0 10px}
  .hb-msg .chanhead b{font-size:14px} .hb-msg .chanhead .back{margin-left:auto;font-size:12px;color:var(--hb-accent,#3D6FE0);cursor:pointer}
  .hb-msg .chanhead .hint{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-msg .chan{border:1px solid var(--hb-line,#e3e8f0);border-radius:11px;padding:11px 12px;margin-bottom:9px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .chan .top{display:flex;align-items:center;gap:9px}
  .hb-msg .chan .nm{font-size:13.5px;font-weight:600;color:var(--hb-ink,#0d1622)}
  .hb-msg .chan .st{font-size:11.5px;color:var(--hb-muted,#5b6b82);margin-left:2px}
  .hb-msg .chan .st.okc{color:var(--hb-accent2,#16B8A6)}
  .hb-msg .chan .act{margin-left:auto;display:flex;gap:6px;align-items:center}
  .hb-msg .chan .cbtn{border:1px solid var(--hb-accent,#3D6FE0);background:transparent;color:var(--hb-accent,#3D6FE0);border-radius:8px;padding:5px 12px;font-size:12.5px;font-weight:600;cursor:pointer}
  .hb-msg .chan .cbtn:hover{background:var(--hb-accent,#3D6FE0);color:#fff}
  .hb-msg .chan .dbtn{border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-muted,#5b6b82);border-radius:8px;padding:5px 11px;font-size:12px;cursor:pointer}
  .hb-msg .chan .dbtn:hover{border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}
  .hb-msg .chan .expand{margin-top:11px;border-top:1px solid var(--hb-line,#eef1f6);padding-top:11px}
  .hb-msg .chan .cfm{margin-top:10px;font-size:12.5px;color:var(--hb-ink,#0d1622)}
  .hb-msg .chan .cfm .row{display:flex;gap:8px;margin-top:8px}
  .hb-msg .chan .cfm .y{border:0;background:var(--hb-risk,#e5484d);color:#fff;border-radius:8px;padding:6px 13px;font-size:12.5px;font-weight:600;cursor:pointer}
  .hb-msg .chan .cfm .n{border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-muted,#5b6b82);border-radius:8px;padding:6px 13px;font-size:12.5px;cursor:pointer}
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

// Card: credentials form (Telegram), guided for a non-technical user.
function credsCard(platform, ctx){
  const p=PLAT[platform];
  const card=el("div","linkcard");
  const ch=el("div","ch"); ch.append(badge(platform), el("b",null,"Conectar "+p.label)); card.appendChild(ch);

  card.appendChild(el("div",null,"Solo la primera vez necesito dos datos de tu cuenta:"));
  const ol=el("ol","steps");
  const li=(...frag)=>{ const e=el("li"); frag.forEach(f=>e.append(f)); ol.appendChild(e); };
  const link=document.createElement("a"); link.href=p.credLink; link.target="_blank"; link.rel="noopener";
  link.textContent="my.telegram.org";
  li("Abre ", link, " e inicia sesión con tu número (te llega un código dentro de Telegram).");
  li("Entra en ", el("b",null,"API development tools"), ".");
  li("Rellena el formulario (", el("b",null,"App title: Zaelar"), ", ", el("b",null,"Short name: Zaelar"),
     ", el resto en blanco) y pulsa ", el("b",null,"Create application"), ".");
  li("Copia el ", el("b",null,"api_id"), " (un número) y el ", el("b",null,"api_hash"),
     " (una cadena larga) y pégalos aquí:");
  card.appendChild(ol);

  const idL=el("label","f","api_id"); const idI=document.createElement("input");
  idI.className="f"; idI.type="text"; idI.inputMode="numeric"; idI.placeholder="p.ej. 12345678";
  idI.value=_draft.telegram.api_id||""; idI.oninput=()=>{_draft.telegram.api_id=idI.value;};
  const hL=el("label","f","api_hash"); const hI=document.createElement("input");
  hI.className="f"; hI.type="text"; hI.placeholder="cadena larga de letras y números";
  hI.value=_draft.telegram.api_hash||""; hI.oninput=()=>{_draft.telegram.api_hash=hI.value;};
  card.append(idL, idI, hL, hI);

  const err=el("div","err"); err.style.display="none";
  const btn=el("button","btn", _busy[platform] ? "Conectando…" : "Conectar "+p.label);
  btn.disabled=!!_busy[platform];
  btn.onclick=async()=>{
    const api_id=(idI.value||"").trim(), api_hash=(hI.value||"").trim();
    if(!/^\d+$/.test(api_id) || !api_hash){
      err.textContent="Necesito el api_id (solo números) y el api_hash."; err.style.display="block"; return;
    }
    _busy[platform]=true; btn.disabled=true; btn.textContent="Conectando…"; err.style.display="none";
    ctx.action("connect", {platform, api_id, api_hash});   // -> store -> supervisor -> real connect; QR arrives by SSE
    _draft.telegram={api_id:"", api_hash:""};
    card.textContent=""; card.append(ch, el("div","waiting","Conectando con "+p.label+"… te muestro el QR en un momento."));
  };
  card.appendChild(err); card.appendChild(btn);
  return card;
}

// Card: EMAIL form (V2-051), provider + address + app password (no QR).
function emailCard(platform, ctx){
  const p=PLAT[platform];
  const d=_draft.email;
  const card=el("div","linkcard");
  const ch=el("div","ch"); ch.append(badge(platform), el("b",null,"Conectar "+p.label)); card.appendChild(ch);
  card.appendChild(el("div",null,"Leo tu correo y puedes responder por voz. En Gmail/Outlook necesitas una "
    +"«contraseña de aplicación» (con la verificación en 2 pasos activada) — no tu contraseña normal."));

  // Provider.
  const provL=el("label","f","Proveedor"); const prov=document.createElement("select"); prov.className="f";
  EMAIL_PROVIDERS.forEach(([v,lab])=>{ const o=document.createElement("option"); o.value=v; o.textContent=lab;
    if(v===d.provider) o.selected=true; prov.appendChild(o); });
  // Address.
  const addrL=el("label","f","Correo"); const addr=document.createElement("input");
  addr.className="f"; addr.type="email"; addr.placeholder="tucuenta@gmail.com"; addr.autocomplete="off";
  addr.value=d.email_address||""; addr.oninput=()=>{d.email_address=addr.value;};
  // Password.
  const pwL=el("label","f","Contraseña de aplicación"); const pw=document.createElement("input");
  pw.className="f"; pw.type="password"; pw.placeholder="pega aquí la contraseña de aplicación"; pw.autocomplete="off";
  pw.value=d.email_password||""; pw.oninput=()=>{d.email_password=pw.value;};
  // Hosts ("otro" only).
  const imapL=el("label","f","Servidor IMAP"); const imap=document.createElement("input");
  imap.className="f"; imap.type="text"; imap.placeholder="imap.tudominio.com";
  imap.value=d.imap_host||""; imap.oninput=()=>{d.imap_host=imap.value;};
  const smtpL=el("label","f","Servidor SMTP"); const smtp=document.createElement("input");
  smtp.className="f"; smtp.type="text"; smtp.placeholder="smtp.tudominio.com";
  smtp.value=d.smtp_host||""; smtp.oninput=()=>{d.smtp_host=smtp.value;};
  const hostsWrap=el("div"); hostsWrap.append(imapL, imap, smtpL, smtp);
  // Per-provider guidance (V2-521): the generic app-password sentence never said WHERE to get one. One
  // line + the exact page, switching with the dropdown — the operator asked to be told the process, the
  // token, whatever the provider needs, right here.
  const GUIDE={
    gmail:   {txt:"Gmail: activa la verificación en 2 pasos y crea una contraseña de aplicación en ",
              url:"https://myaccount.google.com/apppasswords", lbl:"myaccount.google.com/apppasswords"},
    outlook: {txt:"Outlook/Hotmail: con la verificación en 2 pasos activada, crea una contraseña de aplicación en ",
              url:"https://account.live.com/proofs/AppPassword", lbl:"account.live.com/proofs/AppPassword"},
    icloud:  {txt:"iCloud: genera una contraseña de app en ",
              url:"https://appleid.apple.com/account/manage", lbl:"appleid.apple.com"},
    yahoo:   {txt:"Yahoo: genera una contraseña de app en ",
              url:"https://login.yahoo.com/account/security", lbl:"login.yahoo.com/account/security"},
    otro:    {txt:"Cualquier buzón IMAP/SMTP: usa la contraseña (o contraseña de app) de tu proveedor y "
                   +"rellena sus servidores abajo.", url:"", lbl:""},
  };
  const guide=el("div","cap");
  const syncGuide=()=>{
    guide.textContent="";
    const g=GUIDE[prov.value]||GUIDE.otro;
    guide.appendChild(document.createTextNode(g.txt));
    if(g.url){ const a=document.createElement("a"); a.href=g.url; a.target="_blank"; a.rel="noopener";
      a.textContent=g.lbl; guide.appendChild(a); }
  };
  const syncHosts=()=>{ hostsWrap.style.display = (prov.value==="otro") ? "block" : "none"; };
  prov.onchange=()=>{ d.provider=prov.value; syncHosts(); syncGuide(); }; syncHosts(); syncGuide();

  card.append(provL, prov, guide, addrL, addr, pwL, pw, hostsWrap);

  const err=el("div","err"); err.style.display="none";
  const btn=el("button","btn", _busy[platform] ? "Conectando…" : "Conectar "+p.label);
  btn.disabled=!!_busy[platform];
  btn.onclick=()=>{
    const email_address=(addr.value||"").trim(), email_password=(pw.value||"").trim();
    if(!/.+@.+\..+/.test(email_address) || !email_password){
      err.textContent="Necesito tu dirección de correo y la contraseña de aplicación."; err.style.display="block"; return;
    }
    const payload={platform, email_address, email_password, provider:prov.value};
    if(prov.value==="otro"){
      if(!imap.value.trim() || !smtp.value.trim()){
        err.textContent="Para «Otro» necesito el servidor IMAP y el SMTP."; err.style.display="block"; return;
      }
      payload.imap_host=imap.value.trim(); payload.smtp_host=smtp.value.trim();
    }
    _busy[platform]=true; btn.disabled=true; btn.textContent="Conectando…"; err.style.display="none";
    ctx.action("connect", payload);                            // -> store -> supervisor -> real connect (IMAP/SMTP)
    _draft.email={email_address:"", email_password:"", provider:prov.value, imap_host:"", smtp_host:""};
    card.textContent=""; card.append(ch, el("div","waiting","Conectando con tu correo… un momento."));
  };
  card.appendChild(err); card.appendChild(btn);
  return card;
}

// Card: simple connect button (WhatsApp, no credentials needed).
function connectCard(platform, ctx){
  const p=PLAT[platform];
  const card=el("div","linkcard");
  const ch=el("div","ch"); ch.append(badge(platform), el("b",null,"Conectar "+p.label)); card.appendChild(ch);
  card.appendChild(el("div",null,"Pulsa para vincular tu "+p.label+" con un código QR (como WhatsApp Web)."));
  const btn=el("button","btn", _busy[platform] ? "Conectando…" : "Conectar "+p.label);
  btn.disabled=!!_busy[platform];
  btn.onclick=()=>{
    _busy[platform]=true; btn.disabled=true; btn.textContent="Conectando…";
    ctx.action("connect", {platform});
    card.textContent=""; card.append(ch, el("div","waiting","Conectando con "+p.label+"… te muestro el QR en un momento."));
  };
  card.appendChild(btn);
  return card;
}

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

  const row = el("div","trow");
  const lead = el("span","tlead");
  lead.style.background = urgente ? "var(--hb-risk,#e5484d)" : (mine ? "var(--hb-accent,#3D6FE0)" : "transparent");
  row.appendChild(lead);

  const main = el("div","tmain");
  const head = el("div","thead");
  head.appendChild(el("span","tfrom", it.from!=null?it.from:"?"));
  if(mine) head.appendChild(el("span","tpara","· para ti"));
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
function threadView(active, items, ctx, rerender){
  const wrap = el("div","thread");
  const hd = el("div","thd");
  const back = el("button","back","← volver"); back.onclick=()=>ctx.action("close");
  hd.appendChild(back);
  hd.appendChild(platformChip(active.platform));
  const name = (items.find(it=>it.group||it.from)||{}).group || (items.find(it=>it.from)||{}).from
    || (PLAT[active.platform]||{}).label || "Chat";
  hd.appendChild(el("b","thdname", name));
  wrap.appendChild(hd);

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
  const b=el("button","cbtn","Corregir y reintentar");
  b.onclick=()=>{ _expandConnect.add(pl); rerender(); };
  c.appendChild(b);
  return c;
}

function _connectForm(pl, ctx){
  if(pl==="email") return emailCard(pl, ctx);
  if((PLAT[pl]||{}).requiresCreds) return credsCard(pl, ctx);
  return connectCard(pl, ctx);
}
function _expandWrap(node){ const d=el("div","expand"); d.appendChild(node); return d; }

// CHANNELS / connectors panel (V2-051). Onboarding when nothing is connected ("Available channels" list), and
// always accessible from the header connector button. Each channel: icon + name + status; connect by click or
// voice; disconnect with confirmation because it deletes credentials.
function channelsPanel(platforms, ctx, rerender, connectedCount){
  const wrap=el("div");
  const head=el("div","chanhead");
  head.appendChild(el("b",null, connectedCount ? "Conectores" : "Canales disponibles"));
  head.appendChild(el("span","hint", connectedCount ? "" : "Conecta un canal para empezar — por voz o con un toque."));
  if(connectedCount){ const back=el("span","back","← Mensajes"); back.onclick=()=>{ _connectorsOpen=false; _expandConnect.clear(); _confirmDisconnect=null; rerender(); }; head.appendChild(back); }
  wrap.appendChild(head);

  ORDER.forEach(pl=>{
    const p=PLAT[pl]; if(!p) return;
    const pd=platforms[pl]||{status:"off"};
    const st=pd.status||"off";
    if(st!=="off"&&st!=="no_creds"&&st!=="error") _busy[pl]=false;   // engine advanced -> clear local "connecting"

    const card=el("div","chan");
    const top=el("div","top");
    top.appendChild(brandIcon(pl, st==="connected"));
    top.appendChild(el("span","nm", p.label));
    top.appendChild(el("span","st"+(st==="connected"?" okc":""), statusLabel(pd)));
    const act=el("div","act");
    if(st==="connected"){
      const d=el("button","dbtn","Desconectar");
      d.onclick=()=>{ _confirmDisconnect=pl; rerender(); };
      act.appendChild(d);
    } else if((st==="off"||st==="no_creds") && !_busy[pl] && !_expandConnect.has(pl)){
      const cb=el("button","cbtn","Conectar");
      cb.onclick=()=>{ _expandConnect.add(pl); rerender(); };
      act.appendChild(cb);
    }
    top.appendChild(act);
    card.appendChild(top);

    // DISCONNECT confirmation, deletes credentials; inline dialog.
    if(_confirmDisconnect===pl){
      const cfm=el("div","cfm");
      cfm.appendChild(document.createTextNode(`¿Eliminar las credenciales de ${p.label}? Tendrás que volver a conectarlo.`));
      const row=el("div","row");
      const y=el("button","y","Sí, desconectar");
      y.onclick=()=>{ _confirmDisconnect=null; _busy[pl]=false; _expandConnect.delete(pl); ctx.action("disconnect",{platform:pl, forget:true}); };
      const n=el("button","n","Cancelar"); n.onclick=()=>{ _confirmDisconnect=null; rerender(); };
      row.append(y,n); cfm.appendChild(row); card.appendChild(cfm);
    }

    // Live state / connection form.
    if(_busy[pl] && (st==="off"||st==="no_creds")){
      card.appendChild(_expandWrap(waitBox("Conectando…", "Un momento, contactando con el servicio…")));
    } else if(st==="starting"){
      card.appendChild(_expandWrap(waitBox("Conectando…", pd.detail||"")));
    } else if(st==="connecting"){
      card.appendChild(_expandWrap(qrCard(pl, pd)));           // WA/TG -> QR to scan
    } else if(st==="error"){
      card.appendChild(_expandWrap(errorCard(pl, pd.detail, ctx, rerender)));
      if(_expandConnect.has(pl)) card.appendChild(_expandWrap(_connectForm(pl, ctx)));
    } else if((st==="off"||st==="no_creds") && _expandConnect.has(pl)){
      card.appendChild(_expandWrap(_connectForm(pl, ctx)));
    }
    wrap.appendChild(card);
  });
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

  // The brain was asked to connect a channel (V2-520): open this panel and expand that channel's form, so
  // "connect my email" lands ON the form instead of on the message list. Honoured once per request.
  const focus = data.connect_focus || null;
  if(focus && Number(focus.ts||0) > _focusDone){
    _focusDone = Number(focus.ts||0);
    _connectorsOpen = true;
    if(focus.platform && PLAT[focus.platform]) _expandConnect.add(focus.platform);
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
  // seeing the catalogue at a glance). A bright icon toggles that platform's lens; a dimmed one opens the
  // connectors panel with its form ready — the same door the voice takes.
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
      ic.onclick=()=>{ _connectorsOpen=true; _expandConnect.add(pl); rerender(); };
    }
    dots.appendChild(ic);
  });
  hd.appendChild(dots);
  const connBtn=el("button","connbtn"+(_connectorsOpen?" active":""),"🔌"); connBtn.title="Canales / conectores";
  connBtn.onclick=()=>{ _connectorsOpen=!_connectorsOpen; if(!_connectorsOpen){ _expandConnect.clear(); _confirmDisconnect=null; } rerender(); };
  hd.appendChild(connBtn);
  const gear=el("button","gear"+(_settingsOpen?" active":""),"⚙"); gear.title="Ajustes";
  gear.onclick=()=>{ _settingsOpen=!_settingsOpen; rerender(); };
  hd.appendChild(gear);
  if(items.length && !_connectorsOpen){
    const clr=el("button","clr","Limpiar"); clr.title="Marcar todo como leído";
    clr.onclick=()=>ctx.action("clear"); hd.appendChild(clr);
  }
  root.appendChild(hd);

  if(_settingsOpen) root.appendChild(settingsPanel(platforms, data, ctx, rerender));

  // CHANNELS panel: onboarding when nothing is connected, or when the user opens it from the header connector
  // button. Messaging starts EMPTY; do not dump every connection form by default (V2-051 product decision).
  const showChannels = _connectorsOpen || connectedCount===0;
  if(showChannels){
    root.appendChild(channelsPanel(platforms, ctx, rerender, connectedCount));
    return;
  }

  // MESSAGES view, reached whenever at least one channel is connected. The lens (V2-521) narrows every
  // shape below to one platform; an open thread wins over it (it already IS one conversation).
  const fItems = _platFilter ? items.filter(it=>it.platform===_platFilter) : items;
  const emptyMsg = _platFilter
    ? "Nada de "+((PLAT[_platFilter]||{}).label||_platFilter)+" que atender ✓"
    : "Nada que atender ahora ✓";
  if(_profile==="completo"){
    if(fItems.length) root.appendChild(richList(fItems, ctx));
    else root.appendChild(el("div","empty",emptyMsg));
    return;
  }
  const activeChat = data.active_chat || null;
  if(activeChat){
    root.appendChild(threadView(activeChat, data.active_items||[], ctx, rerender));
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
