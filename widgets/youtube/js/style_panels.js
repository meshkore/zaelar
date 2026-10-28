// youtube widget — stylesheet, second half: subscriptions, channel page, flags, shelf, account, view switching,
// cinema. Joined after style.js's half into the one sheet injectStyles() adds (refactor2710-12 T-03).
export const CSS_PANELS = `\
  /* SUBSCRIPTIONS as CARDS (2026-09-29): picture, name, subscribers, videos — «otro tipo de cartas». The
     subscription is OURS: the head says so, because «suscribirse» next to a YouTube logo reads as the
     account's subscription, and it is not. */
  .hb-yt-subs{display:flex;flex-direction:column;gap:var(--sp-3,12px)}
  .hb-yt-sechead{display:flex;align-items:center;gap:var(--sp-2,8px);flex-wrap:wrap;min-width:0}
  .hb-yt-sechead .hb-yt-hometitle{flex:0 0 auto}
  .hb-yt-secnote{margin-left:auto;font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD)}
  .hb-yt-chgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:var(--sp-3,12px)}
  .hb-yt-chcard{position:relative;display:flex;align-items:center;gap:var(--sp-3,12px);padding:var(--sp-3,12px);
                border-radius:var(--hb-r-m,10px);background:var(--hb-bg-soft,#272D35);
                border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));cursor:pointer;min-width:0;
                text-align:left;color:inherit;font:inherit;transition:background var(--hb-t-fast,120ms)}
  .hb-yt-chcard:hover{background:var(--hb-bubble,#313740)}
  .hb-yt-chcard:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-yt-av{width:56px;height:56px;border-radius:50%;flex:0 0 auto;object-fit:cover;background:var(--hb-bubble,#313740);
            display:flex;align-items:center;justify-content:center;font-weight:700;font-size:20px;color:var(--hb-muted,#A9B1BD)}
  .hb-yt-av.lg{width:72px;height:72px;font-size:26px}
  .hb-yt-chinfo{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1 1 auto}
  .hb-yt-chname{font-size:var(--fs-ui,14px);font-weight:600;color:var(--hb-ink,#F2F4F7);white-space:nowrap;
                overflow:hidden;text-overflow:ellipsis}
  .hb-yt-chhandle{font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);white-space:nowrap;overflow:hidden;
                  text-overflow:ellipsis}
  .hb-yt-chstats{font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);font-variant-numeric:tabular-nums}
  .hb-yt-chacts{display:flex;align-items:center;gap:4px;margin-top:6px}
  .hb-yt-chx{position:absolute;top:6px;right:6px}
  /* The CHANNEL PAGE — its sections, its videos, paged; the loader while we look for what is new. */
  .hb-yt-chpage{display:flex;flex-direction:column;gap:var(--sp-3,12px);min-width:0}
  .hb-yt-crumb{align-self:flex-start;border:0;background:none;padding:2px 0;cursor:pointer;font:inherit;
               font-size:var(--fs-caption,13.8px);font-weight:600;color:var(--hb-accent,#AE90FF)}
  .hb-yt-crumb:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-yt-chhead{display:flex;align-items:center;gap:var(--sp-4,16px);flex-wrap:wrap;min-width:0}
  .hb-yt-chhead .hb-yt-chname{font-size:var(--fs-title,17px);font-weight:700}
  .hb-yt-chstatus{margin-left:auto;display:flex;align-items:center;gap:var(--sp-2,8px);
                  font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD)}
  .hb-yt-chstatus .hb-yt-spin{width:14px;height:14px;border-width:2px}
  .hb-yt-subtabs{display:flex;gap:4px;flex-wrap:wrap;border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));
                 padding-bottom:var(--sp-2,8px)}
  .hb-yt-subtab{border:1px solid transparent;background:none;border-radius:999px;padding:4px 12px;cursor:pointer;
                font:inherit;font-size:var(--fs-caption,13.8px);font-weight:600;color:var(--hb-muted,#A9B1BD)}
  .hb-yt-subtab:hover{color:var(--hb-ink,#F2F4F7);background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-subtab.on{color:var(--hb-ink,#F2F4F7);border-color:color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent);
                   background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent)}
  .hb-yt-subtab:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-yt-vgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:var(--sp-3,12px)}
  .hb-yt-vgrid.shorts{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}
  .hb-yt-vgrid.shorts .hb-yt-tile img{aspect-ratio:9/16}
  .hb-yt-dur{position:absolute;right:6px;bottom:6px;background:rgba(0,0,0,.72);color:#fff;
             font-size:var(--fs-micro,12.75px);font-weight:600;border-radius:4px;padding:1px 5px;
             font-variant-numeric:tabular-nums}
  .hb-yt-thumb{position:relative;display:block}
  .hb-yt-thumb img{display:block}
  /* FRESHNESS flags: last 24 h and last 72 h, each with its OWN colour and its own WORD — a state is never
     said by colour alone. Filled tints carry the dark ink (V2-691). */
  .hb-yt-flag{position:absolute;left:6px;top:6px;border-radius:4px;padding:1px 6px;font-size:var(--fs-micro,12.75px);
              font-weight:700;color:var(--canvas,#16191E);line-height:1.35}
  .hb-yt-flag.d1{background:var(--hb-ok,#6FE0B0)}
  .hb-yt-flag.d3{background:var(--hb-warn,#F2CE6B)}
  .hb-yt-flag.live{background:var(--hb-risk,#FF8A92)}
  .hb-yt-tilem{font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);white-space:nowrap;overflow:hidden;
               text-overflow:ellipsis;font-variant-numeric:tabular-nums}
  .hb-yt-more{align-self:center;margin-top:var(--sp-2,8px)}
  .hb-yt-chmsg{color:var(--hb-muted,#A9B1BD);font-size:var(--fs-caption,13.8px);padding:var(--sp-5,24px) 0;
               text-align:center;display:flex;align-items:center;justify-content:center;gap:var(--sp-2,8px)}
  .hb-yt-chmsg .hb-yt-spin{width:16px;height:16px;border-width:2px}
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
  .hb-yt-tile.playing .hb-yt-tilet{color:#f03}
  .hb-yt-tilec{font-size:11px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-homemsg{grid-column:1/-1;color:var(--hb-muted-2,#9aa7b8);font-size:13px;text-align:center;padding:26px 12px}
  .hb-yt-blocked{font-size:11px;color:var(--hb-muted-2,#9aa7b8);padding:2px 2px}
  /* ACCOUNT layer (V2-597): platform icons in the nav row — bright = connected (click: its status screen),
     dimmed = not connected (click: its step wizard). The messaging .dots pattern: every channel always
     visible, never hidden and never disabled. */
  .hb-yt-dots{display:flex;align-items:center;gap:4px}
  .hb-yt-picon{width:var(--hb-icon-h,28px);height:var(--hb-icon-h,28px);border:0;background:none;padding:0;
               border-radius:var(--hb-r-s,8px);cursor:pointer;opacity:.72;flex:0 0 auto;
               display:flex;align-items:center;justify-content:center}
  .hb-yt-picon:hover{opacity:1;background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-picon.on{opacity:1}
  .hb-yt-picon svg{width:18px;height:18px;display:block}
  /* Connect screens (V2-597): the step wizard / status card replaces the card faces while open. */
  .hb-yt-conn{display:flex;flex-direction:column;gap:10px}
  .hb-ytw-crumb{font-size:12px;color:var(--hb-accent,#3D6FE0);cursor:pointer;font-weight:600;
                align-self:flex-start}
  /* V2-603 — secondary actions under the primary button: the manual check (now a fallback, not the way the
     flow completes) and the escape hatch to one's own OAuth app. Links, not buttons: a second button next to
     «Conectar» reads as an equal choice, and neither of these is one. */
  /* HOME suggestions band (V2-597): section header spanning the grid; tiles reuse .hb-yt-tile. */
  .hb-yt-sughead{grid-column:1/-1;display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;
                 color:var(--hb-ink,#0d1622);margin-top:2px}
  .hb-yt-sugsub{font-weight:400;color:var(--hb-muted-2,#9aa7b8)}
  /* V2-604 — the operator's OWN library, above everything that depends on a connector. */
  .hb-yt-lib{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:2px 0 6px}
  .hb-yt-libh{font-size:12px;font-weight:700;color:var(--hb-fg,#0f1720);margin-right:2px}
  .hb-yt-libp{grid-column:1/-1;font-size:11px;color:var(--hb-muted-2,#9aa7b8);padding:0 0 8px}
  .hb-yt-catch{grid-column:1/-1;border-top:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));margin-top:4px}
  .hb-yt-catch:last-child{display:none}              /* a divider with nothing after it divides nothing */
  /* View switching is CLASS-driven, never inline display (an inline style would beat the cinema rules
     below). V2-632: one class per TAB — every face hidden by default, each tab shows its own with the
     right display value. Cinema and connmode are declared AFTER and win by order at equal specificity. */
  .hb-yt .hb-yt-blockmsg,
  .hb-yt .hb-yt-frame,.hb-yt .hb-yt-tline,.hb-yt .hb-yt-ctrls,.hb-yt .hb-yt-hint,
  .hb-yt .hb-yt-list,.hb-yt .hb-yt-addrow,.hb-yt .hb-yt-home,.hb-yt .hb-yt-blocked,.hb-yt .hb-yt-subs,
  .hb-yt .hb-yt-mylists{display:none}
  .hb-yt.hb-yt-t-inicio .hb-yt-home{display:grid}
  .hb-yt.hb-yt-t-inicio .hb-yt-homehead{display:flex}
  .hb-yt.hb-yt-t-inicio .hb-yt-blocked{display:block}
  .hb-yt.hb-yt-t-player .hb-yt-frame{display:block}
  .hb-yt.hb-yt-t-player .hb-yt-blockmsg{display:block}
  .hb-yt.hb-yt-t-player .hb-yt-tline{display:flex}
  /* The voice hint only teaches over an EMPTY player: beside a filled bar it is noise below the fold. */
  .hb-yt.hb-yt-t-player:not(.hb-yt-hasvid) .hb-yt-hint{display:block}
  .hb-yt.hb-yt-t-player .hb-yt-ctrls{display:flex}
  .hb-yt.hb-yt-t-cola .hb-yt-list,.hb-yt.hb-yt-t-cola .hb-yt-addrow{display:flex}
  .hb-yt.hb-yt-t-subs .hb-yt-subs{display:flex}
  .hb-yt.hb-yt-t-listas .hb-yt-mylists{display:flex}
  /* Connect mode (the 🔌 screen) hides every tab face — declared AFTER the tab rules on purpose: equal
     specificity, so ORDER is what lets the shelf win over the active tab (measured: the queue rendered
     underneath the shelf when this block sat first). */
  .hb-yt.hb-yt-connmode .hb-yt-frame,.hb-yt.hb-yt-connmode .hb-yt-tline,
  .hb-yt.hb-yt-connmode .hb-yt-ctrls,.hb-yt.hb-yt-connmode .hb-yt-hint,.hb-yt.hb-yt-connmode .hb-yt-list,
  .hb-yt.hb-yt-connmode .hb-yt-addrow,.hb-yt.hb-yt-connmode .hb-yt-home,.hb-yt.hb-yt-connmode .hb-yt-subs,
  .hb-yt.hb-yt-connmode .hb-yt-mylists,.hb-yt.hb-yt-connmode .hb-yt-blocked,
  .hb-yt.hb-yt-connmode .hb-yt-blockmsg,.hb-yt.hb-yt-connmode .hb-yt-homehead{display:none}
  .hb-yt:not(.hb-yt-connmode) .hb-yt-conn{display:none}
  /* CINEMA (V2-596): inside a maximized/fullscreen card the video IS the screen — the frame fills the card and
     the card-shaped furniture (title, controls, hint, playlist, add row) disappears. Without this, a voice
     "maximize the video" grew the CARD while the player kept its 56% card ratio inside a black void. The host
     sets .hb-cinema on the card (desktop.js) and its floating exit button restores everything; the unmute pill
     stays, it is the one control the browser's autoplay policy makes necessary. */
  .hb-win.hb-cinema .hb-yt,.hb-win:fullscreen .hb-yt{width:100%;height:100%;max-width:none;background:#000}
  .hb-win.hb-cinema .hb-yt-body,.hb-win:fullscreen .hb-yt-body{padding:0;gap:0;overflow:hidden}
  .hb-win.hb-cinema .hb-yt-homehead,.hb-win:fullscreen .hb-yt-homehead{display:none}
  .hb-win.hb-cinema .hb-yt-frame,.hb-win:fullscreen .hb-yt-frame{display:block;aspect-ratio:auto;
    flex:1 1 auto;min-height:0;border-radius:0}
  .hb-win.hb-cinema .hb-yt-tline,.hb-win.hb-cinema .hb-yt-ctrls,
  .hb-win.hb-cinema .hb-yt-hint,.hb-win.hb-cinema .hb-yt-list,.hb-win.hb-cinema .hb-yt-addrow,
  .hb-win.hb-cinema .hb-yt-nav,.hb-win.hb-cinema .hb-yt-home,.hb-win.hb-cinema .hb-yt-blocked,
  .hb-win.hb-cinema .hb-yt-blockmsg,.hb-win:fullscreen .hb-yt-blockmsg,
  .hb-win.hb-cinema .hb-yt-conn,.hb-win.hb-cinema .hb-yt-subs,.hb-win.hb-cinema .hb-yt-mylists,
  .hb-win:fullscreen .hb-yt-tline,.hb-win:fullscreen .hb-yt-ctrls,
  .hb-win:fullscreen .hb-yt-hint,.hb-win:fullscreen .hb-yt-list,.hb-win:fullscreen .hb-yt-addrow,
  .hb-win:fullscreen .hb-yt-nav,.hb-win:fullscreen .hb-yt-home,.hb-win:fullscreen .hb-yt-blocked,
  .hb-win:fullscreen .hb-yt-conn,.hb-win:fullscreen .hb-yt-subs,.hb-win:fullscreen .hb-yt-mylists{display:none}
  /* Cinema: the video is the screen — the frame must show whatever tab was active. */
  .hb-win.hb-cinema .hb-yt-frame,.hb-win:fullscreen .hb-yt-frame{display:block}
  `;
