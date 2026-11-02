// musica — the third part of the stylesheet: the four arrangements of js/layout.js (wide · compact · narrow · mobile),
// the sidebar, the bottom navigation, the mini-player, the expanded phone player and the queue drawer/sheet.
// Joined to CSS in style.js. Same rule as the other two: no backtick anywhere in here, not even in a comment.

export const CSS_LAYOUT = `
  /* ── the frame: a body row (sidebar + main [+ queue panel]) over the foot (bar, mini-player, bottom nav) ── */
  .hb-mus2-body{flex:1 1 auto;min-height:0;display:flex;min-width:0}
  .hb-mus2-main{flex:1 1 auto;min-width:0;min-height:0;display:flex;flex-direction:column}
  /* inside the phone shell the shell's own card already pads its content: the player uses the full width, and keeps
     the shell's bottom padding so the page pips never sit on top of the navigation */
  .zm-scroll > .hb-mus2-root.inshell{padding-left:0;padding-right:0;padding-top:0}

  /* ── SIDEBAR (desktop) ── */
  .hb-mus2-side{flex:0 0 200px;display:flex;flex-direction:column;gap:2px;padding:10px 8px;min-height:0;overflow:auto;
                border-right:1px solid var(--mus-line);background:var(--hb-bg-soft,rgba(127,127,127,.05));box-sizing:border-box}
  .hb-mus2-side.rail{flex-basis:60px;align-items:center;padding:10px 6px}
  .hb-mus2-sideb{display:flex;align-items:center;gap:10px;width:100%;min-height:40px;padding:0 10px;border:0;border-radius:9px;
                 background:none;color:var(--hb-muted,#5b6b82);font-size:13px;font-weight:700;cursor:pointer;text-align:left;
                 box-sizing:border-box}
  .hb-mus2-sideb svg{width:19px;height:19px;flex:none}
  .hb-mus2-sideb:hover{background:var(--mus-hover);color:var(--hb-ink,#0d1622)}
  .hb-mus2-sideb.on{background:var(--mus-card);color:var(--hb-ink,#0d1622);box-shadow:inset 3px 0 0 var(--sp-green)}
  .hb-mus2-side.rail .hb-mus2-sideb{width:44px;height:44px;padding:0;justify-content:center}
  .hb-mus2-side.rail .hb-mus2-sideb span{display:none}
  .hb-mus2-sidetog{align-self:flex-end;width:32px;height:32px;border:0;border-radius:8px;background:none;cursor:pointer;
                   color:var(--hb-muted,#5b6b82);display:flex;align-items:center;justify-content:center;margin-bottom:4px}
  .hb-mus2-side.rail .hb-mus2-sidetog{align-self:center}
  .hb-mus2-sidetog svg{width:17px;height:17px}
  .hb-mus2-sidetog:hover{background:var(--mus-hover);color:var(--hb-ink,#0d1622)}
  .hb-mus2-sidek{font-size:11.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--hb-muted-2,#9aa7b8);
                 margin:14px 10px 4px}
  .hb-mus2-sidepls{display:flex;flex-direction:column;gap:1px;min-height:0}
  .hb-mus2-sidepl{border:0;background:none;text-align:left;padding:7px 10px;border-radius:8px;color:var(--hb-muted,#5b6b82);
                  font-size:13px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-sidepl:hover{background:var(--mus-hover);color:var(--hb-ink,#0d1622)}
  .hb-mus2-sidepl.on{color:var(--sp-green);font-weight:700}

  /* the desktop bar: a search field that is always there, and the two sources on the right */
  .L-wide .hb-mus2-headfix,.L-compact .hb-mus2-headfix{min-height:44px;padding:6px 14px;box-sizing:border-box}
  .L-wide .hb-mus2-headfix .hb-mus2-sbox,.L-compact .hb-mus2-headfix .hb-mus2-sbox{max-width:420px;height:32px}
  .hb-mus2-provs{display:flex;gap:6px}
  .hb-mus2-prov.live{color:var(--hb-ink,#0d1622);border-color:color-mix(in srgb,var(--sp-green) 60%,transparent)}
  .hb-mus2-sinp::-webkit-search-cancel-button{-webkit-appearance:none;appearance:none;display:none}
  .hb-mus2-sclear{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);cursor:pointer;padding:0;width:24px;height:24px;
                  display:flex;align-items:center;justify-content:center;flex:none;border-radius:50%}
  .hb-mus2-sclear svg{width:13px;height:13px}
  .hb-mus2-sclear:hover{color:var(--hb-ink,#0d1622);background:var(--mus-hover)}
  .hb-mus2-cbtn.qbtn.on{color:var(--sp-green)}

  /* the wide card's queue, beside the song */
  .hb-mus2-qpanel{flex:0 0 340px;min-height:0;overflow:auto;border-left:1px solid var(--mus-line);padding:14px;
                  box-sizing:border-box;background:var(--hb-bg-soft,rgba(127,127,127,.04))}
  .hb-mus2-qbody{display:flex;flex-direction:column;gap:12px}

  /* the song's actions under its name, every layout */
  .hb-mus2-nowinfo{display:flex;flex-direction:column;align-items:center;width:100%;min-width:0}
  .hb-mus2-nowwords{min-width:0;max-width:100%;display:flex;flex-direction:column;align-items:center}
  .hb-mus2-nowacts{display:flex;gap:6px;margin-top:8px;flex:0 0 auto}
  .hb-mus2-ibtn.big{width:44px;height:44px;border-radius:50%}
  /* on a desktop card the bar at the foot already carries the heart: a short card gives the cover that row back */
  @container (height < 360px){ .hb-mus2-now:not(.m) .hb-mus2-nowacts{display:none} }
  /* the short-card rule in style.js loses to the facts line's own later declaration; said again with the weight it needs */
  @container (height < 250px){ .hb-mus2-now .hb-mus2-nowm{display:none} }
  .hb-mus2-ibtn.big svg{width:20px;height:20px}

  /* ── filters / tabs (search, your music) ── */
  .hb-mus2-filters{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;flex:0 0 auto;padding:1px}
  .hb-mus2-filters::-webkit-scrollbar{display:none}
  .hb-mus2-filter{flex:0 0 auto;border:1px solid var(--hb-line,#e3e8f0);background:var(--mus-card);color:var(--hb-ink,#0d1622);
                  border-radius:999px;padding:0 14px;min-height:34px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
  .hb-mus2-filter.on{background:var(--hb-ink,#0d1622);color:var(--hb-bg,#fff);border-color:transparent}
  .hb-mus2-cfilter{flex:0 0 auto;height:36px;max-width:420px}
  .hb-mus2-phead{display:flex;align-items:center;gap:10px;flex:0 0 auto}
  .hb-mus2-pheadt{font-size:22px;font-weight:800;letter-spacing:-.02em;flex:1 1 auto;min-width:0}
  .hb-mus2-pheadr{display:flex;align-items:center;gap:6px;flex:0 0 auto}
  .hb-mus2-note.mid{margin:auto;text-align:center}
  .hb-mus2-trsrc{color:var(--hb-muted-2,#9aa7b8)}
  .hb-mus2-menuh{font-size:12px;color:var(--hb-muted,#5b6b82);padding:6px 9px 7px;border-bottom:1px solid var(--mus-line);
                 margin-bottom:3px;white-space:normal;line-height:1.35}

  /* ── SHELVES: cards in a row that scrolls sideways; about two cards across on a phone ── */
  .hb-mus2-shelf{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x proximity;padding-bottom:4px;scrollbar-width:thin}
  .hb-mus2-shelf > .hb-mus2-pl{flex:0 0 132px;scroll-snap-align:start}
  .hb-mus2-card.current .hb-mus2-plname{color:var(--sp-green)}
  /* on a card the play button sits ON the cover (its corner), never over the name under it */
  .hb-mus2-art{position:relative}
  .hb-mus2-art > .hb-mus2-plplay{top:auto;right:8px;bottom:8px}
  .hb-mus2-lists.two{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
  .hb-mus2-plmore{position:absolute;right:6px;top:6px;background:rgba(0,0,0,.45);color:#fff;opacity:0;width:32px;height:32px}
  .hb-mus2-plmore svg{color:#fff}
  .hb-mus2-pl:hover .hb-mus2-plmore,.hb-mus2-plmore:focus-visible{opacity:1}
  .hb-mus2-plmore:hover{background:rgba(0,0,0,.6);color:#fff}
  .hb-mus2-trmore{display:none}

  /* ── BOTTOM NAVIGATION (narrow window, phone) ── */
  .hb-mus2-bnav{flex:0 0 auto;display:flex;border-top:1px solid var(--mus-line);background:var(--hb-bg-soft,rgba(127,127,127,.06))}
  .hb-mus2-root:not(.inshell) .hb-mus2-bnav{padding-bottom:env(safe-area-inset-bottom)}
  .hb-mus2-bnavb{flex:1 1 0;min-width:0;min-height:54px;border:0;background:none;color:var(--hb-muted,#5b6b82);cursor:pointer;
                 display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:11px;
                 font-weight:700;padding:4px 2px}
  .hb-mus2-bnavb svg{width:22px;height:22px}
  .hb-mus2-bnavb span{max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-bnavb.on{color:var(--hb-ink,#0d1622)}
  .hb-mus2-bnavb.on svg{color:var(--sp-green)}
  /* the narrow window's tab strip: icon and word; when it gets tight only the tab you are on keeps its word */
  .L-narrow .hb-mus2-headfix{padding-top:4px;padding-bottom:4px}
  .L-narrow .hb-mus2-segb{min-height:24px}
  @container (width < 540px){ .L-narrow .hb-mus2-segb:not(.on) span{display:none}
                              .L-narrow .hb-mus2-segb:not(.on){padding:4px 8px} }

  /* ── MINI-PLAYER (phone): 64 px, a progress line on its top edge ── */
  .hb-mus2-mini{flex:0 0 auto;position:relative;display:flex;align-items:center;gap:10px;height:64px;padding:0 6px 0 10px;
                margin:0 8px 6px;border-radius:12px;background:var(--mus-card);box-shadow:var(--mus-shadow);cursor:pointer;
                overflow:hidden}
  .hb-mus2-miniprog{position:absolute;left:0;right:0;top:0;height:2px;background:var(--hb-line,#e3e8f0)}
  .hb-mus2-miniprog b{display:block;height:100%;width:0;background:var(--sp-green)}
  .hb-mus2-mini .hb-mus2-art{width:44px;height:44px;border-radius:7px}
  .hb-mus2-minimeta{flex:1 1 auto;min-width:0}
  .hb-mus2-minit{font-size:14px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-minia{font-size:12.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-minib{flex:0 0 auto;width:44px;height:44px;border:0;border-radius:50%;background:none;color:var(--hb-ink,#0d1622);
                 cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0}
  .hb-mus2-minib svg{width:22px;height:22px}
  .hb-mus2-minib.main svg{width:24px;height:24px}

  /* ── THE PHONE: tighter middle, touch-size rows, no hover-only actions ── */
  .L-mobile .hb-mus2-scroll{padding:10px 12px;gap:12px}
  .L-mobile .hb-mus2-sec{padding:10px;box-shadow:none}
  .L-mobile .hb-mus2-headfix.slim{background:none;border-bottom:0;padding:4px 6px 0;min-height:0}
  .L-mobile .hb-mus2-back{min-height:44px;padding:0 10px 0 4px}
  .L-mobile .hb-mus2-tr{min-height:56px}
  .hb-mus2-stop{flex:0 0 auto;position:sticky;top:-10px;z-index:3;margin:-10px -12px 0;padding:10px 12px 4px;
                background:var(--hb-bg,#fff)}
  .hb-mus2-stop .hb-mus2-sbox{height:44px;font-size:16px}
  .hb-mus2-stop .hb-mus2-sinp{font-size:16px}
  .L-mobile .hb-mus2-shelf > .hb-mus2-pl{flex-basis:calc((100% - 10px) / 2.15)}
  .L-mobile .hb-mus2-lists.two{grid-template-columns:repeat(2,minmax(0,1fr))}
  /* A touch screen has no hover: what a pointer reveals is always drawn, or reached by a tap. */
  @media (hover:none){
    .hb-mus2-plplay,.hb-mus2-plmore{opacity:1;transform:none}
    .hb-mus2-plplay{width:40px;height:40px}
    .hb-mus2-trmore{display:flex;opacity:1;width:44px;height:44px}
    .hb-mus2-tr.selected .hb-mus2-trx{display:none}
    .hb-mus2-grip{opacity:1;width:32px;height:44px;align-items:center;justify-content:center}
    .hb-mus2-x{display:none}
    .hb-mus2-cbtn{min-width:40px;min-height:40px;align-items:center;justify-content:center}
    .hb-mus2-sideb{min-height:44px}
    .hb-mus2-ibtn,.hb-mus2-sclear,.hb-mus2-plmore{min-width:44px;min-height:44px}
    .hb-mus2-pill,.hb-mus2-prov,.hb-mus2-filter,.hb-mus2-back{min-height:40px}
    .hb-mus2-sbox{min-height:40px}
  }
  .hb-mus2-tr.lifted{background:var(--mus-hover);box-shadow:var(--mus-shadow)}

  /* ── THE EXPANDED PLAYER (phone, portrait): one column sized by the height that is there ── */
  .hb-mus2-scroll.player{padding:8px 16px 10px}
  .hb-mus2-now.m{max-width:480px;gap:0;justify-content:safe center}
  .hb-mus2-now.m .hb-mus2-nowart{height:auto;max-width:none;flex:0 0 auto;
                                 width:clamp(96px, calc(100cqh - 296px), min(82cqw, 420px))}
  .hb-mus2-now.m .hb-mus2-nowinfo{flex-direction:row;align-items:center;gap:8px;margin-top:clamp(10px,3cqh,22px);text-align:left}
  .hb-mus2-now.m .hb-mus2-nowwords{flex:1 1 auto;align-items:flex-start}
  .hb-mus2-now.m .hb-mus2-nowt{margin-top:0;font-size:20px;-webkit-line-clamp:1;display:block;white-space:nowrap;
                               text-overflow:ellipsis;max-width:100%}
  .hb-mus2-now.m .hb-mus2-nowa{margin-top:2px;font-size:15px}
  .hb-mus2-now.m .hb-mus2-nowacts{margin-top:0}
  .hb-mus2-now.m .hb-mus2-seekslot{min-height:36px;display:flex;align-items:center}
  .hb-mus2-now.m .hb-mus2-seek{margin-top:6px}
  .hb-mus2-now.m .hb-mus2-rail{height:28px}
  .hb-mus2-now.m .hb-mus2-knob{opacity:1}
  .hb-mus2-barc.big .mode{display:flex}
  .hb-mus2-barc.big{justify-content:space-between;width:100%;max-width:360px;margin-top:4px}
  .hb-mus2-barc.big .hb-mus2-cbtn{width:48px;height:48px;align-items:center;justify-content:center;padding:0}
  .hb-mus2-barc.big .hb-mus2-cbtn svg{width:26px;height:26px}
  .hb-mus2-barc.big .hb-mus2-cbtn.mode svg{width:22px;height:22px}
  .hb-mus2-barc.big .hb-mus2-cbtn.main{width:68px;height:68px;margin:0}
  .hb-mus2-barc.big .hb-mus2-cbtn.main svg{width:28px;height:28px}
  .hb-mus2-nowxw{width:100%;max-width:360px;margin-top:6px}
  .hb-mus2-nowx{display:flex;align-items:center;gap:8px;min-height:44px}
  .hb-mus2-nowxb{display:flex;align-items:center;gap:7px;min-height:44px;padding:0 12px;border:1px solid var(--hb-line,#e3e8f0);
                 border-radius:999px;background:var(--mus-card);color:var(--hb-ink,#0d1622);font-size:13px;font-weight:700;cursor:pointer}
  .hb-mus2-nowxb svg{width:17px;height:17px}
  .hb-mus2-nowsrc{flex:1 1 auto;text-align:center;font-size:12px;letter-spacing:.06em;text-transform:uppercase;
                  color:var(--hb-muted-2,#9aa7b8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-volpop{display:flex;align-items:center;gap:8px;padding:2px 0}
  .hb-mus2-volpop[hidden]{display:none}
  .hb-mus2-volpop .hb-mus2-vol{flex:1 1 auto;width:auto;height:28px}
  /* a SHORT phone: the art shrinks first (the clamp above), then the secondary row folds into one line */
  @container (height < 430px){ .hb-mus2-now.m .hb-mus2-nowinfo{margin-top:8px}
                               .hb-mus2-barc.big .hb-mus2-cbtn.main{width:58px;height:58px} }

  /* ── PHONE ON ITS SIDE: art on the left, everything else on the right, play always in reach ── */
  .hb-mus2-now.m.land{display:grid;grid-template-columns:auto minmax(0,1fr);grid-template-rows:auto auto auto auto;
                      column-gap:20px;align-content:safe center;max-width:none;height:100%}
  .hb-mus2-now.m.land .hb-mus2-nowart{grid-row:1 / span 4;align-self:center;width:clamp(96px, calc(100cqh - 16px), 40cqw)}
  .hb-mus2-now.m.land .hb-mus2-nowinfo{margin-top:0}
  .hb-mus2-now.m.land .hb-mus2-barc.big{max-width:none;margin-top:0}
  .hb-mus2-now.m.land .hb-mus2-barc.big .hb-mus2-cbtn.main{width:56px;height:56px}
  .hb-mus2-now.m.land .hb-mus2-nowxw{max-width:none;margin-top:0}
  /* on its side a phone has width to spare and no height: the navigation becomes a rail on the left, so the content
     keeps the height the bottom bar would have eaten */
  .L-mobile.land{display:grid;grid-template-columns:76px minmax(0,1fr);grid-template-rows:minmax(0,1fr) auto}
  .L-mobile.land > .hb-mus2-body{grid-column:2;grid-row:1}
  .L-mobile.land > .hb-mus2-mini,.L-mobile.land > .hb-mus2-tapsound{grid-column:2;grid-row:2;height:56px;margin-top:4px}
  .L-mobile.land > .hb-mus2-bnav{grid-column:1;grid-row:1 / span 2;flex-direction:column;border-top:0;
                                  border-right:1px solid var(--mus-line);justify-content:center}
  .L-mobile.land .hb-mus2-bnavb{flex:0 0 auto;min-height:52px}
  .L-mobile.land > .hb-mus2-qlayer{grid-column:1 / span 2;grid-row:1 / span 2}

  /* the YouTube embed, laid over the (square) art slot while the song is on screen and the slot is big enough */
  .hb-mus2-nowart.video{background:#000}
  .hb-mus2-audio.vis{opacity:1;z-index:4;border-radius:14px;overflow:hidden;pointer-events:none;width:auto;height:auto}
  .hb-mus2-audio.vis .hb-mus2-frame{width:100%;height:100%}

  /* ── THE QUEUE as a layer: a drawer from the right (desktop window), a sheet from the bottom (narrow, phone) ── */
  .hb-mus2{position:relative}
  .hb-mus2-qlayer{position:absolute;inset:0;z-index:15;display:flex}
  .hb-mus2-qscrim{position:absolute;inset:0;background:rgba(0,0,0,.42)}
  .hb-mus2-qsheet{position:relative;display:flex;flex-direction:column;min-height:0;background:var(--hb-bg,#fff);
                  box-shadow:var(--hb-shadow-2,0 16px 40px rgba(0,0,0,.35))}
  .hb-mus2-qlayer.drawer{justify-content:flex-end}
  .hb-mus2-qlayer.drawer .hb-mus2-qsheet{width:min(380px,88%);height:100%;border-left:1px solid var(--mus-line)}
  .hb-mus2-qlayer.sheet{align-items:flex-end}
  .hb-mus2-qlayer.sheet .hb-mus2-qsheet{width:100%;max-height:86%;height:86%;border-radius:16px 16px 0 0}
  .hb-mus2-qhead{flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:8px 8px 6px 16px;position:relative;
                 border-bottom:1px solid var(--mus-line)}
  .hb-mus2-qgrab{position:absolute;left:50%;top:5px;width:38px;height:4px;margin-left:-19px;border-radius:999px;
                 background:var(--hb-line,#e3e8f0)}
  .hb-mus2-qtitle{flex:1 1 auto;font-size:17px;font-weight:800;padding-top:6px}
  .hb-mus2-qscroll{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain;padding:12px}
  `;
