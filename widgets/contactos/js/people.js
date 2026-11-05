// Contacts widget — who a person is to him: his GROUPS (the rail section, the strip over a group's list, the
// toggles on a card), the words he uses for them (ALIAS), who they are to him (RELATION) and the AGENTS they are
// reachable through (V2-854 F5). Every write is an action of this card; a message to a group is never sent from
// here — `message_group` hands HIS order to the conversation, where the same send door as the voice decides.
import { editable, section } from "./fields.js";
import { el2, hooks, kindOf, memberOf, byRelation, normJs, selOf, tt } from "./shared.js";

//: The mark of each native group in the rail. Presentation only — WHICH natives exist and which relation files a
//: person in each is the manifest's `native_groups`, shipped in `data.native_groups`.
const NATIVE_ICON = {family: "♥", friends: "☺", colleagues: "⚒"};
//: The kinds that may carry linked agents (mirrors `model.AGENT_HOLDERS`).
const AGENT_HOLDERS = ["person", "company"];

export function groupLabel(g){
  if(!g) return "";
  if(g.native) return g.groupId==="favorites" ? tt("favs", null, "★ Favoritos")
                    : tt("group_"+g.groupId, null, ({family:"Familia",friends:"Amigos",colleagues:"Compañeros"})[g.groupId] || g.name);
  return String(g.name||"");
}

// The groups the rail and the card offer: his rows (natives first, as the store ranks them), or — on data from
// before the groups collection — his labels, read as groups by name.
export function groupRows(data){
  if(Array.isArray(data.groupRows)) return data.groupRows;
  const by={}; (data.contacts||[]).forEach(c=>(c.groups||[]).forEach(g=>{ const k=normJs(g); if(!k) return;
    (by[k]=by[k]||{groupId:"", name:g, native:false, legacy:true}); }));
  return Object.values(by);
}

const redrawOf=(el,data,ctx)=>nd=>hooks.render(el,(nd&&nd.contacts)?nd:data,ctx);
const actOf=(el,data,ctx)=>async(name,payload)=>{ const nd=await ctx.action(name,payload); redrawOf(el,data,ctx)(nd); return nd; };

// An inline input in place of `btn`: Enter saves, Escape cancels, leaving saves.
function inlineInput(btn, ph, onSave, onCancel, width){
  const inp=document.createElement("input"); inp.className="ctin"; inp.placeholder=ph||"";
  if(width) inp.style.maxWidth=width;
  let done=false;
  const fin=(save)=>{ if(done)return; done=true; const t=String(inp.value||"").trim();
    if(save && t) onSave(t, inp); else onCancel(); };
  inp.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();fin(true);} else if(e.key==="Escape"){e.preventDefault();fin(false);} };
  inp.onblur=()=>fin(true);
  btn.replaceWith(inp); inp.focus();
  return inp;
}

// ── THE RAIL SECTION — natives always (a 0 says «nobody filed here yet»), then his, + Nuevo grupo ──────────────
export function railGroups(side, el, data, ctx, row, pool, page){
  const rows=groupRows(data).filter(g=>!(g.native && g.groupId==="favorites"));   // ★ Favoritos lives above
  const nats=data.native_groups||[];
  const counted=rows.map(g=>({g, n: pool.filter(c=>g.legacy ? (c.groups||[]).some(x=>normJs(x)===normJs(g.name))
                                                                  : memberOf(g,c,nats)).length}));
  const natives=counted.filter(x=>x.g.native);
  const his=counted.filter(x=>!x.g.native && x.n>0).sort((a,b)=>b.n-a.n || (normJs(a.g.name)<normJs(b.g.name)?-1:1));
  const empty=counted.filter(x=>!x.g.native && !x.n);
  his.push(...empty);                                  // a group he just made, still empty, stays reachable
  if(!natives.length && !his.length) return;
  side.appendChild(el2("div","ctsep"));
  side.appendChild(el2("div","ctsidelbl", tt("side_groups", null, "Grupos")));
  natives.forEach(x=>row("groupId", x.g.groupId, groupLabel(x.g), x.n, NATIVE_ICON[x.g.groupId]||""));
  const open=!!el._ctAllGroups;
  (open ? his : his.slice(0, page)).forEach(x=>x.g.legacy ? row("group", x.g.name, x.g.name, x.n)
                                                          : row("groupId", x.g.groupId, groupLabel(x.g), x.n));
  if(his.length > page){
    const more=el2("button","ctgmore", open ? tt("rail_less", null, "ver menos")
      : tt("rail_more", {n: his.length-page}, "ver "+(his.length-page)+" más"));
    more.onclick=()=>{ el._ctAllGroups=!open; hooks.render(el,data,ctx); };
    side.appendChild(more);
  }
  if(!Array.isArray(data.groupRows)) return;
  const add=el2("button","ctact","+ "+tt("new_group", null, "Nuevo grupo"));
  add.onclick=()=>inlineInput(add, tt("new_group_ph", null, "nombre del grupo…"), async(t)=>{
    const nd=await ctx.action("create_group",{name:t});
    const g=nd && nd.result && nd.result.group;
    if(g && g.groupId){ el._ctFilter={groupId:String(g.groupId)}; el._ctDetail=null; el._ctShown=0; }
    redrawOf(el,data,ctx)(nd); }, ()=>hooks.render(el,data,ctx));
  side.appendChild(add);
}

export function groupById(data, id){ return groupRows(data).find(g=>String(g.groupId)===String(id)) || null; }

// ── THE STRIP over a group's list: add members, send a message, the WhatsApp mirror, rename / delete ───────────
export function groupStrip(el, main, data, ctx){
  const g=groupById(data, selOf(el).groupId);
  if(!g) return;
  const act=actOf(el,data,ctx);
  const nats=data.native_groups||[];
  const n=(data.contacts||[]).filter(c=>memberOf(g,c,nats)).length;
  const bar=el2("div","ctgstrip");
  bar.appendChild(el2("span","ctgsname", groupLabel(g)+" · "+n));
  const add=el2("button","ctbtn"+(el._ctPick?" on":""), "+ "+tt("group_add", null, "Añadir"));
  add.onclick=()=>{ el._ctPick = el._ctPick ? null
    : {groupId:String(g.groupId), on:new Set((data.contacts||[]).filter(c=>memberOf(g,c,nats)).map(c=>c.id))};
    hooks.render(el,data,ctx); };
  bar.appendChild(add);
  const send=el2("button","ctbtn primary","✉ "+tt("group_send", null, "Mandar mensaje"));
  send.onclick=()=>inlineInput(send, tt("group_send_ph", null, "el mensaje…"), (t)=>{
    if(g.mirror) return handOver(el, data, ctx, {groupId:g.groupId, text:t, mode:"group"});
    el._ctAsk={groupId:String(g.groupId), text:t}; hooks.render(el,data,ctx); }, ()=>hooks.render(el,data,ctx), "260px");
  bar.appendChild(send);
  if(g.mirror) bar.appendChild(el2("span","ctpill", "WhatsApp: "+tt("group_mirror_on", null, "enlazado")+" ✓"));
  else if(!g.native){
    const mk=el2("button","ctbtn","⇄ WhatsApp: "+tt("group_mirror_make", null, "crear"));
    mk.title=tt("group_mirror_hint", null, "Crea un grupo de WhatsApp con los de este grupo que tienen WhatsApp");
    mk.onclick=()=>handOver(el, data, ctx, {groupId:g.groupId, mode:"mirror"});
    bar.appendChild(mk);
  }
  if(!g.native){
    const rn=el2("button","ctdel",tt("group_rename", null, "renombrar"));
    rn.onclick=()=>inlineInput(rn, groupLabel(g), (t)=>act("rename_group",{groupId:g.groupId,name:t}),
                               ()=>hooks.render(el,data,ctx), "160px");
    const del=el2("button","ctdel",tt("group_delete", null, "borrar"));
    del.title=tt("group_delete_hint", null, "Borra el grupo; sus contactos se quedan en el directorio");
    del.onclick=()=>{ if(!del.dataset.sure){ del.dataset.sure="1"; del.textContent=tt("group_delete_sure", null, "¿seguro? borrar"); return; }
      el._ctFilter={}; el._ctPick=null; act("delete_group",{groupId:g.groupId}); };
    bar.append(rn, del);
  }
  main.appendChild(bar);
  if(el._ctAsk && el._ctAsk.groupId===String(g.groupId)) main.appendChild(askHow(el, data, ctx, g));
  if(el._ctNote) main.appendChild(el2("div","ctnote", el._ctNote));
  if(el._ctPick) main.appendChild(pickBar(el, data, ctx, g));
}

// «Send to a group with no WhatsApp mirror» — asked ONCE, here: create the WhatsApp group, or one by one.
function askHow(el, data, ctx, g){
  const box=el2("div","ctgask");
  box.appendChild(el2("span",null,tt("group_ask_how", null, "Este grupo no tiene grupo de WhatsApp. ¿Cómo lo mando?")));
  const ask=el._ctAsk;
  const go=(mode)=>()=>{ el._ctAsk=null; handOver(el, data, ctx, {groupId:g.groupId, text:ask.text, mode}); };
  const a=el2("button","ctbtn primary",tt("group_ask_create", null, "Crear el grupo de WhatsApp y escribir ahí")); a.onclick=go("create");
  const b=el2("button","ctbtn",tt("group_ask_each", null, "Uno a uno")); b.onclick=go("each");
  const x=el2("button","ctdel",tt("cancel", null, "Cancelar")); x.onclick=()=>{ el._ctAsk=null; hooks.render(el,data,ctx); };
  box.append(a,b,x);
  return box;
}

// The card names the act; the conversation does it. What came back is said where he clicked.
async function handOver(el, data, ctx, payload){
  const nd=await ctx.action("message_group", payload);
  const r=(nd && nd.result) || {};
  el._ctNote = nd && nd.ok ? tt("group_handed", null, "Se lo he pasado al agente: ")+"«"+String(r.handed||"")+"»"
      + ((r.left_out||[]).length ? " · "+tt("group_left_out", {names:r.left_out.join(", ")}, "sin canal: "+r.left_out.join(", ")) : "")
    : tt("group_not_handed", null, "No se ha podido pasar al agente: ")+String((nd&&nd.error)||"");
  hooks.render(el, (nd&&nd.contacts)?nd:data, ctx);
}

// Selection mode: every row wears a box, ticked when inside; «Listo» writes the difference in two calls at most.
function pickBar(el, data, ctx, g){
  const bar=el2("div","ctgstrip");
  bar.appendChild(el2("span","ctnote",tt("group_pick_hint", null, "Marca a quién va en el grupo; usa el buscador para encontrarlos.")));
  const done=el2("button","ctbtn primary",tt("done", null, "Listo"));
  done.onclick=async()=>{
    const pick=el._ctPick, nats=data.native_groups||[];
    const was=new Set((data.contacts||[]).filter(c=>memberOf(g,c,nats)).map(c=>c.id));
    const add=[...pick.on].filter(id=>!was.has(id)), rem=[...was].filter(id=>!pick.on.has(id));
    el._ctPick=null;
    let nd=null;
    if(add.length) nd=await ctx.action("add_to_group",{groupId:g.groupId, contactIds:add});
    if(rem.length) nd=await ctx.action("add_to_group",{groupId:g.groupId, contactIds:rem, remove:true});
    hooks.render(el,(nd&&nd.contacts)?nd:data,ctx); };
  const cancel=el2("button","ctbtn",tt("cancel", null, "Cancelar"));
  cancel.onclick=()=>{ el._ctPick=null; hooks.render(el,data,ctx); };
  bar.append(done, cancel);
  return bar;
}

export function pickBox(el, c){
  const b=document.createElement("input"); b.type="checkbox"; b.className="ctpickbox";
  b.checked=el._ctPick.on.has(c.id);
  b.onclick=(ev)=>{ ev.stopPropagation(); if(b.checked) el._ctPick.on.add(c.id); else el._ctPick.on.delete(c.id); };
  return b;
}

// ── THE CARD: relation, aliases, groups, agents ────────────────────────────────────────────────────────────────
export function relationPick(c, data, act){
  const pick=document.createElement("select"); pick.className="ctpick";
  pick.title=tt("relation_hint", null, "Quién es para ti");
  const none=document.createElement("option"); none.value=""; none.textContent=tt("rel_none", null, "— sin relación —");
  pick.appendChild(none);
  (data.relations||[]).forEach(r=>{ const o=document.createElement("option"); o.value=r;
    o.textContent=tt("rel_"+r, null, r); pick.appendChild(o); });
  pick.value=String(c.relation||"");
  pick.onchange=()=>act("set_alias",{contactId:c.id, relation:pick.value});
  return pick;
}

export function detailPeople(box, el, data, ctx, c, redraw, act){
  detailAliases(box, c, redraw, act);
  if(Array.isArray(data.groupRows)) detailGroups(box, data, c, redraw, act);
  if(AGENT_HOLDERS.includes(kindOf(c))) detailAgents(box, c, redraw, act);
}

function detailAliases(box, c, redraw, act){
  const sec=section(box, tt("sec_aliases", null, "Alias"));
  const tw=el2("div","cttags");
  const learned=c.aliasSources||{};
  (c.aliases||[]).forEach(a=>{
    const isL=learned[a]==="learned";
    const t=el2("span","cttag"+(isL?" learned":""));
    const word=el2("span",null,a+(isL?" ·a":""));
    if(isL) t.title=tt("alias_learned_hint", null, "Aprendido cuando elegiste entre varios");
    // Editing it makes it HIS: the same word typed again carries no «learned» mark.
    editable(word, word, a, v=>{ const n=String(v).trim();
      if(!n) return act("set_alias",{contactId:c.id, alias:a, remove:true});
      if(n===a) return isL ? act("set_alias",{contactId:c.id, alias:a}) : redraw(null);
      ctxChain(act, [["set_alias",{contactId:c.id, alias:a, remove:true}], ["set_alias",{contactId:c.id, alias:n}]]); });
    t.appendChild(word);
    const x=el2("button",null,"✕"); x.title=tt("alias_remove", null, "Quitar este alias");
    x.onclick=()=>act("set_alias",{contactId:c.id, alias:a, remove:true});
    t.appendChild(x); tw.appendChild(t);
  });
  const add=el2("button","ctaddtag","+ "+tt("alias_add", null, "alias"));
  add.onclick=()=>inlineInput(add, tt("alias_ph", null, "cómo la llamas…"),
                              (t)=>act("set_alias",{contactId:c.id, alias:t}), ()=>redraw(null), "160px");
  tw.appendChild(add);
  sec.appendChild(tw);
}

async function ctxChain(act, calls){ for(const [n,p] of calls) await act(n,p); }

function detailGroups(box, data, c, redraw, act){
  const sec=section(box, tt("sec_groups", null, "Grupos"));
  const tw=el2("div","cttags");
  const nats=data.native_groups||[];
  const rows=groupRows(data).filter(g=>!(g.native && g.groupId==="favorites"));
  rows.filter(g=>g.native).forEach(g=>{
    const on=memberOf(g,c,nats), rel=byRelation(g,c,nats);
    const b=el2("button","cttag ctnat"+(on?" on":""), (NATIVE_ICON[g.groupId]||"")+" "+groupLabel(g));
    if(rel){ b.disabled=true; b.title=tt("group_by_relation", {rel:tt("rel_"+c.relation, null, c.relation)},
                                        "Por su relación ("+c.relation+"): cámbiala para sacarla"); }
    else b.onclick=()=>act("add_to_group",{groupId:g.groupId, contactId:c.id, ...(on?{remove:true}:{})});
    tw.appendChild(b);
  });
  rows.filter(g=>!g.native && memberOf(g,c,nats)).forEach(g=>{
    const t=el2("span","cttag"); t.appendChild(el2("span",null,groupLabel(g)));
    const x=el2("button",null,"✕"); x.title=tt("group_leave", null, "Sacar de este grupo");
    x.onclick=()=>act("add_to_group",{groupId:g.groupId, contactId:c.id, remove:true});
    t.appendChild(x); tw.appendChild(t);
  });
  const free=rows.filter(g=>!g.native && !memberOf(g,c,nats));
  const add=el2("button","ctaddtag","+ "+tt("group_join", null, "grupo"));
  add.onclick=()=>{
    const pick=document.createElement("select"); pick.className="ctpick";
    const head=document.createElement("option"); head.value=""; head.textContent=tt("group_choose", null, "— elige un grupo —");
    pick.appendChild(head);
    free.forEach(g=>{ const o=document.createElement("option"); o.value=g.groupId; o.textContent=groupLabel(g); pick.appendChild(o); });
    const nw=document.createElement("option"); nw.value="__new"; nw.textContent="+ "+tt("new_group", null, "Nuevo grupo");
    pick.appendChild(nw);
    pick.onchange=()=>{
      if(pick.value==="__new") return inlineInput(pick, tt("new_group_ph", null, "nombre del grupo…"),
        (t)=>act("create_group",{name:t, contactIds:[c.id]}), ()=>redraw(null), "160px");
      if(pick.value) act("add_to_group",{groupId:pick.value, contactId:c.id}); };
    add.replaceWith(pick); pick.focus();
  };
  tw.appendChild(add);
  sec.appendChild(tw);
}

function detailAgents(box, c, redraw, act){
  const sec=section(box, tt("sec_agents", null, "Agentes"));
  (c.agents||[]).forEach(a=>{
    const r=el2("div","ctfr ctagent");
    r.appendChild(el2("span","ctfv",String(a.agent_id||"")));
    const meta=[a.cluster ? tt("agent_cluster", {c:a.cluster}, "cluster "+a.cluster) : "", a.label||""].filter(Boolean).join(" · ");
    if(meta) r.appendChild(el2("span","ctnote",meta));
    const x=el2("button","ctchx","✕"); x.title=tt("agent_remove", null, "Desvincular este agente");
    x.onclick=()=>act("set_agent",{contactId:c.id, agent_id:a.agent_id, cluster:a.cluster||"", remove:true});
    r.appendChild(x); sec.appendChild(r);
  });
  if(!(c.agents||[]).length) sec.appendChild(el2("div","ctnote",tt("agents_none", null, "Ningún agente vinculado.")));
  const add=el2("button","ctaddtag","+ "+tt("agent_add", null, "agente"));
  add.onclick=()=>{
    const row=el2("div","ctfr");
    const id=document.createElement("input"); id.className="ctin"; id.placeholder=tt("agent_id_ph", null, "id del agente…");
    const cl=document.createElement("input"); cl.className="ctin"; cl.placeholder=tt("agent_cluster_ph", null, "cluster (opcional)");
    const save=()=>{ const v=String(id.value||"").trim(); if(!v) return redraw(null);
      act("set_agent",{contactId:c.id, agent_id:v, cluster:String(cl.value||"").trim()}); };
    [id,cl].forEach(i=>i.onkeydown=e=>{ if(e.key==="Enter"){e.preventDefault();save();} else if(e.key==="Escape"){e.preventDefault();redraw(null);} });
    row.append(id,cl); add.replaceWith(row); id.focus();
  };
  sec.appendChild(add);
}
