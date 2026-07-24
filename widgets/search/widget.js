// Search widget — live web-search view (from the debug-log refinement): shows the URLs being consulted, each
// with 2-3 lines of status/analysis, like parallel in-progress tasks; states a conclusion; then fades out.
// data = /widgets/search/data (sources pre-resolved). We animate loading → resolved to feel live.

function injectStyles(){
  if(document.getElementById("hb-search-css"))return;
  const s=document.createElement("style"); s.id="hb-search-css"; s.textContent=`
  .hb-search{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(440px,88vw)}
  .hb-search .hd{display:flex;align-items:center;gap:9px;margin:0 0 12px}
  .hb-search .scan{width:30px;height:30px;border-radius:50%;border:3px solid var(--hb-line,#e3e8f0);border-top-color:var(--hb-accent,#3D6FE0);animation:hbspin .8s linear infinite}
  @keyframes hbspin{to{transform:rotate(360deg)}}
  .hb-search .hd b{font-size:14px}.hb-search .hd .q{font-size:12px;color:var(--hb-muted-2,#7d8a9c);margin-left:auto;font-family:ui-monospace,Menlo,monospace;max-width:45%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-search .src{border:1px solid var(--hb-line,#eef1f6);border-left:3px solid var(--hb-neutral,#c2ccda);border-radius:10px;padding:9px 12px;margin-bottom:8px;background:var(--hb-bg,#fff);
                  opacity:0;transform:translateY(6px);transition:.3s}
  .hb-search .src.in{opacity:1;transform:none}
  .hb-search .src.ok{border-left-color:var(--hb-accent2,#16B8A6)}.hb-search .src.fail{border-left-color:var(--hb-risk,#e5484d)}
  .hb-search .src .u{font-size:20px;font-weight:600;color:var(--hb-ink,#0d1622);display:flex;align-items:center;gap:8px;line-height:1.2;word-break:break-word}
  .hb-search .src .u .dot{width:8px;height:8px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:none}
  .hb-search .src.ok .u .dot{background:var(--hb-accent2,#16B8A6)}.hb-search .src.fail .u .dot{background:var(--hb-risk,#e5484d)}
  .hb-search .src.load .u .dot{background:var(--hb-accent,#3D6FE0);animation:hbpulse 1s infinite}
  @keyframes hbpulse{50%{opacity:.3}}
  .hb-search .src .ln{font-size:12.5px;color:var(--hb-muted,#5b6b82);margin-top:4px;line-height:1.45}
  .hb-search .src .ln.s2{color:var(--hb-muted,#3a4757)}
  .hb-search .concl{opacity:0;transition:.4s;font-size:13.5px;color:var(--hb-ink,#0d1622);line-height:1.45;margin-top:6px;border-top:1px solid var(--hb-line,#eef1f6);padding-top:9px}
  .hb-search .concl.in{opacity:1}
  `; document.head.appendChild(s);
}

export function render(el, data, ctx){
  injectStyles();
  const srcs=data.sources||[];
  el.className="hb-search";
  // Header built as DOM: the query is web/user-sourced → it goes in via textContent, never interpolated into
  // innerHTML (XSS). Static chrome (scan bar, containers) is fine as elements too.
  el.textContent="";
  const hd=document.createElement("div"); hd.className="hd";
  const scan=document.createElement("div"); scan.className="scan"; scan.id="hb-scan";
  const b=document.createElement("b"); b.textContent="Estoy buscando…";
  const q=document.createElement("span"); q.className="q"; q.textContent=(data.query||data.location||"").slice(0,40);
  hd.append(scan,b,q); el.appendChild(hd);
  const host=document.createElement("div"); host.id="hb-srcs"; el.appendChild(host);
  const concl=document.createElement("div"); concl.className="concl"; concl.id="hb-concl"; el.appendChild(concl);

  // safe builders — source text comes from the web, so NEVER use innerHTML for it (XSS): textContent only
  const elc=(cls,txt)=>{const e=document.createElement("div");e.className=cls;if(txt!=null)e.textContent=txt;return e;};
  function srcCard(s){
    const c=document.createElement("div"); c.className="src load";
    const u=elc("u"); u.appendChild(elc("dot")); u.appendChild(document.createTextNode(" "+(s.title||s.url||"")));
    c.appendChild(u); return c;
  }
  // show all sources as "loading" cards (parallel tasks), then resolve each with a small stagger → feels live
  srcs.forEach((s,i)=>{
    const c=srcCard(s); c.dataset.i=i; c.appendChild(elc("ln","analizando…"));
    host.appendChild(c); requestAnimationFrame(()=>c.classList.add("in"));
  });

  let pending=srcs.length;
  srcs.forEach((s,i)=>{
    setTimeout(()=>{
      const c=host.querySelector(`.src[data-i="${i}"]`); if(!c)return;
      c.classList.remove("load"); c.classList.add(s.status==="ok"?"ok":"fail");
      c.textContent="";                                  // rebuild safely (no innerHTML for web text)
      const u=elc("u"); u.appendChild(elc("dot")); u.appendChild(document.createTextNode(" "+(s.title||s.url||"")));
      c.appendChild(u);
      (s.lines||[]).slice(0,3).forEach((l,j)=>c.appendChild(elc("ln"+(j?" s2":""), l)));
      if(--pending<=0)finish();
    }, 700 + i*650);   // staggered resolve
  });
  if(!srcs.length)finish();

  function finish(){
    const scan=el.querySelector("#hb-scan"); if(scan){scan.style.animation="none";scan.style.borderTopColor="#16B8A6";}
    const c=el.querySelector("#hb-concl"); c.textContent=data.conclusion||"";
    requestAnimationFrame(()=>c.classList.add("in"));
    setTimeout(()=>{ if(ctx&&ctx.close)ctx.close(); }, 7000);   // short-term memory: fade out when done
  }
}
