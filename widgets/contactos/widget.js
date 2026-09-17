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
  // V2-714 — «en el widget de contactos quiero que aparezcan los iconos de WhatsApp y de Telegram y que se
  // vea si están conectados o no». They are message connectors AND contact sources now, and the same
  // connector deliberately lives in both cards: «eso le da claridad al asunto».
  telegram: {color:"#26A5E4", path:"M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"},
  whatsapp: {color:"#25D366", path:"M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a12.8 12.8 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z"},
  meshkore: {color:"var(--hb-accent,#4f7cff)", path:"M12 2a3 3 0 0 1 1 5.83V10h4a3 3 0 0 1 3 3v1.17a3 3 0 1 1-2 0V13a1 1 0 0 0-1-1h-4v2.17a3 3 0 1 1-2 0V12H7a1 1 0 0 0-1 1v1.17a3 3 0 1 1-2 0V13a3 3 0 0 1 3-3h4V7.83A3 3 0 0 1 12 2z"},
};

//: The only source with a connector behind it today. Everything else stays VISIBLE but INERT — no button,
//: no click handler — until it lands in `connectors/contacts/providers.py`. «No lo has enlazado» and «no lo
//: hemos construido» are different sentences and the strip has to be able to say both.
const LIVE_SOURCES = {"google-contacts": true, telegram: true, whatsapp: true, meshkore: true};

//: Sources that IMPORT (V2-714). They carry one switch, not two: «no vamos a poner dos opciones… un botón
//: de sincronizar que se queda activado». The switch brings contacts AND groups in the same pass, and the
//: server refuses it when the connector is not linked, so the card never promises what it cannot do.
const IMPORT_SOURCES = {telegram: true, whatsapp: true, meshkore: true};

function injectStyles(){
  if(document.getElementById("hb-contactos-css"))return;
  const s=document.createElement("style"); s.id="hb-contactos-css"; s.textContent=`
  .hb-contactos{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:100%;box-sizing:border-box}
  .hb-contactos button{font-family:inherit}
  .hb-contactos .ctsearch{flex:1 1 200px;min-width:140px;max-width:380px;display:flex;align-items:center;gap:6px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:5px 12px;background:var(--hb-bg,#fff)}
  .hb-contactos .ctsearch:focus-within{border-color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctsearch span{font-size:12px;color:var(--hb-muted-2,#7d8a9c);flex:0 0 auto}
  .hb-contactos .ctsearch input{border:none;outline:none;background:none;color:var(--hb-ink,#0d1622);font-size:13px;width:100%;padding:0}
  .hb-contactos .ctcols{display:grid;grid-template-columns:188px 1fr;gap:14px;align-items:start}
  @media(max-width:600px){.hb-contactos .ctcols{grid-template-columns:1fr}}

  /* ── THE ONE BAR (V2-715) ───────────────────────────────────────────────────────────────────────
     Operator, 2026-09-17: «de estas tres líneas iniciales del widget —la barra negra, la barra de
     búsqueda y la barra de selección de All People Places— todo eso hay que convertirlo en dos barras».
     The window chrome the canvas draws is bar ONE and already says «Contactos» beside the widget's own
     mark, so a brand disc and a title under it were the same sentence twice; the kind tabs moved into the
     rail, where they are DERIVED from what the directory holds instead of being four fixed words. What is
     left is the one row that could not live anywhere else: search, the sources, and the door to them. */
  .hb-contactos .ctbar{display:flex;align-items:center;gap:var(--sp-2,8px);flex:0 0 auto;min-width:0;
    border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.06));
    padding:0 0 var(--sp-2,8px);margin-bottom:var(--sp-3,12px)}
  .hb-contactos .ctviewsright{margin-left:auto;display:flex;align-items:center;gap:8px;flex:0 0 auto}
  .hb-contactos .ctconnicons{display:flex;align-items:center;gap:4px}
  .hb-contactos .ctconnicon{width:var(--hb-icon-h,28px);height:var(--hb-icon-h,28px);border-radius:var(--hb-r-s,8px);
    border:0;background:none;cursor:pointer;display:flex;align-items:center;justify-content:center;opacity:.72}
  .hb-contactos .ctconnicon svg{width:15px;height:15px;display:block}
  .hb-contactos .ctconnicon:hover:not(:disabled){opacity:1;background:var(--hb-bg-soft,#f4f7fb)}
  .hb-contactos .ctconnicon.on{opacity:1}
  .hb-contactos .ctconnicon.off{opacity:.4;cursor:default}
  /* SELECTED — the directory is showing only this platform. The accent ring is the same «this is the one
     on screen» language the tabs used to wear, moved to the control that now owns that job. */
  .hb-contactos .ctconnicon.sel{opacity:1;background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);
    box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent)}
  /* The plug is an ICON, not a labelled button: the operator's «ocupa mucho espacio», and with the icons
     beside it already saying «sources», the word was the third time this row said the same thing. */
  .hb-contactos .ctplug{width:var(--hb-ctl-h-sm,32px);height:var(--hb-ctl-h-sm,32px);flex:0 0 auto;
    border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);color:var(--hb-muted,#5b6b82);
    border-radius:var(--hb-r-s,8px);cursor:pointer;display:flex;align-items:center;justify-content:center}
  .hb-contactos .ctplug svg{width:15px;height:15px;display:block}
  .hb-contactos .ctplug:hover,.hb-contactos .ctplug.on{border-color:var(--hb-accent,#3D6FE0);
    color:var(--hb-accent,#3D6FE0)}

  /* ── THE CRUMB — what is being filtered right now, and how to drop it ──────────────────────────── */
  .hb-contactos .ctcrumb{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:11.5px;
    color:var(--hb-muted-2,#7d8a9c)}
  .hb-contactos .ctcrumb .ctcx{display:inline-flex;align-items:center;gap:6px;border-radius:999px;
    border:1px solid var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0);background:none;
    padding:2px 9px;font-size:11.5px;cursor:pointer;font-weight:600}
  .hb-contactos .ctcount{margin-left:auto;font-family:ui-monospace,Menlo,monospace}
  .hb-contactos .ctmore{border:1px dashed var(--hb-line,#d6dde8);background:none;border-radius:10px;
    padding:8px;font-size:12px;cursor:pointer;color:var(--hb-muted,#5b6b82);width:100%}
  .hb-contactos .ctmore:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0);
    border-style:solid}
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
  /* ONE CARD PER SOURCE. The account row and everything that source owns (its sync panel) live INSIDE the
     same box — a panel floating beside its account reads as a second, unrelated feature. */
  .hb-contactos .ctsrcbox{border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;
    background:var(--hb-bg,#fff);overflow:hidden}
  .hb-contactos .ctsrcbox.dim{opacity:.55}
  .hb-contactos .ctsrcbox.on{border-color:color-mix(in srgb,var(--hb-accent,#3D6FE0) 30%,var(--hb-line,#e3e8f0))}
  .hb-contactos .ctsrc{display:flex;align-items:center;gap:11px;padding:11px 13px}
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

  /* ── THE SYNC PANEL — the connected source's own half of its card, never a box of its own ──────── */
  .hb-contactos .ctsync{border-top:1px solid var(--hb-line,#e3e8f0);padding:12px 13px 13px;
    background:var(--hb-bg-soft,#f6f8fb);display:flex;flex-direction:column;gap:9px}
  .hb-contactos .ctsynctop{display:flex;align-items:center;gap:8px}
  .hb-contactos .ctsynctop svg{width:14px;height:14px;display:block;color:var(--hb-muted-2,#7d8a9c)}
  .hb-contactos .ctsynctop b{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.09em;
    color:var(--hb-muted-2,#7d8a9c)}
  .hb-contactos .ctsyncdir{display:flex;align-items:flex-start;gap:9px;font-size:12.5px;line-height:1.5;
    color:var(--hb-muted,#5b6b82)}
  .hb-contactos .ctsyncarrow{font-family:ui-monospace,Menlo,monospace;color:var(--hb-accent,#3D6FE0);
    font-weight:700;flex:0 0 auto}
  /* THE SWITCH. A permanent state wears a switch, not a button: a button says «do it once» and that is
     exactly the reading the operator rejected. Local to this widget for now — the day a second connector
     panel needs one it gets promoted to components.css under the hb- prefix. */
  .hb-contactos .ctswrow{display:flex;align-items:center;gap:10px;cursor:pointer;
    border:0;background:none;padding:0;width:100%;text-align:left;color:inherit}
  .hb-contactos .ctsw{width:34px;height:20px;flex:0 0 auto;border-radius:999px;position:relative;
    background:var(--hb-line,#e3e8f0);transition:background .14s ease}
  .hb-contactos .ctsw::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;
    border-radius:50%;background:var(--hb-bg,#fff);transition:transform .14s ease;
    box-shadow:0 1px 2px rgba(0,0,0,.3)}
  .hb-contactos .ctswrow.on .ctsw{background:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctswrow.on .ctsw::after{transform:translateX(14px)}
  .hb-contactos .ctswrow[disabled]{opacity:.5;cursor:default}
  .hb-contactos .ctswtx{font-size:13px;font-weight:600}
  .hb-contactos .ctswsub{font-size:11.5px;color:var(--hb-muted-2,#7d8a9c);margin-left:auto;text-align:right}
  .hb-contactos .ctsyncfoot{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  /* ⚠️ NOT ctlink — that class already means «jump to a linked contact» further down this sheet, and a
     second meaning on one surface loses to the first one silently (measured: the accent underline won). */
  .hb-contactos .ctquiet{border:0;background:none;padding:0;font-size:12px;font-weight:600;cursor:pointer;
    color:var(--hb-muted,#5b6b82)}
  .hb-contactos .ctquiet:hover{color:var(--hb-accent,#3D6FE0);text-decoration:underline}
  .hb-contactos .ctquiet[disabled]{opacity:.5;cursor:default;text-decoration:none}
  .hb-contactos .ctsyncwhen{font-size:11.5px;color:var(--hb-muted-2,#7d8a9c);margin-left:auto;text-align:right}
  .hb-contactos .ctwarn{font-size:11.5px;line-height:1.5;color:var(--hb-warn,#E0A23D);
    border-left:2px solid var(--hb-warn,#E0A23D);padding-left:9px}

  /* SIDEBAR — a real panel with a ground of its own, not four buttons floating on the canvas. */
  .hb-contactos .ctside{display:flex;flex-direction:column;gap:3px;background:var(--hb-bg-soft,#f6f8fb);border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;padding:7px;max-height:62vh;overflow:auto}
  .hb-contactos .ctside .ctgmore{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);font-size:11.5px;
    cursor:pointer;text-align:left;padding:3px 9px}
  .hb-contactos .ctside .ctgmore:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctg .ctgi{flex:0 0 auto;font-size:12px;opacity:.85}
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
  /* A phone/e-mail ROW: the label is a chip, not a column — a contact may have three of them and a fixed
     key column would push the number itself into a narrow strip. */
  .hb-contactos .ctdrow{display:flex;gap:8px;align-items:center;padding:3px 0;font-size:13px;min-height:24px}
  .hb-contactos .ctdrow .ctdl{flex:0 0 auto;font-size:10px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--hb-muted-2,#9aa7b8);border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;
    padding:1px 7px;cursor:pointer;background:none}
  .hb-contactos .ctdrow .ctdl:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctdrow .ctfv{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
  .hb-contactos .ctdrow .ctchx{opacity:0}
  .hb-contactos .ctdrow:hover .ctchx{opacity:1}
  .hb-contactos .ctpick{border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:3px 7px;
    font-size:12.5px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);font-family:inherit;max-width:100%}
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

// ── WHICH CONTACTS ARE ON SCREEN (V2-715) ───────────────────────────────────────────────────────────────
// Two independent axes, and they are independent on purpose: the RAIL picks ONE thing to look at (all,
// favourites, a kind, a label, a city, the hidden ones), and the PLATFORM narrows whatever that is. His
// own words for the second one: «cuando entramos en Telegram quiero ver solo los contactos de Telegram».
// A mirror of `model.py::matches` / `model.py::source_matches`, marked as such — this one is the same
// decision made client-side over a directory the card already holds whole, and the two must never drift.
const KIND_ORDER = ["person", "company", "place", "group", "agent"];

function kindOf(c){ const k=String(c.kind||"person"); return KIND_ORDER.indexOf(k)<0 ? "person" : k; }

function srcKey(v){
  const n=normJs(v);
  return ({"google-contacts":"google","google contacts":"google","googlecontacts":"google","gmail":"google",
           "google-people":"google","apple":"icloud"})[n] || n;
}

// Mirrors `model.source_matches`: where the row CAME FROM and where he can REACH the person. A contact he
// typed here and later matched to a Telegram account is as much a Telegram contact as an imported one.
function sourceMatch(c, source){
  const s=srcKey(source);
  if(!s) return true;
  if(srcKey(c.source)===s || srcKey(c.platform)===s) return true;
  for(const k in (c.externalIds||{})) if(srcKey(k)===s) return true;
  if(s==="google" && String(c.googleId||"").trim()) return true;
  return (c.channels||[]).some(ch=>srcKey(ch.platform)===s);
}

function cityMatch(want, c){
  const cw=normJs(want), cn=normJs(c.city);
  return cw ? (cn.includes(cw)||(!!cn&&cw.includes(cn))) : true;
}

function detailValues(c, key){
  const rows=(c[key]||[]).map(r=>String((r&&r.value)||"")).filter(Boolean);
  const head=String((key==="phones"?c.phone:c.email)||"").trim();
  return rows.length ? rows : (head?[head]:[]);
}

function haystack(c){
  return normJs([c.name,c.city,c.address,c.notes,(c.groups||[]).join(" "),
    detailValues(c,"phones").join(" "), detailValues(c,"emails").join(" "),
    (c.channels||[]).map(ch=>ch.handle||"").join(" ")].join(" "));
}

// ── THE FILTER: every axis at once, because the VOICE can set several ───────────────────────────────────
// A click on the rail means «show me THIS», so it sets one axis and clears the others. A pushed
// `show_view` does not: «mi restaurante favorito en Barcelona» is group + city + favourites in one
// sentence, and the spoken answer is already computed over all three. A card that could hold only one
// would show a different set from the one it had just read out — the two-surfaces-disagreeing failure
// this widget's own digest exists to stop (V2-576). Measured: a single-axis rail broke exactly that case.
const AXES = ["fav", "hidden", "kind", "group", "city"];

function selOf(el){ return el._ctFilter || {}; }

function selEmpty(f){ return !AXES.some(a=>f && f[a]); }

function bySel(list, f){
  if(!f) return list;
  let out = list;
  if(f.fav) out = out.filter(c=>c.favorite);
  if(f.kind) out = out.filter(c=>kindOf(c)===f.kind);
  if(f.group) out = out.filter(c=>groupMatch(f.group,c));
  if(f.city) out = out.filter(c=>cityMatch(f.city,c));
  return out;                                    // `hidden` chooses the POOL, not a predicate — see basePool
}

// The pool the RAIL counts over: everything the platform filter allows. Counting over the whole archive
// instead would paint a rail whose numbers disagree with what a click on it actually shows.
function basePool(data, el){
  const hidden = !!selOf(el).hidden;
  const list = (hidden ? (data.hidden_rows||[]) : (data.contacts||[])).slice();
  const src = el._ctSource||"";
  return src ? list.filter(c=>sourceMatch(c,src)) : list;
}

function rowsOf(data, el){
  let out = bySel(basePool(data,el), selOf(el));
  const q = normJs(el._ctQuery||"");
  if(q) out = out.filter(c=>haystack(c).includes(q));
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

// ── SEVERAL phones, several e-mails, each with a free label (V2-715) ───────────────────────────────────
// A company is not one number: a switchboard, a mobile and a billing line are three facts about the same
// entry, and the label is what makes the difference sayable («el fijo», «la centralita»). Every gesture
// sends the WHOLE list through `update_contact`, because `phone`/`email` are only the head of it and the
// store keeps the two in step — writing one without the other would be undone on the next read.
function detailRows(box, el, data, ctx, c, key, title, addLabel, ph){
  const redraw=nd=>render(el,(nd&&nd.contacts)?nd:data,ctx);
  const act=async(name,payload)=>redraw(await ctx.action(name,payload));
  const rows=(c[key]||[]).slice();
  const head=String((key==="phones"?c.phone:c.email)||"").trim();
  const list=rows.length ? rows : (head ? [{value:head,label:""}] : []);
  const put=(next)=>act("update_contact",{contactId:c.id,[key]:next});

  const sec=el2("div","ctdsec");
  const h=el2("h4",null,title); sec.appendChild(h);
  list.forEach((rw,i)=>{
    const r=el2("div","ctdrow");
    const lb=el2("button","ctdl", String(rw.label||"").trim() || tt("label_add", null, "etiqueta"));
    lb.title=tt("label_hint", null, "Pulsa para decir de qué es: móvil, centralita, trabajo…");
    lb.onclick=()=>{
      const inp=document.createElement("input"); inp.className="ctin"; inp.style.maxWidth="120px";
      inp.value=String(rw.label||"");
      let done=false;
      const fin=(save)=>{ if(done)return; done=true;
        if(!save) return redraw(null);
        const next=list.map((x,j)=>j===i?{value:x.value,label:String(inp.value||"").trim()}:x);
        put(next); };
      inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                         else if(e.key==="Escape"){e.preventDefault();fin(false);} };
      inp.onblur=()=>fin(true);
      lb.replaceWith(inp); inp.focus(); inp.select();
    };
    r.appendChild(lb);
    const v=el2("span","ctfv",String(rw.value||""));
    v.title=tt("edit_hint", null, "Pulsa para editar");
    editable(v, v, rw.value, val=>{
      const t=String(val).trim();
      if(t===String(rw.value||"")) return redraw(null);
      const next=list.map((x,j)=>j===i?{value:t,label:x.label}:x).filter(x=>x.value);
      put(next);
    });
    r.appendChild(v);
    const x=el2("button","ctchx","✕");
    x.title=tt("detail_remove", null, "Quitar");
    x.onclick=()=>put(list.filter((_,j)=>j!==i));
    r.appendChild(x);
    sec.appendChild(r);
  });
  if(!list.length){
    // EMPTY IS A ROW (V2-699's rule, kept): «no muestra ni siquiera los campos básicos, aunque sean
    // vacíos, para que se vea que es una ficha de un contacto». A section that disappeared when there was
    // nothing in it would make «no tengo su teléfono» and «esta ficha no enseña teléfonos» look alike.
    const r=el2("div","ctdrow"); r.appendChild(el2("span","ctfv void","—")); sec.appendChild(r);
  }
  const add=el2("button","ctaddtag",addLabel);
  add.onclick=()=>{
    const inp=document.createElement("input"); inp.className="ctin"; inp.style.maxWidth="190px";
    inp.placeholder=ph;
    let done=false;
    const fin=(save)=>{ if(done)return; done=true;
      const t=String(inp.value||"").trim();
      if(save && t) act("add_" + (key==="phones"?"phone":"email"),
                        {contactId:c.id, [key==="phones"?"phone":"email"]:t});
      else redraw(null); };
    inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                       else if(e.key==="Escape"){e.preventDefault();fin(false);} };
    inp.onblur=()=>fin(true);
    add.replaceWith(inp); inp.focus();
  };
  sec.appendChild(add);
  box.appendChild(sec);
  return sec;
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
  // HIDE, not delete (V2-714's rule, reachable at last): a row that came from a platform and is deleted
  // here comes straight back on the next import, so «quítalo de la lista» has to be the hiding one — and
  // the same button brings it back from the rail's «Ocultos».
  const hid=!!c.hidden;
  const hb=el2("button","ctdel", hid ? "◌ "+tt("unhide", null, "Devolver al directorio")
                                     : "◌ "+tt("hide", null, "Ocultar"));
  hb.title = hid ? tt("unhide_hint", null, "Vuelve a salir en el directorio")
                 : tt("hide_hint", null, "Lo quita de la lista sin borrarlo, y la siguiente importación no lo vuelve a traer");
  hb.onclick=()=>act("hide_contact",{contactId:c.id,hidden:!hid}).then(()=>{ el._ctDetail=null; });
  hb.style.marginLeft="auto";
  bar.appendChild(hb);
  const del=el2("button","ctdel",tt("delete", null, "Borrar"));
  del.style.marginLeft="0";
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
  // V2-715 — «varios teléfonos que estén vinculados a la misma empresa». Each list is its own section,
  // ABOVE the single-valued fields: the list is the truth and the scalar is only its head
  // (`model.normalize`), so the card always sends the WHOLE list — an edit that moved only the scalar
  // would be undone by the next normalisation.
  detailRows(box, el, data, ctx, c, "phones", tt("sec_phones", null, "Teléfonos"),
             tt("add_phone", null, "+ teléfono"), tt("phone_ph", null, "número…"));
  detailRows(box, el, data, ctx, c, "emails", tt("sec_emails", null, "Correos"),
             tt("add_email", null, "+ correo"), tt("email_ph", null, "dirección…"));
  const dat=section(box, tt("sec_data", null, "Datos"));
  const setField=(key)=>(v)=>{ const t=String(v).trim();
    if(t===String(c[key]||"")) return redraw(null);
    const p={contactId:c.id};
    // An EMPTY string does not clear through `update_contact` — that guard exists so a model omitting a
    // field cannot wipe it. The card is a deliberate gesture, so it says `clear` instead of relying on "".
    if(!t) p.clear=key; else p[key]=t;
    act("update_contact",p); };
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
  const ln=section(box, tt("sec_links", null, "Conexiones"));
  const jump=(t)=>{ const a=el2("span","ctlink",t.name||t.id);
    a.onclick=()=>{ el._ctDetail=t.id; render(el,data,ctx); }; return a; };
  if(kids.length){ const r=el2("div","ctfr"); r.appendChild(el2("span","ctfk",tt("linked", null, "Conectados")));
    const wrap=el2("span",null,"");
    kids.forEach((k,i)=>{ if(i)wrap.appendChild(document.createTextNode(" · "));
      wrap.appendChild(jump(k)); });
    r.appendChild(wrap); ln.appendChild(r); }
  // …and the link is EDITABLE from here (V2-715). `link_contact` existed from birth and had no control
  // behind it, so «cuatro personas vinculadas a la misma empresa» was a sentence only the voice could say.
  const lr=el2("div","ctfr");
  lr.appendChild(el2("span","ctfk",tt("linked_to", null, "Conectado a")));
  const pick=document.createElement("select");
  pick.className="ctpick";
  const none=document.createElement("option");
  none.value=""; none.textContent=tt("link_none", null, "— sin conexión —");
  pick.appendChild(none);
  // Companies and places only: a person hangs from the company or the restaurant where you deal with her,
  // never from another person — and a 2 688-row menu is not a chooser.
  (data.contacts||[]).filter(x=>x.id!==c.id && (kindOf(x)==="company"||kindOf(x)==="place"))
    .sort((a,b)=>normJs(a.name)<normJs(b.name)?-1:1).slice(0,300)
    .forEach(x=>{ const o=document.createElement("option"); o.value=x.id;
                  o.textContent=(x.name||x.id)+(x.city?" · "+x.city:""); pick.appendChild(o); });
  if(parent && !Array.from(pick.options).some(o=>o.value===parent.id)){
    const o=document.createElement("option"); o.value=parent.id; o.textContent=parent.name||parent.id;
    pick.appendChild(o);
  }
  pick.value=c.parentId||"";
  pick.onchange=()=>act("link_contact",{contactId:c.id,parentId:pick.value});
  lr.appendChild(pick);
  ln.appendChild(lr);

  host.appendChild(box);
}

// ── THE PROVIDER ICONS — a FILTER for a linked source, a door for one that is not (V2-715) ─────────────
// The operator's correction, 2026-09-17: «cuando entramos en Telegram quiero ver solo los contactos de
// Telegram… ya tenemos el botón de conectores para manejar la sincronización». So the icon stopped being
// a second door to the connectors screen — which is what V2-699 made it, and what made two controls on
// this row do one thing — and became the platform filter. It still opens the screen when the source is
// LINKABLE but not linked, because there is nothing to filter and «conéctalo» is the only useful answer.
//
// Three states remain three different sentences (the house standard): full colour = linked, dimmed = built
// and not linked, `.off` + disabled = no connector exists at all.
function renderProviderIcons(providers, el, data, ctx){
  const wrap = el2("div","ctconnicons");
  (providers||[]).forEach(p=>{
    const live = !!LIVE_SOURCES[p.id];
    const on = p.status === "connected";
    const sel = !!el._ctSource && srcKey(el._ctSource) === srcKey(p.id);
    const btn = el2("button","ctconnicon" + (on?" on":"") + (live?"":" off") + (sel?" sel":""));
    const spec = SRC_SVG[p.id];
    if(spec){ btn.style.color = spec.color; btn.appendChild(svgEl(spec.path, {fill:true})); }
    else { btn.appendChild(svgEl(ICO_PEOPLE)); }
    btn.title = (p.label || p.id) + " — " + (!live ? tt("src_soon", null, "aún no disponible")
                                                   : !on ? tt("src_off_connect", null, "sin conectar — pulsa para conectarlo")
                                                   : sel ? tt("src_filter_off", null, "quitar el filtro")
                                                         : tt("src_filter_on", null, "ver solo estos contactos"));
    if(!live){ btn.disabled = true; }
    else if(!on){ btn.onclick = ()=>{ el._ctScreen = "conn"; el._ctDetail = null; render(el,data,ctx); }; }
    else { btn.onclick = ()=>{
      el._ctSource = sel ? "" : p.id;
      el._ctDetail = null; el._ctScreen = null; el._ctShown = 0; render(el,data,ctx); }; }
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
    // The CARD is the source; the row is only its first line. Everything that belongs to this account —
    // today the sync panel — goes inside this same box, so it reads as «what Google does here» instead of
    // as a loose feature sitting next to it.
    const box = el2("div","ctsrcbox" + (live?"":" dim") + (on?" on":""));
    const row = el2("div","ctsrc");
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
    if(live && IMPORT_SOURCES[p.id]){
      // V2-714 — an IMPORT source. It is not connected from here (Telegram and WhatsApp are linked in
      // Mensajería, MeshKore in its own tab), so this box carries the one thing that IS this card's
      // business: whether its address book keeps coming in. The row says where to go when it is not.
      if(!on){
        const hint = el2("div","ctsrcst", tt("src_link_in_messages", null,
          "Conéctalo en la tarjeta de Mensajes y vuelve aquí"));
        row.appendChild(hint);
      }
    } else if(live){
      // A CONNECT is the operator's click and nothing else: the consent window only survives inside the
      // gesture that opened it, so the window is opened SYNCHRONOUSLY here and its location filled in
      // afterwards. Awaiting the action first and opening then is what a popup blocker eats (V2-603).
      if(!on){
        const busy = el._ctConnecting === p.id;
        const b = el2("button","ctbtn primary", busy ? tt("src_connecting", null, "Abriendo Google…")
                                                     : tt("src_connect", null, "Conectar"));
        b.disabled = busy;
        // `ctx.connect` owns the window AND the noticing (V2-700): it opens the popup inside this click,
        // then watches for the callback page's message, for the window closing, and polls as a backstop —
        // so the card stops offering «Conectar» the moment the token lands, without the operator touching
        // anything. Doing it here by hand is what left two widgets with two different behaviours.
        b.onclick = async ()=>{
          el._ctConnecting = p.id; redraw(null);
          const r = await ctx.connect("connect", {origin: location.origin},
                                      {family: "contactos", onDone: ()=>{ el._ctConnecting = null; }});
          if(!(r && r.ok)){
            el._ctConnecting = null;
            el._ctConnErr = (r && r.error) || tt("src_connect_failed", null,
              "No pude abrir la ventana de Google. Revisa el conector en Configuración.");
            redraw(null);
          }
        };
        row.appendChild(b);
      } else {
        const b = el2("button","ctbtn danger", tt("src_disconnect", null, "Desconectar"));
        b.onclick = ()=>act("disconnect", {provider: p.id});
        row.appendChild(b);
      }
    }
    box.appendChild(row);
    if(live && on && IMPORT_SOURCES[p.id]){
      box.appendChild(renderImportBox(el, data, ctx, p, redraw));
    } else if(live && on){
      // A connection that just landed clears the «connecting» state with it — otherwise the button would
      // come back as «Abriendo Google…» on the very render that proves it worked.
      el._ctConnecting = null; el._ctConnErr = "";
      box.appendChild(renderSyncBox(el, data, ctx, sync, redraw));
    }
    wrap.appendChild(box);
  });
  if(el._ctConnErr){
    const e = el2("div","ctwarn", String(el._ctConnErr));
    e.style.color = "var(--hb-danger,#D9534F)";
    e.style.borderLeftColor = "var(--hb-danger,#D9534F)";
    wrap.appendChild(e);
  }
  host.appendChild(wrap);
}

// ── THE IMPORT SWITCH (V2-714) — one control, both halves, and an honest count ──────────────────────────
// «No vamos a poner dos opciones, quieres sincronizar esto, lo otro. En el momento en que le damos a
// conectar… un botón de sincronizar que se queda activado y se queda en modo sincronizando en tiempo real.»
// So: ONE switch. It brings contacts AND groups, and turning it on runs a pass immediately rather than
// promising one in fifteen minutes.
function renderImportBox(el, data, ctx, p, redraw){
  const st = (p.sync || {});
  const on = !!st.on;
  const box = el2("div","ctsync");
  const top = el2("div","ctsynctop");
  top.appendChild(svgEl(ICO_SYNC));
  top.appendChild(el2("b", null, tt("import_title", null, "Contactos y grupos")));
  box.appendChild(top);

  const line = el2("div","ctsyncfoot");
  const sw = el2("button","ctbtn" + (on ? " primary" : ""),
                 on ? tt("import_on", null, "Sincronizando") : tt("import_off", null, "Sincronizar"));
  sw.onclick = async ()=>{
    sw.disabled = true;
    sw.textContent = tt("import_working", null, "Trayendo…");
    redraw(await ctx.action("set_auto", {source: p.id, auto: !on}));
  };
  line.appendChild(sw);
  box.appendChild(line);

  // WHAT IT BROUGHT, and — for the one platform that cannot be asked for everything — what that number
  // does NOT mean. A count presented as a total when it is not is a promise the card cannot keep.
  const bits = [];
  if(st.last){ bits.push(tt("import_added", {n: st.added || 0}, (st.added || 0) + " nuevos en la última pasada")); }
  if(p.id === "whatsapp"){ bits.push(tt("import_partial", null,
    "WhatsApp va entregando su libreta a medida que el móvil la sincroniza: esto es lo conocido hasta ahora")); }
  if(st.error){ bits.push(String(st.error)); }
  if(bits.length){ box.appendChild(el2("div","ctsyncwhen", bits.join(" · "))); }
  return box;
}

function renderSyncBox(el, data, ctx, sync, redraw){
  const box = el2("div","ctsync");
  const top = el2("div","ctsynctop");
  top.appendChild(svgEl(ICO_SYNC));
  top.appendChild(el2("b",null, tt("sync_title", null, "Sincronización")));
  box.appendChild(top);

  // THE CONTROL IS A STATE, NOT AN ERRAND (V2-701). His words: «el tema de la sincronización de contactos
  // no es algo que deberíamos hacer de forma puntual… eso debería quedarse conectado de forma permanente».
  // A button is a one-off by its very grammar, so the button stopped being the control and became the
  // switch that is either on or off — and while it is on, the engine keeps them in step on its own.
  const on = sync.auto !== false;
  const row = el2("button","ctswrow" + (on?" on":""));
  row.appendChild(el2("span","ctsw"));
  row.appendChild(el2("span","ctswtx", tt("sync_auto", null, "Mantener sincronizado con Google")));
  const every = Math.max(1, Math.round((sync.every || 60)/60));
  row.appendChild(el2("span","ctswsub", on
    ? tt("sync_auto_on", {min: every}, every === 1 ? "comprueba cada minuto"
                                                   : "comprueba cada " + every + " minutos")
    : tt("sync_auto_off", null, "apagada")));
  row.onclick = ()=>{ sync.auto = !on; redraw(null); ctx.action("set_auto", {auto: !on}).then(redraw); };
  box.appendChild(row);

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
    // The direction line above already SAYS it only brings; repeating it here in a louder register is noise,
    // so the warning carries only what the line cannot: what unblocks it.
    box.appendChild(el2("div","ctwarn", tt("sync_needs_write", null,
      "Para que vaya en los dos sentidos hace falta el permiso de escritura de contactos en la app de "
      + "Google Cloud.")));
  }

  if(sync.blockedDeletes){
    // Said out loud rather than swallowed: the engine REFUSED to mirror a deletion it did not believe, and
    // a guard that protects silently is indistinguishable from one that is not there (V2-701).
    const w = el2("div","ctwarn", tt("sync_blocked_deletes", {n: sync.blockedDeletes},
      "Google decía que " + sync.blockedDeletes + " contactos se habían borrado. Eran demasiados de golpe, "
      + "así que no he borrado ninguno. Revísalo en Google y vuelve a sincronizar."));
    w.style.color = "var(--hb-danger,#D9534F)";
    w.style.borderLeftColor = "var(--hb-danger,#D9534F)";
    box.appendChild(w);
  }

  const foot = el2("div","ctsyncfoot");
  // «Sincronizar ahora» is impatience, not the feature: the switch above is what keeps them in step. It
  // stays a quiet link so nothing on this panel reads as «syncing is something you do by hand».
  const go = el2("button","ctquiet", tt("sync_now", null, "Sincronizar ahora"));
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
  if(r.error){
    when.appendChild(el2("div",null, String(r.error)));
  } else if(sync.last){
    const bits = [];
    if(r.added) bits.push(tt("sync_added", {n:r.added}, r.added + " nuevos"));
    if(r.updated) bits.push(tt("sync_updated", {n:r.updated}, r.updated + " completados"));
    if(r.removed) bits.push(tt("sync_removed", {n:r.removed}, r.removed + " borrados"));
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
    case "group":   return tt("kind_group", null, "grupo");
    case "agent":   return tt("kind_agent", null, "agente");
    default:        return "";
  }
}

// The RAIL says them in the plural, because a rail row is a set and not an example.
function kindPlural(kind){
  switch(String(kind || "")){
    case "person":  return tt("kind_people", null, "Personas");
    case "place":   return tt("kind_places", null, "Sitios");
    case "company": return tt("kind_companies", null, "Empresas");
    case "group":   return tt("kind_groups", null, "Grupos");
    case "agent":   return tt("kind_agents", null, "Agentes");
    default:        return "";
  }
}


// ── THE RAIL — the directory's own map, derived from what it holds (V2-715) ─────────────────────────────
// The operator, 2026-09-17: «en la barra lateral de la izquierda es donde vayamos a desarrollar de forma
// dinámica todo lo que tenemos», and about the four fixed tabs that used to sit on top: «un contacto nunca
// va a ser un lugar, con lo cual eso no tiene ningún sentido ahí».
//
// So nothing here is a fixed word. Every section is TALLIED from the rows on screen and a section with
// nothing in it is not drawn — a directory of 2 688 people and no places never shows «Sitios (0)», and a
// directory that grows its first cluster grows a «Grupos» row the same day. The counts are tallied over
// the platform-filtered pool, so a number in the rail is a promise about what a click on it will show.
function railSection(side, label){
  side.appendChild(el2("div","ctsep"));
  side.appendChild(el2("div","ctsidelbl", label));
}

function tally(list, keyOf){
  const out = {};
  list.forEach(c=>{
    (keyOf(c)||[]).forEach(k=>{
      const n = normJs(k);
      if(!n) return;
      const e = out[n] || (out[n] = {id: k, count: 0});
      e.count++;
    });
  });
  return Object.values(out).sort((a,b)=> b.count - a.count || (normJs(a.id) < normJs(b.id) ? -1 : 1));
}

//: How many labels / cities the rail shows before it offers the rest. A Google address book brings its own
//: contact groups, so this list is long in real life and an unbounded rail would push «+ Nuevo contacto»
//: off the bottom of every card.
const RAIL_PAGE = 10;

function renderRail(el, data, ctx){
  const side = el2("div","ctside");
  const sel = selOf(el);
  const pool = basePool(data, el);
  const hiddenN = (data.hidden_rows||[]).length;

  const row = (axis, value, label, count, icon)=>{
    const on = axis==="all" ? selEmpty(sel)
             : (axis==="fav"||axis==="hidden") ? !!sel[axis]
             : String(sel[axis]||"")===String(value||"");
    const b = el2("button","ctg"+(on?" on":""));
    if(icon) b.append(el2("span","ctgi", icon));
    b.append(el2("span",null,label));
    if(count!=null) b.append(el2("span","ctgc",String(count)));
    // A CLICK means «show me this one thing», so it replaces the whole filter. Several axes at once is
    // something only a sentence can ask for, and the pushed view is where that arrives.
    b.onclick = ()=>{ el._ctFilter = axis==="all" ? {}
                    : (axis==="fav"||axis==="hidden") ? {[axis]: true} : {[axis]: value};
                      el._ctDetail=null; el._ctScreen=null; el._ctShown=0; render(el,data,ctx); };
    side.appendChild(b);
    return b;
  };

  // The count he asked for, where he asked for it: «con poner entre paréntesis al lado de las letras ALL
  // el número de contactos, todo el mundo lo entiende de la misma manera».
  row("all", "", tt("all", null, "Todos"),
      selOf(el).hidden ? (data.contacts||[]).length : pool.length);
  const favs = pool.filter(c=>c.favorite).length;
  row("fav", "", tt("favs", null, "★ Favoritos"), favs);

  const kinds = KIND_ORDER.map(k=>({k, n: pool.filter(c=>kindOf(c)===k).length})).filter(x=>x.n>0);
  // ONE kind present is not a classification, it is the whole directory said twice.
  if(kinds.length > 1){
    railSection(side, tt("side_kinds", null, "Tipos"));
    kinds.forEach(x=>row("kind", x.k, kindPlural(x.k), x.n, KICON[x.k]||""));
  }

  const labels = tally(pool, c=>c.groups||[]);
  if(labels.length){
    railSection(side, tt("side_groups", null, "Etiquetas"));
    const open = !!el._ctAllGroups;
    (open ? labels : labels.slice(0, RAIL_PAGE)).forEach(g=>row("group", g.id, g.id, g.count));
    if(labels.length > RAIL_PAGE){
      const more = el2("button","ctgmore", open ? tt("rail_less", null, "ver menos")
        : tt("rail_more", {n: labels.length - RAIL_PAGE}, "ver " + (labels.length - RAIL_PAGE) + " más"));
      more.onclick = ()=>{ el._ctAllGroups = !open; render(el,data,ctx); };
      side.appendChild(more);
    }
  }

  const cities = tally(pool, c=>[String(c.city||"").trim()].filter(Boolean));
  if(cities.length){
    railSection(side, tt("side_cities", null, "Ciudades"));
    const open = !!el._ctAllCities;
    (open ? cities : cities.slice(0, RAIL_PAGE)).forEach(g=>row("city", g.id, g.id, g.count));
    if(cities.length > RAIL_PAGE){
      const more = el2("button","ctgmore", open ? tt("rail_less", null, "ver menos")
        : tt("rail_more", {n: cities.length - RAIL_PAGE}, "ver " + (cities.length - RAIL_PAGE) + " más"));
      more.onclick = ()=>{ el._ctAllCities = !open; render(el,data,ctx); };
      side.appendChild(more);
    }
  }

  // HIDDEN — the rows he took off the directory. They were unreachable from the card until now, and a
  // «quítalo de la lista» that cannot be undone from the same card is a delete wearing a softer word.
  if(hiddenN){
    railSection(side, tt("side_hidden", null, "Ocultos"));
    row("hidden", "", tt("hidden_rows", null, "Ocultos"), hiddenN, "◌");
  }

  side.appendChild(el2("div","ctsep"));
  const addB = el2("button","ctact","+ "+tt("new_contact", null, "Nuevo contacto"));
  addB.onclick = ()=>{
    const inp=document.createElement("input"); inp.className="ctin";
    inp.placeholder=tt("new_name_ph", null, "nombre…");
    let done=false;
    const fin=async(save)=>{ if(done)return; done=true;
      const t=String(inp.value||"").trim();
      if(save && t){ const nd=await ctx.action("add_contact",{name:t});
                     render(el,(nd&&nd.contacts)?nd:data,ctx); }
      else render(el,data,ctx); };
    inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                       else if(e.key==="Escape"){e.preventDefault();fin(false);} };
    inp.onblur=()=>fin(true);
    addB.replaceWith(inp); inp.focus();
  };
  side.appendChild(addB);
  // NO import button here. It lived in this rail for one build and the operator had it removed: importing
  // is a CONNECTOR gesture, and in this product every connector gesture is reached the same way — the plug
  // button in the bar. A second door to it would be a second place to keep in sync.
  return side;
}

// ── WHAT IS BEING FILTERED RIGHT NOW, and how to drop it ────────────────────────────────────────────────
// Two of the three filters live somewhere the eye can miss (an icon in the bar, a row in a rail that
// scrolls), and a list showing 412 of 2 688 rows with no visible reason is indistinguishable from a
// directory that lost them. Each chip REMOVES its own filter, so the way out is where the surprise is.
function renderCrumb(el, data, ctx, shown, total){
  const bar = el2("div","ctcrumb");
  const sel = selOf(el);
  const chip = (label, clear)=>{
    const b = el2("button","ctcx");
    b.append(el2("span",null,label));
    b.append(el2("span",null,"✕"));
    b.title = tt("crumb_clear", null, "quitar este filtro");
    b.onclick = ()=>{ clear(); el._ctDetail=null; el._ctShown=0; render(el,data,ctx); };
    bar.appendChild(b);
  };
  if(el._ctSource){
    const p = (data.providers||[]).find(x=>srcKey(x.id)===srcKey(el._ctSource));
    chip((p && p.label) || el._ctSource, ()=>{ el._ctSource=""; });
  }
  const drop=(axis)=>()=>{ const f={...selOf(el)}; delete f[axis]; el._ctFilter=f; };
  if(sel.hidden) chip(tt("hidden_rows", null, "Ocultos"), drop("hidden"));
  if(sel.fav) chip(tt("favs", null, "★ Favoritos"), drop("fav"));
  if(sel.kind) chip(kindPlural(sel.kind), drop("kind"));
  if(sel.group) chip(String(sel.group), drop("group"));
  if(sel.city) chip(String(sel.city), drop("city"));
  if(el._ctQuery) chip("“"+String(el._ctQuery)+"”", ()=>{ el._ctQuery=""; });
  bar.appendChild(el2("span","ctcount", shown < total
    ? tt("shown_of", {n: shown, total: total}, shown + " de " + total)
    : tt("shown_n", {n: total}, String(total))));
  return bar;
}

//: How many rows are painted before «ver más». His own directory holds 2 688 and every one of them used to
//: become a DOM node on every keystroke of the search box.
const PAGE = 120;

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();

  // A VIEW PUSHED FROM VOICE (`show_view` / `show_contact` / `show_connectors`). Applied only when its
  // token MOVES — a plain data refresh never yanks what the operator is reading, but asking twice for the
  // same filter still lands, because the token is a counter and not the filter itself (V2-540).
  const pushed=data.view;
  if(pushed && pushed.n!==el._ctViewN){
    el._ctViewN=pushed.n;
    const sel=pushed.sel||{};
    if(sel.screen==="connectors"){ el._ctScreen="conn"; el._ctDetail=null; }
    else if(sel.contactId){ el._ctDetail=sel.contactId; el._ctScreen=null; }
    else{
      // ⚠️ `kind` and `source` were pushed by `show_view` and DROPPED here until V2-715: «enséñame mis
      // empresas» filtered the spoken answer and left the card showing everything, which is the pair of
      // disagreeing surfaces this widget's own digest exists to prevent.
      el._ctDetail=null; el._ctScreen=null; el._ctShown=0;
      el._ctSource=sel.source||"";
      el._ctQuery=sel.query||"";
      const f={};
      if(sel.hidden) f.hidden=true;
      if(sel.favorites) f.fav=true;
      if(sel.kind) f.kind=String(sel.kind);
      if(sel.group) f.group=String(sel.group);
      if(sel.city) f.city=String(sel.city);
      el._ctFilter=f;
    }
  }

  el.className="hb-contactos";
  el.textContent="";                                          // reset (no innerHTML)

  const contacts=data.contacts||[];
  const redraw=nd=>render(el,(nd&&nd.contacts)?nd:data,ctx);

  // ── THE ONE BAR — search, the sources, and the door to them ───────────────────────────────────────────
  const bar=el2("div","ctbar");
  const sb=el2("div","ctsearch");
  sb.appendChild(el2("span",null,"\u{1F50D}"));
  const q=document.createElement("input");
  q.placeholder=tt("search_ph", null, "Buscar…");
  q.value=el._ctQuery||"";
  q.oninput=()=>{ el._ctQuery=q.value; const keep=q.value; el._ctScreen=null; el._ctShown=0;
    render(el,data,ctx);
    const nq=el.querySelector(".ctsearch input");
    if(nq){ nq.focus(); nq.setSelectionRange(keep.length,keep.length); } };
  sb.appendChild(q);
  bar.appendChild(sb);
  const right=el2("div","ctviewsright");
  right.appendChild(renderProviderIcons(data.providers||[], el, data, ctx));
  const connBtn=el2("button","ctplug"+(el._ctScreen?" on":""));
  connBtn.appendChild(svgEl(ICO_PLUG));
  connBtn.title=tt("connectors_hint", null, "Qué fuentes de contactos están conectadas");
  connBtn.setAttribute("aria-label", tt("connectors", null, "Conectores"));
  connBtn.onclick=()=>{ el._ctScreen = el._ctScreen ? null : "conn"; el._ctDetail=null; render(el,data,ctx); };
  right.appendChild(connBtn);
  bar.appendChild(right);
  el.appendChild(bar);

  if(el._ctScreen === "conn"){
    renderConnectors(el, el, data, ctx);
    return;
  }

  const cols=el2("div","ctcols");
  cols.appendChild(renderRail(el, data, ctx));

  const main=el2("div","ctmain");
  const detail=el._ctDetail
    ? (contacts.find(c=>c.id===el._ctDetail) || (data.hidden_rows||[]).find(c=>c.id===el._ctDetail))
    : null;

  if(!contacts.length && !(data.hidden_rows||[]).length){
    main.appendChild(el2("div","ctempty",
      tt("empty_1", null, "El directorio está vacío. Dile a Zaelar: «apúntame el restaurante Elfo On de Soria como favorito» ")+
      tt("empty_2", null, "o «añade a Marta, amiga del trabajo».")));
  } else if(detail){
    renderDetail(el,main,data,ctx,detail);
  } else {
    const sel=selOf(el);
    const rows=rowsOf(data, el);
    const shown=Math.min(rows.length, Math.max(PAGE, el._ctShown||0));
    const filtering = !!(el._ctSource || el._ctQuery) || !selEmpty(sel);
    if(filtering || rows.length>PAGE) main.appendChild(renderCrumb(el, data, ctx, shown, rows.length));
    if(sel.hidden){
      main.appendChild(el2("div","ctnote", tt("hidden_hint", null,
        "Ocultos: no salen en el directorio y la siguiente importación NO los vuelve a traer. "
        + "Pulsa ◌ en su ficha para devolverlos.")));
    }

    const list=el2("div","ctlist");
    if(!rows.length){
      list.appendChild(el2("div","ctempty",tt("no_match", null, "Nada que casar con ese filtro.")));
    }
    rows.slice(0, shown).forEach(c=>{
      const r=el2("div","ctrow");
      r.appendChild(avatar(c,false));
      const tx=el2("div","ctrtx");
      tx.appendChild(el2("span","ctnm",c.name||c.id));
      const sub=preferredLine(c) || detailValues(c,"phones")[0] || "";
      if(sub) tx.appendChild(el2("span","ctsub",sub));
      r.appendChild(tx);
      if(c.city)r.appendChild(el2("span","ctci",c.city));
      const gs=el2("span","ctgs");
      // The KIND on the row, but only when it is not the obvious one: a directory of people that labelled
      // every row «persona» would be spending its only free strip on a word that says nothing.
      if(kindOf(c)!=="person") gs.appendChild(el2("span","ctpill",kindLabel(kindOf(c))));
      (c.groups||[]).slice(0,2).forEach(g=>gs.appendChild(el2("span","ctpill",g)));
      r.appendChild(gs);
      r.appendChild(favBtn(c,ctx,el,data));
      r.onclick=()=>{ el._ctDetail=c.id; render(el,data,ctx); };
      list.appendChild(r);
    });
    main.appendChild(list);
    if(rows.length>shown){
      const more=el2("button","ctmore",
        tt("rows_more", {n: rows.length-shown}, "Ver más (" + (rows.length-shown) + ")"));
      more.onclick=()=>{ el._ctShown=shown+PAGE; render(el,data,ctx); };
      main.appendChild(more);
    }
  }

  cols.appendChild(main);
  el.appendChild(cols);

  // A failed action says so where the gesture happened, instead of leaving the card looking unchanged.
  if(data.ok===false && data.error){
    const w=el2("div","ctnote",String(data.error)); w.style.color="var(--hb-danger,#D9534F)";
    el.appendChild(w);
  }
}
