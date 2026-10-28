// archivos · the card's CSS, injected once by widget.js under its <style id> guard.

export const CSS = `
/* V2-764 — the TORRENTS section: a sub-tab bar, a cinema-style catalogue and the two live lists. */
.arx-pchip.tor.on{border-color:var(--hb-accent,#2f6df6)}
.arx-tabs{display:flex;gap:4px;padding:8px 12px 0;flex:0 0 auto}
.arx-tab{flex:0 0 auto;padding:6px 12px;border:0;border-radius:8px 8px 0 0;background:transparent;font:inherit;
  font-weight:700;color:var(--hb-muted-2,#9aa4b2);cursor:pointer;display:flex;align-items:center;gap:6px}
.arx-tab:hover{color:var(--hb-ink,#0d1622);background:var(--hb-bg-soft,#f5f7fb)}
.arx-tab.on{color:var(--hb-ink,#0d1622);background:var(--hb-bg-soft,#f5f7fb);box-shadow:inset 0 -2px 0 var(--hb-accent,#2f6df6)}
.arx-tab .arx-n{font-size:11px;font-weight:700;padding:0 6px;border-radius:999px;background:var(--hb-line,#eef1f6);color:var(--hb-muted,#67707d)}
.arx-cine{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.arx-film{display:flex;flex-direction:column;border:1px solid var(--hb-line,#eef1f6);border-radius:12px;overflow:hidden;
  background:var(--hb-bg-soft,#f5f7fb)}
.arx-poster{position:relative;aspect-ratio:16/9;display:grid;place-items:center;font-size:34px;
  background:linear-gradient(135deg,color-mix(in srgb,var(--hb-accent,#2f6df6) 26%,#111),#111)}
.arx-poster .arx-num{position:absolute;top:8px;left:8px;min-width:22px;height:22px;padding:0 6px;border-radius:999px;
  background:rgba(0,0,0,.6);color:#fff;font-size:12px;font-weight:800;display:grid;place-items:center}
.arx-poster .arx-res{position:absolute;top:8px;right:8px;padding:1px 7px;border-radius:6px;background:rgba(0,0,0,.6);
  color:#fff;font-size:11px;font-weight:800;letter-spacing:.03em}
.arx-film-b{display:flex;flex-direction:column;gap:6px;padding:10px}
.arx-film-t{font-weight:700;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.arx-film-m{display:flex;flex-wrap:wrap;gap:6px;color:var(--hb-muted,#67707d);font-size:12px}
.arx-film-m .seed{color:var(--hb-accent2,#12a594);font-weight:700}
.arx-dl{margin-top:2px;padding:7px 10px;border:0;border-radius:8px;background:var(--hb-accent,#2f6df6);color:#fff;
  font:inherit;font-weight:700;cursor:pointer}
.arx-dl:hover{filter:brightness(1.08)}
.arx-trow{display:flex;flex-direction:column;gap:6px;padding:10px 12px;border:1px solid var(--hb-line,#eef1f6);
  border-radius:10px;margin-bottom:8px}
.arx-trow-h{display:flex;align-items:center;gap:8px;min-width:0}
.arx-trow-t{flex:1 1 auto;min-width:0;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-tbar{height:6px;border-radius:999px;background:var(--hb-line,#eef1f6);overflow:hidden}
.arx-tbar>i{display:block;height:100%;background:var(--hb-accent,#2f6df6)}
.arx-trow-s{display:flex;flex-wrap:wrap;gap:10px;color:var(--hb-muted,#67707d);font-size:12px}
.arx-tnote{padding:18px 6px;color:var(--hb-muted,#67707d);text-align:center}

.arx{display:flex;flex-direction:column;width:100%;height:100%;min-height:0;box-sizing:border-box;
  position:relative;background:var(--hb-bg,#fff);border-radius:14px;overflow:hidden;
  font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial;color:var(--hb-ink,#0d1622)}
.arx-layout{display:flex;flex:1 1 auto;min-height:0}
.arx-main{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;min-height:0}
/* The SIDEBAR — a Finder/Explorer-style nav column. Only shown once the card is wide enough to hold it
   without squeezing the content area; see the tier system below, ensureTierObserver. */
.arx-side{flex:0 0 190px;display:none;flex-direction:column;gap:1px;padding:10px 6px;overflow:auto;
  border-right:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff)}
.arx[data-tier="l"] .arx-side{display:flex}
.arx-side-head{background:none;border:0;text-align:left;font:inherit;font-size:10.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.05em;color:var(--hb-muted-2,#9aa4b2);padding:9px 8px 4px;cursor:pointer}
.arx-side-head:hover{color:var(--hb-ink,#0d1622)}
.arx-side-item{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:8px;border:0;
  background:none;text-align:left;cursor:pointer;color:var(--hb-ink,#0d1622);font:inherit;width:100%}
.arx-side-item:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-side-item.on{background:color-mix(in srgb,var(--hb-accent,#2f6df6) 14%,transparent);
  color:var(--hb-accent,#2f6df6);font-weight:600}
.arx-side-item .arx-ic{width:18px;flex:0 0 auto;text-align:center;font-size:14px}
.arx-side-nm{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-side-count{flex:0 0 auto;color:var(--hb-muted-2,#9aa4b2);font-size:11px}
.arx-side-dot{width:7px;height:7px;border-radius:50%;background:var(--hb-muted-2,#9aa4b2);flex:0 0 auto}
.arx-side-dot.conn{background:var(--hb-accent2,#12a594)}
/* ONE header row — the storage chips, the breadcrumb and the tools live together so the chrome never reads
   as two half-empty bands with a void between them. */
.arx-bar{display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid var(--hb-line,#eef1f6);
  flex:0 0 auto;flex-wrap:wrap;row-gap:8px}
.arx-chips{display:flex;align-items:center;gap:6px;flex:0 0 auto}
.arx-pchip{width:32px;height:32px;border-radius:10px;border:1px solid var(--hb-line,#eef1f6);
  background:var(--hb-bg,#fff);display:grid;place-items:center;font-size:16px;line-height:1;
  font-weight:700;cursor:pointer;flex:0 0 auto;color:var(--hb-muted,#67707d);
  box-shadow:0 1px 2px rgba(0,0,0,.14);transition:transform .1s ease}
.arx-pchip:hover{background:var(--hb-bg-soft,#f5f7fb);transform:translateY(-1px)}
.arx-pchip.on{border-color:var(--hb-accent,#2f6df6);box-shadow:0 0 0 2px color-mix(in srgb,var(--hb-accent,#2f6df6) 30%,transparent);
  color:var(--hb-accent,#2f6df6)}
.arx-pchip.conn:not(.on){border-color:var(--hb-accent2,#12a594);color:var(--hb-accent2,#12a594)}
.arx-pchip.off{opacity:.5}
.arx-divider{width:1px;align-self:stretch;background:var(--hb-line,#eef1f6);flex:0 0 auto}
.arx-crumbs{display:flex;align-items:center;gap:4px;flex:1 1 180px;min-width:0;overflow:hidden;flex-wrap:nowrap}
.arx-crumb{background:none;border:0;padding:2px 6px;border-radius:6px;color:var(--hb-accent,#2f6df6);cursor:pointer;font:inherit;max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:0 1 auto}
.arx-crumb:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-crumb[disabled]{color:var(--hb-ink,#0d1622);cursor:default;font-weight:600}
.arx-crumb-more{max-width:none;padding:2px 8px;font-weight:700}
.arx-sep{color:var(--hb-muted-2,#9aa4b2);flex:0 0 auto}
.arx-tag{flex:0 0 auto;font-size:11.5px;color:var(--hb-muted,#67707d);background:var(--hb-bg-soft,#f5f7fb);
  border-radius:999px;padding:1px 8px;white-space:nowrap}
.arx-tools{display:flex;align-items:center;gap:6px;flex:0 0 auto}
.arx-find{display:flex;align-items:center;gap:4px;background:var(--hb-bg-soft,#f5f7fb);border:1px solid var(--hb-line,#eef1f6);border-radius:8px;padding:3px 6px}
.arx-find.active{border-color:var(--hb-accent,#2f6df6)}
/* A phone: the search takes a row of its own and the buttons line up under it (V2-813 — at 44px a tap the five
   buttons and the field could not share 366px, and the row broke wherever it ran out of room). */
@media (max-width:520px){.arx-tools{flex:1 1 100%;flex-wrap:wrap}.arx-find{order:-1;flex:1 1 100%}
  /* …the toolbar's glyphs read at a thumb's size inside their 44px boxes, and a file row puts its name on a line of
     its own — four 44px actions beside it left «Presu…» of a long name (V2-813). */
  .arx-btn{font-size:17px}
  .arx-row{flex-wrap:wrap;row-gap:2px}.arx-clickable{flex:1 1 100%}.arx-acts{margin-left:auto}}
.arx-find input{border:0;background:none;outline:none;font:inherit;color:var(--hb-ink,#0d1622);width:130px}
.arx-find-ic{color:var(--hb-muted,#67707d);font-size:13px}
.arx-find-count{flex:0 0 auto;font-size:11px;color:var(--hb-muted,#67707d);background:var(--hb-bg,#fff);
  border-radius:999px;padding:1px 6px}
.arx-find-x{border:0;background:none;color:var(--hb-muted,#67707d);cursor:pointer;font-size:13px;padding:0 2px;line-height:1}
.arx-find-x:hover{color:var(--hb-ink,#0d1622)}
.arx-btn{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);border-radius:8px;padding:3px 8px;cursor:pointer;font:inherit;line-height:1.6}
.arx-btn:hover{background:var(--hb-bg-soft,#f5f7fb)}
.arx-btn[disabled]{opacity:.4;cursor:default}
.arx-btn.on{border-color:var(--hb-accent,#2f6df6);color:var(--hb-accent,#2f6df6)}
.arx-btn.danger{color:var(--hb-risk,#d64545);border-color:var(--hb-risk,#d64545)}
/* The content PANEL — a visibly different surface from the chrome above it, so "where the files are" reads
   as one bounded area instead of bleeding into the rest of the card. */
.arx-body{flex:1 1 auto;min-height:0;overflow:auto;padding:12px;background:var(--hb-bg-soft,#f5f7fb)}
.arx-shelves{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.arx-shelf{display:flex;flex-direction:column;align-items:center;gap:8px;padding:20px 10px;
  border:1px solid var(--hb-line,#eef1f6);border-radius:14px;cursor:pointer;background:var(--hb-bg,#fff);
  box-shadow:0 1px 3px rgba(0,0,0,.12)}
.arx-shelf:hover{border-color:var(--hb-accent,#2f6df6);box-shadow:0 2px 8px rgba(0,0,0,.18)}
.arx-shelf .arx-ic{width:52px;height:52px;border-radius:16px;background:var(--hb-bg-soft,#f5f7fb);
  display:grid;place-items:center;font-size:26px;line-height:1}
.arx-shelf b{font-size:.85rem}
.arx-shelf span{color:var(--hb-muted,#67707d);font-size:.72rem}
.arx-row{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:9px;
  background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);margin-bottom:6px}
.arx-row:hover{border-color:var(--hb-accent,#2f6df6)}
.arx-row.sel{box-shadow:inset 3px 0 0 var(--hb-accent,#2f6df6)}
.arx-clickable{cursor:pointer;flex:1 1 auto;min-width:0;display:flex;align-items:center;gap:10px}
.arx-ic{flex:0 0 auto;font-size:17px;width:22px;text-align:center;line-height:1}
.arx-nm{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-meta{flex:0 0 auto;display:flex;align-items:center;color:var(--hb-muted,#67707d);font-size:11.5px;white-space:nowrap}
.arx-col-date{display:none}
.arx-col-loc{display:none;color:var(--hb-muted-2,#9aa4b2)}
.arx[data-tier="m"] .arx-col-date,.arx[data-tier="l"] .arx-col-date{display:inline}
.arx[data-tier="l"] .arx-col-loc{display:inline}
.arx-acts{display:flex;align-items:center;gap:3px;flex:0 0 auto}
.arx-ac{border:0;background:none;color:var(--hb-muted,#67707d);cursor:pointer;font-size:15px;padding:4px 5px;border-radius:6px;line-height:1}
.arx-ac:hover{background:var(--hb-bg-soft,#f5f7fb);color:var(--hb-ink,#0d1622)}
.arx-ac.danger:hover{color:var(--hb-risk,#d64545)}
.arx-rename{flex:1 1 auto;display:flex;gap:6px;min-width:0}
.arx-rename input{flex:1 1 auto;min-width:0;border:1px solid var(--hb-accent,#2f6df6);border-radius:6px;padding:3px 6px;font:inherit;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
.arx-confirm{display:flex;align-items:center;gap:6px;flex:0 1 auto;min-width:0;flex-wrap:wrap}
.arx-confirm span{color:var(--hb-risk,#d64545);font-size:11.5px;min-width:0;overflow-wrap:anywhere}
.arx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}
.arx-tile{display:flex;flex-direction:column;align-items:center;gap:5px;padding:12px 6px;
  border:1px solid var(--hb-line,#eef1f6);border-radius:12px;cursor:pointer;background:var(--hb-bg,#fff);
  box-shadow:0 1px 3px rgba(0,0,0,.12)}
.arx-tile:hover{border-color:var(--hb-accent,#2f6df6);box-shadow:0 2px 8px rgba(0,0,0,.18)}
.arx-tile img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px}
.arx-tile .arx-ic{font-size:26px;width:auto}
.arx-tile .arx-nm{width:100%;text-align:center;font-size:12px;white-space:normal;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.arx-note{padding:10px 12px;border-radius:10px;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);color:var(--hb-muted,#67707d);
  margin-bottom:10px;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.arx-path{background:var(--hb-bg-soft,#f5f7fb);border-radius:6px;padding:2px 6px;color:var(--hb-ink,#0d1622);
  word-break:break-all;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}
.arx-note.warn{background:var(--hb-warn-bg,#fff8e6);border-color:var(--hb-warn-border,#f5d78e);color:var(--hb-warn-ink,#7a5b00)}
.arx-note.bad{border-color:var(--hb-risk,#d64545);color:var(--hb-risk,#d64545)}
.arx-foot{flex:0 0 auto;border-top:1px solid var(--hb-line,#eef1f6);padding:8px 10px;display:flex;gap:10px;align-items:center}
.arx-foot .arx-nm{font-weight:600}
.arx-lb{position:absolute;inset:0;background:rgba(10,12,16,.96);display:flex;flex-direction:column;z-index:5;border-radius:14px}
.arx-lb-top{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;color:#fff;flex:0 0 auto}
.arx-lb-top b{font-size:.85rem;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.arx-lb-close{background:none;border:0;color:#fff;font-size:20px;cursor:pointer;padding:2px 8px;line-height:1}
.arx-lb-body{flex:1 1 auto;display:flex;align-items:center;justify-content:center;overflow:auto;padding:10px;min-height:0}
.arx-lb-body img{max-width:100%;max-height:100%;object-fit:contain;border-radius:6px}
.arx-lb-body iframe{width:100%;height:100%;border:0;border-radius:6px;background:#fff}
`;
