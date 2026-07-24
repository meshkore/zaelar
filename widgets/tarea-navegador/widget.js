// tarea-navegador — panel vertical de progreso para tareas del navegador.
// Contract: render(el, data, ctx).
//   Arriba: miniatura del navegador (captura en vivo, con cache-busting por data.navegador_rev).
//   Abajo: 10-12 líneas de estado. Resize handle en el borde derecho.
//   El cerebro empuja datos por [[push:tarea-navegador]] o ctx.action.

function injectStyles(){
  if(document.getElementById("hb-tn-css"))return;
  const s=document.createElement("style"); s.id="hb-tn-css"; s.textContent=`
  .hb-tn-wrap{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    color:var(--hb-ink,#0d1622);width:200px;min-width:100px;max-width:200px;
    resize:horizontal;overflow:auto;border:1px solid var(--hb-line,#eef1f6);
    border-radius:12px;background:var(--hb-bg,#fff);display:flex;flex-direction:column;
    position:relative;user-select:none}
  .hb-tn-wrap::-webkit-resizer{display:none}
  .hb-tn-drag{position:absolute;right:0;top:0;bottom:0;width:6px;cursor:col-resize;
    z-index:5;background:transparent}
  .hb-tn-drag::after{content:"";position:absolute;right:2px;top:50%;width:3px;
    height:24px;background:var(--hb-line,#d0d6e0);border-radius:2px;transform:translateY(-50%)}
  .hb-tn-drag:hover::after{background:var(--hb-accent,#3D6FE0)}
  .hb-tn-head{font-size:11px;font-weight:600;color:var(--hb-muted-2,#7d8a9c);
    padding:8px 10px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    letter-spacing:.3px;display:flex;align-items:center;gap:6px}
  .hb-tn-head .prog{font-weight:400;color:var(--hb-accent,#3D6FE0);font-size:10px;
    margin-left:auto}
  .hb-tn-thumb{flex:0 0 auto;padding:0 10px 6px;position:relative}
  .hb-tn-thumb-inner{position:relative;border:1px solid var(--hb-line,#eef1f6);
    border-radius:8px;overflow:hidden;aspect-ratio:1280/800;background:var(--hb-bg-soft,#f5f7fb);}
  .hb-tn-img{display:block;width:100%;height:100%;object-fit:cover;object-position:top}
  .hb-tn-load{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    background:rgba(0,0,0,.04);color:var(--hb-muted,#7d8a9c);font-size:10px;
    backdrop-filter:blur(1px)}
  .hb-tn-body{flex:1;overflow-y:auto;padding:0 10px 10px;scrollbar-width:thin;
    scrollbar-color:var(--hb-line,#d0d6e0) transparent}
  .hb-tn-body::-webkit-scrollbar{width:3px}
  .hb-tn-body::-webkit-scrollbar-thumb{background:var(--hb-line,#d0d6e0);border-radius:3px}
  .hb-tn-line{font-size:11px;line-height:1.45;padding:2px 0;color:var(--hb-ink,#0d1622);
    display:flex;gap:5px;align-items:flex-start;word-break:break-word}
  .hb-tn-line .dot{flex:0 0 6px;width:6px;height:6px;border-radius:50%;margin-top:4px;
    background:var(--hb-neutral,#c2ccda)}
  .hb-tn-line.ok .dot{background:var(--hb-accent2,#16B8A6)}
  .hb-tn-line.fail .dot{background:var(--hb-risk,#e5484d)}
  .hb-tn-line.cur .dot{background:var(--hb-accent,#3D6FE0);animation:hbtnpulse 1s infinite}
  .hb-tn-line .txt{flex:1;min-width:0}
  .hb-tn-empty{font-size:11px;color:var(--hb-muted,#7d8a9c);padding:12px 0;text-align:center;
    line-height:1.5}
  .hb-tn-bar{margin:0 10px 8px;height:4px;border-radius:4px;background:var(--hb-line,#eef1f6);
    overflow:hidden}
  .hb-tn-bar-fill{height:100%;border-radius:4px;background:var(--hb-accent2,#16B8A6);
    transition:width .4s ease}
  @keyframes hbtnpulse{50%{opacity:.3}}
  `; document.head.appendChild(s);
}

// Custom resize: handle mousedown on the drag zone → mousemove resize
let _resizeActive = false;
let _resizeStartX = 0;
let _resizeStartW = 0;

function startResize(e, el){
  _resizeActive = true;
  _resizeStartX = e.clientX;
  _resizeStartW = el.offsetWidth;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  e.preventDefault();
}

function onMove(e, el, ctx){
  if(!_resizeActive)return;
  const dx = e.clientX - _resizeStartX;
  const w = Math.max(100, Math.min(200, _resizeStartW + dx));
  el.style.width = w + "px";
  // Notify the brain so it persists the width preference
  ctx.action("resize", {width: w});
  e.preventDefault();
}

function onUp(e){
  if(!_resizeActive)return;
  _resizeActive = false;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  e.preventDefault();
}

// Determine status for each line based on content heuristics
function lineStatus(line, idx, totalLines){
  const t = (line||"").trim();
  if(!t) return "none";
  if(t.startsWith("✅") || t.startsWith("✔") || t.startsWith("✓")
     || t.startsWith("OK") || t.startsWith("Hecho")) return "ok";
  if(t.startsWith("❌") || t.startsWith("✗") || t.startsWith("✖")
     || t.startsWith("Error") || t.startsWith("Fallo")) return "fail";
  if(idx === totalLines - 1 && (t.startsWith("🔄") || t.startsWith("→")
     || t.startsWith("⏳") || t.startsWith("●"))) return "cur";
  return "none";
}

export function render(el, data, ctx){
  injectStyles();
  data = data || {};
  el.textContent = "";

  const wrap = document.createElement("div"); wrap.className = "hb-tn-wrap";
  // Restore persisted width from a previous size choice (from data.width or data.style)
  const w = Math.max(100, Math.min(200, data.width || 200));
  wrap.style.width = w + "px";

  // ── Header: título + progreso ──────────────────────────────────────────────
  const hd = document.createElement("div"); hd.className = "hb-tn-head";
  const titleSpan = document.createElement("span");
  titleSpan.textContent = data.title || "Navegador";
  hd.appendChild(titleSpan);
  if(data.progress){
    const pg = document.createElement("span"); pg.className = "prog";
    pg.textContent = String(data.progress); hd.appendChild(pg);
  }
  wrap.appendChild(hd);

  // ── Miniatura del navegador (última captura) ───────────────────────────────
  const thumb = document.createElement("div"); thumb.className = "hb-tn-thumb";
  const inner = document.createElement("div"); inner.className = "hb-tn-thumb-inner";

  const rev = data.navegador_rev || 0;
  if(rev > 0 && data.navegador_mode !== "blank"){
    const img = document.createElement("img"); img.className = "hb-tn-img";
    img.alt = "vista previa";
    img.src = "/widgets/navegador/asset/shot.png?v=" + rev;
    img.loading = "lazy";
    inner.appendChild(img);
  } else if(data.navegador_loading){
    const ld = document.createElement("div"); ld.className = "hb-tn-load";
    ld.textContent = "Cargando…"; inner.appendChild(ld);
  } else {
    const ld = document.createElement("div"); ld.className = "hb-tn-load";
    ld.textContent = "Navegador inactivo"; inner.appendChild(ld);
  }
  thumb.appendChild(inner);
  wrap.appendChild(thumb);

  // ── Barra de progreso (opcional, si se ha definido una fracción) ────────────
  if(data.progress && /^[\d.]+\//.test(String(data.progress))){
    const parts = String(data.progress).split("/");
    const pct = Math.min(100, Math.round((parseFloat(parts[0])||0) / (parseFloat(parts[1])||1) * 100));
    if(pct > 0 && pct <= 100){
      const bar = document.createElement("div"); bar.className = "hb-tn-bar";
      const fill = document.createElement("div"); fill.className = "hb-tn-bar-fill";
      fill.style.width = pct + "%"; bar.appendChild(fill); wrap.appendChild(bar);
    }
  }

  // ── Cuerpo: líneas de progreso ────────────────────────────────────────────
  const body = document.createElement("div"); body.className = "hb-tn-body";
  const allLines = Array.isArray(data.lines) ? data.lines : [];
  const showLines = allLines.slice(-12);  // máximo 12 líneas visibles

  if(showLines.length === 0){
    const empty = document.createElement("div"); empty.className = "hb-tn-empty";
    empty.textContent = "Esperando tarea…\nDi algo como «busca en Wallapop»";
    body.appendChild(empty);
  } else {
    showLines.forEach((ln, i) => {
      const row = document.createElement("div"); row.className = "hb-tn-line";
      const st = lineStatus(ln, i, showLines.length);
      if(st === "ok") row.classList.add("ok");
      else if(st === "fail") row.classList.add("fail");
      else if(st === "cur") row.classList.add("cur");
      const dot = document.createElement("span"); dot.className = "dot";
      row.appendChild(dot);
      const txt = document.createElement("span"); txt.className = "txt";
      // Strip leading emoji/status prefix for cleaner text
      const clean = ln.replace(/^[✅✔✓❌✗✖🔄→⏳●⏰🔍🔗📄📋🗂️💡]\s*/, "");
      txt.textContent = clean || ln;
      row.appendChild(txt);
      body.appendChild(row);
    });
  }
  wrap.appendChild(body);

  // ── Resize handle personalizado ─────────────────────────────────────────────
  const drag = document.createElement("div"); drag.className = "hb-tn-drag";
  drag.addEventListener("mousedown", (e) => startResize(e, wrap));
  document.addEventListener("mousemove", (e) => onMove(e, wrap, ctx));
  document.addEventListener("mouseup", onUp);
  wrap.appendChild(drag);

  el.appendChild(wrap);
}
