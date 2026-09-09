// youtube — REAL YouTube player embedded in the canvas (an <iframe>, not a capture). Controlled by VOICE: data.py
// stores the desired command (last_cmd + cmd_seq) and state (paused/muted/volume); here we apply it to the player
// with postMessage (YouTube IFrame API, NO external library — only iframe messages). Contract: render(el, data, ctx).
// No network from JS: the <iframe> is an element, not our own request.

function injectStyles(){
  if(document.getElementById("hb-yt-css")) return;
  const s = document.createElement("style"); s.id = "hb-yt-css"; s.textContent = `
  /* Fluid width, ANCHORED to the parent card (operator, 2026-09-05: «el contenido interior debe ir anclado
     al borde del widget, al contenedor parent»). The old width:min(680px,92vw) was content-sized: a
     maximized or hand-grown card kept the widget at 680px hugging the left edge with a dead area beside it.
     The CARD decides the width now (the default footprint moved to manifest.size); border-box or the
     padding+border would overflow the card by 30px. */
  .hb-yt{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
         width:100%;box-sizing:border-box;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);
         border-radius:16px;padding:14px;display:flex;flex-direction:column;gap:10px}
  .hb-yt-title{font-size:14px;font-weight:600;color:var(--hb-ink,#0d1622);line-height:1.3;
               white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-meta{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.3;margin-top:-4px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-meta .hb-yt-latest{color:var(--hb-accent,#3D6FE0);font-weight:600}
  .hb-yt-blockmsg{font-size:12px;line-height:1.35;color:#8a5a00;background:rgba(240,170,20,.12);
    border:1px solid rgba(240,170,20,.35);border-radius:8px;padding:6px 9px;margin:2px 0 4px}
  .hb-yt-frame{position:relative;width:100%;padding-top:56.25%;border-radius:12px;overflow:hidden;
               background:var(--hb-bg-soft,#0d1622)}
  .hb-yt-frame iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
  .hb-yt-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
               color:var(--hb-muted-2,#9aa7b8);font-size:13px;text-align:center;padding:0 20px}
  .hb-yt-loading{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
                 justify-content:center;gap:10px;color:var(--hb-muted,#5b6b82);font-size:13px;text-align:center;
                 padding:0 20px}
  .hb-yt-spin{width:28px;height:28px;border-radius:50%;border:3px solid var(--hb-line,#eef1f6);
              border-top-color:var(--hb-accent,#3D6FE0);animation:hbytspin .8s linear infinite}
  @keyframes hbytspin{to{transform:rotate(360deg)}}
  .hb-yt-ctrls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
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
  .hb-yt-list{display:flex;flex-direction:column;gap:2px;border-top:1px solid var(--hb-line,#eef1f6);padding-top:8px}
  .hb-yt-listh{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:var(--hb-ink,#0d1622)}
  .hb-yt-chip{font-size:11px;color:var(--hb-accent,#3D6FE0);border:1px solid var(--hb-line,#eef1f6);
              border-radius:999px;padding:1px 8px;display:inline-flex;align-items:center;gap:5px;cursor:pointer}
  .hb-yt-row{display:flex;align-items:center;gap:8px;padding:4px 6px;border-radius:8px;cursor:pointer;min-width:0}
  .hb-yt-row:hover{background:var(--hb-bg-soft,#fbfdff)}
  .hb-yt-row.playing .hb-yt-rowt{color:var(--hb-accent,#3D6FE0);font-weight:700}
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
  .hb-yt-nav{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
  .hb-yt-tab{border:1px solid transparent;background:none;color:var(--hb-muted,#5b6b82);border-radius:9px;
             padding:5px 10px;font-size:12.5px;font-weight:600;cursor:pointer;line-height:1;white-space:nowrap}
  .hb-yt-tab:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-yt-tab.on{background:var(--hb-bg-soft,#fbfdff);border-color:var(--hb-line,#eef1f6);
                color:var(--hb-ink,#0d1622)}
  .hb-yt-conbtn{margin-left:auto;border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
                border-radius:9px;padding:5px 9px;font-size:13px;cursor:pointer;line-height:1}
  .hb-yt-conbtn.active,.hb-yt-conbtn:hover{border-color:var(--hb-accent,#3D6FE0)}
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
  .hb-yt-subs,.hb-yt-mylists{display:flex;flex-direction:column;gap:4px}
  .hb-yt-secmsg{color:var(--hb-muted-2,#9aa7b8);font-size:12.5px;padding:14px 6px;text-align:center}
  .hb-yt-saverow{display:flex;gap:6px;margin-top:6px}
  /* Connector SHELF (V2-632): the messaging igrid visual language, local copy (V2-557 isolation). */
  .hb-yt-igrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:12px}
  .hb-yt-ibox{display:flex;flex-direction:column;align-items:center;gap:7px;padding:16px 10px;cursor:pointer;
              border:1px solid var(--hb-line,#eef1f6);border-radius:12px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-yt-ibox:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-yt-ibox.conn{border-color:var(--hb-accent2,#16B8A6)}
  .hb-yt-ibox.off{opacity:.5;cursor:default}
  .hb-yt-ibox.off:hover{border-color:var(--hb-line,#eef1f6)}
  .hb-yt-iicon{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;
               background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);font-weight:700;
               font-size:17px;color:var(--hb-muted,#5b6b82)}
  .hb-yt-iicon svg{width:24px;height:24px}
  .hb-yt-ilabel{font-size:13px;font-weight:600;color:var(--hb-ink,#0d1622)}
  .hb-yt-isub{font-size:11px;color:var(--hb-muted-2,#9aa7b8);text-align:center}
  .hb-yt-shnote{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.45;border:1px solid
                var(--hb-line,#eef1f6);border-radius:10px;padding:10px 12px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-yt-home{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
  .hb-yt-tile{position:relative;display:flex;flex-direction:column;gap:5px;cursor:pointer;border-radius:10px;padding:4px;min-width:0}
  .hb-yt-tilex{position:absolute;top:8px;right:8px;background:rgba(0,0,0,.5);color:#fff;border-radius:6px}
  .hb-yt-tile:hover{background:var(--hb-bg-soft,#fbfdff)}
  .hb-yt-tile img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;background:var(--hb-bg-soft,#0d1622)}
  .hb-yt-tilet{font-size:12.5px;font-weight:600;color:var(--hb-ink,#0d1622);line-height:1.25;
               display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .hb-yt-tile.playing .hb-yt-tilet{color:var(--hb-accent,#3D6FE0)}
  .hb-yt-tilec{font-size:11px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-homemsg{grid-column:1/-1;color:var(--hb-muted-2,#9aa7b8);font-size:13px;text-align:center;padding:26px 12px}
  .hb-yt-blocked{font-size:11px;color:var(--hb-muted-2,#9aa7b8);padding:2px 2px}
  /* ACCOUNT layer (V2-597): platform icons in the nav row — bright = connected (click: its status screen),
     dimmed = not connected (click: its step wizard). The messaging .dots pattern: every channel always
     visible, never hidden and never disabled. */
  .hb-yt-dots{display:flex;align-items:center;gap:8px;margin-left:auto}
  .hb-yt-picon{width:20px;height:20px;cursor:pointer;opacity:.35;flex:0 0 auto}
  .hb-yt-picon.on{opacity:1}
  .hb-yt-picon svg{width:100%;height:100%;display:block}
  /* Connect screens (V2-597): the step wizard / status card replaces the card faces while open. */
  .hb-yt-conn{display:flex;flex-direction:column;gap:10px}
  .hb-ytw-crumb{font-size:12px;color:var(--hb-accent,#3D6FE0);cursor:pointer;font-weight:600;
                align-self:flex-start}
  .hb-ytw-step{border:1px solid var(--hb-line,#eef1f6);border-radius:12px;padding:12px;
               display:flex;flex-direction:column;gap:8px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-ytw-head{display:flex;align-items:center;gap:8px}
  .hb-ytw-num{width:22px;height:22px;border-radius:50%;background:var(--hb-accent,#3D6FE0);color:#fff;
              display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;
              flex:0 0 auto}
  .hb-ytw-title{font-size:13.5px;font-weight:700;color:var(--hb-ink,#0d1622)}
  .hb-ytw-count{margin-left:auto;font-size:11px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-ytw-body{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.45;
               display:flex;flex-direction:column;gap:7px}
  .hb-ytw-body a{color:var(--hb-accent,#3D6FE0)}
  .hb-ytw-foot{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .hb-ytw-err{font-size:12px;color:var(--hb-risk,#e5484d);line-height:1.4}
  .hb-ytw-ok{font-size:12.5px;color:var(--hb-accent,#3D6FE0);font-weight:600}
  /* V2-603 — secondary actions under the primary button: the manual check (now a fallback, not the way the
     flow completes) and the escape hatch to one's own OAuth app. Links, not buttons: a second button next to
     «Conectar» reads as an equal choice, and neither of these is one. */
  .hb-ytw-alt{display:flex;gap:14px;flex-wrap:wrap;margin-top:2px}
  .hb-ytw-link{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);cursor:pointer;text-decoration:underline;
    text-underline-offset:2px;min-height:44px;display:inline-flex;align-items:center}
  .hb-ytw-link:hover{color:var(--hb-accent,#3D6FE0)}
  /* HOME suggestions band (V2-597): section header spanning the grid; tiles reuse .hb-yt-tile. */
  .hb-yt-sughead{grid-column:1/-1;display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;
                 color:var(--hb-ink,#0d1622);margin-top:2px}
  .hb-yt-sugsub{font-weight:400;color:var(--hb-muted-2,#9aa7b8)}
  /* V2-604 — the operator's OWN library, above everything that depends on a connector. */
  .hb-yt-lib{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:2px 0 6px}
  .hb-yt-libh{font-size:12px;font-weight:700;color:var(--hb-fg,#0f1720);margin-right:2px}
  .hb-yt-libp{grid-column:1/-1;font-size:11px;color:var(--hb-muted-2,#9aa7b8);padding:0 0 8px}
  .hb-yt-catch{grid-column:1/-1;border-top:1px solid var(--hb-line,#eef1f6);margin-top:4px}
  /* View switching is CLASS-driven, never inline display (an inline style would beat the cinema rules
     below). V2-632: one class per TAB — every face hidden by default, each tab shows its own with the
     right display value. Cinema and connmode are declared AFTER and win by order at equal specificity. */
  .hb-yt .hb-yt-blockmsg,
  .hb-yt .hb-yt-frame,.hb-yt .hb-yt-title,.hb-yt .hb-yt-meta,.hb-yt .hb-yt-ctrls,.hb-yt .hb-yt-hint,
  .hb-yt .hb-yt-list,.hb-yt .hb-yt-addrow,.hb-yt .hb-yt-home,.hb-yt .hb-yt-blocked,.hb-yt .hb-yt-subs,
  .hb-yt .hb-yt-mylists{display:none}
  .hb-yt.hb-yt-t-inicio .hb-yt-home{display:grid}
  .hb-yt.hb-yt-t-inicio .hb-yt-blocked{display:block}
  .hb-yt.hb-yt-t-player .hb-yt-frame{display:block}
  .hb-yt.hb-yt-t-player .hb-yt-blockmsg{display:block}
  .hb-yt.hb-yt-t-player .hb-yt-title,.hb-yt.hb-yt-t-player .hb-yt-meta,
  .hb-yt.hb-yt-t-player .hb-yt-hint{display:block}
  .hb-yt.hb-yt-t-player .hb-yt-ctrls{display:flex}
  .hb-yt.hb-yt-t-cola .hb-yt-list,.hb-yt.hb-yt-t-cola .hb-yt-addrow{display:flex}
  .hb-yt.hb-yt-t-subs .hb-yt-subs{display:flex}
  .hb-yt.hb-yt-t-listas .hb-yt-mylists{display:flex}
  /* Connect mode (the 🔌 screen) hides every tab face — declared AFTER the tab rules on purpose: equal
     specificity, so ORDER is what lets the shelf win over the active tab (measured: the queue rendered
     underneath the shelf when this block sat first). */
  .hb-yt.hb-yt-connmode .hb-yt-frame,.hb-yt.hb-yt-connmode .hb-yt-title,.hb-yt.hb-yt-connmode .hb-yt-meta,
  .hb-yt.hb-yt-connmode .hb-yt-ctrls,.hb-yt.hb-yt-connmode .hb-yt-hint,.hb-yt.hb-yt-connmode .hb-yt-list,
  .hb-yt.hb-yt-connmode .hb-yt-addrow,.hb-yt.hb-yt-connmode .hb-yt-home,.hb-yt.hb-yt-connmode .hb-yt-subs,
  .hb-yt.hb-yt-connmode .hb-yt-mylists,.hb-yt.hb-yt-connmode .hb-yt-blocked,
  .hb-yt.hb-yt-connmode .hb-yt-blockmsg{display:none}
  .hb-yt:not(.hb-yt-connmode) .hb-yt-conn{display:none}
  /* CINEMA (V2-596): inside a maximized/fullscreen card the video IS the screen — the frame fills the card and
     the card-shaped furniture (title, controls, hint, playlist, add row) disappears. Without this, a voice
     "maximize the video" grew the CARD while the player kept its 56% card ratio inside a black void. The host
     sets .hb-cinema on the card (desktop.js) and its floating exit button restores everything; the unmute pill
     stays, it is the one control the browser's autoplay policy makes necessary. */
  .hb-win.hb-cinema .hb-yt,.hb-win:fullscreen .hb-yt{width:100%;height:100%;max-width:none;padding:0;gap:0;
    border:0;border-radius:0;background:#000}
  .hb-win.hb-cinema .hb-yt-frame,.hb-win:fullscreen .hb-yt-frame{display:block;padding-top:0;flex:1 1 auto;
    min-height:0;border-radius:0}
  .hb-win.hb-cinema .hb-yt-title,.hb-win.hb-cinema .hb-yt-meta,.hb-win.hb-cinema .hb-yt-ctrls,
  .hb-win.hb-cinema .hb-yt-hint,.hb-win.hb-cinema .hb-yt-list,.hb-win.hb-cinema .hb-yt-addrow,
  .hb-win.hb-cinema .hb-yt-nav,.hb-win.hb-cinema .hb-yt-home,.hb-win.hb-cinema .hb-yt-blocked,
  .hb-win.hb-cinema .hb-yt-blockmsg,.hb-win:fullscreen .hb-yt-blockmsg,
  .hb-win.hb-cinema .hb-yt-conn,.hb-win.hb-cinema .hb-yt-subs,.hb-win.hb-cinema .hb-yt-mylists,
  .hb-win:fullscreen .hb-yt-title,.hb-win:fullscreen .hb-yt-meta,.hb-win:fullscreen .hb-yt-ctrls,
  .hb-win:fullscreen .hb-yt-hint,.hb-win:fullscreen .hb-yt-list,.hb-win:fullscreen .hb-yt-addrow,
  .hb-win:fullscreen .hb-yt-nav,.hb-win:fullscreen .hb-yt-home,.hb-win:fullscreen .hb-yt-blocked,
  .hb-win:fullscreen .hb-yt-conn,.hb-win:fullscreen .hb-yt-subs,.hb-win:fullscreen .hb-yt-mylists{display:none}
  /* Cinema: the video is the screen — the frame must show whatever tab was active. */
  .hb-win.hb-cinema .hb-yt-frame,.hb-win:fullscreen .hb-yt-frame{display:block}
  `; document.head.appendChild(s);
}

function el(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

// The playlist plays one after another because the PLAYER tells us the video ENDED (YouTube IFrame API over
// postMessage, `listening` handshake — same mechanism musica uses). The handler filters by the handshake `id`:
// both this widget and musica's hidden audio player listen on the same window, and without the filter one
// player's ending would advance the OTHER's queue.
let _ytEnded = null;
let _ytError = null;   // V2-401: the player refusing to play (onError) is reported back, never swallowed
let _ytQuality = null; // V2-604: the quality levels the video really HAS, reported back once per video
let _qSeen = "";       // last videoId whose levels were reported (infoDelivery repeats several times a second)
if(typeof window !== "undefined" && !window.__hbYtWidgetBound){
  window.__hbYtWidgetBound = true;
  window.addEventListener("message", (ev) => {
    if(typeof ev.data !== "string" || ev.data.indexOf("\"event\"") < 0) return;
    let d; try{ d = JSON.parse(ev.data); }catch(_){ return; }
    if(d.id !== "hb-youtube") return;
    if(d.event === "onStateChange" && Number(d.info) === 0 && _ytEnded) _ytEnded();   // 0 = ENDED
    // onError codes: 2 bad id · 5 HTML5 error · 100 removed · 101/150 embedding disabled by the owner.
    // Without this, "This video is unavailable" on screen coexisted with a declared state that said
    // playing — and /widgets/producing, the brain and the judge all believed the declared state (V2-401).
    if(d.event === "onError" && _ytError) _ytError(d.info);
    // V2-604 — the definition of the video. The results page does not publish it (measured: only 4K carries
    // a badge at all), so the player is the ONLY honest source, and this is the only moment it exists. Read
    // from the `infoDelivery` the player already sends because we asked to listen; reported ONCE per video,
    // because that stream repeats several times a second and each report is a store write.
    if(d.event === "infoDelivery" && d.info && d.info.availableQualityLevels && _ytQuality){
      const vid = String(d.info.videoData && d.info.videoData.video_id || "");
      const key = vid || "current";
      if(key !== _qSeen){ _qSeen = key; _ytQuality(d.info.availableQualityLevels, vid); }
    }
  });
}
function startListening(iframe){
  try{ iframe.contentWindow.postMessage(JSON.stringify({event:"listening", id:"hb-youtube", channel:"widget"}), "*"); }catch(_){}
}

function post(iframe, func, args){
  try{
    if(!iframe || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage(JSON.stringify({event:"command", func:func, args:args||[]}), "*");
  }catch(_){}
}

// ── ACCOUNT layer (V2-597) ────────────────────────────────────────────────────────────────────────────────
// Module-lived screen state (the module loads once, so it survives re-renders — the messaging pattern):
// null = normal faces · {view:"wizard"|"status", platform} = a platform's connect/status screen.
let _screen = null;
// V2-632 — the active TAB. Module-lived like _screen; "" = derive from data at build (video → player,
// none → inicio). selectTab is the ONLY writer and also clears _screen (the V2-626 rule: choosing a surface
// is ONE state transition — a connectors screen left open would silently sit on top of the chosen tab).
let _tab = "";
const _TABS = [["inicio", "⌂ Inicio"], ["player", "▶ Reproductor"], ["cola", "≡ Cola"],
               ["subs", "★ Suscripciones"], ["listas", "≣ Listas"]];
function applyTabClass(root){
  _TABS.forEach(([id]) => root.classList.toggle("hb-yt-t-" + id, _tab === id));
}
const _wizStep = {};        // platform -> current wizard step (1..2)
let _connUrl = "";          // consent URL to offer as a link when the pop-up was blocked
let _focusDone = 0;         // last honoured connect_focus ts (consumed once per timestamp)
let _syncAsked = 0;         // last time this card asked for a platform re-sync (guards against loops)
let _connBusy = false;      // a connect/check round-trip is running (buttons disabled meanwhile)
let _connErr = "";          // an error of THIS screen's own attempt — never a stale stored one (V2-582)

// Brand mark, inline SVG (simple-icons outline path, CC0) — never a CDN: widget.js touches no network.
const _BRAND = {
  youtube: {color: "#FF0000", path: "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 " +
    "12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 " +
    "3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 " +
    "2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"},
};

function brandIcon(pid, on){
  const wrap = el("span", "hb-yt-picon" + (on ? " on" : ""));
  const b = _BRAND[pid] || null;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", b ? b.path : "M12 2a10 10 0 1 0 0 20a10 10 0 0 0 0-20z");
  path.setAttribute("fill", b ? b.color : "currentColor");
  svg.appendChild(path);
  wrap.appendChild(svg);
  return wrap;
}

function fmtAge(ts){
  if(!ts) return "";
  const m = Math.max(0, Math.round((Date.now() / 1000 - Number(ts)) / 60));
  if(m < 1) return "ahora mismo";
  if(m < 60) return "hace " + m + " min";
  return "hace " + Math.round(m / 60) + " h";
}

function stepBox(n, total, title){
  const box = el("div", "hb-ytw-step");
  const head = el("div", "hb-ytw-head");
  head.appendChild(el("span", "hb-ytw-num", String(n)));
  head.appendChild(el("span", "hb-ytw-title", title));
  if(total > 1) head.appendChild(el("span", "hb-ytw-count", "Paso " + n + " de " + total));
  box.appendChild(head);
  return box;
}

// The connect screens (V2-597): a step WIZARD for a platform that is not connected — one step visible at a
// time, the middle one being work done elsewhere (the ⚙ panel holds the credentials; V2-520: nothing here
// carries one) — and a STATUS screen with disconnect for one that is. Rebuilt on every render, like the list.
function renderConn(E, root, data, ctx){
  const box = E.conn;
  if(!box) return;
  
  root.classList.toggle("hb-yt-connmode", !!_screen);
  box.textContent = "";
  if(!_screen) return;
  const pid = _screen.platform || "youtube";
  const rows = Array.isArray(data.platforms) ? data.platforms : [];
  const row = rows.find((r) => r.id === pid)
              || {id: pid, label: "YouTube", connected: false, app_configured: false};
  const repaint = () => renderConn(E, root, data, ctx);

  const back = () => {
    if(_screen && _screen.view !== "shelf"){ _screen = {view: "shelf"}; _connErr = ""; repaint(); return; }
    if(root._hbYtSelectTab) root._hbYtSelectTab(_tab || "inicio");
    else { _screen = null; repaint(); }
  };
  const crumb = el("div", "hb-ytw-crumb",
                   (_screen && _screen.view !== "shelf") ? "‹ Fuentes de vídeo" : "‹ Volver");
  crumb.addEventListener("click", back);
  box.appendChild(crumb);

  // THE SHELF (V2-632): every video source, live or not, with its honest state — the messaging igrid
  // language. YouTube disabled says WHY (INI-032: no OAuth client yet); a planned provider says it is not
  // built. Nothing here pretends: a box that cannot open never wears an active face.
  if(_screen.view === "shelf"){
    const grid = el("div", "hb-yt-igrid");
    const shelf = Array.isArray(data.connector_shelf) && data.connector_shelf.length
      ? data.connector_shelf
      : [{id: "youtube", label: "YouTube", state: "planned", connected: false, note: ""}];
    const enabled = !!data.accounts_enabled;
    shelf.forEach((rw) => {
      const usable = rw.id === "youtube" && enabled;
      const bx = el("button", "hb-yt-ibox" + (rw.connected ? " conn" : "") + (usable ? "" : " off"));
      const ic = el("span", "hb-yt-iicon");
      if(_BRAND[rw.id]){
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", _BRAND[rw.id].path);
        path.setAttribute("fill", _BRAND[rw.id].color);
        svg.appendChild(path); ic.appendChild(svg);
      } else {
        ic.textContent = (rw.label || rw.id || "?").slice(0, 1).toUpperCase();
      }
      bx.appendChild(ic);
      bx.appendChild(el("span", "hb-yt-ilabel", rw.label || rw.id));
      bx.appendChild(el("span", "hb-yt-isub",
        rw.connected ? "Conectada"
          : usable ? "Sin conectar — toca para conectarla"
          : rw.state === "not-possible" ? "No es posible"
          : "No disponible aún"));
      bx.addEventListener("click", () => {
        if(usable){
          _screen = {view: rw.connected ? "status" : "wizard", platform: rw.id};
          if(!_wizStep[rw.id]) _wizStep[rw.id] = 1;
          _connErr = ""; repaint(); return;
        }
        _connErr = (rw.label || rw.id) + ": " + (rw.note ||
          (rw.id === "youtube"
            ? "de momento no es posible conectar la cuenta — falta registrar el cliente OAuth."
            : "todavía no está construido."));
        repaint();
      });
      grid.appendChild(bx);
    });
    box.appendChild(grid);
    if(_connErr) box.appendChild(el("div", "hb-yt-shnote", _connErr));
    return;
  }

  const act = async (name, payload) => {
    if(!ctx || !ctx.action) return null;
    _connBusy = true; repaint();
    let r = null;
    try { r = await ctx.action(name, payload || {}); } catch(_e){ r = null; }
    _connBusy = false;
    return r;
  };
  const btn = (label, cls) => {
    const b = el("button", "hb-yt-btn", label);
    if(cls) b.classList.add(cls);
    b.disabled = _connBusy;
    return b;
  };

  if(row.connected && _screen.view !== "wizard"){
    const st = stepBox("✓", 1, (row.label || "YouTube") + " conectado");
    const body = el("div", "hb-ytw-body");
    body.appendChild(el("div", "", "Cuenta conectada en modo solo lectura: las sugerencias del inicio "
                                   + "salen de tus suscripciones. Tu cuenta no se toca."));
    st.appendChild(body);
    const foot = el("div", "hb-ytw-foot");
    const sug = btn("↻ Traer sugerencias");
    sug.addEventListener("click", async () => {
      const r = await act("suggest", {platform: pid});
      if(r && r.ok){
        _connErr = "";
        if(root._hbYtSelectTab) root._hbYtSelectTab("inicio");   // the band lives on the dashboard — go look
        else { _screen = null; repaint(); }
      } else { _connErr = (r && (r.message || r.error)) || "No pude traer sugerencias."; repaint(); }
    });
    foot.appendChild(sug);
    const dis = btn("Desconectar");
    dis.addEventListener("click", async () => { await act("disconnect_account", {platform: pid}); repaint(); });
    foot.appendChild(dis);
    st.appendChild(foot);
    if(_connErr) st.appendChild(el("div", "hb-ytw-err", _connErr));
    box.appendChild(st);
    return;
  }

  // WIZARD (V2-603). Its SHAPE depends on whose OAuth app this install uses, because that is the whole
  // difference between one click and an afternoon:
  //
  //   builtin_app: true  → ONE step. The operator gives consent and nothing else.
  //   builtin_app: false → the bring-your-own-app road, still two steps, but the first one now OPENS the
  //                        settings panel on the right tab instead of telling him to go find it.
  //
  // What is deliberately NOT here: a client_id field. Two invariants forbid it — `widget.js` never touches
  // the network (V2-557) and a widget data-op never carries a credential (V2-520) — so the credential is
  // typed in ⚙ → Conectores, which is the one surface allowed to hold it. The fix for the old dead-end was
  // never to move the field; it was to stop making the operator navigate there on his own.
  //
  // And there is no mandatory «comprobar» any more: the OAuth callback lands on our own server, refreshes
  // this widget's store and the card repaints over SSE. The manual check survives only as a quiet fallback
  // for the case where that push never arrives.
  const builtin = !!row.builtin_app;
  const total = builtin ? 1 : 2;
  let step = Math.min(Math.max(_wizStep[pid] || 1, 1), total);
  if(builtin) step = 1;
  _wizStep[pid] = step;

  // Opening the consent. The window is opened SYNCHRONOUSLY on the click or the browser blocks it (the
  // archivos pattern) — and when it IS blocked (a phone, a strict desktop policy) the URL is shown as a
  // link the operator can tap instead of the flow dying with no explanation. That degradation is why this
  // needs no environment detection: one path that works on a self-hosted desktop, in the cloud and on the
  // PWA beats three that each need their own testing.
  const startConsent = async () => {
    const w = window.open("", "_blank");
    const r = await act("connect_account", {platform: pid});
    if(r && r.ok && r.url){
      _connErr = "";
      if(w){ w.location = r.url; _connUrl = ""; }
      else { _connUrl = r.url; }                  // pop-up blocked → offer the link
    } else {
      if(w){ try{ w.close(); }catch(_e){} }
      _connUrl = "";
      _connErr = (r && (r.message || r.error)) || "No pude empezar la conexión.";
    }
    repaint();
  };

  let sb;
  if(!builtin && step === 1){
    sb = stepBox(1, total, "Registra una app OAuth de Google");
    const body = el("div", "hb-ytw-body");
    body.appendChild(el("div", "", "Esta instalación todavía no trae una app de Google propia, así que hace "
                                   + "falta la tuya: se registra UNA vez y sirve también para Drive y Fotos."));
    body.appendChild(row.app_configured
      ? el("div", "hb-ytw-ok", "✓ App registrada — puedes continuar.")
      : el("div", "", "Las credenciales se guardan en Configuración; por esta tarjeta nunca viajan."));
    sb.appendChild(body);
    const foot = el("div", "hb-ytw-foot");
    const go = btn("Abrir Configuración → Conectores");
    go.addEventListener("click", () => {
      // The card cannot import the app's store, so it asks for the panel the way every widget talks to the
      // host: a DOM event (the `hb:` convention desktop.js and the rail already use).
      try{ document.dispatchEvent(new CustomEvent("hb:open-config", {detail: {tab: "conectores"}})); }catch(_e){}
    });
    foot.appendChild(go);
    const next = btn("Ya está — continuar");
    next.addEventListener("click", async () => {
      const r = await act("sync_platforms", {});
      const fresh = r && Array.isArray(r.platforms) ? r.platforms.find((x) => x.id === pid) : null;
      if(fresh && fresh.app_configured){ _wizStep[pid] = 2; _connErr = ""; }
      else { _connErr = "Aún no veo el client_id — guárdalo en ⚙ → Conectores y vuelve a intentarlo."; }
      repaint();
    });
    foot.appendChild(next);
    sb.appendChild(foot);
  } else {
    sb = stepBox(builtin ? 1 : 2, total, "Autoriza tu cuenta de YouTube");
    const body = el("div", "hb-ytw-body");
    body.appendChild(el("div", "", "Se abrirá la ventana de Google para que des permiso de SOLO LECTURA a tus "
                                   + "suscripciones. Zaelar no puede tocar tu cuenta."));
    body.appendChild(el("div", "", "En cuanto termines, esta tarjeta se actualiza sola."));
    sb.appendChild(body);
    const foot = el("div", "hb-ytw-foot");
    if(!builtin){
      const back = btn("‹ Anterior");
      back.addEventListener("click", () => { _wizStep[pid] = 1; _connErr = ""; _connUrl = ""; repaint(); });
      foot.appendChild(back);
    }
    const go = btn(_connBusy ? "Conectando…" : "Conectar " + (row.label || "YouTube"), "bt-primary");
    go.addEventListener("click", startConsent);
    foot.appendChild(go);
    sb.appendChild(foot);
    if(_connUrl){
      // The pop-up never opened. Say so plainly and hand over the link — silence here reads as a dead button.
      const blocked = el("div", "hb-ytw-body");
      blocked.appendChild(el("div", "", "Tu navegador bloqueó la ventana. Abre este enlace para autorizar:"));
      const a = document.createElement("a");
      a.href = _connUrl; a.target = "_blank"; a.rel = "noopener";
      a.textContent = "Abrir la autorización de Google";
      blocked.appendChild(a);
      sb.appendChild(blocked);
    }
    const alt = el("div", "hb-ytw-alt");
    const chk = el("span", "hb-ytw-link", "¿No se ha actualizado? Comprobar ahora");
    chk.addEventListener("click", async () => {
      const r = await act("sync_platforms", {});
      const fresh = r && Array.isArray(r.platforms) ? r.platforms.find((x) => x.id === pid) : null;
      if(fresh && fresh.connected){ _screen = {view: "status", platform: pid}; _connErr = ""; _connUrl = ""; }
      else { _connErr = "Todavía no veo la cuenta conectada — termina la ventana de Google."; }
      repaint();
    });
    alt.appendChild(chk);
    if(builtin){
      const own = el("span", "hb-ytw-link", "Usar mi propia app OAuth");
      own.addEventListener("click", () => {
        try{ document.dispatchEvent(new CustomEvent("hb:open-config", {detail: {tab: "conectores"}})); }catch(_e){}
      });
      alt.appendChild(own);
    }
    sb.appendChild(alt);
  }
  if(_connErr) sb.appendChild(el("div", "hb-ytw-err", _connErr));
  box.appendChild(sb);
}

// Is the agent STOPPED? (V2-092) — with ⏻ off, this widget must NOT play anything. The case that made this necessary
// is MOUNT: the operator stopped the agent, RELOADED the page, and the video started again by itself, because the
// <iframe> is born with `autoplay=1` and nobody had told it the agent was stopped. `ctx.running` is a live canvas
// getter (widgets/desktop.js) reflecting server truth (nucleo/runstate.py).
// Read as "stopped ONLY if explicitly stated": an old ctx without the field (undefined) must not leave the player
// muted forever.
function halted(ctx){ return !!(ctx && ctx.running === false); }

// Reassert desired state in the player (idempotent) — used when loading a new video.
function applyState(iframe, data, ctx){
  if(data.muted){ post(iframe, "mute", []); }
  else { post(iframe, "unMute", []); post(iframe, "setVolume", [Number(data.volume != null ? data.volume : 70)]); }
  // Captions re-asserted HERE, not only in applyCmd, or the choice silently drops on the next `load` (V2-590).
  applyCaptions(iframe, data);
  // With the agent stopped, ALWAYS pause, whatever saved state says: this is the last line of defense in case the
  // store kept `paused:false` from before stop (or from an older engine version).
  if(data.paused || halted(ctx)) post(iframe, "pauseVideo", []);
  else post(iframe, "playVideo", []);
}

// Captions on/off (V2-590): both module names are sent — "captions" is the HTML5 player's, "cc" the
// historical one — and the player ignores the one it does not know. No track is picked: the player's own
// default/auto track is what a viewer gets clicking CC, and guessing a language here would override it.
function applyCaptions(iframe, data){
  if(data.captions){ post(iframe, "loadModule", ["captions"]); post(iframe, "loadModule", ["cc"]); }
  else { post(iframe, "unloadModule", ["captions"]); post(iframe, "unloadModule", ["cc"]); }
}

// Apply the LAST command requested by voice/click (only when cmd_seq advances).
function applyCmd(iframe, data, ctx){
  const c = data.last_cmd || "";
  // A command that would make the video play is ignored while the agent is stopped. The server already rejects them
  // in the funnel (widgets/producers.py::gate), so this only covers already saved state — but pausing too much never
  // hurts, while playing too much does.
  if(halted(ctx) && (c === "play" || c === "load" || c === "restart" || c === "unmute"
                     || c === "volume_up" || c === "set_volume"
                     || c === "next" || c === "previous" || c === "play_item")){
    post(iframe, "pauseVideo", []);
    return;
  }
  const vol = Number(data.volume != null ? data.volume : 70);
  if(c === "play") post(iframe, "playVideo", []);
  else if(c === "pause") post(iframe, "pauseVideo", []);
  else if(c === "mute") post(iframe, "mute", []);
  else if(c === "unmute"){ post(iframe, "unMute", []); post(iframe, "setVolume", [vol]); }
  else if(c === "volume_up" || c === "volume_down" || c === "set_volume"){
    post(iframe, "unMute", []); post(iframe, "setVolume", [vol]);
  }
  else if(c === "captions_on" || c === "captions_off"){ applyCaptions(iframe, data); }
  else if(c === "restart"){ post(iframe, "seekTo", [0, true]); post(iframe, "playVideo", []); }
  // A queue jump normally lands as a NEW videoId (card rebuild); when the target is the SAME video (a list
  // with the current one repeated after a manual load) nothing rebuilds — treat it as a restart.
  else if(c === "next" || c === "previous" || c === "play_item"){
    post(iframe, "seekTo", [0, true]); post(iframe, "playVideo", []);
  }
}

export function render(root, data, ctx){
  injectStyles();
  data = data || {};
  const id = data.videoId || "";
  const seq = Number(data.cmd_seq || 0);
  const loading = !!data.loading;
  const st = root._hbYt || null;

  // (Re)build the card when the video changes, or when entering/leaving "searching" state (real bug 2026-07-23:
  // without this the card looked COMPLETELY empty while load searched YouTube, with no signal).
  if(!st || st.id !== id || st.loading !== loading || !root._hbYtBuilt){
    root.className = "hb-yt";
    root.textContent = "";
    // HOME vs PLAYER (V2-596): with no video loaded the card IS the home catalog; with one, the nav button
    // under the card header switches views WITHOUT unmounting the iframe (audio keeps playing while browsing —
    // remounting would cut it, the same reason the mobile Deck hides instead of unmounting).
    if(id) root.classList.add("hb-yt-hasvid");
    // V2-632 — default tab: a video on screen means the player; nothing loaded means the dashboard. A tab the
    // operator already chose this page-life survives the rebuild (module-lived, like _screen) — EXCEPT that a
    // video ARRIVING on a card that had none jumps to the player: «ponme el vídeo de X» means watching it,
    // and leaving the dashboard up while it plays underneath is the confusion the redesign exists to end.
    if(!_tab) _tab = id ? "player" : "inicio";
    if(id && st && !st.id && !loading) _tab = "player";
    applyTabClass(root);

    const nav = el("div", "hb-yt-nav");
    const tabBtns = {};
    const selectTab = (tid) => {
      _tab = tid;
      _screen = null; _connErr = "";                       // choosing a tab is ONE transition (V2-626)
      applyTabClass(root);
      Object.keys(tabBtns).forEach((k) => tabBtns[k].classList.toggle("on", k === _tab));
      const cb = root.querySelector(".hb-yt-conbtn"); if(cb) cb.classList.remove("active");
      root.classList.remove("hb-yt-connmode");
      const connBox = root._hbYtEls && root._hbYtEls.conn; if(connBox) connBox.textContent = "";
      if(ctx && ctx.top) ctx.top();
    };
    _TABS.forEach(([tid, label]) => {
      const b = el("button", "hb-yt-tab" + (tid === _tab ? " on" : ""), label);
      b.dataset.tab = tid;
      b.addEventListener("click", () => selectTab(tid));
      tabBtns[tid] = b;
      nav.appendChild(b);
    });
    root._hbYtSelectTab = selectTab;
    root._hbYtTabBtns = tabBtns;
    // Platform icons (V2-597) + the connectors button (V2-632, the messaging 🔌 pattern) at the bar's right.
    const dots = el("div", "hb-yt-dots");
    nav.appendChild(dots);
    const connBtn = el("button", "hb-yt-conbtn", "🔌");
    connBtn.title = "Fuentes de vídeo / conectores";
    connBtn.addEventListener("click", () => {
      if(_screen){ selectTab(_tab); return; }              // toggle off → back to the active tab
      _screen = {view: "shelf"}; _connErr = "";
      connBtn.classList.add("active");
      renderConn(root._hbYtEls || {}, root, root._hbYtData || {}, ctx);
    });
    nav.appendChild(connBtn);
    root.appendChild(nav);

    const title = el("div", "hb-yt-title", data.title || "YouTube");
    root.appendChild(title);
    // V2-634 — the playback-block banner: when the owner refuses embedding, the card SAYS what happened
    // (a swap of our own pick, or the honest «only on YouTube» for a pasted link) instead of leaving the
    // operator alone with the player's raw error screen. Filled per render from data.blocked_notice.
    const blockMsg = el("div", "hb-yt-blockmsg", "");
    root.appendChild(blockMsg);
    const meta = el("div", "hb-yt-meta", "");            // channel · publication date (verifiable, V2-057)
    root.appendChild(meta);

    const frame = el("div", "hb-yt-frame");
    let iframe = null;
    let unmuteHint = null;
    if(loading){
      const box = el("div", "hb-yt-loading");
      box.appendChild(el("div", "hb-yt-spin"));
      box.appendChild(el("div", "", data.loading_query ? `Buscando «${data.loading_query}»…` : "Buscando…"));
      frame.appendChild(box);
    } else if(id){
      iframe = document.createElement("iframe");
      iframe.title = data.title || "YouTube";
      iframe.allow = "autoplay; encrypted-media; fullscreen; picture-in-picture";
      iframe.setAttribute("allowfullscreen", "");
      // `autoplay` ONLY if the agent is running and the video was not paused. It used to be fixed to 1: when reloading
      // with the agent stopped, the video started BEFORE any pause command arrived (the 700ms below) — the start was
      // audible. Removing it from the `src` itself is the only way to avoid playing EVEN FOR AN INSTANT.
      const auto = (!data.paused && !halted(ctx)) ? 1 : 0;
      // cc_load_policy only when captions are wanted: the param covers the LOAD case robustly (a module
      // loaded before the player is ready can be ignored); the live toggle goes through applyCaptions.
      const cc = data.captions ? "&cc_load_policy=1" : "";
      const params = "enablejsapi=1&rel=0&modestbranding=1&playsinline=1&autoplay=" + auto + "&mute=1" + cc
                     + "&origin=" + encodeURIComponent(location.origin);
      iframe.src = "https://www.youtube.com/embed/" + encodeURIComponent(id) + "?" + params;
      const d0 = data, c0 = ctx;
      iframe.addEventListener("load", function(){
        startListening(iframe);
        setTimeout(function(){ applyState(iframe, d0, c0); }, 700);
      });
      frame.appendChild(iframe);
      // The browser requires a real TOUCH to give sound to an autoplay that started muted (voice-requested "unmute"
      // does not count as a user gesture and audio may stay silently blocked). This button is a real click → unlock
      // audio NOW, in the same gesture.
      unmuteHint = el("div", "hb-yt-unmute", "");
      unmuteHint.appendChild(el("span", "", "🔊"));
      unmuteHint.appendChild(el("span", "", "Toca para activar el sonido"));
      frame.appendChild(unmuteHint);
    }
    else {
      // V2-632 — the PLACEHOLDER: with no video the player tab still shows WHERE the video will live
      // (operator: «que se vea que ese es el lugar donde eso se va a representar»).
      const ph = el("div", "hb-yt-empty");
      const inner = el("div", "");
      inner.appendChild(el("div", "hb-yt-empt-ico", "▶"));
      inner.appendChild(el("div", "", "Sin vídeo — di «pon el vídeo de…» o busca desde Inicio."));
      ph.appendChild(inner);
      frame.appendChild(ph);
    }
    root.appendChild(frame);

    const home = el("div", "hb-yt-home");             // populated on every render, like the list below
    root.appendChild(home);
    const blockedLine = el("div", "hb-yt-blocked", "");
    root.appendChild(blockedLine);
    const conn = el("div", "hb-yt-conn");             // connect screens (V2-597), rebuilt per render
    root.appendChild(conn);

    // Click controls (mirror of what can also be requested by voice).
    const ctrls = el("div", "hb-yt-ctrls");
    const btn = (label, action) => {
      const b = el("button", "hb-yt-btn", label);
      b.addEventListener("click", () => { if(ctx && ctx.action) ctx.action(action); });
      return b;
    };
    ctrls.appendChild(btn("▶︎ Play", "play"));
    ctrls.appendChild(btn("❚❚ Pausa", "pause"));
    ctrls.appendChild(btn("🔉 −", "volume_down"));
    ctrls.appendChild(btn("🔊 +", "volume_up"));
    const muteBtn = el("button", "hb-yt-btn", "🔇 Silencio");   // action/label are set on each render (toggle)
    ctrls.appendChild(muteBtn);
    const vol = el("div", "hb-yt-vol", "");
    ctrls.appendChild(vol);
    root.appendChild(ctrls);

    root.appendChild(el("div", "hb-yt-hint",
      "Por voz: «pon el vídeo de…», «búscame vídeos de…» (salen en Inicio), «reproduce el tercero», "
      + "«siguiente», «pausa», «sigue a este canal»."));

    // The QUEUE (V2-366; V2-632 gives every row a thumbnail — «que se intuya mejor de qué vídeo hablamos»).
    const listBox = el("div", "hb-yt-list");
    root.appendChild(listBox);
    const subsBox = el("div", "hb-yt-subs");             // V2-632: followed authors, OUR references
    root.appendChild(subsBox);
    const listsBox = el("div", "hb-yt-mylists");         // V2-632: saved lists
    root.appendChild(listsBox);
    const addRow = el("div", "hb-yt-addrow");
    const addInp = el("input", "hb-yt-addinp");
    addInp.placeholder = "Pega un enlace de YouTube o escribe un título…";
    const addBtn = el("button", "hb-yt-btn", "＋ Añadir");
    const doAdd = () => {
      const v = (addInp.value || "").trim();
      if(!v || !ctx || !ctx.action) return;
      addInp.value = "";
      ctx.action("add", {url: v});                       // the server tries link/id first, then searches by name
    };
    addBtn.addEventListener("click", doAdd);
    addInp.addEventListener("keydown", (e) => { if(e.key === "Enter") doAdd(); });
    addRow.appendChild(addInp); addRow.appendChild(addBtn);
    root.appendChild(addRow);

    root._hbYt = { id: id, seq: seq, loading: loading };   // "load" is already covered by new src → do not re-post as command
    root._hbYtBuilt = true;
    root._hbYtEls = { iframe: iframe, title: title, meta: meta, blockMsg: blockMsg, vol: vol, muteBtn: muteBtn, unmuteHint: unmuteHint,
                      listBox: listBox, home: home, blockedLine: blockedLine, dots: dots, conn: conn,
                      subsBox: subsBox, listsBox: listsBox };
  }

  // Dynamic refresh on EVERY render (title, verifiable metadata, mute-toggle button, volume).
  const E = root._hbYtEls || {};
  root._hbYtData = data;
  // Tab chrome per render: the Cola tab wears its count, the active tab wears .on (V2-632).
  if(root._hbYtTabBtns){
    const nQ = Array.isArray(data.list) ? data.list.length : 0;
    if(root._hbYtTabBtns.cola) root._hbYtTabBtns.cola.textContent = nQ ? ("≡ Cola · " + nQ) : "≡ Cola";
    Object.keys(root._hbYtTabBtns).forEach((k) => root._hbYtTabBtns[k].classList.toggle("on", k === _tab));
  }

  // ACCOUNT layer (V2-597) — the card asks for ONE platform re-sync when the cache is stale (the archivos
  // needs_refresh pattern; local file reads server-side, no provider network), consumes the voice door's
  // connect_focus once per timestamp, paints the platform icons and the connect screens.
  // V2-603 F2 — the account layer is HIDDEN whole while no OAuth client exists anywhere (operator's
  // directive, 2026-09-06: «until that is done I do not want the connector active, leave it deactivated and
  // hidden»). Not a disabled button and not a wizard that dead-ends: no platform row, no connect screen, and
  // no `sync_platforms` chatter either. The player itself is untouched — searching, playing and lists never
  // depended on an account. `accounts_enabled` is DERIVED server-side, so this whole surface comes back on
  // its own the day a client id exists.
  if(!data.accounts_enabled){
    if(E.dots){ E.dots.textContent = ""; E.dots.style.display = "none"; }
    // V2-632: the SHELF survives the gate — the operator asked to SEE the sources, disabled and honest
    // (INI-032's note included). Only the wizard/status views die with the flip: a door that cannot open.
    if(_screen && _screen.view !== "shelf") _screen = null;
    renderConn(E, root, data, ctx);
  } else {
  if(E.dots) E.dots.style.display = "";
  if(data.platforms_stale && ctx && ctx.action && Date.now() - _syncAsked > 60000){
    _syncAsked = Date.now();
    try{ ctx.action("sync_platforms", {}); }catch(_e){}
  }
  const _focus = data.connect_focus || null;
  if(_focus && Number(_focus.ts || 0) > _focusDone){
    _focusDone = Number(_focus.ts || 0);
    const pid = _focus.platform || "youtube";
    const row = (Array.isArray(data.platforms) ? data.platforms : []).find((r) => r.id === pid);
    _screen = {view: (row && row.connected) ? "status" : "wizard", platform: pid};
    if(!_wizStep[pid]) _wizStep[pid] = 1;
    _connErr = "";
  }
  if(E.dots){
    E.dots.textContent = "";
    const rows = Array.isArray(data.platforms) ? data.platforms : [];
    const list = rows.length ? rows : [{id: "youtube", label: "YouTube", connected: false, app_configured: false}];
    list.forEach((r) => {
      const ic = brandIcon(r.id, !!r.connected);
      ic.title = (r.label || r.id) + (r.connected ? ": cuenta conectada"
                                                  : ": sin conectar — toca para conectarla");
      ic.addEventListener("click", () => {
        _screen = {view: r.connected ? "status" : "wizard", platform: r.id};
        if(!_wizStep[r.id]) _wizStep[r.id] = 1;
        _connErr = "";
        renderConn(E, root, data, ctx);
      });
      E.dots.appendChild(ic);
    });
  }
  renderConn(E, root, data, ctx);
  }
  if(E.title) E.title.textContent = data.title || (id ? "YouTube" : "Sin vídeo");
  if(E.blockMsg){
    const bn = data.blocked_notice || {};
    const tt = (key, params, fb) => {
      try{
        if(ctx && typeof ctx.t === "function"){
          const s = ctx.t(key, params);
          if(s && s !== key) return s;
        }
      }catch(_){}
      let s = fb;
      if(params) for(const k in params) s = s.split("{" + k + "}").join(String(params[k]));
      return s;
    };
    let msg = "";
    if(bn.kind === "swapped")
      msg = tt("widgets.youtube.blocked_swapped", {from: bn.from || "", to: bn.to || ""},
               "«{from}» está bloqueado por su propietario para reproducirse aquí — pongo el siguiente: «{to}».");
    else if(bn.kind === "explicit")
      msg = tt("widgets.youtube.blocked_explicit", {from: bn.from || ""},
               "Su propietario bloquea la reproducción fuera de YouTube — este vídeo solo puede verse allí.");
    else if(bn.kind === "exhausted")
      msg = tt("widgets.youtube.blocked_exhausted", {from: bn.from || ""},
               "«{from}» está bloqueado por su propietario y no encontré sustituto — dime otra búsqueda.");
    E.blockMsg.textContent = msg;
    E.blockMsg.style.display = msg ? "" : "none";
  }
  if(E.meta){
    const bits = [];
    if(data.channel) bits.push(data.channel);
    if(data.published) bits.push((data.latest ? "más reciente · " : "") + data.published);
    E.meta.textContent = bits.join("  ·  ");
    E.meta.style.display = bits.length ? "" : "none";
  }
  const vol0 = Number(data.volume != null ? data.volume : 70);
  if(E.muteBtn){
    E.muteBtn.textContent = data.muted ? "🔊 Sonido" : "🔇 Silencio";
    E.muteBtn.onclick = () => {
      // Direct `post` (does not go through the server: it is the REAL click that unlocks browser audio) is also gated
      // — otherwise, with the agent stopped, this button would make the video play through the back door.
      if(data.muted && !halted(ctx)){ post(E.iframe, "unMute", []); post(E.iframe, "setVolume", [vol0]); }
      if(ctx && ctx.action) ctx.action(data.muted ? "unmute" : "mute");
    };
  }
  if(E.unmuteHint){
    E.unmuteHint.style.display = data.muted ? "flex" : "none";
    E.unmuteHint.onclick = () => {
      if(!halted(ctx)){ post(E.iframe, "unMute", []); post(E.iframe, "setVolume", [vol0]); }
      if(ctx && ctx.action) ctx.action("unmute");
    };
  }
  if(E.vol) E.vol.textContent = data.muted ? "silencio" : ("vol " + (data.volume != null ? data.volume : 70));

  // The queue advances because the player told us the video ended — refreshed every render so the callback
  // always carries the CURRENT ctx. Gated on halted: a stopped agent starts no playback (V2-092).
  _ytEnded = () => { if(ctx && ctx.action && !halted(ctx)) ctx.action("ended"); };
  // V2-634: the report names WHICH video failed — the store swaps the current one for the next playable
  // candidate, and a late onError for an already-replaced video must not be attributed to its successor.
  _ytError = (code) => { if(ctx && ctx.action) ctx.action("player_error",
      {code: String(code == null ? "unknown" : code), videoId: id || ""}); };
  _ytQuality = (levels, vid) => {
    if(ctx && ctx.action) ctx.action("player_quality", {levels: Array.isArray(levels) ? levels : [], videoId: vid || ""});
  };

  // The list rows, re-rendered on every render (text only; the iframe is never touched by this).
  if(E.listBox){
    E.listBox.textContent = "";
    const lst = Array.isArray(data.list) ? data.list : [];
    const filt = String(data.list_filter || "").trim().toLowerCase();
    // V2-467 — the list NAME takes precedence over the generic label: if the operator called it “the afternoon
    // one,” that is what must be shown on the card so they can verify at a glance that their request was followed.
    const _nom = String(data.list_name || "").trim();
    const _rot = _nom || "Lista";
    const head = el("div", "hb-yt-listh", lst.length ? (_rot + " · " + lst.length) : _rot);
    if(filt){
      const chip = el("span", "hb-yt-chip", "filtro: «" + filt + "» ✕");
      chip.title = "Quitar el filtro";
      chip.addEventListener("click", () => { if(ctx && ctx.action) ctx.action("filter_list", {q: ""}); });
      head.appendChild(chip);
    }
    E.listBox.appendChild(head);
    if(data.adding) E.listBox.appendChild(el("div", "hb-yt-note", "Buscando «" + data.adding + "»…"));
    const pos = Number(data.pos != null ? data.pos : -1);
    let shown = 0;
    lst.forEach((it, i) => {
      const hay = ((it.title || "") + " " + (it.channel || "")).toLowerCase();
      if(filt && hay.indexOf(filt) < 0) return;
      shown++;
      const row = el("div", "hb-yt-row" + (i === pos ? " playing" : ""));
      row.appendChild(el("span", "hb-yt-rown", i === pos ? "▶" : String(i + 1)));
      const th = document.createElement("img");                     // V2-632: the queue shows its faces
      th.className = "hb-yt-rimg"; th.loading = "lazy"; th.alt = "";
      if(it.videoId) th.src = "https://i.ytimg.com/vi/" + encodeURIComponent(it.videoId) + "/mqdefault.jpg";
      row.appendChild(th);
      row.appendChild(el("span", "hb-yt-rowt", it.title || it.url || "—"));
      if(it.channel) row.appendChild(el("span", "hb-yt-rowc", it.channel));
      const x = el("button", "hb-yt-rowx", "✕");
      x.title = "Quitar de la lista";
      x.addEventListener("click", (e) => { e.stopPropagation(); if(ctx && ctx.action) ctx.action("remove", {item: String(i + 1)}); });
      row.appendChild(x);
      row.addEventListener("click", () => {
        if(ctx && ctx.action) ctx.action("play_item", {item: String(i + 1)});
        if(root._hbYtSelectTab) root._hbYtSelectTab("player");
      });
      E.listBox.appendChild(row);
    });
    if(lst.length && filt && !shown) E.listBox.appendChild(el("div", "hb-yt-note", "Nada en la lista casa con el filtro."));
    if(!lst.length) E.listBox.appendChild(el("div", "hb-yt-note", "La lista está vacía: pega un enlace o dime «añade a la lista…»."));
  }

  // DASHBOARD (V2-596 → V2-632): the Inicio tab. Order is the operator's: the SEARCH band on top when a
  // search is live (numbered — «reproduce el tercero» steers by voice), then what he watched recently, then
  // the suggestions band (account-fed), then the enforced preferences line. The queue moved to its own tab.
  // Text + <img> elements only; the thumb host is YouTube's public CDN, never a fetch from our JS.
  if(E.home){
    E.home.textContent = "";
    const mkTile = (it, extras) => {
      const tile = el("div", "hb-yt-tile");
      const img = document.createElement("img");
      img.loading = "lazy"; img.alt = "";
      if(it.videoId) img.src = "https://i.ytimg.com/vi/" + encodeURIComponent(it.videoId) + "/mqdefault.jpg";
      tile.appendChild(img);
      (extras || []).forEach((x) => tile.appendChild(x));
      tile.appendChild(el("div", "hb-yt-tilet", it.title || "—"));
      if(it.channel) tile.appendChild(el("div", "hb-yt-tilec", it.channel));
      return tile;
    };
    const goPlayer = () => { if(root._hbYtSelectTab) root._hbYtSelectTab("player"); };

    // 1 — SEARCH RESULTS (V2-632): the dashboard's top band. Numbered so voice and eye share one index.
    const res = Array.isArray(data.search_results) ? data.search_results : [];
    if(data.adding){
      const sh = el("div", "hb-yt-schead");
      sh.appendChild(el("span", "", "Buscando «" + data.adding + "»…"));
      E.home.appendChild(sh);
    }
    if(res.length){
      const sh = el("div", "hb-yt-schead");
      sh.appendChild(el("span", "", "Resultados: «" + (data.search_query || "") + "»"));
      const clr = el("span", "hb-yt-chip", "✕ quitar");
      clr.title = "Quitar los resultados de búsqueda";
      clr.addEventListener("click", () => { if(ctx && ctx.action) ctx.action("clear_search", {}); });
      sh.appendChild(clr);
      E.home.appendChild(sh);
      res.forEach((it, i) => {
        const addB = el("button", "hb-yt-radd", "+ cola");
        addB.title = "Añadir a la cola sin reproducir";
        addB.addEventListener("click", (e) => {
          e.stopPropagation();
          if(ctx && ctx.action) ctx.action("add_results", {items: String(i + 1)});
        });
        const tile = mkTile(it, [el("span", "hb-yt-rnum", String(i + 1)), addB]);
        tile.addEventListener("click", () => {
          if(ctx && ctx.action) ctx.action("play_result", {item: String(i + 1)});
          goPlayer();
        });
        E.home.appendChild(tile);
      });
      E.home.appendChild(el("div", "hb-yt-catch"));
    }

    // 2 — RECENTLY WATCHED: the library's history is ours (V2-604); the dashboard shows the last few.
    const hist = Array.isArray(data.history) ? data.history : [];
    if(hist.length){
      const hh = el("div", "hb-yt-schead");
      hh.appendChild(el("span", "", "Vistos hace poco"));
      const all = el("span", "hb-yt-chip", "⏱ todo el historial → cola");
      all.title = "Carga el historial completo en la cola";
      all.addEventListener("click", () => {
        if(ctx && ctx.action) ctx.action("show_history", {});
        if(root._hbYtSelectTab) root._hbYtSelectTab("cola");
      });
      hh.appendChild(all);
      E.home.appendChild(hh);
      hist.slice(0, 6).forEach((h) => {
        const tile = mkTile(h);
        tile.addEventListener("click", () => {
          if(ctx && ctx.action) ctx.action("load", {videoId: h.videoId, title: h.title || ""});
          goPlayer();
        });
        E.home.appendChild(tile);
      });
      E.home.appendChild(el("div", "hb-yt-catch"));
    }

    // 3 — SUGGESTIONS band (V2-597): account-fed, pulled only when asked. Unconnected, a quiet pointer to
    // the shelf instead of an empty band pretending to be one.
    const sug = Array.isArray(data.suggested) ? data.suggested : [];
    const connectedAny = (Array.isArray(data.platforms) ? data.platforms : []).some((r) => r.connected);
    if(sug.length || connectedAny || data.suggesting){
      const sh = el("div", "hb-yt-sughead");
      sh.appendChild(el("span", "", "Sugerencias de tus suscripciones"));
      const bits = [];
      if(data.suggested_at) bits.push(fmtAge(data.suggested_at));
      if(data.suggested_channels) bits.push(data.suggested_channels + " canales");
      if(bits.length) sh.appendChild(el("span", "hb-yt-sugsub", "· " + bits.join(" · ")));
      const rf = el("span", "hb-yt-chip", data.suggesting ? "buscando…" : "↻ refrescar");
      rf.title = "Traer los vídeos recientes de tus suscripciones";
      rf.addEventListener("click", () => { if(ctx && ctx.action && !data.suggesting) ctx.action("suggest", {}); });
      sh.appendChild(rf);
      E.home.appendChild(sh);
      if(!sug.length && !data.suggesting)
        E.home.appendChild(el("div", "hb-yt-homemsg",
          "Toca «refrescar» para traer los vídeos recientes de tus suscripciones."));
      sug.forEach((it) => {
        const tile = mkTile(it);
        tile.addEventListener("click", () => {
          if(ctx && ctx.action) ctx.action("load", {videoId: it.videoId, title: it.title || ""});
          goPlayer();
        });
        E.home.appendChild(tile);
      });
    }

    // 4 — the enforced preferences, spelled out (V2-604): a filter he cannot SEE is one he cannot trust.
    const prefs = data.prefs || {};
    const notes = Array.isArray(data.prefs_notes) ? data.prefs_notes : [];
    const pbits = [];
    if(prefs.min_definition) pbits.push("mínimo " + prefs.min_definition + "p");
    if(prefs.captions === true) pbits.push("subtítulos siempre");
    if(prefs.captions === false) pbits.push("sin subtítulos");
    if(prefs.volume != null) pbits.push("volumen " + prefs.volume);
    notes.forEach((n) => { const t = String(n && n.text || "").trim(); if(t) pbits.push("nota: " + t); });
    if(pbits.length) E.home.appendChild(el("div", "hb-yt-libp", pbits.join(" · ")));

    if(!res.length && !hist.length && !sug.length && !connectedAny && !data.adding && !data.suggesting){
      E.home.appendChild(el("div", "hb-yt-homemsg",
        "No hay ningún vídeo cargado. Dime qué quieres ver, o «búscame vídeos de…» y elige de aquí."));
    }
  }

  // SUBSCRIPTIONS tab (V2-632): the authors he follows — OUR references, no account touched.
  if(E.subsBox){
    E.subsBox.textContent = "";
    const chans = Array.isArray(data.channels) ? data.channels : [];
    E.subsBox.appendChild(el("div", "hb-yt-listh", "Suscripciones · " + chans.length));
    if(!chans.length){
      E.subsBox.appendChild(el("div", "hb-yt-secmsg",
        "No sigues a nadie todavía. Con un vídeo puesto, di «sigue a este canal» y guardo al autor — "
        + "sin tocar ninguna cuenta."));
    }
    chans.forEach((c) => {
      const nom = String(c && c.name || "").trim();
      if(!nom) return;
      const row = el("div", "hb-yt-row");
      row.appendChild(el("span", "hb-yt-rown", "★"));
      row.appendChild(el("span", "hb-yt-rowt", nom));
      const vids = el("span", "hb-yt-chip", "vídeos → cola");
      vids.title = "Lo más reciente de " + nom + ", a la cola";
      vids.addEventListener("click", (e) => {
        e.stopPropagation();
        if(ctx && ctx.action) ctx.action("channel_videos", {channel: nom});
        if(root._hbYtSelectTab) root._hbYtSelectTab("cola");
      });
      row.appendChild(vids);
      const x = el("button", "hb-yt-rowx", "✕");
      x.title = "Dejar de seguir";
      x.addEventListener("click", (e) => {
        e.stopPropagation();
        if(ctx && ctx.action) ctx.action("unfollow_channel", {channel: nom});
      });
      row.appendChild(x);
      E.subsBox.appendChild(row);
    });
  }

  // SAVED LISTS tab (V2-632).
  if(E.listsBox){
    E.listsBox.textContent = "";
    const saved = Array.isArray(data.lists) ? data.lists : [];
    E.listsBox.appendChild(el("div", "hb-yt-listh", "Listas guardadas · " + saved.length));
    if(!saved.length){
      E.listsBox.appendChild(el("div", "hb-yt-secmsg",
        "No hay listas guardadas. Monta una cola y di «guarda la lista como…»."));
    }
    saved.forEach((L) => {
      const nom = String(L && L.name || "").trim();
      if(!nom) return;
      const row = el("div", "hb-yt-row");
      row.appendChild(el("span", "hb-yt-rown", "≣"));
      row.appendChild(el("span", "hb-yt-rowt", nom));
      row.appendChild(el("span", "hb-yt-rowc", (Array.isArray(L.items) ? L.items.length : 0) + " vídeos"));
      const open = el("span", "hb-yt-chip", "abrir → cola");
      open.addEventListener("click", (e) => {
        e.stopPropagation();
        if(ctx && ctx.action) ctx.action("open_list", {name: nom});
        if(root._hbYtSelectTab) root._hbYtSelectTab("cola");
      });
      row.appendChild(open);
      const x = el("button", "hb-yt-rowx", "✕");
      x.title = "Borrar la lista guardada";
      x.addEventListener("click", (e) => {
        e.stopPropagation();
        if(ctx && ctx.action) ctx.action("delete_list", {name: nom});
      });
      row.appendChild(x);
      E.listsBox.appendChild(row);
    });
    const saveRow = el("div", "hb-yt-saverow");
    const inp = el("input", "hb-yt-addinp");
    inp.placeholder = "Guardar la cola actual como…";
    const b = el("button", "hb-yt-btn", "Guardar");
    const doSave = () => {
      const v = (inp.value || "").trim();
      if(!v || !ctx || !ctx.action) return;
      inp.value = "";
      ctx.action("save_list", {name: v});
    };
    b.addEventListener("click", doSave);
    inp.addEventListener("keydown", (e) => { if(e.key === "Enter") doSave(); });
    saveRow.appendChild(inp); saveRow.appendChild(b);
    E.listsBox.appendChild(saveRow);
  }

  if(E.blockedLine){
    const blk = Array.isArray(data.blocked_channels) ? data.blocked_channels : [];
    E.blockedLine.textContent = blk.length ? ("🚫 Canales bloqueados: " + blk.join(", ")) : "";
    E.blockedLine.style.display = blk.length ? "" : "none";
  }

  // Apply the last command if the counter advanced (same video; video changes are covered by the new src).
  if(seq !== root._hbYt.seq){
    applyCmd(E.iframe, data, ctx);
    root._hbYt.seq = seq;
  }
}
