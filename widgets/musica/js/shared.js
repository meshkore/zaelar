// musica — what every part of the card shares: the icon set, the DOM helpers, the cover art, the now-playing match,
// the small control pieces and the i18n seam (refactor2710-12 T-03).
// ── icon set, "our line" (V2-629) ────────────────────────────────────────────────────────────────────────
// Two attribute sets, never combined on one <svg> — the HTML parser keeps the FIRST occurrence of a duplicate
// attribute, so an outline base plus a later fill override stays an outline forever.
export const _SW = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
           'stroke-linejoin="round"';                                            // OUTLINE icons
export const _SF = 'viewBox="0 0 24 24" fill="currentColor" stroke="none"';              // SOLID icons
export const ICON_NOTE      = `<svg ${_SW}><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;
export const ICON_PLUS       = `<svg ${_SW}><path d="M12 5v14"/><path d="M5 12h14"/></svg>`;
export const ICON_BACK       = `<svg ${_SW}><path d="m15 18-6-6 6-6"/></svg>`;
export const ICON_CLOSE      = `<svg ${_SW}><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`;
export const ICON_PREV       = `<svg ${_SW}><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>`;
export const ICON_NEXT       = `<svg ${_SW}><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>`;
export const ICON_PLAY       = `<svg ${_SF}><path d="M8 5v14l11-7z"/></svg>`;
export const ICON_PAUSE      = `<svg ${_SF}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
export const ICON_VOL_OFF    = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>`;
export const ICON_VOL_UP     = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
export const ICON_LIST       = `<svg ${_SW}><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>`;
export const ICON_QUEUE      = `<svg ${_SW}><path d="M3 6h13"/><path d="M3 12h9"/><path d="M3 18h9"/><path d="m16 13 5 3-5 3z"/></svg>`;
export const ICON_SEARCH     = `<svg ${_SW}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`;
export const ICON_SHUFFLE    = `<svg ${_SW}><path d="M16 3h5v5"/><path d="M4 20 21 3"/><path d="M21 16v5h-5"/><path d="m15 15 6 6"/><path d="M4 4l5 5"/></svg>`;
export const ICON_REPEAT     = `<svg ${_SW}><path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/></svg>`;
export const ICON_REPEAT_ONE = `<svg ${_SW}><path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/><path d="M11 10h1v4"/></svg>`;
export const ICON_EDIT       = `<svg ${_SW}><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>`;
export const ICON_TRASH      = `<svg ${_SW}><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>`;
export const ICON_GRIP       = `<svg ${_SW}><circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/></svg>`;
export const ICON_ADDLIST    = `<svg ${_SW}><path d="M3 6h12"/><path d="M3 12h12"/><path d="M3 18h8"/><path d="M18 14v8"/><path d="M14 18h8"/></svg>`;
export const ICON_HEART      = `<svg ${_SW}><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z"/></svg>`;
export const ICON_HEART_FILL = `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" ` +
  `stroke-linecap="round" stroke-linejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 ` +
  `0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z"/></svg>`;

// Raw SVG markup -> element (same trick as frontend/app/core/dom.js::raw — duplicated, widgets never import
// app-shell code).
export function svgEl(markup){
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild;
}

export function h(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

// Animated "now playing" bars — the visible signal that THIS row/mini-player is the one making sound.
export function eqIcon(){
  const wrap = h("div", "hb-mus2-eq");
  wrap.appendChild(h("span")); wrap.appendChild(h("span")); wrap.appendChild(h("span"));
  return wrap;
}

// Cover art: image (Spotify URL) or fallback emoji. URL goes into img.src, never innerHTML.
export function artNode(art, fallback){
  const a = h("div", "hb-mus2-art");
  const paintFallback = () => { a.textContent = ""; a.appendChild(svgEl(fallback || ICON_NOTE)); };
  if(art){
    const img = document.createElement("img"); img.src = art; img.alt = "";
    // A dead or since-removed thumbnail (V2-629) degrades to the SAME placeholder a missing one gets,
    // instead of the browser's broken-image glyph — cheap, and it is what "a player nicer than the rest"
    // means for the one part of this that is a hotlink to somebody else's server (the V2-563 fact of life).
    img.onerror = paintFallback;
    a.appendChild(img);
  }
  // A crisp SVG placeholder instead of an emoji glyph (V2-629): an emoji font renders differently per OS —
  // the exact "looks like a different app" seam a redesign is supposed to close — an inline vector does not.
  else paintFallback();
  return a;
}

// Text compare for "is this the track that's playing" — accent/case-insensitive, same spirit as the server's
// own `_norm` (data.py), kept separately here because widget.js never imports server code (V2-557).
export function _norm(s){
  return String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

export function nowPlayingMatches(t, np){
  if(!np) return false;
  const a = _norm(t.title || t.query), b = _norm(np.title);
  if(!a || !b) return false;
  const aa = _norm(t.artist), ba = _norm(np.artist);
  if(a === b) return (aa && ba) ? aa === ba : true;   // missing artist on either side: the title match is enough
  // A legacy merged title ("madonna papa don't preach", no separate artist field) played through a CONNECTED
  // provider reports its own clean, real title ("papa don't preach") — a plain equality never matches, so this
  // row would never light up for the exact case the redesign exists to fix. If the stored title ENDS with the
  // now-playing title, treat the leftover prefix as the artist and require it to agree with `np.artist` when
  // that is known — a bare suffix match with no artist to cross-check would risk lighting up an unrelated song
  // that merely ends the same way.
  if(!aa && b.length > 3 && a.endsWith(b)){
    const prefix = a.slice(0, a.length - b.length).trim();
    return !ba || prefix === ba || prefix.endsWith(ba);
  }
  return false;
}

// A playlist where every track shares the SAME artist should say that artist ONCE (the header), not on every
// row — the operator's complaint on a playlist that happened to be one Madonna album, titles like "Madonna
// Papa Don't Preach" repeated verbatim in each row. Two cases: (1) tracks already carry a proper `artist`
// field, uniformly — show it, strip nothing (`title`/`artist` were already separate). (2) legacy/free-text
// data where the artist got baked INTO `title` with no separator (a bare `query` used as the title, V2-384's
// "one call is all the model gets" combined with a search string that already had the artist inside it): if
// EVERY track's title starts with the same leading word(s) and something real is left over after them, treat
// that shared prefix as the artist for DISPLAY ONLY — the stored data is never touched, so this is always
// reversible and never invents a fact that is not already, verbatim, in every row.
export function deriveArtistInfo(tracks){
  const list = tracks || [];
  const noStrip = {commonArtist: "", strip: (title) => title};
  if(list.length < 2) return noStrip;

  const artists = list.map(t => String(t.artist || "").trim());
  if(artists.every(a => a)){
    return (new Set(artists.map(_norm)).size === 1) ? {commonArtist: artists[0], strip: (t) => t} : noStrip;
  }
  if(artists.some(a => a)) return noStrip;   // mixed metadata quality (some tagged, some not) — don't guess

  const wordLists = list.map(t => String(t.title || "").trim().split(/\s+/).filter(Boolean));
  const minWords = Math.min(...wordLists.map(w => w.length));
  if(minWords < 2) return noStrip;
  let k = 0;
  for(let i = 0; i < minWords - 1; i++){       // leave at least one real word behind as the title
    const w0 = _norm(wordLists[0][i]);
    if(!w0 || !wordLists.every(w => _norm(w[i]) === w0)) break;
    k = i + 1;
  }
  if(k === 0) return noStrip;
  const commonArtist = wordLists[0].slice(0, k).join(" ");
  return {
    commonArtist,
    strip: (title) => {
      const words = String(title || "").trim().split(/\s+/);
      return words.length > k ? words.slice(k).join(" ") : title;
    },
  };
}
// ── small shared pieces (V2-795) ─────────────────────────────────────────────────────────────────────────
export function fire(ctx, name, payload){
  // Fire-and-forget like every control here; tolerant of a ctx whose action returns nothing thenable.
  try{ const p = ctx.action(name, payload); if(p && typeof p.catch === "function") p.catch(() => {}); return p; }
  catch(_){ return null; }
}

export function iconBtn(svg, title, onclick, cls){
  const b = h("button", "hb-mus2-ibtn" + (cls ? " " + cls : ""));
  b.appendChild(svgEl(svg));
  if(title){ b.title = title; b.setAttribute("aria-label", title); }
  if(onclick) b.onclick = (e) => { e.stopPropagation(); onclick(e); };
  b.ondblclick = (e) => e.stopPropagation();
  return b;
}

export function trackQuery(t){
  return t.query || [t.title, t.artist].filter(Boolean).join(" ") || t.title || "";
}

// What a play of ONE catalogue/library track asks: its words, plus its uri when it has one (the server keeps the
// uri only if the provider playing now is the one that minted it).
export function playOne(t, ctx){
  const p = {query: trackQuery(t)};
  if(t.uri) p.uri = t.uri;
  if(t.provider) p.provider = t.provider;
  fire(ctx, "play", p);
}
// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
let _T = null;

// Bound once per render, here: an imported binding is read-only, so the module that declares `_T` writes it.
export function bindT(ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
}
export function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.musica."+key, params); if(s && s!=="widgets.musica."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}
