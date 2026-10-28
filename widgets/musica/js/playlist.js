// musica — the rows and the lists: likes, the add-to-list menu, panels, covers, the track row and its reorder, the
// playlist screen and the queue screen (refactor2710-12 T-03).
import { shell } from "./browse.js";
import { maybeEnrich, nowPlaying } from "./controls.js";
import { ICON_ADDLIST, ICON_CLOSE, ICON_EDIT, ICON_GRIP, ICON_HEART, ICON_HEART_FILL, ICON_NOTE,
  ICON_PLAY, ICON_QUEUE, ICON_SHUFFLE, ICON_TRASH, _norm, artNode, deriveArtistInfo, eqIcon, fire,
  h, iconBtn, nowPlayingMatches, playOne, svgEl, trackQuery, tt } from "./shared.js";
import { askName } from "./views.js";

// The favourites list is the SERVER's (`data.fav`): its id when it exists, the name the server would create.
export function favList(data){
  const f = data.fav || {};
  return (data.playlists || []).find(p => p.id === f.id) || null;
}
export function isLiked(t, data){
  const fl = favList(data);
  if(!fl) return false;
  const k = _norm(t.title || t.query) + "|" + _norm(t.artist);
  return (fl.tracks || []).some(x => (_norm(x.title || x.query) + "|" + _norm(x.artist)) === k);
}
export function likeBtn(t, data, ctx){
  const liked = isLiked(t, data);
  return iconBtn(liked ? ICON_HEART_FILL : ICON_HEART,
    liked ? tt("unlike", null, "Quitar de Favoritos") : tt("like", null, "Guardar en Favoritos"),
    () => {
      const fl = favList(data);
      if(liked && fl) fire(ctx, "remove_from_playlist", {playlist: fl.id, item: t.title || t.query});
      else fire(ctx, "add_to_playlist", {playlist: fl ? fl.id : ((data.fav || {}).name || "Favoritos"),
                                        title: t.title || t.query, artist: t.artist || "", query: trackQuery(t)});
    }, liked ? "on" : "");
}

// A tiny menu over the card: «add this song to which list». Closed by any click outside it.
export function openMenu(anchor, items){
  const root = anchor.closest(".hb-mus2-root");
  if(!root) return;
  root.querySelectorAll(".hb-mus2-menu").forEach(m => m.remove());
  const m = h("div", "hb-mus2-menu");
  items.forEach(it => {
    const b = h("button", null, it.label);
    b.onclick = (e) => { e.stopPropagation(); m.remove(); it.run(); };
    m.appendChild(b);
  });
  const r = anchor.getBoundingClientRect(), rr = root.getBoundingClientRect();
  m.style.top = Math.max(4, Math.min(rr.height - 250, r.bottom - rr.top + 4)) + "px";
  m.style.right = Math.max(4, rr.right - r.right) + "px";
  root.appendChild(m);
  const away = (e) => { if(!m.contains(e.target)){ m.remove(); document.removeEventListener("pointerdown", away, true); } };
  setTimeout(() => document.addEventListener("pointerdown", away, true), 0);
}
export function addToListBtn(t, data, ctx){
  return iconBtn(ICON_ADDLIST, tt("add_to_list", null, "Añadir a una lista"), (e) => {
    const items = (data.playlists || []).map(pl => ({label: pl.name, run: () => fire(ctx, "add_to_playlist",
      {playlist: pl.id, title: t.title || t.query, artist: t.artist || "", query: trackQuery(t)})}));
    items.push({label: "＋ " + tt("new_playlist", null, "Nueva lista"), run: () => {
      fire(ctx, "add_to_playlist", {playlist: (t.artist || t.title || tt("new_playlist", null, "Nueva lista")),
                                    title: t.title || t.query, artist: t.artist || "", query: trackQuery(t)});
    }});
    openMenu(e.currentTarget, items);
  });
}

// A shelf: ONE quiet panel with its own head (title, a count, actions on the right).
export function panel(title, count, actions){
  const sec = h("div", "hb-mus2-sec");
  const head = h("div", "hb-mus2-sechead");
  head.appendChild(h("div", "hb-mus2-sech", title));
  if(count != null && count !== "") head.appendChild(h("div", "hb-mus2-secn", String(count)));
  const right = h("div", "hb-mus2-secact");
  (actions || []).forEach(a => a && right.appendChild(a));
  head.appendChild(right);
  sec.appendChild(head);
  sec.head = head; sec.right = right;
  return sec;
}

export function pill(svg, label, onclick, cls){
  const b = h("button", "hb-mus2-pill" + (cls ? " " + cls : ""));
  if(svg) b.appendChild(svgEl(svg));
  b.appendChild(h("span", null, label));
  b.onclick = (e) => { e.stopPropagation(); onclick(e); };
  return b;
}

// A list's cover: its own art; else a MOSAIC of the first four different covers it holds; else one cover; else
// the gradient with the note (a heart for the favourites list).
export function coverOf(pl, isFav){
  if(pl.art) return artNode(pl.art, ICON_NOTE);
  const arts = [];
  (pl.tracks || []).forEach(t => { if(t.art && arts.indexOf(t.art) < 0) arts.push(t.art); });
  if(arts.length >= 4){
    const a = h("div", "hb-mus2-art hb-mus2-mosaic");
    arts.slice(0, 4).forEach(u => { const img = document.createElement("img"); img.src = u; img.alt = "";
                                    img.onerror = () => { img.style.visibility = "hidden"; }; a.appendChild(img); });
    return a;
  }
  if(arts.length) return artNode(arts[0], ICON_NOTE);
  const a = artNode(null, isFav ? ICON_HEART_FILL : ICON_NOTE);
  if(isFav) a.classList.add("fav");
  return a;
}

// ── TRACK ROWS ───────────────────────────────────────────────────────────────────────────────────────────
// Click SELECTS (visual, nothing sent); double-click — or the play button over the cover — PLAYS; the row's own
// buttons (heart, queue, add to a list, remove) are quiet until the row is under the pointer.
export function trackRow(t, ctx, opts){
  opts = opts || {};
  maybeEnrich(t, ctx);
  // `current` = the song the player holds; `playing` = it is SOUNDING now. Only the second animates.
  const current = !!(opts.current || opts.playing);
  const row = h("div", "hb-mus2-tr" + (current ? " current" : "") + (opts.playing ? " playing" : ""));
  if(opts.drag){
    const grip = h("div", "hb-mus2-grip"); grip.appendChild(svgEl(ICON_GRIP)); grip.title = tt("drag", null, "Arrastra para mover");
    row.appendChild(grip);
  }
  if(opts.index != null || current){
    const cell = h("div", "hb-mus2-trn");
    if(opts.playing) cell.appendChild(eqIcon());
    else if(current) cell.appendChild(svgEl(ICON_NOTE));        // paused: a still marker, never a meter
    else cell.textContent = opts.index;
    row.appendChild(cell);
  }
  const art = artNode(t.art, ICON_NOTE);
  const play = opts.play || (() => playOne(t, ctx));
  const pb = h("button", "hb-mus2-trplay"); pb.appendChild(svgEl(ICON_PLAY));
  pb.title = tt("play", null, "Reproducir");
  pb.onclick = (e) => { e.stopPropagation(); play(); };
  pb.ondblclick = (e) => e.stopPropagation();
  art.appendChild(pb);
  row.appendChild(art);
  const meta = h("div", "hb-mus2-trmeta");
  meta.appendChild(h("div", "hb-mus2-trt", opts.title || t.title || t.query || "—"));
  const times = t.count ? tt("times", {n: t.count}, "{n} veces") : "";
  const sub = opts.hideArtist ? times : [t.artist, times].filter(Boolean).join(" · ");
  if(sub) meta.appendChild(h("div", "hb-mus2-tra", sub));
  row.appendChild(meta);
  const x = h("div", "hb-mus2-trx");
  if(opts.data){
    x.appendChild(likeBtn(t, opts.data, ctx));
    if(opts.queue !== false) x.appendChild(iconBtn(ICON_QUEUE, tt("add_queue", null, "Añadir a la cola"),
                                                   () => fire(ctx, "queue", {query: trackQuery(t)})));
    if(opts.addToList) x.appendChild(addToListBtn(t, opts.data, ctx));
  }
  row.appendChild(x);
  row.onclick = () => {
    const list = row.parentElement;
    if(list) list.querySelectorAll(".hb-mus2-tr.selected").forEach(r => r.classList.remove("selected"));
    row.classList.add("selected");
  };
  row.ondblclick = () => play();
  if(opts.remove){
    const rm = h("button", "hb-mus2-x"); rm.appendChild(svgEl(ICON_CLOSE));
    rm.title = opts.removeTitle || tt("remove_track", null, "Quitar de la lista");
    rm.onclick = (e) => { e.stopPropagation(); opts.remove(); };
    rm.ondblclick = (e) => e.stopPropagation();
    row.appendChild(rm);
  }
  if(opts.drag) makeReorderable(row, opts.dragIndex, opts.drag);
  return row;
}

// One state model for every row: CURRENT when it is the song the player holds, PLAYING only while that song is
// actually sounding (`np.playing`, the player's own report) — never inferred from «is the current track».
export function rowState(t, np){
  const current = nowPlayingMatches(t, np);
  return {current, playing: current && !!(np && np.playing)};
}

// Reorder by dragging a row onto another (HTML5 drag and drop): ONE call on drop, never one per hover.
export function makeReorderable(row, index, onMove){
  row.draggable = true;
  row.dataset.idx = String(index);
  row.addEventListener("dragstart", (e) => { try{ e.dataTransfer.setData("text/plain", String(index));
                                                   e.dataTransfer.effectAllowed = "move"; }catch(_){} });
  row.addEventListener("dragover", (e) => { e.preventDefault(); row.classList.add("dragover"); });
  row.addEventListener("dragleave", () => row.classList.remove("dragover"));
  row.addEventListener("drop", (e) => {
    e.preventDefault(); row.classList.remove("dragover");
    let from = NaN;
    try{ from = parseInt(e.dataTransfer.getData("text/plain"), 10); }catch(_){}
    if(isFinite(from) && from !== index) onMove(from, index);
  });
}
// ── A LIST: cover (play button INSIDE it), name you can rename, actions, the tracklist you can reorder ──
export function playlistView(el, data, ctx, pl){
  const s = shell(el, data, ctx, "playlist", {back: "library"});
  const tracks = pl.tracks || [];
  const n = tracks.length;
  const derived = deriveArtistInfo(tracks);
  const head = h("div", "hb-mus2-head");
  const artwrap = h("div", "hb-mus2-artwrap");
  artwrap.appendChild(coverOf(pl, favList(data) === pl));
  const play = h("button", "hb-mus2-playfab"); play.appendChild(svgEl(ICON_PLAY));
  play.title = tt("play_playlist", null, "Reproducir esta lista");
  if(!n) play.disabled = true;
  play.onclick = () => fire(ctx, "play_playlist", {playlist: pl.id});
  artwrap.appendChild(play);
  head.appendChild(artwrap);
  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", tt("playlist", null, "Lista")));
  const name = h("div", "hb-mus2-headn", pl.name || tt("playlist", null, "Lista"));
  hm.appendChild(name);
  const subParts = [];
  if(derived.commonArtist) subParts.push(derived.commonArtist);
  subParts.push(`${n} ${n === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`);
  hm.appendChild(h("div", "hb-mus2-plsub", subParts.join(" · ")));
  const acts = h("div", "hb-mus2-acts");
  if(n) acts.appendChild(pill(ICON_SHUFFLE, tt("shuffle", null, "Aleatorio"),
                              () => fire(ctx, "play_playlist", {playlist: pl.id, shuffle: true})));
  acts.appendChild(iconBtn(ICON_EDIT, tt("rename", null, "Renombrar"), () => {
    const inp = askName(name, (v) => fire(ctx, "rename_playlist", {playlist: pl.id, name: v}), pl.name);
    inp.className = "hb-mus2-renin";
  }));
  const del = iconBtn(ICON_TRASH, tt("delete", null, "Borrar lista"), () => {
    // A whole list is a sweep: asked here, on the card, before it is gone.
    acts.textContent = "";
    acts.appendChild(h("span", "hb-mus2-plsub", tt("delete_q", {name: pl.name}, "¿Borrar «{name}»?")));
    acts.appendChild(pill(ICON_TRASH, tt("delete_yes", null, "Borrar"), () => fire(ctx, "delete_playlist", {playlist: pl.id}), "risk"));
    acts.appendChild(pill(null, tt("cancel", null, "Cancelar"), () => fire(ctx, "open_view", {kind: "playlist", id: pl.id})));
  }, "risk");
  acts.appendChild(del);
  hm.appendChild(acts);
  head.appendChild(hm);
  s.scroll.appendChild(head);

  const sec = panel(tt("songs", null, "Canciones"), n || "", []);
  const g = h("div", "hb-mus2-grid");
  const np = nowPlaying(data);
  if(n){
    tracks.forEach((t, i) => g.appendChild(trackRow(t, ctx, {
      index: String(i + 1),
      remove: () => fire(ctx, "remove_from_playlist", {playlist: pl.id, item: String(i + 1)}),
      title: derived.commonArtist ? derived.strip(t.title) : null,
      hideArtist: !!derived.commonArtist,
      ...rowState(t, np),
      // a song in a list plays IN the list: from this one on, the rest queued behind it
      play: () => fire(ctx, "play_playlist", {playlist: pl.id, from: String(i + 1)}),
      data, queue: true,
      drag: (from, to) => fire(ctx, "move_track", {playlist: pl.id, item: String(from + 1), to: String(to + 1)}),
      dragIndex: i,
    })));
  } else {
    g.appendChild(h("div", "hb-mus2-empty", tt("playlist_empty", null, "Lista vacía. Dime «añade una canción a esta lista».")));
  }
  sec.appendChild(g);
  s.scroll.appendChild(sec);
  s.done();
}

// ── THE QUEUE: what sounds now, and what comes next (editable where the player allows it) ───────────────
export function queueView(el, data, ctx){
  const s = shell(el, data, ctx, "queue");
  const np = nowPlaying(data);
  const q = data.queue || {};
  const items = q.items || [];
  if(np){
    const cur = panel(tt("now_title", null, "Sonando ahora"), null, []);
    const g = h("div", "hb-mus2-grid");
    g.appendChild(trackRow(np, ctx, {current: true, playing: !!np.playing, data, queue: false, play: () => fire(ctx, np.playing ? "pause" : "resume")}));
    cur.appendChild(g); s.scroll.appendChild(cur);
  }
  const acts = [];
  if(q.editable && items.length) acts.push(pill(ICON_TRASH, tt("queue_clear", null, "Vaciar"), () => fire(ctx, "queue_clear", {})));
  const sec = panel(tt("queue_title", null, "A continuación"), items.length || "", acts);
  if(!q.editable && items.length) sec.appendChild(h("div", "hb-mus2-note",
    tt("queue_readonly", null, "Esta cola se ve aquí; para cambiarla, usa la app de Spotify.")));
  const g = h("div", "hb-mus2-grid");
  items.forEach((t, i) => g.appendChild(trackRow(t, ctx, {
    index: String(i + 1), data, queue: false,
    remove: q.editable ? () => fire(ctx, "queue_remove", {item: String(i + 1)}) : null,
    removeTitle: tt("remove_queue", null, "Quitar de la cola"),
    drag: q.editable ? (from, to) => fire(ctx, "queue_move", {item: String(from + 1), to: String(to + 1)}) : null,
    dragIndex: i,
  })));
  if(!items.length) g.appendChild(h("div", "hb-mus2-empty", tt("queue_empty", null, "No hay nada en cola. Añade canciones con ＋ desde cualquier lista.")));
  sec.appendChild(g);
  s.scroll.appendChild(sec);
  s.done();
}
