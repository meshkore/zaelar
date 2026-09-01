// Contacts widget — client render module (V2-541). Contract: render(el, data, ctx).
// ONE directory for every identity: left rail = the groups, centre = the entries of the selection, subheader =
// the filters that vary with it (favorites, cities, co-occurring labels). A favourite place IS an entry here.
// Self-contained: scoped styles, plain DOM, no innerHTML on data, no network, no polling.

const KICON = {person: "\u{1F464}", place: "\u{1F4CD}", company: "\u{1F3E2}"};
const KLABEL = {person: "persona", place: "sitio", company: "empresa"};

function injectStyles(){
  if(document.getElementById("hb-contactos-css"))return;
  const s=document.createElement("style"); s.id="hb-contactos-css"; s.textContent=`
  .hb-contactos{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:min(700px,92vw)}
  .hb-contactos .cthd{display:flex;align-items:baseline;gap:10px;margin:0 0 10px}
  .hb-contactos .cthd b{font-size:18px}
  .hb-contactos .cthd .ctn{font-size:12px;color:var(--hb-muted-2,#7d8a9c);margin-left:auto;font-family:ui-monospace,Menlo,monospace}
  .hb-contactos .ctcols{display:grid;grid-template-columns:158px 1fr;gap:12px}
  @media(max-width:560px){.hb-contactos .ctcols{grid-template-columns:1fr}}
  .hb-contactos .ctrail{display:flex;flex-direction:column;gap:4px;max-height:52vh;overflow:auto}
  .hb-contactos .ctg{display:flex;gap:6px;align-items:center;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:9px;padding:6px 9px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#3a4757);text-align:left}
  .hb-contactos .ctg:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctg.on{background:var(--hb-accent,#3D6FE0);border-color:var(--hb-accent,#3D6FE0);color:#fff}
  .hb-contactos .ctg .ctgc{margin-left:auto;font-size:10.5px;font-family:ui-monospace,Menlo,monospace;opacity:.75}
  .hb-contactos .ctmain{display:flex;flex-direction:column;gap:8px;min-width:0}
  .hb-contactos .ctfil{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
  .hb-contactos .ctchip{font-size:11.5px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:3px 10px;cursor:pointer;color:var(--hb-muted,#5b6b82);background:var(--hb-bg,#fff)}
  .hb-contactos .ctchip:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctchip.on{background:var(--hb-accent2,#16B8A6);border-color:var(--hb-accent2,#16B8A6);color:#fff}
  .hb-contactos .ctq{border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:3px 10px;font-size:11.5px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);width:120px}
  .hb-contactos .ctlist{display:flex;flex-direction:column;gap:5px;max-height:44vh;overflow:auto}
  .hb-contactos .ctrow{display:flex;gap:9px;align-items:center;border:1px solid var(--hb-line,#eef1f6);border-radius:10px;padding:8px 10px;background:var(--hb-bg,#fff);cursor:pointer}
  .hb-contactos .ctrow:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-contactos .ctrow .ctnm{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-contactos .ctrow .ctci{font-size:12px;color:var(--hb-muted-2,#7d8a9c);white-space:nowrap}
  .hb-contactos .ctrow .ctgs{display:flex;gap:4px;overflow:hidden}
  .hb-contactos .ctpill{font-size:10px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:1px 7px;color:var(--hb-muted,#5b6b82);white-space:nowrap}
  .hb-contactos .ctfav{margin-left:auto;border:none;background:none;font-size:15px;cursor:pointer;opacity:.35;flex:0 0 auto}
  .hb-contactos .ctfav.on{opacity:1}
  .hb-contactos .ctempty{font-size:13px;color:var(--hb-muted-2,#7d8a9c);border:1px dashed var(--hb-line,#e3e8f0);border-radius:12px;padding:18px;text-align:center}
  .hb-contactos .ctdet{border:1px solid var(--hb-line,#e3e8f0);border-radius:14px;padding:14px;background:var(--hb-bg-soft,#fbfdff);display:flex;flex-direction:column;gap:8px}
  .hb-contactos .ctdet .ctback{align-self:flex-start;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:9px;padding:4px 10px;font-size:12px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-contactos .ctdet .ctdnm{font-size:17px;font-weight:700;display:flex;gap:8px;align-items:center}
  .hb-contactos .ctdet .ctk{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace}
  .hb-contactos .ctdet .ctf{display:flex;gap:8px;font-size:13px}
  .hb-contactos .ctdet .ctf .ctfk{color:var(--hb-muted-2,#7d8a9c);min-width:74px}
  .hb-contactos .ctlink{color:var(--hb-accent,#3D6FE0);cursor:pointer;text-decoration:underline}
  `; document.head.appendChild(s);
}

function el2(tag, cls, text){ const e=document.createElement(tag); if(cls)e.className=cls;
  if(text!=null)e.textContent=text; return e; }

function normJs(s){ return String(s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"")
  .replace(/\s+/g," ").trim().toLowerCase(); }

// Loose group match, BOTH directions («fontanero» ↔ «fontaneros») — mirrors data.py's `_group_matches`.
function groupMatch(want, c){
  const w=normJs(want); if(!w) return true;
  return (c.groups||[]).some(g=>{const gn=normJs(g); return gn.includes(w)||w.includes(gn);});
}

function filtered(data, st){
  let out=(data.contacts||[]).slice();
  if(st.group==="__fav") out=out.filter(c=>c.favorite);
  else if(st.group) out=out.filter(c=>groupMatch(st.group,c));
  if(st.fav) out=out.filter(c=>c.favorite);
  if(st.city){ const cw=normJs(st.city);
    out=out.filter(c=>{const cn=normJs(c.city); return cn.includes(cw)||(cn&&cw.includes(cn));}); }
  if(st.query){ const qn=normJs(st.query);
    out=out.filter(c=>normJs([c.name,c.city,c.address,c.phone,c.email,c.notes,(c.groups||[]).join(" ")].join(" ")).includes(qn)); }
  out.sort((a,b)=>(a.favorite===b.favorite ? normJs(a.name)<normJs(b.name)?-1:1 : (a.favorite?-1:1)));
  return out;
}

function favBtn(c, ctx, el, data){
  const b=el2("button","ctfav"+(c.favorite?" on":""),"★");
  b.title=c.favorite?"Quitar de favoritos":"Marcar como favorito";
  b.onclick=async(ev)=>{ ev.stopPropagation();
    const nd=await ctx.action("set_favorite",{contactId:c.id,favorite:!c.favorite});
    render(el,(nd&&nd.contacts)?nd:data,ctx); };
  return b;
}

// `el` is always the widget ROOT (state + re-renders live there); `host` is where the panel is appended.
// Passing the column as `el` would re-render the whole widget INSIDE it — V2-124's detached-canvas family.
function renderDetail(el, host, data, ctx, c){
  const box=el2("div","ctdet");
  const back=el2("button","ctback","← Volver");
  back.onclick=()=>{ el._ctDetail=null; render(el,data,ctx); };
  box.appendChild(back);
  const nm=el2("div","ctdnm"); nm.append(el2("span",null,KICON[c.kind]||KICON.person),
    el2("span",null,c.name||c.id), favBtn(c,ctx,el,data));
  box.appendChild(nm);
  box.appendChild(el2("div","ctk",KLABEL[c.kind]||c.kind||""));
  const row=(k,v)=>{ if(!v)return; const r=el2("div","ctf");
    r.append(el2("span","ctfk",k), el2("span",null,String(v))); box.appendChild(r); };
  row("Ciudad", c.city); row("Dirección", c.address); row("Teléfono", c.phone);
  row("Email", c.email); row("Notas", c.notes);
  if((c.groups||[]).length){
    const gs=el2("div","ctfil");
    c.groups.forEach(g=>gs.appendChild(el2("span","ctpill",g)));
    box.appendChild(gs);
  }
  const byId={}; (data.contacts||[]).forEach(x=>byId[x.id]=x);
  const parent=c.parentId?byId[c.parentId]:null;
  if(parent){ const r=el2("div","ctf"); r.appendChild(el2("span","ctfk","Conectado a"));
    const a=el2("span","ctlink",parent.name||parent.id);
    a.onclick=()=>{ el._ctDetail=parent.id; render(el,data,ctx); };
    r.appendChild(a); box.appendChild(r); }
  const kids=(data.contacts||[]).filter(x=>x.parentId===c.id);
  if(kids.length){
    const r=el2("div","ctf"); r.appendChild(el2("span","ctfk","Conectados"));
    const wrap=el2("span",null,"");
    kids.forEach((k,i)=>{ if(i)wrap.appendChild(document.createTextNode(" · "));
      const a=el2("span","ctlink",k.name||k.id);
      a.onclick=()=>{ el._ctDetail=k.id; render(el,data,ctx); }; wrap.appendChild(a); });
    r.appendChild(wrap); box.appendChild(r);
  }
  host.appendChild(box);
}

export function render(el, data, ctx){
  injectStyles();

  // A VIEW PUSHED FROM VOICE (`show_view`/`show_contact`). Applied only when its token MOVES — a plain data
  // refresh never yanks the group the operator is reading, but asking twice for the same filter still lands,
  // because the token is a counter and not the filter itself (the agenda's V2-540 contract).
  const pushed=data.view;
  if(pushed && pushed.n!==el._ctViewN){
    el._ctViewN=pushed.n;
    const sel=pushed.sel||{};
    if(sel.contactId){ el._ctDetail=sel.contactId; }
    else{
      el._ctDetail=null;
      el._ctGroup=sel.group||"";
      el._ctCity=sel.city||"";
      el._ctFav=!!sel.favorites;
      el._ctQuery=sel.query||"";
    }
  }
  const st={group:el._ctGroup||"", city:el._ctCity||"", fav:!!el._ctFav, query:el._ctQuery||""};

  el.className="hb-contactos";
  el.textContent="";                                          // reset (no innerHTML)

  const hd=el2("div","cthd");
  hd.append(el2("b",null,"Contactos"), el2("span","ctn",`${data.count||0} en el directorio`));
  el.appendChild(hd);

  const contacts=data.contacts||[];
  if(!contacts.length){
    el.appendChild(el2("div","ctempty",
      "El directorio está vacío. Dile a Zaelar: «apúntame el restaurante Elfo On de Soria como favorito» "+
      "o «añade a Marta, amiga del trabajo»."));
    return;
  }

  const cols=el2("div","ctcols");

  // LEFT RAIL — the main concepts: Todos, ★ Favoritos, then every group label with its count.
  const rail=el2("div","ctrail");
  const gbtn=(label,id,count)=>{ const b=el2("button","ctg"+((st.group||"")===id?" on":""));
    b.append(el2("span",null,label)); if(count!=null)b.append(el2("span","ctgc",String(count)));
    b.onclick=()=>{ el._ctGroup=id; el._ctDetail=null; el._ctCity=""; render(el,data,ctx); };
    return b; };
  rail.appendChild(gbtn("Todos","",contacts.length));
  rail.appendChild(gbtn("★ Favoritos","__fav",data.favorites_count||0));
  (data.groups||[]).forEach(g=>rail.appendChild(gbtn(g.id,g.id,g.count)));
  cols.appendChild(rail);

  const main=el2("div","ctmain");
  const detail=el._ctDetail ? contacts.find(c=>c.id===el._ctDetail) : null;
  if(detail){
    renderDetail(el,main,data,ctx,detail);
  } else {
    // SUBHEADER — the filters, derived from the SELECTION: favorites toggle, the cities present, free text.
    const fil=el2("div","ctfil");
    const favChip=el2("button","ctchip"+(st.fav?" on":""),"★ favoritos");
    favChip.onclick=()=>{ el._ctFav=!st.fav; render(el,data,ctx); };
    fil.appendChild(favChip);
    const inGroup=filtered(data,{group:st.group,city:"",fav:false,query:""});
    const cities={}; inGroup.forEach(c=>{ const ct=(c.city||"").trim(); if(ct)cities[normJs(ct)]=ct; });
    Object.values(cities).sort().forEach(ct=>{
      const on=normJs(st.city)===normJs(ct);
      const b=el2("button","ctchip"+(on?" on":""),ct);
      b.onclick=()=>{ el._ctCity=on?"":ct; render(el,data,ctx); };
      fil.appendChild(b);
    });
    const q=el2("input","ctq"); q.placeholder="filtrar…"; q.value=st.query;
    q.oninput=()=>{ el._ctQuery=q.value; const keep=q; render(el,data,ctx);
      const nq=el.querySelector(".ctq"); if(nq){ nq.focus(); nq.setSelectionRange(keep.value.length,keep.value.length); } };
    fil.appendChild(q);
    main.appendChild(fil);

    const rows=filtered(data,st);
    const list=el2("div","ctlist");
    if(!rows.length){
      list.appendChild(el2("div","ctempty","Nada que casar con ese filtro."));
    }
    rows.forEach(c=>{
      const r=el2("div","ctrow");
      r.append(el2("span",null,KICON[c.kind]||KICON.person), el2("span","ctnm",c.name||c.id));
      if(c.city)r.appendChild(el2("span","ctci",c.city));
      const gs=el2("span","ctgs");
      (c.groups||[]).slice(0,2).forEach(g=>gs.appendChild(el2("span","ctpill",g)));
      r.appendChild(gs);
      r.appendChild(favBtn(c,ctx,el,data));
      r.onclick=()=>{ el._ctDetail=c.id; render(el,data,ctx); };
      list.appendChild(r);
    });
    main.appendChild(list);
  }
  cols.appendChild(main);
  el.appendChild(cols);
}
