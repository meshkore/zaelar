// Contacts widget — the card's scoped stylesheet, injected once by `injectStyles` in widget.js
// (refactor2710-12 T-03).
export const CSS = `
  .hb-contactos{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:100%;box-sizing:border-box}
  .hb-contactos button{font-family:inherit}
  .hb-contactos .ctsearch{flex:1 1 200px;min-width:140px;max-width:380px;display:flex;align-items:center;gap:6px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:5px 12px;background:var(--hb-bg,#fff)}
  .hb-contactos .ctsearch:focus-within{border-color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctsearch span{font-size:12px;color:var(--hb-muted-2,#7d8a9c);flex:0 0 auto}
  .hb-contactos .ctsearch input{border:none;outline:none;background:none;color:var(--hb-ink,#0d1622);font-size:13px;width:100%;padding:0}
  .hb-contactos .ctcols{display:grid;grid-template-columns:188px 1fr;gap:14px;align-items:start}
  @media(max-width:600px){.hb-contactos .ctcols{grid-template-columns:1fr}
    /* One column: an open contact IS the screen — the groups rail above it pushed the card half a screen down
       (V2-813, iPhone 14). «← Back» brings the rail back with the list. */
    .hb-contactos .ctcols.detail > :first-child{display:none}}

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
  /* A phone: the search gets the whole row and the sources go under it — five 44px icons and a search box do not
     fit 366px, and the plug was cut off the edge (V2-813). */
  @media (max-width:520px){.hb-contactos .ctbar{flex-wrap:wrap;row-gap:var(--sp-2,8px)}
    .hb-contactos .ctsearch{flex:1 1 100%;max-width:none}}
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
  `;
