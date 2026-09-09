// S-04: agenda widget must render brain-pushed data via textContent, never as HTML.
let innerHTMLWrites = [];
const mkEl = () => {
  const e = {
    _text: "", className: "", dataset: {}, id: "",
    style: { _p: {}, setProperty(k, v){ this._p[k] = v; }, getPropertyValue(k){ return this._p[k] || ""; } },
    children: [], attrs: {},
    set textContent(v){ this._text = v; this.children = []; },
    get textContent(){ return this._text; },
    set innerHTML(v){ innerHTMLWrites.push(v); },       // any HTML sink is a red flag
    get innerHTML(){ return ""; },
    appendChild(c){ this.children.push(c); return c; },
    append(...cs){ cs.forEach(c=>this.children.push(c)); },
    setAttribute(k,v){ this.attrs[k]=v; },
    querySelector(){ return null; },
    querySelectorAll(){ return []; },
    addEventListener(){}, remove(){}, classList: {add(){}, remove(){}, contains(){ return false; }},
  };
  return e;
};
globalThis.document = {
  getElementById: () => mkEl(),             // styles already injected
  createElement: () => mkEl(),
  createElementNS: () => mkEl(),            // the widget draws its own inline icons (V2-643)
  head: { appendChild(){} },
};
globalThis.clearInterval = ()=>{}; globalThis.setInterval = ()=>0;

const XSS = "<img src=x onerror=alert(1)>";
const { render } = await import("../../../../widgets/agenda/widget.js");

// V2-643: the widget draws a real calendar, so the untrusted surface is what a MEETING carries (title,
// notes, location, attendee names — all brain-pushable) plus the planner's own blocks. The fixture has to
// reach the paths the redesign actually renders, or it certifies an empty screen.
const TODAY = new Date();
const _p = n => String(n).padStart(2, "0");
const DAY = `${TODAY.getFullYear()}-${_p(TODAY.getMonth()+1)}-${_p(TODAY.getDate())}`;
const data = { date: DAY, now: "12:00", active: { label: XSS, remaining_min: 5, taskId: "t1" },
  plan: { focus: [{label: XSS, objective: XSS}], blocks: [{start:"09:00",end:"10:00",kind:"deep",label:XSS}] },
  days: [{date: DAY, label: XSS, weekday: XSS,
          plan: {summary: XSS, blocks: [{start:"09:00",end:"10:00",kind:"deep",label:XSS}],
                 focus: [], coaching: [XSS], warnings: [XSS]}}],
  meetings: [{title: XSS, date: DAY, startTime: "11:00", endTime: "12:00", notes: XSS,
              location: XSS, attendees: [XSS], status: "pending", category: XSS, remindAt: XSS}],
  calendars: [{id: XSS, label: XSS, status: XSS}],
  coaching: [XSS], warnings: [XSS] };

const root = mkEl();
render(root, data, { action: async()=>null, close(){} });

// walk the tree, collect every textContent and confirm the payload only appears as text, never via innerHTML
let texts = [];
(function walk(n){ if(n._text) texts.push(n._text); (n.children||[]).forEach(walk); })(root);

if (innerHTMLWrites.length) { console.error("FAIL: innerHTML was written:", innerHTMLWrites); process.exit(1); }
const asText = texts.filter(t => t.includes(XSS)).length;
if (asText < 1) { console.error("FAIL: XSS payload not found as textContent (render changed?)", texts); process.exit(1); }
console.log(`OK: no innerHTML writes; payload rendered as textContent in ${asText} node(s)`);
console.log("S-04 PASS");
