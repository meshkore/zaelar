// youtube widget — stylesheet, first half: the box, header line, frame, tabs, bar, home head, search, queue.
// `CSS` is both halves in their original order (refactor2710-12 T-03).
import { CSS_PANELS } from "./style_panels.js";

const CSS_PLAYER = `
  /* ONE BOX (V2-717 applied here, 2026-09-29). The canvas window IS the frame: the root draws no border,
     radius, background or padding of its own, and it switches the host scroller's inset and scroll OFF so
     the bar sits flush under the window header and the content reaches the window's edges — operator:
     «un marco que tiene la ventana y dentro otro espacio como de premarco… lo único que conseguimos es
     perder espacio». The root fills the card (height:100%) and ONE inner region (.hb-yt-body) owns the
     scroll, so the bar never scrolls away. Width stays the card's (anchored, 2026-09-05). */
  .hb-scroll:has(> .hb-yt){overflow:hidden;padding:0}
  .hb-yt{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
         color:var(--hb-ink,#F2F4F7);width:100%;height:100%;min-height:0;box-sizing:border-box;
         display:flex;flex-direction:column}
  .hb-yt button,.hb-yt input{font-family:inherit}
  .hb-yt-body{flex:1 1 auto;min-height:0;overflow:auto;display:flex;flex-direction:column;gap:var(--sp-3,12px);
              padding:var(--sp-3,12px) var(--sp-4,16px) var(--sp-4,16px);box-sizing:border-box}
  /* V2-636 - ONE header line: title left (ellipsis), channel/date right. Saves a vertical row. */
  .hb-yt-tline{display:flex;align-items:baseline;gap:12px;min-width:0}
  .hb-yt-title{font-size:14px;font-weight:700;color:var(--hb-ink,#0d1622);line-height:1.3;
               white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1 1 auto;min-width:0}
  .hb-yt-meta{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.3;flex:0 1 auto;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-meta .hb-yt-latest{color:var(--hb-accent,#3D6FE0);font-weight:600}
  .hb-yt-blockmsg{font-size:12px;line-height:1.35;color:#8a5a00;background:rgba(240,170,20,.12);
    border:1px solid rgba(240,170,20,.35);border-radius:8px;padding:6px 9px;margin:2px 0 4px}
  .hb-yt-frame{position:relative;width:100%;aspect-ratio:16/9;border-radius:12px;overflow:hidden;
               background:#000;flex:0 0 auto}
  /* V2-638 - a library or torrent row plays in a plain <video>, filling the same frame the embed does so
     the player looks identical whatever the source. object-fit:contain letterboxes rather than crops: a
     film in the wrong aspect must not lose its edges. */
  .hb-yt-video{position:absolute;inset:0;width:100%;height:100%;background:#000;object-fit:contain}
  /* V2-636 - the PLAYER tab FILLS the card: the frame takes every spare pixel (YouTube letterboxes inside
     the iframe) and the control bar below stays pinned and visible at ANY card size - the operator grew the
     card and the buttons were CLIPPED under its bottom edge. Since the one-box pass the video also runs
     EDGE TO EDGE: no inset and no radius around it, the title and the controls carry their own gutter.
     connmode is excluded: the connector shelf is a list and must keep its scroll. */
  .hb-yt.hb-yt-t-player:not(.hb-yt-connmode) .hb-yt-body{overflow:hidden;padding:0;gap:0}
  .hb-yt.hb-yt-t-player:not(.hb-yt-connmode) .hb-yt-frame{flex:1 1 auto;min-height:140px;aspect-ratio:auto;
    border-radius:0}
  .hb-yt.hb-yt-t-player:not(.hb-yt-connmode) .hb-yt-tline{padding:var(--sp-2,8px) var(--sp-4,16px)}
  .hb-yt.hb-yt-t-player:not(.hb-yt-connmode) .hb-yt-blockmsg{margin:0 var(--sp-4,16px) var(--sp-2,8px)}
  .hb-yt.hb-yt-t-player:not(.hb-yt-connmode) .hb-yt-ctrls{margin:0;padding:var(--sp-2,8px) var(--sp-3,12px)}
  .hb-yt.hb-yt-t-player:not(.hb-yt-connmode) .hb-yt-hint{padding:0 var(--sp-4,16px) var(--sp-3,12px)}
  .hb-yt-frame iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
  .hb-yt-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
               color:var(--hb-muted-2,#9aa7b8);font-size:13px;text-align:center;padding:0 20px}
  .hb-yt-loading{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
                 justify-content:center;gap:10px;color:var(--hb-muted,#5b6b82);font-size:13px;text-align:center;
                 padding:0 20px}
  .hb-yt-spin{width:28px;height:28px;border-radius:50%;border:3px solid var(--hb-line,#eef1f6);
              border-top-color:var(--hb-accent,#3D6FE0);animation:hbytspin .8s linear infinite}
  @keyframes hbytspin{to{transform:rotate(360deg)}}
  .hb-yt-ctrls{display:flex;align-items:center;gap:6px;flex-wrap:nowrap;flex:0 0 auto;
               border-top:1px solid var(--hb-line,#eef1f6);padding-top:9px;margin-top:2px}
  .hb-yt-cbtn{border:0;background:none;color:var(--hb-ink,#0d1622);cursor:pointer;padding:8px;
              border-radius:9px;line-height:1;display:flex;flex:0 0 auto}
  .hb-yt-cbtn svg{width:17px;height:17px;display:block}
  .hb-yt-cbtn:hover{color:#f03;background:var(--hb-bg-soft,#fbfdff)}
  .hb-yt-cbtn.main{width:38px;height:38px;border-radius:50%;background:#f03;color:#fff;
                   align-items:center;justify-content:center;padding:0}
  .hb-yt-cbtn.main svg{width:16px;height:16px}
  .hb-yt-cbtn.main:hover{color:#fff;background:#f03;opacity:.88}
  .hb-yt-btn{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
             color:var(--hb-ink,#0d1622);border-radius:9px;padding:7px 12px;font-size:13px;font-weight:600;
             cursor:pointer;line-height:1}
  .hb-yt-btn:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-yt-vol{margin-left:auto;font-size:12px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums}
  .hb-yt-hint{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);line-height:1.35}
  .hb-yt-unmute{position:absolute;left:50%;bottom:10px;transform:translateX(-50%);display:none;
                align-items:center;gap:6px;background:rgba(0,0,0,.6);color:#fff;font-size:12.5px;
                font-weight:600;padding:6px 12px;border-radius:999px;cursor:pointer}
  .hb-yt-unmute:hover{background:rgba(0,0,0,.75)}
  /* No rule above the list: the bar's hairline already closes the band, and a second one drew a double line. */
  .hb-yt-list{display:flex;flex-direction:column;gap:2px}
  .hb-yt-listh{display:flex;align-items:center;gap:8px;font-size:var(--fs-ui,14px);font-weight:600;
               color:var(--hb-ink,#0d1622);padding-bottom:4px}
  .hb-yt-chip{font-size:11px;color:var(--hb-accent,#3D6FE0);border:1px solid var(--hb-line,#eef1f6);
              border-radius:999px;padding:1px 8px;display:inline-flex;align-items:center;gap:5px;cursor:pointer}
  .hb-yt-row{display:flex;align-items:center;gap:8px;padding:4px 6px;border-radius:8px;cursor:pointer;min-width:0}
  .hb-yt-row:hover{background:var(--hb-bg-soft,#fbfdff)}
  .hb-yt-row.playing .hb-yt-rowt{color:#f03;font-weight:700}
  .hb-yt-rown{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace;
              min-width:16px;text-align:right;flex:0 0 auto}
  .hb-yt-rowt{font-size:13px;color:var(--hb-ink,#0d1622);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
              flex:1;min-width:0}
  .hb-yt-rowc{font-size:11.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;
              text-overflow:ellipsis;max-width:32%;flex:0 1 auto}
  .hb-yt-rowx{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);font-size:14px;cursor:pointer;
              padding:1px 6px;border-radius:6px;line-height:1;flex:0 0 auto}
  .hb-yt-rowx:hover{color:var(--hb-risk,#e5484d)}
  .hb-yt-addrow{display:flex;gap:6px;margin-top:4px}
  .hb-yt-addinp{flex:1;min-width:0;box-sizing:border-box;border:1px solid var(--hb-line,#eef1f6);border-radius:8px;
                padding:6px 9px;font-size:12.5px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hb-yt-note{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);padding:1px 2px}
  /* HOME (V2-596): the catalog screen — a grid of the queue's videos with thumbnails, the closest thing to a
     YouTube home built from data WE hold (the connector-fed suggestions are the V2-596 initiative). It shows
     when nothing is loaded, and the nav button under the header switches home <-> player without unmounting
     the iframe (a video keeps playing while the operator browses; V2-092's stop still governs). Thumbnails are
     <img> ELEMENTS pointing at YouTube's public thumb host — the same class of resource as the player iframe,
     not a fetch from our JS. */
  /* TABS (V2-632): the operator's redesign — top tabs instead of the home<->player toggle. The bar is the
     ONE navigation surface; a tab click is a single state transition owned by selectTab (the V2-626 rule:
     it also clears the connectors screen, so no face can stay stuck underneath another). */
  /* THE ONE BAR (house standard, V2-715): the window header above already says «YouTube» with its mark,
     so the bar carries no brand of its own — view tabs on the left, then margin-left:auto and the source
     icons + the plug, pinned to the RIGHT edge (the red mark that used to lead the strip was that sentence
     said a second time). Flush under the window header, one hairline under it, never a box. */
  .hb-yt-nav{display:flex;align-items:center;gap:var(--sp-2,8px);flex:0 0 auto;min-width:0;box-sizing:border-box;
             padding:var(--sp-2,8px) var(--sp-3,12px);border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.09))}
  .hb-yt-tabs{display:flex;align-items:center;gap:2px;min-width:0;flex:0 1 auto;overflow-x:auto;scrollbar-width:none}
  .hb-yt-tabs::-webkit-scrollbar{display:none}
  .hb-yt-tab{border:0;background:none;color:var(--hb-muted,#A9B1BD);border-radius:999px;
             padding:6px 12px;font-size:var(--fs-caption,13.8px);font-weight:600;cursor:pointer;
             line-height:var(--hb-lh-tight,1.35);white-space:nowrap;flex:0 0 auto;
             transition:background var(--hb-t-fast,120ms),color var(--hb-t-fast,120ms)}
  .hb-yt-tab:hover{background:var(--hb-hover,rgba(255,255,255,.06));color:var(--hb-ink,#F2F4F7)}
  .hb-yt-tab:focus-visible,.hb-yt-plug:focus-visible,.hb-yt-picon:focus-visible{outline:none;
             box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  /* SELECTION is an accent-tinted chip with a ring and the label in ink at 700 (V2-690/691) — the one
     «this is the face on screen» shape of the whole product. The inverted white pill it replaces was a
     second filled language and the loudest thing on the card. */
  .hb-yt-tab.on{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);
                box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent);
                color:var(--hb-ink,#F2F4F7);font-weight:700}
  .hb-yt-navright{margin-left:auto;display:flex;align-items:center;gap:var(--sp-2,8px);flex:0 0 auto}
  /* The plug — the SAME control every connector widget wears (contactos' .ctplug): an icon, no word. */
  .hb-yt-plug{width:var(--hb-ctl-h-sm,32px);height:var(--hb-ctl-h-sm,32px);flex:0 0 auto;padding:0;
              border:1px solid var(--hb-line,rgba(255,255,255,.14));background:transparent;color:var(--hb-muted,#A9B1BD);
              border-radius:var(--hb-r-s,8px);cursor:pointer;display:flex;align-items:center;justify-content:center}
  .hb-yt-plug svg{width:15px;height:15px;display:block}
  .hb-yt-plug:hover,.hb-yt-plug.on{border-color:var(--hb-accent,#AE90FF);color:var(--hb-accent,#AE90FF)}
  /* INICIO's own head: what the grid below is, and a search box that carries the question on screen —
     so the card works by hand as well as by voice (operator, 2026-09-29). Built ONCE, outside the grid
     that is rebuilt per render, or an SSE repaint would eat what he is typing. */
  .hb-yt-homehead{display:none;align-items:center;gap:var(--sp-3,12px);flex-wrap:wrap;min-width:0}
  .hb-yt-hometitle{font-size:var(--fs-ui,14px);font-weight:600;color:var(--hb-ink,#F2F4F7);white-space:nowrap;
                   display:flex;align-items:center;gap:var(--sp-2,8px)}
  .hb-yt-homecount{font-weight:400;color:var(--hb-muted,#A9B1BD);font-variant-numeric:tabular-nums}
  .hb-yt-search{margin-left:auto;flex:1 1 220px;max-width:420px;min-width:0;display:flex;align-items:center;
                gap:var(--sp-2,8px);height:var(--hb-ctl-h-sm,32px);box-sizing:border-box;padding:0 4px 0 var(--sp-3,12px);
                border:1px solid var(--hb-line,rgba(255,255,255,.14));border-radius:999px;
                background:var(--hb-bg-soft,#272D35)}
  .hb-yt-search:focus-within{border-color:var(--hb-accent,#AE90FF)}
  .hb-yt-search input{flex:1 1 auto;min-width:0;border:0;outline:none;background:none;padding:0;
                      color:var(--hb-ink,#F2F4F7);font-size:var(--fs-caption,13.8px)}
  .hb-yt-search input::placeholder{color:var(--hb-muted,#A9B1BD)}
  .hb-yt-sbtn{width:26px;height:26px;flex:0 0 auto;border:0;border-radius:999px;background:none;padding:0;
              color:var(--hb-muted,#A9B1BD);cursor:pointer;display:flex;align-items:center;justify-content:center}
  .hb-yt-sbtn svg{width:15px;height:15px;display:block}
  .hb-yt-sbtn:hover{background:var(--hb-hover,rgba(255,255,255,.06));color:var(--hb-ink,#F2F4F7)}
  .hb-yt-sbtn:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-yt-sbtn.go{color:var(--hb-ink,#F2F4F7)}
  /* Placeholder (V2-632): with no video, the player tab still SHOWS where the video will live. */
  .hb-yt-empt-ico{font-size:34px;opacity:.5;line-height:1}
  /* Search band on the dashboard (V2-632): numbered result tiles + a per-tile «a la cola» button. */
  .hb-yt-schead{grid-column:1/-1;display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;
                color:var(--hb-ink,#0d1622)}
  .hb-yt-rnum{position:absolute;top:8px;left:8px;background:rgba(0,0,0,.62);color:#fff;font-size:11px;
              font-weight:700;border-radius:6px;padding:2px 6px;font-family:ui-monospace,Menlo,monospace}
  .hb-yt-radd{position:absolute;top:8px;right:8px;background:rgba(0,0,0,.55);color:#fff;border:0;
              border-radius:6px;font-size:11px;padding:2px 7px;cursor:pointer}
  .hb-yt-radd:hover{background:var(--hb-accent,#3D6FE0)}
  /* Queue rows carry a thumbnail now (V2-632): «que se intuya mejor de qué vídeo estamos hablando». */
  .hb-yt-rimg{width:62px;aspect-ratio:16/9;object-fit:cover;border-radius:6px;flex:0 0 auto;
              background:var(--hb-bg-soft,#0d1622)}
  /* Subscriptions and saved lists get their own tabs (V2-632). */
  .hb-yt-mylists{display:flex;flex-direction:column;gap:4px}
`;

export const CSS = CSS_PLAYER + CSS_PANELS;
