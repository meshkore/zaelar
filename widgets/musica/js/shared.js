// musica — what every part of the card shares: the icon set, the DOM helpers, the cover art, the now-playing match,
// the small control pieces and the i18n seam (refactor2710-12 T-03).
// ── icon set, "our line" (V2-629): the app shell's own, imported (V2-831 T-12) — never a copy that drifts.
import * as I from "/frontend/app/lib/icons.js";
export const ICON_NOTE = I.MUSIC_ICON, ICON_PLUS = I.PLUS_ICON, ICON_BACK = I.CHEVRON_LEFT_ICON, ICON_CLOSE = I.CLOSE_ICON,
  ICON_PREV = I.PREV_ICON, ICON_NEXT = I.NEXT_ICON, ICON_PLAY = I.PLAY_ICON, ICON_PAUSE = I.PAUSE_ICON,
  ICON_VOL_OFF = I.VOLUME_X_ICON, ICON_VOL_UP = I.VOLUME_UP_ICON, ICON_LIST = I.LIST_ICON, ICON_QUEUE = I.QUEUE_ICON,
  ICON_SEARCH = I.SEARCH_ICON, ICON_SHUFFLE = I.SHUFFLE_ICON, ICON_REPEAT = I.REPEAT_ICON,
  ICON_REPEAT_ONE = I.REPEAT_ONE_ICON, ICON_EDIT = I.EDIT_ICON, ICON_TRASH = I.TRASH_ICON, ICON_GRIP = I.GRIP_ICON,
  ICON_ADDLIST = I.LIST_ADD_ICON, ICON_HEART = I.HEART_ICON, ICON_HEART_FILL = I.HEART_FILL_ICON;

// Raw SVG markup -> element (same trick as frontend/app/core/dom.js::raw).
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
