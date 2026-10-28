// results widget — the sheet's stylesheet, injected once by widget.js::injectStyles (moved verbatim, refactor2710-12).
export const CSS = `
  /* ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
     SYSTEM, not loose numbers. The previous version accumulated thirteen font sizes (10.5, 11, 11.5, 12, 12.5, 13,
     13.5, 14, 15, 15.5, 18, 21...) and margins of 3, 5, 6, 7, 8, 9, 10, 11px chosen one by one: that does not read
     like a surface, it reads like patches. Here there is ONE four-step type scale and ONE 4px spacing grid in local
     variables, so everything follows the same rhythm and changing density is one line. The rest of CSS no longer
     carries raw magnitudes.
     COLORS all come from the theme --hb-* contract (never hex): the card repaints itself on theme changes.
     CAREFUL when editing: this is a template literal — no backticks inside.
     ───────────────────────────────────────────────────────────────────────────────────────────────────────────── */
  .hb-results{
    /* V2-797 — the local names stay, their VALUES come from the design system (palette.css): the sheet's
       rhythm is the desktop's rhythm, and the ⚙ size knob scales it with everything else. The fallbacks are
       the old local values, for a sheet mounted outside the shell. */
    --s1:var(--sp-1,5px); --s2:var(--sp-2,9px); --s3:var(--sp-3,14px); --s4:var(--sp-4,18px); --s5:var(--sp-5,26px);
    --f-micro:var(--fs-micro,11px);                           /* uppercase labels, with tracking */
    --f-sm:var(--fs-caption,13px);                            /* metadata, states */
    --f-body:var(--fs-ui,14.5px);                             /* body for everything */
    --f-md:var(--fs-body,16px);                               /* record title */
    --f-lg:19px; --f-xl:23px;                                 /* record and summary figures */
    --r-sm:var(--hb-r-s,7px); --r-md:var(--hb-r-m,10px); --r-lg:var(--hb-r-l,13px); --r-pill:99px;   /* radii */
    --line:1px solid var(--hb-line,#e3e8f0);
    font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    color:var(--hb-ink,#0d1622);font-size:var(--f-body);line-height:1.62;
    width:100%;min-width:0;display:flex;flex-direction:column;height:100%;min-height:0;box-sizing:border-box}
  /* Every COMPARED number uses tabular figures. On a surface whose job is stacking prices and scores, variable-width
     digits force rereading to know which is greater. */
  .hb-results .hr-price,.hb-results .hr-score,.hb-results .hr-pp,.hb-results .hr-n,
  .hb-results .hr-stat b,.hb-results .hr-sn,.hb-results .hr-tbl td,.hb-results .hr-dprice{
    font-variant-numeric:tabular-nums}
  .hb-results .hr-bt,.hb-results .hr-cgt,.hb-results .hr-pk,.hb-results .hr-stat span{
    font-size:var(--f-micro);font-weight:700;letter-spacing:.06em;text-transform:uppercase;
    color:var(--hb-muted-2,#9aa7b8)}

  /* ── THE HEADER STAYS PUT BECAUSE IT IS NOT IN THE SCROLLER (V2-821) ────────────────────────────────────────
     A ten-result sheet is scrolled, and the tabs have to stay where they are while it is (look at the last card and
     jump to Sources). Until V2-821 that was done with position:sticky against the CARD's scroller, and the card's
     scroller is padded: sticky holds at the CONTENT edge, so the padding band above the header was a window the
     list scrolled through («canal, email, no, whatsapp» peeking over the tabs), and the tabs' bottom margin was a
     second, transparent band under them. The operator: the content went behind the header and showed through it.
     So the root is a flex column that fills the card — the header is a flex:none band and the PANEL is the only
     scroller, starting exactly at the tab line. Nothing can pass behind a header that is not over the scroller.
     The panel declares itself with data-hb-scroller, which is how the hosts' ctx.top()/ctx.scroll() find it. */
  .hb-results .hr-top{flex:none;background:var(--hb-bg,#fff)}
  .hb-results .hr-panel{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain;
    padding:var(--s4) var(--s2) var(--sp-4,16px);margin:0 calc(-1 * var(--s2)) calc(-1 * var(--sp-4,16px))}
  /* (The negative margins hand the panel part of the host's gutter on the sides and all of it at the bottom, so a
     card's hover shadow and the last row reach the card edge as they did when the card itself scrolled. The bottom
     is written with the host's OWN inset token and fallback (.hb-scroll pads with var(--sp-4,16px)): one pixel more
     and the card's scroller would scroll again, behind the panel.) */
  .hb-results .hr-hd{font-size:var(--f-md);font-weight:650;letter-spacing:-.01em;margin:0;word-break:break-word}
  .hb-results .hr-sub{font-size:var(--f-sm);color:var(--hb-muted-2,#9aa7b8);margin:var(--s1) 0 0}
  /* With the TASK already in the card header, the subtitle is the sheet's first line: no top margin. */
  .hb-results .hr-top>.hr-sub:first-child{margin-top:0}
  .hb-results .hr-sub.clamp2{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  /* A standalone subtitle inside a panel needs air BELOW: without it, the context line ("recreational boating ·
     minimum width 40") stuck to the next label and they read as a single thing. */
  .hb-results .hr-panel>.hr-sub{margin-bottom:var(--s4)}
  .hb-results .hr-panel>.hr-why{margin-bottom:var(--s4)}

  /* ── SESSION IDENTIFIERS (bottom of the SUMMARY tab since V2-538) ───────────────────────────────────────────────────────────────────────────
     User and session for this installation, with a button that copies BOTH together: the operator passes them to a
     code agent to audit the session (whether it went well/badly, where it failed). Displayed SHORTENED (full id in
     the hover 'title') and copied in full. From the theme --hb-* contract. */
  .hb-results .hr-ident{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s2);margin-top:var(--s3);
    font-size:var(--f-sm)}
  .hb-results .hr-idbit{display:inline-flex;align-items:center;gap:6px;
    background:var(--hb-bubble,#f1f4f9);border-radius:var(--r-pill);padding:4px var(--s3);cursor:default}
  .hb-results .hr-idbit b{font-size:var(--f-micro);font-weight:700;letter-spacing:.06em;text-transform:uppercase;
    color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-idbit code{font-family:var(--mono,ui-monospace,SFMono-Regular,Menlo,Consolas,monospace);
    color:var(--hb-ink,#0d1622);font-variant-numeric:tabular-nums}
  .hb-results .hr-idcopy{display:inline-flex;align-items:center;gap:5px;font:700 var(--f-sm)/1 inherit;
    color:var(--hb-accent,#3D6FE0);background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 12%,transparent);
    border:1px solid color-mix(in srgb,var(--hb-accent,#3D6FE0) 32%,transparent);
    border-radius:var(--r-sm);padding:5px 11px;cursor:pointer;transition:.14s}
  .hb-results .hr-idcopy:hover{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 18%,transparent)}
  .hb-results .hr-idcopy[disabled]{opacity:.5;cursor:default}
  .hb-results .hr-idcopy.ok{color:var(--hb-ok,#1f9d55);
    border-color:color-mix(in srgb,var(--hb-ok,#1f9d55) 42%,transparent);
    background:color-mix(in srgb,var(--hb-ok,#1f9d55) 14%,transparent)}

  /* ── TABS ── the active underline continues the bottom line, instead of becoming a separate box. */
  .hb-results .hr-tabs{display:flex;gap:2px;border-bottom:var(--line);margin:var(--s3) 0 0;
    overflow-x:auto;scrollbar-width:none}
  .hb-results .hr-tabs::-webkit-scrollbar{display:none}
  .hb-results .hr-tab{flex:none;display:inline-flex;align-items:center;gap:var(--s1);border:none;background:none;
    cursor:pointer;font:600 var(--f-body)/1 inherit;color:var(--hb-muted,#5f6b7c);
    padding:var(--s2) var(--s3) 9px;border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;
    transition:color .14s}
  .hb-results .hr-tab:hover{color:var(--hb-ink,#0d1622)}
  .hb-results .hr-tab.on{color:var(--hb-accent,#3D6FE0);border-bottom-color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-tab .hr-n{font-size:var(--f-micro);font-weight:700;padding:1.5px 6px;border-radius:var(--r-pill);
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5f6b7c);line-height:1.4}
  .hb-results .hr-tab.on .hr-n{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 16%,transparent);
    color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-tab .hr-n.bad{background:color-mix(in srgb,var(--hb-risk,#e5484d) 15%,transparent);
    color:var(--hb-risk,#e5484d)}
  /* the TAB loader: slightly smaller than the panel's, because it accompanies a label rather than heading it */
  .hb-results .hr-tab .hr-tspin{width:.8em;height:.8em;border-width:1.5px}

  /* ── THE CARD SYSTEM (V2-797) ── ONE template, laid out by the space it REALLY has ─────────────────────────
     «monta un sistema para que cualquier resultado se monte bien, adecuado al UI, a las ventanas, al espacio y
     formato disponibles. Nada de parches.» Before this, the sheet budgeted CHARACTERS per field (title 34,
     subtitle 70): the server cut every real listing name to fit a width it never measured, and the worker was
     told its payload «broke the card». A card does not know its width in characters; it knows it in pixels, and
     only once it is on screen. So:
       · every card is a CONTAINER ('hrcard') and its inside is laid out by its own width (@container), never by
         the viewport and never by a number the filler sent;
       · text is CLAMPED to its lines with an ellipsis, the whole text is one click away («Ver todo») and in the
         hover title — a long name is the layout's job, not the data's;
       · the grid reflows to as many columns as the sheet's width holds ('gridStyle', auto-fill);
       · photos sit in plates of FIXED aspect, contained, never cropped; a missing or dead photo keeps its plate
         (a monogram), so one result without a picture never drags the row out of formation;
       · the item template is driven by DECLARED fields: title, subtitle, meta chips (rating, distance, hours…),
         price, badge, image, and the action that opens the record. Nothing per domain.
     Colours, radii, spacing and type come from the design system tokens (palette.css, V2-689 ladder): a card is
     one rung above the widget it sits on ('--hb-bg-soft' on '--hb-bg'), never the same rung (V2-691).
     CAREFUL when editing: this is a template literal — no backticks inside. */
  .hb-results .hr-grid{display:grid;gap:var(--s3);min-width:0;align-items:stretch}
  .hb-results .hr-grid + .hr-grid{margin-top:var(--s3)}
  .hb-results .hr-card{position:relative;display:flex;flex-direction:column;min-width:0;
    text-decoration:none;color:inherit;container:hrcard / inline-size;
    background:var(--hb-bg-soft,#fbfdff);border:1px solid var(--hb-line-subtle,var(--hb-line,#e3e8f0));
    border-radius:var(--hb-r-l,12px);padding:var(--s3);
    transition:border-color var(--hb-t,.16s),box-shadow var(--hb-t,.16s),transform var(--hb-t,.16s)}
  /* The featured card is marked with border and ground, never with size (V2-703: one track for every card). */
  .hb-results .hr-card.primary{border-color:color-mix(in srgb,var(--hb-accent2,#16B8A6) 48%,var(--hb-line,#e3e8f0))}
  .hb-results a.hr-card:hover,.hb-results .hr-card.choosable:hover{
    border-color:var(--hb-line-strong,var(--hb-accent,#3D6FE0));
    box-shadow:var(--hb-shadow-1,0 8px 30px rgba(13,22,34,.12));transform:translateY(-1px)}
  .hb-results .hr-card .hr-in{display:flex;flex-direction:column;gap:var(--s3);flex:1 1 auto;min-width:0}
  .hb-results .hr-card .hr-body{display:flex;flex-direction:column;gap:var(--s2);min-width:0;flex:1 1 auto}

  /* ── THE PLATE ── fixed aspect, image CONTAINED (V2-702: a box whose aspect came from the card width cropped
     81% of a pot away). Its ground is one step off the card in either theme: a neutral tray, never a white
     rectangle glaring on a dark card. */
  .hb-results .hr-shot{position:relative;display:grid;place-items:center;overflow:hidden;width:100%;
    aspect-ratio:4/3;border-radius:var(--hb-r-m,10px);
    background:color-mix(in srgb,var(--hb-ink,#0d1622) 6%,var(--hb-bg-soft,#f4f6fa))}
  /* Absolutely filling the plate with 'contain': a percentage max-height inside a grid plate never resolves (the
     track is content-sized), and a tall photo then overflowed the plate and was clipped. */
  .hb-results .hr-shot img{position:absolute;inset:0;display:block;width:100%;height:100%;object-fit:contain}
  /* No photo, or a dead one: the plate stays and says WHAT it is, by its initial. */
  .hb-results .hr-shot .hr-mono{font-size:clamp(18px,9cqi,40px);font-weight:700;letter-spacing:-.02em;
    color:color-mix(in srgb,var(--hb-accent,#3D6FE0) 70%,var(--hb-muted,#5f6b7c));opacity:.75;user-select:none}
  .hb-results .hr-sec .hr-shot{margin-bottom:var(--s3)}

  /* ── THE FOUR LIST LAYOUTS ── variants of the SAME template, chosen by 'layoutFor()' from the content shape
     (or named by the worker, V2-703): split = photo left, data right (articles) · gallery = photo on top
     (places, rooms, the image IS the answer) · rows = no photo (documents, links) · compare = composite plans. */
  .hb-results .hr-card.split .hr-in{display:grid;grid-template-columns:minmax(88px,34%) minmax(0,1fr);
    align-items:stretch}
  .hb-results .hr-card.split .hr-shot{aspect-ratio:1/1;align-self:start}
  /* The photo goes back on top, shorter, still a plate, when there is no room for two columns: a ONE-column
     sheet (the grid's own width, below ~430px) or a card whose content box is under 340px in a wider grid. Both are widths
     of the sheet as it is drawn, never of the viewport. */
  .hb-results .hr-grid{container:hrgrid / inline-size}
  @container hrgrid (max-width: 430px){
    .hb-results .hr-card.split .hr-in{display:flex;flex-direction:column}
    .hb-results .hr-card.split .hr-shot{aspect-ratio:16/10}
  }
  @container hrcard (max-width: 339px){
    .hb-results .hr-card.split .hr-in{display:flex;flex-direction:column}
    .hb-results .hr-card.split .hr-shot{aspect-ratio:16/10}
  }
  .hb-results .hr-card.gallery .hr-shot{aspect-ratio:4/3}

  /* ── TEXT ── clamped to its lines, whole on expand. The clamp lives on a plain child ('.hr-cl'): a clamp
     declared on a flex item is dropped (the 2026-09 «four-line title» trap). */
  .hb-results .hr-card .hr-txt{display:flex;flex-direction:column;gap:var(--s1);min-width:0}
  .hb-results .hr-card .hr-t{font-size:var(--f-md);font-weight:650;letter-spacing:-.01em;
    line-height:var(--hb-lh-tight,1.35);overflow-wrap:anywhere;min-width:0;flex:none}
  .hb-results .hr-card .hr-s{font-size:var(--f-sm);line-height:var(--hb-lh-tight,1.35);
    color:var(--hb-muted,#5f6b7c);overflow-wrap:anywhere}
  .hb-results .hr-card .hr-cl{display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden;-webkit-line-clamp:2}
  @container hrcard (min-width: 560px){
    .hb-results .hr-card .hr-s .hr-cl{-webkit-line-clamp:3}
  }
  .hb-results .hr-card.hr-x .hr-cl{display:block;-webkit-line-clamp:unset;overflow:visible}
  .hb-results .hr-card .hr-xbtn{display:none;align-self:flex-start;border:0;background:none;padding:0;
    font:600 var(--f-sm)/1.3 inherit;color:var(--hb-accent,#3D6FE0);cursor:pointer}
  .hb-results .hr-card .hr-xbtn:hover{text-decoration:underline}
  .hb-results .hr-card .hr-txt.can-x .hr-xbtn,.hb-results .hr-card.hr-x .hr-xbtn{display:inline}

  /* ── META CHIPS ── the 1-4 data that decide at a glance, each one line, ellipsized; never a paragraph. */
  .hb-results .hr-card .hr-metarow{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s1);min-width:0;
    margin:0}
  .hb-results .hr-card .hr-chip{display:inline-block;max-width:100%;min-width:0;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap;font-size:var(--f-sm);line-height:1.35;
    padding:2px var(--s2);border-radius:var(--r-pill);background:var(--hb-bubble,#f1f4f9);
    color:var(--hb-ink,#0d1622)}
  .hb-results .hr-card .hr-chip small{font-size:inherit;color:var(--hb-muted-2,#9aa7b8);margin-right:var(--s1)}
  .hb-results .hr-card .hr-metarow .hr-badge,.hb-results .hr-card .hr-metarow .hr-score{flex:none}

  /* ── FOOT ── price and the way into the record, pushed to the bottom so every row lines its buttons up. */
  .hb-results .hr-card .hr-foot{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s2);
    margin-top:auto;padding-top:var(--s1)}
  .hb-results .hr-card .hr-foot .hr-price{font-size:var(--f-md);font-weight:700;
    margin-right:auto;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}
  .hb-results .hr-card .hr-foot .hr-more,.hb-results .hr-card .hr-foot .hr-open{margin-top:0}

  /* ── THE LINK TO THE ORIGINAL PAGE ── on EVERY card that has one ────────────────────────────────────────────
     «asegúrate de que cuando un widget de resultados busca cosas siempre muestre los links a la página web
     original donde se puede ver la ficha súper ampliada». It used to be shown only when the card had NOTHING
     else to offer: 'asLink = url && !hasDetail', so the richest results —the ones with a rating, facts and
     photos, i.e. the ones worth opening— were exactly the ones whose link never reached the screen. Measured on
     his own pot sheet: the item carried 'https://www.amazon.es/dp/B075WGKKGB' and the rendered list contained
     ZERO anchors. It names the SITE, not the raw url: «Ver en amazon.es» says where the click lands. */
  /* 'hr-open', not 'hr-src': the SOURCES tab already owns '.hr-src' (a full-width grid row) and got there
     first, so a same-specificity rule declared later in this same sheet quietly won and stretched the link
     across the whole card. One stylesheet, one namespace. */
  .hb-results .hr-foot{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s2);margin-top:var(--s3)}
  .hb-results .hr-foot .hr-more{margin-top:0}
  /* It wears the SAME shape as 'Ver detalle' (declared once, down in the '.hr-more' rule, which names both):
     they are two controls in one row and the eye should read them as siblings. Only the deltas live here. */
  .hb-results .hr-open{text-decoration:none;max-width:100%;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap}
  .hb-results .hr-open.wide{font-size:var(--f-body);padding:var(--s2) var(--s4);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 12%,transparent);
    border-color:color-mix(in srgb,var(--hb-accent,#3D6FE0) 40%,transparent)}
  /* A view that could not be PERSISTED still painted. Saying so is the honest half: the screen is right, the
     brain's copy of it may not be. */
  .hb-results .hr-warn{font-size:var(--f-sm);color:var(--hb-warn-ink,#9a5b1b);margin-top:var(--s2)}

  .hb-results .hr-head{display:flex;align-items:baseline;justify-content:space-between;gap:var(--s1) var(--s2);
    flex-wrap:wrap}
  .hb-results .hr-t{font-size:var(--f-md);font-weight:650;line-height:1.3;letter-spacing:-.01em;
    word-break:break-word;flex:1 1 8em;min-width:0}
  /* The featured card does NOT carry its own size. It used to (15.5px, from when body was 14), and when the scale was
     raised it ended BELOW the normal title —16px—: the recommended card had smaller type than its siblings. A number
     outside the scale does not know the scale changed; it inherits and already stands out by background, border, and
     badge. */
  .hb-results .hr-price{flex:none;font-size:var(--f-md);font-weight:700;color:var(--hb-ink,#0d1622);
    white-space:nowrap;letter-spacing:-.01em}
  /* The subtitle does NOT shout (not turquoise or bold: in one card only one fact wins, and that is the price), but it
     DOES need to read: light gray on white between blue accents was exactly the weak contrast that was hard to read
     (2026-08-12). Raise it to a near-ink tone: context, but crisp. */
  .hb-results .hr-s{font-size:var(--f-sm);color:color-mix(in srgb,var(--hb-ink,#0d1622) 74%,var(--hb-muted,#5f6b7c))}
  /* Subtitle and badge on the SAME line, baseline-aligned: this is the result metadata row. */
  .hb-results .hr-metarow{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s1) var(--s2);
    margin-top:var(--s2)}
  /* Body reads in INK, not gray: it is result text, not a footnote. */
  .hb-results .hr-ln{font-size:var(--f-body);color:var(--hb-ink,#0d1622);margin-top:var(--s1);
    overflow-wrap:break-word}
  .hb-results .hr-ln.strong{color:var(--hb-ink,#0d1622);font-weight:600}
  .hb-results .hr-ln.warn{color:var(--hb-warn-ink,#9a5b1b)}
  .hb-results .hr-badge{display:inline-block;font-size:var(--f-micro);font-weight:700;letter-spacing:.04em;
    text-transform:uppercase;color:var(--hb-accent,#3D6FE0);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 10%,transparent);
    border-radius:var(--r-sm);padding:2.5px 7px}
  .hb-results .hr-empty{color:var(--hb-muted,#5f6b7c);font-size:var(--f-body);padding:var(--s5) 0;
    max-width:52ch;line-height:1.6}
  .hb-results .hr-card.chosen{border-color:var(--hb-accent2,#16B8A6);
    box-shadow:0 0 0 1px var(--hb-accent2,#16B8A6) inset;cursor:default;transform:none}
  .hb-results .hr-chosen-tag{display:inline-block;font-size:var(--f-sm);font-weight:700;
    color:var(--hb-accent2,#16B8A6);margin-top:var(--s2)}

  /* ── PIECES of a composite proposal ── one labeled row each, to compare proposal by proposal. */
  .hb-results .hr-parts{margin-top:var(--s3);padding-top:var(--s3);border-top:var(--line);display:grid;gap:var(--s2)}
  /* wrap + min-width: in a narrow card the price (nowrap, pushed to the right) strangled the title until it split
     letter by letter ("Valenci / a → / Palma"). With wrap, the price moves down as a whole line. */
  .hb-results .hr-part{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--s1) var(--s2);
    font-size:var(--f-body);line-height:1.4}
  .hb-results .hr-pk{flex:none;background:var(--hb-bubble,#f1f4f9);border-radius:var(--r-sm);padding:2px 6px;
    color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-pt{flex:1 1 7em;min-width:7em;color:var(--hb-ink,#0d1622);overflow-wrap:break-word}
  .hb-results .hr-pp{flex:0 0 auto;margin-left:auto;font-weight:600;color:var(--hb-ink,#0d1622);white-space:nowrap}
  .hb-results .hr-more,.hb-results .hr-open{margin-top:var(--s3);display:inline-flex;align-items:center;gap:5px;
    font:600 var(--f-sm)/1 inherit;
    color:var(--hb-accent,#3D6FE0);background:none;border:var(--line);border-radius:var(--r-sm);
    padding:6px 10px;cursor:pointer;transition:.14s}
  .hb-results .hr-more:hover,.hb-results .hr-open:hover{border-color:var(--hb-accent,#3D6FE0);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 8%,transparent)}
  .hb-results .hr-more-err{color:var(--hb-danger,#d6455d);border-color:var(--hb-danger,#d6455d)}

  /* ── RATING ── score next to the title; the reason in the record. Without the reason, it cannot be discussed. */
  .hb-results .hr-score{flex:none;display:inline-flex;align-items:baseline;gap:1px;font-weight:700;
    font-size:var(--f-sm);color:var(--hb-accent,#3D6FE0);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 10%,transparent);
    border-radius:var(--r-pill);padding:2.5px var(--s2)}
  .hb-results .hr-score small{font-weight:600;font-size:var(--f-micro);opacity:.7}
  .hb-results .hr-bar{height:4px;border-radius:var(--r-pill);background:var(--hb-bubble,#f1f4f9);
    margin:var(--s2) 0 var(--s1);overflow:hidden}
  .hb-results .hr-bar i{display:block;height:100%;border-radius:var(--r-pill);
    background:linear-gradient(90deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6))}
  /* The WHY is body text and reads in ink: light gray between blue pills was the blue+gray+white combo that was hard
     to read (2026-08-12). A little air above separates it from the bar. */
  .hb-results .hr-why{font-size:var(--f-body);color:var(--hb-ink,#0d1622);margin-top:var(--s1)}

  /* ── BLOCKS for the custom record ── */
  .hb-results .hr-blocks{display:grid;gap:var(--s3);margin-top:var(--s3)}
  .hb-results .hr-bt{margin-bottom:var(--s1)}
  .hb-results .hr-chips{display:flex;flex-wrap:wrap;gap:5px}
  .hb-results .hr-chip{font-size:var(--f-sm);padding:2.5px var(--s2);border-radius:var(--r-pill);
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5f6b7c)}
  .hb-results .hr-strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(84px,1fr));gap:5px}
  .hb-results .hr-strip img{width:100%;height:62px;object-fit:cover;border-radius:var(--r-sm);
    background:var(--hb-bubble,#f1f4f9)}
  /* The table lives in its OWN scroll container: making it display:block to overflow removed its table behavior (the
     columns stopped aligning across rows, which is the whole point of a table). */
  .hb-results .hr-tblwrap{overflow-x:auto;scrollbar-width:thin}
  .hb-results .hr-tbl{border-collapse:collapse;font-size:var(--f-body);min-width:100%}
  .hb-results .hr-tbl th,.hb-results .hr-tbl td{text-align:left;padding:5px var(--s3) 5px 0;
    border-bottom:var(--line);white-space:nowrap}
  .hb-results .hr-tbl tr:last-child td{border-bottom:none}
  .hb-results .hr-tbl th{font-size:var(--f-micro);font-weight:700;letter-spacing:.06em;text-transform:uppercase;
    color:var(--hb-muted-2,#9aa7b8)}
  .hb-results .hr-tbl td:last-child,.hb-results .hr-tbl th:last-child{padding-right:0;text-align:right}
  .hb-results .hr-sub-sec{border-left:2px solid var(--hb-line,#e3e8f0);padding-left:var(--s3);display:grid;
    gap:var(--s2)}

  /* ── DATA SHEET (shared by card, record, and blocks) ──
     It sits in a tempered PANEL with its own color, not as loose text on the background: it separates hard data from
     the rest of the card and gives the requested color "play" (2026-08-12), without shouting. LABEL in accent (not
     light gray): this way the label→value pair reads as accent→ink, with contrast, instead of muddled
     gray+blue+white. VALUE always in ink. */
  .hb-results .hr-facts{display:grid;grid-template-columns:auto 1fr;gap:var(--s1) var(--s3);
    margin:var(--s3) 0;font-size:var(--f-body);min-width:0;
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 5%,var(--hb-bg-soft,#fbfdff));
    border:1px solid color-mix(in srgb,var(--hb-accent,#3D6FE0) 12%,transparent);
    border-radius:var(--r-md);padding:var(--s3) var(--s4)}
  .hb-results .hr-fl{color:var(--hb-accent,#3D6FE0);font-weight:600}
  .hb-results .hr-fv{color:var(--hb-ink,#0d1622);word-break:break-word}
  /* In a 'facts' block (renderBlock), the block already wraps the panel: there the sheet uses no double box. */
  .hb-results .hr-blocks .hr-facts{background:none;border:none;padding:0}

  /* ── RECORD (page 2) ── */
  .hb-results .hr-back{display:inline-flex;align-items:center;gap:5px;font:600 var(--f-sm)/1 inherit;
    color:var(--hb-muted,#5f6b7c);background:none;border:none;padding:0 0 var(--s3);cursor:pointer}
  .hb-results .hr-back:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-dt{font-size:var(--f-lg);font-weight:700;line-height:1.25;letter-spacing:-.015em;
    word-break:break-word}
  .hb-results .hr-dprice{font-size:var(--f-md);font-weight:700;color:var(--hb-ink,#0d1622);margin-top:2px}
  .hb-results .hr-gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:var(--s1);
    margin:var(--s3) 0}
  /* The record's gallery had the SAME band defect as the list (100px of 'cover'), and here it is worse: this is
     the page the operator opens BECAUSE he wants to look at the thing. Aspect plate + contained image. */
  .hb-results .hr-gal .hr-shot{width:100%;aspect-ratio:1/1}
  .hb-results .hr-sec{border:var(--line);border-radius:var(--r-lg);padding:var(--s3) var(--s4);
    margin-top:var(--s3);background:var(--hb-bg,#fff)}
  .hb-results .hr-sec .hr-pk{margin-bottom:var(--s1);display:inline-block}
  .hb-results .hr-sect{font-size:var(--f-md);font-weight:650;margin-top:2px;word-break:break-word}
  .hb-results .hr-link{display:inline-block;margin-top:var(--s2);font-size:var(--f-sm);font-weight:600;
    color:var(--hb-accent,#3D6FE0);text-decoration:none;word-break:break-all}
  .hb-results .hr-link:hover{text-decoration:underline}

  /* ── SUMMARY ── */
  .hb-results .hr-state{display:inline-flex;align-items:center;gap:var(--s2);font-size:var(--f-body);
    font-weight:600;margin-bottom:var(--s3)}
  .hb-results .hr-dot{width:7px;height:7px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:none}
  .hb-results .hr-dot.ok{background:var(--hb-ok,#1f9d55)}
  .hb-results .hr-dot.warn{background:var(--hb-warn,#c98a00)}
  .hb-results .hr-dot.bad{background:var(--hb-risk,#e5484d)}
  .hb-results .hr-dot.idle{background:var(--hb-accent,#3D6FE0);animation:hrpulse 1.8s ease-in-out infinite}
  @keyframes hrpulse{0%,100%{opacity:1}50%{opacity:.3}}
  /* ── THE LOADER (V2-227 C) ── animates via CSS, NEVER via a JS timer: an interval freezes with the tab in the
     background and survives a render that disconnects it, and both things leave a loader that is in the DOM
     and lies. The hr-spin class genuinely spins while it exists. */
  /* Sizes in em rather than px: they scale with the row's typography, so the loader does not become too small if the
     scale changes — which is exactly what the raw-magnitude ratchet monitors. */
  .hb-results .hr-spin{width:1em;height:1em;flex:none;border-radius:50%;
    border:2px solid var(--hb-neutral,#c2ccda);border-top-color:var(--hb-accent,#3D6FE0);
    animation:hrspin .8s linear infinite}
  @keyframes hrspin{to{transform:rotate(360deg)}}
  .hb-results .hr-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:var(--s2);
    margin-bottom:var(--s4)}
  .hb-results .hr-stat{border:var(--line);border-radius:var(--r-md);padding:var(--s2) var(--s3) 9px;
    background:var(--hb-bg,#fff)}
  .hb-results .hr-stat b{display:block;font-size:var(--f-xl);line-height:1.1;font-weight:700;letter-spacing:-.02em;
    color:var(--hb-ink,#0d1622)}
  .hb-results .hr-stat span{display:block;margin-top:var(--s1);line-height:1.35;letter-spacing:.04em}
  .hb-results .hr-stat.dim b{color:var(--hb-muted-2,#9aa7b8)}
  .hb-results .hr-stat.cut{background:color-mix(in srgb,var(--hb-line,#e3e8f0) 22%,transparent)}
  .hb-results .hr-stat.cut b{color:var(--hb-muted,#6b7a90);font-weight:600}
  .hb-results .hr-stat.warn{border-color:color-mix(in srgb,var(--hb-warn,#c98a00) 34%,var(--hb-line,#e3e8f0))}
  .hb-results .hr-stat.warn b{color:var(--hb-warn-ink,#9a5b1b)}
  /* Logbook: a timeline with the CURRENT milestone marked — reading "where it is" should not require counting. */
  .hb-results .hr-steps{list-style:none;margin:var(--s2) 0 0;padding:0;display:grid}
  .hb-results .hr-steps li{position:relative;padding:0 0 var(--s3) var(--s4);color:var(--hb-muted,#5f6b7c)}
  .hb-results .hr-steps li::before{content:"";position:absolute;left:2px;top:6px;width:6px;height:6px;
    border-radius:50%;background:var(--hb-neutral,#c2ccda)}
  .hb-results .hr-steps li::after{content:"";position:absolute;left:4.5px;top:var(--s3);bottom:0;width:1px;
    background:var(--hb-line,#e3e8f0)}
  .hb-results .hr-steps li:last-child{padding-bottom:0;color:var(--hb-ink,#0d1622);font-weight:600}
  .hb-results .hr-steps li:last-child::after{display:none}
  .hb-results .hr-steps li:last-child::before{background:var(--hb-accent,#3D6FE0);
    box-shadow:0 0 0 3px color-mix(in srgb,var(--hb-accent,#3D6FE0) 18%,transparent)}
  /* V2-728 — the rejected pile. Deliberately DIM and dense: it is an audit trail, not a second results list,
     and it is long (the cap is 120). The reason is the load-bearing half, so it gets its own line rather
     than a parenthesis after the name, which is unreadable once a name wraps. */
  .hb-results .hr-rejected{list-style:none;margin:var(--s2) 0 0;padding:0;display:grid;gap:var(--s2)}
  .hb-results .hr-rejected li{display:flex;flex-direction:column;gap:1px;padding-left:var(--s3);
    border-left:2px solid var(--hb-line,#e3e8f0)}
  .hb-results .hr-rej-t{color:var(--hb-muted,#5f6b7c);font-weight:600;text-decoration:none}
  .hb-results a.hr-rej-t:hover{text-decoration:underline}
  .hb-results .hr-rej-w{color:var(--hb-muted-2,#8b98ac);font-size:var(--f-sm,12px)}

  /* ── THE BROWSER NEEDS HIM (V2-571 · V2-822) ────────────────────────────────────────────────────────────
     Not progress — a REQUEST: a wall, a login, a question the page put to him. Only then does the errand's page
     show on its sheet, above whatever tab he is on, because he has to act on it. */
  .hb-results .hr-proc{margin-bottom:var(--s3)}
  .hb-results .hr-navview{position:relative;border:var(--line);border-radius:var(--r-md);overflow:hidden;
    background:var(--hb-bg-soft,#fbfdff);aspect-ratio:1280/800}
  .hb-results .hr-navimg{display:block;width:100%;height:100%;object-fit:cover;object-position:top}
  .hb-results .hr-navph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    color:var(--hb-muted-2,#9aa7b8);font-size:var(--f-sm)}
  .hb-results .hr-navurl{font-size:var(--f-sm);color:var(--hb-muted-2,#9aa7b8);margin-top:var(--s1);
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-results .hr-wall{margin-top:var(--s2);padding:var(--s2) var(--s3);border-radius:var(--r-md);
    font-size:var(--f-sm);color:var(--hb-warn-ink,#9a5b1b);
    background:color-mix(in srgb,var(--hb-warn,#c98a00) 12%,transparent);
    border:1px solid color-mix(in srgb,var(--hb-warn,#c98a00) 35%,transparent)}
  .hb-results .hr-login{margin-top:var(--s2);padding:var(--s3);border-radius:var(--r-md);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 8%,transparent);
    border:1px solid color-mix(in srgb,var(--hb-accent,#3D6FE0) 30%,transparent)}
  .hb-results .hr-login-t{font-size:var(--f-sm);margin-bottom:var(--s2)}
  .hb-results .hr-login-btn{border:0;background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);border-radius:var(--r-sm);
    padding:var(--s2) var(--s3);font:600 var(--f-sm)/1 inherit;cursor:pointer;width:100%}
  .hb-results .hr-login-btn:hover{filter:brightness(1.06)}
  .hb-results .hr-login-btn[disabled]{opacity:.6;cursor:default}
  .hb-results .hr-navq{margin-top:var(--s2);padding:var(--s2) var(--s3);border-radius:var(--r-md);
    background:color-mix(in srgb,var(--hb-warn,#c98a00) 10%,transparent);
    border:1px solid color-mix(in srgb,var(--hb-warn,#c98a00) 32%,transparent);font-size:var(--f-sm)}
  .hb-results .hr-navq small{display:block;color:var(--hb-muted,#5f6b7c);margin-top:2px}

  /* ── SOURCES ── the colored dot gives the verdict before reading; the count is aligned on the right. */
  .hb-results .hr-srcs{display:grid;gap:var(--s2)}
  .hb-results .hr-src{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;
    gap:var(--s2) var(--s3);padding:var(--s3) var(--s4);border:var(--line);border-radius:var(--r-md);
    background:var(--hb-bg,#fff)}
  .hb-results .hr-src .hr-dot{margin-top:6px}
  .hb-results .hr-src.bad{border-color:color-mix(in srgb,var(--hb-risk,#e5484d) 30%,var(--hb-line,#e3e8f0))}
  .hb-results .hr-src.warn{border-color:color-mix(in srgb,var(--hb-warn,#c98a00) 34%,var(--hb-line,#e3e8f0))}
  .hb-results .hr-sname{font-size:var(--f-body);font-weight:650;word-break:break-word}
  .hb-results .hr-sname a{color:inherit;text-decoration:none}
  .hb-results .hr-sname a:hover{color:var(--hb-accent,#3D6FE0);text-decoration:underline}
  .hb-results .hr-sst{font-size:var(--f-sm);font-weight:600;color:var(--hb-muted,#5f6b7c);margin-top:1px}
  .hb-results .hr-sst.warn{color:var(--hb-warn-ink,#9a5b1b)}
  .hb-results .hr-sst.bad{color:var(--hb-risk,#e5484d)}
  .hb-results .hr-sd{font-size:var(--f-body);color:var(--hb-muted,#5f6b7c);margin-top:var(--s1);
    overflow-wrap:break-word}
  .hb-results .hr-sn{text-align:right;font-size:var(--f-md);font-weight:700;color:var(--hb-ink,#0d1622);
    white-space:nowrap;line-height:1.2}
  .hb-results .hr-sn.zero{color:var(--hb-muted-2,#9aa7b8)}
  /* The unit repeats on every row, so it is lowercase and without tracking: in small caps it competed in weight with
     the number itself, and six "RESULTS" in a row shouted more than the numbers, which are what must be read. */
  .hb-results .hr-sn small{display:block;font-size:var(--f-micro);font-weight:500;
    color:var(--hb-muted-2,#9aa7b8);margin-top:1px}

  /* ── CRITERIA ── */
  .hb-results .hr-goal{font-size:var(--f-body);line-height:1.55;padding:var(--s3) var(--s4);
    border-radius:var(--r-md);background:var(--hb-bg-soft,#fbfdff);border:var(--line);
    border-left:2px solid var(--hb-accent,#3D6FE0);margin-bottom:var(--s3);word-break:break-word}
  .hb-results .hr-cgrp{margin-bottom:var(--s4)}
  .hb-results .hr-cgrp:last-child{margin-bottom:0}
  .hb-results .hr-cgt{margin-bottom:var(--s2)}
  .hb-results .hr-cgt em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:500;
    color:var(--hb-muted-2,#9aa7b8);opacity:.85}
  .hb-results .hr-clist{list-style:none;margin:0;padding:0;display:grid;gap:5px}
  .hb-results .hr-clist li{position:relative;padding-left:var(--s3);line-height:1.5;color:var(--hb-ink,#0d1622);
    overflow-wrap:break-word}
  .hb-results .hr-clist li::before{content:"";position:absolute;left:0;top:7px;width:4px;height:4px;
    border-radius:50%;background:var(--hb-neutral,#c2ccda)}
  .hb-results .hr-cgrp.hard .hr-clist li::before{background:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-cgrp.changes .hr-clist li::before{background:var(--hb-accent2,#16B8A6)}
  `;
