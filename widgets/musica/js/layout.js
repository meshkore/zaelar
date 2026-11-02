// musica — ONE app, two kinds of screen (the responsive pass). Everything here is PRESENTATION: the views, the
// playback, the queue and the lists are the same objects on every screen, and switching size never resets any of
// them — the face is server state (`data.view`), the players are persistent hosts (widget.js), and the only local
// state is the sidebar's collapsed flag (a per-viewer convenience) and the volume popover.
//
// The layout is read from the card's REAL box, never from the device: a desktop window can be narrow, a tablet can
// be wide. Four arrangements:
//   wide     ≥1100 px desktop       sidebar (collapsible) · content · queue panel beside the song · full bar
//   compact  700-1099 px desktop    icon rail · content · queue as a drawer · full bar
//   narrow   <700 px desktop        a tab strip in the one bar · content · full bar · queue as a sheet
//   mobile   the phone shell        bottom navigation · mini-player · expanded player · queue as a sheet
// A card inside the phone shell (`.zm-scroll`) or on a coarse-pointer small screen is `mobile`; a tablet-sized one
// (both sides ≥700) gets `compact` — the touch rules still apply there through `(hover:none)`.
import { nowPlaying } from "./controls.js";
import { ICON_HOME, ICON_LIBRARY, ICON_NEXT, ICON_NOTE, ICON_PAUSE, ICON_PLAY, ICON_QUEUE, ICON_SEARCH,
  ICON_SIDEBAR, artNode, fire, h, svgEl, tt } from "./shared.js";

export function inShell(el){ return !!(el && el.closest && el.closest(".zm-scroll")); }

function smallTouchScreen(){
  try{
    const coarse = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
    return !!coarse && Math.min(window.screen.width, window.screen.height) < 600;
  }catch(_){ return false; }
}

export function layoutOf(el){
  const w = el.clientWidth || 0, hgt = el.clientHeight || 0;
  const touch = inShell(el) || smallTouchScreen();
  let mode;
  if(touch) mode = (w >= 700 && hgt >= 700) ? "compact" : "mobile";
  else mode = w >= 1100 ? "wide" : (w >= 700 ? "compact" : "narrow");
  const land = mode === "mobile" && w > hgt && hgt < 520;
  return {mode, land, key: mode + (land ? ":land" : "")};
}

// Which destination a face belongs to — the tab that lights up. `home` is ADAPTIVE (V2-717): the song while one
// sounds, the library otherwise, so it lights whichever of the two it is actually showing.
export function tabOf(kind, data){
  if(kind === "home") return nowPlaying(data) ? "now" : "home";
  if(kind === "library") return "home";
  if(kind === "collection" || kind === "playlist") return "collection";
  if(kind === "search" || kind === "artist" || kind === "album") return "search";
  if(kind === "now" || kind === "queue") return "now";
  return "";
}

const DESTS = [
  {id: "home", kind: "library", icon: ICON_HOME, label: () => tt("nav_home", null, "Inicio")},
  {id: "search", kind: "search", icon: ICON_SEARCH, label: () => tt("nav_search", null, "Buscar")},
  {id: "collection", kind: "collection", icon: ICON_LIBRARY, label: () => tt("nav_collection", null, "Tu música")},
  {id: "now", kind: "now", icon: ICON_NOTE, label: () => tt("nav_now", null, "Sonando")},
];

function navBtn(d, active, ctx, cls){
  const b = h("button", cls + (active ? " on" : ""));
  b.appendChild(svgEl(d.icon));
  b.appendChild(h("span", null, d.label()));
  b.setAttribute("aria-label", d.label());
  if(active) b.setAttribute("aria-current", "page");
  b.onclick = () => fire(ctx, "open_view", {kind: d.kind});
  return b;
}

// The phone's (and the narrow window's) navigation: four destinations at the foot, each a 44 px target at least.
export function bottomNav(data, ctx, kind){
  const nav = h("nav", "hb-mus2-bnav");
  nav.setAttribute("aria-label", tt("nav_label", null, "Música"));
  const tab = tabOf(kind, data);
  DESTS.forEach(d => nav.appendChild(navBtn(d, tab === d.id, ctx, "hb-mus2-bnavb")));
  return nav;
}

// The narrow window's navigation: the same destinations as a one-row strip in the card's one bar (a small desktop
// card cannot spend 50 px of its height on a second bar), plus the queue while there is one.
export function navTabs(data, ctx, kind){
  const seg = h("div", "hb-mus2-seg");
  seg.setAttribute("role", "tablist");   // one row of views — never wraps into a two-line pill
  const tab = tabOf(kind, data);
  const list = DESTS.slice();
  if(((data.queue || {}).items || []).length || kind === "queue")
    list.push({id: "queue", kind: "queue", icon: ICON_QUEUE, label: () => tt("tab_queue", null, "Cola")});
  list.forEach(d => {
    const on = kind === "queue" ? d.id === "queue" : tab === d.id;
    const b = navBtn(d, on, ctx, "hb-mus2-segb");
    b.setAttribute("role", "tab"); b.setAttribute("aria-selected", on ? "true" : "false");
    seg.appendChild(b);
  });
  return seg;
}

// The desktop's navigation: the same four destinations, the queue, and the lists one click away. Collapsible; the
// compact layout always shows it as an icon rail.
const SIDE_KEY = "hb-mus2-side-collapsed";
function readCollapsed(){ try{ return window.localStorage.getItem(SIDE_KEY) === "1"; }catch(_){ return false; } }
function writeCollapsed(v){ try{ window.localStorage.setItem(SIDE_KEY, v ? "1" : "0"); }catch(_){} }

export function sidebar(el, data, ctx, kind, mode){
  const rail = mode === "compact" || readCollapsed();
  const side = h("nav", "hb-mus2-side" + (rail ? " rail" : ""));
  side.setAttribute("aria-label", tt("nav_label", null, "Música"));
  if(mode === "wide"){
    const tog = h("button", "hb-mus2-sidetog");
    tog.appendChild(svgEl(ICON_SIDEBAR));
    const lbl = rail ? tt("expand_side", null, "Mostrar el menú") : tt("collapse_side", null, "Contraer el menú");
    tog.title = lbl; tog.setAttribute("aria-label", lbl);
    tog.onclick = () => { writeCollapsed(!rail); if(el._hbRedraw) el._hbRedraw(); };
    side.appendChild(tog);
  }
  const tab = tabOf(kind, data);
  DESTS.forEach(d => {
    const b = navBtn(d, tab === d.id && !(kind === "queue" && d.id === "now"), ctx, "hb-mus2-sideb");
    if(rail) b.title = d.label();
    side.appendChild(b);
  });
  const q = navBtn({id: "queue", kind: "queue", icon: ICON_QUEUE, label: () => tt("tab_queue", null, "Cola")}, kind === "queue", ctx, "hb-mus2-sideb");
  if(rail) q.title = tt("tab_queue", null, "Cola");
  side.appendChild(q);
  if(!rail){
    const pls = data.playlists || [];
    if(pls.length){
      side.appendChild(h("div", "hb-mus2-sidek", tt("your_playlists", null, "Tus listas")));
      const box = h("div", "hb-mus2-sidepls");
      const vid = (data.view || {}).id;
      pls.forEach(pl => {
        const b = h("button", "hb-mus2-sidepl" + (kind === "playlist" && vid === pl.id ? " on" : ""), pl.name || tt("playlist", null, "Lista"));
        b.title = pl.name || "";
        b.onclick = () => fire(ctx, "open_view", {kind: "playlist", id: pl.id});
        box.appendChild(b);
      });
      side.appendChild(box);
    }
  }
  return side;
}

// ── THE MINI-PLAYER (phone): art, title, artist, play/pause, next — and a thin progress line on its top edge.
// Tapping it opens the expanded player. No volume, modes or queue here on purpose: those live in the big one.
export function miniPlayer(el, data, ctx, playback){
  const np = nowPlaying(data);
  if(!np) return null;
  const mini = h("div", "hb-mus2-mini");
  mini.setAttribute("role", "button");
  mini.setAttribute("aria-label", tt("open_player", null, "Abrir el reproductor"));
  const line = h("div", "hb-mus2-miniprog"); const fill = h("b"); line.appendChild(fill);
  mini.appendChild(line);
  mini.appendChild(artNode(np.art, ICON_NOTE));
  const meta = h("div", "hb-mus2-minimeta");
  meta.appendChild(h("div", "hb-mus2-minit", np.title || tt("music_fb", null, "Música")));
  if(np.artist) meta.appendChild(h("div", "hb-mus2-minia", np.artist));
  mini.appendChild(meta);
  const playing = !!np.playing;
  const mk = (svg, action, label, cls) => {
    const b = h("button", "hb-mus2-minib" + (cls ? " " + cls : ""));
    b.appendChild(svgEl(svg)); b.title = label; b.setAttribute("aria-label", label);
    b.onclick = (e) => { e.stopPropagation(); fire(ctx, action); };
    return b;
  };
  mini.appendChild(mk(playing ? ICON_PAUSE : ICON_PLAY, playing ? "pause" : "resume",
                      playing ? tt("pause", null, "Pausa") : tt("play", null, "Reproducir"), "main"));
  mini.appendChild(mk(ICON_NEXT, "next", tt("next", null, "Siguiente")));
  mini.onclick = () => fire(ctx, "open_view", {kind: "now"});
  el._hbTickers.push(() => {
    const pb = playback(el, data, ctx);
    fill.style.width = (pb && pb.dur ? Math.max(0, Math.min(1, pb.pos / pb.dur)) * 100 : 0) + "%";
  });
  return mini;
}
