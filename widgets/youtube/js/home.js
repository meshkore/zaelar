// youtube widget — the Inicio face: its head with the search box and the dashboard bands.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { ICON_SEARCH, ICON_CLEAR, svgEl, el, tt } from "./shared.js";

export function fmtAge(ts){
  if(!ts) return "";
  const m = Math.max(0, Math.round((Date.now() / 1000 - Number(ts)) / 60));
  if(m < 1) return tt("age_now", null, "ahora mismo");
  if(m < 60) return tt("age_min", {n: m}, "hace " + m + " min");
  return tt("age_hour", {n: Math.round(m / 60)}, "hace " + Math.round(m / 60) + " h");
}

export function buildHomeHead(root, ctx, body){
  // INICIO's head (2026-09-29): the title of what the grid holds + a real search box. Built once here and
  // only its TEXT refreshed per render, so a repaint mid-typing never eats the words (see the CSS note).
  const homeHead = el("div", "hb-yt-homehead");
  const homeTitle = el("div", "hb-yt-hometitle");
  homeHead.appendChild(homeTitle);
  const sForm = el("form", "hb-yt-search");
  sForm.setAttribute("role", "search");
  const sInp = el("input", "");
  sInp.type = "search";
  sInp.name = "q";
  sInp.autocomplete = "off";
  sInp.placeholder = tt("search_ph", null, "Buscar en YouTube…");
  sInp.setAttribute("aria-label", tt("search_label", null, "Buscar vídeos"));
  sForm.appendChild(sInp);
  const sClr = el("button", "hb-yt-sbtn");
  sClr.type = "button";
  sClr.appendChild(svgEl(ICON_CLEAR));
  sClr.title = tt("clear_results", null, "Quitar los resultados de búsqueda");
  sClr.setAttribute("aria-label", sClr.title);
  sClr.addEventListener("click", () => {
    sInp.value = "";
    const dd = root._hbYtData || {};
    if(ctx && ctx.action && ((dd.search_results || []).length || dd.search_query)) ctx.action("clear_search", {});
    sClr.style.display = "none";
    sInp.focus();
  });
  sForm.appendChild(sClr);
  const sGo = el("button", "hb-yt-sbtn go");
  sGo.type = "submit";
  sGo.appendChild(svgEl(ICON_SEARCH));
  sGo.title = tt("search_go", null, "Buscar");
  sGo.setAttribute("aria-label", sGo.title);
  sForm.appendChild(sGo);
  sInp.addEventListener("input", () => { sClr.style.display = sInp.value ? "" : "none"; });
  sForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = (sInp.value || "").trim();
    if(!q || !ctx || !ctx.action) return;
    sInp.blur();
    ctx.action("search", {query: q});                  // the same data-op the voice uses; nothing plays
  });
  homeHead.appendChild(sForm);
  body.appendChild(homeHead);
  const home = el("div", "hb-yt-home");             // populated on every render, like the list below
  body.appendChild(home);
  const blockedLine = el("div", "hb-yt-blocked", "");
  body.appendChild(blockedLine);
  const conn = el("div", "hb-yt-conn");             // connect screens (V2-597), rebuilt per render
  body.appendChild(conn);
  return {homeTitle, sInp, sClr, home, blockedLine, conn};
}

export function paintHomeHead(E, data){
  // INICIO's head: the title says what the grid holds; the box carries the question being answered —
  // unless he is typing in it right now, in which case his words win over the repaint.
  if(E.homeTitle){
    const nR = Array.isArray(data.search_results) ? data.search_results.length : 0;
    E.homeTitle.textContent = "";
    E.homeTitle.appendChild(el("span", "", (nR || data.adding) ? tt("results", null, "Resultados")
                                                               : tt("home_title", null, "Inicio")));
    if(nR) E.homeTitle.appendChild(el("span", "hb-yt-homecount", String(nR)));
  }
  if(E.sInp && document.activeElement !== E.sInp){
    E.sInp.value = String(data.adding || data.search_query || "");
    if(E.sClr) E.sClr.style.display = E.sInp.value ? "" : "none";
  }
}

export function paintHome(root, E, data, ctx){
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
      sh.appendChild(el("span", "", tt("searching_q", {q: data.adding}, "Buscando «{q}»…")));
      E.home.appendChild(sh);
    }
    if(res.length){
      // The query and its ✕ live in the search box of the head above (2026-09-29): the grid is only tiles.
      res.forEach((it, i) => {
        const addB = el("button", "hb-yt-radd", tt("to_queue", null, "+ cola"));
        addB.title = tt("to_queue_hint", null, "Añadir a la cola sin reproducir");
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
      hh.appendChild(el("span", "", tt("recent", null, "Vistos hace poco")));
      const all = el("span", "hb-yt-chip", tt("all_history", null, "⏱ todo el historial → cola"));
      all.title = tt("all_history_hint", null, "Carga el historial completo en la cola");
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
      sh.appendChild(el("span", "", tt("subs_suggestions", null, "Sugerencias de tus suscripciones")));
      const bits = [];
      if(data.suggested_at) bits.push(fmtAge(data.suggested_at));
      if(data.suggested_channels) bits.push(tt("n_channels", {n: data.suggested_channels}, "{n} canales"));
      if(bits.length) sh.appendChild(el("span", "hb-yt-sugsub", "· " + bits.join(" · ")));
      const rf = el("span", "hb-yt-chip", data.suggesting ? tt("loading", null, "buscando…") : tt("refresh", null, "↻ refrescar"));
      rf.title = tt("refresh_hint", null, "Traer los vídeos recientes de tus suscripciones");
      rf.addEventListener("click", () => { if(ctx && ctx.action && !data.suggesting) ctx.action("suggest", {}); });
      sh.appendChild(rf);
      E.home.appendChild(sh);
      if(!sug.length && !data.suggesting)
        E.home.appendChild(el("div", "hb-yt-homemsg",
          tt("subs_empty", null, "Toca «refrescar» para traer los vídeos recientes de tus suscripciones.")));
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
    if(prefs.min_definition) pbits.push(tt("min_def", {n: prefs.min_definition}, "mínimo {n}p"));
    if(prefs.captions === true) pbits.push(tt("cc_on", null, "subtítulos siempre"));
    if(prefs.captions === false) pbits.push(tt("cc_off", null, "sin subtítulos"));
    if(prefs.volume != null) pbits.push(tt("volume_n", {n: prefs.volume}, "volumen {n}"));
    notes.forEach((n) => { const t = String(n && n.text || "").trim(); if(t) pbits.push(tt("note", {text: t}, "nota: {text}")); });
    if(pbits.length) E.home.appendChild(el("div", "hb-yt-libp", pbits.join(" · ")));

    if(!res.length && !hist.length && !sug.length && !connectedAny && !data.adding && !data.suggesting){
      E.home.appendChild(el("div", "hb-yt-homemsg",
        tt("home_empty", null, "No hay ningún vídeo cargado. Dime qué quieres ver, o «búscame vídeos de…» y elige de aquí.")));
    }
  }
}
