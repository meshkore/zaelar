// Mounts renderTask() from widget.js in a minimal DOM and checks WHAT it renders with real data from the new view.
import { readFileSync } from "node:fs";
const SRC = readFileSync(process.argv[2], "utf8");

// Toy DOM sufficient for this render (textContent + appendChild + className + style + onclick).
class N {
  constructor(tag){ this.tag=tag; this.children=[]; this.className=""; this.style={cssText:""}; this._text=""; }
  set textContent(v){ this._text = String(v); this.children = []; }
  get textContent(){ return this._text + this.children.map(c=>c.textContent).join(""); }
  appendChild(c){ this.children.push(c); return c; }
  get classes(){ return [this.className, ...this.children.flatMap(c=>c.classes)]; }
}
globalThis.document = {
  getElementById: () => ({}),          // the styles are already "injected"
  createElement: (t) => new N(t),
  head: { appendChild(){} },
};
globalThis.requestAnimationFrame = (f) => f();

const mod = await import("data:text/javascript;base64," + Buffer.from(SRC).toString("base64"));
const root = new N("div");
mod.render(root, {
  kind: "task", id: "t1", status: "working",
  title: "Fontaneros en Madrid centro · urgencia hoy",
  page_title: "Fontanero Madrid centro - Buscar con Google",
  url: "https://www.google.com/search?q=fontanero",
  shot: "shot-t1.png", shot_rev: 3,
  phase: "conduciendo el navegador", phase_active: true,
  state: ["🌐 abrió google.com/search?q=fontanero", "📋 5 fichas encontradas", "⭐ extrayendo teléfonos"],
}, { action(){} });

const txt = root.textContent;
const cls = root.classes.filter(Boolean);
const fail = [];
const ok = (name, cond, detail="") => { console.log((cond?"  ok   ":"  FAIL ")+name+(cond?"":"\n         "+detail)); if(!cond) fail.push(name); };

ok("pinta las tres líneas de estado", ["abrió google","5 fichas","extrayendo"].every(s=>txt.includes(s)), txt);
ok("pinta la fase con spinner", cls.includes("hb-navt-spin") && txt.includes("conduciendo el navegador"));
ok("NO repite el título de la tarea dentro de la tarjeta", !txt.includes("Fontaneros en Madrid centro"),
   "la cabecera del chrome ya lo pone; repetirlo es lo que el operador señaló");
ok("no queda ni una fila de resultados", !cls.some(c=>c.includes("hb-navt-item")||c.includes("hb-navt-results")));
ok("no queda el feed de eventos", !cls.some(c=>c.includes("hb-navt-feed")||c.includes("hb-navt-ev")));
ok("sigue enseñando qué página está mirando", txt.includes("Buscar con Google"));

// …and with results in the data (old worker, stale payload), the card does NOT render them.
const root2 = new N("div");
mod.render(root2, { kind:"task", id:"t2", status:"done", state:["listo"],
                    results:{conclusion:"NO DEBE SALIR", items:[{title:"Cómo llegar"},{title:"Sitio web"}]},
                    events:[{t:"11:59",text:"NO DEBE SALIR TAMPOCO"}] }, { action(){} });
const t2 = root2.textContent;
ok("un payload con `results` no se cuela", !t2.includes("NO DEBE SALIR") && !t2.includes("Cómo llegar"), t2);

console.log(fail.length ? "\nFAILED: "+fail.join(", ") : "\nall checks passed");
process.exit(fail.length ? 1 : 0);
