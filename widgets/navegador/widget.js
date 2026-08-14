// Navegador — client render. Contract: render(el, data, ctx).
//   data = GET /widgets/navegador/data (written by backend owner.py). NO polling: desktop.js repaints when
//   store.save emits the SSE notice. The page is shown as a live CAPTURE (GET /widgets/navegador/asset/shot.png,
//   cache-busted by data.rev); YouTube plays EMBEDDED (youtube-nocookie iframe) because a capture does not provide
//   video/audio. Click/scroll on the capture → page coordinates → ctx.action → owner → new capture.
//   ctx.action(name,payload): open/search/youtube/back/forward/reload/scroll/click/press. NO fetch (isolation
//   contract): the same-origin <img> and YouTube <iframe> are elements, not our own requests.
const VP = {w: 1280, h: 800};        // backend Chromium viewport — basis for mapping click coordinates
let _editing = false;                // operator is typing in the bar → do not overwrite its value while repainting
let _wheelAt = 0;                    // simple mouse-wheel scroll throttle

function injectStyles(){
  if(document.getElementById("hb-nav-css")) return;
  const s = document.createElement("style"); s.id = "hb-nav-css"; s.textContent = `
  .hb-nav{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(920px,94vw)}
  .hb-nav-bar{display:flex;gap:6px;align-items:center;margin-bottom:8px}
  .hb-nav-ic{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);color:var(--hb-muted,#3a4757);border-radius:8px;width:32px;height:32px;font-size:15px;cursor:pointer;line-height:1;flex:0 0 auto}
  .hb-nav-ic:hover:not(:disabled){border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-nav-ic:disabled{opacity:.4;cursor:default}
  .hb-nav-url{flex:1;min-width:0;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);border-radius:9px;padding:7px 11px;font-size:13px}
  .hb-nav-url:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-nav-go{border:0;background:var(--hb-accent,#3D6FE0);color:#fff;border-radius:9px;padding:0 14px;height:32px;font-size:13px;font-weight:600;cursor:pointer;flex:0 0 auto}
  .hb-nav-go:hover{filter:brightness(1.06)}
  .hb-nav-view{position:relative;border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;overflow:hidden;background:var(--hb-bg-soft,#f5f7fb);aspect-ratio:${VP.w} / ${VP.h}}
  .hb-nav-img{display:block;width:100%;height:100%;object-fit:cover;object-position:top;cursor:crosshair}
  .hb-nav-yt{display:block;width:100%;height:100%;border:0}
  .hb-nav-load{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.06);color:var(--hb-muted,#3a4757);font-size:13px;backdrop-filter:blur(1px)}
  .hb-nav-err{margin-top:8px;color:var(--hb-risk,#e5484d);font-size:12.5px}
  .hb-nav-title{font-size:12px;color:var(--hb-muted-2,#7d8a9c);margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-nav-hint{position:absolute;inset:0;display:flex;flex-direction:column;gap:12px;align-items:center;justify-content:center;text-align:center;color:var(--hb-muted,#5b6b82);padding:20px}
  .hb-nav-hint .t{font-size:14px} .hb-nav-hint .chips{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}
  .hb-nav-chip{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);color:var(--hb-muted,#3a4757);border-radius:999px;padding:5px 13px;font-size:12.5px;cursor:pointer}
  .hb-nav-chip:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-nav-scroll{position:absolute;right:10px;bottom:10px;display:flex;flex-direction:column;gap:6px}
  .hb-nav-scroll button{width:30px;height:30px;border-radius:8px;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);color:var(--hb-muted,#3a4757);cursor:pointer;font-size:13px;opacity:.85}
  .hb-nav-scroll button:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0);opacity:1}
  /* ── TASK CARD (kind:"task"): vertical, mini-browser above + feed below. One per task/tab. ── */
  .hb-navt{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:560px;max-width:92vw}
  .hb-navt-head{display:flex;align-items:center;gap:7px;margin-bottom:7px}
  .hb-navt-status{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;padding:2px 7px;border-radius:999px;background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5b6b82);flex:0 0 auto}
  .hb-navt-status.s-working{background:rgba(61,111,224,.14);color:var(--hb-accent,#3D6FE0)}
  .hb-navt-status.s-done{background:rgba(22,184,166,.16);color:var(--hb-accent2,#16B8A6)}
  .hb-navt-status.s-failed,.hb-navt-status.s-cancelled{background:rgba(229,72,77,.14);color:var(--hb-risk,#e5484d)}
  .hb-navt-status.s-needs_input{background:rgba(245,158,11,.16);color:var(--hb-warn,#d97706)}
  .hb-navt-title{font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}
  .hb-navt-view{position:relative;border:1px solid var(--hb-line,#e3e8f0);border-radius:10px;overflow:hidden;background:var(--hb-bg-soft,#f5f7fb);height:300px}
  .hb-navt-img{display:block;width:100%;height:100%;object-fit:cover;object-position:top}
  .hb-navt-ph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--hb-muted-2,#7d8a9c);font-size:12px}
  /* PHASE line with spinner (process state: searching/collecting/investigating/ready) */
  .hb-navt-phase{display:flex;align-items:center;gap:8px;margin-top:8px;font-size:12.5px;color:var(--hb-ink,#0d1622);font-weight:600}
  .hb-navt-phase.active{color:var(--hb-accent,#3D6FE0)}
  .hb-navt-spin{width:14px;height:14px;border-radius:50%;flex:0 0 auto;border:2px solid var(--hb-line,#e3e8f0);border-top-color:var(--hb-accent,#3D6FE0);animation:hbnavspin .8s linear infinite}
  @keyframes hbnavspin{to{transform:rotate(360deg)}}
  .hb-navt-done{width:14px;height:14px;flex:0 0 auto;color:var(--hb-accent2,#16B8A6)}
  .hb-navt-login{margin-top:8px;padding:10px;border-radius:9px;background:rgba(61,111,224,.1);border:1px solid rgba(61,111,224,.35)}
  .hb-navt-login-t{font-size:12.5px;color:var(--hb-ink,#0d1622);margin-bottom:8px}
  .hb-navt-login-btn{border:0;background:var(--hb-accent,#3D6FE0);color:#fff;border-radius:8px;padding:8px 14px;font-size:12.5px;font-weight:600;cursor:pointer;width:100%}
  .hb-navt-login-btn:hover{filter:brightness(1.06)}
  .hb-navt-urlline{font-size:10.5px;color:var(--hb-muted-2,#7d8a9c);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-navt-q{margin-top:8px;padding:8px 10px;border-radius:9px;background:rgba(245,158,11,.12);border:1px solid rgba(245,158,11,.4)}
  .hb-navt-q-t{font-size:12.5px;color:var(--hb-ink,#0d1622)} .hb-navt-q-h{font-size:11px;color:var(--hb-muted,#5b6b82);margin-top:2px}
  .hb-navt-results{margin-top:8px;display:flex;flex-direction:column;gap:6px}
  .hb-navt-concl{font-size:12px;color:var(--hb-ink,#0d1622);font-weight:600;line-height:1.35}
  .hb-navt-item{display:flex;gap:10px;text-decoration:none;color:inherit;border:1px solid var(--hb-line,#e3e8f0);border-radius:10px;padding:8px;align-items:center}
  .hb-navt-item:hover{border-color:var(--hb-accent,#3D6FE0);background:var(--hb-bubble,#f1f4f9)}
  .hb-navt-thumb{width:84px;height:84px;object-fit:cover;border-radius:8px;flex:0 0 auto;background:var(--hb-bg-soft,#f5f7fb)}
  .hb-navt-meta{min-width:0}
  .hb-navt-it-title{font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-navt-price{font-size:12px;color:var(--hb-accent2,#16B8A6);font-weight:700}
  .hb-navt-sub{font-size:11px;color:var(--hb-muted-2,#7d8a9c);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-navt-feed{margin-top:8px;max-height:180px;overflow:auto;border-top:1px solid var(--hb-line,#e3e8f0);padding-top:6px;display:flex;flex-direction:column;gap:3px}
  .hb-navt-ev{font-size:11.5px;line-height:1.35;color:var(--hb-muted,#5b6b82);display:flex;gap:6px}
  .hb-navt-tt{color:var(--hb-muted-2,#9aa7b8);flex:0 0 auto;font-variant-numeric:tabular-nums}
  .hb-navt-xx{min-width:0;word-break:break-word}
  `; document.head.appendChild(s);
}

function el(tag, cls, text){ const e = document.createElement(tag); if(cls) e.className = cls;
  if(text != null) e.textContent = String(text); return e; }

const STATUS_LABEL = {queued:"en cola", working:"trabajando", needs_input:"pregunta", open:"abierto",
                      done:"hecho", failed:"falló", cancelled:"cancelada"};

// TASK CARD (kind:"task"): mini-browser (capture of ITS tab) above + progress/results feed below.
// One card per task (id navegador::<taskid>). Only textContent + same-origin <img> (isolation contract).
function renderTask(root, data, ctx){
  root.className = "hb-navt";
  root.textContent = "";
  const head = el("div", "hb-navt-head");
  head.appendChild(el("span", "hb-navt-status s-" + (data.status || ""), STATUS_LABEL[data.status] || data.status || ""));
  head.appendChild(el("div", "hb-navt-title", data.goal_summary || data.title || data.page_title || data.url || "Navegador"));
  root.appendChild(head);

  const view = el("div", "hb-navt-view");
  if((data.shot_rev || 0) > 0 && data.shot){
    const img = el("img", "hb-navt-img"); img.alt = data.page_title || "página";
    img.src = "/widgets/navegador/asset/" + data.shot + "?v=" + (data.shot_rev || 0);
    view.appendChild(img);
  } else {
    view.appendChild(el("div", "hb-navt-ph", "abriendo pestaña…"));
  }
  root.appendChild(view);
  if(data.url || data.page_title) root.appendChild(el("div", "hb-navt-urlline", data.page_title || data.url));

  // MAIN TASK always VISIBLE below the capture (V2-035): synthesized ESSENCE of the objective (objective + criteria,
  // compressed by LLM) — falls back to the raw goal if not computed yet. Thus, if the brain drifts from the request
  // (e.g. "enduro motorcycle" → "trial/road"), the operator SEES it and can correct it by voice ("I said enduro"),
  // and the brain refines this SAME task (continuity V2-032). NO hover tooltip (it duplicated the text).
  const _goalText = data.goal_summary || data.goal;
  if(_goalText){
    const g = el("div", "hb-navt-goal", "🎯 " + _goalText);
    g.style.cssText = "font-size:12px;color:var(--hb-ink,#0d1622);background:var(--hb-accent-soft,rgba(61,111,224,.08));"
      + "border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:6px 9px;margin-top:8px;line-height:1.35;white-space:normal";
    root.appendChild(g);
  }

  // Process PHASE + spinner: WHAT we are doing now (searching / collecting / investigating / ready).
  if(data.phase){
    const ph = el("div", "hb-navt-phase" + (data.phase_active ? " active" : ""));
    if(data.phase_active){ ph.appendChild(el("span", "hb-navt-spin")); }
    else { const d = el("span", "hb-navt-done"); d.textContent = "✓"; ph.appendChild(d); }
    ph.appendChild(el("span", null, data.phase + (data.phase_active ? "…" : "")));
    root.appendChild(ph);
  }

  // LOGIN: the task waits for the operator to sign in in the real window → confirmation button.
  if(data.awaiting_login){
    const box = el("div", "hb-navt-login");
    box.appendChild(el("div", "hb-navt-login-t",
      "🔓 Inicia sesión en la ventana de Chrome que se abrió. Tu sesión se guardará para las próximas tareas."));
    const btn = el("button", "hb-navt-login-btn", "Ya he iniciado sesión");
    btn.onclick = () => ctx.action("auth_done", {task_id: data.id});
    box.appendChild(btn);
    root.appendChild(box);
  }

  // Rich results (Phase 4): conclusion + listings with photo/price/link.
  const res = data.results;
  if(res && Array.isArray(res.items) && res.items.length){
    const rz = el("div", "hb-navt-results");
    if(res.conclusion) rz.appendChild(el("div", "hb-navt-concl", res.conclusion));
    res.items.slice(0, 5).forEach(it => {
      const row = el(it.url ? "a" : "div", "hb-navt-item");
      if(it.url){ row.href = it.url; row.target = "_blank"; row.rel = "noopener noreferrer"; }
      if(it.image){ const im = el("img", "hb-navt-thumb"); im.src = it.image; im.referrerPolicy = "no-referrer"; row.appendChild(im); }
      const meta = el("div", "hb-navt-meta");
      meta.appendChild(el("div", "hb-navt-it-title", it.title || ""));
      if(it.price) meta.appendChild(el("div", "hb-navt-price", it.price));
      if(it.subtitle) meta.appendChild(el("div", "hb-navt-sub", it.subtitle));
      row.appendChild(meta); rz.appendChild(row);
    });
    root.appendChild(rz);
  }

  // Pending question for the operator (answered BY VOICE; the orchestrator routes it to this task).
  if(data.question){
    const q = el("div", "hb-navt-q");
    q.appendChild(el("div", "hb-navt-q-t", "❓ " + data.question));
    q.appendChild(el("div", "hb-navt-q-h", "Responde por voz."));
    root.appendChild(q);
  }

  // Live task feed (progress). Autoscroll to the last event.
  const feed = el("div", "hb-navt-feed");
  (data.events || []).slice(-16).forEach(ev => {
    const line = el("div", "hb-navt-ev");
    line.appendChild(el("span", "hb-navt-tt", ev.t || ""));
    line.appendChild(el("span", "hb-navt-xx", ev.text || ""));
    feed.appendChild(line);
  });
  root.appendChild(feed);
  requestAnimationFrame(() => { feed.scrollTop = feed.scrollHeight; });
}

// SINGLE FORMAT: vertical card (mini-browser + feed), one per tab/task. There is no large view anymore — if you want
// to drive/watch the real browser, look at the real Chrome WINDOW; the card is the monitor + feed.
export function render(root, data, ctx){
  injectStyles();
  renderTask(root, data || {}, ctx);
}
