// youtube widget — the queue (Cola) and the saved lists (Listas) faces.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { el, tt } from "./shared.js";

export function buildQueueBoxes(ctx, body){
  // The QUEUE (V2-366; V2-632 gives every row a thumbnail — «que se intuya mejor de qué vídeo hablamos»).
  const listBox = el("div", "hb-yt-list");
  body.appendChild(listBox);
  const subsBox = el("div", "hb-yt-subs");             // V2-632: followed authors, OUR references
  body.appendChild(subsBox);
  const listsBox = el("div", "hb-yt-mylists");         // V2-632: saved lists
  body.appendChild(listsBox);
  const addRow = el("div", "hb-yt-addrow");
  const addInp = el("input", "hb-yt-addinp");
  addInp.placeholder = tt("add_ph", null, "Pega un enlace de YouTube o escribe un título…");
  const addBtn = el("button", "hb-yt-btn", tt("add", null, "＋ Añadir"));
  const doAdd = () => {
    const v = (addInp.value || "").trim();
    if(!v || !ctx || !ctx.action) return;
    addInp.value = "";
    ctx.action("add", {url: v});                       // the server tries link/id first, then searches by name
  };
  addBtn.addEventListener("click", doAdd);
  addInp.addEventListener("keydown", (e) => { if(e.key === "Enter") doAdd(); });
  addRow.appendChild(addInp); addRow.appendChild(addBtn);
  body.appendChild(addRow);
  return {listBox, subsBox, listsBox};
}

export function paintQueue(root, E, data, ctx){
  // The list rows, re-rendered on every render (text only; the iframe is never touched by this).
  if(E.listBox){
    E.listBox.textContent = "";
    const lst = Array.isArray(data.list) ? data.list : [];
    const filt = String(data.list_filter || "").trim().toLowerCase();
    // V2-467 — the list NAME takes precedence over the generic label: if the operator called it “the afternoon
    // one,” that is what must be shown on the card so they can verify at a glance that their request was followed.
    const _nom = String(data.list_name || "").trim();
    const _rot = _nom || tt("list", null, "Lista");
    const head = el("div", "hb-yt-listh", lst.length ? (_rot + " · " + lst.length) : _rot);
    if(filt){
      const chip = el("span", "hb-yt-chip", tt("filter_chip", {q: filt}, "filtro: «{q}» ✕"));
      chip.title = tt("clear_filter", null, "Quitar el filtro");
      chip.addEventListener("click", () => { if(ctx && ctx.action) ctx.action("filter_list", {q: ""}); });
      head.appendChild(chip);
    }
    E.listBox.appendChild(head);
    if(data.adding) E.listBox.appendChild(el("div", "hb-yt-note", tt("searching_q", {q: data.adding}, "Buscando «{q}»…")));
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
      // V2-791 — with WHEN it was published: «which of these is today's?» is read at a glance
      const sub = [it.channel, it.published].filter(Boolean).join(" · ");
      if(sub) row.appendChild(el("span", "hb-yt-rowc", sub));
      const x = el("button", "hb-yt-rowx", "✕");
      x.title = tt("remove_from_list", null, "Quitar de la lista");
      x.addEventListener("click", (e) => { e.stopPropagation(); if(ctx && ctx.action) ctx.action("remove", {item: String(i + 1)}); });
      row.appendChild(x);
      row.addEventListener("click", () => {
        if(ctx && ctx.action) ctx.action("play_item", {item: String(i + 1)});
        if(root._hbYtSelectTab) root._hbYtSelectTab("player");
      });
      E.listBox.appendChild(row);
    });
    if(lst.length && filt && !shown) E.listBox.appendChild(el("div", "hb-yt-note", tt("list_no_match", null, "Nada en la lista casa con el filtro.")));
    if(!lst.length) E.listBox.appendChild(el("div", "hb-yt-note", tt("list_empty", null, "La lista está vacía: pega un enlace o dime «añade a la lista…».")));
  }
}

export function paintSavedLists(root, E, data, ctx){
  // SAVED LISTS tab (V2-632).
  if(E.listsBox){
    E.listsBox.textContent = "";
    const saved = Array.isArray(data.lists) ? data.lists : [];
    E.listsBox.appendChild(el("div", "hb-yt-listh", tt("saved_lists_n", {n: saved.length}, "Listas guardadas · {n}")));
    if(!saved.length){
      E.listsBox.appendChild(el("div", "hb-yt-secmsg",
        tt("lists_empty", null, "No hay listas guardadas. Monta una cola y di «guarda la lista como…».")));
    }
    saved.forEach((L) => {
      const nom = String(L && L.name || "").trim();
      if(!nom) return;
      const row = el("div", "hb-yt-row");
      row.appendChild(el("span", "hb-yt-rown", "≣"));
      row.appendChild(el("span", "hb-yt-rowt", nom));
      row.appendChild(el("span", "hb-yt-rowc", tt("n_videos", {n: Array.isArray(L.items) ? L.items.length : 0}, "{n} vídeos")));
      const open = el("span", "hb-yt-chip", tt("open_to_queue", null, "abrir → cola"));
      open.addEventListener("click", (e) => {
        e.stopPropagation();
        if(ctx && ctx.action) ctx.action("open_list", {name: nom});
        if(root._hbYtSelectTab) root._hbYtSelectTab("cola");
      });
      row.appendChild(open);
      const x = el("button", "hb-yt-rowx", "✕");
      x.title = tt("delete_list", null, "Borrar la lista guardada");
      x.addEventListener("click", (e) => {
        e.stopPropagation();
        if(ctx && ctx.action) ctx.action("delete_list", {name: nom});
      });
      row.appendChild(x);
      E.listsBox.appendChild(row);
    });
    const saveRow = el("div", "hb-yt-saverow");
    const inp = el("input", "hb-yt-addinp");
    inp.placeholder = tt("save_queue_ph", null, "Guardar la cola actual como…");
    const b = el("button", "hb-yt-btn", tt("save", null, "Guardar"));
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
}
