// Contacts widget — the editable rows of the detail card: one field, a section, a labelled list of phones or
// e-mails (refactor2710-12 T-03).
import { el2, hooks, tt } from "./shared.js";

// ── Editing in place ─────────────────────────────────────────────────────────────────────────────────────
// `commit` receives the typed string and does whatever that row means; the caller re-renders from whatever
// the action returned. Escape restores without a round trip — a cancel that still wrote would be a lie.
export function editable(holder, shown, value, commit){
  holder.onclick=()=>{
    const inp=document.createElement("input");
    inp.className="ctin"; inp.value=String(value||"");
    let done=false;
    const finish=(save)=>{ if(done)return; done=true;
      if(save) commit(inp.value); else holder.replaceWith(shown); };
    inp.onkeydown=(e)=>{ if(e.key==="Enter"){e.preventDefault();finish(true);}
                         else if(e.key==="Escape"){e.preventDefault();finish(false);} };
    inp.onblur=()=>finish(true);
    holder.replaceWith(inp); inp.focus(); inp.select();
  };
}

export function fieldRow(box, label, value, commit){
  const r=el2("div","ctfr");
  r.appendChild(el2("span","ctfk",label));
  const v=el2("span","ctfv"+(value?"":" void"), value || "—");
  v.title=tt("edit_hint", null, "Pulsa para editar");
  editable(v, v, value, commit);
  r.appendChild(v); box.appendChild(r);
  return r;
}

export function section(box, title){
  const s=el2("div","ctdsec"); s.appendChild(el2("h4",null,title)); box.appendChild(s); return s;
}

// ── SEVERAL phones, several e-mails, each with a free label (V2-715) ───────────────────────────────────
// A company is not one number: a switchboard, a mobile and a billing line are three facts about the same
// entry, and the label is what makes the difference sayable («el fijo», «la centralita»). Every gesture
// sends the WHOLE list through `update_contact`, because `phone`/`email` are only the head of it and the
// store keeps the two in step — writing one without the other would be undone on the next read.
export function detailRows(box, el, data, ctx, c, key, title, addLabel, ph){
  const redraw=nd=>hooks.render(el,(nd&&nd.contacts)?nd:data,ctx);
  const act=async(name,payload)=>redraw(await ctx.action(name,payload));
  const rows=(c[key]||[]).slice();
  const head=String((key==="phones"?c.phone:c.email)||"").trim();
  const list=rows.length ? rows : (head ? [{value:head,label:""}] : []);
  const put=(next)=>act("update_contact",{contactId:c.id,[key]:next});

  const sec=el2("div","ctdsec");
  const h=el2("h4",null,title); sec.appendChild(h);
  list.forEach((rw,i)=>{
    const r=el2("div","ctdrow");
    const lb=el2("button","ctdl", String(rw.label||"").trim() || tt("label_add", null, "etiqueta"));
    lb.title=tt("label_hint", null, "Pulsa para decir de qué es: móvil, centralita, trabajo…");
    lb.onclick=()=>{
      const inp=document.createElement("input"); inp.className="ctin"; inp.style.maxWidth="120px";
      inp.value=String(rw.label||"");
      let done=false;
      const fin=(save)=>{ if(done)return; done=true;
        if(!save) return redraw(null);
        const next=list.map((x,j)=>j===i?{value:x.value,label:String(inp.value||"").trim()}:x);
        put(next); };
      inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                         else if(e.key==="Escape"){e.preventDefault();fin(false);} };
      inp.onblur=()=>fin(true);
      lb.replaceWith(inp); inp.focus(); inp.select();
    };
    r.appendChild(lb);
    const v=el2("span","ctfv",String(rw.value||""));
    v.title=tt("edit_hint", null, "Pulsa para editar");
    editable(v, v, rw.value, val=>{
      const t=String(val).trim();
      if(t===String(rw.value||"")) return redraw(null);
      const next=list.map((x,j)=>j===i?{value:t,label:x.label}:x).filter(x=>x.value);
      put(next);
    });
    r.appendChild(v);
    const x=el2("button","ctchx","✕");
    x.title=tt("detail_remove", null, "Quitar");
    x.onclick=()=>put(list.filter((_,j)=>j!==i));
    r.appendChild(x);
    sec.appendChild(r);
  });
  if(!list.length){
    // EMPTY IS A ROW (V2-699's rule, kept): «no muestra ni siquiera los campos básicos, aunque sean
    // vacíos, para que se vea que es una ficha de un contacto». A section that disappeared when there was
    // nothing in it would make «no tengo su teléfono» and «esta ficha no enseña teléfonos» look alike.
    const r=el2("div","ctdrow"); r.appendChild(el2("span","ctfv void","—")); sec.appendChild(r);
  }
  const add=el2("button","ctaddtag",addLabel);
  add.onclick=()=>{
    const inp=document.createElement("input"); inp.className="ctin"; inp.style.maxWidth="190px";
    inp.placeholder=ph;
    let done=false;
    const fin=(save)=>{ if(done)return; done=true;
      const t=String(inp.value||"").trim();
      if(save && t) act("add_" + (key==="phones"?"phone":"email"),
                        {contactId:c.id, [key==="phones"?"phone":"email"]:t});
      else redraw(null); };
    inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                       else if(e.key==="Escape"){e.preventDefault();fin(false);} };
    inp.onblur=()=>fin(true);
    add.replaceWith(inp); inp.focus();
  };
  sec.appendChild(add);
  box.appendChild(sec);
  return sec;
}
