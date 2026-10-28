// musica — the second half of the card's stylesheet: page heads, artists, albums, the hero and the rest of the
// screens (refactor2710-12 T-03). Joined to `CSS` in style.js.

export const CSS_PAGES = `  /* ── a page head (list, artist, album): cover, kicker, name, facts, actions ── */
  .hb-mus2-head{display:flex;gap:16px;align-items:flex-end;padding:2px 2px 4px}
  .hb-mus2-artwrap{position:relative;flex:0 0 auto}
  .hb-mus2-head .hb-mus2-art{width:112px;height:112px;border-radius:10px;
                             box-shadow:0 14px 30px -12px rgba(0,0,0,.6),0 2px 6px rgba(0,0,0,.2)}
  .hb-mus2-head .hb-mus2-art.round{border-radius:50%}
  .hb-mus2-headmeta{display:flex;flex-direction:column;gap:6px;min-width:0;flex:1}
  .hb-mus2-headk{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--hb-muted-2,#9aa7b8);font-weight:600}
  .hb-mus2-headn{font-size:22px;font-weight:800;line-height:1.1;letter-spacing:-.02em;word-break:break-word}
  .hb-mus2-headn.link,.hb-mus2-plsub.link{cursor:pointer}
  .hb-mus2-plsub.link:hover{color:var(--hb-ink,#0d1622);text-decoration:underline}
  .hb-mus2-acts{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:2px}
  .hb-mus2-renin{font:inherit;font-size:20px;font-weight:800;border:1px solid var(--hb-accent,#3D6FE0);border-radius:8px;
                 padding:2px 8px;background:var(--hb-bg,transparent);color:var(--hb-ink,#0d1622);min-width:0;width:100%;box-sizing:border-box}
  .hb-mus2-playfab{position:absolute;right:8px;bottom:8px;width:44px;height:44px;border-radius:50%;
                   background:var(--sp-green);color:#0b1a10;border:0;cursor:pointer;
                   display:flex;align-items:center;justify-content:center;box-shadow:0 6px 14px rgba(0,0,0,.35);
                   transition:transform .15s}
  .hb-mus2-playfab svg{width:18px;height:18px}
  .hb-mus2-playfab:hover{transform:scale(1.06)}
  .hb-mus2-playfab:disabled{opacity:.4;cursor:default;box-shadow:none;transform:none}

  /* artists: round faces in a row that scrolls sideways */
  .hb-mus2-faces{display:flex;gap:12px;overflow-x:auto;padding-bottom:2px}
  .hb-mus2-face{flex:0 0 auto;width:84px;display:flex;flex-direction:column;align-items:center;gap:6px;cursor:pointer;
                text-align:center;border-radius:10px;padding:6px 2px}
  .hb-mus2-face:hover{background:var(--mus-hover)}
  .hb-mus2-face .hb-mus2-art{width:64px;height:64px;border-radius:50%}
  .hb-mus2-facen{font-size:12px;font-weight:600;max-width:80px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

  /* ── THE TRANSPORT, lifted off the content: its own tone, a hairline, a soft upward shadow, and a thin
     progress line along its top edge (the mini-player's own shape) ── */
  .hb-mus2-bar{flex:0 0 auto;position:relative;border-top:1px solid var(--mus-line);background:var(--hb-bg-soft,rgba(127,127,127,.06));
               box-shadow:0 -10px 24px -18px rgba(0,0,0,.55);padding:9px 14px 8px;display:flex;flex-direction:column;gap:4px}
  .hb-mus2-barrow{display:flex;align-items:center;gap:10px;min-width:0}
  .hb-mus2-tapsound{display:block;width:100%;margin:0 0 8px;padding:9px 12px;border:0;border-radius:10px;cursor:pointer;
    background:var(--hb-accent,#7c5cff);color:#fff;font-size:13px;font-weight:600;text-align:center}
  /* V2-795 — the progress row: elapsed · the rail you click or drag · total, then the volume you can SEE */
  .hb-mus2-barprog{display:flex;align-items:center;gap:8px;min-width:0;height:20px}
  .hb-mus2-bartime{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-variant-numeric:tabular-nums;min-width:34px;flex:0 0 auto}
  .hb-mus2-bartime.r{text-align:right}
  .hb-mus2-barprog .hb-mus2-cbtn{padding:3px}
  .hb-mus2-barprog .hb-mus2-cbtn svg{width:16px;height:16px}
  .hb-mus2-barartwrap{position:relative;flex:0 0 auto}
  .hb-mus2-bar .hb-mus2-art{width:44px;height:44px;border-radius:8px;box-shadow:0 3px 10px rgba(0,0,0,.18)}
  .hb-mus2-bar.empty .hb-mus2-art{background:var(--hb-bg,transparent);border:1.5px dashed var(--hb-line,#e3e8f0);
                                  box-shadow:none;color:var(--hb-muted,#5b6b82)}
  .hb-mus2-bar.empty .hb-mus2-art svg{color:var(--hb-muted,#5b6b82)}
  .hb-mus2-areq{position:absolute;right:-3px;bottom:-3px;width:19px;height:19px;border-radius:50%;
                background:var(--hb-ink,#0d1622);display:flex;align-items:center;justify-content:center;
                box-shadow:0 0 0 2px var(--hb-bg-soft,#fbfdff)}
  .hb-mus2-areq .hb-mus2-eq{width:10px;height:9px}
  .hb-mus2-areq .hb-mus2-eq span{width:2px}
  .hb-mus2-barmeta{min-width:0;flex:1}
  .hb-mus2-bart{font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-bara{font-size:12.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-baridle{font-size:13px;font-weight:600;color:var(--hb-muted,#5b6b82);font-style:italic}
  .hb-mus2-barc{display:flex;align-items:center;gap:2px;flex:0 0 auto}
  .hb-mus2-barside{display:flex;align-items:center;gap:2px;flex:0 0 auto}
  .hb-mus2-cbtn{border:0;background:none;color:var(--hb-ink,#0d1622);cursor:pointer;padding:6px;
                border-radius:8px;line-height:1;display:flex;position:relative}
  .hb-mus2-cbtn svg{width:18px;height:18px}
  .hb-mus2-cbtn:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-cbtn.mode{color:var(--hb-muted,#5b6b82)}
  .hb-mus2-cbtn.mode svg{width:16px;height:16px}
  .hb-mus2-cbtn.mode.on{color:var(--sp-green)}
  .hb-mus2-cbtn.mode.on::after{content:"";position:absolute;left:50%;bottom:1px;width:4px;height:4px;margin-left:-2px;
                               border-radius:50%;background:var(--sp-green)}
  .hb-mus2-cbtn.fav{color:var(--sp-green)}
  .hb-mus2-cbtn.fav:hover{color:var(--sp-green);opacity:.8}
  .hb-mus2-cbtn.main{width:38px;height:38px;border-radius:50%;background:var(--hb-ink,#0d1622);margin:0 3px;
                     color:var(--hb-bg,#fff);align-items:center;justify-content:center;padding:0;
                     box-shadow:0 4px 12px rgba(0,0,0,.28)}
  .hb-mus2-cbtn.main svg{width:16px;height:16px}
  .hb-mus2-cbtn.main:hover{color:var(--hb-bg,#fff);opacity:.88}
  .hb-mus2-cbtn:disabled{opacity:.32;cursor:default;pointer-events:none}
  /* the volume, always visible: where it is, clickable, draggable — the same rail drawing as the progress */
  .hb-mus2-vol{width:72px;flex:0 0 auto;accent-color:var(--hb-ink,#0d1622);height:14px;margin:0;cursor:pointer}
  .hb-mus2-vol:hover{accent-color:var(--sp-green)}
  .hb-mus2-barrail{position:relative;flex:1 1 auto;height:14px;cursor:pointer;touch-action:none;min-width:40px}
  .hb-mus2-barrail i{position:absolute;left:0;right:0;top:5px;height:4px;border-radius:999px;background:var(--hb-line,#e3e8f0)}
  .hb-mus2-barrail b{position:absolute;left:0;top:5px;height:4px;border-radius:999px;background:var(--hb-ink,#0d1622);max-width:100%}
  .hb-mus2-barrail u{position:absolute;top:2px;width:10px;height:10px;margin-left:-5px;border-radius:50%;background:var(--sp-green);
                     box-shadow:0 1px 4px rgba(0,0,0,.45);opacity:0;transition:opacity .12s}
  .hb-mus2-barrail:hover b,.hb-mus2-barrail.hb-mus2-drag b{background:var(--sp-green)}
  .hb-mus2-barrail:hover u,.hb-mus2-barrail.hb-mus2-drag u{opacity:1}
  /* the card is resizable: the play modes are the first things to go when it is narrow */
  @container (width <= 400px){ .hb-mus2-barc .mode{display:none} .hb-mus2-vol{width:52px} }

  .hb-mus2-connect{display:flex;flex-direction:column;gap:8px}
  .hb-mus2-sub{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.45}
  .hb-mus2-btn{border:0;background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);border-radius:10px;padding:9px 13px;
               font-size:13px;font-weight:700;cursor:pointer;line-height:1;align-self:flex-start}
  .hb-mus2-btn:disabled{opacity:.5;cursor:default}
  .hb-mus2-btn.ghost{background:var(--mus-card);color:var(--hb-ink,#0d1622);border:1px solid var(--hb-line,#e3e8f0)}
  .hb-mus2-inp{width:100%;box-sizing:border-box;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;
               padding:6px 9px;font-size:13px;background:var(--hb-bg,transparent);color:var(--hb-ink,#0d1622)}
  .hb-mus2-newinp{width:150px}
  .hb-mus2-audio{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;left:-9999px;top:0}
  .hb-mus2-frame{width:1px;height:1px;border:0}
  .hb-mus2-eq{display:flex;align-items:flex-end;gap:2px;width:14px;height:14px}
  .hb-mus2-eq span{width:3px;background:var(--sp-green);border-radius:1px;animation:hbMusEq .9s ease-in-out infinite}
  .hb-mus2-eq span:nth-child(1){height:40%;animation-delay:-.6s}
  .hb-mus2-eq span:nth-child(2){height:100%;animation-delay:-.3s}
  .hb-mus2-eq span:nth-child(3){height:65%;animation-delay:0s}
  @keyframes hbMusEq{0%,100%{transform:scaleY(.4)}50%{transform:scaleY(1)}}

  /* ── AHORA SUENA — the song IS the screen (V2-717): sized against the HEIGHT that is there, so the whole ficha
     fits the card's first footprint with nothing to scroll ── */
  .hb-mus2-now{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;
               width:100%;max-width:520px;height:100%;margin:0 auto;box-sizing:border-box}
  .hb-mus2-nowart{position:relative;height:min(68%,320px);width:auto;max-width:72%;aspect-ratio:1/1;
                  border-radius:16px;overflow:hidden;flex:0 1 auto;display:flex;align-items:center;justify-content:center;
                  background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6));
                  box-shadow:0 26px 48px -20px rgba(0,0,0,.62),0 2px 8px rgba(0,0,0,.18)}
  .hb-mus2-nowart img{width:100%;height:100%;object-fit:cover}
  .hb-mus2-nowart svg{width:34%;height:34%;color:rgba(255,255,255,.92)}
  .hb-mus2-nowt{font-size:20px;font-weight:800;letter-spacing:-.02em;line-height:1.22;
                margin-top:clamp(10px,4%,20px);flex:0 0 auto;
                display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
  .hb-mus2-nowa{font-size:14px;color:var(--hb-muted,#5b6b82);margin-top:6px;white-space:nowrap;overflow:hidden;
                text-overflow:ellipsis;max-width:100%}
  .hb-mus2-nowa.link{cursor:pointer}
  .hb-mus2-nowa.link:hover{color:var(--hb-ink,#0d1622);text-decoration:underline}
  .hb-mus2-nowm{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:10px;font-size:12px;
                letter-spacing:.06em;text-transform:uppercase;color:var(--hb-muted-2,#9aa7b8)}
  .hb-mus2-nowm .hb-mus2-eq{width:11px;height:10px}
  .hb-mus2-nowm i{font-style:normal;opacity:.45}
  /* the scrubber's slot needs a width of its own: in a centred column a bare div shrinks to nothing (V2-717) */
  .hb-mus2-seekslot{width:100%;flex:0 0 auto}
  .hb-mus2-seek{width:100%;margin-top:clamp(12px,4%,22px);display:flex;align-items:center;gap:10px}
  .hb-mus2-time{font-size:12px;color:var(--hb-muted-2,#9aa7b8);min-width:40px;flex:0 0 auto;font-variant-numeric:tabular-nums}
  .hb-mus2-time.r{text-align:right}
  .hb-mus2-rail{position:relative;flex:1 1 auto;height:18px;display:flex;align-items:center;cursor:pointer;touch-action:none}
  .hb-mus2-railbg{position:absolute;left:0;right:0;height:4px;border-radius:999px;background:var(--hb-line,#e3e8f0)}
  .hb-mus2-fill{position:absolute;left:0;height:4px;border-radius:999px;background:var(--hb-ink,#0d1622);
                max-width:100%;transition:background .15s}
  .hb-mus2-knob{position:absolute;width:11px;height:11px;border-radius:50%;background:var(--hb-ink,#0d1622);
                box-shadow:0 1px 5px rgba(0,0,0,.45);transform:translateX(-50%);opacity:0;transition:opacity .12s}
  .hb-mus2-rail:hover .hb-mus2-fill,.hb-mus2-rail.hb-mus2-drag .hb-mus2-fill{background:var(--sp-green)}
  .hb-mus2-rail:hover .hb-mus2-knob,.hb-mus2-rail.hb-mus2-drag .hb-mus2-knob{opacity:1;background:var(--sp-green)}

  /* ── an empty library still has something to say (V2-717); its chips are REAL: each one plays ── */
  .hb-mus2-hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:12px;margin:auto;
                padding:10px 0;max-width:340px}
  .hb-mus2-herod{position:relative;width:76px;height:76px;border-radius:50%;flex:0 0 auto;
                 display:flex;align-items:center;justify-content:center;
                 background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6));
                 box-shadow:0 14px 30px -12px rgba(0,0,0,.55)}
  .hb-mus2-herod svg{width:31px;height:31px;color:#fff}
  .hb-mus2-herod::after{content:"";position:absolute;inset:-9px;border-radius:50%;
                        border:1.5px solid var(--hb-accent,#3D6FE0);opacity:.3;animation:hbMusRing 3.2s ease-out infinite}
  @keyframes hbMusRing{0%{transform:scale(.92);opacity:.34}70%{transform:scale(1.12);opacity:0}100%{opacity:0}}
  .hb-mus2-herot{font-size:16.5px;font-weight:800;letter-spacing:-.015em}
  .hb-mus2-heros{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.5}
  .hb-mus2-chips{display:flex;flex-wrap:wrap;gap:7px;justify-content:center}
  .hb-mus2-chip{border:1px solid var(--hb-line,#e3e8f0);background:var(--mus-panel);
                color:var(--hb-ink,#0d1622);border-radius:999px;padding:6px 12px;font-size:12.5px;font-weight:600;
                cursor:pointer;line-height:1.2}
  .hb-mus2-chip:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-hero .hb-mus2-pl{width:auto;align-items:center;gap:5px;background:none;padding:2px}
  .hb-mus2-hero .hb-mus2-pl:hover{transform:none;box-shadow:none}
  .hb-mus2-hero .hb-mus2-new .hb-mus2-art{width:44px;height:44px;border-radius:12px}
  .hb-mus2-hero .hb-mus2-plname{font-size:12px;color:var(--hb-muted,#5b6b82)}
  `;
