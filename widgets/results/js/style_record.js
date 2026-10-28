// results widget — the record half of the sheet's stylesheet (pieces, rating, blocks, data sheet, record, summary,
// loader…), joined after the chrome half by style.js (moved verbatim, refactor2710-12).
export const CSS_RECORD = `
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
