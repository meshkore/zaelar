// Agenda widget — stylesheet, first half: card frame, toolbar, view band, grid, chips, composer, month, list,
// coach rail, detail panel. `CSS` is both halves in their original order (refactor2710-12 T-03).
import { CSS_PANELS } from "./style_panels.js";

const CSS_CALENDAR = `
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
  /* V2-728 — the SYSTEM's own work. Read at a glance as «something will happen here», never as «you have
     an appointment here»: a dotted edge is the calendar convention for a mark that is not a commitment. */
  .hb-agenda .agev.system{background:color-mix(in srgb, var(--evc,#9A6BFF) 10%, transparent);
    border:1px dotted var(--evc,#9A6BFF);border-left-width:3px;border-left-style:solid}
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
  .hb-agenda .agpstate.declined{background:color-mix(in srgb,var(--hb-risk,#e5484d) 15%,transparent);
    color:var(--hb-risk,#e5484d)}
`;

export const CSS = CSS_CALENDAR + CSS_PANELS;
