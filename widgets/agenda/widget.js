// Agenda widget — client render module (lazy-loaded by the canvas host). Contract: render(el, data, ctx).
// data = GET /widgets/agenda/data ; ctx.action(name,payload) -> new data (re-renders) ; ctx.close().
// Self-contained: scoped styles, live countdown, coach actions. The render is portable (plain DOM).
//
// V2-643 — a REAL calendar, in the shapes everybody already knows (the operator's spec: «tiene que parecerse a
// Google Calendar o a la agenda de Apple»): a toolbar with ‹ Hoy ›, the four classic views (Día · Semana · Mes ·
// Lista), a WEEK laid out as seven columns over an hour grid with the events inside each column, chips coloured
// by category and shaded by whether the other side has CONFIRMED, and badges for the reminder bell and how many
// people are coming. The card FILLS its frame and the grid scrolls inside it, so nothing is ever clipped.

const SVG_NS_AG = "http://www.w3.org/2000/svg";

// Event palette. HUE says WHAT KIND of thing it is; the INTENSITY (below) says how settled it is. Both are
// derived from stored data — the category the operator dictated, or the planner's own block kind — never from
// sniffing the title, which would be guessing intent (V2-095).
const HUES = {
  meeting:  "#7C6BFF",   // an appointment with the world
  work:     "#3D6FE0",
  deep:     "#3D6FE0",
  admin:    "#16B8A6",
  health:   "#E5484D",
  travel:   "#0EA5E9",
  social:   "#EC4899",
  personal: "#22A06B",
  exercise: "#E8973A",
  break:    "#8B98AC",
  buffer:   "#8B98AC",
};
// Dictated category → hue key. Spanish and English, because the category is PRODUCT DATA the operator speaks.
const CATEGORY_HUE = {
  trabajo:"work", work:"work", oficina:"work", reunion:"meeting", meeting:"meeting",
  salud:"health", health:"health", medico:"health", doctor:"health", dentista:"health",
  viaje:"travel", travel:"travel", vuelo:"travel", trip:"travel",
  social:"social", amigos:"social", family:"social", familia:"social", cumpleanos:"social", birthday:"social",
  personal:"personal", casa:"personal", home:"personal",
  deporte:"exercise", gym:"exercise", exercise:"exercise", sport:"exercise",
};

function injectStyles(){
  const prev = document.getElementById("hb-agenda-css");
  if(prev && (prev.dataset||{}).v === "640") return;   // dataset is optional on a foreign node
  if(prev) prev.remove();                      // an older build's sheet would fight this one, silently
  const s=document.createElement("style"); s.id="hb-agenda-css"; s.dataset.v="640"; s.textContent=`
  /* The card decides the size (manifest.size); the widget fills it and scrolls INSIDE — the operator's
     report was «se muestra muy pequeño, se cortan las palabras de abajo». :has reaches the card chrome
     (.hb-scroll wraps the widget root) exactly as the video widget does since V2-636. */
  .hb-scroll:has(> .hb-agenda){overflow:hidden}
  .hb-agenda{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    color:var(--hb-ink,#0d1622);width:100%;height:100%;box-sizing:border-box;
    display:flex;flex-direction:column;gap:0;position:relative;min-height:0}

  /* ── TOOLBAR: brand · range title · ‹ Hoy › — one line, like every calendar ─────────────────────── */
  .hb-agenda .agbar{display:flex;align-items:center;gap:10px;padding:0 0 9px;flex:0 0 auto;min-width:0}
  .hb-agenda .agbrand{width:26px;height:26px;border-radius:8px;background:var(--hb-accent,#3D6FE0);color:#fff;
    display:flex;align-items:center;justify-content:center;flex:0 0 auto}
  .hb-agenda .agbrand svg{width:15px;height:15px;display:block}
  .hb-agenda .agrange{font-size:15px;font-weight:700;letter-spacing:-.01em;white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis;flex:1 1 auto;min-width:0;text-transform:capitalize}
  .hb-agenda .agnav{display:flex;align-items:center;gap:4px;flex:0 0 auto}
  .hb-agenda .agnav button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);border-radius:9px;height:30px;min-width:30px;padding:0 9px;font-size:13px;
    font-weight:600;cursor:pointer;line-height:1;display:flex;align-items:center;justify-content:center}
  .hb-agenda .agnav button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agnav svg{width:13px;height:13px;display:block}

  /* ── VIEW BAND: a defined strip, active view an INVERTED chip (the V2-636 language) ─────────────── */
  .hb-agenda .agviews{display:flex;align-items:center;gap:5px;flex-wrap:nowrap;overflow-x:auto;
    border-bottom:1px solid var(--hb-line,#e3e8f0);padding-bottom:9px;margin-bottom:10px;flex:0 0 auto;
    scrollbar-width:none}
  .hb-agenda .agviews::-webkit-scrollbar{display:none}
  .hb-agenda .agtab{border:0;background:none;color:var(--hb-muted,#5b6b82);border-radius:999px;
    padding:6px 14px;font-size:12.5px;font-weight:600;cursor:pointer;line-height:1.2;white-space:nowrap;flex:0 0 auto}
  .hb-agenda .agtab:hover{background:var(--hb-bg-soft,#f4f7fb);color:var(--hb-ink,#0d1622)}
  .hb-agenda .agtab.on{background:var(--hb-ink,#0d1622);color:var(--hb-bg,#fff)}
  .hb-agenda .agcalbtn{margin-left:auto;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);border-radius:9px;height:30px;padding:0 11px;font-size:12.5px;font-weight:600;
    cursor:pointer;display:flex;align-items:center;gap:7px;flex:0 0 auto}
  .hb-agenda .agcalbtn:hover,.hb-agenda .agcalbtn.on{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agcalbtn svg{width:14px;height:14px;display:block}

  .hb-agenda .agbody{flex:1 1 auto;min-height:0;overflow:auto;position:relative}

  /* ── TIME GRID (day + week) ──────────────────────────────────────────────────────────────────────── */
  .hb-agenda .aghead{display:grid;position:sticky;top:0;z-index:3;background:var(--hb-bg,#fff);
    border-bottom:1px solid var(--hb-line,#e3e8f0)}
  .hb-agenda .agdh{padding:5px 4px 7px;text-align:center;min-width:0;border-left:1px solid var(--hb-line,#eef1f6)}
  .hb-agenda .agdh:first-child{border-left:0}
  .hb-agenda .agdh .agdw{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--hb-muted-2,#9aa7b8);font-weight:700}
  .hb-agenda .agdh .agdn{font-size:17px;font-weight:600;line-height:1.35;color:var(--hb-ink,#0d1622);
    width:29px;height:29px;margin:1px auto 0;border-radius:50%;display:flex;align-items:center;justify-content:center}
  .hb-agenda .agdh.today .agdw{color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agdh.today .agdn{background:var(--hb-accent,#3D6FE0);color:#fff}
  .hb-agenda .agdh.pick{cursor:pointer}
  .hb-agenda .agdh.pick:hover .agdn{background:var(--hb-bg-soft,#f4f7fb)}
  .hb-agenda .agdh.today.pick:hover .agdn{background:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agallday{display:grid;border-bottom:1px solid var(--hb-line,#e3e8f0);position:sticky;
    top:var(--aghead-h,54px);z-index:2;background:var(--hb-bg,#fff);min-height:22px}
  .hb-agenda .agallcell{padding:3px;display:flex;flex-direction:column;gap:2px;min-width:0;
    border-left:1px solid var(--hb-line,#eef1f6)}
  .hb-agenda .agallcell:first-child{border-left:0}
  .hb-agenda .agalllb{font-size:10px;color:var(--hb-muted-2,#9aa7b8);text-transform:uppercase;
    letter-spacing:.06em;padding:5px 4px 0;text-align:right;font-weight:700}
  .hb-agenda .aggrid{display:grid;position:relative}
  .hb-agenda .aghours{position:relative}
  .hb-agenda .aghour{position:absolute;right:6px;font-size:10.5px;color:var(--hb-muted-2,#9aa7b8);
    font-variant-numeric:tabular-nums;transform:translateY(-50%)}
  .hb-agenda .agcol{position:relative;border-left:1px solid var(--hb-line,#eef1f6);min-width:0}
  .hb-agenda .agline{position:absolute;left:0;right:0;border-top:1px solid var(--hb-line,#eef1f6)}
  .hb-agenda .agline.half{border-top-style:dotted;opacity:.55}
  .hb-agenda .agnow{position:absolute;left:0;right:0;height:0;border-top:2px solid var(--hb-risk,#e5484d);z-index:4}
  .hb-agenda .agnow::before{content:"";position:absolute;left:-4px;top:-5px;width:8px;height:8px;
    border-radius:50%;background:var(--hb-risk,#e5484d)}

  /* ── EVENT CHIP: hue = category, INTENSITY = how settled it is ──────────────────────────────────── */
  .hb-agenda .agev{position:absolute;box-sizing:border-box;border-radius:7px;padding:3px 6px;overflow:hidden;
    cursor:pointer;border:1px solid transparent;border-left:3px solid var(--evc,#3D6FE0);
    background:color-mix(in srgb, var(--evc,#3D6FE0) 17%, transparent);min-height:20px;
    display:flex;flex-direction:column;gap:1px;line-height:1.2}
  .hb-agenda .agev:hover{filter:brightness(1.07)}
  .hb-agenda .agev.pending{background:color-mix(in srgb, var(--evc,#3D6FE0) 7%, transparent);
    border:1px dashed var(--evc,#3D6FE0);border-left-width:3px;border-left-style:solid}
  .hb-agenda .agev.planned{background:color-mix(in srgb, var(--evc,#3D6FE0) 8%, transparent);
    border-left-width:2px;opacity:.92}
  .hb-agenda .agev.sel{box-shadow:0 0 0 2px var(--evc,#3D6FE0)}
  .hb-agenda .agevt{font-size:11.5px;font-weight:600;color:var(--hb-ink,#0d1622);white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis}
  .hb-agenda .agevh{font-size:10.5px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:5px}
  .hb-agenda .agbadges{display:inline-flex;align-items:center;gap:5px;flex:0 0 auto}
  .hb-agenda .agbadge{display:inline-flex;align-items:center;gap:2px;font-size:10px;color:var(--hb-muted,#5b6b82);
    font-variant-numeric:tabular-nums}
  .hb-agenda .agbadge svg{width:10px;height:10px;display:block}
  .hb-agenda .agev.allday{position:static;min-height:0;padding:2px 6px}

  /* ── MONTH ───────────────────────────────────────────────────────────────────────────────────────── */
  .hb-agenda .agmgrid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:0;height:100%;
    border-top:1px solid var(--hb-line,#e3e8f0);border-left:1px solid var(--hb-line,#e3e8f0)}
  .hb-agenda .agmdow{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--hb-muted-2,#9aa7b8);text-align:center;font-weight:700;padding:5px 0}
  .hb-agenda .agmdows{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));flex:0 0 auto}
  .hb-agenda .agmcell{min-height:74px;border-right:1px solid var(--hb-line,#e3e8f0);
    border-bottom:1px solid var(--hb-line,#e3e8f0);padding:3px 4px;display:flex;flex-direction:column;gap:2px;
    overflow:hidden;cursor:pointer;background:var(--hb-bg,#fff)}
  .hb-agenda .agmcell:hover{background:var(--hb-bg-soft,#f4f7fb)}
  .hb-agenda .agmcell.out{background:var(--hb-bg-soft,#fbfdff);opacity:.62}
  .hb-agenda .agmn{font-size:11.5px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;
    align-self:flex-start;width:20px;height:20px;border-radius:50%;display:flex;align-items:center;
    justify-content:center;flex:0 0 auto}
  .hb-agenda .agmcell.today .agmn{background:var(--hb-accent,#3D6FE0);color:#fff;font-weight:700}
  .hb-agenda .agmev{display:flex;align-items:center;gap:4px;font-size:10.5px;min-width:0;
    padding:1px 4px;border-radius:5px;background:color-mix(in srgb, var(--evc,#3D6FE0) 15%, transparent);
    cursor:pointer}
  .hb-agenda .agmev.pending{background:transparent;border:1px dashed var(--evc,#3D6FE0)}
  .hb-agenda .agmdot{width:6px;height:6px;border-radius:50%;background:var(--evc,#3D6FE0);flex:0 0 auto}
  .hb-agenda .agmt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--hb-ink,#0d1622)}
  .hb-agenda .agmh{color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;flex:0 0 auto}
  .hb-agenda .agmore{font-size:10px;color:var(--hb-muted-2,#9aa7b8);padding-left:3px}

  /* ── LIST (the classic Schedule view) ────────────────────────────────────────────────────────────── */
  .hb-agenda .aglist{display:flex;flex-direction:column;gap:0}
  .hb-agenda .agday{display:flex;gap:12px;padding:9px 2px;border-bottom:1px solid var(--hb-line,#eef1f6);min-width:0}
  .hb-agenda .agdaydate{width:58px;flex:0 0 auto;text-align:center}
  .hb-agenda .agdaydate .d{font-size:19px;font-weight:700;line-height:1.1}
  .hb-agenda .agdaydate .w{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;
    color:var(--hb-muted-2,#9aa7b8);font-weight:700}
  .hb-agenda .agday.today .agdaydate .d,.hb-agenda .agday.today .agdaydate .w{color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agdayevs{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:5px}
  .hb-agenda .agrow{display:flex;align-items:center;gap:9px;padding:5px 7px;border-radius:9px;min-width:0;
    cursor:pointer;background:color-mix(in srgb, var(--evc,#3D6FE0) 10%, transparent);
    border-left:3px solid var(--evc,#3D6FE0)}
  .hb-agenda .agrow:hover{background:color-mix(in srgb, var(--evc,#3D6FE0) 18%, transparent)}
  .hb-agenda .agrow.pending{background:transparent;border:1px dashed var(--evc,#3D6FE0);border-left-width:3px;
    border-left-style:solid}
  .hb-agenda .agrowh{font-size:12px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;
    width:78px;flex:0 0 auto}
  .hb-agenda .agrowt{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    flex:1 1 auto;min-width:0}
  .hb-agenda .agrowm{font-size:11.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;
    text-overflow:ellipsis;flex:0 1 auto;max-width:38%}
  .hb-agenda .agempty{padding:26px 10px;text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:13px}

  /* ── DAY view side rail: the coach half this widget has always had ───────────────────────────────── */
  .hb-agenda .agday-wrap{display:flex;gap:12px;height:100%;min-height:0}
  .hb-agenda .agday-grid{flex:1 1 auto;min-width:0;overflow:auto}
  .hb-agenda .agside{width:246px;flex:0 0 auto;display:flex;flex-direction:column;gap:9px;overflow:auto;
    padding-right:2px}
  @media(max-width:660px){.hb-agenda .agday-wrap{flex-direction:column}
    .hb-agenda .agside{width:auto;flex:0 0 auto}}
  .hb-agenda .agcard{border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;padding:11px;
    background:var(--hb-bg-soft,#fbfdff);display:flex;flex-direction:column;gap:7px}
  .hb-agenda .agk{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--hb-muted-2,#9aa7b8);
    font-weight:700}
  .hb-agenda .agtask{font-size:14.5px;font-weight:600}
  .hb-agenda .agcount{font-size:26px;font-variant-numeric:tabular-nums;color:var(--hb-accent2,#16B8A6);
    font-weight:600}
  .hb-agenda .agacts{display:flex;flex-wrap:wrap;gap:6px}
  .hb-agenda .agacts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    border-radius:9px;padding:7px 10px;font-size:12px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-agenda .agacts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agacts .done{border-color:var(--hb-accent2,#16B8A6);color:#0f766e}
  .hb-agenda .agnudge{font-size:12px;color:var(--hb-warn-ink,#9a6a00);background:var(--hb-warn-bg,#fff7e8);
    border:1px solid var(--hb-warn-border,#f2dca6);border-radius:9px;padding:7px 9px}
  .hb-agenda .agwarn{font-size:11.5px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-agenda .agchip{font-size:11.5px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;
    padding:3px 9px;color:var(--hb-muted,#3a4757);background:var(--hb-bg,#fff)}
  .hb-agenda .agchips{display:flex;gap:6px;flex-wrap:wrap}

  /* ── DETAIL panel + CONNECTORS panel: overlays inside the card ───────────────────────────────────── */
  .hb-agenda .agveil{position:absolute;inset:0;background:rgba(8,14,22,.34);z-index:9;display:flex;
    align-items:center;justify-content:center;padding:16px;border-radius:12px}
  .hb-agenda .agpanel{background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#e3e8f0);border-radius:14px;
    box-shadow:0 18px 50px rgba(13,22,34,.22);padding:14px;width:min(360px,100%);max-height:100%;
    overflow:auto;display:flex;flex-direction:column;gap:9px}
  .hb-agenda .agphead{display:flex;align-items:flex-start;gap:9px}
  .hb-agenda .agpbar{width:4px;align-self:stretch;border-radius:3px;background:var(--evc,#3D6FE0);flex:0 0 auto}
  .hb-agenda .agptitle{font-size:15px;font-weight:700;line-height:1.3;flex:1 1 auto;min-width:0;word-break:break-word}
  .hb-agenda .agpx{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);font-size:17px;cursor:pointer;
    line-height:1;padding:0 2px;flex:0 0 auto}
  .hb-agenda .agpx:hover{color:var(--hb-ink,#0d1622)}
  .hb-agenda .agprow{display:flex;align-items:flex-start;gap:8px;font-size:12.5px;color:var(--hb-muted,#3a4757);
    line-height:1.35;min-width:0}
  .hb-agenda .agprow svg{width:13px;height:13px;display:block;flex:0 0 auto;margin-top:2px;
    color:var(--hb-muted-2,#9aa7b8)}
  .hb-agenda .agpstate{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;
    border-radius:999px;padding:3px 10px;align-self:flex-start}
  .hb-agenda .agpstate.confirmed{background:rgba(22,184,166,.16);color:#0f766e}
  .hb-agenda .agpstate.pending{background:rgba(240,170,20,.16);color:#8a5a00}
  .hb-agenda .agpacts{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
  .hb-agenda .agpacts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    border-radius:9px;padding:7px 11px;font-size:12px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-agenda .agpacts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agpacts button.risk:hover{border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}
  .hb-agenda .agcalrow{display:flex;align-items:center;gap:10px;padding:8px 4px;
    border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-agenda .agcalrow:last-of-type{border-bottom:0}
  .hb-agenda .agcalico{width:26px;height:26px;border-radius:8px;background:var(--hb-bg-soft,#f4f7fb);
    display:flex;align-items:center;justify-content:center;flex:0 0 auto}
  .hb-agenda .agcalico svg{width:15px;height:15px;display:block}
  .hb-agenda .agcalname{font-size:13px;font-weight:600;flex:1 1 auto;min-width:0;white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis}
  .hb-agenda .agcalst{font-size:11px;font-weight:600;border-radius:999px;padding:3px 9px;flex:0 0 auto;
    background:var(--hb-bg-soft,#f4f7fb);color:var(--hb-muted-2,#7d8a9c)}
  .hb-agenda .agcalst.on{background:rgba(22,184,166,.16);color:#0f766e}
  .hb-agenda .agnote{font-size:11.5px;color:var(--hb-muted-2,#7d8a9c);line-height:1.4}
  `; document.head.appendChild(s);
}

// ── i18n seam (V2-613): `ctx.t` for our own chrome, `ctx.lang` for locale SHAPE (Intl) ────────────────
let _T = null, _LANG = "es";
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.agenda."+key, params); if(s && s!=="widgets.agenda."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}
function intl(opts){ try{ return new Intl.DateTimeFormat(_LANG, opts); }catch(_){ return null; } }
function fmtDate(d, opts, fb){ const f=intl(opts); return f ? f.format(d) : fb; }

// ── date helpers (local time, no libraries) ───────────────────────────────────────────────────────────
// Optional browser surface — a widget must render (and a headless DOM stub must be able to drive it) even
// where these do not exist; neither carries behaviour, only polish.
function raf(fn){ try{ if(typeof requestAnimationFrame === "function") requestAnimationFrame(fn); else fn(); }
  catch(_){} }

const _pad = n => String(n).padStart(2,"0");
function ymd(d){ return `${d.getFullYear()}-${_pad(d.getMonth()+1)}-${_pad(d.getDate())}`; }
function parseYmd(s){
  const p = String(s||"").split("-").map(Number);
  return (p[0] && p[1] && p[2]) ? new Date(p[0], p[1]-1, p[2]) : new Date();
}
function addDays(d, n){ const x = new Date(d.getTime()); x.setDate(x.getDate()+n); return x; }
function startOfWeek(d){ const x=new Date(d.getTime()); x.setDate(x.getDate()-((x.getDay()+6)%7)); return x; }  // Monday
function mins(hhmm){ const p=String(hhmm||"").split(":"); const h=Number(p[0]), m=Number(p[1]);
  return (isFinite(h)?h:0)*60 + (isFinite(m)?m:0); }
function hhmm(m){ return `${_pad(Math.floor(m/60)%24)}:${_pad(Math.round(m)%60)}`; }
function fmtCount(min){ const m=Math.max(0,Math.round(min));
  return `${_pad(Math.floor(m/60))}:${_pad(m%60)}`; }

// ── DOM builder — data-derived text ALWAYS via textContent (data is brain-pushable, i.e. UNTRUSTED) ───
function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=String(text); return e; }
function svgEl(paths, opts){
  const svg=document.createElementNS(SVG_NS_AG,"svg");
  svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("aria-hidden","true");
  svg.setAttribute("fill", (opts&&opts.fill) || "none");
  if(!(opts&&opts.fill)){ svg.setAttribute("stroke","currentColor"); svg.setAttribute("stroke-width","2");
    svg.setAttribute("stroke-linecap","round"); svg.setAttribute("stroke-linejoin","round"); }
  else { svg.setAttribute("fill","currentColor"); }
  (Array.isArray(paths)?paths:[paths]).forEach(d=>{
    const p=document.createElementNS(SVG_NS_AG,"path"); p.setAttribute("d",d); svg.appendChild(p);
  });
  return svg;
}
const ICO_CAL   = ["M8 2v4","M16 2v4","M3 10h18","M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"];
const ICO_PREV  = "M15 18l-6-6 6-6";
const ICO_NEXT  = "M9 18l6-6-6-6";
const ICO_BELL  = ["M18 8a6 6 0 0 0-12 0c0 7-3 8-3 8h18s-3-1-3-8","M13.7 21a2 2 0 0 1-3.4 0"];
const ICO_USERS = ["M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2","M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
                   "M23 21v-2a4 4 0 0 0-3-3.87","M16 3.13a4 4 0 0 1 0 7.75"];
const ICO_PIN   = ["M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0","M12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5"];
const ICO_NOTE  = ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z","M14 2v6h6","M8 13h8","M8 17h5"];
const ICO_CHECK = "M20 6L9 17l-5-5";
const ICO_CLOCK = ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z","M12 6v6l4 2"];
const ICO_PLUG  = ["M9 2v6","M15 2v6","M6 8h12v3a6 6 0 0 1-12 0z","M12 17v5"];

// CALENDAR CONNECTORS (V2-540). Official simple-icons outlines (CC0), inline so the widget stays
// self-contained with no CDN. CalDAV is a PROTOCOL, not a brand, so it wears a calendar glyph: painting a
// Microsoft logo on it would be a lie for a Fastmail account.
const CAL_SVG = {
  google: {color:"#4285F4", path:"M18.316 5.684H24v12.632h-5.684V5.684zM5.684 24h12.632v-5.684H5.684V24zM18.316 5.684V0H1.895A1.894 1.894 0 0 0 0 1.895v16.421h5.684V5.684h12.632zm-7.207 6.25v-.065c.272-.144.5-.349.687-.617s.279-.595.279-.982c0-.379-.099-.72-.3-1.025a2.05 2.05 0 0 0-.832-.714 2.703 2.703 0 0 0-1.197-.257c-.6 0-1.094.156-1.481.467-.386.311-.65.671-.793 1.078l1.085.452c.086-.249.224-.461.413-.633.189-.172.445-.257.767-.257.33 0 .602.088.816.264a.86.86 0 0 1 .322.703c0 .33-.12.589-.36.778-.24.19-.535.284-.886.284h-.567v1.085h.633c.407 0 .748.109 1.02.327.272.218.407.499.407.843 0 .336-.129.614-.387.832s-.565.327-.924.327c-.351 0-.651-.103-.897-.311-.248-.208-.422-.502-.521-.881l-1.096.452c.178.616.505 1.082.977 1.401.472.319.984.478 1.538.477a2.84 2.84 0 0 0 1.293-.291c.382-.193.684-.458.902-.794.218-.336.327-.72.327-1.149 0-.429-.115-.797-.344-1.105a2.067 2.067 0 0 0-.881-.689zm2.093-1.931l.602.913L15 10.045v5.744h1.187V8.446h-.827l-2.158 1.557zM22.105 0h-3.289v5.184H24V1.895A1.894 1.894 0 0 0 22.105 0zm-3.289 23.5l4.684-4.684h-4.684V23.5zM0 22.105C0 23.152.848 24 1.895 24h3.289v-5.184H0v3.289z"},
  icloud: {color:"#3693F3", path:"M13.762 4.29a6.51 6.51 0 0 0-5.669 3.332 3.571 3.571 0 0 0-1.558-.36 3.571 3.571 0 0 0-3.516 3A4.918 4.918 0 0 0 0 14.796a4.918 4.918 0 0 0 4.92 4.914 4.93 4.93 0 0 0 .617-.045h14.42c2.305-.272 4.041-2.258 4.043-4.589v-.009a4.594 4.594 0 0 0-3.727-4.508 6.51 6.51 0 0 0-6.511-6.27z"},
  caldav: {color:"var(--hb-muted,#6b7b92)", path:"M19 3h-1V1h-2v2H8V1H6v2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm0 18H5V9h14v12z"},
};

// ── the model: one shape for everything that can be drawn on a calendar ───────────────────────────────
// A MEETING is authoritative and comes from `data.meetings` (any date, all its detail). A planner BLOCK is
// the coach half — a task placed in a free gap — and only exists for the horizon (today..+6); its meeting
// blocks are dropped because the same appointment already arrived through `meetings` with more inside it.
function hueOf(ev){
  const cat = String(ev.category||"").toLowerCase();
  const key = CATEGORY_HUE[cat] || (HUES[cat] ? cat : null) || ev.kind || "meeting";
  return HUES[key] || HUES.meeting;
}
function eventsOf(data){
  const out = [];
  (data.meetings||[]).forEach((m,i)=>{
    if(!m || !m.date) return;
    const allDay = !!m.allDay;
    const start = allDay ? 0 : mins(m.startTime);
    let end = allDay ? 24*60 : mins(m.endTime||"");
    if(!allDay && end <= start) end = start + 60;
    out.push({key:"m"+i, kind:"meeting", date:String(m.date).slice(0,10), allDay,
      start, end, title:m.title!=null?String(m.title):"", notes:m.notes||"", location:m.location||"",
      attendees:Array.isArray(m.attendees)?m.attendees:[], status:m.status||"confirmed",
      category:m.category||"", remindAt:m.remindAt||"", meeting:true});
  });
  (data.days||[]).forEach(d=>{
    ((d.plan||{}).blocks||[]).forEach((b,i)=>{
      if(b.kind === "meeting") return;                 // already here, richer, from `meetings`
      out.push({key:`b${d.date}-${i}`, kind:b.kind||"admin", date:d.date, allDay:false,
        start:mins(b.start), end:Math.max(mins(b.start)+15, mins(b.end)), title:b.label!=null?String(b.label):"",
        notes:b.why||"", location:"", attendees:[], status:"planned", category:"",
        remindAt:"", planned:true, taskId:b.taskId||"", projectId:b.projectId||""});
    });
  });
  return out;
}
function eventsOn(all, dateStr){
  return all.filter(e=>e.date===dateStr).sort((a,b)=>a.start-b.start || a.end-b.end);
}

// Side-by-side layout for events sharing a slot — what turns a list into a calendar. Overlapping events are
// grouped, then each takes 1/N of the column's width. Without it two 10:00 meetings hide one another.
function layoutColumn(evs){
  const timed = evs.filter(e=>!e.allDay);
  const groups = []; let cur = [];
  let end = -1;
  timed.forEach(e=>{
    if(cur.length && e.start >= end){ groups.push(cur); cur = []; end = -1; }
    cur.push(e); end = Math.max(end, e.end);
  });
  if(cur.length) groups.push(cur);
  const placed = [];
  groups.forEach(g=>{
    const cols = [];                                    // greedy column packing inside the overlap group
    g.forEach(e=>{
      let ci = cols.findIndex(c => c[c.length-1].end <= e.start);
      if(ci < 0){ cols.push([e]); ci = cols.length-1; } else { cols[ci].push(e); }
      placed.push({ev:e, col:ci});
    });
    const n = cols.length;
    placed.slice(-g.length).forEach(p=>{ p.of = n; });
  });
  return placed;
}

// ── one event chip, in the time grid ──────────────────────────────────────────────────────────────────
function badges(ev){
  const box = el2("span","agbadges");
  if(ev.remindAt){
    const b=el2("span","agbadge"); b.title=tt("has_reminder",{at:ev.remindAt},"Aviso programado: {at}");
    b.appendChild(svgEl(ICO_BELL)); box.appendChild(b);
  }
  const n = (ev.attendees||[]).length;
  if(n){
    const b=el2("span","agbadge"); b.appendChild(svgEl(ICO_USERS)); b.appendChild(el2("span",null,String(n)));
    b.title=tt("n_people",{n},"{n} personas"); box.appendChild(b);
  }
  return box;
}
function chipClasses(ev){
  return "agev" + (ev.planned ? " planned" : (ev.status==="pending" ? " pending" : ""));
}
function timeLabel(ev){
  if(ev.allDay) return tt("all_day", null, "Todo el día");
  return `${hhmm(ev.start)}–${hhmm(ev.end)}`;
}

// ── the grid (day + week share it) ────────────────────────────────────────────────────────────────────
const HOUR_PX = 46, GUTTER = 46;

function hourRange(evs){
  let lo = 8*60, hi = 20*60;
  evs.forEach(e=>{ if(e.allDay) return; lo = Math.min(lo, e.start); hi = Math.max(hi, e.end); });
  lo = Math.max(0, Math.floor(lo/60)*60 - 60);
  hi = Math.min(24*60, Math.ceil(hi/60)*60 + 60);
  if(hi - lo < 8*60) hi = Math.min(24*60, lo + 8*60);
  return [lo, hi];
}

function renderGrid(host, dates, all, data, onPick, onDayPick){
  const today = data.date || ymd(new Date());
  const visible = [];
  dates.forEach(d=>{ eventsOn(all, d).forEach(e=>visible.push(e)); });
  const [lo, hi] = hourRange(visible);
  const cols = `${GUTTER}px repeat(${dates.length},minmax(0,1fr))`;

  const head = el2("div","aghead"); head.style.gridTemplateColumns = cols;
  head.appendChild(el2("div","agdh"));                  // gutter corner
  dates.forEach(d=>{
    const dt = parseYmd(d);
    const h = el2("div","agdh" + (d===today?" today":"") + (dates.length>1?" pick":""));
    h.appendChild(el2("div","agdw", fmtDate(dt,{weekday:"short"},"").replace(/\.$/,"")));
    h.appendChild(el2("div","agdn", String(dt.getDate())));
    if(dates.length>1){ h.onclick=()=>onDayPick(d); h.title=fmtDate(dt,{weekday:"long",day:"numeric",month:"long"},d); }
    head.appendChild(h);
  });
  host.appendChild(head);

  // ALL-DAY band — a row above the hours, exactly where every calendar puts it.
  const anyAllDay = visible.some(e=>e.allDay);
  if(anyAllDay){
    const band = el2("div","agallday"); band.style.gridTemplateColumns = cols;
    band.appendChild(el2("div","agalllb", tt("all_day_short", null, "Todo el día")));
    dates.forEach(d=>{
      const cell = el2("div","agallcell");
      eventsOn(all, d).filter(e=>e.allDay).forEach(e=>{
        const chip = el2("div", chipClasses(e)+" allday");
        chip.style.setProperty("--evc", hueOf(e));
        chip.appendChild(el2("div","agevt", e.title));
        chip.onclick = ev => { ev.stopPropagation(); onPick(e); };
        cell.appendChild(chip);
      });
      band.appendChild(cell);
    });
    host.appendChild(band);
  }

  const grid = el2("div","aggrid"); grid.style.gridTemplateColumns = cols;
  const height = (hi-lo)/60*HOUR_PX;
  const gut = el2("div","aghours"); gut.style.height = height+"px";
  for(let m=lo; m<=hi; m+=60){
    const lb = el2("div","aghour", hhmm(m)); lb.style.top = ((m-lo)/60*HOUR_PX)+"px"; gut.appendChild(lb);
  }
  grid.appendChild(gut);

  dates.forEach(d=>{
    const col = el2("div","agcol"); col.style.height = height+"px";
    for(let m=lo; m<=hi; m+=30){
      const line = el2("div","agline" + (m%60?" half":""));
      line.style.top = ((m-lo)/60*HOUR_PX)+"px"; col.appendChild(line);
    }
    if(d===today && data.now){
      const nowM = mins(data.now);
      if(nowM>=lo && nowM<=hi){
        const n = el2("div","agnow"); n.style.top = ((nowM-lo)/60*HOUR_PX)+"px";
        n.title = tt("now", null, "Ahora"); col.appendChild(n);
      }
    }
    layoutColumn(eventsOn(all, d)).forEach(p=>{
      const e = p.ev, of = p.of || 1;
      const chip = el2("div", chipClasses(e));
      chip.style.setProperty("--evc", hueOf(e));
      chip.style.top = ((e.start-lo)/60*HOUR_PX)+"px";
      chip.style.height = Math.max(20, (e.end-e.start)/60*HOUR_PX - 2)+"px";
      chip.style.left = (p.col*100/of)+"%";
      chip.style.width = `calc(${100/of}% - 3px)`;
      chip.appendChild(el2("div","agevt", e.title));
      const h = el2("div","agevh", hhmm(e.start));
      h.appendChild(badges(e)); chip.appendChild(h);
      chip.title = `${timeLabel(e)} · ${e.title}`;
      chip.onclick = ev => { ev.stopPropagation(); onPick(e); };
      col.appendChild(chip);
    });
    grid.appendChild(col);
  });
  host.appendChild(grid);

  // The sticky all-day band has to sit exactly under the sticky header, whose height depends on the fonts.
  raf(()=>{ try{ host.style.setProperty("--aghead-h", head.offsetHeight+"px"); }catch(_){} });
  return {lo, hi, height};
}

// ── MONTH ─────────────────────────────────────────────────────────────────────────────────────────────
function renderMonth(host, anchor, all, data, onPick, onDayPick){
  const today = data.date || ymd(new Date());
  const a = parseYmd(anchor);
  const first = new Date(a.getFullYear(), a.getMonth(), 1);
  const start = startOfWeek(first);
  const dows = el2("div","agmdows");
  for(let i=0;i<7;i++) dows.appendChild(el2("div","agmdow",
    fmtDate(addDays(start,i),{weekday:"short"},"").replace(/\.$/,"")));
  host.appendChild(dows);

  const grid = el2("div","agmgrid");
  const weeks = Math.ceil((((first.getDay()+6)%7) + new Date(a.getFullYear(), a.getMonth()+1, 0).getDate())/7);
  grid.style.gridTemplateRows = `repeat(${weeks},minmax(74px,1fr))`;
  for(let i=0;i<weeks*7;i++){
    const d = addDays(start, i), ds = ymd(d);
    const cell = el2("div","agmcell" + (d.getMonth()!==a.getMonth()?" out":"") + (ds===today?" today":""));
    cell.appendChild(el2("div","agmn", String(d.getDate())));
    const evs = eventsOn(all, ds);
    evs.slice(0,3).forEach(e=>{
      const row = el2("div","agmev" + (e.status==="pending"?" pending":""));
      row.style.setProperty("--evc", hueOf(e));
      row.appendChild(el2("span","agmdot"));
      if(!e.allDay) row.appendChild(el2("span","agmh", hhmm(e.start)));
      row.appendChild(el2("span","agmt", e.title));
      row.title = `${timeLabel(e)} · ${e.title}`;
      row.onclick = ev => { ev.stopPropagation(); onPick(e); };
      cell.appendChild(row);
    });
    if(evs.length>3) cell.appendChild(el2("div","agmore", tt("n_more",{n:evs.length-3},"+{n} más")));
    cell.onclick = ()=>onDayPick(ds);
    grid.appendChild(cell);
  }
  host.appendChild(grid);
}

// ── LIST (Schedule) ───────────────────────────────────────────────────────────────────────────────────
function renderList(host, anchor, all, data, onPick){
  const today = data.date || ymd(new Date());
  const from = anchor;
  const rows = all.filter(e=>e.date >= from).sort((a,b)=>
    a.date.localeCompare(b.date) || a.start-b.start);
  if(!rows.length){
    host.appendChild(el2("div","agempty", tt("nothing_ahead", null, "No tienes nada apuntado a partir de hoy.")));
    return;
  }
  const wrap = el2("div","aglist");
  const byDay = {};
  rows.forEach(e=>{ (byDay[e.date] = byDay[e.date] || []).push(e); });
  Object.keys(byDay).sort().slice(0,60).forEach(ds=>{
    const d = parseYmd(ds);
    const row = el2("div","agday" + (ds===today?" today":""));
    const dd = el2("div","agdaydate");
    dd.appendChild(el2("div","d", String(d.getDate())));
    dd.appendChild(el2("div","w", fmtDate(d,{weekday:"short"},"").replace(/\.$/,"")));
    row.appendChild(dd);
    const evs = el2("div","agdayevs");
    byDay[ds].forEach(e=>{
      const r = el2("div","agrow" + (e.status==="pending"?" pending":""));
      r.style.setProperty("--evc", hueOf(e));
      r.appendChild(el2("div","agrowh", e.allDay ? tt("all_day_short", null, "Todo el día") : hhmm(e.start)));
      r.appendChild(el2("div","agrowt", e.title));
      const meta = [];
      if(e.location) meta.push(e.location);
      if((e.attendees||[]).length) meta.push(tt("n_people",{n:e.attendees.length},"{n} personas"));
      if(meta.length) r.appendChild(el2("div","agrowm", meta.join(" · ")));
      r.appendChild(badges(e));
      r.onclick = ev => { ev.stopPropagation(); onPick(e); };
      evs.appendChild(r);
    });
    row.appendChild(evs);
    wrap.appendChild(row);
  });
  host.appendChild(wrap);
}

// ── DETAIL panel — what an event IS, and the few actions that are real ────────────────────────────────
function renderDetail(root, ev, ctx, state, redraw){
  const veil = el2("div","agveil");
  veil.onclick = e => { if(e.target===veil){ state.sel=null; state.confirmDel=false; redraw(); } };
  const p = el2("div","agpanel"); p.style.setProperty("--evc", hueOf(ev));
  const head = el2("div","agphead");
  head.appendChild(el2("div","agpbar"));
  head.appendChild(el2("div","agptitle", ev.title));
  const x = el2("button","agpx","×"); x.title = tt("close", null, "Cerrar");
  x.onclick = ()=>{ state.sel=null; state.confirmDel=false; redraw(); };
  head.appendChild(x); p.appendChild(head);

  const when = el2("div","agprow"); when.appendChild(svgEl(ICO_CLOCK));
  const d = parseYmd(ev.date);
  when.appendChild(el2("span",null,
    `${fmtDate(d,{weekday:"long",day:"numeric",month:"long"},ev.date)} · ${timeLabel(ev)}`));
  p.appendChild(when);

  if(ev.location){ const r=el2("div","agprow"); r.appendChild(svgEl(ICO_PIN));
    r.appendChild(el2("span",null,ev.location)); p.appendChild(r); }
  if((ev.attendees||[]).length){
    const named = ev.attendees.filter(a=>String(a).trim());
    const r=el2("div","agprow"); r.appendChild(svgEl(ICO_USERS));
    r.appendChild(el2("span",null, named.length
      ? `${ev.attendees.length} · ${named.join(", ")}`
      : tt("n_people",{n:ev.attendees.length},"{n} personas")));
    p.appendChild(r);
  }
  if(ev.remindAt){ const r=el2("div","agprow"); r.appendChild(svgEl(ICO_BELL));
    r.appendChild(el2("span",null, tt("reminder_at",{at:ev.remindAt},"Aviso el {at}"))); p.appendChild(r); }
  if(ev.notes){ const r=el2("div","agprow"); r.appendChild(svgEl(ICO_NOTE));
    r.appendChild(el2("span",null,ev.notes)); p.appendChild(r); }

  if(ev.meeting && (ev.attendees||[]).length){
    const st = el2("div","agpstate " + (ev.status==="pending" ? "pending" : "confirmed"));
    st.appendChild(svgEl(ev.status==="pending" ? ICO_CLOCK : ICO_CHECK));
    st.appendChild(el2("span",null, ev.status==="pending"
      ? tt("state_pending", null, "Sin confirmar por la otra parte")
      : tt("state_confirmed", null, "Confirmada")));
    p.appendChild(st);
  }

  // Only actions that map to a DECLARED data-op — a button that promises what the API cannot do is the
  // failure this widget's own history is made of (V2-540).
  if(ev.meeting){
    const acts = el2("div","agpacts");
    const call = (name, payload) => {
      state.sel = null; state.confirmDel = false;
      Promise.resolve(ctx.action(name, payload)).then(nd => redraw(nd)).catch(()=>redraw());
    };
    if(ev.status === "pending"){
      const b = el2("button",null,"✓ " + tt("mark_confirmed", null, "Ya está confirmada"));
      b.onclick = ()=>call("update_meeting", {title: ev.title, date: ev.date, status: "confirmed"});
      acts.appendChild(b);
    }
    if(!ev.remindAt && !ev.allDay){
      const b = el2("button",null,"🔔 " + tt("remind_2h", null, "Avisarme 2 h antes"));
      b.onclick = ()=>call("set_reminder",
        {title: ev.title, date: ev.date, at: hhmm(Math.max(0, ev.start-120))});
      acts.appendChild(b);
    }
    if(state.confirmDel){
      const yes = el2("button","risk", tt("delete_yes", null, "Sí, cancélala"));
      yes.onclick = ()=>call("cancel_meeting", {title: ev.title, date: ev.date});
      const no = el2("button",null, tt("delete_no", null, "No"));
      no.onclick = ()=>{ state.confirmDel=false; redraw(); };
      acts.appendChild(yes); acts.appendChild(no);
    } else {
      const b = el2("button","risk", tt("delete", null, "Cancelar cita"));
      b.onclick = ()=>{ state.confirmDel=true; redraw(); };
      acts.appendChild(b);
    }
    p.appendChild(acts);
  } else if(ev.planned){
    p.appendChild(el2("div","agnote",
      tt("planned_note", null, "Bloque planificado por tu agenda, no una cita: se recoloca solo al replanificar.")));
  }
  veil.appendChild(p); root.appendChild(veil);
}

// ── CONNECTORS panel — readable rows, not three cramped icons in the header ───────────────────────────
function renderCalendars(root, cals, state, redraw){
  const veil = el2("div","agveil");
  veil.onclick = e => { if(e.target===veil){ state.cals=false; redraw(); } };
  const p = el2("div","agpanel");
  const head = el2("div","agphead");
  head.appendChild(el2("div","agptitle", tt("calendars", null, "Calendarios")));
  const x = el2("button","agpx","×"); x.onclick = ()=>{ state.cals=false; redraw(); };
  head.appendChild(x); p.appendChild(head);
  (cals||[]).forEach(c=>{
    const row = el2("div","agcalrow");
    const ico = el2("div","agcalico"); const spec = CAL_SVG[c.id];
    if(spec){ ico.style.color = spec.color; ico.appendChild(svgEl(spec.path, {fill:true})); }
    else { ico.appendChild(svgEl(ICO_CAL)); }
    row.appendChild(ico);
    row.appendChild(el2("div","agcalname", c.label || c.id));
    const on = c.status === "connected";
    row.appendChild(el2("div","agcalst" + (on?" on":""),
      on ? tt("cal_connected", null, "conectado")
         : (c.status === "unavailable" ? tt("cal_soon", null, "aún no disponible")
                                       : tt("cal_off", null, "sin conectar"))));
    p.appendChild(row);
  });
  p.appendChild(el2("div","agnote", tt("cal_footer", null,
    "Mientras no haya ninguno conectado, esta agenda es la de Zaelar: lo que le dictes vive aquí.")));
  veil.appendChild(p); root.appendChild(veil);
}

// ── the render ────────────────────────────────────────────────────────────────────────────────────────
export function render(el, data, ctx){
  injectStyles();
  if(el._timer){ clearInterval(el._timer); el._timer=null; }
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  _LANG = (ctx && ctx.lang) || "es";

  const today = data.date || ymd(new Date());
  if(!el._ag) el._ag = {view:"week", anchor:today, sel:null, cals:false, confirmDel:false, viewN:null};
  const S = el._ag;

  // A VIEW PUSHED FROM VOICE (`show_day`). Applied only when its token MOVES, so a plain refresh never
  // yanks what the operator is reading — but asking twice for the same day still lands, because the token
  // is a counter and not the day itself.
  const pushed = data.view;
  if(pushed && pushed.n !== S.viewN){
    S.viewN = pushed.n;
    const want = String(pushed.sel||"");
    if(want==="week" || want==="month" || want==="list"){ S.view = want; S.anchor = today; }
    else if(/^\d{4}-\d{2}-\d{2}$/.test(want)){ S.view = "day"; S.anchor = want; }
    S.sel = null;
  }
  if(!S.anchor) S.anchor = today;

  const all = eventsOf(data);
  const anchor = parseYmd(S.anchor);
  const redraw = nd => render(el, (nd && typeof nd === "object" && nd.date) ? nd : data, ctx);

  el.className = "hb-agenda";
  el.textContent = "";                                   // reset (never innerHTML)

  // ── toolbar ────────────────────────────────────────────────────────────────────────────────────────
  const bar = el2("div","agbar");
  const brand = el2("div","agbrand"); brand.appendChild(svgEl(ICO_CAL)); bar.appendChild(brand);

  let rangeTxt = "", dates = [];
  if(S.view === "week"){
    const s = startOfWeek(anchor);
    for(let i=0;i<7;i++) dates.push(ymd(addDays(s,i)));
    const e = addDays(s,6);
    rangeTxt = (s.getMonth()===e.getMonth())
      ? `${s.getDate()} – ${e.getDate()} ${fmtDate(e,{month:"long",year:"numeric"},"")}`
      : `${s.getDate()} ${fmtDate(s,{month:"short"},"")} – ${e.getDate()} ${fmtDate(e,{month:"short",year:"numeric"},"")}`;
  } else if(S.view === "day"){
    dates = [S.anchor];
    rangeTxt = fmtDate(anchor,{weekday:"long",day:"numeric",month:"long"}, S.anchor);
  } else if(S.view === "month"){
    rangeTxt = fmtDate(anchor,{month:"long",year:"numeric"}, S.anchor);
  } else {
    rangeTxt = tt("upcoming", null, "Próximamente");
  }
  bar.appendChild(el2("div","agrange", rangeTxt));

  const nav = el2("div","agnav");
  const step = (n) => {
    const a = parseYmd(S.anchor);
    S.anchor = ymd(S.view==="month" ? new Date(a.getFullYear(), a.getMonth()+n, 1)
                                    : addDays(a, n * (S.view==="week" ? 7 : 1)));
    S.sel = null; render(el, data, ctx);
  };
  const prev = el2("button"); prev.appendChild(svgEl(ICO_PREV));
  prev.title = tt("prev", null, "Anterior"); prev.dataset.nav = "prev"; prev.onclick = ()=>step(-1);
  const now = el2("button", null, tt("today", null, "Hoy")); now.dataset.nav = "today";
  now.onclick = ()=>{ S.anchor = today; S.sel = null; render(el, data, ctx); };
  const next = el2("button"); next.appendChild(svgEl(ICO_NEXT));
  next.title = tt("next", null, "Siguiente"); next.dataset.nav = "next"; next.onclick = ()=>step(1);
  if(S.view !== "list"){ nav.appendChild(prev); }
  nav.appendChild(now);
  if(S.view !== "list"){ nav.appendChild(next); }
  bar.appendChild(nav);
  el.appendChild(bar);

  // ── view band ──────────────────────────────────────────────────────────────────────────────────────
  const views = el2("div","agviews");
  [["day", tt("day", null, "Día")], ["week", tt("week", null, "Semana")],
   ["month", tt("month", null, "Mes")], ["list", tt("list", null, "Lista")]].forEach(([id,label])=>{
    const t = el2("button","agtab" + (S.view===id?" on":""), label);
    t.dataset.view = id;
    t.onclick = ()=>{ S.view = id; S.sel = null; render(el, data, ctx); };
    views.appendChild(t);
  });
  const calBtn = el2("button","agcalbtn" + (S.cals?" on":""));
  calBtn.appendChild(svgEl(ICO_PLUG));
  calBtn.appendChild(el2("span",null, tt("calendars", null, "Calendarios")));
  calBtn.title = tt("calendars_hint", null, "Qué calendarios están conectados");
  calBtn.onclick = ()=>{ S.cals = !S.cals; render(el, data, ctx); };
  views.appendChild(calBtn);
  el.appendChild(views);

  // ── body ───────────────────────────────────────────────────────────────────────────────────────────
  const body = el2("div","agbody");
  const pick = e => { S.sel = e.key; S.confirmDel = false; render(el, data, ctx); };
  const pickDay = ds => { S.view = "day"; S.anchor = ds; S.sel = null; render(el, data, ctx); };

  let active = null;
  if(S.view === "week"){
    renderGrid(body, dates, all, data, pick, pickDay);
  } else if(S.view === "month"){
    renderMonth(body, S.anchor, all, data, pick, pickDay);
  } else if(S.view === "list"){
    renderList(body, today, all, data, pick);
  } else {
    // DAY = the hour grid plus the coach rail this widget has always had (Now + countdown + task actions).
    const wrap = el2("div","agday-wrap");
    const gridBox = el2("div","agday-grid");
    renderGrid(gridBox, dates, all, data, pick, pickDay);
    wrap.appendChild(gridBox);

    const isToday = S.anchor === today;
    const dayPlan = (data.days||[]).find(d=>d.date===S.anchor);
    const plan = (dayPlan && dayPlan.plan) || (isToday ? (data.plan||{}) : {});
    active = isToday ? data.active : null;

    const side = el2("div","agside");
    const focus = (plan.focus||[]);
    if(focus.length){
      const chips = el2("div","agchips");
      focus.forEach(f=>{ const c=el2("span","agchip","🎯 " + (f.label!=null?f.label:""));
        if(f.objective!=null) c.setAttribute("title", String(f.objective)); chips.appendChild(c); });
      side.appendChild(chips);
    }
    const card = el2("div","agcard");
    if(isToday){
      card.appendChild(el2("div","agk", tt("now", null, "Ahora")));
      card.appendChild(el2("div","agtask", active ? active.label : "—"));
      const cnt = el2("div","agcount", active ? fmtCount(active.remaining_min||0) : "—");
      cnt.id = "hb-count"; card.appendChild(cnt);
      const taskId = active && active.taskId;
      if(taskId){
        const acts = el2("div","agacts");
        [["done","✓ "+tt("done", null, "Hecha"),"done"], ["not_now", tt("not_now", null, "No me apetece")],
         ["snooze", tt("snooze", null, "Posponer")], ["drop", tt("drop", null, "Quitar tarea")]]
          .forEach(([a,label,extra])=>{ const b=el2("button",extra||null,label); b.dataset.a=a; b.dataset.tid=taskId;
            if(active.projectId) b.dataset.pid=active.projectId; acts.appendChild(b); });
        card.appendChild(acts);
      } else {
        card.appendChild(el2("div","agwarn", tt("no_active", null, "Ahora mismo no hay tarea activa de foco.")));
      }
    } else {
      card.appendChild(el2("div","agk", fmtDate(anchor,{weekday:"long"}, S.anchor)));
      card.appendChild(el2("div","agtask", plan.summary || tt("planned_day", null, "Día planificado")));
    }
    side.appendChild(card);
    ((isToday ? data.coaching : plan.coaching)||[]).forEach(c=>side.appendChild(el2("div","agnudge","🧭 "+c)));
    ((isToday ? data.warnings : plan.warnings)||[]).forEach(w=>side.appendChild(el2("div","agwarn","⚠ "+w)));
    const replan = el2("button","agchip","↻ " + tt("replan", null, "Replanificar"));
    replan.dataset.a = "replan"; replan.style.cursor = "pointer"; side.appendChild(replan);
    wrap.appendChild(side);
    body.appendChild(wrap);
  }
  el.appendChild(body);

  // ── overlays ───────────────────────────────────────────────────────────────────────────────────────
  if(S.sel){
    const ev = all.find(e=>e.key===S.sel);
    if(ev) renderDetail(el, ev, ctx, S, redraw); else S.sel = null;
  }
  if(S.cals) renderCalendars(el, data.calendars||[], S, ()=>render(el, data, ctx));

  // Live countdown for the active block (today only).
  if(active){
    let rem = (active.remaining_min||0)*60;
    el._timer = setInterval(()=>{ rem -= 1; const c = el.querySelector("#hb-count");
      if(c) c.textContent = fmtCount(rem/60); if(rem<=0) clearInterval(el._timer); }, 1000);
  }

  // Coach actions → host applies + re-renders.
  el.querySelectorAll("[data-a]").forEach(btn=>btn.onclick = async ()=>{
    const p = {}; if(btn.dataset.tid) p.taskId = btn.dataset.tid; if(btn.dataset.pid) p.projectId = btn.dataset.pid;
    const nd = await ctx.action(btn.dataset.a, p);
    if(nd) render(el, nd, ctx);
  });

  // Open the grid on the working hours instead of at midnight-ish, once per paint.
  if(S.view === "day" || S.view === "week"){
    const scroller = el.querySelector(".agday-grid") || el.querySelector(".agbody");
    if(scroller){
      const [lo] = hourRange(dates.flatMap(d=>eventsOn(all, d)));
      const target = Math.max(0, (mins(isFinite(mins(data.now))&&S.anchor===today ? data.now : "08:00") - lo - 60)/60*HOUR_PX);
      raf(()=>{ try{ scroller.scrollTop = target; }catch(_){} });
    }
  }
}
