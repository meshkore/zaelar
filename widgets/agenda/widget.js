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
  if(prev && (prev.dataset||{}).v === "691") return;   // dataset is optional on a foreign node
  if(prev) prev.remove();                      // an older build's sheet would fight this one, silently
  const s=document.createElement("style"); s.id="hb-agenda-css"; s.dataset.v="691"; s.textContent=`
  /* The card decides the size (manifest.size); the widget fills it and scrolls INSIDE — the operator's
     report was «se muestra muy pequeño, se cortan las palabras de abajo». :has reaches the card chrome
     (.hb-scroll wraps the widget root) exactly as the video widget does since V2-636. */
  .hb-scroll:has(> .hb-agenda){overflow:hidden}
  .hb-agenda{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    color:var(--hb-ink,#0d1622);width:100%;height:100%;box-sizing:border-box;
    display:flex;flex-direction:column;gap:0;position:relative;min-height:0}

  /* ── TOOLBAR: brand · range title · ‹ Hoy › — one line, like every calendar ─────────────────────── */
  /* V2-690 — four levels, and only ONE of them needs a rule to be legible: the window's own title bar
     already draws a full-weight line right above this, so the calendar header is separated from the view
     nav by SPACE and by type, and the single hairline left on the screen is the subtle one under the nav.
     Two full-weight lines a few pixels apart was the redundancy the operator was looking at. */
  .hb-agenda .agbar{display:flex;align-items:center;gap:var(--sp-2,8px);padding:0 0 var(--sp-3,12px);
    flex:0 0 auto;min-width:0}
  .hb-agenda .agbrand{width:26px;height:26px;border-radius:8px;background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);
    display:flex;align-items:center;justify-content:center;flex:0 0 auto}
  .hb-agenda .agbrand svg{width:15px;height:15px;display:block}
  /* the range is the CONTENT's header, so it sits one step under the window title rather than over it —
     a 15/700 range beside a 14/600 window name inverted the hierarchy it was supposed to express. */
  .hb-agenda .agrange{font-size:14px;font-weight:600;letter-spacing:-.01em;white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis;flex:1 1 auto;min-width:0}
  /* «14 – 20 Septiembre De 2026»: text-transform:capitalize raises EVERY word, which is an English
     convention and wrong in the language this ships in. Only the first letter is ours to raise. */
  .hb-agenda .agrange::first-letter{text-transform:uppercase}
  .hb-agenda .agnav{display:flex;align-items:center;gap:4px;flex:0 0 auto}
  .hb-agenda .agnav button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);border-radius:var(--hb-r-s,8px);height:var(--hb-ctl-h-sm,32px);
    min-width:var(--hb-ctl-h-sm,32px);padding:0 var(--sp-2,8px);font-size:13px;
    font-weight:600;cursor:pointer;line-height:1;display:flex;align-items:center;justify-content:center}
  .hb-agenda .agnav button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agnav svg{width:13px;height:13px;display:block}

  /* ── VIEW BAND: a defined strip, active view an INVERTED chip (the V2-636 language) ─────────────── */
  .hb-agenda .agviews{display:flex;align-items:center;gap:var(--sp-1,4px);flex-wrap:nowrap;overflow-x:auto;
    border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.06));
    padding-bottom:var(--sp-2,8px);margin-bottom:var(--sp-4,16px);flex:0 0 auto;
    scrollbar-width:none}
  .hb-agenda .agviews::-webkit-scrollbar{display:none}
  .hb-agenda .agtab{border:0;background:none;color:var(--hb-muted,#5b6b82);border-radius:999px;
    padding:var(--sp-2,8px) var(--sp-3,12px);font-size:13px;font-weight:600;cursor:pointer;line-height:1.2;
    white-space:nowrap;flex:0 0 auto;font-family:var(--sans,system-ui)}
  .hb-agenda .agtab:hover{background:var(--hb-hover,#242A34);color:var(--hb-ink,#0d1622)}
  /* V2-690 — SELECTED is said the same way everywhere in the product now (the chat's tabs, the tray's open
     panel, the dock's active app): an accent-tinted chip with an accent ring. The inverted near-white pill
     this used to be was a SECOND filled language on the screen, and the loudest thing on the card. */
  .hb-agenda .agtab.on{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);
    color:var(--hb-ink,#F2F4F7);font-weight:700;
    box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent)}
  /* «disabled» has to read as unavailable, not as absent — the tabs are still the map of where you are.
     V2-691 MEASURED it on the connectors screen, which is the only place they are ever disabled and which
     no audit had ever reached: at .6 the effective ink came out at 4.25:1, under the floor. .75 keeps a
     clear step below an enabled tab (5.8:1 against 9.4:1) and stays over it. */
  .hb-agenda .agtab:disabled{opacity:.75;cursor:default;pointer-events:none}
  /* Platform icons + Conectores button, ONE right-aligned cluster — mirroring the messaging widget's own
     header pattern (icons for every provider, a door into the connectors screen), per the operator's V2-679
     follow-up: «he dicho que hay un icono, un botón para conectores y luego a la izquierda los tres iconos». */
  .hb-agenda .agviewsright{margin-left:auto;display:flex;align-items:center;gap:10px;flex:0 0 auto}
  .hb-agenda .agconnicons{display:flex;align-items:center;gap:4px}
  .hb-agenda .agconnicon{width:var(--hb-icon-h,28px);height:var(--hb-icon-h,28px);border-radius:var(--hb-r-s,8px);
    border:0;background:none;cursor:pointer;
    display:flex;align-items:center;justify-content:center;opacity:.72}
  .hb-agenda .agconnicon svg{width:15px;height:15px;display:block}
  .hb-agenda .agconnicon:hover:not(:disabled){opacity:1;background:var(--hb-bg-soft,#f4f7fb)}
  .hb-agenda .agconnicon.on{opacity:1}
  .hb-agenda .agconnicon.off{opacity:.4;cursor:default}
  .hb-agenda .agcalbtn{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);border-radius:var(--hb-r-s,8px);height:var(--hb-ctl-h-sm,32px);
    padding:0 var(--sp-3,12px);font-size:13px;font-weight:600;
    cursor:pointer;display:flex;align-items:center;gap:7px;flex:0 0 auto}
  .hb-agenda .agcalbtn:hover,.hb-agenda .agcalbtn.on{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agcalbtn svg{width:14px;height:14px;display:block}

  .hb-agenda .agbody{flex:1 1 auto;min-height:0;overflow:auto;position:relative}

  /* ── TIME GRID (day + week) ──────────────────────────────────────────────────────────────────────── */
  .hb-agenda .aghead{display:grid;position:sticky;top:0;z-index:3;background:var(--hb-bg,#fff);
    border-bottom:1px solid var(--hb-line,#e3e8f0)}
  .hb-agenda .agdh{padding:5px 4px 7px;text-align:center;min-width:0;border-left:1px solid var(--hb-line,#eef1f6)}
  .hb-agenda .agdh:first-child{border-left:0}
  .hb-agenda .agdh .agdw{font-size:12px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--hb-muted-2,#9aa7b8);font-weight:700}
  .hb-agenda .agdh .agdn{font-size:17px;font-weight:600;line-height:1.35;color:var(--hb-ink,#0d1622);
    width:29px;height:29px;margin:1px auto 0;border-radius:50%;display:flex;align-items:center;justify-content:center}
  .hb-agenda .agdh.today .agdw{color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agdh.today .agdn{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216)}
  .hb-agenda .agdh.pick{cursor:pointer}
  .hb-agenda .agdh.pick:hover .agdn{background:var(--hb-bg-soft,#f4f7fb)}
  .hb-agenda .agdh.today.pick:hover .agdn{background:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agallday{display:grid;border-bottom:1px solid var(--hb-line,#e3e8f0);position:sticky;
    top:var(--aghead-h,54px);z-index:2;background:var(--hb-bg,#fff);min-height:22px}
  .hb-agenda .agallcell{padding:3px;display:flex;flex-direction:column;gap:2px;min-width:0;
    border-left:1px solid var(--hb-line,#eef1f6)}
  .hb-agenda .agallcell:first-child{border-left:0}
  .hb-agenda .agalllb{font-size:12px;color:var(--hb-muted-2,#9aa7b8);text-transform:uppercase;
    letter-spacing:.06em;padding:5px 4px 0;text-align:right;font-weight:700}
  .hb-agenda .aggrid{display:grid;position:relative}
  .hb-agenda .aghours{position:relative}
  .hb-agenda .aghour{position:absolute;right:6px;font-size:12px;color:var(--hb-muted-2,#9aa7b8);
    font-variant-numeric:tabular-nums;transform:translateY(-50%)}
  .hb-agenda .agcol{position:relative;border-left:1px solid var(--hb-line,#eef1f6);min-width:0}
  .hb-agenda .agline{position:absolute;left:0;right:0;border-top:1px solid var(--hb-line,#eef1f6);
    pointer-events:none}
  .hb-agenda .agline.half{border-top-style:dotted;opacity:.55}
  /* HALF-HOUR SLOTS — the empty calendar is a SURFACE, not a backdrop (V2-693). His ask: «asegúrate de que
     el widget permite clicar en algún punto para añadir un ítem, y cuando pase el ratón por encima de los
     cuadritos se pueden iluminar». They sit UNDER the chips (z-index) so an event still takes its own click,
     and each one carries its own minute — no offsetY arithmetic that drifts when the row height changes. */
  .hb-agenda .agslot{position:absolute;left:0;right:0;cursor:pointer;border-radius:5px}
  .hb-agenda .agslot:hover{background:color-mix(in srgb, var(--hb-accent,#6c5ce7) 13%, transparent);
    box-shadow:inset 0 0 0 1px color-mix(in srgb, var(--hb-accent,#6c5ce7) 42%, transparent)}
  .hb-agenda .agslot::after{content:"+";position:absolute;right:5px;top:50%;transform:translateY(-50%);
    font-size:13px;font-weight:700;line-height:1;color:var(--hb-accent,#6c5ce7);opacity:0}
  .hb-agenda .agslot:hover::after{opacity:.95}
  .hb-agenda .agnow{position:absolute;left:0;right:0;height:0;border-top:2px solid var(--hb-risk,#e5484d);z-index:4}
  .hb-agenda .agnow::before{content:"";position:absolute;left:-4px;top:-5px;width:8px;height:8px;
    border-radius:50%;background:var(--hb-risk,#e5484d)}

  /* ── EVENT CHIP: hue = category, INTENSITY = how settled it is ──────────────────────────────────── */
  .hb-agenda .agev{position:absolute;z-index:2;box-sizing:border-box;border-radius:7px;padding:3px 6px;overflow:hidden;
    cursor:pointer;border:1px solid transparent;border-left:3px solid var(--evc,#3D6FE0);
    background:color-mix(in srgb, var(--evc,#3D6FE0) 17%, transparent);min-height:20px;
    display:flex;flex-direction:column;gap:1px;line-height:1.2}
  .hb-agenda .agev:hover{filter:brightness(1.07)}
  .hb-agenda .agev.pending{background:color-mix(in srgb, var(--evc,#3D6FE0) 7%, transparent);
    border:1px dashed var(--evc,#3D6FE0);border-left-width:3px;border-left-style:solid}
  .hb-agenda .agev.planned{background:color-mix(in srgb, var(--evc,#3D6FE0) 8%, transparent);
    border-left-width:2px;opacity:.92}
  .hb-agenda .agev.sel{box-shadow:0 0 0 2px var(--evc,#3D6FE0)}
  .hb-agenda .agevt{font-size:13px;font-weight:600;color:var(--hb-ink,#0d1622);white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis;min-width:0}
  /* A SHORT EVENT GETS ONE LINE. A 30-minute chip is 21px tall and was being given a title line plus an
     hour line — ~36px of content inside it — so overflow:hidden cut the second one through the middle of
     its glyphs. That is the «texto pegado, se ven cosas raras» the operator photographed on a 15:00–15:30
     appointment. The hour is already said by WHERE the chip is, and the tooltip carries it in full. */
  .hb-agenda .agev.tight{padding:1px 6px;justify-content:center}
  .hb-agenda .agev.tight .agevh{display:none}
  .hb-agenda .agev.tiny .agevt{font-size:11px;letter-spacing:-.01em}
  /* A NARROW chip cannot hold words; it can still hold its first letters, which is what he asked for
     («solo se muestra un trozo o las tres primeras letras»). Below that the ellipsis itself is the content,
     so the padding gets out of its way instead of eating it. */
  .hb-agenda .agev.narrow{padding-left:3px;padding-right:2px;border-left-width:2px}
  .hb-agenda .agev.narrow .agevt{font-size:11px;font-weight:700}
  .hb-agenda .agev.narrow .agevh{display:none}
  /* «+N» — the honest end of the lane budget. Below a readable width a chip is a coloured bar, so the
     overflow says HOW MANY are hidden and takes you to the day view, where the column is the whole card. */
  .hb-agenda .agev.more{background:var(--hb-bg-soft,#fbfdff);border:1px dashed var(--hb-line,#c9d3e0);
    border-left:1px dashed var(--hb-line,#c9d3e0);align-items:center;justify-content:center}
  .hb-agenda .agev.more .agevt{font-size:11px;font-weight:700;color:var(--hb-muted,#5b6b82)}
  .hb-agenda .agevh{font-size:12px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:5px}
  .hb-agenda .agbadges{display:inline-flex;align-items:center;gap:5px;flex:0 0 auto}
  .hb-agenda .agbadge{display:inline-flex;align-items:center;gap:2px;font-size:12px;color:var(--hb-muted,#5b6b82);
    font-variant-numeric:tabular-nums}
  .hb-agenda .agbadge svg{width:10px;height:10px;display:block}
  .hb-agenda .agev.allday{position:static;min-height:0;padding:2px 6px}

  /* ── NEW-APPOINTMENT COMPOSER (V2-693) ───────────────────────────────────────────────────────────── */
  .hb-agenda .agaddp{gap:9px}
  .hb-agenda .agfield{width:100%;box-sizing:border-box;font:inherit;font-size:13px;
    color:var(--hb-ink,#0d1622);background:var(--hb-bg,#fff);
    border:1px solid var(--hb-line,#d7dfea);border-radius:var(--hb-r-s,8px);padding:7px 9px}
  .hb-agenda .agfield:focus{outline:none;border-color:var(--hb-accent,#6c5ce7);
    box-shadow:0 0 0 2px color-mix(in srgb, var(--hb-accent,#6c5ce7) 22%, transparent)}
  .hb-agenda .agfrow{display:flex;gap:7px}
  .hb-agenda .agftime{flex:1 1 auto;min-width:0}
  .hb-agenda .agfdur{flex:0 0 auto;width:104px}
  .hb-agenda .agfcheck{display:flex;align-items:center;gap:7px;font-size:13px;
    color:var(--hb-muted,#5b6b82);cursor:pointer}

  /* ── MONTH ───────────────────────────────────────────────────────────────────────────────────────── */
  .hb-agenda .agmgrid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:0;height:100%;
    border-top:1px solid var(--hb-line,#e3e8f0);border-left:1px solid var(--hb-line,#e3e8f0)}
  .hb-agenda .agmdow{font-size:12px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--hb-muted-2,#9aa7b8);text-align:center;font-weight:700;padding:5px 0}
  .hb-agenda .agmdows{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));flex:0 0 auto}
  .hb-agenda .agmcell{min-height:74px;border-right:1px solid var(--hb-line,#e3e8f0);
    border-bottom:1px solid var(--hb-line,#e3e8f0);padding:3px 4px;display:flex;flex-direction:column;gap:2px;
    overflow:hidden;cursor:pointer;background:var(--hb-bg,#fff)}
  .hb-agenda .agmcell:hover{background:var(--hb-bg-soft,#f4f7fb)}
  .hb-agenda .agmcell.out{background:var(--hb-bg-soft,#fbfdff);opacity:.62}
  .hb-agenda .agmn{font-size:13px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;
    align-self:flex-start;width:20px;height:20px;border-radius:50%;display:flex;align-items:center;
    justify-content:center;flex:0 0 auto}
  .hb-agenda .agmcell.today .agmn{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);font-weight:700}
  .hb-agenda .agmev{display:flex;align-items:center;gap:4px;font-size:12px;min-width:0;
    padding:1px 4px;border-radius:5px;background:color-mix(in srgb, var(--evc,#3D6FE0) 15%, transparent);
    cursor:pointer}
  .hb-agenda .agmev.pending{background:transparent;border:1px dashed var(--evc,#3D6FE0)}
  .hb-agenda .agmdot{width:6px;height:6px;border-radius:50%;background:var(--evc,#3D6FE0);flex:0 0 auto}
  .hb-agenda .agmt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--hb-ink,#0d1622)}
  .hb-agenda .agmh{color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;flex:0 0 auto}
  .hb-agenda .agmore{font-size:12px;color:var(--hb-muted-2,#9aa7b8);padding-left:3px}

  /* ── LIST (the classic Schedule view) ────────────────────────────────────────────────────────────── */
  .hb-agenda .aglist{display:flex;flex-direction:column;gap:0}
  .hb-agenda .agday{display:flex;gap:12px;padding:9px 2px;border-bottom:1px solid var(--hb-line,#eef1f6);min-width:0}
  .hb-agenda .agdaydate{width:58px;flex:0 0 auto;text-align:center}
  .hb-agenda .agdaydate .d{font-size:19px;font-weight:700;line-height:1.1}
  .hb-agenda .agdaydate .w{font-size:12px;text-transform:uppercase;letter-spacing:.06em;
    color:var(--hb-muted-2,#9aa7b8);font-weight:700}
  .hb-agenda .agday.today .agdaydate .d,.hb-agenda .agday.today .agdaydate .w{color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agdayevs{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:5px}
  .hb-agenda .agrow{display:flex;align-items:center;gap:9px;padding:5px 7px;border-radius:9px;min-width:0;
    cursor:pointer;background:color-mix(in srgb, var(--evc,#3D6FE0) 10%, transparent);
    border-left:3px solid var(--evc,#3D6FE0)}
  .hb-agenda .agrow:hover{background:color-mix(in srgb, var(--evc,#3D6FE0) 18%, transparent)}
  .hb-agenda .agrow.pending{background:transparent;border:1px dashed var(--evc,#3D6FE0);border-left-width:3px;
    border-left-style:solid}
  .hb-agenda .agrowh{font-size:13px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums;
    width:78px;flex:0 0 auto}
  .hb-agenda .agrowt{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    flex:1 1 auto;min-width:0}
  .hb-agenda .agrowm{font-size:13px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;
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
  .hb-agenda .agk{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--hb-muted-2,#9aa7b8);
    font-weight:700}
  .hb-agenda .agtask{font-size:14.5px;font-weight:600}
  .hb-agenda .agcount{font-size:26px;font-variant-numeric:tabular-nums;color:var(--hb-accent2,#16B8A6);
    font-weight:600}
  .hb-agenda .agacts{display:flex;flex-wrap:wrap;gap:6px}
  .hb-agenda .agacts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    border-radius:9px;padding:7px 10px;font-size:13px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-agenda .agacts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agacts .done{border-color:var(--hb-accent2,#16B8A6);color:#0f766e}
  .hb-agenda .agnudge{font-size:13px;color:var(--hb-warn-ink,#9a6a00);background:var(--hb-warn-bg,#fff7e8);
    border:1px solid var(--hb-warn-border,#f2dca6);border-radius:9px;padding:7px 9px}
  .hb-agenda .agwarn{font-size:13px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-agenda .agchip{font-size:13px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;
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
  .hb-agenda .agprow{display:flex;align-items:flex-start;gap:8px;font-size:13px;color:var(--hb-muted,#3a4757);
    line-height:1.35;min-width:0}
  .hb-agenda .agprow svg{width:13px;height:13px;display:block;flex:0 0 auto;margin-top:2px;
    color:var(--hb-muted-2,#9aa7b8)}
  .hb-agenda .agpstate{display:inline-flex;align-items:center;gap:5px;font-size:13px;font-weight:600;
    border-radius:999px;padding:3px 10px;align-self:flex-start}
  /* V2-689 — a state pill reads its colour from the SEMANTIC tokens. These carried literal dark-teal/dark-amber
     ink over a translucent wash, which is legible on paper and invisible on the dark skin the product ships. */
  .hb-agenda .agpstate.confirmed{background:color-mix(in srgb,var(--hb-ok,#5FD3A2) 15%,transparent);
    color:var(--hb-ok,#5FD3A2)}
  .hb-agenda .agpstate.pending{background:color-mix(in srgb,var(--hb-warn,#EFC75E) 15%,transparent);
    color:var(--hb-warn,#EFC75E)}
  .hb-agenda .agpacts{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
  .hb-agenda .agpacts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    border-radius:9px;padding:7px 11px;font-size:13px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-agenda .agpacts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agpacts button.risk:hover{border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}
  /* V2-690 — ONE block per provider: the row, and whatever acts on it, indented to the row's own name
     column so the pair reads as attached instead of floating between two rows. */
  .hb-agenda .agcalgrp{margin-bottom:var(--sp-4,16px)}
  .hb-agenda .agcalgrp .agcalbtn2{margin:var(--sp-2,8px) 0 0 50px}
  .hb-agenda .agcalgrp .agcaldef{padding-left:50px}
  .hb-agenda .agcalrow{display:flex;align-items:center;gap:10px;padding:10px 12px;
    background:var(--hb-bubble,#1D222A);border:1px solid var(--hb-line-subtle,rgba(255,255,255,.06));
    border-radius:var(--hb-r-m,10px)}
  .hb-agenda .agcalico{width:28px;height:28px;border-radius:8px;background:var(--hb-bg,#12151A);
    display:flex;align-items:center;justify-content:center;flex:0 0 auto}
  .hb-agenda .agcalico svg{width:15px;height:15px;display:block}
  .hb-agenda .agcalname{font-size:13px;font-weight:600;flex:1 1 auto;min-width:0;white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis}
  /* V2-691 — the ink was picked for the WIDGET's ground and this pill sits on a lighter rung, where the
     tertiary step loses a point of contrast (5.38:1, the tightest thing left on the screen). A status a
     provider row is ABOUT is not tertiary text anyway. */
  .hb-agenda .agcalst{font-size:13px;font-weight:600;border-radius:999px;padding:3px 9px;flex:0 0 auto;
    background:var(--hb-bg,#f4f7fb);color:var(--hb-muted,#5b6b82)}
  .hb-agenda .agcalst.on{background:color-mix(in srgb,var(--hb-ok,#5FD3A2) 15%,transparent);
    color:var(--hb-ok,#5FD3A2)}
  .hb-agenda .agnote{font-size:13px;color:var(--hb-muted-2,#7d8a9c);line-height:1.4}
  .hb-agenda .agcalst.unconf{background:color-mix(in srgb,var(--hb-warn,#EFC75E) 15%,transparent);
    color:var(--hb-warn,#EFC75E)}
  .hb-agenda .agcalbtn2{margin:6px 4px 2px;align-self:flex-start}
  .hb-agenda .agcaldef{display:flex;flex-direction:column;gap:5px;padding:4px 4px 2px}
  .hb-agenda .agcaldeflabel{font-size:13px;font-weight:600;color:var(--hb-muted,#5b6b82)}
  .hb-agenda .agcaldefrow{display:flex;align-items:center;gap:7px;font-size:13px;cursor:pointer}
  .hb-agenda .agcaldot{width:9px;height:9px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:0 0 auto}

  /* ── CONNECTORS SCREEN — takes over the WHOLE content area (V2-679 follow-up), like the messaging
     widget's own connectors screen, instead of a small floating overlay. .agconnscreen overrides
     .agpanel's modal width (source-order wins at equal specificity) while keeping ".agpanel .agnote"
     reachable for anything that still queries the old selector. ─────────────────────────────────────── */
  /* TOP-LEFT, never centred. «margin:0 auto» floated this column in the middle of a card that is often
     1400px wide: the breadcrumb read as centred, the step box looked «metido ahí en el medio, suelto», and
     the widget wasted the screen it had been given. Centring is also wrong for a GUIDE specifically —
     every step is a different height, so a centred column jumps under the reader between steps. The
     content anchors at the same x as the view tabs above it and stays there. */
  .hb-agenda .agconnscreen{width:100%;max-width:720px;margin:0;box-shadow:none;border:0;padding:2px 0}
  .hb-agenda .agconnhead{display:flex;align-items:center;gap:10px;margin-bottom:4px}
  .hb-agenda .agconnback{cursor:pointer;color:var(--hb-accent,#9B7CFF);font-weight:600;font-size:13px;
    margin-left:auto;flex:0 0 auto;border:0;background:transparent;padding:0;font-family:var(--sans,system-ui)}
  .hb-agenda .agconnback:hover{text-decoration:underline}
  .hb-agenda .agconnback:focus-visible{outline:none;
    box-shadow:var(--hb-focus-ring,0 0 0 2px var(--hb-accent,#9B7CFF));border-radius:4px}
  /* Breadcrumb inside the wizard — same shape as messaging's .crumb (V2-570), so a step-by-step guide
     always tells you where "back" goes: to the connectors list, never out of the widget entirely. */
  /* V2-690 — the breadcrumb needs room of its own: at 14px below it the step card read as hanging off it. */
  .hb-agenda .agwcrumb{display:flex;align-items:center;gap:var(--sp-2,8px);margin:0 0 var(--sp-5,24px);
    font-size:13px}
  .hb-agenda .agwcrumb .agconnback{margin-left:0}
  .hb-agenda .agwsep{color:var(--hb-muted-2,#9aa7b8)}
  .hb-agenda .agwcur{color:var(--hb-ink,#0d1622);font-weight:700}
  .hb-agenda .agwstep{border:1px solid var(--hb-line,rgba(255,255,255,.10));border-radius:var(--hb-r-l,12px);
    padding:var(--sp-4,16px);background:var(--hb-bg-soft,#171B21);margin:2px 0 var(--sp-4,16px)}
  /* V2-690 — the numeral and the title share ONE line box (24px, the badge's own height), so the «1» is
     aligned with the title by construction rather than by whatever the two line heights happened to do. */
  .hb-agenda .agwhead{display:flex;align-items:center;gap:var(--sp-3,12px);margin-bottom:var(--sp-3,12px)}
  .hb-agenda .agwnum{width:24px;height:24px;flex:0 0 auto;border-radius:50%;display:inline-flex;
    align-items:center;justify-content:center;font:700 13px/24px var(--sans,system-ui);
    color:var(--hb-accent,#9B7CFF);
    background:color-mix(in srgb,var(--hb-accent,#9B7CFF) 18%,transparent)}
  .hb-agenda .agwtitle{font:600 15px/24px var(--sans,system-ui);color:var(--hb-ink,#0d1622);min-width:0}
  .hb-agenda .agwcount{margin-left:auto;flex:0 0 auto;font-size:13px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-agenda .agwbody{font-size:14px;color:var(--hb-muted,#4a5a70);line-height:1.6}
  .hb-agenda .agwlink{display:inline-flex;align-items:center;gap:6px;margin:9px 9px 0 0;
    border:1px solid var(--hb-line,rgba(255,255,255,.10));color:var(--hb-ink,#F2F4F7);
    background:var(--hb-bubble,#1D222A);border-radius:var(--hb-r-m,10px);
    padding:9px 14px;font-size:13px;font-weight:600;text-decoration:none}
  .hb-agenda .agwlink:hover{border-color:var(--hb-line-strong,rgba(255,255,255,.18));
    background:var(--hb-hover,#242A34)}
  .hb-agenda .agwtip{margin-top:10px;font-size:13px;color:var(--hb-muted,#A7AFBC);
    background:var(--hb-bubble,#1D222A);border:1px solid var(--hb-line-subtle,rgba(255,255,255,.06));
    border-radius:var(--hb-r-m,10px);padding:9px 11px;line-height:1.55}
  .hb-agenda .agwerr{margin-top:10px;font-size:13px;color:var(--hb-risk,#e5484d);line-height:1.5}
  /* A button is the size of its label. «flex:1 1 auto» made the primary swallow every spare pixel of the
     row — «un botón gigante» — which also destroyed the one thing a wizard's footer is for: the same
     control in the same place on every step. Natural width, a comfortable floor, and the pair sits under
     the step box where the reader's eye already is. */
  /* V2-690 — THE STEP'S ACTION ZONE. «Atrás» and «Conectar Google Calendar» used to sit outside the step
     box entirely, floating on the card's ground with nothing tying them to the thing they act on. They are
     inside it now, under a hairline: the panel says what the step is, the band under it says what you can do
     about it, and the pair still lands in the same place on every step. */
  .hb-agenda .agwfoot{display:flex;gap:var(--sp-2,8px);align-items:center;
    margin:var(--sp-4,16px) 0 0;padding-top:var(--sp-4,16px);
    border-top:1px solid var(--hb-line-subtle,rgba(255,255,255,.06))}
  .hb-agenda .agwfoot .agcalbtn2{flex:0 0 auto;margin:0;min-width:104px}
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
  groups.forEach((g, gi)=>{
    const cols = [];                                    // greedy column packing inside the overlap group
    g.forEach(e=>{
      let ci = cols.findIndex(c => c[c.length-1].end <= e.start);
      if(ci < 0){ cols.push([e]); ci = cols.length-1; } else { cols[ci].push(e); }
      placed.push({ev:e, col:ci, g:gi});
    });
    const n = cols.length;
    placed.slice(-g.length).forEach(p=>{ p.of = n; });
  });
  return placed;
}

// How many events may sit side by side before the column stops being readable. Measured on the operator's
// own week: SIX appointments at 17:00 in a ~110px column is 18px each — not a truncated title, a coloured
// bar. «No se puede dejar así de mal.» Past the budget the last lane becomes a «+N» that opens the day.
//
// It is a BUDGET, not a constant, and that is the half a first attempt got wrong: with one number for every
// view, the «+N» in the week opened a day that still said «+N» — a dead end dressed as a way out. A day
// column is the whole card, so it holds what a seventh of it cannot, and the overflow always has somewhere
// wider to send you.
function laneBudget(nDates){ return nDates > 1 ? 3 : 8; }

// Trim each overlap group to the lane budget and hand back what has to be drawn: the chips that fit, plus
// one overflow marker per group that had to hide something.
function lanes(placed, budget){
  const byGroup = new Map();
  placed.forEach(p=>{ if(!byGroup.has(p.g)) byGroup.set(p.g, []); byGroup.get(p.g).push(p); });
  const shown = [], more = [];
  byGroup.forEach(items=>{
    const of = items[0] && items[0].of || 1;
    if(of <= budget){ items.forEach(p=>shown.push({...p, of})); return; }
    const keep = items.filter(p=>p.col < budget-1);
    const hid  = items.filter(p=>p.col >= budget-1);
    keep.forEach(p=>shown.push({...p, of: budget}));
    if(hid.length){
      more.push({col: budget-1, of: budget, n: hid.length,
                 start: Math.min(...hid.map(p=>p.ev.start)),
                 end: Math.max(...hid.map(p=>p.ev.end))});
    }
  });
  return {shown, more};
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

function renderGrid(host, dates, all, data, onPick, onDayPick, onSlot, onOverflow){
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
    // The empty half-hours, each one its own target. Drawn BEFORE the chips so an event keeps its click,
    // and each carries the minute it represents rather than reading it back out of a mouse coordinate.
    for(let m=lo; m<hi; m+=30){
      const slot = el2("div","agslot");
      slot.style.top = ((m-lo)/60*HOUR_PX)+"px";
      slot.style.height = (HOUR_PX/2 - 1)+"px";
      slot.title = tt("add_at", {at: hhmm(m)}, "Nueva cita a las {at}");
      slot.onclick = ev => { ev.stopPropagation(); onSlot(d, m); };
      col.appendChild(slot);
    }
    if(d===today && data.now){
      const nowM = mins(data.now);
      if(nowM>=lo && nowM<=hi){
        const n = el2("div","agnow"); n.style.top = ((nowM-lo)/60*HOUR_PX)+"px";
        n.title = tt("now", null, "Ahora"); col.appendChild(n);
      }
    }
    const packed = lanes(layoutColumn(eventsOn(all, d)), laneBudget(dates.length));
    packed.shown.forEach(p=>{
      const e = p.ev, of = p.of || 1;
      const h = Math.max(20, (e.end-e.start)/60*HOUR_PX - 2);
      // What the chip can HOLD decides what goes in it. Two lines need ~34px; one needs ~24. And a lane
      // narrower than a word holds initials, not a sentence — the class is what the stylesheet reads.
      const cls = chipClasses(e)
        + (h < 34 ? " tight" : "") + (h < 24 ? " tiny" : "") + (of >= 3 ? " narrow" : "");
      const chip = el2("div", cls);
      chip.style.setProperty("--evc", hueOf(e));
      chip.style.top = ((e.start-lo)/60*HOUR_PX)+"px";
      chip.style.height = h+"px";
      chip.style.left = (p.col*100/of)+"%";
      chip.style.width = `calc(${100/of}% - 3px)`;
      chip.appendChild(el2("div","agevt", e.title));
      const hr = el2("div","agevh", hhmm(e.start));
      hr.appendChild(badges(e)); chip.appendChild(hr);
      chip.title = `${timeLabel(e)} · ${e.title}`;
      chip.onclick = ev => { ev.stopPropagation(); onPick(e); };
      col.appendChild(chip);
    });
    packed.more.forEach(m=>{
      const chip = el2("div","agev more");
      chip.style.top = ((m.start-lo)/60*HOUR_PX)+"px";
      chip.style.height = Math.max(20, (m.end-m.start)/60*HOUR_PX - 2)+"px";
      chip.style.left = (m.col*100/m.of)+"%";
      chip.style.width = `calc(${100/m.of}% - 3px)`;
      chip.appendChild(el2("div","agevt", "+" + m.n));
      chip.title = tt("more_n", {n: m.n}, "{n} citas más — ábrelas en el día");
      chip.onclick = ev => { ev.stopPropagation(); onOverflow(d); };
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
// ── NEW APPOINTMENT, from a click on an empty half-hour (V2-693) ────────────────────────────────────────
// Until today the only way to put something in this calendar was to SAY it. His ask is the plain one every
// calendar answers: «asegúrate de que el widget permite clicar en algún punto para añadir un ítem». It sends
// `add_meeting` — a DECLARED data-op — and nothing else: a button that promises what the API cannot do is
// the failure this widget's own history is made of (V2-540).
function renderAdd(root, ctx, state, redraw){
  const at = state.add || {};
  const veil = el2("div","agveil");
  const close = ()=>{ state.add = null; redraw(); };
  veil.onclick = e => { if(e.target===veil) close(); };
  const p = el2("div","agpanel agaddp");

  const head = el2("div","agphead");
  head.appendChild(el2("div","agpbar"));
  head.appendChild(el2("div","agptitle", tt("new_meeting", null, "Nueva cita")));
  const x = el2("button","agpx","×"); x.title = tt("close", null, "Cerrar"); x.onclick = close;
  head.appendChild(x); p.appendChild(head);

  const when = el2("div","agprow"); when.appendChild(svgEl(ICO_CLOCK));
  when.appendChild(el2("span",null, fmtDate(parseYmd(at.date),
    {weekday:"long",day:"numeric",month:"long"}, at.date)));
  p.appendChild(when);

  const title = el2("input","agfield");
  title.type = "text"; title.placeholder = tt("what_is_it", null, "¿Qué es?");
  title.value = at.title || "";
  p.appendChild(title);

  const row = el2("div","agfrow");
  const start = el2("input","agfield agftime"); start.type = "time"; start.value = hhmm(at.start || 9*60);
  const mins = el2("select","agfield agfdur");
  [[30,"30 min"],[60,"1 h"],[90,"1 h 30"],[120,"2 h"]].forEach(([v,l])=>{
    const o = el2("option",null,l); o.value = String(v); if(v===60) o.selected = true; mins.appendChild(o);
  });
  row.appendChild(start); row.appendChild(mins); p.appendChild(row);

  const meetRow = el2("label","agfcheck");
  const meet = el2("input"); meet.type = "checkbox";
  meetRow.appendChild(meet);
  meetRow.appendChild(el2("span",null, tt("with_meet", null, "Con videollamada de Google Meet")));
  p.appendChild(meetRow);

  const err = el2("div","agwarn"); err.hidden = true; p.appendChild(err);

  const acts = el2("div","agpacts");
  const save = el2("button","done", tt("save", null, "Guardar"));
  save.onclick = ()=>{
    const t = (title.value || "").trim();
    if(!t){ err.textContent = tt("needs_title", null, "Ponle un nombre a la cita."); err.hidden = false;
            title.focus(); return; }
    const m = mins2(start.value);
    if(m == null){ err.textContent = tt("needs_time", null, "Esa hora no la entiendo."); err.hidden = false;
                   return; }
    const dur = Number(mins.value) || 60;
    state.add = null;
    Promise.resolve(ctx.action("add_meeting", {
      title: t, date: at.date, startTime: hhmm(m), endTime: hhmm(Math.min(24*60-1, m + dur)),
      meet: meet.checked ? true : undefined,
    })).then(nd => redraw(nd)).catch(()=>redraw());
  };
  const no = el2("button",null, tt("cancel", null, "Cancelar")); no.onclick = close;
  acts.appendChild(save); acts.appendChild(no);
  p.appendChild(acts);

  veil.appendChild(p); root.appendChild(veil);
  raf(()=>{ try{ title.focus(); }catch(_){} });
}

// "HH:MM" → minutes, or null when the field is empty or unreadable. An unreadable time must not silently
// become midnight: an appointment nobody asked for at 00:00 is worse than a refusal that says so.
function mins2(v){
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(v || "").trim());
  if(!m) return null;
  const h = Number(m[1]), mi = Number(m[2]);
  if(h > 23 || mi > 59) return null;
  return h*60 + mi;
}

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

// ── The PLATFORM ICONS in the subheader (V2-679 follow-up) — the messaging widget's own pattern: every
// provider visible at a glance, the ones we have not built dimmed and inert, the live one a door into its
// screen. Deliberately NOT the cramped 15px strip V2-643 removed: these are 26px targets with a tooltip each,
// sitting beside the Conectores button instead of competing with the range title. ───────────────────────────
function renderProviderIcons(cals, S, redraw){
  const wrap = el2("div","agconnicons");
  (cals||[]).forEach(c=>{
    const live = c.id === "google";            // the only provider with a connector behind it today
    const on = c.status === "connected";
    const btn = el2("button","agconnicon" + (on?" on":"") + (live?"":" off"));
    const spec = CAL_SVG[c.id];
    if(spec){ btn.style.color = spec.color; btn.appendChild(svgEl(spec.path, {fill:true})); }
    else { btn.appendChild(svgEl(ICO_CAL)); }
    btn.title = (c.label || c.id) + " — " + (!live ? tt("cal_soon", null, "aún no disponible")
                                                   : on ? tt("cal_connected", null, "conectado")
                                                        : tt("cal_off", null, "sin conectar"));
    if(!live){ btn.disabled = true; }
    else {
      btn.onclick = ()=>{
        // Connected → the list screen (where the default calendar and «Desconectar» live); not connected →
        // straight into its wizard, the same shortcut messaging's dimmed icons take.
        S.screen = on ? "list" : "wizard";
        if(!on){ S.wizStep = 1; S.connectErr = ""; }
        redraw();
      };
    }
    wrap.appendChild(btn);
  });
  return wrap;
}

// ── CONNECTORS SCREEN (list) — the whole content area, not an overlay ────────────────────────────────────
function renderConnectorScreen(data, ctx, S, redraw){
  const cals = data.calendars || [];
  const wrap = el2("div","agconnscreen agpanel");
  const head = el2("div","agconnhead");
  head.appendChild(el2("div","agptitle", tt("connectors", null, "Conectores")));
  const back = el2("button","agconnback", "← " + tt("back_to_agenda", null, "Agenda"));
  back.onclick = ()=>{ S.screen = null; redraw(); };
  head.appendChild(back);
  wrap.appendChild(head);

  cals.forEach(c=>{
    // V2-690 — a provider is ONE block: its row and whatever acts on it. «Conectar Google Calendar» used to
    // be a sibling of the list, so it rendered in the gap between the Google row and the iCloud row with the
    // same distance to each — reading, at a glance, as iCloud's button. Everything a provider owns now hangs
    // off its own group, and the group is what the spacing separates.
    const grp = el2("div","agcalgrp");
    const row = el2("div","agcalrow");
    const ico = el2("div","agcalico"); const spec = CAL_SVG[c.id];
    if(spec){ ico.style.color = spec.color; ico.appendChild(svgEl(spec.path, {fill:true})); }
    else { ico.appendChild(svgEl(ICO_CAL)); }
    row.appendChild(ico);
    row.appendChild(el2("div","agcalname", c.label || c.id));
    const on = c.status === "connected";
    row.appendChild(el2("div","agcalst" + (on?" on":"") + (c.status==="unconfigured"?" unconf":""),
      on ? tt("cal_connected", null, "conectado")
         : (c.status === "unavailable" ? tt("cal_soon", null, "aún no disponible")
                                       : (c.status === "unconfigured" ? tt("cal_unconf", null, "sin configurar")
                                                                      : tt("cal_off", null, "sin conectar")))));
    grp.appendChild(row);
    wrap.appendChild(grp);
    // Only Google is wired to a real connector today (V2-679); iCloud/CalDAV stay VISIBLE but INERT — no
    // button, no click handler — until a second provider lands in `connectors/calendar/providers.py`.
    if(c.id !== "google") return;
    if(on){
      const cald = el2("div","agcaldef");
      const gcals = data.googleCalendars || [];
      if(gcals.length){
        cald.appendChild(el2("div","agcaldeflabel", tt("cal_default_label", null,
          "Calendario donde crear las citas nuevas:")));
        gcals.forEach(gc=>{
          const line = el2("label","agcaldefrow");
          const radio = document.createElement("input"); radio.type = "radio"; radio.name = "hb-ag-defcal";
          radio.checked = gc.id === data.defaultCalendarId;
          radio.onchange = ()=>{ ctx.action("set_default_calendar", {calendarId: gc.id}); };
          line.appendChild(radio);
          const dot = el2("span","agcaldot"); if(gc.backgroundColor) dot.style.background = gc.backgroundColor;
          line.appendChild(dot);
          line.appendChild(el2("span",null, gc.summary || gc.id));
          cald.appendChild(line);
        });
      }
      grp.appendChild(cald);
      const disc = el2("button","agcalbtn2 hb-btn hb-btn--danger", tt("cal_disconnect", null, "Desconectar Google Calendar"));
      disc.onclick = ()=>{ ctx.action("disconnect", {provider:"google"}); };
      grp.appendChild(disc);
    } else {
      // The operator's rule: this button STARTS THE GUIDE, it does not fire an OAuth handshake that cannot
      // succeed yet — «lo que hace es iniciar un wizard con las instrucciones en la zona central del widget».
      const btn = el2("button","agcalbtn2 hb-btn hb-btn--primary", tt("cal_connect", null, "Conectar Google Calendar"));
      btn.onclick = ()=>{ S.screen = "wizard"; S.wizStep = 1; S.connectErr = ""; redraw(); };
      grp.appendChild(btn);
    }
  });
  wrap.appendChild(el2("div","agnote", tt("cal_footer", null,
    "Conecta Google Calendar y esta agenda pasa a sincronizarse con él: tus citas de ahí se ven aquí y lo que " +
    "dictes por voz aparece allí. Mientras no haya nada conectado, esta agenda es la de Zaelar.")));
  return wrap;
}

// ── GOOGLE CALENDAR WIZARD — one step at a time, in the content area, with a way back at every step ──────
// Steps 1-3 are the work that happens OUTSIDE (a Google Cloud project, an OAuth client, pasting its id into
// ⚙ → Conectores); the last one is the only one that talks to anybody, and it is the real handshake.
function agWizardSteps(){
  return [
    {title: tt("wiz1_title", null, "Crea el proyecto en Google y activa Calendar")},
    {title: tt("wiz2_title", null, "Crea el ID de cliente OAuth"),
     next:  tt("wiz_have_it", null, "Ya lo tengo — continuar")},
    {title: tt("wiz3_title", null, "Pega el ID en Configuración → Conectores")},
  ];
}
function agLink(href, label){
  const a = document.createElement("a"); a.className = "agwlink"; a.href = href;
  a.target = "_blank"; a.rel = "noopener"; a.textContent = label + " \u2197";
  return a;
}
function agStepBody(step){
  const wrap = el2("div");
  if(step === 1){
    wrap.appendChild(el2("div","agwbody", tt("wiz1_body", null,
      "En Google Cloud crea un proyecto (o reutiliza uno que ya tengas) y activa en él la API de Google "
      + "Calendar. Es gratis y solo se hace una vez.")));
    wrap.appendChild(agLink("https://console.cloud.google.com/projectcreate",
      tt("wiz1_link1", null, "Crear un proyecto de Google Cloud")));
    wrap.appendChild(agLink("https://console.cloud.google.com/apis/library/calendar-json.googleapis.com",
      tt("wiz1_link2", null, "Activar la API de Calendar")));
  } else if(step === 2){
    wrap.appendChild(el2("div","agwbody", tt("wiz2_body", null,
      "En «Credenciales» crea un ID de cliente de OAuth de tipo «Aplicación de escritorio»: ese tipo no "
      + "necesita secreto ni dominio. Copia el ID de cliente que te da Google.")));
    wrap.appendChild(agLink("https://console.cloud.google.com/apis/credentials",
      tt("wiz2_link", null, "Abrir Credenciales de Google Cloud")));
    wrap.appendChild(el2("div","agwtip", tt("wiz2_tip", null,
      "El ID de cliente termina en .apps.googleusercontent.com. No es un secreto: lo que protege la conexión "
      + "es el propio permiso que das en la ventana de Google.")));
  } else {
    wrap.appendChild(el2("div","agwbody", tt("wiz3_body", null,
      "Abre Configuración (⚙) → Conectores → Calendario y pega ahí el ID de cliente. Al guardarlo, este "
      + "asistente ya puede pedirle permiso a Google.")));
    wrap.appendChild(el2("div","agwtip", tt("wiz3_tip", null,
      "Si tu cliente OAuth es de tipo «Web» en vez de escritorio, pega también su secreto en esa misma "
      + "tarjeta y añade la URL de retorno que ahí se indica.")));
  }
  return wrap;
}
function renderGoogleWizard(data, ctx, S, redraw){
  const wrap = el2("div","agconnscreen agpanel");
  const crumb = el2("div","agwcrumb");
  const back = el2("button","agconnback", "‹ " + tt("connectors", null, "Conectores"));
  back.onclick = ()=>{ S.screen = "list"; S.connectErr = ""; redraw(); };
  crumb.appendChild(back);
  crumb.appendChild(el2("span","agwsep","/"));
  crumb.appendChild(el2("span","agwcur", "Google Calendar"));
  wrap.appendChild(crumb);

  // HOW MANY STEPS is decided by the ACCOUNT, not by a constant. Until V2-685 this was always a four-step
  // tutorial — create a Google Cloud project, create an OAuth client, paste it into ⚙ — teaching the
  // operator to register an app FOR THE CALENDAR. That app is now the Google ACCOUNT's, and registering it
  // once lights Gmail, Calendar, Meet, Drive, Photos and YouTube together (`registry._google`). So when it
  // is already registered — which is every operator who connected any other Google surface first — those
  // three steps are somebody else's job already done, and showing them reads as the previous generation's
  // flow. They stay for the operator who has NO account yet, because today nothing else teaches it.
  const gcal = (data.calendars || []).find(c => c.id === "google") || {};
  const steps = gcal.status === "unconfigured" ? agWizardSteps() : [];
  const total = steps.length + 1;                        // +1 = the step that actually connects
  const step = Math.min(Math.max(Number(S.wizStep) || 1, 1), total);
  S.wizStep = step;
  const last = step === total;

  const box = el2("div","agwstep");
  const head = el2("div","agwhead");
  head.appendChild(el2("span","agwnum", String(step)));
  head.appendChild(el2("span","agwtitle", last ? tt("wiz4_title", null, "Autoriza tu cuenta de Google")
                                               : steps[step-1].title));
  if(total > 1) head.appendChild(el2("span","agwcount", tt("wiz_step_n", {n:step, total}, "Paso {n} de {total}")));
  box.appendChild(head);
  if(last){
    box.appendChild(el2("div","agwbody", tt("wiz4_body", null,
      "Se abrirá una ventana de Google para que autorices el acceso a tu calendario. Al aceptar, tus citas "
      + "aparecen aquí y lo que dictes por voz se crea allí.")));
    if(S.connectErr) box.appendChild(el2("div","agwerr", S.connectErr));
  } else {
    box.appendChild(agStepBody(step));
  }
  const foot = el2("div","agwfoot");
  const backBtn = el2("button","agcalbtn2 hb-btn hb-btn--secondary", tt("wiz_back", null, "Atrás"));
  backBtn.onclick = ()=>{
    if(step > 1){ S.wizStep = step - 1; S.connectErr = ""; } else { S.screen = "list"; }
    redraw();
  };
  foot.appendChild(backBtn);

  if(!last){
    const nextBtn = el2("button","agcalbtn2 hb-btn hb-btn--primary", steps[step-1].next || tt("wiz_next", null, "Continuar"));
    nextBtn.onclick = ()=>{ S.wizStep = step + 1; redraw(); };
    foot.appendChild(nextBtn);
  } else {

    const go = el2("button","agcalbtn2 hb-btn hb-btn--primary", S.connectBusy ? tt("cal_connecting", null, "Abriendo Google…")
                                                       : tt("cal_connect", null, "Conectar Google Calendar"));
    go.disabled = !!S.connectBusy;
    go.onclick = async ()=>{
      // The popup is opened SYNCHRONOUSLY, inside the click — a window.open() that runs after an `await` is
      // outside the user gesture and every mainstream browser blocks it in SILENCE, which is exactly why the
      // previous version of this button «ni siquiera funciona»: the URL arrived, and nothing ever showed.
      let popup = null;
      try{ popup = window.open("", "gcal_connect", "width=520,height=760"); }catch(_){ popup = null; }
      S.connectBusy = true; S.connectErr = ""; redraw();
      // V2-687 — the ORIGIN travels. Two doors open this same consent and they were sending DIFFERENT
      // redirect_uris: the settings panel derives it from the request headers (V2-603), and this one sent
      // nothing, so it always fell back to the loopback default. Which URI Google saw depended on which
      // button was pressed, so registering one of them left the other failing with redirect_uri_mismatch —
      // measured on the operator's first real connect, 2026-09-14. An origin is not a credential (V2-520),
      // and the engine validates it before it ever reaches a URL.
      let res;
      // `force` is a HUMAN pressing this button, and it is the only thing that sends it: re-linking a
      // different Google account has to stay possible, while a voice turn or a Brain Worker asking to
      // "connect" a calendar that is already connected gets told so instead of getting a wizard (V2-689).
      try{ res = await ctx.action("connect", {provider:"google", origin: location.origin, force:true}); }
      catch(_){ res = null; }
      S.connectBusy = false;
      const url = res && res.url;
      if(url && popup){ try{ popup.location = url; }catch(_){ try{ window.open(url, "gcal_connect"); }catch(_2){} } }
      else if(url){ try{ window.open(url, "gcal_connect", "width=520,height=760"); }catch(_){} }
      else {
        if(popup){ try{ popup.close(); }catch(_){} }
        // A refusal SAYS what went wrong — the connector's own sentence when it has one («sin app OAuth
        // registrada…»), which is the step above this one still pending.
        S.connectErr = (res && res.error) || tt("cal_connect_failed", null,
          "No pude abrir la ventana de Google. Revisa que el ID de cliente esté guardado en Configuración → "
          + "Conectores → Calendario.");
      }
      redraw();
    };
    foot.appendChild(go);
  }
  // V2-690 — the actions belong to the STEP, so they hang off the step box and not off the screen: they used
  // to float on the card's ground with nothing tying them to the panel they act on.
  box.appendChild(foot);
  wrap.appendChild(box);
  return wrap;
}

// ── the render ────────────────────────────────────────────────────────────────────────────────────────
export function render(el, data, ctx){
  injectStyles();
  if(el._timer){ clearInterval(el._timer); el._timer=null; }
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  _LANG = (ctx && ctx.lang) || "es";

  const today = data.date || ymd(new Date());
  // `screen` is the CONNECTORS area (null = the calendar itself, "list" = every provider, "wizard" = the
  // guided Google connect). It is a SCREEN and not an overlay: the operator asked for the whole content area,
  // «igual que en mensajería», where the same three-state machine has lived since V2-570.
  if(!el._ag) el._ag = {view:"week", anchor:today, sel:null, screen:null, wizStep:1, connectBusy:false,
                        connectErr:"", confirmDel:false, viewN:null, connN:null, add:null};
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
    // A pushed view is a NAVIGATION order: it has to leave the connectors screen, or the day it asked for
    // renders underneath a setup screen and the order looks ignored (V2-626's lesson, one widget over).
    S.screen = null;
  }

  // A CONNECT PUSHED FROM VOICE (V2-686). «Conecta mi Google Calendar» cannot finish here — the consent
  // popup only survives inside the operator's own click — so the voice does the half it can: it leaves the
  // card ON the step that holds the button. Same token rule as the view above: it lands when the counter
  // MOVES, never on a plain repaint.
  // ⚠️ …and NEVER over a calendar that is already linked (V2-689). `S.connN` starts at null on a fresh
  // element, so within the push's 3-minute life ANY repaint that rebuilt the card re-applied it — which is
  // how the button came back the instant Google finished authorizing, and how a Brain Worker calling this
  // action threw a setup wizard over the week he was reading. The backend no longer pushes when connected;
  // this is the second half, because a token already in the store must not fire on the next mount either.
  const gcalOn = (data.calendars||[]).some(c => c.id === "google" && c.status === "connected");
  // ⚠️ A WIZARD OVER A CONNECTED ACCOUNT IS A LIE (V2-693). The consent happens in Google's own popup, which
  // closes itself — so the card stayed on «Authorize your Google account», with a Connect button, for an
  // account that was already linked. The operator reported exactly that: «la ventana se ha abierto, se ha
  // cerrado el pop-up, y en la agenda sigo viendo autoriza tu Google Account… si vuelvo atrás sí que se ve
  // perfectamente conectado». Nothing was broken underneath; the screen simply never heard the news.
  // It goes to the connectors LIST and not to the calendar on purpose: that screen is where the state he
  // just changed is actually shown («connected», and the calendar to write into), so the step he completed
  // gets an answer instead of just vanishing.
  if(S.screen === "wizard" && gcalOn){ S.screen = "list"; S.connectBusy = false; S.connectErr = ""; S.wizStep = 1; }
  const pushedConn = gcalOn ? null : data.connect;
  if(pushedConn && pushedConn.n !== S.connN){
    S.connN = pushedConn.n;
    S.screen = "wizard";
    S.wizStep = 99;            // the LAST step, whatever the count is — the wizard clamps it, and the count
    S.connectErr = "";         // is no longer a constant (it depends on whether the Google account exists)
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
    // While the connectors screen owns the content, NO view is the one on screen — so none of them is lit and
    // none of them is clickable (the operator: «se desactiva el foco o el botón activo de día, semana, mes y
    // lista»). The chosen view survives underneath and comes back when the screen closes.
    const t = el2("button","agtab" + (!S.screen && S.view===id ? " on" : ""), label);
    t.dataset.view = id;
    t.disabled = !!S.screen;
    t.onclick = ()=>{ S.view = id; S.sel = null; render(el, data, ctx); };
    views.appendChild(t);
  });
  const right = el2("div","agviewsright");
  right.appendChild(renderProviderIcons(data.calendars || [], S, ()=>render(el, data, ctx)));
  const calBtn = el2("button","agcalbtn" + (S.screen?" on":""));
  calBtn.appendChild(svgEl(ICO_PLUG));
  calBtn.appendChild(el2("span",null, tt("connectors", null, "Conectores")));
  calBtn.title = tt("calendars_hint", null, "Qué calendarios están conectados");
  calBtn.onclick = ()=>{
    S.screen = S.screen ? null : "list";
    if(S.screen === "list"){ S.sel = null; S.connectErr = ""; }
    render(el, data, ctx);
  };
  right.appendChild(calBtn);
  views.appendChild(right);
  el.appendChild(views);

  // ── body ───────────────────────────────────────────────────────────────────────────────────────────
  const body = el2("div","agbody");
  const pick = e => { S.sel = e.key; S.confirmDel = false; render(el, data, ctx); };
  const pickDay = ds => { S.view = "day"; S.anchor = ds; S.sel = null; render(el, data, ctx); };
  const pickSlot = (ds, m) => { S.add = {date: ds, start: m, title: ""}; S.sel = null; render(el, data, ctx); };
  // The way OUT of a crowded slot, and it always goes somewhere wider: the week sends you to the day, the
  // day to the list, where a row is a row and nothing is hidden behind a count.
  const overflow = ds => {
    if(S.view === "day"){ S.view = "list"; } else { S.view = "day"; S.anchor = ds; }
    S.sel = null; render(el, data, ctx);
  };

  let active = null;
  if(S.screen === "list"){
    body.appendChild(renderConnectorScreen(data, ctx, S, ()=>render(el, data, ctx)));
  } else if(S.screen === "wizard"){
    body.appendChild(renderGoogleWizard(data, ctx, S, ()=>render(el, data, ctx)));
  } else if(S.view === "week"){
    renderGrid(body, dates, all, data, pick, pickDay, pickSlot, overflow);
  } else if(S.view === "month"){
    renderMonth(body, S.anchor, all, data, pick, pickDay);
  } else if(S.view === "list"){
    renderList(body, today, all, data, pick);
  } else {
    // DAY = the hour grid plus the coach rail this widget has always had (Now + countdown + task actions).
    const wrap = el2("div","agday-wrap");
    const gridBox = el2("div","agday-grid");
    renderGrid(gridBox, dates, all, data, pick, pickDay, pickSlot, overflow);
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
  if(S.add) renderAdd(el, ctx, S, redraw);
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
  if(!S.screen && (S.view === "day" || S.view === "week")){
    const scroller = el.querySelector(".agday-grid") || el.querySelector(".agbody");
    if(scroller){
      const [lo] = hourRange(dates.flatMap(d=>eventsOn(all, d)));
      const target = Math.max(0, (mins(isFinite(mins(data.now))&&S.anchor===today ? data.now : "08:00") - lo - 60)/60*HOUR_PX);
      raf(()=>{ try{ scroller.scrollTop = target; }catch(_){} });
    }
  }
}
