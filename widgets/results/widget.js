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

const TABS = [
  {id: "results",  label: "Resultados"},
  {id: "summary",  label: "Sumario"},
  {id: "sources",  label: "Fuentes"},
  {id: "criteria", label: "Criterios"},
];

// Source state → how it is phrased and colored. The vocabulary is closed in the backend; here it is only translated.
// The distinction matters: "could not enter" and "entered but was capped at 50" are VERY different outcomes.
const SOURCE_STATUS = {
  ok:      {label: "Entró",              cls: "ok"},
  partial: {label: "Entró con límite",   cls: "warn"},
  auth:    {label: "Pedía autenticación", cls: "warn"},
  blocked: {label: "Acceso bloqueado",   cls: "bad"},
  error:   {label: "Error",              cls: "bad"},
  pending: {label: "En curso",           cls: "idle"},
};

const CRIT_SECTIONS = [
  {key: "hard",        label: "Criterios duros",     note: "incumplirlos descalifica"},
  {key: "soft",        label: "Preferencias",        note: "puntúan, no descalifican"},
  {key: "enrichments", label: "Añadido por criterio propio", note: ""},
  {key: "assumed",     label: "Datos asumidos",      note: "no los dijiste — corrígelos si no van"},
  {key: "quality_bar", label: "Baremo de calidad",   note: "qué hay que verificar de verdad"},
  {key: "changes",     label: "Tus correcciones",    note: "lo que fuiste ajustando por el camino"},
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
    --f-lg:19px; --f-xl:23px;                                 /* expediente y cifras del sumario */
    --r-sm:7px; --r-md:10px; --r-lg:13px; --r-pill:99px;       /* radios */
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

  /* ── SESSION IDENTIFIERS (header) ───────────────────────────────────────────────────────────────────────────
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
  .hb-results .hr-img{display:block;width:100%;height:128px;object-fit:cover;border-radius:var(--r-md);
    margin:0 0 var(--s3);background:var(--hb-bubble,#f1f4f9)}
  .hb-results .hr-card.primary .hr-img{height:168px}
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
  .hb-results .hr-more{margin-top:var(--s3);display:inline-flex;align-items:center;gap:5px;font:600 var(--f-sm)/1 inherit;
    color:var(--hb-accent,#3D6FE0);background:none;border:var(--line);border-radius:var(--r-sm);
    padding:6px 10px;cursor:pointer;transition:.14s}
  .hb-results .hr-more:hover{border-color:var(--hb-accent,#3D6FE0);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 8%,transparent)}

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
  .hb-results .hr-gal img{width:100%;height:100px;object-fit:cover;border-radius:var(--r-md);
    background:var(--hb-bubble,#f1f4f9)}
  .hb-results .hr-sec{border:var(--line);border-radius:var(--r-lg);padding:var(--s3) var(--s4);
    margin-top:var(--s3);background:var(--hb-bg,#fff)}
  .hb-results .hr-sec .hr-pk{margin-bottom:var(--s1);display:inline-block}
  .hb-results .hr-sect{font-size:var(--f-md);font-weight:650;margin-top:2px;word-break:break-word}
  .hb-results .hr-link{display:inline-block;margin-top:var(--s2);font-size:var(--f-sm);font-weight:600;
    color:var(--hb-accent,#3D6FE0);text-decoration:none;word-break:break-all}
  .hb-results .hr-link:hover{text-decoration:underline}

  /* ── SUMARIO ── */
  .hb-results .hr-state{display:inline-flex;align-items:center;gap:var(--s2);font-size:var(--f-body);
    font-weight:600;margin-bottom:var(--s3)}
  .hb-results .hr-dot{width:7px;height:7px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:none}
  .hb-results .hr-dot.ok{background:var(--hb-ok,#1f9d55)}
  .hb-results .hr-dot.warn{background:var(--hb-warn,#c98a00)}
  .hb-results .hr-dot.bad{background:var(--hb-risk,#e5484d)}
  .hb-results .hr-dot.idle{background:var(--hb-accent,#3D6FE0);animation:hrpulse 1.8s ease-in-out infinite}
  @keyframes hrpulse{0%,100%{opacity:1}50%{opacity:.3}}
  .hb-results .hr-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:var(--s2);
    margin-bottom:var(--s4)}
  .hb-results .hr-stat{border:var(--line);border-radius:var(--r-md);padding:var(--s2) var(--s3) 9px;
    background:var(--hb-bg,#fff)}
  .hb-results .hr-stat b{display:block;font-size:var(--f-xl);line-height:1.1;font-weight:700;letter-spacing:-.02em;
    color:var(--hb-ink,#0d1622)}
  .hb-results .hr-stat span{display:block;margin-top:var(--s1);line-height:1.35;letter-spacing:.04em}
  .hb-results .hr-stat.dim b{color:var(--hb-muted-2,#9aa7b8)}
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

  /* ── FUENTES ── el punto de color da el veredicto antes de leer; el recuento va a la derecha, alineado. */
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

  /* ── CRITERIOS ── */
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
// Served by `GET /api/observability/identity` (open on loopback). Cached at module level: the header repaints on each
// data refresh and there is no point asking who I am every time.
let IDENT = null, IDENT_PROMISE = null;
function fetchIdentity(){
  if(IDENT) return Promise.resolve(IDENT);
  if(IDENT_PROMISE) return IDENT_PROMISE;
  IDENT_PROMISE = fetch("/api/observability/identity", {headers:{accept:"application/json"}})
    .then(r => r.ok ? r.json() : null)
    .then(j => { if(j){ IDENT = {user_id: String(j.user_id||""), session_id: String(j.session_id||"")}; } return IDENT; })
    .catch(() => null);
  return IDENT_PROMISE;
}

function shortId(id){
  id = String(id||"");
  return id.length > 13 ? id.slice(0,8) + "…" : (id || "—");
}

// Header strip: User · Session · Copy. The button copies BOTH FULL ids, in a format a code agent understands at a
// glance. It is painted immediately (with "...") and filled when fetch returns; if there is no identity (endpoint
// down), the strip removes itself instead of leaving an empty gap.
function identityStrip(){
  const strip = elem("div","hr-ident");
  const uBit = elem("span","hr-idbit"); const uCode = elem("code","","…"); uBit.append(elem("b","","Usuario"), uCode);
  const sBit = elem("span","hr-idbit"); const sCode = elem("code","","…"); sBit.append(elem("b","","Sesión"), sCode);
  const btn = elem("button","hr-idcopy","⧉ Copiar"); btn.type = "button"; btn.disabled = true;
  strip.append(uBit, sBit, btn);

  fetchIdentity().then(id => {
    if(!id){ strip.remove(); return; }
    uCode.textContent = shortId(id.user_id);  uBit.title = "Usuario: " + (id.user_id || "—");
    sCode.textContent = shortId(id.session_id); sBit.title = "Sesión: " + (id.session_id || "—");
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
      btn.textContent = ok ? "✓ Copiado" : "No se pudo copiar";
      btn.classList.toggle("ok", ok);
      if(reset) clearTimeout(reset);
      reset = setTimeout(() => { btn.textContent = "⧉ Copiar"; btn.classList.remove("ok"); }, 1800);
    });
  });
  return strip;
}

function photo(url, alt, cls){
  const img=document.createElement("img"); img.className=cls||"";
  img.src=url; img.alt=alt||""; img.loading="lazy"; img.referrerPolicy="no-referrer";
  img.addEventListener("error",()=>img.remove());   // dead photo link → drop silently, never break the card
  return img;
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
  box.appendChild(elem("div","hr-bt","Valoración"));
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
function gridStyle(items, cap){
  const rich = items.some(it => it && (
    (it.parts && it.parts.length) ||
    (it.blocks && it.blocks.length) ||
    (it.facts && it.facts.length > 3) ||
    (it.images && it.images.length) ||
    (it.lines && it.lines.length > 4)
  ));
  const medium = !rich && items.some(it => it && ((it.lines && it.lines.length) || it.image || it.facts));
  const min = rich ? 400 : medium ? 300 : 230;
  let maxCols = rich ? 2 : medium ? 3 : 4;
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
function makeCard(it, isPrimary, choose, ctx){
  const parts = Array.isArray(it.parts) ? it.parts : [];
  const blocks = Array.isArray(it.blocks) ? it.blocks : [];
  const hasDetail = parts.length || blocks.length || it.score
                    || (Array.isArray(it.images) && it.images.length)
                    || (Array.isArray(it.facts) && it.facts.length);
  // A composite card owns interactive children (per-piece links, "ver detalle") so it can't be an <a> — nesting
  // links/buttons inside an anchor is invalid and swallows their clicks into the outer navigation.
  const asLink = it.url && !hasDetail;
  const card = document.createElement(asLink ? "a" : "div");
  card.className = "hr-card" + (isPrimary ? " primary" : "");
  if(asLink){ card.href = it.url; card.target = "_blank"; card.rel = "noopener noreferrer"; }
  if(it.image) card.appendChild(photo(it.image, it.title, "hr-img"));
  const head = elem("div","hr-head");
  head.appendChild(elem("div","hr-t", it.title || ""));
  const sc = scoreTag(it.score); if(sc) head.appendChild(sc);
  if(it.price) head.appendChild(elem("div","hr-price", it.price));
  card.appendChild(head);
  // The BADGE goes with the title, not the footer. It is a label that QUALIFIES the result ("Best set"), and below it
  // ended up next to the detail button, where it read like a second button.
  const meta = elem("div","hr-metarow");
  if(it.subtitle) meta.appendChild(elem("span","hr-s", it.subtitle));
  if(it.badge) meta.appendChild(elem("span","hr-badge", it.badge));
  if(meta.childElementCount) card.appendChild(meta);
  // 80 lines (data.py's cap) so a full block of text — e.g. a song's lyrics — fits in one item's body, not just
  // a handful of spec-sheet bullets (2026-08-03). In the list they are bounded: the full block belongs to the record.
  (Array.isArray(it.lines) ? it.lines : []).slice(0, hasDetail ? 3 : 80)
    .forEach(l=>card.appendChild(elem("div","hr-ln", l)));

  const bl = renderBlocks(blocks, {compact: true}); if(bl) card.appendChild(bl);

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
    card.appendChild(box);
  }

  if(hasDetail && ctx){
    const btn=elem("button","hr-more","Ver detalle →"); btn.type="button";
    btn.addEventListener("click", async (e)=>{ e.preventDefault(); e.stopPropagation();
      await ctx.action("detail", { title: it.title || "" }); });
    card.appendChild(btn);
  }

  if(choose && !asLink){
    card.classList.add("choosable");
    const tagOf=()=>elem("span","hr-chosen-tag","✓ Elegido");
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
function renderDetail(panel, it, ctx){
  const back=elem("button","hr-back","← Volver a la lista"); back.type="button";
  back.addEventListener("click", async ()=>{ await ctx.action("list", {}); });
  panel.appendChild(back);

  panel.appendChild(elem("div","hr-dt", it.title||""));
  if(it.price) panel.appendChild(elem("div","hr-dprice", it.price));
  const dmeta = elem("div","hr-metarow");
  if(it.subtitle) dmeta.appendChild(elem("span","hr-s", it.subtitle));
  if(it.badge) dmeta.appendChild(elem("span","hr-badge", it.badge));
  if(dmeta.childElementCount) panel.appendChild(dmeta);

  // THE RATING goes ABOVE, before photos: it is the VERDICT. Below the gallery it read like one more datum at the end
  // of the record, when it is exactly what answers "why this one and not another?"
  const sb=scoreBlock(it.score);
  if(sb){ const sec=elem("div","hr-sec"); sec.appendChild(sb); panel.appendChild(sec); }

  const gallery = Array.isArray(it.images) && it.images.length ? it.images : (it.image ? [it.image] : []);
  if(gallery.length){
    const g=elem("div","hr-gal");
    gallery.forEach(u=>g.appendChild(photo(u, it.title, "")));
    panel.appendChild(g);
  }

  (Array.isArray(it.lines)?it.lines:[]).slice(0,80).forEach(l=>panel.appendChild(elem("div","hr-ln", l)));

  const ft=factsTable(it.facts); if(ft) panel.appendChild(ft);
  const bl=renderBlocks(it.blocks); if(bl) panel.appendChild(bl);

  if(it.url){
    const a=elem("a","hr-link", it.url);
    a.href=it.url; a.target="_blank"; a.rel="noopener noreferrer"; panel.appendChild(a);
  }

  (Array.isArray(it.parts)?it.parts:[]).forEach(p=>{
    const sec=elem("div","hr-sec");
    if(p.kind) sec.appendChild(elem("span","hr-pk", p.kind));
    sec.appendChild(elem("div","hr-sect", p.title||""));
    if(p.price) sec.appendChild(elem("div","hr-dprice", p.price));
    if(p.subtitle) sec.appendChild(elem("div","hr-s", p.subtitle));
    if(p.image) sec.appendChild(photo(p.image, p.title, "hr-img"));
    (Array.isArray(p.lines)?p.lines:[]).forEach(l=>sec.appendChild(elem("div","hr-ln", l)));
    const pf=factsTable(p.facts); if(pf) sec.appendChild(pf);
    if(p.url){
      const a=elem("a","hr-link", p.url);
      a.href=p.url; a.target="_blank"; a.rel="noopener noreferrer"; sec.appendChild(a);
    }
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
function paintResults(panel, data, ctx){
  const items = Array.isArray(data.items) ? data.items : [];

  if(data.view === "detail"){
    const it = findFocused(items, data.focus);
    if(it){ renderDetail(panel, it, ctx); return; }
    // focus pointing at nothing (list replaced under it) → fall through to the list, never a blank screen
  }

  const total = items.length;
  const all = items.slice(0, 24);
  if(!all.length){
    panel.appendChild(elem("div","hr-empty", data.note || "Sin resultados todavía."));
    return;
  }

  const primary = all.filter(it => it && it.primary);
  const rest = all.filter(it => !it || !it.primary);
  const choose = data.choosable ? { root: panel, ctx, chosenTitle: data.chosen } : null;

  // primary items: share the top row and decide width (one featured item occupies the whole sheet).
  if(primary.length){
    const pgrid = elem("div","hr-grid");
    pgrid.style.gridTemplateColumns = gridStyle(primary, primary.length === 1 ? 1 : 2);
    panel.appendChild(pgrid);
    primary.forEach(it => pgrid.appendChild(makeCard(it, true, choose, ctx)));
  }

  if(rest.length){
    const sgrid = elem("div","hr-grid");
    sgrid.style.gridTemplateColumns = gridStyle(rest, primary.length ? 2 : data.columns);
    panel.appendChild(sgrid);
    rest.forEach(it => sgrid.appendChild(makeCard(it, false, choose, ctx)));
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
      "Todavía no hay nada que resumir. Esta pestaña se llena mientras se trabaja: estado, cuántos candidatos se "
      + "han explorado y qué se ha ido haciendo."));
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
    box.appendChild(elem("span","", label));
    stats.appendChild(box);
  };
  const noBreadth = s.explored == null;
  add(noBreadth ? "—" : s.explored, noBreadth ? "sin reportar" : "explorados", noBreadth ? "dim" : "");
  add(c.shown || 0, "en pantalla");
  if(s.discarded != null) add(s.discarded, "descartados");
  if(c.sources) add(c.sources, "fuentes");
  // Problem sources go in their OWN cell and warning color. Stuffed into the "sources" label, they made a two-line
  // label ("SOURCES · 3 WITH / PROBLEM") that broke the row, and also hid the only datum here that asks the operator
  // for a decision inside another number's footer.
  if(c.sources_failed) add(c.sources_failed, "sin aprovechar", "warn");
  if(s.round && s.round > 1) add(s.round, "ronda");
  panel.appendChild(stats);

  if(s.note) panel.appendChild(elem("div","hr-why", s.note));

  if(Array.isArray(s.steps) && s.steps.length){
    panel.appendChild(elem("div","hr-cgt","Lo que se ha hecho"));
    const ul=elem("ul","hr-steps");
    s.steps.forEach(st=>ul.appendChild(elem("li","", st)));
    panel.appendChild(ul);
  }
}

// ── TAB 3 · SOURCES ─────────────────────────────────────────────────────────────────────────────────────────
// Where data comes from and WHAT happened at each site. This turns "I found nothing" into data that can be audited
// and corrected ("you enter that one, it asks for login").
function paintSources(panel, data){
  const src = Array.isArray(data.sources) ? data.sources : [];
  if(!src.length){
    panel.appendChild(elem("div","hr-empty",
      "Nadie ha reportado fuentes todavía. Aquí aparecerá cada web que se consulte y qué pasó en ella: si entró, "
      + "si le limitaron los resultados, si pedía autenticación o si dio error."));
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
    mid.appendChild(elem("div","hr-sst "+st.cls, st.label));
    if(s.detail) mid.appendChild(elem("div","hr-sd", s.detail));
    row.appendChild(mid);
    if(s.found != null){
      const n=elem("div","hr-sn"+(s.found ? "" : " zero"), String(s.found));
      n.appendChild(elem("small","", s.found === 1 ? "resultado" : "resultados"));
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
      "Todavía no hay criterios fijados. En cuanto se dirija una búsqueda aparecerán aquí el objetivo, los "
      + "requisitos que descalifican, las preferencias y lo que se haya dado por supuesto — y podrás corregirlos "
      + "hablando."));
    return;
  }
  if(c.goal) panel.appendChild(elem("div","hr-goal", c.goal));
  const meta=[];
  if(c.domain) meta.push(c.domain);
  if(c.min_candidates) meta.push(`amplitud mínima: ${c.min_candidates} candidatos`);
  if(c.n_final) meta.push(`entrega: ${c.n_final} finalistas`);
  if(meta.length) panel.appendChild(elem("div","hr-sub", meta.join(" · ")));

  CRIT_SECTIONS.forEach(sec=>{
    const list = c[sec.key];
    if(!Array.isArray(list) || !list.length) return;
    const grp=elem("div","hr-cgrp "+sec.key);
    const t=elem("div","hr-cgt", sec.label);
    if(sec.note){ t.appendChild(document.createTextNode(" ")); t.appendChild(elem("em","","— "+sec.note)); }
    grp.appendChild(t);
    const ul=elem("ul","hr-clist");
    list.forEach(x=>ul.appendChild(elem("li","", x)));
    grp.appendChild(ul);
    panel.appendChild(grp);
  });
}

const PAINT = {results: paintResults, summary: paintSummary, sources: paintSources, criteria: paintCriteria};

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
  return null;
}

export function render(el, data, ctx){
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
  // User/session identifiers + Copy: to pass them to an agent auditing this session.
  top.appendChild(identityStrip());

  let cur = TABS.some(t=>t.id===data.tab) ? data.tab : "results";
  const bar = elem("div","hr-tabs");
  const panel = elem("div","hr-panel");

  const paint = (moved)=>{
    panel.textContent="";
    (PAINT[cur] || paintResults)(panel, data, ctx);
    bar.querySelectorAll(".hr-tab").forEach(b=>b.classList.toggle("on", b.dataset.tab===cur));
    if(moved && ctx && ctx.top) ctx.top();
  };

  TABS.forEach(t=>{
    const b=elem("button","hr-tab"); b.type="button"; b.dataset.tab=t.id;
    b.appendChild(document.createTextNode(t.label));
    const c=tabCount(t.id, data);
    if(c) b.appendChild(elem("span","hr-n"+(c.bad?" bad":""), String(c.n)));
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
}
