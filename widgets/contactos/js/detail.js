// Contacts widget — the CARD of one contact (refactor2710-12 T-03).
import { detailRows, editable, fieldRow, section } from "./fields.js";
import { CHANNELS, KICON, avatar, channelOf, el2, favBtn, hooks, kindLabel, kindOf, normJs, tt } from "./shared.js";

// `el` is always the widget ROOT (state + re-renders live there); `host` is where the panel is appended.
// Passing the column as `el` would re-render the whole widget INSIDE it — V2-124's detached-canvas family.
export function renderDetail(el, host, data, ctx, c){
  const box=el2("div","ctdet");
  const redraw=nd=>hooks.render(el,(nd&&nd.contacts)?nd:data,ctx);
  const act=async(name,payload)=>redraw(await ctx.action(name,payload));
  detailHead(box, el, data, ctx, c, redraw, act);
  detailReach(box, el, data, ctx, c, redraw, act);
  detailFields(box, el, data, ctx, c, redraw, act);
  detailLinks(box, el, data, ctx, c, redraw, act);
  host.appendChild(box);
}

// The top bar (back, hide, delete) and the hero (face, name, kind, favourite).
function detailHead(box, el, data, ctx, c, redraw, act){
  // Top bar — back, and the one destructive action, kept far from everything else.
  const bar=el2("div","ctdbar");
  const back=el2("button","ctback",tt("back", null, "← Volver"));
  back.onclick=()=>{ el._ctDetail=null; hooks.render(el,data,ctx); };
  bar.appendChild(back);
  // HIDE, not delete (V2-714's rule, reachable at last): a row that came from a platform and is deleted
  // here comes straight back on the next import, so «quítalo de la lista» has to be the hiding one — and
  // the same button brings it back from the rail's «Ocultos».
  const hid=!!c.hidden;
  const hb=el2("button","ctdel", hid ? "◌ "+tt("unhide", null, "Devolver al directorio")
                                     : "◌ "+tt("hide", null, "Ocultar"));
  hb.title = hid ? tt("unhide_hint", null, "Vuelve a salir en el directorio")
                 : tt("hide_hint", null, "Lo quita de la lista sin borrarlo, y la siguiente importación no lo vuelve a traer");
  hb.onclick=()=>act("hide_contact",{contactId:c.id,hidden:!hid}).then(()=>{ el._ctDetail=null; });
  hb.style.marginLeft="auto";
  bar.appendChild(hb);
  const del=el2("button","ctdel",tt("delete", null, "Borrar"));
  del.style.marginLeft="0";
  del.onclick=()=>act("remove_contact",{contactId:c.id}).then(()=>{ el._ctDetail=null; });
  bar.appendChild(del);
  box.appendChild(bar);

  // Hero — face, name, kind, favourite.
  const hero=el2("div","cthero");
  hero.appendChild(avatar(c,true));
  const ht=el2("div","ctht");
  const nm=el2("div","ctdnm",c.name||c.id);
  editable(nm, nm, c.name||"", v=>{ const t=String(v).trim();
    if(!t || t===String(c.name||"")) return redraw(null);
    act("update_contact",{contactId:c.id,name:t}); });
  ht.appendChild(nm);
  const kinds=["person","place","company"];
  const kb=el2("button","ctkind",(KICON[c.kind]||KICON.person)+"  "+(kindLabel(c.kind)||c.kind||""));
  kb.title=tt("kind_hint", null, "Pulsa para cambiar el tipo");
  kb.onclick=()=>{ const i=kinds.indexOf(String(c.kind||"person"));
    act("update_contact",{contactId:c.id,kind:kinds[(i<0?0:i+1)%kinds.length]}); };
  ht.appendChild(kb);
  hero.appendChild(ht);
  hero.appendChild(favBtn(c,ctx,el,data));
  box.appendChild(hero);
}

function detailReach(box, el, data, ctx, c, redraw, act){
  // ── HOW TO REACH HIM — all three platforms, present even when empty ────────────────────────────────────
  const reach=section(box, tt("sec_reach", null, "Cómo contactar"));
  CHANNELS.forEach(p=>{
    const ch=channelOf(c,p.id);
    const r=el2("div","ctch");
    r.appendChild(el2("span","ctcic",p.icon));
    r.appendChild(el2("span","ctcpl",p.label));
    const shownVal=ch?ch.handle:"";
    const v=el2("span","ctfv"+(shownVal?"":" void"), shownVal || "—");
    v.title=tt("edit_hint", null, "Pulsa para editar");
    editable(v, v, shownVal, val=>{
      const t=String(val).trim();
      if(t===shownVal) return redraw(null);
      // A stored `email` field and an email CHANNEL are the same capability said twice; write back to
      // whichever of the two this row is actually showing, so the card never creates a second truth.
      if(p.id==="email" && (!ch || !ch.stored)){
        if(!t) return act("update_contact",{contactId:c.id,clear:"email"});
        return act("update_contact",{contactId:c.id,email:t});
      }
      if(!t) return act("set_channel",{contactId:c.id,platform:p.id,remove:true});
      act("set_channel",{contactId:c.id,platform:p.id,handle:t,preferred:false});
    });
    r.appendChild(v);
    if(ch && ch.handle){
      const x=el2("button","ctchx","✕");
      x.title=tt("channel_clear", null, "Quitar este canal");
      x.onclick=()=>{ if(p.id==="email" && !ch.stored) return act("update_contact",{contactId:c.id,clear:"email"});
        act("set_channel",{contactId:c.id,platform:p.id,remove:true}); };
      r.appendChild(x);
      const pref=String(c.preferred||"")===p.id;
      const pb=el2("button","ctpref"+(pref?" on":""),"★");
      pb.title=pref?tt("pref_is", null, "Es el canal preferido")
                   :tt("pref_set", null, "Escribirle por aquí por defecto");
      if(!pref) pb.onclick=()=>act("set_channel",{contactId:c.id,platform:p.id,preferred:true});
      r.appendChild(pb);
    }
    reach.appendChild(r);
  });
  if(c.phone && !channelOf(c,"whatsapp")){
    // Said out loud rather than guessed: the number is there, and it is still not a WhatsApp.
    reach.appendChild(el2("div","ctnote",
      tt("phone_not_whatsapp", null, "Tienes su teléfono, pero tener un número no prueba que use WhatsApp: "
        + "escribe su WhatsApp arriba si quieres poder mandarle mensajes por ahí.")));
  }
}

function detailFields(box, el, data, ctx, c, redraw, act){
  // ── THE BASIC FIELDS — all of them, empty or not ───────────────────────────────────────────────────────
  // V2-715 — «varios teléfonos que estén vinculados a la misma empresa». Each list is its own section,
  // ABOVE the single-valued fields: the list is the truth and the scalar is only its head
  // (`model.normalize`), so the card always sends the WHOLE list — an edit that moved only the scalar
  // would be undone by the next normalisation.
  detailRows(box, el, data, ctx, c, "phones", tt("sec_phones", null, "Teléfonos"),
             tt("add_phone", null, "+ teléfono"), tt("phone_ph", null, "número…"));
  detailRows(box, el, data, ctx, c, "emails", tt("sec_emails", null, "Correos"),
             tt("add_email", null, "+ correo"), tt("email_ph", null, "dirección…"));
  const dat=section(box, tt("sec_data", null, "Datos"));
  const setField=(key)=>(v)=>{ const t=String(v).trim();
    if(t===String(c[key]||"")) return redraw(null);
    const p={contactId:c.id};
    // An EMPTY string does not clear through `update_contact` — that guard exists so a model omitting a
    // field cannot wipe it. The card is a deliberate gesture, so it says `clear` instead of relying on "".
    if(!t) p.clear=key; else p[key]=t;
    act("update_contact",p); };
  fieldRow(dat, tt("city", null, "Ciudad"), c.city||"", setField("city"));
  fieldRow(dat, tt("address", null, "Dirección"), c.address||"", setField("address"));
  fieldRow(dat, tt("notes", null, "Notas"), c.notes||"", setField("notes"));

  // ── TAGS ───────────────────────────────────────────────────────────────────────────────────────────────
  const tags=section(box, tt("sec_tags", null, "Etiquetas"));
  const tw=el2("div","cttags");
  (c.groups||[]).forEach(g=>{
    const t=el2("span","cttag"); t.appendChild(el2("span",null,g));
    const x=el2("button",null,"✕"); x.title=tt("tag_remove", null, "Quitar esta etiqueta");
    // `groups` REPLACES the whole list (an empty string empties it) — `group` only ever adds, so removing
    // the last tag through it would be a no-op wearing the face of a delete.
    x.onclick=()=>act("update_contact",{contactId:c.id,
      groups:(c.groups||[]).filter(y=>y!==g).join(",")});
    t.appendChild(x); tw.appendChild(t);
  });
  const addT=el2("button","ctaddtag","+ "+tt("tag_add", null, "añadir"));
  addT.onclick=()=>{
    const inp=document.createElement("input"); inp.className="ctin"; inp.style.maxWidth="150px";
    let done=false;
    const fin=(save)=>{ if(done)return; done=true;
      const t=String(inp.value||"").trim();
      if(save && t) act("update_contact",{contactId:c.id,group:t}); else redraw(null); };
    inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);}
                       else if(e.key==="Escape"){e.preventDefault();fin(false);} };
    inp.onblur=()=>fin(true);
    addT.replaceWith(inp); inp.focus();
  };
  tw.appendChild(addT);
  tags.appendChild(tw);
}

function detailLinks(box, el, data, ctx, c, redraw, act){
  // ── LINKS — the people you deal with AT a place, and the place a person hangs from ──────────────────────
  const byId={}; (data.contacts||[]).forEach(x=>byId[x.id]=x);
  const parent=c.parentId?byId[c.parentId]:null;
  const kids=(data.contacts||[]).filter(x=>x.parentId===c.id);
  const ln=section(box, tt("sec_links", null, "Conexiones"));
  const jump=(t)=>{ const a=el2("span","ctlink",t.name||t.id);
    a.onclick=()=>{ el._ctDetail=t.id; hooks.render(el,data,ctx); }; return a; };
  if(kids.length){ const r=el2("div","ctfr"); r.appendChild(el2("span","ctfk",tt("linked", null, "Conectados")));
    const wrap=el2("span",null,"");
    kids.forEach((k,i)=>{ if(i)wrap.appendChild(document.createTextNode(" · "));
      wrap.appendChild(jump(k)); });
    r.appendChild(wrap); ln.appendChild(r); }
  // …and the link is EDITABLE from here (V2-715). `link_contact` existed from birth and had no control
  // behind it, so «cuatro personas vinculadas a la misma empresa» was a sentence only the voice could say.
  const lr=el2("div","ctfr");
  lr.appendChild(el2("span","ctfk",tt("linked_to", null, "Conectado a")));
  const pick=document.createElement("select");
  pick.className="ctpick";
  const none=document.createElement("option");
  none.value=""; none.textContent=tt("link_none", null, "— sin conexión —");
  pick.appendChild(none);
  // Companies and places only: a person hangs from the company or the restaurant where you deal with her,
  // never from another person — and a 2 688-row menu is not a chooser.
  (data.contacts||[]).filter(x=>x.id!==c.id && (kindOf(x)==="company"||kindOf(x)==="place"))
    .sort((a,b)=>normJs(a.name)<normJs(b.name)?-1:1).slice(0,300)
    .forEach(x=>{ const o=document.createElement("option"); o.value=x.id;
                  o.textContent=(x.name||x.id)+(x.city?" · "+x.city:""); pick.appendChild(o); });
  if(parent && !Array.from(pick.options).some(o=>o.value===parent.id)){
    const o=document.createElement("option"); o.value=parent.id; o.textContent=parent.name||parent.id;
    pick.appendChild(o);
  }
  pick.value=c.parentId||"";
  pick.onchange=()=>act("link_contact",{contactId:c.id,parentId:pick.value});
  lr.appendChild(pick);
  ln.appendChild(lr);
}
