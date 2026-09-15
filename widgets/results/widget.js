// Results widget — the GENERIC SURFACE where zaelar shows what it found. Whoever did the work (a Brain Worker, the
// browser, the brain) fills it through declared actions; this only RENDERS. It never searches by itself.
//
// FOUR TABS (2026-08-12) — because a complex search is not just its result:
//   · RESULTS — the cards, and a full record when one is opened (second page, with its "back").
//   · SUMMARY — where the work stands, how many candidates it explored, how many remain, and what it did.
//   · SOURCES — which websites it entered and WHAT HAPPENED on each one (entered · capped at 50 · required login · error).
//   · CRITERIA — the task as currently executed, with corrections the operator gave along the way.
// The active tab lives in the PERSISTED payload (like `view`/`focus`), not in a variable in this file: this is why
// "show me where you got this from" —a voice phrase that arrives through the brain— moves the screen, and why the
// sheet survives re-render, reconnect, and restart. The local click is rendered IMMEDIATELY and also persisted, so
// the tab does not blink waiting for the server and is not lost either.
//
// DYNAMIC RECORD. A boat does not read like a paper or an email: beyond fixed fields, an item may bring `blocks` — a
// list of composition pieces from a CLOSED vocabulary (text · facts · chips · gallery · meter · table · link ·
// section). This gives the freedom of "a different HTML record per result type" WITHOUT accepting third-party HTML:
// this payload comes from the open web, and everything is rendered with textContent.
//
// FLUID WIDTH. The sheet no longer owns its width (before: fixed 620px, so fullscreen left a narrow column in the
// middle of the screen). It takes 100% of its card and CSS distributes columns by the REAL available width — with a
// minimum per card type and a column CAP, so it neither strangles when shrunk nor turns into eight confetti columns
// when maximized.
//
// SECURITY: item text is web/3rd-party-sourced → built with textContent ONLY (never innerHTML).

// V2-227 scope C — PROCESS comes FIRST, and this is not a preference about ordering: the sheet opens BEFORE there is a
// single result, so the first tab is the only one that has anything to show during the first few minutes.
// The operator's request was literal: "if the worker takes a while, the user gets bored and the experience is poor.
// They need to see IN REAL TIME what is happening."
// The LABELS are resolved per paint (`tabLabel`), never stored in this table: a module-level constant is built
// once, at IMPORT time, so its text would freeze in whatever language happened to be active the first time this
// module loaded and would survive every later switch (V2-694). The table keeps only the ids, which are data.
const TABS = [{id: "process"}, {id: "results"}, {id: "summary"}, {id: "sources"}, {id: "criteria"}];

// Source state → how it is phrased and colored. The vocabulary is closed in the backend; here it is only translated.
// The distinction matters: "could not enter" and "entered but was capped at 50" are VERY different outcomes.
const SOURCE_STATUS = {
  ok:      {cls: "ok"},
  partial: {cls: "warn"},
  auth:    {cls: "warn"},
  blocked: {cls: "bad"},
  error:   {cls: "bad"},
  pending: {cls: "idle"},
};

const CRIT_SECTIONS = [
  {key: "hard"}, {key: "soft"}, {key: "enrichments"},
  {key: "assumed"}, {key: "quality_bar"}, {key: "changes"},
];

function injectStyles(){
  if(document.getElementById("hb-results-css"))return;
  const s=document.createElement("style"); s.id="hb-results-css"; s.textContent=`
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
    --s1:5px; --s2:9px; --s3:14px; --s4:18px; --s5:26px;      /* ~4-5 grid, with more air (2026-08-12) */
    --f-micro:11px;                                           /* uppercase labels, with tracking */
    --f-sm:13px;                                              /* metadata, states (+1.5px) */
    --f-body:14.5px;                                          /* body for everything (+2px, readability) */
    --f-md:16px;                                              /* record title (+2px) */
    --f-lg:19px; --f-xl:23px;                                 /* record and summary figures */
    --r-sm:7px; --r-md:10px; --r-lg:13px; --r-pill:99px;       /* radii */
    --line:1px solid var(--hb-line,#e3e8f0);
    font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    color:var(--hb-ink,#0d1622);font-size:var(--f-body);line-height:1.62;
    width:100%;min-width:0;display:flex;flex-direction:column}
  /* Every COMPARED number uses tabular figures. On a surface whose job is stacking prices and scores, variable-width
     digits force rereading to know which is greater. */
  .hb-results .hr-price,.hb-results .hr-score,.hb-results .hr-pp,.hb-results .hr-n,
  .hb-results .hr-stat b,.hb-results .hr-sn,.hb-results .hr-tbl td,.hb-results .hr-dprice{
    font-variant-numeric:tabular-nums}
  .hb-results .hr-bt,.hb-results .hr-cgt,.hb-results .hr-pk,.hb-results .hr-stat span{
    font-size:var(--f-micro);font-weight:700;letter-spacing:.06em;text-transform:uppercase;
    color:var(--hb-muted-2,#9aa7b8)}

  /* ── STICKY HEADER ──────────────────────────────────────────────────────────────────────────────────────────
     A ten-result sheet is scrolled, and with the header in flow the tabs disappeared upward exactly when they were
     needed most (look at the last card and jump to Sources). The card provides scrolling (.hb-scroll from canvas);
     here we only stick to its edge. The OPAQUE background is not decoration: without it, cards would read underneath
     the title while scrolling. */
  .hb-results .hr-top{position:sticky;top:0;z-index:5;background:var(--hb-bg,#fff);
    padding-top:2px;margin:-2px 0 0}
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
  .hb-results .hr-tabs{display:flex;gap:2px;border-bottom:var(--line);margin:var(--s3) 0 var(--s4);
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

  /* ── GRID AND RECORDS ──────────────────────────────────────────────────────────────────────────────────────
     The accent strip remains ONLY on the featured card. With ten results —the new delivery default— ten vertical
     blue bars read like a barcode and stop highlighting anything: if everything shouts, nothing shouts. The others
     carry a 1px line and lift on hover only if clicking does something. */
  .hb-results .hr-grid{display:grid;gap:var(--s3);min-width:0}
  .hb-results .hr-grid + .hr-grid{margin-top:var(--s3)}
  .hb-results .hr-card{position:relative;display:block;text-decoration:none;color:inherit;
    border:var(--line);border-radius:var(--r-lg);padding:var(--s3) var(--s4);background:var(--hb-bg,#fff);
    min-width:0;transition:border-color .15s,box-shadow .15s,transform .15s}
  /* The featured card is marked with border and background, period. A color strip peeking from the top ("label tab")
     was also tried: with the card radius it looked like a loose dash FLOATING above the border, i.e. a layout defect.
     The tempered background + turquoise border + badge already distinguish it from nine siblings; one more ornament
     did not highlight better, it only added something that could look broken. */
  .hb-results .hr-card.primary{border-color:color-mix(in srgb,var(--hb-accent2,#16B8A6) 42%,var(--hb-line,#e3e8f0));
    background:var(--hb-bg-soft,#fbfdff)}
  .hb-results a.hr-card:hover,.hb-results .hr-card.choosable:hover{border-color:var(--hb-accent,#3D6FE0);
    box-shadow:var(--hb-shadow-1,0 8px 30px rgba(13,22,34,.12));transform:translateY(-1px)}
  /* ── THE PHOTO ── a PLATE with a fixed aspect, and the image CONTAINED inside it ────────────────────────────
     It used to be a 100%-wide box of 128 fixed pixels under 'object-fit:cover', i.e. a band whose aspect came from the CARD's width
     and a constant. On a maximized sheet that band measured 1142x168 (6.8:1) and the photo of a pot is 320x251
     (1.27:1): 'cover' scaled it to 1142x896 and cropped away 81% of its height, leaving a horizontal strip of
     steel with no pot in it. The operator, with the screenshot: «estas fotos horizontales no sirven para nada
     porque no se ve absolutamente nada».
     'cover' is only safe when the box aspect is CLOSE to the photo's; it never is here, because the sheet is
     resizable and the photos come from whatever shop the search landed on — portrait bottles, landscape cars,
     square product shots. So: the box aspect is FIXED by the layout (not by the card width), and the image is
     CONTAINED — whole, always, whatever its shape. The plate behind it is light on purpose: product photography
     ships with a white background baked in, so a light tray is what makes it look seamless instead of a white
     rectangle floating on a dark card. */
  .hb-results .hr-shot{position:relative;display:grid;place-items:center;overflow:hidden;
    border-radius:var(--r-md);background:#f4f6fa;border:1px solid rgba(13,22,34,.07)}
  .hb-results .hr-shot img{display:block;max-width:100%;max-height:100%;width:auto;height:auto;
    object-fit:contain}
  .hb-results .hr-sec .hr-shot{width:100%;aspect-ratio:4/3;margin-bottom:var(--s3)}

  /* ── THE FOUR LIST LAYOUTS ── the surface decides which, from the SHAPE of what it was given ────────────────
     «me gustaría que la lista de resultados pueda tener de uno a cinco tipos de formato y que nos adaptemos a
     cada tipo de artículo». They are PRESET here —not improvised per delivery— and chosen by 'layoutFor()'.
     They are named after SHAPES and the sheet's optional 'kind' after THINGS, deliberately: the first draft
     called this one 'media' and the vocabulary of kinds also has a 'media' (audio, video), which is two
     meanings on one word in one file — the older one wins the argument and the newer one goes quietly wrong.
       · split    photo LEFT, data RIGHT. The operator's explicit ask and the market standard for anything that
                  is an ARTICLE (a pot, a car, a flat): the photo identifies it, the data decides it.
       · gallery  photo on top, wide. For results where the image IS the answer (places, rooms, artwork).
       · rows     no photo. A dense readable list for documents, quotes, links.
       · compare  composite proposals side by side (the 'parts' card that already existed).
     What is NOT preset is which FIELDS a card carries: those come from 'facts', filled per article type by
     whoever ran the search — a car brings year/km/fuel and a pot brings capacity/diameter/lid. */
  .hb-results .hr-card.split{display:grid;grid-template-columns:minmax(110px,var(--hr-shot-col,.32fr)) 1fr;
    gap:var(--s4);align-items:start}
  .hb-results .hr-card.split .hr-shot{width:100%;aspect-ratio:1/1}
  .hb-results .hr-card.split.primary{--hr-shot-col:.38fr}
  .hb-results .hr-card.gallery .hr-shot{width:100%;aspect-ratio:4/3;margin-bottom:var(--s3)}
  .hb-results .hr-card.gallery.primary .hr-shot{aspect-ratio:16/9}
  .hb-results .hr-body{min-width:0}
  /* Below ~430px the two columns strangle both halves (a 110px photo next to a 7-em title). The photo goes back
     on top — still a FIXED aspect plate with the image contained, never a band. */
  @container (max-width: 430px){
    .hb-results .hr-card.split{grid-template-columns:1fr}
    .hb-results .hr-card.split .hr-shot{aspect-ratio:4/3;margin-bottom:var(--s2)}
  }
  .hb-results .hr-grid{container-type:inline-size}

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
  /* ── PROCESS (V2-227 C) ── the loader animates via CSS, NEVER via a JS timer: an interval freezes with
     the tab in the background and survives a render that disconnects it, and both things leave a loader that
     is in the DOM and lies. The hr-spin class genuinely spins while it exists. */
  /* Sizes in em rather than px: they scale with the row's typography, so the loader does not become too small if the
     scale changes — which is exactly what the raw-magnitude ratchet monitors. */
  .hb-results .hr-spin{width:1em;height:1em;flex:none;border-radius:50%;
    border:2px solid var(--hb-neutral,#c2ccda);border-top-color:var(--hb-accent,#3D6FE0);
    animation:hrspin .8s linear infinite}
  @keyframes hrspin{to{transform:rotate(360deg)}}
  .hb-results .hr-steps{display:flex;flex-direction:column;gap:var(--s2);margin-top:var(--s4)}
  .hb-results .hr-step{display:flex;align-items:baseline;gap:var(--s2);font-size:var(--f-body);
    color:var(--hb-muted,#5f6b7c);line-height:1.45}
  /* The LAST line with the worker alive is what is happening NOW: it is read first without having to count rows. */
  .hb-results .hr-step.now{color:var(--hb-ink,#16202c);font-weight:500}
  .hb-results .hr-bullet{width:.42em;height:.42em;flex:none;border-radius:50%;
    background:var(--hb-neutral,#c2ccda);transform:translateY(-2px)}
  .hb-results .hr-step.now .hr-bullet{background:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-steptext{flex:1;min-width:0;overflow-wrap:anywhere}
  .hb-results .hr-note{margin-top:var(--s4);font-size:var(--f-small,12px);color:var(--hb-muted,#5f6b7c)}
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

  /* ── PROCESS · EMBEDDED BROWSER (V2-571) ─────────────────────────────────────────────────────────────────
     The operator's redesign: the browser and the sheet are ONE flow, so the capture renders INSIDE the process
     tab (top-left), with the search FILTERS beside it and the event feed below, newest first. Flex with wrap
     rather than a fixed grid: on a narrow card the filters drop below the capture instead of strangling it. */
  .hb-results .hr-proc{display:flex;flex-wrap:wrap;gap:var(--s3);margin-bottom:var(--s3);align-items:flex-start}
  .hb-results .hr-proc-nav{flex:2 1 380px;min-width:0}
  .hb-results .hr-proc-side{flex:1 1 200px;min-width:0}
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
  `; document.head.appendChild(s);
}

// ── safe primitives ─────────────────────────────────────────────────────────────────────────────────────────
function elem(tag, cls, text){
  const e=document.createElement(tag);
  if(cls) e.className=cls;
  if(text!=null) e.textContent=String(text);
  return e;
}

// ── installation and session identifiers ─────────────────────────────────────────────────────────────────────
// They RIDE THE PAYLOAD now (`data.identity`, filled by data.py): the widget contract bans network in widget.js,
// and this fetch was the violation that kept `make test-widgets` permanently red — under which a NEW violation in
// any widget was invisible (V2-601 T-10). Same visible behavior: no identity → the strip removes itself.

function shortId(id){
  id = String(id||"");
  return id.length > 13 ? id.slice(0,8) + "…" : (id || "—");
}

// Identity strip: User · Session · Copy (bottom of the Summary tab since V2-538). The button copies BOTH FULL ids, in a format a code agent understands at a
// glance. It is painted immediately (with "...") and filled when fetch returns; if there is no identity (endpoint
// down), the strip removes itself instead of leaving an empty gap.
function identityStrip(id){
  id = (id && (id.user_id || id.session_id)) ? id : null;
  if(!id) return document.createDocumentFragment();     // no identity in the payload → no strip (as before)
  const strip = elem("div","hr-ident");
  const uBit = elem("span","hr-idbit"); const uCode = elem("code","","…"); uBit.append(elem("b","",tt("user", null, "Usuario")), uCode);
  const sBit = elem("span","hr-idbit"); const sCode = elem("code","","…"); sBit.append(elem("b","",tt("session", null, "Sesión")), sCode);
  const btn = elem("button","hr-idcopy",tt("copy", null, "⧉ Copiar")); btn.type = "button"; btn.disabled = true;
  strip.append(uBit, sBit, btn);
  {
    uCode.textContent = shortId(id.user_id);  uBit.title = tt("user_", null, "Usuario: ") + (id.user_id || "—");
    sCode.textContent = shortId(id.session_id); sBit.title = tt("session_", null, "Sesión: ") + (id.session_id || "—");
    btn.disabled = false;
    let reset = null;
    btn.addEventListener("click", async () => {
      const text = `user_id: ${id.user_id||""}\nsession_id: ${id.session_id||""}`;
      let ok = true;
      try{ await navigator.clipboard.writeText(text); }
      catch(_){                                    // no Clipboard API (insecure context) → textarea + execCommand
        try{
          const ta = document.createElement("textarea");
          ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
          document.body.appendChild(ta); ta.focus(); ta.select();
          ok = document.execCommand("copy"); ta.remove();
        }catch(__){ ok = false; }
      }
      btn.textContent = ok ? tt("copied", null, "✓ Copiado") : tt("copy_failed", null, "No se pudo copiar");
      btn.classList.toggle("ok", ok);
      if(reset) clearTimeout(reset);
      reset = setTimeout(() => { btn.textContent = tt("copy", null, "⧉ Copiar"); btn.classList.remove("ok"); }, 1800);
    });
  }
  return strip;
}

function photo(url, alt, cls){
  const img=document.createElement("img"); img.className=cls||"";
  img.src=url; img.alt=alt||""; img.loading="lazy"; img.referrerPolicy="no-referrer";
  img.addEventListener("error",()=>img.remove());   // dead photo link → drop silently, never break the card
  return img;
}

// A photo inside a PLATE of fixed aspect. The plate is what holds the geometry (so a portrait bottle and a
// landscape car both get the same tile and the grid stays a grid) and the image is CONTAINED inside it, so
// nothing is ever cropped. A dead photo empties the plate rather than collapsing the card's layout — which is
// why the plate keeps its size: a row where one tile vanished reflows every sibling.
function photoPlate(url, alt){
  const box=elem("div","hr-shot");
  box.appendChild(photo(url, alt, ""));
  return box;
}

// The SITE a link lands on, which is what the operator is deciding about when he clicks. A raw url is not an
// answer to "where does this take me": `amazon.es` is.
function hostOf(url){
  try{ return new URL(String(url), "https://x.invalid").hostname.replace(/^www\./, ""); }
  catch(_){ return ""; }
}

// The link to the ORIGINAL page, as a labelled control. `stopPropagation` because a card can be CHOOSABLE:
// without it, opening the shop would also silently pick the result.
function sourceLink(url, {wide=false}={}){
  const u=String(url||""); if(!u) return null;
  const host=hostOf(u);
  const a=elem("a","hr-open"+(wide?" wide":""),
               host ? tt("view_on", {site: host}, "Ver en " + host) : tt("view_source", null, "Ver la ficha original"));
  a.href=u; a.target="_blank"; a.rel="noopener noreferrer";
  a.title = tt("open_original", null, "Abrir la ficha original en una pestaña nueva") + " — " + u;
  a.addEventListener("click", e=>e.stopPropagation());
  return a;
}

// ── WHICH of the four list layouts ──────────────────────────────────────────────────────────────────────────
// The surface decides, from the SHAPE of what it was given — `widgets/presentation.py` rule 1, which exists
// because a guessed `columns:2` from outside once left three rich cards with an orphan. The sheet may declare
// WHAT KIND OF THING it found (`kind`), which is content, not layout: saying "these are products" is a fact
// about the results; saying "draw them in two columns" is a decision that belongs here.
const LAYOUTS = ["split", "gallery", "rows", "compare"];
function layoutFor(items, kind){
  const arr = Array.isArray(items) ? items.filter(Boolean) : [];
  if(arr.some(it => (it.parts||[]).length)) return "compare";
  const k = String(kind||"").trim().toLowerCase();
  if(k === "plan") return "compare";
  const withImg = arr.filter(it => it.image || (it.images||[]).length).length;
  if(!withImg) return "rows";                       // nothing to show: a photo column of empty plates is worse
  if(k === "document" || k === "link") return "rows";
  if(k === "place" || k === "media" || k === "photo") return "gallery";
  // A DECLARED product list is photo-left even when this particular batch came back thin: what a result is does
  // not change because one search forgot to bring prices, and a list that reflows between two formats as facts
  // trickle in is worse than one that stays put.
  if(k === "product") return "split";
  // Does the card carry enough DATA to deserve a column of its own next to the photo? A result with a price, a
  // rating or a spec sheet does; a bare titled thumbnail does not — that one reads better as a gallery tile.
  const rich = arr.some(it => it.price || it.score || (it.facts||[]).length || (it.lines||[]).length > 1
                              || (it.blocks||[]).length);
  return rich ? "split" : "gallery";
}

function factsTable(facts){
  const box=elem("div","hr-facts");
  (Array.isArray(facts)?facts:[]).forEach(f=>{
    if(!f || !f.label) return;
    box.append(elem("div","hr-fl",f.label), elem("div","hr-fv",f.value==null?"":f.value));
  });
  return box.childElementCount ? box : null;
}

function pct(v, max){
  const m=Number(max)||10, n=Number(v);
  if(!isFinite(n) || m<=0) return 0;
  return Math.max(0, Math.min(100, (n/m)*100));
}

// RATING as a compact label (for a card header).
function scoreTag(score){
  if(!score) return null;
  if(score.value == null) return score.label ? elem("span","hr-score",score.label) : null;
  const tag=elem("span","hr-score", String(score.value));
  tag.appendChild(elem("small","", "/"+(score.max||10)));
  if(score.label) tag.title=score.label;
  return tag;
}

// ...and as an explained block (for the record): score, bar, and WHY.
function scoreBlock(score){
  if(!score || (score.value==null && !score.label && !score.why)) return null;
  const box=elem("div","");
  box.appendChild(elem("div","hr-bt",tt("rating", null, "Valoración")));
  if(score.value != null){
    const row=elem("div","hr-head");
    row.appendChild(elem("div","hr-t", `${score.value} / ${score.max||10}`));
    if(score.label) row.appendChild(elem("div","hr-price",score.label));
    box.appendChild(row);
    const bar=elem("div","hr-bar"); const fill=elem("i");
    fill.style.width=pct(score.value, score.max)+"%"; bar.appendChild(fill); box.appendChild(bar);
  } else if(score.label){
    box.appendChild(elem("div","hr-t",score.label));
  }
  if(score.why) box.appendChild(elem("div","hr-why",score.why));
  return box;
}

// ── DYNAMIC RECORD: blocks ──────────────────────────────────────────────────────────────────────────────────
// Closed vocabulary, already sanitized in data.py. Each block is rendered with our primitives: the worker composes
// the record its result type needs, but does not provide even one HTML tag.
function renderBlock(b, depth){
  if(!b || !b.kind) return null;
  const wrap=elem("div","");
  if(b.title) wrap.appendChild(elem("div","hr-bt",b.title));
  switch(b.kind){
    case "text":
      (b.lines||[]).forEach(l=>wrap.appendChild(elem("div","hr-ln"+(b.tone?" "+b.tone:""), l)));
      break;
    case "facts": {
      const ft=factsTable(b.facts); if(ft){ ft.style.margin="0"; wrap.appendChild(ft); }
      break;
    }
    case "chips": {
      const row=elem("div","hr-chips");
      (b.chips||[]).forEach(c=>row.appendChild(elem("span","hr-chip",c)));
      wrap.appendChild(row);
      break;
    }
    case "gallery": {
      const strip=elem("div","hr-strip");
      (b.images||[]).forEach(u=>strip.appendChild(photo(u, b.title||"", "")));
      wrap.appendChild(strip);
      break;
    }
    case "meter": {
      const bar=elem("div","hr-bar"); const fill=elem("i");
      fill.style.width=pct(b.value, b.max)+"%"; bar.appendChild(fill); wrap.appendChild(bar);
      wrap.appendChild(elem("div","hr-why", (b.caption ? b.caption+" · " : "") + `${b.value} / ${b.max||10}`));
      break;
    }
    case "table": {
      // The table lives in its OWN scroll container. It used to get `display:block` to overflow, and that removes its
      // table behavior: columns stop aligning across rows, which is the only thing a table adds over a list.
      const box=elem("div","hr-tblwrap");
      const t=elem("table","hr-tbl");
      if(b.columns && b.columns.length){
        const tr=elem("tr"); b.columns.forEach(c=>tr.appendChild(elem("th","",c)));
        const thead=elem("thead"); thead.appendChild(tr); t.appendChild(thead);
      }
      const tb=elem("tbody");
      (b.rows||[]).forEach(r=>{ const tr=elem("tr"); (r||[]).forEach(c=>tr.appendChild(elem("td","",c))); tb.appendChild(tr); });
      t.appendChild(tb); box.appendChild(t); wrap.appendChild(box);
      break;
    }
    case "link": {
      const a=elem("a","hr-link",b.label||b.url);
      a.href=b.url; a.target="_blank"; a.rel="noopener noreferrer";
      a.style.marginTop="0"; wrap.appendChild(a);
      break;
    }
    case "section": {
      const inner=elem("div","hr-sub-sec");
      (b.blocks||[]).forEach(x=>{ const e=renderBlock(x, (depth||0)+1); if(e) inner.appendChild(e); });
      if(!inner.childElementCount) return null;
      wrap.appendChild(inner);
      break;
    }
    default: return null;
  }
  return wrap.childElementCount ? wrap : null;
}

// The LIST has no room for the full record. Seen on screen: a card with its cost table, meter, and documentation
// section occupied the ENTIRE card, and with ten results —the delivery default since 2026-08-12— the list stops being
// SCANNABLE, which is the only thing a list must do. So the list keeps LIGHT blocks and the rest is what you open the
// record to inspect.
// The exception is `text` with WARNING tone: an important caveat hidden behind a click is exactly what the
// presentation rule forbids ("nothing important at the end of a long field").
const LIGHT_BLOCKS = new Set(["chips"]);
function isLight(b){
  if(!b) return false;
  if(LIGHT_BLOCKS.has(b.kind)) return true;
  return b.kind === "text" && b.tone === "warn";
}

function renderBlocks(blocks, {compact = false} = {}){
  let list = Array.isArray(blocks) ? blocks : [];
  if(compact) list = list.filter(isLight).slice(0, 2);
  const box=elem("div","hr-blocks");
  list.forEach(b=>{ const e=renderBlock(b,0); if(e) box.appendChild(e); });
  return box.childElementCount ? box : null;
}

// ── column distribution: decided by REAL WIDTH, not a guessed parameter ──────────────────────────────────────
// The sheet used to have a fixed 620px width and the number of columns was eyeballed from content shape. Now the card
// is resizable (and can go fullscreen), so available width rules: each column has a MINIMUM based on how rich the card
// is and there is a column CAP so maximizing does not create eight confetti columns. Expressed in pure CSS
// (`auto-fill` + `minmax` with a 100%/cap floor), so it reflows by itself when dragging the corner — without measuring
// anything from JS or listening to resizes.
function gridStyle(items, cap, layout){
  const rich = items.some(it => it && (
    (it.parts && it.parts.length) ||
    (it.blocks && it.blocks.length) ||
    (it.facts && it.facts.length > 3) ||
    (it.images && it.images.length) ||
    (it.lines && it.lines.length > 4)
  ));
  const medium = !rich && items.some(it => it && ((it.lines && it.lines.length) || it.image || it.facts));
  // A `split` card is two columns wide by construction (plate + data), so its floor is the one that has to grow;
  // a `gallery` tile is a picture with a caption and packs tighter than the content heuristic would guess.
  const min = layout === "split" ? 430 : layout === "gallery" ? 260 : rich ? 400 : medium ? 300 : 230;
  let maxCols = layout === "split" ? 2 : layout === "gallery" ? 4 : rich ? 2 : medium ? 3 : 4;
  const n = Number(cap);
  if(Number.isFinite(n) && n >= 1) maxCols = Math.min(maxCols, Math.floor(n));
  maxCols = Math.max(1, maxCols);
  // The GAP comes from the SAME variable that paints it (`--s3`), not from a copied number here. Having it twice cost
  // one column: when the grid rose from 12 to 14px, this calculation kept subtracting 12, so each track floor was 2px
  // above what truly fit and `auto-fill` dropped from two columns to ONE on a 1,420px sheet. A two-pixel mismatch that
  // appears as "maximize no longer uses the width".
  const floor = `calc((100% - ${maxCols - 1} * var(--s3)) / ${maxCols})`;
  return `repeat(auto-fill,minmax(max(min(100%,${min}px),${floor}),1fr))`;
}

// ── one card ────────────────────────────────────────────────────────────────────────────────────────────────
function makeCard(it, isPrimary, choose, ctx, layout, nav){
  const parts = Array.isArray(it.parts) ? it.parts : [];
  const blocks = Array.isArray(it.blocks) ? it.blocks : [];
  const hasDetail = parts.length || blocks.length || it.score
                    || (Array.isArray(it.images) && it.images.length)
                    || (Array.isArray(it.facts) && it.facts.length);
  // A composite card owns interactive children (per-piece links, "ver detalle") so it can't be an <a> — nesting
  // links/buttons inside an anchor is invalid and swallows their clicks into the outer navigation. When it cannot
  // be a link, the url is NOT dropped: it goes to the footer as an explicit control (see `sourceLink`).
  const asLink = it.url && !hasDetail;
  const card = document.createElement(asLink ? "a" : "div");
  const shot = (layout !== "rows" && it.image) ? photoPlate(it.image, it.title) : null;
  // A card with no photo can never wear a PHOTO layout: `split` is a two-column grid, and applied to a card
  // without its first column it would drop the title in the left track and the subtitle in the right one. The
  // list may therefore be mixed, which is correct — and `presentation.audit` already flags items that do not
  // share the same shape, because that is a defect of the DATA, not of the drawing.
  const lay = shot ? (layout || "rows") : "rows";
  card.className = "hr-card " + lay + (isPrimary ? " primary" : "");
  if(asLink){ card.href = it.url; card.target = "_blank"; card.rel = "noopener noreferrer"; }
  if(shot) card.appendChild(shot);
  // In `split` the data is a COLUMN beside the photo, so it needs its own box; in every other layout the card
  // itself is that box and an extra wrapper would only add a nesting level.
  const body = (lay === "split") ? elem("div","hr-body") : card;
  const head = elem("div","hr-head");
  head.appendChild(elem("div","hr-t", it.title || ""));
  const sc = scoreTag(it.score); if(sc) head.appendChild(sc);
  if(it.price) head.appendChild(elem("div","hr-price", it.price));
  body.appendChild(head);
  // The BADGE goes with the title, not the footer. It is a label that QUALIFIES the result ("Best set"), and below it
  // ended up next to the detail button, where it read like a second button.
  const meta = elem("div","hr-metarow");
  if(it.subtitle) meta.appendChild(elem("span","hr-s", it.subtitle));
  if(it.badge) meta.appendChild(elem("span","hr-badge", it.badge));
  if(meta.childElementCount) body.appendChild(meta);
  // 80 lines (data.py's cap) so a full block of text — e.g. a song's lyrics — fits in one item's body, not just
  // a handful of spec-sheet bullets (2026-08-03). In the list they are bounded: the full block belongs to the record.
  (Array.isArray(it.lines) ? it.lines : []).slice(0, hasDetail ? 3 : 80)
    .forEach(l=>body.appendChild(elem("div","hr-ln", l)));

  const bl = renderBlocks(blocks, {compact: true}); if(bl) body.appendChild(bl);

  // In `split` the spec sheet is what fills the column beside the photo — and it is also the per-article-type
  // half of this surface: a car brings year/km/fuel, a pot brings capacity/diameter/lid. Bounded here (the full
  // table belongs to the record) so ten results stay comparable instead of ten different heights.
  if(lay === "split" && Array.isArray(it.facts) && it.facts.length){
    const ft = factsTable(it.facts.slice(0, 4)); if(ft) body.appendChild(ft);
  }

  // the pieces of a composite result, so three proposals stay comparable at a glance
  if(parts.length){
    const box=elem("div","hr-parts");
    parts.forEach(p=>{
      const row=elem("div","hr-part");
      if(p.kind) row.appendChild(elem("span","hr-pk", p.kind));
      row.appendChild(elem("span","hr-pt", p.title||""));
      if(p.price) row.appendChild(elem("span","hr-pp", p.price));
      box.appendChild(row);
    });
    body.appendChild(box);
  }

  // ── the footer: open the record, and open the ORIGINAL page ──
  const foot = elem("div","hr-foot");
  if(hasDetail && ctx){
    const btn=elem("button","hr-more",tt("see_detail", null, "Ver detalle →")); btn.type="button";
    // NAVIGATE FIRST, PERSIST AFTER. This button used to do only the second half: it posted `detail` and waited
    // for the server to push the new state back over SSE. The post landed (the sheet on disk says
    // `view:"detail"`) and the screen never moved, because the push carried the STORAGE id (`results--7aadbb-1`)
    // and the canvas indexes its cards by the CANVAS id (`results::7aadbb-1`) — so `refreshData` looked up a
    // window that does not exist and returned. The operator read it as «el botón de ver los detalles no
    // funciona», which is exactly what a working button looks like when nothing repaints.
    // That id is fixed in `widgets/store.py`. This is the other half, and the one that makes the button
    // independent of it: the tabs above have painted locally and persisted afterwards since V2-538 («the tab
    // cannot blink while waiting for the server»), and opening a record is the same gesture. The item is
    // already on screen, so there is nothing to fetch to draw it.
    btn.addEventListener("click", async (e)=>{ e.preventDefault(); e.stopPropagation();
      if(nav) nav("detail", it.title || "");
      btn.disabled=true;
      const r = await ctx.action("detail", { title: it.title || "" });
      btn.disabled=false;
      // A REFUSED action has to SHOW — but it no longer un-navigates. The record IS painted and correct; what
      // failed is storing that the operator is looking at it, so the brain's copy and a reload would disagree.
      // Saying that is honest; snatching the page back would not be.
      if(!r || r.ok===false){
        const why = (r && r.error) ? String(r.error) : tt("engine_silent", null, "el motor no respondió a la acción");
        if(nav) nav("detail", it.title || "", why);
        else { btn.textContent = tt("see_detail_", null, "Ver detalle → ") + tt("open_failed", null, "no se pudo abrir");
               btn.classList.add("hr-more-err"); btn.title = why; }
      }
    });
    foot.appendChild(btn);
  }
  // ALWAYS, whenever there is one and the card is not itself the link.
  if(!asLink){ const src = sourceLink(it.url); if(src) foot.appendChild(src); }
  if(foot.childElementCount) body.appendChild(foot);

  if(body !== card) card.appendChild(body);

  if(choose && !asLink){
    card.classList.add("choosable");
    const tagOf=()=>elem("span","hr-chosen-tag",tt("chosen", null, "✓ Elegido"));
    if(choose.chosenTitle && it.title === choose.chosenTitle){ card.classList.add("chosen"); card.appendChild(tagOf()); }
    card.addEventListener("click", async () => {
      if(card.classList.contains("chosen")) return;
      choose.root.querySelectorAll(".hr-card.chosen").forEach(c => { c.classList.remove("chosen"); const t=c.querySelector(".hr-chosen-tag"); if(t)t.remove(); });
      card.classList.add("chosen"); card.appendChild(tagOf());
      await choose.ctx.action("choose", { title: it.title || "" });
    });
  }
  return card;
}

// ── page 2: ONE item, in full ────────────────────────────────────────────────────────────────────────────────
// This renders "show me proposal one in detail": every photo, every datum, THE RATING with its reason, the whole
// dynamic record, and each package piece expanded with its price, times, and real link.
function renderDetail(panel, it, ctx, nav, warn){
  const back=elem("button","hr-back",tt("back_list", null, "← Volver a la lista")); back.type="button";
  // Same rule as the detail button and the tabs: paint NOW, persist after. Going back to a list that is already
  // in memory must not wait for a round trip either.
  back.addEventListener("click", async ()=>{ if(nav) nav(null); await ctx.action("list", {}); });
  panel.appendChild(back);

  panel.appendChild(elem("div","hr-dt", it.title||""));
  if(it.price) panel.appendChild(elem("div","hr-dprice", it.price));
  const dmeta = elem("div","hr-metarow");
  if(it.subtitle) dmeta.appendChild(elem("span","hr-s", it.subtitle));
  if(it.badge) dmeta.appendChild(elem("span","hr-badge", it.badge));
  if(dmeta.childElementCount) panel.appendChild(dmeta);
  // The way OUT of our summary and into the full record, ABOVE the fold. The record we render is what the search
  // found worth keeping; the shop's own page is where the thousand remaining fields live, and the operator asked
  // for that door to be on every result. It was at the very bottom, after the whole spec table, printed as a raw
  // url. Now it reads as what it is and sits where it is decided.
  const top = sourceLink(it.url, {wide: true}); if(top) panel.appendChild(top);
  if(warn) panel.appendChild(elem("div","hr-warn", tt("view_not_saved", null,
    "Esta vista no se ha podido guardar en la hoja — la pantalla es correcta, pero al recargar volverá a la lista.")));

  // THE RATING goes ABOVE, before photos: it is the VERDICT. Below the gallery it read like one more datum at the end
  // of the record, when it is exactly what answers "why this one and not another?"
  const sb=scoreBlock(it.score);
  if(sb){ const sec=elem("div","hr-sec"); sec.appendChild(sb); panel.appendChild(sec); }

  const gallery = Array.isArray(it.images) && it.images.length ? it.images : (it.image ? [it.image] : []);
  if(gallery.length){
    const g=elem("div","hr-gal");
    gallery.forEach(u=>g.appendChild(photoPlate(u, it.title)));
    panel.appendChild(g);
  }

  (Array.isArray(it.lines)?it.lines:[]).slice(0,80).forEach(l=>panel.appendChild(elem("div","hr-ln", l)));

  const ft=factsTable(it.facts); if(ft) panel.appendChild(ft);
  const bl=renderBlocks(it.blocks); if(bl) panel.appendChild(bl);

  // The item's own url is NOT repeated here as a bare string: it is the «Ver en <site>» control at the top of
  // this page. Printing it twice —once as a button, once as 60 characters of url— was two controls for one door.

  (Array.isArray(it.parts)?it.parts:[]).forEach(p=>{
    const sec=elem("div","hr-sec");
    if(p.kind) sec.appendChild(elem("span","hr-pk", p.kind));
    sec.appendChild(elem("div","hr-sect", p.title||""));
    if(p.price) sec.appendChild(elem("div","hr-dprice", p.price));
    if(p.subtitle) sec.appendChild(elem("div","hr-s", p.subtitle));
    if(p.image) sec.appendChild(photoPlate(p.image, p.title));
    (Array.isArray(p.lines)?p.lines:[]).forEach(l=>sec.appendChild(elem("div","hr-ln", l)));
    const pf=factsTable(p.facts); if(pf) sec.appendChild(pf);
    const ps = sourceLink(p.url); if(ps) sec.appendChild(ps);
    panel.appendChild(sec);
  });
}

function findFocused(items, focus){
  const f=String(focus||"").trim().toLowerCase();
  if(!f) return null;
  return items.find(it=>String(it&&it.title||"").trim().toLowerCase()===f)
      || items.find(it=>String(it&&it.title||"").trim().toLowerCase().includes(f))
      || null;
}

// ── TAB 1 · RESULTS ─────────────────────────────────────────────────────────────────────────────────────────
function paintResults(panel, data, ctx, nav){
  const items = Array.isArray(data.items) ? data.items : [];

  if(data.view === "detail"){
    const it = findFocused(items, data.focus);
    if(it){ renderDetail(panel, it, ctx, nav, data.viewWarn); return; }
    // focus pointing at nothing (list replaced under it) → fall through to the list, never a blank screen
  }

  const total = items.length;
  const all = items.slice(0, 24);
  if(!all.length){
    panel.appendChild(elem("div","hr-empty", data.note || tt("no_results", null, "Sin resultados todavía.")));
    return;
  }

  const primary = all.filter(it => it && it.primary);
  const rest = all.filter(it => !it || !it.primary);
  const choose = data.choosable ? { root: panel, ctx, chosenTitle: data.chosen } : null;
  // ONE layout for the whole list, decided from ALL the items: choosing per card would put a photo column on
  // some rows and not on others, which is precisely the ragged look the grid exists to prevent.
  const lay = layoutFor(all, data.kind);

  // primary items: share the top row and decide width (one featured item occupies the whole sheet).
  if(primary.length){
    const pgrid = elem("div","hr-grid");
    pgrid.style.gridTemplateColumns = gridStyle(primary, primary.length === 1 ? 1 : 2, lay);
    panel.appendChild(pgrid);
    primary.forEach(it => pgrid.appendChild(makeCard(it, true, choose, ctx, lay, nav)));
  }

  if(rest.length){
    const sgrid = elem("div","hr-grid");
    sgrid.style.gridTemplateColumns = gridStyle(rest, primary.length ? 2 : data.columns, lay);
    panel.appendChild(sgrid);
    rest.forEach(it => sgrid.appendChild(makeCard(it, false, choose, ctx, lay, nav)));
  }

  // Faithful count: if the real pushed results exceed what we render, say so — never silently drop
  // obtained data (the operator asked for a REAL search; the interface must reflect its true size).
  if(total > all.length){
    const more = elem("div","hr-sub", `Mostrando ${all.length} de ${total} resultados.`);
    more.style.marginTop = "10px";
    panel.appendChild(more);
  }
}

// ── TAB 2 · SUMMARY ─────────────────────────────────────────────────────────────────────────────────────────
// REPORTED and DERIVED data are rendered separately on purpose: "explored" is only known by the worker, and if nobody
// said it the tab SAYS so instead of showing the number of cards as if it were the breadth.
function paintSummary(panel, data){
  const s = data.summary || {}, c = data.counts || {};
  const hasAny = Object.keys(s).length || c.shown || c.sources;
  if(!hasAny){
    panel.appendChild(elem("div","hr-empty",
      tt("summary_empty_1", null, "Todavía no hay nada que resumir. Esta pestaña se llena mientras se trabaja: estado, cuántos candidatos se ")
      + tt("summary_empty_2", null, "han explorado y qué se ha ido haciendo.")));
    panel.appendChild(identityStrip(data.identity));   // the audit ids belong to this tab now — see render()'s note (V2-538)
    return;
  }
  if(s.state){
    const row=elem("div","hr-state");
    const done=/termin|complet|listo|entregad|finaliz/i.test(s.state);
    row.appendChild(elem("span","hr-dot "+(done?"ok":"idle")));
    row.appendChild(elem("span","", s.state));
    panel.appendChild(row);
  }
  const stats=elem("div","hr-stats");
  const add=(value, label, tone)=>{
    const box=elem("div","hr-stat"+(tone?" "+tone:""));
    box.appendChild(elem("b","", value));
    // `label`, not `tallyLabel(k)`. There is no `k` in this scope: the call was copied from `paintHarvest`,
    // where the labels come from a table of KEYS, and here every caller already passes the translated string.
    // It went in with V2-694 (77640659) and has been throwing `ReferenceError: k is not defined` ever since —
    // out of `add`, out of `paintSummary`, out of `render`, so the WHOLE sheet died the moment the Summary tab
    // was the active one. `tests/browser/e2e/widgets/test_results_render.py` has been carrying it as an ERROR
    // (not a failure) in its summary fixture, which is why it read as a broken harness rather than a broken
    // widget. The operator's own pot sheet has a summary of 75 explored.
    box.appendChild(elem("span","", label));
    stats.appendChild(box);
  };
  const noBreadth = s.explored == null;
  add(noBreadth ? "—" : s.explored, noBreadth ? tt("unreported", null, "sin reportar") : tt("explored", null, "explorados"), noBreadth ? "dim" : "");
  add(c.shown || 0, tt("on_screen", null, "en pantalla"));
  if(s.discarded != null) add(s.discarded, tt("discarded", null, "descartados"));
  if(c.sources) add(c.sources, tt("sources", null, "fuentes"));
  // Problem sources go in their OWN cell and warning color. Stuffed into the "sources" label, they made a two-line
  // label ("SOURCES · 3 WITH / PROBLEM") that broke the row, and also hid the only datum here that asks the operator
  // for a decision inside another number's footer.
  if(c.sources_failed) add(c.sources_failed, tt("unused", null, "sin aprovechar"), "warn");
  if(s.round && s.round > 1) add(s.round, tt("round", null, "ronda"));
  panel.appendChild(stats);

  if(s.note) panel.appendChild(elem("div","hr-why", s.note));

  if(Array.isArray(s.steps) && s.steps.length){
    panel.appendChild(elem("div","hr-cgt",tt("what_was_done", null, "Lo que se ha hecho")));
    const ul=elem("ul","hr-steps");
    s.steps.forEach(st=>ul.appendChild(elem("li","", st)));
    panel.appendChild(ul);
  }
  panel.appendChild(identityStrip(data.identity));   // audit ids, moved here from the sticky header (V2-538)
}

// ── TAB 3 · SOURCES ─────────────────────────────────────────────────────────────────────────────────────────
// Where data comes from and WHAT happened at each site. This turns "I found nothing" into data that can be audited
// and corrected ("you enter that one, it asks for login").
function paintSources(panel, data){
  const src = Array.isArray(data.sources) ? data.sources : [];
  if(!src.length){
    panel.appendChild(elem("div","hr-empty",
      tt("sources_empty_1", null, "Nadie ha reportado fuentes todavía. Aquí aparecerá cada web que se consulte y qué pasó en ella: si entró, ")
      + tt("sources_empty_2", null, "si le limitaron los resultados, si pedía autenticación o si dio error.")));
    return;
  }
  const c = data.counts || {};
  panel.appendChild(elem("div","hr-sub",
    `${src.length} fuente${src.length===1?"":"s"}`
    + (c.sources_failed ? ` · ${c.sources_failed} sin poder aprovechar` : "")
    + (c.from_sources ? ` · ${c.from_sources} resultados reunidos` : "")));
  // Sources that could NOT be used, FIRST. They are the ones asking for an operator decision ("that one asks for
  // login, I will enter"); successful ones only need to be counted. Stable order within each group.
  const rank = {bad: 0, warn: 1, idle: 2, ok: 3};
  const ordered = src.map((s, i) => [s, i]).sort((a, b) => {
    const ra = rank[(SOURCE_STATUS[a[0].status] || SOURCE_STATUS.ok).cls] ?? 3;
    const rb = rank[(SOURCE_STATUS[b[0].status] || SOURCE_STATUS.ok).cls] ?? 3;
    return ra - rb || a[1] - b[1];
  }).map(x => x[0]);

  const list=elem("div","hr-srcs");
  ordered.forEach(s=>{
    const st = SOURCE_STATUS[s.status] || SOURCE_STATUS.ok;
    const row=elem("div","hr-src"+(st.cls==="bad"||st.cls==="warn" ? " "+st.cls : ""));
    row.appendChild(elem("span","hr-dot "+st.cls));
    const mid=elem("div","");
    const name=elem("div","hr-sname");
    if(s.url){
      const a=elem("a","", s.name); a.href=s.url; a.target="_blank"; a.rel="noopener noreferrer"; name.appendChild(a);
    } else name.textContent = s.name;
    mid.appendChild(name);
    mid.appendChild(elem("div","hr-sst "+st.cls, sourceLabel(s.status)));
    if(s.detail) mid.appendChild(elem("div","hr-sd", s.detail));
    row.appendChild(mid);
    if(s.found != null){
      const n=elem("div","hr-sn"+(s.found ? "" : " zero"), String(s.found));
      n.appendChild(elem("small","", s.found === 1 ? tt("result_one", null, "resultado") : tt("result_many", null, "resultados")));
      row.appendChild(n);
    } else row.appendChild(elem("div",""));
    list.appendChild(row);
  });
  panel.appendChild(list);
}

// ── TAB 4 · CRITERIA ────────────────────────────────────────────────────────────────────────────────────────
// The task as it is being executed NOW. Not the conversation history: the active search criteria at this moment, so
// they can be seen and corrected ("make them 42 to 49 feet").
function paintCriteria(panel, data){
  const c = data.criteria || {};
  const any = c.goal || CRIT_SECTIONS.some(s=>Array.isArray(c[s.key]) && c[s.key].length);
  if(!any){
    panel.appendChild(elem("div","hr-empty",
      tt("criteria_empty_1", null, "Todavía no hay criterios fijados. En cuanto se dirija una búsqueda aparecerán aquí el objetivo, los ")
      + tt("criteria_empty_2", null, "requisitos que descalifican, las preferencias y lo que se haya dado por supuesto — y podrás corregirlos ")
      + tt("criteria_empty_3", null, "hablando.")));
    return;
  }
  if(c.goal) panel.appendChild(elem("div","hr-goal", c.goal));
  const meta=[];
  if(c.domain) meta.push(c.domain);
  if(c.min_candidates) meta.push(tt("min_breadth", {n:c.min_candidates}, `amplitud mínima: ${c.min_candidates} candidatos`));
  if(c.n_final) meta.push(tt("n_final", {n:c.n_final}, `entrega: ${c.n_final} finalistas`));
  if(meta.length) panel.appendChild(elem("div","hr-sub", meta.join(" · ")));

  CRIT_SECTIONS.forEach(sec=>{
    const list = c[sec.key];
    if(!Array.isArray(list) || !list.length) return;
    const grp=elem("div","hr-cgrp "+sec.key);
    const t=elem("div","hr-cgt", critLabel(sec.key));
    const _note = critNote(sec.key);
    if(_note){ t.appendChild(document.createTextNode(" ")); t.appendChild(elem("em","","— "+_note)); }
    grp.appendChild(t);
    const ul=elem("ul","hr-clist");
    list.forEach(x=>ul.appendChild(elem("li","", x)));
    grp.appendChild(ul);
    panel.appendChild(grp);
  });
}

// ── PROCESS ── what is happening while it happens (V2-227 scope C).
//
// It is a VIEW of the live log, not sheet data: `progress` arrives derived in each `view_data` and nobody stores it.
// The phrases already arrive ready to read from scope B ("entering booking.com…"), so nothing is interpreted here —
// they are painted in ORDER, newest at the bottom, which is how something advancing is read.
//
// The loader ANIMATES via CSS rather than JS on purpose: a timer-based animation freezes with the tab in the
// background and survives a render that disconnects it, and both things leave a loader in the DOM that lies.
// This is the lesson of the mobile orb (18/08): 741 frames inside a disconnected canvas, zero pixels, and
// a green test that only counted that the element existed.
// THE HARVEST in numbers (V2-296). The account below says WHAT it is doing; this says HOW MUCH it has done — and it was
// the one thing the tab could not say. The browser now calculates all these figures on each extraction
// (`widgets/browser/act_api._hand_over`) and they were wasted in a sentence.
//
// It is a FUNNEL and is read in that order: how much was examined → what was collected → what fell out at each cut → what remains
// → what reached the conversation. The three pillars (pages, records, candidates) are ALWAYS painted, including zero,
// because "0 records read" is information and precisely distinguishes a page that yielded nothing from one that nobody
// read — the same reason `progress.found(0)` does not stay silent. Rejections appear only when there are any:
// a row "0 repeated" takes up the same space as one that says something.
// `sub` = this one SUBTRACTS. Found by RENDERING it (2026-08-24), which is the only way it was going to show
// up: every geometry check passed — nothing clipped, nothing overflowing, clean reflow 6→3→2 columns — and the
// screenshot still read wrong. Seven identical boxes turn one subtraction into five independent-looking stats:
// "40 records · 9 repeated · 4 unnamed · 5 without a price · 22 candidates" gives no hint that the last number is
// what the others left behind. The ORDER was carrying that meaning, and the order does not survive the reflow —
// at 360px the grid wraps to two columns and "22 candidates" lands beside "5 without a price" looking like its peer.
// A leading minus restores the arithmetic in one character, whatever the grid does with the boxes.
const TALLY = [
  {k:"pages",    always:true},
  {k:"rows",     always:true},
  {k:"repeated", sub:true},
  {k:"unnamed",  sub:true},
  {k:"hollow",   sub:true},
  {k:"kept",     always:true},
  {k:"offered"},
];

function tallyLabel(k){
  switch(k){
    case "pages":    return tt("tally_pages", null, "páginas miradas");
    case "rows":     return tt("tally_rows", null, "fichas leídas");
    case "repeated": return tt("tally_repeated", null, "repetidas");
    case "unnamed":  return tt("tally_unnamed", null, "sin nombre");
    case "hollow":   return tt("tally_hollow", null, "sin precio ni tel.");
    case "kept":     return tt("tally_kept", null, "candidatos");
    case "offered":  return tt("tally_offered", null, "en la conversación");
    default:         return k;
  }
}

function paintHarvest(panel, harvest){
  // `{}` means "we do not know" and nothing is painted: a grid of zeroes would claim that it was examined and empty.
  if(!harvest || !Object.keys(harvest).length) return;
  const grid = elem("div","hr-stats");
  TALLY.forEach(({k, always, sub})=>{
    const n = Number(harvest[k] || 0);
    if(!n && !always) return;
    const box = elem("div","hr-stat" + (!n ? " dim" : "") + (sub ? " cut" : ""));
    // U+2212 MINUS SIGN, not a hyphen: it aligns with the digits and reads as arithmetic, not as a dash.
    box.appendChild(elem("b","", (sub ? "\u2212" : "") + String(n)));
    box.appendChild(elem("span","", tallyLabel(k)));
    grid.appendChild(box);
  });
  if(grid.childNodes.length) panel.appendChild(grid);
}

// ── PROCESS · the errand's BROWSER, embedded (V2-571) ────────────────────────────────────────────────────────
// The operator's redesign: a browser task and its results sheet are ONE flow, so the separate navegador card no
// longer opens for an errand — its capture, its wall and its login handoff render HERE, in the tab that already
// tells the process. Right of the capture: the FILTERS the search runs with (hard criteria + the corrections
// given along the way), because that is what the operator checks the page against. The capture refreshes by SSE
// (the task registry notifies this sheet's card on every view change), never by polling.
// `data.browser` is DERIVED per read and `{}` once the errand ends: a frozen capture pretending to be a live
// browser would lie, so the finished tab keeps only its persisted event history.
function paintBrowser(panel, data, ctx){
  const br = data.browser || {};
  if(!br.task_id) return false;
  const wrap = elem("div","hr-proc");
  const nav = elem("div","hr-proc-nav");
  const view = elem("div","hr-navview");
  if((br.shot_rev || 0) > 0 && br.shot){
    const img = document.createElement("img");
    img.className = "hr-navimg";
    img.alt = br.page_title || tt("page_alt", null, "página");
    img.src = "/widgets/navegador/asset/" + br.shot + "?v=" + (br.shot_rev || 0);
    img.addEventListener("error", ()=>{
      view.textContent = "";
      view.appendChild(elem("div","hr-navph",tt("no_shot", null, "sin captura todavía…")));
    });
    view.appendChild(img);
  } else {
    view.appendChild(elem("div","hr-navph",tt("opening_tab", null, "abriendo pestaña…")));
  }
  nav.appendChild(view);
  if(br.page_title || br.url){
    const u = elem("div","hr-navurl", br.page_title || br.url);
    u.title = br.url || "";
    nav.appendChild(u);
  }
  if(br.wall) nav.appendChild(elem("div","hr-wall","⛔ " + br.wall));
  if(br.awaiting_login){
    const box = elem("div","hr-login");
    box.appendChild(elem("div","hr-login-t",
      tt("login_hint", null, "🔓 Inicia sesión en la ventana de Chrome que se abrió. Tu sesión se guardará para las próximas tareas.")));
    const btn = elem("button","hr-login-btn",tt("login_done", null, "Ya he iniciado sesión")); btn.type = "button";
    btn.addEventListener("click", async ()=>{
      btn.disabled = true;
      const r = (ctx && ctx.action) ? await ctx.action("auth_done", {task_id: br.task_id}) : null;
      // A REFUSED action has to SHOW (the V2-540 lesson): a silently dead login button on a refused forward
      // is exactly the undiagnosable click this sheet already paid for once.
      if(!r || r.ok === false){
        btn.disabled = false;
        btn.textContent = tt("login_done_", null, "Ya he iniciado sesión — ") + ((r && r.error) ? tt("login_retry", null, "no llegó, reintenta") : tt("no_answer", null, "sin respuesta"));
        btn.title = (r && r.error) ? String(r.error) : tt("engine_silent", null, "el motor no respondió a la acción");
      }
    });
    box.appendChild(btn);
    nav.appendChild(box);
  }
  if(br.question){
    const q = elem("div","hr-navq","❓ " + br.question);
    q.appendChild(elem("small","",tt("answer_voice", null, "Responde por voz.")));
    nav.appendChild(q);
  }
  wrap.appendChild(nav);

  // The filters, only when there ARE any: an empty side column would just strangle the capture.
  const c = data.criteria || {};
  const filt = [].concat(Array.isArray(c.hard) ? c.hard : [], Array.isArray(c.changes) ? c.changes : []);
  if(filt.length){
    const side = elem("div","hr-proc-side hr-cgrp hard");
    side.appendChild(elem("div","hr-cgt",tt("filters", null, "Filtros")));
    const ul = elem("ul","hr-clist");
    filt.slice(0, 14).forEach(x=>ul.appendChild(elem("li","", String(x))));
    side.appendChild(ul);
    wrap.appendChild(side);
  }
  panel.appendChild(wrap);
  return true;
}

function paintProcess(panel, data, ctx){
  const pr = data.progress || {};
  const harvest = data.harvest || {};
  const br = data.browser || {};
  const lines = Array.isArray(pr.phases) ? pr.phases.filter(x=>String(x||"").trim()) : [];
  const alive = !!pr.alive;

  if(!lines.length && !alive && !br.task_id && !Object.keys(harvest).length){
    panel.appendChild(elem("div","hr-empty",
      tt("process_empty_1", null, "Aquí se ve lo que va haciendo mientras trabaja: el navegador que conduce, en qué web entra, qué filtro ")
      + tt("process_empty_2", null, "aplica, cuántos resultados encuentra. Todavía no hay ninguna tarea en marcha.")));
    return;
  }

  const head = elem("div","hr-state");
  head.appendChild(elem("span", alive ? "hr-spin" : "hr-dot ok"));
  head.appendChild(elem("span","", alive ? (pr.label || tt("working", null, "Trabajando…")) : tt("finished", null, "Terminado")));
  panel.appendChild(head);

  paintBrowser(panel, data, ctx);
  paintHarvest(panel, harvest);

  // The events read NEWEST FIRST (V2-571, operator: «en orden cronológicamente invertido»): under the browser,
  // the first line is what is happening NOW — nobody scrolls a growing list to its bottom to find the present.
  const list = elem("div","hr-steps");
  lines.slice().reverse().forEach((text, i)=>{
    const row = elem("div","hr-step" + (alive && i === 0 ? " now" : ""));
    row.appendChild(elem("span","hr-bullet"));
    row.appendChild(elem("span","hr-steptext", String(text)));
    list.appendChild(row);
  });
  panel.appendChild(list);

  // When it FINISHES, the tab is not emptied: it remains as a history of what happened (C5). Emptying it would erase the only
  // explanation of why the result is what it is.
  if(!alive && lines.length){
    panel.appendChild(elem("div","hr-note",tt("history_note", null, "Esto es lo que hizo para llegar aquí (lo último, arriba).")));
  }
}


const PAINT = {process: paintProcess, results: paintResults, summary: paintSummary,
               sources: paintSources, criteria: paintCriteria};

// Is this paint a NAVIGATION or a data refresh? It matters for scroll: "View detail →" lives at the end of a card, so
// without returning to top the record opens halfway down (and switching tabs left you mid-list). But a worker `append`
// while the operator is reading must NOT move the page. Compare only the sheet position —tab and page—, never content.
// WeakMap: if the card dies, this goes with it.
const WHERE = new WeakMap();
function navigated(el, data, cur){
  const now = [cur, data.view || "list", data.focus || ""].join("|");
  const was = WHERE.get(el);
  WHERE.set(el, now);
  return was !== undefined && was !== now;
}

// Counter painted on each tab. Only when it says something: a "0" on four tabs is noise, and a red number on Sources
// is exactly what draws attention ("3 sites did not let me in").
function tabCount(id, data){
  const c = data.counts || {}, s = data.summary || {};
  if(id === "results") return c.shown ? {n: c.shown} : null;
  if(id === "sources") return c.sources ? {n: c.sources, bad: !!c.sources_failed} : null;
  if(id === "criteria"){
    const crit=data.criteria||{};
    const n=CRIT_SECTIONS.reduce((a,x)=>a+((crit[x.key]||[]).length),0);
    return n ? {n} : null;
  }
  if(id === "summary") return s.explored ? {n: s.explored} : null;
  if(id === "process"){
    // With the task ALIVE, the tab shows a LOADER instead of a number (operator, 2026-08-20): when the first
    // result arrives, the sheet jumps automatically to the list, and from there the only thing saying "I am still working"
    // is this button — a phase counter cannot distinguish "it is at twelve" from "it got stuck at twelve". The number returns
    // when it finishes, which is when it DOES provide information: how many steps it took to get there. It spins via CSS
    // (`hr-spin`), never via a JS timer.
    const pr = data.progress || {};
    if(pr.alive) return {spin: true};
    const n = (pr.phases||[]).length;
    return n ? {n} : null;
  }
  return null;
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
let _T = null;
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.results."+key, params); if(s && s!=="widgets.results."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

function tabLabel(id){
  switch(id){
    case "process":  return tt("tab_process", null, "Proceso");
    case "results":  return tt("tab_results", null, "Resultados");
    case "summary":  return tt("tab_summary", null, "Sumario");
    case "sources":  return tt("tab_sources", null, "Fuentes");
    case "criteria": return tt("tab_criteria", null, "Criterios");
    default:         return id;
  }
}
function sourceLabel(status){
  switch(String(status || "")){
    case "partial": return tt("src_partial", null, "Entró con límite");
    case "auth":    return tt("src_auth", null, "Pedía autenticación");
    case "blocked": return tt("src_blocked", null, "Acceso bloqueado");
    case "error":   return tt("src_error", null, "Error");
    case "pending": return tt("src_pending", null, "En curso");
    default:        return tt("src_ok", null, "Entró");
  }
}
function critLabel(key){
  switch(key){
    case "hard":        return tt("crit_hard", null, "Criterios duros");
    case "soft":        return tt("crit_soft", null, "Preferencias");
    case "enrichments": return tt("crit_enrichments", null, "Añadido por criterio propio");
    case "assumed":     return tt("crit_assumed", null, "Datos asumidos");
    case "quality_bar": return tt("crit_quality_bar", null, "Baremo de calidad");
    case "changes":     return tt("crit_changes", null, "Tus correcciones");
    default:            return key;
  }
}
function critNote(key){
  switch(key){
    case "hard":        return tt("crit_hard_n", null, "incumplirlos descalifica");
    case "soft":        return tt("crit_soft_n", null, "puntúan, no descalifican");
    case "assumed":     return tt("crit_assumed_n", null, "no los dijiste — corrígelos si no van");
    case "quality_bar": return tt("crit_quality_bar_n", null, "qué hay que verificar de verdad");
    case "changes":     return tt("crit_changes_n", null, "lo que fuiste ajustando por el camino");
    default:            return "";
  }
}

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();
  data = data || {};
  el.className = "hb-results";
  el.textContent = "";

  // Title and tabs live together in a STICKY header: with several dozen results the sheet scrolls and tabs must stay
  // there (looking at the last card and jumping to Sources is a normal case).
  const top = elem("div","hr-top");
  // THE TITLE IS SAID ONCE. If the card already carries the TASK in its header (canvas marks it with
  // `data-host-title` when the manifest declares `live_title`), repeating it here in larger body text was the same
  // text twice 4px apart: noise, and one lost line of height in the most valuable part of the sheet. Own rendering is
  // kept as BACKUP: if this surface is ever mounted without the canvas header, the task cannot disappear.
  if(el.dataset.hostTitle !== "1"){
    top.appendChild(elem("div","hr-hd", data.title || "Resultados"));
  }
  if(data.subtitle){
    // The header is STICKY: every line it occupies is taken away from results throughout scrolling. A real subtitle
    // ("8 real listings from Levante (SUV, ~5.00 m long...), from coches.net and coches.com. Ordered by...") reached
    // three lines. Bound to TWO on screen and keep the full text in the tooltip: control space without losing data,
    // which is different from clipping it.
    const sub = elem("div","hr-sub clamp2", data.subtitle);
    sub.title = data.subtitle;
    top.appendChild(sub);
  }
  // The USER/SESSION identity strip is NOT here anymore (V2-538, operator with the screenshot in front of
  // him: "una línea que no necesito para nada" between the title and the tabs of every sheet). Auditing a
  // session is SUMMARY work, so the strip lives at the bottom of that tab — see paintSummary().

  // ACTIVE TAB — derived when the operator has not chosen one, yielding the two halves they requested:
  //   · the sheet opens in PROCESS while a task is alive and there is still nothing to put in the list;
  //   · as soon as the first result arrives, the derived value switches to "results" and the sheet JUMPS AUTOMATICALLY (C3).
  // If the operator clicked a tab, `data.tab` is persisted and RULES: the automatic jump cannot
  // pull them away from what they decided to look at.
  const _hasItems = ((data.items || []).length > 0);
  const _live = !!(data.progress && data.progress.alive);
  let cur = TABS.some(t=>t.id===data.tab) ? data.tab
          : (!_hasItems && (_live || ((data.progress||{}).phases||[]).length) ? "process" : "results");
  const bar = elem("div","hr-tabs");
  const panel = elem("div","hr-panel");

  const paint = (moved)=>{
    panel.textContent="";
    (PAINT[cur] || paintResults)(panel, data, ctx, nav);
    bar.querySelectorAll(".hr-tab").forEach(b=>b.classList.toggle("on", b.dataset.tab===cur));
    if(moved && ctx && ctx.top) ctx.top();
  };

  // LOCAL NAVIGATION between the list and a record. The page the operator is on is sheet state (so the brain
  // knows what he is looking at, and a reload or «vuelve a la lista» by voice agrees with the screen) — but it
  // does not have to travel to the server and back to be DRAWN: the item is already in `data`. This is the same
  // shape the tabs have used since V2-538, and its absence here is what made «Ver detalle» look like a dead
  // button for as long as the SSE id was wrong. `WHERE` sees the change too, so the record opens at the top
  // instead of halfway down the page the button was at the bottom of.
  function nav(view, focus, warn){
    if(view === "detail"){ data.view = "detail"; data.focus = focus || ""; data.viewWarn = warn || ""; }
    else { delete data.view; delete data.focus; delete data.viewWarn; }
    cur = "results";
    paint(navigated(el, data, cur));
  }

  TABS.forEach(t=>{
    const b=elem("button","hr-tab"); b.type="button"; b.dataset.tab=t.id;
    b.appendChild(document.createTextNode(tabLabel(t.id)));
    const c=tabCount(t.id, data);
    if(c && c.spin) b.appendChild(elem("span","hr-spin hr-tspin"));
    else if(c) b.appendChild(elem("span","hr-n"+(c.bad?" bad":""), String(c.n)));
    b.addEventListener("click", ()=>{
      if(cur===t.id) return;
      cur=t.id;
      // Paint IMMEDIATELY (the tab cannot blink while waiting for the server) and ALSO persist, because this sheet's
      // state does not live in the browser: this way the brain knows what the operator is looking at, and a reload or
      // "go back to results" by voice still matches the screen.
      paint(true);
      if(ctx && ctx.action) ctx.action("tab", {tab: t.id});
    });
    bar.appendChild(b);
  });

  top.appendChild(bar);
  el.append(top, panel);
  paint(navigated(el, data, cur));

  // V2-591 — a voice scroll request, applied ONCE per push (the token guards the re-render loop: every data
  // refresh re-runs render, and without it one order would scroll on every refresh of a live sheet). The
  // scroller is card chrome, so the widget only ASKS its host (ctx.scroll) — same ownership as ctx.top().
  const scReq = data.scroll;
  if(scReq && scReq.n && scReq.n !== el._hbScrollN && ctx && ctx.scroll){
    el._hbScrollN = scReq.n;
    try{ ctx.scroll(scReq.where || "down"); }catch(_){}
  }
}
