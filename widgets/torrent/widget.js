// The Descargas widget (V2-637): a download's progress, and the player that appears once there is enough to
// watch. Nothing here touches the network directly — the <video> loads its own src through the browser's media
// pipeline (the one legitimate way media reaches a widget, V2-620), pointed at our own /api/torrent/stream/{id}.
//
// The <video> is built ONCE and kept across re-renders (the V2-124/4.19 lesson): a data refresh must never
// replace the element mid-playback, so the shell is built on first render and later renders only UPDATE it —
// toggling the player's visibility and refreshing the progress text, never rebuilding.

function injectStyles(){
  if(document.getElementById("hb-torrent-css"))return;
  const s=document.createElement("style"); s.id="hb-torrent-css"; s.textContent=`
  .hbt{width:100%;box-sizing:border-box;display:flex;flex-direction:column;height:100%;min-height:0;
       background:var(--hb-bg,#0d1117);color:var(--hb-ink,#e6edf3);border-radius:14px;overflow:hidden;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .hbt-head{display:flex;align-items:center;gap:10px;padding:12px 18px;border-bottom:1px solid var(--hb-line,#222b36)}
  .hbt-title{font-size:15px;font-weight:650;letter-spacing:-.01em;flex:1 1 auto;min-width:0;
             overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hbt-stop{font-size:12px;color:var(--hb-muted,#8b98a9);border:1px solid var(--hb-line,#222b36);
            background:none;border-radius:8px;padding:4px 10px;cursor:pointer}
  .hbt-stop:hover{color:var(--hb-ink,#e6edf3)}
  .hbt-stage{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;background:#000}
  .hbt-video{flex:1 1 auto;width:100%;min-height:0;background:#000;display:none}
  .hbt-video.on{display:block}
  .hbt-wait{flex:1 1 auto;display:flex;flex-direction:column;align-items:center;justify-content:center;
            gap:12px;padding:28px 22px;text-align:center;color:var(--hb-muted,#8b98a9)}
  .hbt-wait.off{display:none}
  .hbt-spin{font-size:26px}
  .hbt-bar{width:min(340px,80%);height:6px;border-radius:999px;background:var(--hb-line,#222b36);overflow:hidden}
  .hbt-fill{height:100%;width:0;background:var(--hb-accent,#f0761f);transition:width .4s ease}
  .hbt-note{font-size:13px}
  .hbt-sub{font-size:11.5px;color:var(--hb-muted-2,#6b7684)}
  .hbt-err{color:#ff8f8f}
  .hbt-foot{padding:8px 18px;font-size:11.5px;color:var(--hb-muted-2,#6b7684);border-top:1px solid var(--hb-line,#222b36);
            display:flex;gap:14px;flex-wrap:wrap}`;
  document.head.appendChild(s);
}

function pct(p){ return Math.max(0, Math.min(100, Math.round((Number(p)||0)*100))); }
function human(n){ n=Number(n)||0; if(n<1024)return n+" B"; if(n<1048576)return (n/1024).toFixed(0)+" KB";
  if(n<1073741824)return (n/1048576).toFixed(1)+" MB"; return (n/1073741824).toFixed(2)+" GB"; }

function buildShell(root, ctx){
  root.className="hbt"; root.textContent="";
  const head=document.createElement("div"); head.className="hbt-head";
  const title=document.createElement("div"); title.className="hbt-title";
  const stop=document.createElement("button"); stop.className="hbt-stop"; stop.type="button";
  stop.textContent="Cancelar";
  stop.addEventListener("click",()=>{ try{ ctx&&ctx.action&&ctx.action("stop"); }catch(_){} });
  head.appendChild(title); head.appendChild(stop);

  const stage=document.createElement("div"); stage.className="hbt-stage";
  const video=document.createElement("video"); video.className="hbt-video";
  video.controls=true; video.preload="metadata"; video.playsInline=true;
  const wait=document.createElement("div"); wait.className="hbt-wait";
  const spin=document.createElement("div"); spin.className="hbt-spin"; spin.textContent="⬇";
  const bar=document.createElement("div"); bar.className="hbt-bar";
  const fill=document.createElement("div"); fill.className="hbt-fill"; bar.appendChild(fill);
  const note=document.createElement("div"); note.className="hbt-note";
  const sub=document.createElement("div"); sub.className="hbt-sub";
  wait.appendChild(spin); wait.appendChild(note); wait.appendChild(bar); wait.appendChild(sub);
  stage.appendChild(video); stage.appendChild(wait);

  const foot=document.createElement("div"); foot.className="hbt-foot";

  root.appendChild(head); root.appendChild(stage); root.appendChild(foot);
  return { title, stop, video, wait, fill, note, sub, foot, src:"" };
}

export function render(root, data, ctx){
  injectStyles();
  const d = data || {};
  let ui = root.__hbt;
  if(!ui){ ui = root.__hbt = buildShell(root, ctx); }

  ui.title.textContent = d.title || d.query || "Descargas";
  const st = d.status || {};
  const err = d.error || "";

  // The player: mount its src ONCE, the first time a stream URL exists, and never rebuild it afterwards.
  if(d.stream_url && ui.src !== d.stream_url){
    ui.src = d.stream_url;
    ui.video.src = d.stream_url;
    ui.video.classList.add("on");
    ui.wait.classList.add("off");
    try{ ui.video.play().catch(()=>{}); }catch(_){}
  } else if(!d.stream_url){
    ui.video.classList.remove("on");
    ui.wait.classList.remove("off");
  }

  if(!d.stream_url){
    if(err){
      ui.note.className="hbt-note hbt-err";
      ui.note.textContent = err;
      ui.sub.textContent = "";
      ui.fill.style.width = "0%";
    } else if(!d.id){
      ui.note.className="hbt-note";
      ui.note.textContent = "Dime qué peli o vídeo quieres ver.";
      ui.sub.textContent = "";
      ui.fill.style.width = "0%";
    } else {
      const p = pct(st.progress);
      ui.note.className="hbt-note";
      ui.note.textContent = st.name ? `Buscando fuentes y bajando «${st.name}»…` : "Buscando fuentes…";
      ui.sub.textContent = `${p}% · ${st.num_peers||0} fuentes · ${human(st.download_rate)}/s`;
      ui.fill.style.width = p + "%";
    }
  }

  // Footer with live counters (also useful once playing, to see it keep downloading ahead of the playhead).
  ui.foot.textContent = "";
  if(d.id && st.ok){
    const add=(t)=>{ const s=document.createElement("span"); s.textContent=t; ui.foot.appendChild(s); };
    add(`${pct(st.progress)}%`);
    add(`${human(st.downloaded)} / ${human(st.size)}`);
    add(`${st.num_peers||0} fuentes`);
    add(`${human(st.download_rate)}/s`);
  }

  // Keep polling while a download is active OR still filling ahead of playback; stop when there is nothing to
  // watch or the file is complete. One timer per card, cleared and reset on every render.
  if(root.__hbtPoll){ clearTimeout(root.__hbtPoll); root.__hbtPoll = 0; }
  const active = d.id && !err && (st.state !== "seeding") && pct(st.progress) < 100;
  if(active && ctx && ctx.action){
    root.__hbtPoll = setTimeout(()=>{ try{ ctx.action("poll"); }catch(_){} }, 1500);
  }
}
