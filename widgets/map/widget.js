// Map: the places data.py located, pinned and numbered over OpenStreetMap tiles, with the list beneath.
//
// No map library and no fetch: the tiles are plain <img> elements (the same way the image viewer shows remote
// pictures), positioned with Web-Mercator arithmetic. The view FITS every pin, and re-fits when the card changes
// shape — a drag, maximize, or the chat docking beside it — through one ResizeObserver per card. A pin or a row
// goes through ctx.action("select"), the same door as the voice. Place names come from outside: textContent only.

const TILE = 256;
const TILES = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png";

function injectStyles(){
  if(document.getElementById("hb-map-css"))return;
  const s=document.createElement("style"); s.id="hb-map-css"; s.textContent=`
  .hb-map{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
          color:var(--hb-ink,#F2F4F7);width:100%;box-sizing:border-box;height:100%;min-height:0;
          display:flex;flex-direction:column;gap:var(--sp-2,8px)}
  .hb-map .maptitle{font-size:var(--fs-title,1rem);font-weight:600;line-height:var(--hb-lh-tight,1.35)}
  .hb-map .mapview{position:relative;flex:1 1 auto;min-height:180px;overflow:hidden;
          border-radius:var(--hb-r-l,12px);border:1px solid var(--hb-line,rgba(255,255,255,.14));
          background:var(--hb-bg-soft,#272D35)}
  .hb-map .maptile{position:absolute;width:256px;height:256px;user-select:none;-webkit-user-drag:none;pointer-events:none}
  .hb-map .mappin{position:absolute;transform:translate(-50%,-100%);display:flex;flex-direction:column;
          align-items:center;cursor:pointer;z-index:2;background:none;border:none;padding:0;font:inherit}
  .hb-map .mappin b{display:flex;align-items:center;justify-content:center;min-width:26px;height:26px;
          border-radius:13px;background:var(--hb-accent,#AE90FF);color:var(--canvas,#16191E);font-size:.8rem;
          font-weight:700;box-shadow:0 1px 4px rgba(0,0,0,.45);border:2px solid #fff}
  .hb-map .mappin.is-on b{background:var(--hb-warn,#F2CE6B);transform:scale(1.2)}
  .hb-map .mappin i{width:2px;height:8px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.4)}
  .hb-map .mappin:focus-visible b{box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-map .mapattr{position:absolute;right:4px;bottom:2px;font-size:10px;color:#333;
          background:rgba(255,255,255,.75);padding:0 4px;border-radius:3px;z-index:3}
  .hb-map .maplist{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:var(--sp-1,4px)}
  .hb-map .maprow{display:flex;gap:var(--sp-2,8px);align-items:baseline;text-align:left;cursor:pointer;
          font:inherit;color:inherit;background:transparent;border:1px solid transparent;
          border-radius:var(--hb-r-s,8px);padding:4px 8px}
  .hb-map .maprow:hover{background:var(--hb-hover,#3C434F)}
  .hb-map .maprow:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-map .maprow.is-on{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);
          border-color:color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent)}
  .hb-map .maprow b{flex:none;font-size:var(--fs-caption,.86rem)}
  .hb-map .maprow span{font-size:var(--fs-caption,.86rem);font-weight:600}
  .hb-map .maprow small{display:block;font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE);font-weight:400}
  .hb-map .mapempty{font-size:var(--fs-caption,.86rem);color:var(--hb-muted,#A7B0BE);padding:var(--sp-4,16px) 0}
  `; document.head.appendChild(s);
}

let _T = null;
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.map."+key, params); if(s && s!=="widgets.map."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}
function txt(tag, cls, s){ const e=document.createElement(tag); if(cls)e.className=cls; if(s!=null)e.textContent=s; return e; }

// Web Mercator: degrees → world pixels at zoom z.
function project(lat, lon, z){
  const n = TILE * Math.pow(2, z);
  const s = Math.sin(Math.max(-85, Math.min(85, lat)) * Math.PI / 180);
  return { x: (lon + 180) / 360 * n, y: (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n };
}

// The deepest zoom at which every pin fits the box with a margin; one pin sits at street level.
export function fit(places, w, h, pad = 48){
  if(!places.length) return { z: 2, cx: 0, cy: 0 };
  let z = places.length === 1 ? 15 : 17;
  for(; z > 1; z--){
    const pts = places.map(p => project(p.lat, p.lon, z));
    const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
    if(Math.max(...xs) - Math.min(...xs) <= w - 2 * pad && Math.max(...ys) - Math.min(...ys) <= h - 2 * pad){
      return { z, cx: (Math.max(...xs) + Math.min(...xs)) / 2, cy: (Math.max(...ys) + Math.min(...ys)) / 2 };
    }
  }
  const p = project(places[0].lat, places[0].lon, 1);
  return { z: 1, cx: p.x, cy: p.y };
}

function drawMap(view, places, selected, ctx){
  view.textContent = "";
  const w = view.clientWidth || 600, h = view.clientHeight || 360;
  const { z, cx, cy } = fit(places, w, h);
  const ox = cx - w / 2, oy = cy - h / 2;             // world pixel at the view's top-left
  const max = Math.pow(2, z);
  const tx0 = Math.floor(ox / TILE), ty0 = Math.floor(oy / TILE);
  const tx1 = Math.floor((ox + w) / TILE), ty1 = Math.floor((oy + h) / TILE);
  const subs = "abcd";
  for(let tx = tx0; tx <= tx1; tx++){
    for(let ty = ty0; ty <= ty1; ty++){
      if(ty < 0 || ty >= max) continue;
      const wx = ((tx % max) + max) % max;
      const img = document.createElement("img");
      img.className = "maptile"; img.alt = ""; img.loading = "lazy"; img.decoding = "async";
      img.src = TILES.replace("{s}", subs[(wx + ty) % 4]).replace("{z}", z).replace("{x}", wx).replace("{y}", ty);
      img.style.left = Math.round(tx * TILE - ox) + "px"; img.style.top = Math.round(ty * TILE - oy) + "px";
      view.appendChild(img);
    }
  }
  places.forEach((p, i) => {
    const pt = project(p.lat, p.lon, z);
    const pin = document.createElement("button");
    pin.type = "button";
    pin.className = "mappin" + (selected === i + 1 ? " is-on" : "");
    pin.style.left = Math.round(pt.x - ox) + "px"; pin.style.top = Math.round(pt.y - oy) + "px";
    pin.title = p.name;
    pin.setAttribute("aria-label", `${i + 1}. ${p.name}`);
    pin.appendChild(txt("b", null, String(i + 1)));
    pin.appendChild(document.createElement("i"));
    pin.onclick = () => { try{ ctx && ctx.action && ctx.action("select", { item: String(i + 1) }); }catch(_){} };
    view.appendChild(pin);
  });
  view.appendChild(txt("div", "mapattr", "© OpenStreetMap © CARTO"));
}

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();
  el.className = "hb-map";
  el.textContent = "";
  const d = data || {};
  const places = (Array.isArray(d.places) ? d.places : []).filter(p => typeof p.lat === "number" && typeof p.lon === "number");
  if(!places.length){
    el.appendChild(txt("div", "mapempty", tt("empty", null, "Ask to see places on a map — «show them on a map» — and they are pinned here.")));
    return;
  }
  if(d.title) el.appendChild(txt("div", "maptitle", String(d.title)));
  const view = txt("div", "mapview");
  el.appendChild(view);
  const selected = Number(d.selected) || 0;

  const list = txt("div", "maplist");
  places.forEach((p, i) => {
    const row = txt("button", "maprow" + (selected === i + 1 ? " is-on" : ""));
    row.type = "button";
    row.appendChild(txt("b", null, `${i + 1}.`));
    const body = document.createElement("div");
    body.appendChild(txt("span", null, p.name));
    const sub = [p.address, p.note].filter(Boolean).join(" · ");
    if(sub) body.appendChild(txt("small", null, sub));
    row.appendChild(body);
    row.onclick = () => { try{ ctx && ctx.action && ctx.action("select", { item: String(i + 1) }); }catch(_){} };
    list.appendChild(row);
  });
  el.appendChild(list);

  // Lay out once the card has a size, and again whenever it changes shape.
  const relayout = () => drawMap(view, places, selected, ctx);
  try{ if(el._hbMapRO) el._hbMapRO.disconnect(); }catch(_){}
  if(typeof ResizeObserver === "function"){
    let last = "";
    el._hbMapRO = new ResizeObserver(() => {
      const k = `${view.clientWidth}x${view.clientHeight}`;
      if(k !== last){ last = k; relayout(); }
    });
    el._hbMapRO.observe(view);
  }
  relayout();
}
