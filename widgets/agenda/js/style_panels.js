// Agenda widget — stylesheet, second half: detail/proposals panels, the subheader and the TAREAS panes.
// Joined after style.js's half into the one sheet injectStyles() adds (refactor2710-12 T-03).
export const CSS_PANELS = `\
  /* V2-697 — the join link is the one thing on this card somebody needs at a specific minute, so it reads as
     an action and not as another grey detail line. */
  .hb-agenda .agpmeet{color:var(--hb-accent,#3D6FE0);font-weight:600;text-decoration:none}  .hb-agenda .agpmeet:hover{text-decoration:underline}
  .hb-agenda .agpglist{display:flex;flex-direction:column;gap:3px;min-width:0}
  .hb-agenda .agpg{display:flex;align-items:baseline;gap:6px;min-width:0}
  .hb-agenda .agpgm{flex:0 0 auto;width:13px;text-align:center;font-style:normal;font-weight:700;font-size:12px}
  .hb-agenda .agpgm.accepted{color:var(--hb-ok,#5FD3A2)}  .hb-agenda .agpgm.declined{color:var(--hb-risk,#e5484d)}
  .hb-agenda .agpgm.tentative{color:var(--hb-warn,#EFC75E)}  .hb-agenda .agpgm.unknown{color:var(--hb-muted-2,#8d9db4)}
  .hb-agenda .agpgn{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
  .hb-agenda .agpgo{flex:0 0 auto;font-style:normal;font-size:11px;color:var(--hb-muted-2,#8d9db4)}
  /* V2-697 — the proposals band. Deliberately NOT styled like a calendar entry: none of this is on the
     calendar yet, and a row that looks like an appointment is already making the claim. */
  .hb-agenda .agprops{display:flex;flex-direction:column;gap:8px;padding:8px 12px 0}
  .hb-agenda .agprop{border:1px dashed var(--hb-accent,#3D6FE0);border-radius:11px;padding:9px 11px;
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 7%,transparent);
    display:flex;flex-direction:column;gap:4px}
  .hb-agenda .agprophead{font-size:13px;color:var(--hb-ink,#0d1622)}
  .hb-agenda .agpropwhen{font-size:13px;font-weight:600;color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agpropwhy{font-size:12px;color:var(--hb-muted,#3a4757)}  .hb-agenda .agpropacts{display:flex;flex-wrap:wrap;gap:6px;margin-top:3px}
  .hb-agenda .agpropacts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    border-radius:9px;padding:6px 11px;font-size:13px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-agenda .agpropacts button.ok{border-color:color-mix(in srgb,var(--hb-ok,#5FD3A2) 55%,transparent);
    color:var(--hb-ok,#5FD3A2)}
  .hb-agenda .agpropacts button:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agpacts{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
  .hb-agenda .agpacts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    border-radius:9px;padding:7px 11px;font-size:13px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-agenda .agpacts button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-agenda .agpacts button.risk:hover{border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}
  .hb-agenda .agpacts button.ok{border-color:color-mix(in srgb,var(--hb-ok,#5FD3A2) 55%,transparent);
    color:var(--hb-ok,#5FD3A2)}
  .hb-agenda .agpacts button.ok:hover{border-color:var(--hb-ok,#5FD3A2)}
  .hb-agenda .agnote{font-size:13px;color:var(--hb-muted-2,#7d8a9c);line-height:1.4}
  .hb-agenda .agcaldefsel{height:var(--hb-ctl-h-sm,32px);max-width:180px;font-size:13px;border-radius:var(--hb-r-s,8px);
    border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);padding:0 6px}

  /* ── V2-744/V2-746 · THE SUBHEADER ────────────────────────────────────────────────────────────────
     One card, two things: the calendar and the operator's own numbered task lists.

     V2-746 — the operator, 2026-09-21: «esa barra segunda que pone agenda y tareas, quizás debería ser una
     línea de subheader más consistente. Por si hay que crear algo más ahí». It was a pill floating on the
     card's own background, which reads as a control someone dropped on top of the content rather than as a
     part of the window. It is now a full-width band with a rule under it — the second line of chrome under
     the title bar — with a right-hand slot that is EMPTY on the calendar and carries the counts on tasks.
     The band is what makes room for whatever goes there next; the slot exists so the next thing does not
     need a new band.

     The active tab stays a FILLED accent chip (accent ground, "--canvas" ink) and not an underline with
     accent text: V2-691 measured that pairing at 6.1:1 against the dark canvas, and the underline variant
     would put small accent text on a lighter step, which is where the tertiary ink already loses a point.
     A design change is not allowed to spend the contrast that audit bought. */
  /* 2026-10-28 — the band IS the toolbar now (the operator: all the chrome in two lines — the window's bar
     and this one). One strip on surface-2 holding the section switch, ‹ Hoy › · range · views (.agbar) and
     the slot; it wraps only when a phone leaves no other way. The switch sits one rung DOWN on the strip. */
  .hb-agenda .agsub{display:flex;align-items:center;gap:var(--sp-2,8px);flex:0 0 auto;min-width:0;flex-wrap:wrap;
    margin:0 0 var(--sp-3,12px);padding:var(--sp-1,4px) var(--sp-2,8px);background:var(--hb-bg-soft,#272D35);
    border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));border-radius:var(--hb-r-m,10px);
    border-bottom-color:var(--hb-line,rgba(255,255,255,.14))}
  .hb-agenda .agsec{display:flex;gap:2px;flex:0 0 auto;padding:2px;border-radius:999px;
    background:var(--hb-bg,#1F242B);border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09))}
  .hb-agenda .agsecb{border:0;background:none;color:var(--hb-muted,#5b6b82);border-radius:999px;display:inline-flex;
    align-items:center;gap:6px;padding:6px var(--sp-3,12px);font:600 13px/1.2 var(--sans,system-ui);cursor:pointer;white-space:nowrap}
  .hb-agenda .agsecb svg{display:none;width:15px;height:15px}
  .hb-agenda .agsecb:hover{color:var(--hb-ink,#0d1622)}  .hb-agenda .agsecb.on{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#fff)}
  /* The slot. "margin-left:auto" and not a spacer element, so an empty slot costs no node at all. */
  .hb-agenda .agsub-meta{margin-left:auto;flex:0 1 auto;min-width:0;display:flex;align-items:center;
    gap:var(--sp-2,8px);font:600 12px/1 var(--sans,system-ui);color:var(--hb-muted,#BAC2CE);
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-agenda .agsub-meta b{font-weight:700;color:var(--hb-ink,#F2F4F7)}

  /* ── TAREAS: two delimited PANES, and inside each one a table ─────────────────────────────────────
     V2-746, the operator's brief, verbatim: «que tuviera un poco más aspecto tipo Excel… que se delimiten
     mejor las listas de tareas de la izquierda, a la derecha también todo el formato de la lista, los
     botones… delimitando bien lo que es la columna de la izquierda, cada uno de los cuadrados».

     What was there: free-floating rounded cards on the card's own background, separated by gaps. Nothing
     said where the left column ended and the right one began, and «Nueva lista» sat UNDER the list of
     lists — his objection, and the correct one: «cuando tengamos 100 listas no se va a ver».

     Three moves, and the spreadsheet feel is all three together rather than any one of them:
       · each half is a PANE — its own surface off the elevation ladder, a hairline border, a header bar;
       · rows are CONTIGUOUS and separated by hairlines instead of by air, with a quiet zebra, so the eye
         reads a column of cells and not a stack of chips;
       · the numeric columns are MONOSPACE and right-aligned, so «1/3» under «12/40» lines up on the slash.
     No new colour enters: every surface below is a step of the ladder V2-689 defined and every ink is a
     token. «Manteniendo colores, tipos de fuente y estilos básicos» was half the brief. */
  /* The tasks body has to BE a flex column, or the panes below size to their content and the left one
     stops being a column at all — it was 258px tall inside a 620px card, which is exactly the «no se
     delimita» he is looking at. The calendar half keeps the scrolling body it needs. */
  .hb-agenda .agbody.tasks{display:flex;flex-direction:column;overflow:hidden}
  .hb-agenda .agt{display:flex;gap:var(--sp-3,12px);flex:1 1 auto;min-height:0;min-width:0}

  /* Shared pane chrome — the two halves are the same object at two widths. */
  .hb-agenda .agt-side,.hb-agenda .agt-main{display:flex;flex-direction:column;min-height:0;
    border:1px solid var(--hb-line,rgba(255,255,255,.14));border-radius:var(--hb-r-m,10px);
    overflow:hidden}
  .hb-agenda .agt-side{flex:0 0 232px;background:var(--hb-sidebar,#1A1E24)}
  .hb-agenda .agt-main{flex:1 1 auto;min-width:0;background:var(--hb-bg,#1F242B)}

  /* A pane's header bar: one step lighter than the pane, ruled off from the rows under it. The left one is
     STICKY by construction (it is a flex sibling of the scroller, not a row inside it), which is the whole
     answer to «con 100 listas no se va a ver»: the ＋ cannot scroll away because it never scrolls. */
  .hb-agenda .agt-sidehead,.hb-agenda .agt-head{display:flex;align-items:center;gap:var(--sp-2,8px);
    flex:0 0 auto;min-width:0;padding:0 var(--sp-2,8px) 0 var(--sp-3,12px);min-height:40px;
    background:var(--hb-bg-soft,#272D35);
    border-bottom:1px solid var(--hb-line,rgba(255,255,255,.14))}
  .hb-agenda .agt-sidetitle{flex:1 1 auto;min-width:0;font:700 12px/1 var(--sans,system-ui);
    letter-spacing:.08em;text-transform:uppercase;color:var(--hb-muted,#BAC2CE);
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  /* The ＋ as an icon button in the header, and the inline «name it» form taking the header's whole width
     when it opens. ".agt-newl" keeps its name because it keeps its job — it is the new-list affordance,
     wherever it sits. */
  .hb-agenda .agt-newl{display:flex;align-items:center;gap:var(--sp-1,4px);flex:0 0 auto;min-width:0}
  .hb-agenda .agt-newl.open{flex:1 1 auto}
  .hb-agenda .agt-plus{width:26px;height:26px;flex:0 0 auto;border-radius:var(--hb-r-s,8px);
    border:1px solid var(--hb-line,rgba(255,255,255,.14));background:var(--hb-bg,#1F242B);
    color:var(--hb-ink,#F2F4F7);cursor:pointer;display:inline-flex;align-items:center;
    justify-content:center;font:600 15px/1 var(--sans,system-ui);padding:0}
  .hb-agenda .agt-plus:hover{border-color:var(--hb-accent,#AE90FF);color:var(--hb-accent,#AE90FF)}

  /* The rows. "gap:0" and a hairline per row is the whole difference between a list of chips and a table. */
  .hb-agenda .agt-rows{flex:1 1 auto;min-height:0;overflow:auto}
  .hb-agenda .agt-list{display:grid;grid-template-columns:26px 1fr 52px;align-items:center;
    column-gap:var(--sp-2,8px);row-gap:5px;width:100%;text-align:left;border:0;
    border-left:3px solid transparent;
    border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));background:none;
    padding:9px var(--sp-3,12px) 9px 9px;cursor:pointer;font-family:var(--sans,system-ui);
    color:var(--hb-ink,#F2F4F7)}
  .hb-agenda .agt-rows .agt-list:nth-child(even){background:color-mix(in srgb,var(--hb-ink,#F2F4F7) 3%,transparent)}
  .hb-agenda .agt-list:hover{background:var(--hb-hover,#3C434F)}
  /* Selection: tinted ground + an accent EDGE + the label in primary ink at 700 — V2-691's shape, because
     the accent used as small text over its own tint was the tightest thing on that screen. */
  .hb-agenda .agt-list.on,.hb-agenda .agt-rows .agt-list.on:nth-child(even){
    background:color-mix(in srgb,var(--hb-accent,#AE90FF) 16%,transparent);
    border-left-color:var(--hb-accent,#AE90FF)}
  .hb-agenda .agt-list.on .agt-lname{font-weight:700;color:var(--hb-ink,#F2F4F7)}
  /* THE NUMBER IS THE HANDLE. He says «ábreme la lista número 3», so the numeral is not decoration: it is
     the thing he reads before he speaks. A square monospace cell rather than a circle — it is a column of a
     table now, and a two-digit list has to fit in it without the badge changing shape.

     ⚠️ Its ink is PRIMARY, not the accent, and that is measured rather than chosen. Accent glyphs on an
     accent tint measured 4.79:1 on a plain row and 3.67:1 on the selected one — under AA — because the
     selected row is itself an accent tint and the badge was then accent on accent. It is the exact pairing
     V2-691 called the tightest thing on that screen, and the shape it prescribed is the one used here:
     tinted ground, primary ink at 700, and the accent carried by the ROW (its left edge and its tint)
     rather than by the small text sitting on it. Selected, the badge flips to the filled-accent pairing the
     same pass proved — accent ground, "--canvas" ink — which reads at 9:1 and makes the handle he is about
     to speak the brightest thing in the column. */
  .hb-agenda .agt-no{width:26px;height:22px;flex:0 0 auto;border-radius:var(--hb-r-s,8px);
    display:inline-flex;align-items:center;justify-content:center;
    font:700 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
    color:var(--hb-ink,#F2F4F7);background:color-mix(in srgb,var(--hb-ink,#F2F4F7) 12%,transparent)}
  .hb-agenda .agt-list.on .agt-no,.hb-agenda .agt-head .agt-no{
    color:var(--canvas,#16191E);background:var(--hb-accent,#AE90FF)}
  .hb-agenda .agt-lname{min-width:0;font-size:13px;font-weight:600;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  /* Monospace and right-aligned so «1/3» sits under «12/40» on the slash. The brighter ink is deliberate:
     this is a column of the table now, not a caption, and V2-691 measured the tertiary ink losing a point
     on every step above surface-1 — which is exactly where the zebra puts half these cells. */
  .hb-agenda .agt-count{text-align:right;font:600 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
    color:var(--hb-muted,#BAC2CE);font-variant-numeric:tabular-nums;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
  /* The meter. Two pixels and not three: five of these stacked in a column were the loudest thing on the
     screen and they were competing with the selection for the same purple. A FINISHED list turns green —
     the one place this pass adds colour, and it adds it because it says something: «Regalos 2/2» used to
     be a full purple bar, which is what a selected row also looks like out of the corner of an eye. */
  .hb-agenda .agt-prog{grid-column:2 / -1;height:2px;border-radius:999px;
    background:color-mix(in srgb,var(--hb-ink,#F2F4F7) 12%,transparent);overflow:hidden}
  .hb-agenda .agt-prog span{display:block;height:100%;border-radius:999px;
    background:color-mix(in srgb,var(--hb-accent,#AE90FF) 82%,transparent)}
  .hb-agenda .agt-prog.full span{background:var(--hb-ok,#6FE0B0)}

  /* The right pane's header carries the identity of the list and everything you can do TO the list. */
  .hb-agenda .agt-title{flex:1 1 auto;font:700 14px/1.2 var(--sans,system-ui);min-width:0;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap}
  /* The list's IDENTIFIER, shown rather than hidden: it is what he will hand to another agent over the
     MeshKore cluster, and an id you cannot see is an id you cannot share. */
  .hb-agenda .agt-id{font:500 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
    color:var(--hb-muted,#BAC2CE);background:var(--hb-bg,#1F242B);
    border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));border-radius:6px;padding:4px 7px;
    flex:0 0 auto;cursor:pointer}
  /* The actions as a SEGMENTED group: one outline around the set, hairlines between the members. Three
     separate outlined buttons read as three unrelated decisions; they are one toolbar. */
  .hb-agenda .agt-acts{margin-left:auto;display:flex;flex:0 0 auto;
    border:1px solid var(--hb-line,rgba(255,255,255,.14));border-radius:var(--hb-r-s,8px);overflow:hidden}
  .hb-agenda .agt-acts .agt-b{border:0;border-left:1px solid var(--hb-line,rgba(255,255,255,.14));
    border-radius:0;background:var(--hb-bg,#1F242B)}
  .hb-agenda .agt-acts .agt-b:first-child{border-left:0}
  .hb-agenda .agt-b{border:1px solid var(--hb-line,rgba(255,255,255,.14));background:var(--hb-bg,#1F242B);
    color:var(--hb-muted,#BAC2CE);border-radius:var(--hb-r-s,8px);height:var(--hb-ctl-h-sm,32px);
    padding:0 var(--sp-3,12px);font:600 12px/1 var(--sans,system-ui);cursor:pointer}
  .hb-agenda .agt-b:hover{background:var(--hb-hover,#3C434F);color:var(--hb-ink,#F2F4F7)}
  .hb-agenda .agt-b.danger:hover{background:var(--hb-risk-soft,rgba(255,138,146,.16));
    color:var(--hb-risk,#FF8A92)}
  .hb-agenda .agt-b.on{background:var(--hb-accent,#AE90FF);color:var(--canvas,#16191E);border-color:transparent}
  .hb-agenda .agt-b.on:hover{background:var(--hb-accent,#AE90FF);color:var(--canvas,#16191E)}

  /* The table's own header row — the label line a spreadsheet has and a list of chips does not. */
  .hb-agenda .agt-cols{display:grid;grid-template-columns:20px 26px 1fr 108px 56px;align-items:center;
    gap:var(--sp-2,8px);flex:0 0 auto;padding:6px var(--sp-3,12px);
    background:color-mix(in srgb,var(--hb-ink,#F2F4F7) 4%,transparent);
    border-bottom:1px solid var(--hb-line,rgba(255,255,255,.14));
    font:700 12px/1 var(--sans,system-ui);letter-spacing:.09em;text-transform:uppercase;
    color:var(--hb-muted,#BAC2CE)}
  .hb-agenda .agt-cols i{font-style:normal;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-agenda .agt-cols i.n{text-align:right;padding-right:2px}

  .hb-agenda .agt-items{flex:1 1 auto;min-height:0;overflow:auto}
  .hb-agenda .agt-item{display:grid;grid-template-columns:20px 26px 1fr 108px 56px;align-items:center;
    gap:var(--sp-2,8px);border:0;
    border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));
    padding:8px var(--sp-3,12px)}
  .hb-agenda .agt-items .agt-item:nth-child(even){background:color-mix(in srgb,var(--hb-ink,#F2F4F7) 3%,transparent)}
  .hb-agenda .agt-item:hover{background:var(--hb-hover,#3C434F)}
  .hb-agenda .agt-check{width:18px;height:18px;flex:0 0 auto;border-radius:5px;cursor:pointer;
    border:1.5px solid var(--hb-line-strong,rgba(255,255,255,.24));background:none;display:inline-flex;
    align-items:center;justify-content:center;color:var(--canvas,#16191E);padding:0}
  .hb-agenda .agt-check.on{background:var(--hb-accent,#AE90FF);border-color:var(--hb-accent,#AE90FF)}
  .hb-agenda .agt-check svg{width:11px;height:11px;display:block}
  .hb-agenda .agt-ino{text-align:right;padding-right:2px;font-variant-numeric:tabular-nums;
    font:600 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--hb-muted,#BAC2CE)}
  .hb-agenda .agt-text{min-width:0;font-size:13.5px;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap}
  .hb-agenda .agt-item.done .agt-text{text-decoration:line-through;color:var(--hb-muted,#BAC2CE)}
  .hb-agenda .agt-when{justify-self:stretch;text-align:right;font:500 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
    color:var(--hb-muted,#BAC2CE);background:color-mix(in srgb,var(--hb-ink,#F2F4F7) 7%,transparent);
    border-radius:5px;padding:4px 7px;white-space:nowrap}
  /* The row's own controls live in a fixed last column, so they line up down the table instead of drifting
     with the length of each title — and they are always there rather than appearing on hover, because a
     control that only exists while the pointer is over it cannot be found by somebody looking for it. */
  .hb-agenda .agt-ops{grid-column:5;justify-self:end;display:flex;gap:2px}
  .hb-agenda .agt-ib{border:0;background:none;color:var(--hb-muted,#BAC2CE);cursor:pointer;
    padding:4px;border-radius:6px;flex:0 0 auto;display:inline-flex;font-size:12px;font-weight:600}
  .hb-agenda .agt-ib:hover{color:var(--hb-ink,#F2F4F7);background:var(--hb-bg-soft,#272D35)}
  .hb-agenda .agt-ib.danger:hover{color:var(--hb-risk,#FF8A92);background:var(--hb-risk-soft,rgba(255,138,146,.16))}
  /* A phone (V2-813): every control there is 44px (the shell's touch floor), so the columns that were 20px for the
     tick and 56px for two icons overflowed — the tick spilled into the number and the ✎/× stacked. The columns
     make room for the floor, and the tick keeps its small square drawn INSIDE its 44px hit area. */
  @media (max-width:520px){
    .hb-agenda .agt-cols,.hb-agenda .agt-item{grid-template-columns:44px 18px minmax(0,1fr) auto 92px;gap:6px;
      padding-left:6px;padding-right:6px}
    .hb-agenda .agt-check{border:0;padding:13px;background-clip:content-box;border-radius:6px;
      outline:1.5px solid var(--hb-line-strong,rgba(255,255,255,.24));outline-offset:-13px}
    .hb-agenda .agt-check.on{outline-color:var(--hb-accent,#AE90FF)}
    .hb-agenda .agt-ops{flex-wrap:nowrap;align-items:center}
    .hb-agenda .agt-ib{align-items:center;justify-content:center}
  }
  /* An item being renamed spans the columns its text and its controls occupied — the row must not reflow. */
  .hb-agenda .agt-item > .agt-in{grid-column:3 / -1}
  /* The pane's footer — the «new row» line of the spreadsheet, ruled off from the rows above it. */
  .hb-agenda .agt-add{display:flex;gap:var(--sp-2,8px);flex:0 0 auto;align-items:center;
    padding:var(--sp-2,8px) var(--sp-3,12px);background:var(--hb-bg-soft,#272D35);
    border-top:1px solid var(--hb-line,rgba(255,255,255,.14))}
  .hb-agenda .agt-in{flex:1 1 auto;min-width:0;border:1px solid var(--hb-line,rgba(255,255,255,.14));
    background:var(--hb-bg,#1F242B);color:var(--hb-ink,#F2F4F7);border-radius:var(--hb-r-s,8px);
    height:var(--hb-ctl-h-sm,32px);padding:0 10px;font:400 13px/1 var(--sans,system-ui)}
  .hb-agenda .agt-in:focus{outline:none;border-color:var(--hb-accent,#AE90FF)}
  .hb-agenda .agt-sidehead .agt-in{height:26px;font-size:12px}
  .hb-agenda .agt-sidehead .agt-b{height:26px;padding:0 var(--sp-2,8px)}
  .hb-agenda .agt-empty{font-size:13px;color:var(--hb-muted,#BAC2CE);
    padding:var(--sp-5,24px) var(--sp-3,12px);text-align:center}
  .hb-agenda .agt-ask{display:flex;align-items:center;gap:var(--sp-2,8px);flex:0 0 auto;font-size:13px;
    color:var(--hb-ink,#F2F4F7);background:var(--hb-risk-soft,rgba(255,138,146,.16));
    border-bottom:1px solid var(--hb-line,rgba(255,255,255,.14));padding:9px var(--sp-3,12px)}
  .hb-agenda .agt-ask span{flex:1 1 auto;min-width:0}
  /* Narrow card: the panes stack, the left one stops being a column and becomes a short scrolling strip.
     It keeps its border and its header — the delimitation is the point and it does not get cheaper here. */
  @media (max-width: 640px){
    .hb-agenda .agt{flex-direction:column}
    .hb-agenda .agt-side{flex:0 0 auto;max-height:168px}
    .hb-agenda .agt-main{min-height:240px}
  }
  /* The band's three widths — see style.js «THE VIEWS». Last on purpose: a tier has to beat the base rules. */
  @container (max-width:1040px){ .hb-agenda .agcaldefsel{max-width:58px} }
  @container (max-width:820px){ .hb-agenda .agtab,.hb-agenda .agcaldefsel{display:none} .hb-agenda .agviewsel{display:block} }
  @container (max-width:560px){ .hb-agenda .agsecb span,.hb-agenda .agconnicons,.hb-agenda .agmev .agmh{display:none}
    .hb-agenda .agsecb svg{display:block} .hb-agenda .agsecb{padding:7px 9px}
    .hb-agenda .agsub,.hb-agenda .agbar{gap:var(--sp-1,4px)} .hb-agenda .agnav button{min-width:28px;padding:0 6px} }
  `;
