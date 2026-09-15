// Contacts widget — client render module (V2-541, redesigned V2-699). Contract: render(el, data, ctx).
// ONE directory for every identity: a sidebar with the groups, a list of entries, and a CARD that looks like
// a contact card — every basic field present even when it is empty, and «how to reach this person» as a block
// of its own. Self-contained: scoped styles, plain DOM, no innerHTML on data, no network, no polling.

const KICON = {person: "\u{1F464}", place: "\u{1F4CD}", company: "\u{1F3E2}"};

// ── The three channels a contact can carry, and the ORDER the card lists them in ─────────────────────────
// Mirrors `widgets/directory.py::PLATFORMS`. It is a fixed list on purpose: a card that only drew the
// channels a contact HAS is the card this replaced — the operator could not tell «no tengo su WhatsApp»
// from «esta ficha no enseña WhatsApp», which is exactly what he reported («no muestra ni siquiera los
// campos básicos, aunque sean vacíos»).
const CHANNELS = [
  {id: "telegram", icon: "✈", label: "Telegram"},
  {id: "whatsapp", icon: "✆", label: "WhatsApp"},
  {id: "email",    icon: "✉", label: "Email"},
];

// ── The HOUSE HEADER (V2-699) — the same two bars every widget with a connector wears ────────────────────
// Operator, 2026-09-15: «esto es un sistema operativo, con lo cual esas barras ya tienen un formato estándar
// y nos llevan al sistema de conectores». The contract is written up in
// `.meshkore/docs/conventions/zaelar-widget-header-standard.md`; the shape copied here is the agenda's
// (V2-679), which copied messaging's. Icons, class names and behaviour are deliberately one-for-one.
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(paths, opts){
  const svg=document.createElementNS(SVG_NS,"svg");
  svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("aria-hidden","true");
  svg.setAttribute("fill", (opts&&opts.fill) || "none");
  if(!(opts&&opts.fill)){ svg.setAttribute("stroke","currentColor"); svg.setAttribute("stroke-width","2");
    svg.setAttribute("stroke-linecap","round"); svg.setAttribute("stroke-linejoin","round"); }
  else { svg.setAttribute("fill","currentColor"); }
  (Array.isArray(paths)?paths:[paths]).forEach(d=>{
    const p=document.createElementNS(SVG_NS,"path"); p.setAttribute("d",d); svg.appendChild(p);
  });
  return svg;
}

const ICO_PEOPLE = ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2","M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
                    "M22 21v-2a4 4 0 0 0-3-3.87","M16 3.13a4 4 0 0 1 0 7.75"];
const ICO_PLUG   = ["M9 2v6","M15 2v6","M6 8h12v3a6 6 0 0 1-12 0z","M12 17v5"];
const ICO_SYNC   = ["M21 2v6h-6","M3 12a9 9 0 0 1 15-6.7L21 8","M3 22v-6h6","M21 12a9 9 0 0 1-15 6.7L3 16"];

// The provider marks. Same source as the agenda's `CAL_SVG` so Google looks like Google in both.
const SRC_SVG = {
  "google-contacts": {color:"#4285F4", path:"M12.545 10.239v3.821h5.445c-.712 2.315-2.647 3.972-5.445 3.972a6.033 6.033 0 1 1 0-12.064c1.498 0 2.866.549 3.921 1.453l2.814-2.814A9.969 9.969 0 0 0 12.545 2C7.021 2 2.543 6.477 2.543 12s4.478 10 10.002 10c8.396 0 10.249-7.85 9.426-11.748l-9.426-.013z"},
  icloud: {color:"#3693F3", path:"M13.762 4.29a6.51 6.51 0 0 0-5.669 3.332 3.571 3.571 0 0 0-1.558-.36 3.571 3.571 0 0 0-3.516 3A4.918 4.918 0 0 0 0 14.796a4.918 4.918 0 0 0 4.92 4.914 4.93 4.93 0 0 0 .617-.045h14.42c2.305-.272 4.041-2.258 4.043-4.589v-.009a4.594 4.594 0 0 0-3.727-4.508 6.51 6.51 0 0 0-6.511-6.27z"},
  carddav: {color:"var(--hb-muted,#6b7b92)", path:"M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm-9 4a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zm4.5 9h-9v-.75c0-1.5 3-2.32 4.5-2.32s4.5.82 4.5 2.32V17z"},
};

//: The only source with a connector behind it today. Everything else stays VISIBLE but INERT — no button,
//: no click handler — until it lands in `connectors/contacts/providers.py`. «No lo has enlazado» and «no lo
//: hemos construido» are different sentences and the strip has to be able to say both.
const LIVE_SOURCES = {"google-contacts": true};

function injectStyles(){
  if(document.getElementById("hb-contactos-css"))return;
  const s=document.createElement("style"); s.id="hb-contactos-css"; s.textContent=`
  .hb-contactos{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:100%;box-sizing:border-box}
  .hb-contactos button{font-family:inherit}
  .hb-contactos .cthd{display:flex;align-items:center;gap:12px;margin:0 0 12px;flex-wrap:wrap}
  .hb-contactos .cthd b{font-size:18px;flex:0 0 auto}
  .hb-contactos .cthd .ctn{font-size:12px;color:var(--hb-muted-2,#7d8a9c);font-family:ui-monospace,Menlo,monospace;flex:0 0 auto;margin-left:auto}
  .hb-contactos .ctsearch{flex:1 1 200px;min-width:140px;display:flex;align-items:center;gap:6px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:5px 12px;background:var(--hb-bg,#fff)}
  .hb-contactos .ctsearch:focus-within{border-color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctsearch span{font-size:12px;color:var(--hb-muted-2,#7d8a9c);flex:0 0 auto}
  .hb-contactos .ctsearch input{border:none;outline:none;background:none;color:var(--hb-ink,#0d1622);font-size:13px;width:100%;padding:0}
  .hb-contactos .ctcols{display:grid;grid-template-columns:170px 1fr;gap:14px;align-items:start}
  @media(max-width:600px){.hb-contactos .ctcols{grid-template-columns:1fr}}

  /* ── HOUSE HEADER BAR — brand disc + content title + right slot (V2-699 standard) ──────────────── */
  .hb-contactos .ctbar{display:flex;align-items:center;gap:var(--sp-2,8px);padding:0 0 var(--sp-3,12px);
    flex:0 0 auto;min-width:0}
  .hb-contactos .ctbrand{width:26px;height:26px;border-radius:8px;background:var(--hb-accent,#3D6FE0);
    color:var(--canvas,#101216);display:flex;align-items:center;justify-content:center;flex:0 0 auto}
  .hb-contactos .ctbrand svg{width:15px;height:15px;display:block}
  .hb-contactos .cttitle{font-size:14px;font-weight:600;letter-spacing:-.01em;white-space:nowrap;flex:0 0 auto}

  /* ── HOUSE SUBHEADER BAND — view tabs left, provider icons + Conectores right ──────────────────── */
  .hb-contactos .ctviews{display:flex;align-items:center;gap:var(--sp-1,4px);flex-wrap:nowrap;overflow-x:auto;
    border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.06));
    padding-bottom:var(--sp-2,8px);margin-bottom:var(--sp-3,12px);flex:0 0 auto;scrollbar-width:none}
  .hb-contactos .ctviews::-webkit-scrollbar{display:none}
  .hb-contactos .cttab{border:0;background:none;color:var(--hb-muted,#5b6b82);border-radius:999px;
    padding:var(--sp-2,8px) var(--sp-3,12px);font-size:13px;font-weight:600;cursor:pointer;line-height:1.2;
    white-space:nowrap;flex:0 0 auto}
  .hb-contactos .cttab:hover{background:var(--hb-hover,#242A34);color:var(--hb-ink,#0d1622)}
  .hb-contactos .cttab.on{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);
    color:var(--hb-ink,#F2F4F7);font-weight:700;
    box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent)}
  .hb-contactos .cttab:disabled{opacity:.75;cursor:default;pointer-events:none}
  .hb-contactos .ctviewsright{margin-left:auto;display:flex;align-items:center;gap:10px;flex:0 0 auto}
  .hb-contactos .ctconnicons{display:flex;align-items:center;gap:4px}
  .hb-contactos .ctconnicon{width:var(--hb-icon-h,28px);height:var(--hb-icon-h,28px);border-radius:var(--hb-r-s,8px);
    border:0;background:none;cursor:pointer;display:flex;align-items:center;justify-content:center;opacity:.72}
  .hb-contactos .ctconnicon svg{width:15px;height:15px;display:block}
  .hb-contactos .ctconnicon:hover:not(:disabled){opacity:1;background:var(--hb-bg-soft,#f4f7fb)}
  .hb-contactos .ctconnicon.on{opacity:1}
  .hb-contactos .ctconnicon.off{opacity:.4;cursor:default}
  .hb-contactos .ctconnbtn{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);border-radius:var(--hb-r-s,8px);height:var(--hb-ctl-h-sm,32px);
    padding:0 var(--sp-3,12px);font-size:13px;font-weight:600;cursor:pointer;display:flex;align-items:center;
    gap:7px;flex:0 0 auto}
  .hb-contactos .ctconnbtn:hover,.hb-contactos .ctconnbtn.on{border-color:var(--hb-accent,#3D6FE0);
    color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctconnbtn svg{width:14px;height:14px;display:block}

  /* ── CONNECTORS SCREEN — the whole content area, never a floating overlay ──────────────────────── */
  .hb-contactos .ctconnscreen{display:flex;flex-direction:column;gap:10px;max-width:720px}
  .hb-contactos .ctconnhead{display:flex;align-items:center;gap:10px}
  .hb-contactos .ctconntitle{font-size:15px;font-weight:700}
  .hb-contactos .ctconnback{margin-left:auto;cursor:pointer;color:var(--hb-accent,#9B7CFF);font-weight:600;
    font-size:13px;border:0;background:none;padding:4px 2px}
  .hb-contactos .ctconnback:hover{text-decoration:underline}
  .hb-contactos .ctsrc{display:flex;align-items:center;gap:11px;border:1px solid var(--hb-line,#e3e8f0);
    border-radius:12px;padding:11px 13px;background:var(--hb-bg,#fff)}
  .hb-contactos .ctsrc.dim{opacity:.55}
  .hb-contactos .ctsrcic{width:28px;height:28px;flex:0 0 auto;display:flex;align-items:center;justify-content:center}
  .hb-contactos .ctsrcic svg{width:19px;height:19px;display:block}
  .hb-contactos .ctsrctx{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1 1 auto}
  .hb-contactos .ctsrcnm{font-size:13.5px;font-weight:600}
  .hb-contactos .ctsrcst{font-size:11.5px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-contactos .ctdot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;
    background:var(--hb-muted-2,#9aa7b8);vertical-align:middle}
  .hb-contactos .ctdot.ok{background:var(--hb-ok,#3BB273)}
  .hb-contactos .ctbtn{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);border-radius:var(--hb-r-s,8px);height:var(--hb-ctl-h-sm,32px);
    padding:0 var(--sp-3,12px);font-size:12.5px;font-weight:600;cursor:pointer;flex:0 0 auto}
  .hb-contactos .ctbtn:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctbtn.primary{background:var(--hb-accent,#3D6FE0);border-color:var(--hb-accent,#3D6FE0);
    color:var(--canvas,#101216)}
  .hb-contactos .ctbtn.primary:hover{opacity:.9;color:var(--canvas,#101216)}
  .hb-contactos .ctbtn.danger:hover{border-color:var(--hb-danger,#D9534F);color:var(--hb-danger,#D9534F)}
  .hb-contactos .ctbtn[disabled]{opacity:.5;cursor:default;pointer-events:none}

  /* ── THE SYNC BOX ──────────────────────────────────────────────────────────────────────────────── */
  .hb-contactos .ctsync{border:1px solid var(--hb-line,#e3e8f0);border-radius:14px;padding:14px 15px;
    background:var(--hb-bg-soft,#f6f8fb);display:flex;flex-direction:column;gap:10px}
  .hb-contactos .ctsynctop{display:flex;align-items:center;gap:9px}
  .hb-contactos .ctsynctop svg{width:16px;height:16px;display:block;color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctsynctop b{font-size:13.5px}
  .hb-contactos .ctsyncdir{display:flex;align-items:center;gap:9px;font-size:12.5px;
    color:var(--hb-muted,#5b6b82);background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);
    border-radius:10px;padding:9px 11px}
  .hb-contactos .ctsyncarrow{font-family:ui-monospace,Menlo,monospace;color:var(--hb-accent,#3D6FE0);
    font-weight:700;flex:0 0 auto}
  .hb-contactos .ctsyncfoot{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .hb-contactos .ctsyncwhen{font-size:11.5px;color:var(--hb-muted-2,#7d8a9c);margin-left:auto;text-align:right}
  .hb-contactos .ctwarn{font-size:11.5px;line-height:1.5;color:var(--hb-warn,#E0A23D);
    border-left:2px solid var(--hb-warn,#E0A23D);padding-left:9px}

  /* SIDEBAR — a real panel with a ground of its own, not four buttons floating on the canvas. */
  .hb-contactos .ctside{display:flex;flex-direction:column;gap:3px;background:var(--hb-bg-soft,#f6f8fb);border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;padding:7px;max-height:56vh;overflow:auto}
  .hb-contactos .ctg{display:flex;gap:6px;align-items:center;border:1px solid transparent;background:none;border-radius:8px;padding:6px 9px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#3a4757);text-align:left;width:100%;box-sizing:border-box}
  .hb-contactos .ctg:hover{background:var(--hb-bg,#fff);color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctg.on{background:var(--hb-accent,#3D6FE0);border-color:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);font-weight:600}
  .hb-contactos .ctg .ctgc{margin-left:auto;font-size:10.5px;font-family:ui-monospace,Menlo,monospace;opacity:.75}
  .hb-contactos .ctsep{height:1px;background:var(--hb-line,#e3e8f0);margin:6px 3px;flex:0 0 auto}
  .hb-contactos .ctsidelbl{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--hb-muted-2,#9aa7b8);padding:2px 9px 3px}
  .hb-contactos .ctside .ctact{display:flex;gap:6px;align-items:center;border:1px dashed var(--hb-line,#d6dde8);background:none;border-radius:8px;padding:6px 9px;font-size:12px;cursor:pointer;color:var(--hb-muted,#5b6b82);width:100%;box-sizing:border-box;text-align:left}
  .hb-contactos .ctside .ctact:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0);border-style:solid}
  .hb-contactos .ctside .ctact[disabled]{opacity:.5;cursor:default}

  .hb-contactos .ctmain{display:flex;flex-direction:column;gap:9px;min-width:0}
  .hb-contactos .ctfil{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
  .hb-contactos .ctchip{font-size:11.5px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:3px 10px;cursor:pointer;color:var(--hb-muted,#5b6b82);background:var(--hb-bg,#fff)}
  .hb-contactos .ctchip:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctchip.on{background:var(--hb-accent2,#16B8A6);border-color:var(--hb-accent2,#16B8A6);color:var(--canvas,#101216)}
  .hb-contactos .ctlist{display:flex;flex-direction:column;gap:5px;max-height:46vh;overflow:auto}
  .hb-contactos .ctrow{display:flex;gap:10px;align-items:center;border:1px solid var(--hb-line,#eef1f6);border-radius:10px;padding:8px 11px;background:var(--hb-bg,#fff);cursor:pointer}
  .hb-contactos .ctrow:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctrtx{display:flex;flex-direction:column;gap:1px;min-width:0;flex:1 1 auto}
  .hb-contactos .ctrow .ctnm{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-contactos .ctrow .ctsub{font-size:11.5px;color:var(--hb-muted-2,#7d8a9c);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:ui-monospace,Menlo,monospace}
  .hb-contactos .ctrow .ctci{font-size:12px;color:var(--hb-muted-2,#7d8a9c);white-space:nowrap;flex:0 0 auto}
  .hb-contactos .ctrow .ctgs{display:flex;gap:4px;overflow:hidden;flex:0 0 auto}
  .hb-contactos .ctpill{font-size:10px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:1px 7px;color:var(--hb-muted,#5b6b82);white-space:nowrap}
  .hb-contactos .ctfav{border:none;background:none;font-size:15px;cursor:pointer;opacity:.3;flex:0 0 auto;color:inherit;padding:0 2px}
  .hb-contactos .ctfav.on{opacity:1;color:var(--hb-warn,#E0A23D)}
  .hb-contactos .ctempty{font-size:13px;color:var(--hb-muted-2,#7d8a9c);border:1px dashed var(--hb-line,#e3e8f0);border-radius:12px;padding:18px;text-align:center}

  /* AVATAR — an initial in a disc. It is what makes a list of names read as a list of PEOPLE. */
  .hb-contactos .ctav{width:32px;height:32px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;color:#fff}
  .hb-contactos .ctav.big{width:52px;height:52px;font-size:21px}

  /* THE CARD */
  .hb-contactos .ctdet{border:1px solid var(--hb-line,#e3e8f0);border-radius:14px;background:var(--hb-bg,#fff);overflow:hidden}
  .hb-contactos .ctdet .ctback{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:8px;padding:4px 10px;font-size:12px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-contactos .ctdet .ctback:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctdbar{display:flex;align-items:center;gap:8px;padding:9px 12px;border-bottom:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#f6f8fb)}
  .hb-contactos .ctdel{margin-left:auto;border:1px solid transparent;background:none;border-radius:8px;padding:4px 9px;font-size:12px;cursor:pointer;color:var(--hb-muted-2,#9aa7b8)}
  .hb-contactos .ctdel:hover{color:var(--hb-danger,#D9534F);border-color:var(--hb-danger,#D9534F)}
  .hb-contactos .cthero{display:flex;align-items:center;gap:13px;padding:15px 16px 13px}
  .hb-contactos .cthero .ctht{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1 1 auto}
  .hb-contactos .cthero .ctdnm{font-size:19px;font-weight:700;line-height:1.2}
  .hb-contactos .ctkind{font-size:12px;color:var(--hb-muted-2,#7d8a9c);border:none;background:none;padding:0;cursor:pointer;text-align:left}
  .hb-contactos .ctkind:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctdsec{border-top:1px solid var(--hb-line,#eef1f6);padding:11px 16px 13px}
  .hb-contactos .ctdsec h4{margin:0 0 8px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.11em;color:var(--hb-muted-2,#9aa7b8)}
  .hb-contactos .ctfr{display:flex;gap:10px;align-items:baseline;padding:4px 0;font-size:13px;min-height:22px}
  .hb-contactos .ctfr .ctfk{color:var(--hb-muted-2,#7d8a9c);flex:0 0 86px;font-size:12px}
  .hb-contactos .ctfv{flex:1 1 auto;min-width:0;cursor:text;border-bottom:1px dashed transparent;word-break:break-word}
  .hb-contactos .ctfv:hover{border-bottom-color:var(--hb-line,#d6dde8)}
  .hb-contactos .ctfv.void{color:var(--hb-muted-2,#9aa7b8)}
  .hb-contactos .ctin{flex:1 1 auto;min-width:0;border:1px solid var(--hb-accent,#3D6FE0);border-radius:6px;padding:2px 7px;font-size:13px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);font-family:inherit}
  .hb-contactos .ctch{display:flex;gap:9px;align-items:center;padding:5px 0;font-size:13px;min-height:26px}
  .hb-contactos .ctch .ctcic{flex:0 0 18px;text-align:center;font-size:13px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-contactos .ctch .ctcpl{flex:0 0 74px;color:var(--hb-muted-2,#7d8a9c);font-size:12px}
  .hb-contactos .ctch .ctfv{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
  .hb-contactos .ctchx{border:none;background:none;cursor:pointer;color:var(--hb-muted-2,#9aa7b8);font-size:13px;padding:0 3px;flex:0 0 auto;opacity:0}
  .hb-contactos .ctch:hover .ctchx{opacity:1}
  .hb-contactos .ctchx:hover{color:var(--hb-danger,#D9534F)}
  .hb-contactos .ctpref{border:none;background:none;cursor:pointer;font-size:13px;padding:0 2px;flex:0 0 auto;opacity:.25;color:inherit}
  .hb-contactos .ctpref.on{opacity:1;color:var(--hb-warn,#E0A23D)}
  .hb-contactos .ctlink{color:var(--hb-accent,#3D6FE0);cursor:pointer;text-decoration:underline}
  .hb-contactos .cttags{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
  .hb-contactos .cttag{font-size:11px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:2px 9px;color:var(--hb-muted,#5b6b82);display:inline-flex;gap:5px;align-items:center}
  .hb-contactos .cttag button{border:none;background:none;cursor:pointer;color:var(--hb-muted-2,#9aa7b8);padding:0;font-size:12px;line-height:1}
  .hb-contactos .cttag button:hover{color:var(--hb-danger,#D9534F)}
  .hb-contactos .ctaddtag{font-size:11px;border:1px dashed var(--hb-line,#d6dde8);border-radius:999px;padding:2px 9px;color:var(--hb-muted-2,#9aa7b8);cursor:pointer;background:none}
  .hb-contactos .ctaddtag:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0);border-style:solid}
  .hb-contactos .ctnote{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);margin-top:7px;line-height:1.45}
  `; document.head.appendChild(s);
}

function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=text; return e; }

function normJs(s){ return String(s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"")
  .replace(/\s+/g," ").trim().toLowerCase(); }

// Loose group match, BOTH directions («fontanero» ↔ «fontaneros») — mirrors data.py's `_group_matches`.
function groupMatch(want, c){
  const w=normJs(want); if(!w) return true;
  return (c.groups||[]).some(g=>{const gn=normJs(g); return gn.includes(w)||w.includes(gn);});
}

// ── Reachability, mirroring `widgets/directory.py` — INCLUDING its one asymmetry ─────────────────────────
// A stored `email` IS an email channel: the address is the whole capability. A stored `phone` is NOT a
// WhatsApp channel — having somebody's number is not proof they use WhatsApp. Painting a green WhatsApp row
// off `c.phone` would make the card claim a reachability the sending door refuses, which is the worst kind
// of disagreement between two surfaces of the same fact.
function channelOf(c, id){
  const row=(c.channels||[]).find(ch=>String(ch.platform||"")===id);
  if(row && (row.handle || row.chatId)) return {handle:String(row.handle||""), chatId:String(row.chatId||""), stored:true};
  if(id==="email" && c.email) return {handle:String(c.email), chatId:"", stored:false};
  return null;
}

function preferredLine(c){
  const p=String(c.preferred||"");
  const order=p ? [p].concat(CHANNELS.map(x=>x.id).filter(x=>x!==p)) : CHANNELS.map(x=>x.id);
  for(const id of order){ const ch=channelOf(c,id); if(ch && ch.handle) return ch.handle; }
  return "";
}

// A stable colour per contact so the same face keeps the same disc across renders and reorders.
function avatarHue(s){ let h=0; const t=String(s||"?");
  for(let i=0;i<t.length;i++) h=(h*31+t.charCodeAt(i))>>>0;
  return h%360; }

function avatar(c, big){
  const nm=String(c.name||c.id||"?").trim();
  const a=el2("div","ctav"+(big?" big":""), (nm[0]||"?").toUpperCase());
  a.style.background="hsl("+avatarHue(nm)+",42%,42%)";   // L=42% keeps white text above the 4.5:1 floor
  return a;
}

function filtered(data, st){
  let out=(data.contacts||[]).slice();
  // The subheader's KIND tab. Empty means «Todos»; an unknown stored kind reads as a person, mirroring
  // `data.py::_kind`, so a row can never fall out of every tab at once.
  if(st.kind) out=out.filter(c=>(String(c.kind||"person")||"person")===st.kind);
  if(st.group==="__fav") out=out.filter(c=>c.favorite);
  else if(st.group) out=out.filter(c=>groupMatch(st.group,c));
  if(st.fav) out=out.filter(c=>c.favorite);
  if(st.city){ const cw=normJs(st.city);
    out=out.filter(c=>{const cn=normJs(c.city); return cn.includes(cw)||(cn&&cw.includes(cn));}); }
  if(st.query){ const qn=normJs(st.query);
    out=out.filter(c=>normJs([c.name,c.city,c.address,c.phone,c.email,c.notes,
      (c.groups||[]).map(g=>g).join(" "),
      (c.channels||[]).map(ch=>ch.handle||"").join(" ")].join(" ")).includes(qn)); }
  out.sort((a,b)=>(a.favorite===b.favorite ? (normJs(a.name)<normJs(b.name)?-1:1) : (a.favorite?-1:1)));
  return out;
}

function favBtn(c, ctx, el, data){
  const b=el2("button","ctfav"+(c.favorite?" on":""),"★");
  b.title=c.favorite?tt("unfav", null, "Quitar de favoritos"):tt("fav", null, "Marcar como favorito");
  b.onclick=async(ev)=>{ ev.stopPropagation();
    const nd=await ctx.action("set_favorite",{contactId:c.id,favorite:!c.favorite});
    render(el,(nd&&nd.contacts)?nd:data,ctx); };
  return b;
}

// ── Editing in place ─────────────────────────────────────────────────────────────────────────────────────
// `commit` receives the typed string and does whatever that row means; the caller re-renders from whatever
// the action returned. Escape restores without a round trip — a cancel that still wrote would be a lie.
function editable(holder, shown, value, commit){
  holder.onclick=()=>{
    const inp=document.createElement("input");
    inp.className="ctin"; inp.value=String(value||"");
    let done=false;
    const finish=(save)=>{ if(done)return; done=true;
      if(save) commit(inp.value); else holder.replaceWith(shown); };
    inp.onkeydown=(e)=>{ if(e.key==="Enter"){e.preventDefault();finish(true);}
                         else if(e.key==="Escape"){e.preventDefault();finish(false);} };
    inp.onblur=()=>finish(true);
    holder.replaceWith(inp); inp.focus(); inp.select();
  };
}

function fieldRow(box, label, value, commit){
  const r=el2("div","ctfr");
  r.appendChild(el2("span","ctfk",label));
  const v=el2("span","ctfv"+(value?"":" void"), value || "—");
  v.title=tt("edit_hint", null, "Pulsa para editar");
  editable(v, v, value, commit);
  r.appendChild(v); box.appendChild(r);
  return r;
}

function section(box, title){
  const s=el2("div","ctdsec"); s.appendChild(el2("h4",null,title)); box.appendChild(s); return s;
}

// `el` is always the widget ROOT (state + re-renders live there); `host` is where the panel is appended.
// Passing the column as `el` would re-render the whole widget INSIDE it — V2-124's detached-canvas family.
function renderDetail(el, host, data, ctx, c){
  const box=el2("div","ctdet");
  const redraw=nd=>render(el,(nd&&nd.contacts)?nd:data,ctx);
  const act=async(name,payload)=>redraw(await ctx.action(name,payload));

  // Top bar — back, and the one destructive action, kept far from everything else.
  const bar=el2("div","ctdbar");
  const back=el2("button","ctback",tt("back", null, "← Volver"));
  back.onclick=()=>{ el._ctDetail=null; render(el,data,ctx); };
  bar.appendChild(back);
  const del=el2("button","ctdel",tt("delete", null, "Borrar"));
  del.onclick=()=>act("remove_contact",{contactId:c.id}).then(()=>{ el._ctDetail=null; });
  bar.appendChild(del);
  box.appendChild(bar);

  // Hero — face, name, kind, favourite.
  const hero=el2("div","cthero");
  hero.appendChild(avatar(c,true));
  const ht=el2("div","ctht");
  const nm=el2("div","ctdnm",c.name||c.id);
  editable(nm, nm, c.name||"", v=>{ const t=String(v).trim();
    if(!t || t===String(c.name||"")) return redraw(null);
    act("update_contact",{contactId:c.id,name:t}); });
  ht.appendChild(nm);
  const kinds=["person","place","company"];
  const kb=el2("button","ctkind",(KICON[c.kind]||KICON.person)+"  "+(kindLabel(c.kind)||c.kind||""));
  kb.title=tt("kind_hint", null, "Pulsa para cambiar el tipo");
  kb.onclick=()=>{ const i=kinds.indexOf(String(c.kind||"person"));
    act("update_contact",{contactId:c.id,kind:kinds[(i<0?0:i+1)%kinds.length]}); };
  ht.appendChild(kb);
  hero.appendChild(ht);
  hero.appendChild(favBtn(c,ctx,el,data));
  box.appendChild(hero);

  // ── HOW TO REACH HIM — all three platforms, present even when empty ────────────────────────────────────
  const reach=section(box, tt("sec_reach", null, "Cómo contactar"));
  CHANNELS.forEach(p=>{
    const ch=channelOf(c,p.id);
    const r=el2("div","ctch");
    r.appendChild(el2("span","ctcic",p.icon));
    r.appendChild(el2("span","ctcpl",p.label));
    const shownVal=ch?ch.handle:"";
    const v=el2("span","ctfv"+(shownVal?"":" void"), shownVal || "—");
    v.title=tt("edit_hint", null, "Pulsa para editar");
    editable(v, v, shownVal, val=>{
      const t=String(val).trim();
      if(t===shownVal) return redraw(null);
      // A stored `email` field and an email CHANNEL are the same capability said twice; write back to
      // whichever of the two this row is actually showing, so the card never creates a second truth.
      if(p.id==="email" && (!ch || !ch.stored)){
        if(!t) return act("update_contact",{contactId:c.id,clear:"email"});
        return act("update_contact",{contactId:c.id,email:t});
      }
      if(!t) return act("set_channel",{contactId:c.id,platform:p.id,remove:true});
      act("set_channel",{contactId:c.id,platform:p.id,handle:t,preferred:false});
    });
    r.appendChild(v);
    if(ch && ch.handle){
      const x=el2("button","ctchx","✕");
      x.title=tt("channel_clear", null, "Quitar este canal");
      x.onclick=()=>{ if(p.id==="email" && !ch.stored) return act("update_contact",{contactId:c.id,clear:"email"});
        act("set_channel",{contactId:c.id,platform:p.id,remove:true}); };
      r.appendChild(x);
      const pref=String(c.preferred||"")===p.id;
      const pb=el2("button","ctpref"+(pref?" on":""),"★");
      pb.title=pref?tt("pref_is", null, "Es el canal preferido")
                   :tt("pref_set", null, "Escribirle por aquí por defecto");
      if(!pref) pb.onclick=()=>act("set_channel",{contactId:c.id,platform:p.id,preferred:true});
      r.appendChild(pb);
    }
    reach.appendChild(r);
  });
  if(c.phone && !channelOf(c,"whatsapp")){
    // Said out loud rather than guessed: the number is there, and it is still not a WhatsApp.
    reach.appendChild(el2("div","ctnote",
      tt("phone_not_whatsapp", null, "Tienes su teléfono, pero tener un número no prueba que use WhatsApp: "
        + "escribe su WhatsApp arriba si quieres poder mandarle mensajes por ahí.")));
  }

  // ── THE BASIC FIELDS — all of them, empty or not ───────────────────────────────────────────────────────
  const dat=section(box, tt("sec_data", null, "Datos"));
  const setField=(key)=>(v)=>{ const t=String(v).trim();
    if(t===String(c[key]||"")) return redraw(null);
    const p={contactId:c.id};
    // An EMPTY string does not clear through `update_contact` — that guard exists so a model omitting a
    // field cannot wipe it. The card is a deliberate gesture, so it says `clear` instead of relying on "".
    if(!t) p.clear=key; else p[key]=t;
    act("update_contact",p); };
  fieldRow(dat, tt("phone", null, "Teléfono"), c.phone||"", setField("phone"));
  fieldRow(dat, tt("city", null, "Ciudad"), c.city||"", setField("city"));
  fieldRow(dat, tt("address", null, "Dirección"), c.address||"", setField("address"));
  fieldRow(dat, tt("notes", null, "Notas"), c.notes||"", setField("notes"));

  // ── TAGS ───────────────────────────────────────────────────────────────────────────────────────────────
  const tags=section(box, tt("sec_tags", null, "Etiquetas"));
  const tw=el2("div","cttags");
  (c.groups||[]).forEach(g=>{
    const t=el2("span","cttag"); t.appendChild(el2("span",null,g));
    const x=el2("button",null,"✕"); x.title=tt("tag_remove", null, "Quitar esta etiqueta");
    // `groups` REPLACES the whole list (an empty string empties it) — `group` only ever adds, so removing
    // the last tag through it would be a no-op wearing the face of a delete.
    x.onclick=()=>act("update_contact",{contactId:c.id,
      groups:(c.groups||[]).filter(y=>y!==g).join(",")});
    t.appendChild(x); tw.appendChild(t);
  });
  const addT=el2("button","ctaddtag","+ "+tt("tag_add", null, "añadir"));
  addT.onclick=()=>{
    const inp=document.createElement("input"); inp.className="ctin"; inp.style.maxWidth="150px";
    let done=false;
    const fin=(save)=>{ if(done)return; done=true;
      const t=String(inp.value||"").trim();
      if(save && t) act("update_contact",{contactId:c.id,group:t}); else redraw(null); };
    inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                       else if(e.key==="Escape"){e.preventDefault();fin(false);} };
    inp.onblur=()=>fin(true);
    addT.replaceWith(inp); inp.focus();
  };
  tw.appendChild(addT);
  tags.appendChild(tw);

  // ── LINKS — the people you deal with AT a place, and the place a person hangs from ──────────────────────
  const byId={}; (data.contacts||[]).forEach(x=>byId[x.id]=x);
  const parent=c.parentId?byId[c.parentId]:null;
  const kids=(data.contacts||[]).filter(x=>x.parentId===c.id);
  if(parent||kids.length){
    const ln=section(box, tt("sec_links", null, "Conexiones"));
    const jump=(t)=>{ const a=el2("span","ctlink",t.name||t.id);
      a.onclick=()=>{ el._ctDetail=t.id; render(el,data,ctx); }; return a; };
    if(parent){ const r=el2("div","ctfr"); r.appendChild(el2("span","ctfk",tt("linked_to", null, "Conectado a")));
      r.appendChild(jump(parent)); ln.appendChild(r); }
    if(kids.length){ const r=el2("div","ctfr"); r.appendChild(el2("span","ctfk",tt("linked", null, "Conectados")));
      const wrap=el2("span",null,"");
      kids.forEach((k,i)=>{ if(i)wrap.appendChild(document.createTextNode(" · "));
        wrap.appendChild(jump(k)); });
      r.appendChild(wrap); ln.appendChild(r); }
  }

  host.appendChild(box);
}

// ── THE PROVIDER ICONS in the subheader — the house standard (V2-699) ───────────────────────────────────
// Every source visible at a glance: the live one in its own colour, the ones we have not built dimmed and
// INERT. Operator: «el iconito de Google y el de Apple desactivado, para que la gente sepa que se pueden
// conectar varias fuentes de contactos al sistema».
function renderProviderIcons(providers, el, data, ctx){
  const wrap = el2("div","ctconnicons");
  (providers||[]).forEach(p=>{
    const live = !!LIVE_SOURCES[p.id];
    const on = p.status === "connected";
    const btn = el2("button","ctconnicon" + (on?" on":"") + (live?"":" off"));
    const spec = SRC_SVG[p.id];
    if(spec){ btn.style.color = spec.color; btn.appendChild(svgEl(spec.path, {fill:true})); }
    else { btn.appendChild(svgEl(ICO_PEOPLE)); }
    btn.title = (p.label || p.id) + " — " + (!live ? tt("src_soon", null, "aún no disponible")
                                                   : on ? tt("src_connected", null, "conectado")
                                                        : tt("src_off", null, "sin conectar"));
    if(!live){ btn.disabled = true; }
    else { btn.onclick = ()=>{ el._ctScreen = "conn"; el._ctDetail = null; render(el,data,ctx); }; }
    wrap.appendChild(btn);
  });
  return wrap;
}

// ── THE CONNECTORS SCREEN — sources, and the sync box for the one that is linked ────────────────────────
function renderConnectors(el, host, data, ctx){
  const wrap = el2("div","ctconnscreen");
  const redraw = nd=>render(el,(nd&&nd.contacts)?nd:data,ctx);
  const act = async(n,p)=>redraw(await ctx.action(n,p||{}));

  const head = el2("div","ctconnhead");
  head.appendChild(el2("div","ctconntitle", tt("connectors", null, "Conectores")));
  const back = el2("button","ctconnback", "‹ " + tt("title", null, "Contactos"));
  back.onclick = ()=>{ el._ctScreen = null; render(el,data,ctx); };
  head.appendChild(back);
  wrap.appendChild(head);

  const sync = data.sync || {};
  (data.providers||[]).forEach(p=>{
    const live = !!LIVE_SOURCES[p.id];
    const on = p.status === "connected";
    const row = el2("div","ctsrc" + (live?"":" dim"));
    const ic = el2("div","ctsrcic");
    const spec = SRC_SVG[p.id];
    if(spec){ ic.style.color = spec.color; ic.appendChild(svgEl(spec.path,{fill:true})); }
    else { ic.appendChild(svgEl(ICO_PEOPLE)); }
    row.appendChild(ic);
    const tx = el2("div","ctsrctx");
    tx.appendChild(el2("div","ctsrcnm", p.label || p.id));
    const st = el2("div","ctsrcst");
    st.appendChild(el2("span","ctdot" + (on?" ok":"")));
    st.appendChild(document.createTextNode(
      !live ? tt("src_soon", null, "aún no disponible")
            : on ? tt("src_connected", null, "conectado")
                 : tt("src_off", null, "sin conectar")));
    tx.appendChild(st);
    row.appendChild(tx);
    if(live){
      // A CONNECT is the operator's click and nothing else: the consent window only survives inside the
      // gesture that opened it, so the window is opened SYNCHRONOUSLY here and its location filled in
      // afterwards. Awaiting the action first and opening then is what a popup blocker eats (V2-603).
      if(!on){
        const b = el2("button","ctbtn primary", tt("src_connect", null, "Conectar"));
        b.onclick = ()=>{
          const w = window.open("", "_blank");
          ctx.action("connect", {origin: location.origin}).then(r=>{
            if(r && r.ok && r.url){ if(w) w.location = r.url; }
            else if(w){ w.close(); }
            redraw(null);
          });
        };
        row.appendChild(b);
      } else {
        const b = el2("button","ctbtn danger", tt("src_disconnect", null, "Desconectar"));
        b.onclick = ()=>act("disconnect", {provider: p.id});
        row.appendChild(b);
      }
    }
    wrap.appendChild(row);
    if(live && on) wrap.appendChild(renderSyncBox(el, data, ctx, sync, redraw));
  });
  host.appendChild(wrap);
}

function renderSyncBox(el, data, ctx, sync, redraw){
  const box = el2("div","ctsync");
  const top = el2("div","ctsynctop");
  top.appendChild(svgEl(ICO_SYNC));
  top.appendChild(el2("b",null, tt("sync_title", null, "Sincronización")));
  box.appendChild(top);

  // ONE state, said in one line — his own simplification: «quizás quieras simplificar esto de Google a
  // nosotros y nosotros a Google, quitando esas opciones y solo dejando la sincronización activa».
  const dir = el2("div","ctsyncdir");
  dir.appendChild(el2("span","ctsyncarrow", sync.twoWay ? "⇄" : "→"));
  dir.appendChild(el2("span",null, sync.twoWay
    ? tt("sync_two_way", null, "Google y zaelar se mantienen iguales. Lo que cambies aquí —un nombre, un "
        + "teléfono— también cambia en Google.")
    : tt("sync_one_way", null, "De Google hacia zaelar. Trae tus contactos; por ahora no puede devolver "
        + "los cambios que hagas aquí.")));
  box.appendChild(dir);

  if(!sync.twoWay){
    box.appendChild(el2("div","ctwarn", tt("sync_needs_write", null,
      "Para que la sincronización vaya en los dos sentidos hace falta el permiso de escritura de contactos "
      + "en la app de Google Cloud. Mientras no esté, esto solo trae.")));
  }

  const foot = el2("div","ctsyncfoot");
  const go = el2("button","ctbtn primary", tt("sync_now", null, "Sincronizar contactos"));
  go.onclick = async()=>{
    go.disabled = true; go.textContent = tt("syncing", null, "Sincronizando…");
    redraw(await ctx.action("sync_contacts", {}));
  };
  foot.appendChild(go);
  const when = el2("div","ctsyncwhen");
  when.appendChild(el2("div",null, sync.last
    ? tt("sync_last", {when: new Date(sync.last*1000).toLocaleString()},
         "Última vez: " + new Date(sync.last*1000).toLocaleString())
    : tt("sync_never", null, "Todavía no se ha sincronizado")));
  const r = sync.lastResult || {};
  if(sync.last){
    const bits = [];
    if(r.added) bits.push(tt("sync_added", {n:r.added}, r.added + " nuevos"));
    if(r.updated) bits.push(tt("sync_updated", {n:r.updated}, r.updated + " completados"));
    if(r.pushed || r.created) bits.push(tt("sync_pushed", {n:(r.pushed||0)+(r.created||0)},
      ((r.pushed||0)+(r.created||0)) + " enviados a Google"));
    when.appendChild(el2("div",null, bits.length ? bits.join(" · ")
      : tt("sync_nothing", null, "sin cambios")));
  }
  foot.appendChild(when);
  box.appendChild(foot);
  return box;
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
let _T = null;
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.contactos."+key, params); if(s && s!=="widgets.contactos."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

// A FUNCTION, not the module-level map it replaces: a table built at IMPORT time freezes its labels in
// whatever language was active when the module first loaded, and survives every later switch (V2-694).
function kindLabel(kind){
  switch(String(kind || "")){
    case "person":  return tt("kind_person", null, "persona");
    case "place":   return tt("kind_place", null, "sitio");
    case "company": return tt("kind_company", null, "empresa");
    default:        return "";
  }
}

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();

  // A VIEW PUSHED FROM VOICE (`show_view`/`show_contact`). Applied only when its token MOVES — a plain data
  // refresh never yanks the group the operator is reading, but asking twice for the same filter still lands,
  // because the token is a counter and not the filter itself (the agenda's V2-540 contract).
  const pushed=data.view;
  if(pushed && pushed.n!==el._ctViewN){
    el._ctViewN=pushed.n;
    const sel=pushed.sel||{};
    if(sel.contactId){ el._ctDetail=sel.contactId; }
    else{
      el._ctDetail=null;
      el._ctGroup=sel.group||"";
      el._ctCity=sel.city||"";
      el._ctFav=!!sel.favorites;
      el._ctQuery=sel.query||"";
    }
  }
  const st={group:el._ctGroup||"", city:el._ctCity||"", fav:!!el._ctFav, query:el._ctQuery||"",
           kind:el._ctKind||""};

  el.className="hb-contactos";
  el.textContent="";                                          // reset (no innerHTML)

  const contacts=data.contacts||[];
  const redraw=nd=>render(el,(nd&&nd.contacts)?nd:data,ctx);

  // ── HOUSE HEADER BAR — brand disc, content title, search, count ────────────────────────────────────────
  const bar=el2("div","ctbar");
  const brand=el2("div","ctbrand"); brand.appendChild(svgEl(ICO_PEOPLE)); bar.appendChild(brand);
  bar.appendChild(el2("div","cttitle",tt("title", null, "Contactos")));
  const sb=el2("div","ctsearch");
  sb.appendChild(el2("span",null,"\u{1F50D}"));
  const q=document.createElement("input");
  q.placeholder=tt("search_ph", null, "Buscar por nombre, ciudad, etiqueta o cuenta…");
  q.value=st.query;
  q.oninput=()=>{ el._ctQuery=q.value; const keep=q.value; el._ctScreen=null; render(el,data,ctx);
    const nq=el.querySelector(".ctsearch input");
    if(nq){ nq.focus(); nq.setSelectionRange(keep.length,keep.length); } };
  sb.appendChild(q);
  bar.appendChild(sb);
  bar.appendChild(el2("span","ctn",tt("count", {n: data.count||0}, (data.count||0)+" en el directorio")));
  el.appendChild(bar);

  // ── HOUSE SUBHEADER BAND — kind tabs left, provider icons + Conectores right ────────────────────────────
  // The tabs filter by KIND; the sidebar filters by his own group labels. Two different axes on purpose —
  // putting «Todos / ★ Favoritos» in both is the duplication he reported as «un menú ahí suelto».
  const views=el2("div","ctviews");
  [["", tt("all", null, "Todos")], ["person", tt("kind_people", null, "Personas")],
   ["place", tt("kind_places", null, "Sitios")], ["company", tt("kind_companies", null, "Empresas")]]
   .forEach(([id,label])=>{
    // While the connectors screen owns the content NO tab is the one on screen, so none is lit and none is
    // clickable. The chosen kind survives underneath and comes back when the screen closes (agenda V2-679).
    const t=el2("button","cttab"+(!el._ctScreen && (el._ctKind||"")===id?" on":""),label);
    t.dataset.kind=id; t.disabled=!!el._ctScreen;
    t.onclick=()=>{ el._ctKind=id; el._ctDetail=null; render(el,data,ctx); };
    views.appendChild(t);
  });
  const right=el2("div","ctviewsright");
  right.appendChild(renderProviderIcons(data.providers||[], el, data, ctx));
  const connBtn=el2("button","ctconnbtn"+(el._ctScreen?" on":""));
  connBtn.appendChild(svgEl(ICO_PLUG));
  connBtn.appendChild(el2("span",null,tt("connectors", null, "Conectores")));
  connBtn.title=tt("connectors_hint", null, "Qué fuentes de contactos están conectadas");
  connBtn.onclick=()=>{ el._ctScreen = el._ctScreen ? null : "conn"; el._ctDetail=null; render(el,data,ctx); };
  right.appendChild(connBtn);
  views.appendChild(right);
  el.appendChild(views);

  if(el._ctScreen === "conn"){
    renderConnectors(el, el, data, ctx);
    return;
  }

  const cols=el2("div","ctcols");

  // ── SIDEBAR ────────────────────────────────────────────────────────────────────────────────────────────
  const side=el2("div","ctside");
  const gbtn=(label,id,count)=>{ const b=el2("button","ctg"+((st.group||"")===id?" on":""));
    b.append(el2("span",null,label)); if(count!=null)b.append(el2("span","ctgc",String(count)));
    b.onclick=()=>{ el._ctGroup=id; el._ctDetail=null; el._ctCity=""; render(el,data,ctx); };
    return b; };
  const inKind=filtered(data,{group:"",city:"",fav:false,query:"",kind:st.kind});
  side.appendChild(gbtn(tt("all", null, "Todos"),"",inKind.length));
  side.appendChild(gbtn(tt("favs", null, "★ Favoritos"),"__fav",data.favorites_count||0));
  const groups=data.groups||[];
  if(groups.length){
    side.appendChild(el2("div","ctsep"));
    side.appendChild(el2("div","ctsidelbl",tt("side_groups", null, "Grupos")));
    groups.forEach(g=>side.appendChild(gbtn(g.id,g.id,g.count)));
  }
  side.appendChild(el2("div","ctsep"));
  const addB=el2("button","ctact","+ "+tt("new_contact", null, "Nuevo contacto"));
  addB.onclick=()=>{
    const inp=document.createElement("input"); inp.className="ctin";
    inp.placeholder=tt("new_name_ph", null, "nombre…");
    let done=false;
    const fin=async(save)=>{ if(done)return; done=true;
      const t=String(inp.value||"").trim();
      if(save && t){ const nd=await ctx.action("add_contact",{name:t}); redraw(nd); }
      else redraw(null); };
    inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                       else if(e.key==="Escape"){e.preventDefault();fin(false);} };
    inp.onblur=()=>fin(true);
    addB.replaceWith(inp); inp.focus();
  };
  side.appendChild(addB);
  // NO import button here. It lived in this rail for one build and the operator had it removed: importing
  // is a CONNECTOR gesture, and in this product every connector gesture is reached the same way — the plug
  // button in the subheader. A second door to it would be a second place to keep in sync and a second
  // vocabulary for the same idea.
  cols.appendChild(side);

  const main=el2("div","ctmain");
  const detail=el._ctDetail ? contacts.find(c=>c.id===el._ctDetail) : null;

  if(!contacts.length){
    main.appendChild(el2("div","ctempty",
      tt("empty_1", null, "El directorio está vacío. Dile a Zaelar: «apúntame el restaurante Elfo On de Soria como favorito» ")+
      tt("empty_2", null, "o «añade a Marta, amiga del trabajo».")));
  } else if(detail){
    renderDetail(el,main,data,ctx,detail);
  } else {
    // SUBHEADER — only the filters that vary with the selection. The favourites toggle is GONE: the sidebar
    // already has «★ Favoritos» and two controls for one fact is how the old layout read as a loose menu.
    const inGroup=filtered(data,{group:st.group,city:"",fav:false,query:"",kind:st.kind});
    const cities={}; inGroup.forEach(c=>{ const ct=(c.city||"").trim(); if(ct)cities[normJs(ct)]=ct; });
    const cityNames=Object.values(cities).sort();
    if(cityNames.length>1){
      const fil=el2("div","ctfil");
      cityNames.forEach(ct=>{
        const on=normJs(st.city)===normJs(ct);
        const b=el2("button","ctchip"+(on?" on":""),ct);
        b.onclick=()=>{ el._ctCity=on?"":ct; render(el,data,ctx); };
        fil.appendChild(b);
      });
      main.appendChild(fil);
    }

    const rows=filtered(data,st);
    const list=el2("div","ctlist");
    if(!rows.length){
      list.appendChild(el2("div","ctempty",tt("no_match", null, "Nada que casar con ese filtro.")));
    }
    rows.forEach(c=>{
      const r=el2("div","ctrow");
      r.appendChild(avatar(c,false));
      const tx=el2("div","ctrtx");
      tx.appendChild(el2("span","ctnm",c.name||c.id));
      const sub=preferredLine(c);
      if(sub) tx.appendChild(el2("span","ctsub",sub));
      r.appendChild(tx);
      if(c.city)r.appendChild(el2("span","ctci",c.city));
      const gs=el2("span","ctgs");
      (c.groups||[]).slice(0,2).forEach(g=>gs.appendChild(el2("span","ctpill",g)));
      r.appendChild(gs);
      r.appendChild(favBtn(c,ctx,el,data));
      r.onclick=()=>{ el._ctDetail=c.id; render(el,data,ctx); };
      list.appendChild(r);
    });
    main.appendChild(list);
  }

  cols.appendChild(main);
  el.appendChild(cols);

  // A failed action says so where the gesture happened, instead of leaving the card looking unchanged.
  if(data.ok===false && data.error){
    const w=el2("div","ctnote",String(data.error)); w.style.color="var(--hb-danger,#D9534F)";
    el.appendChild(w);
  }
}
