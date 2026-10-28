// musica — the card's scoped stylesheet, injected once by `injectStyles` in widget.js; the page screens' half
// lives in style_pages.js (refactor2710-12 T-03).
//
// ⚠️ No backtick may appear inside these CSS templates, not even in a comment: it ends the literal and the whole
// module (`node --check` catches it, nothing at runtime does).
import { CSS_PAGES } from "./style_pages.js";

export const CSS = `
  /* THREE bands that never trade places: the one bar, a scrolling middle, the transport at the foot. The root
     fills the card and switches OFF the card's own scroll (the :has rule), so the middle owns the overflow. */
  .hb-scroll:has(> .hb-mus2-root){overflow:hidden}
  .hb-mus2-root{position:relative;height:100%;display:flex;flex-direction:column;overflow:hidden}
  /* el._viewHost sits between root and the visible card and needs its own place in the height chain: with no
     rule of its own it is height:auto, and a percentage height under it resolves against nothing (V2-678). */
  .hb-mus2-viewhost{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
  /* V2-717 — ONE box: no border, radius or background of our own; the window is the frame.
     V2-795 — the rungs this card uses, named once so every panel picks the same step of the ladder:
     the card sits on --hb-bg (surface 1), a PANEL is --hb-bg-soft (surface 2), a card inside a panel is
     --hb-bubble (surface 3), and hover is --hb-hover. Hairlines are alpha so they weigh the same on every rung. */
  .hb-mus2{--sp-green:#1DB954;--mus-panel:var(--hb-bg-soft,rgba(127,127,127,.07));
           --mus-card:var(--hb-bubble,rgba(127,127,127,.11));--mus-hover:var(--hb-hover,rgba(127,127,127,.16));
           --mus-line:var(--hb-line-subtle,rgba(127,127,127,.18));--mus-r:var(--hb-r-l,12px);
           --mus-shadow:var(--hb-shadow-1,0 1px 2px rgba(0,0,0,.18),0 4px 12px rgba(0,0,0,.10));
           font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
           width:100%;height:100%;min-height:0;box-sizing:border-box;background:transparent;overflow:hidden;
           color:var(--hb-ink,#0d1622);display:flex;flex-direction:column;container-type:inline-size}
  .hb-mus2 svg{display:block}
  .hb-mus2 button{font-family:inherit}

  /* ── THE ONE BAR: where you are on the left, the search and the source chip in ONE right cluster ── */
  .hb-mus2-headfix{flex:0 0 auto;background:var(--hb-bg-soft,rgba(127,127,127,.05));
                   border-bottom:1px solid var(--mus-line);padding:5px 12px;min-height:32px;
                   display:flex;align-items:center;gap:8px}
  .hb-mus2-right{margin-left:auto;display:flex;align-items:center;gap:6px;flex:0 0 auto}
  .hb-mus2-prov{font-size:12px;color:var(--hb-muted,#5b6b82);border:1px solid var(--hb-line,#e3e8f0);
                border-radius:999px;padding:3px 10px;display:flex;align-items:center;gap:6px;flex:0 0 auto;
                background:var(--hb-bg,transparent);cursor:pointer;line-height:1.5}
  .hb-mus2-prov:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-ink,#0d1622)}
  .hb-mus2-dot{width:7px;height:7px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:0 0 auto}
  .hb-mus2-dot.on{background:var(--sp-green)}
  .hb-mus2-seg{display:flex;gap:2px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:2px;
               background:var(--hb-bg,transparent);flex:0 1 auto;min-width:0;overflow-x:auto;scrollbar-width:none}
  .hb-mus2-seg::-webkit-scrollbar{display:none}
  .hb-mus2-segb{flex:0 0 auto}
  .hb-mus2-segb{border:0;background:none;color:var(--hb-muted,#5b6b82);font-size:12px;font-weight:700;
                padding:4px 10px;border-radius:999px;cursor:pointer;display:flex;align-items:center;gap:5px;
                line-height:1;white-space:nowrap}
  .hb-mus2-segb svg{width:13px;height:13px;flex:none}
  .hb-mus2-segb:hover{color:var(--hb-ink,#0d1622)}
  .hb-mus2-segb.on{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 18%,transparent);color:var(--hb-ink,#0d1622);
                   box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--hb-accent,#3D6FE0) 55%,transparent)}
  .hb-mus2-back{border:0;background:none;color:var(--hb-muted,#5b6b82);font-size:13px;font-weight:600;cursor:pointer;
                display:flex;align-items:center;gap:4px;padding:2px 4px 2px 0;flex:0 0 auto}
  .hb-mus2-back svg{width:15px;height:15px}
  .hb-mus2-back:hover{color:var(--hb-accent,#3D6FE0)}
  /* a quiet square icon button — the house kit's shape, drawn here so a card rendered outside the app keeps it */
  .hb-mus2-ibtn{border:1px solid transparent;background:none;color:var(--hb-muted,#5b6b82);cursor:pointer;
                width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;
                padding:0;flex:0 0 auto;transition:background .12s,color .12s}
  .hb-mus2-ibtn svg{width:16px;height:16px}
  .hb-mus2-ibtn:hover{background:var(--mus-hover);color:var(--hb-ink,#0d1622)}
  .hb-mus2-ibtn.on{color:var(--sp-green)}
  .hb-mus2-ibtn.risk:hover{color:var(--hb-risk,#e5484d)}
  .hb-mus2-ibtn:disabled{opacity:.35;cursor:default;pointer-events:none}
  .hb-mus2-sbox{flex:1 1 auto;min-width:0;display:flex;align-items:center;gap:7px;height:28px;padding:0 10px;
                border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;background:var(--hb-bg,transparent)}
  .hb-mus2-sbox:focus-within{border-color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-sbox svg{width:14px;height:14px;color:var(--hb-muted-2,#9aa7b8);flex:none}
  .hb-mus2-sinp{flex:1 1 auto;min-width:0;border:0;outline:none;background:none;color:var(--hb-ink,#0d1622);
                font:inherit;font-size:13px}

  /* ── the middle ── */
  .hb-mus2-scroll{flex:1 1 auto;min-height:0;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:12px}
  /* safe center, never plain center: a centred column CLIPS what overflows at both ends (V2-717, measured) */
  .hb-mus2-scroll.mid{justify-content:safe center;align-items:center;container-type:size}
  /* a SHORT card (the window is resizable) gives the cover the room first: the facts line goes, the title shrinks */
  @container (height < 250px){ .hb-mus2-nowm{display:none} .hb-mus2-nowt{font-size:17px;margin-top:8px}
                               .hb-mus2-nowa{margin-top:2px} .hb-mus2-nowart{height:min(76%,320px)}
                               .hb-mus2-seek{margin-top:8px} }

  /* V2-795 — A PANEL per shelf: one rung up, a hairline, the soft resting shadow. Quiet on purpose: the content
     is the music, the panel only says where one group ends and the next begins. */
  .hb-mus2-sec{display:flex;flex-direction:column;gap:10px;background:var(--mus-panel);border:1px solid var(--mus-line);
               border-radius:var(--mus-r);box-shadow:var(--mus-shadow);padding:12px;flex:0 0 auto}
  .hb-mus2-sechead{display:flex;align-items:center;gap:8px;min-height:24px}
  .hb-mus2-sech{font-size:13.5px;font-weight:700;letter-spacing:-.005em}
  .hb-mus2-secn{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-variant-numeric:tabular-nums}
  .hb-mus2-secact{margin-left:auto;display:flex;align-items:center;gap:6px}
  .hb-mus2-note{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.45}
  .hb-mus2-pill{border:1px solid var(--hb-line,#e3e8f0);background:var(--mus-card);color:var(--hb-ink,#0d1622);
                border-radius:999px;padding:4px 11px;font-size:12px;font-weight:600;cursor:pointer;line-height:1.3;
                display:flex;align-items:center;gap:5px}
  .hb-mus2-pill svg{width:13px;height:13px}
  .hb-mus2-pill:hover{border-color:var(--hb-accent,#3D6FE0);background:var(--mus-hover)}
  .hb-mus2-pill.risk{color:var(--hb-risk,#e5484d)}

  /* lists as CARDS with a cover mosaic; the «new list» is a pill in the panel's head, not a giant tile */
  .hb-mus2-lists{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:10px}
  .hb-mus2-pl{min-width:0;display:flex;flex-direction:column;gap:7px;padding:8px;border-radius:10px;cursor:pointer;
              background:var(--mus-card);border:1px solid transparent;position:relative;
              transition:background .14s,transform .14s,box-shadow .14s}
  .hb-mus2-pl:hover{background:var(--mus-hover);transform:translateY(-1px);box-shadow:var(--mus-shadow)}
  .hb-mus2-pl .hb-mus2-art{width:100%;height:auto;aspect-ratio:1/1}
  .hb-mus2-plname{font-size:13px;font-weight:600;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-plsub{font-size:12px;color:var(--hb-muted,#5b6b82)}
  .hb-mus2-plplay{position:absolute;right:13px;top:calc(100% - 78px);width:34px;height:34px;border-radius:50%;
                  border:0;background:var(--sp-green);color:#0b1a10;display:flex;align-items:center;justify-content:center;
                  cursor:pointer;box-shadow:0 6px 14px rgba(0,0,0,.35);opacity:0;transform:translateY(4px);
                  transition:opacity .14s,transform .14s}
  .hb-mus2-plplay svg{width:15px;height:15px}
  .hb-mus2-pl:hover .hb-mus2-plplay{opacity:1;transform:none}

  .hb-mus2-art{border-radius:8px;display:flex;align-items:center;justify-content:center;overflow:hidden;flex:0 0 auto;
               background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6))}
  .hb-mus2-art img{width:100%;height:100%;object-fit:cover}
  .hb-mus2-art svg{width:38%;height:38%;color:rgba(255,255,255,.92)}
  .hb-mus2-art.fav{background:linear-gradient(135deg,#7b5cff,#e05ca8)}
  .hb-mus2-mosaic{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}
  .hb-mus2-mosaic img{width:100%;height:100%;object-fit:cover;display:block}
  .hb-mus2-new .hb-mus2-art{background:var(--mus-card);border:1.5px dashed var(--hb-line,#e3e8f0);
                            color:var(--hb-muted,#5b6b82)}
  .hb-mus2-new .hb-mus2-art svg{color:var(--hb-muted,#5b6b82)}

  /* ── rows ── */
  .hb-mus2-grid{display:flex;flex-direction:column;gap:2px}
  .hb-mus2-tr{display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:8px;cursor:pointer;
              user-select:none;position:relative;transition:background .12s}
  .hb-mus2-tr:hover{background:var(--mus-hover)}
  .hb-mus2-tr.selected{background:var(--mus-card);box-shadow:inset 0 0 0 1px var(--hb-line,#e3e8f0)}
  /* V2-795 — three states that never look alike: HOVER is a neutral tone; CURRENT (the song the player holds)
     is a green title and a green edge, with no fill of its own, so it reads the same under the pointer and
     away from it; the animated meter is drawn ONLY while it is actually sounding. */
  .hb-mus2-tr.current{box-shadow:inset 3px 0 0 var(--sp-green)}
  .hb-mus2-tr.current .hb-mus2-trt{color:var(--sp-green)}
  .hb-mus2-tr.current .hb-mus2-trn svg{width:14px;height:14px;color:var(--sp-green)}
  .hb-mus2-tr.dragover{box-shadow:inset 0 2px 0 var(--hb-accent,#3D6FE0)}
  .hb-mus2-tr.current.selected{box-shadow:inset 3px 0 0 var(--sp-green),inset 0 0 0 1px var(--hb-line,#e3e8f0)}
  .hb-mus2-tr .hb-mus2-art{width:40px;height:40px;border-radius:6px;position:relative}
  .hb-mus2-trplay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;border:0;padding:0;
                  background:rgba(0,0,0,.55);color:#fff;opacity:0;cursor:pointer;transition:opacity .12s;border-radius:6px}
  .hb-mus2-trplay svg{width:16px;height:16px;color:#fff}
  .hb-mus2-tr:hover .hb-mus2-trplay{opacity:1}
  .hb-mus2-trn{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-variant-numeric:tabular-nums;
               min-width:18px;text-align:center;display:flex;align-items:center;justify-content:center}
  .hb-mus2-trmeta{min-width:0;flex:1}
  .hb-mus2-trt{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-tra{font-size:12px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-trx{display:flex;align-items:center;gap:2px;flex:0 0 auto}
  /* a row's own buttons are quiet until the row is under the pointer; a liked heart stays lit, it is a STATE */
  .hb-mus2-trx .hb-mus2-ibtn{opacity:0;width:26px;height:26px}
  .hb-mus2-trx .hb-mus2-ibtn svg{width:14px;height:14px}
  .hb-mus2-tr:hover .hb-mus2-trx .hb-mus2-ibtn,.hb-mus2-trx .hb-mus2-ibtn.on,.hb-mus2-trx .hb-mus2-ibtn:focus-visible{opacity:1}
  /* A finger has no hover (V2-813): the three row actions were invisible yet held three 44px slots, so a title read
     «Despech…». On a touch screen they are not there until the row is tapped, and then they take a line of their own. */
  @media (hover:none){
    .hb-mus2-trx{display:none}
    .hb-mus2-tr.selected{flex-wrap:wrap}
    .hb-mus2-tr.selected .hb-mus2-trx{display:flex;flex:1 1 100%;justify-content:flex-end}
    .hb-mus2-tr.selected .hb-mus2-trx .hb-mus2-ibtn{opacity:1}
  }
  .hb-mus2-x{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);cursor:pointer;
             padding:5px;border-radius:7px;line-height:1;flex:0 0 auto;display:flex}
  .hb-mus2-x svg{width:14px;height:14px}
  .hb-mus2-x:hover{color:var(--hb-risk,#e5484d)}
  .hb-mus2-grip{color:var(--hb-muted-2,#9aa7b8);cursor:grab;display:flex;opacity:0;flex:0 0 auto}
  .hb-mus2-grip svg{width:14px;height:14px}
  .hb-mus2-tr:hover .hb-mus2-grip{opacity:1}
  .hb-mus2-empty{font-size:12.5px;color:var(--hb-muted-2,#9aa7b8);padding:2px}

  /* a small menu that floats over the card (add to which list) */
  .hb-mus2-menu{position:absolute;z-index:20;min-width:180px;max-width:240px;max-height:240px;overflow:auto;padding:5px;
                background:var(--hb-bubble,#fff);border:1px solid var(--hb-line,#e3e8f0);border-radius:10px;
                box-shadow:var(--hb-shadow-2,0 16px 40px rgba(0,0,0,.25))}
  .hb-mus2-menu button{display:block;width:100%;text-align:left;border:0;background:none;color:var(--hb-ink,#0d1622);
                       padding:7px 9px;border-radius:7px;font-size:13px;cursor:pointer;white-space:nowrap;
                       overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-menu button:hover{background:var(--mus-hover)}

` + CSS_PAGES;
