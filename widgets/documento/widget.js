// The blank sheet (V2-549). One document on screen, laid out to be READ: a measure that does not run the eye
// off the edge, generous leading, and a hairline of chrome that says what this is and where it came from.
//
// Three renderers and no more, one per declared kind: markdown (the default — a recipe, a report, notes), html
// (a fragment somebody already formatted) and pdf (handed to the browser's own viewer).
//
// Everything here builds DOM nodes. There is no innerHTML anywhere on purpose: this widget's whole job is to
// display text that came from the web, from a worker or from a model, which is precisely the text that must
// never be able to execute. The html kind goes through an inert parse and a whitelist before a single node is
// adopted, and it loses its own class/style attributes on the way in — so a fragment from anywhere lands in
// THIS sheet's typography instead of dragging a foreign stylesheet's ideas into the canvas.

function injectStyles(){
  if(document.getElementById("hb-documento-css"))return;
  const s=document.createElement("style"); s.id="hb-documento-css"; s.textContent=`
  .hbd-doc{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
           color:var(--hb-ink,#0d1622);background:var(--hb-bg,#fff);display:flex;flex-direction:column;
           height:100%;min-height:0;border-radius:14px;overflow:hidden}
  .hbd-head{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;padding:14px 22px 10px;
            border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hbd-title{font-size:16px;font-weight:650;letter-spacing:-.01em;line-height:1.25;margin:0}
  .hbd-sub{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.4;flex:1 1 100%;margin:0}
  .hbd-meta{display:flex;align-items:center;gap:8px;flex:1 1 100%;margin-top:2px}
  .hbd-kind{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;font-weight:600;
            color:var(--hb-accent2,#16B8A6);border:1px solid var(--hb-line,#eef1f6);border-radius:999px;
            padding:1px 8px;white-space:nowrap}
  .hbd-src{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hbd-sheet{flex:1 1 auto;min-height:0;overflow:auto;padding:20px 24px 28px;font-size:14px;line-height:1.66}
  .hbd-sheet>*:first-child{margin-top:0}
  .hbd-sheet p{margin:0 0 .85em}
  .hbd-sheet h1,.hbd-sheet h2,.hbd-sheet h3,.hbd-sheet h4,.hbd-sheet h5,.hbd-sheet h6{
      line-height:1.3;font-weight:650;letter-spacing:-.01em;margin:1.5em 0 .5em}
  .hbd-sheet h1{font-size:19px}
  .hbd-sheet h2{font-size:16.5px}
  .hbd-sheet h3{font-size:15px}
  .hbd-sheet h4,.hbd-sheet h5,.hbd-sheet h6{font-size:14px;color:var(--hb-muted,#5b6b82)}
  .hbd-sheet ul,.hbd-sheet ol{margin:0 0 .9em;padding-left:1.35em}
  .hbd-sheet li{margin:.22em 0}
  .hbd-sheet li::marker{color:var(--hb-accent2,#16B8A6)}
  .hbd-sheet a{color:var(--hb-accent,#2f6fed);text-decoration:none;border-bottom:1px solid transparent}
  .hbd-sheet a:hover{border-bottom-color:var(--hb-accent,#2f6fed)}
  .hbd-sheet code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;
                  background:var(--hb-bg-soft,#f6f8fb);border-radius:5px;padding:1px 5px}
  .hbd-sheet pre{background:var(--hb-bg-soft,#f6f8fb);border:1px solid var(--hb-line,#eef1f6);border-radius:10px;
                 padding:12px 14px;overflow:auto;margin:0 0 1em}
  .hbd-sheet pre code{background:none;padding:0;font-size:12.5px;line-height:1.55}
  .hbd-sheet blockquote{margin:0 0 1em;padding:2px 0 2px 14px;border-left:3px solid var(--hb-accent2,#16B8A6);
                        color:var(--hb-muted,#5b6b82)}
  .hbd-sheet hr{border:0;border-top:1px solid var(--hb-line,#eef1f6);margin:1.6em 0}
  .hbd-sheet img{max-width:100%;border-radius:10px;display:block;margin:.6em 0}
  .hbd-tw{overflow-x:auto;margin:0 0 1.1em;-webkit-overflow-scrolling:touch}
  .hbd-sheet table{border-collapse:collapse;width:100%;font-size:13px}
  .hbd-sheet th,.hbd-sheet td{border-bottom:1px solid var(--hb-line,#eef1f6);padding:7px 10px;text-align:left;
                              vertical-align:top}
  .hbd-sheet th{font-weight:650;font-size:11.5px;letter-spacing:.03em;text-transform:uppercase;
                color:var(--hb-muted,#5b6b82)}
  .hbd-sheet tr:last-child td{border-bottom:0}
  .hbd-pdf{flex:1 1 auto;min-height:320px;width:100%;border:0;background:var(--hb-bg-soft,#f6f8fb)}
  .hbd-blank{flex:1 1 auto;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
             padding:34px 22px;text-align:center;color:var(--hb-muted-2,#9aa7b8)}
  .hbd-blank b{font-size:13.5px;font-weight:600;color:var(--hb-muted,#5b6b82)}
  .hbd-blank span{font-size:12px;max-width:34ch;line-height:1.5}
  .hbd-mark{width:26px;height:32px;border:1px solid var(--hb-line,#eef1f6);border-radius:3px;
            background:var(--hb-bg-soft,#f6f8fb);margin-bottom:6px}
  @media(max-width:520px){.hbd-head{padding:12px 16px 9px}.hbd-sheet{padding:16px 17px 22px;font-size:13.5px}}
  `; document.head.appendChild(s);
}

const el = (tag, cls, text) => { const n=document.createElement(tag); if(cls)n.className=cls;
  if(text!=null)n.textContent=text; return n; };

// ── links ────────────────────────────────────────────────────────────────────────────────────────────────
// A link whose scheme we do not recognise is shown as TEXT, never as a link: the sheet's content arrives from
// the open web, and `javascript:` in a markdown link is the oldest trick there is.
const SAFE_HREF = /^(https?:\/\/|mailto:|\/widgets\/|#)/i;
const SAFE_IMG = /^(https?:\/\/|\/widgets\/|data:image\/(png|jpe?g|gif|webp|avif);base64,)/i;

// ── markdown → DOM ───────────────────────────────────────────────────────────────────────────────────────
// Deliberately small: headings, lists, tables, quotes, rules, fenced code, and the four inline marks a person
// actually types. Enough for a recipe, an instruction sheet or a report, and not one construct more — this is
// a widget, not a document processor.
const INLINE = /`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*\n]+)\*|(?:^|(?<=[\s(]))_([^_\n]+)_|\[([^\]]*)\]\(([^)\s]+)\)/g;

function inlineInto(parent, text){
  const src = String(text==null?"":text);
  let last = 0, m;
  INLINE.lastIndex = 0;
  while((m = INLINE.exec(src))){
    if(m.index > last) parent.appendChild(document.createTextNode(src.slice(last, m.index)));
    if(m[1]!=null) parent.appendChild(el("code", null, m[1]));
    else if(m[2]!=null || m[3]!=null) parent.appendChild(el("strong", null, m[2]!=null?m[2]:m[3]));
    else if(m[4]!=null || m[5]!=null) parent.appendChild(el("em", null, m[4]!=null?m[4]:m[5]));
    else {
      const label = m[6] || m[7], href = m[7];
      if(SAFE_HREF.test(href)){
        const a = el("a", null, label); a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
        parent.appendChild(a);
      } else parent.appendChild(document.createTextNode(label));
    }
    last = m.index + m[0].length;
  }
  if(last < src.length) parent.appendChild(document.createTextNode(src.slice(last)));
  return parent;
}

const isTableSep = (s) => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(s) && s.indexOf("|") >= 0;
const cells = (s) => s.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(c => c.trim());

function markdownInto(root, src){
  const lines = String(src||"").replace(/\r\n?/g, "\n").split("\n");
  let i = 0, para = [];
  const flushPara = () => {
    if(!para.length) return;
    inlineInto(root.appendChild(el("p")), para.join(" "));
    para = [];
  };
  while(i < lines.length){
    const line = lines[i];
    if(/^\s*$/.test(line)){ flushPara(); i++; continue; }

    const fence = line.match(/^\s*(?:```|~~~)(.*)$/);
    if(fence){
      flushPara(); i++;
      const buf = [];
      while(i < lines.length && !/^\s*(?:```|~~~)\s*$/.test(lines[i])) buf.push(lines[i++]);
      i++;                                                   // step over the closing fence (or off the end)
      root.appendChild(el("pre")).appendChild(el("code", null, buf.join("\n")));
      continue;
    }
    const head = line.match(/^\s{0,3}(#{1,6})\s+(.*)$/);
    if(head){ flushPara(); inlineInto(root.appendChild(el("h"+head[1].length)), head[2].trim()); i++; continue; }

    if(/^\s{0,3}(?:-{3,}|_{3,}|\*{3,})\s*$/.test(line)){ flushPara(); root.appendChild(el("hr")); i++; continue; }

    if(/^\s*>\s?/.test(line)){
      flushPara();
      const buf = [];
      while(i < lines.length && /^\s*>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      markdownInto(root.appendChild(el("blockquote")), buf.join("\n"));
      continue;
    }
    // A table needs its separator row to BE a table; without it the pipes are just pipes in a sentence.
    if(line.indexOf("|") >= 0 && i+1 < lines.length && isTableSep(lines[i+1])){
      flushPara();
      // A wide table scrolls INSIDE its own box; the sheet itself must never scroll sideways (house rule).
      const table = root.appendChild(el("div","hbd-tw")).appendChild(el("table"));
      const thead = table.appendChild(el("thead")), hr = thead.appendChild(el("tr"));
      for(const c of cells(line)) inlineInto(hr.appendChild(el("th")), c);
      i += 2;
      const tbody = table.appendChild(el("tbody"));
      while(i < lines.length && lines[i].indexOf("|") >= 0 && !/^\s*$/.test(lines[i])){
        const tr = tbody.appendChild(el("tr"));
        for(const c of cells(lines[i++])) inlineInto(tr.appendChild(el("td")), c);
      }
      continue;
    }
    const bullet = line.match(/^\s*[-*+•]\s+(.*)$/), numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if(bullet || numbered){
      flushPara();
      const ordered = !!numbered;
      const list = root.appendChild(el(ordered ? "ol" : "ul"));
      while(i < lines.length){
        const m = lines[i].match(ordered ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*+•]\s+(.*)$/);
        if(!m) break;
        const li = list.appendChild(el("li"));
        inlineInto(li, m[1]);
        i++;
        // A wrapped bullet continues on the next indented, unmarked line rather than starting a paragraph.
        while(i < lines.length && /^\s{2,}\S/.test(lines[i]) &&
              !/^\s*(?:[-*+•]|\d+[.)])\s+/.test(lines[i])){
          inlineInto(li, " " + lines[i++].trim());
        }
      }
      continue;
    }
    para.push(line.trim());
    i++;
  }
  flushPara();
  return root;
}

// ── html → DOM (inert parse, then a whitelist) ───────────────────────────────────────────────────────────
// Parsing into a detached document runs nothing and loads nothing; only nodes that survive the whitelist are
// ever adopted into the page. Unknown-but-harmless wrappers become plain divs so their CONTENT is not lost,
// while the tags that carry behaviour are dropped whole, children and all.
const HTML_OK = new Set(["P","DIV","SPAN","A","B","STRONG","I","EM","U","S","DEL","INS","MARK","SMALL","SUB","SUP",
  "CODE","PRE","KBD","SAMP","BR","HR","H1","H2","H3","H4","H5","H6","UL","OL","LI","DL","DT","DD","BLOCKQUOTE",
  "FIGURE","FIGCAPTION","IMG","TABLE","THEAD","TBODY","TFOOT","TR","TD","TH","CAPTION","SECTION","ARTICLE",
  "HEADER","FOOTER","MAIN","ASIDE","NAV","ABBR","TIME","ADDRESS"]);
const HTML_DROP = new Set(["SCRIPT","STYLE","IFRAME","FRAME","FRAMESET","OBJECT","EMBED","APPLET","FORM","INPUT",
  "BUTTON","SELECT","TEXTAREA","OPTION","LABEL","LINK","META","BASE","TEMPLATE","SVG","MATH","AUDIO","VIDEO",
  "SOURCE","TRACK","CANVAS","NOSCRIPT","DIALOG","PORTAL"]);

function cleanNode(node, depth){
  if(node.nodeType === 3) return document.createTextNode(node.nodeValue);
  if(node.nodeType !== 1 || depth > 24) return null;
  const tag = node.tagName ? node.tagName.toUpperCase() : "";
  if(HTML_DROP.has(tag)) return null;
  const known = HTML_OK.has(tag);
  const out = document.createElement(known ? tag.toLowerCase() : "div");
  if(known && tag === "A"){
    const href = node.getAttribute("href") || "";
    if(SAFE_HREF.test(href)){ out.href = href; out.target = "_blank"; out.rel = "noopener noreferrer"; }
  } else if(known && tag === "IMG"){
    const src = node.getAttribute("src") || "";
    if(!SAFE_IMG.test(src)) return null;
    out.src = src; out.alt = node.getAttribute("alt") || "";
  } else if(known && (tag === "TD" || tag === "TH")){
    for(const a of ["colspan","rowspan"]){
      const v = parseInt(node.getAttribute(a) || "", 10);
      if(v > 1 && v < 100) out.setAttribute(a, String(v));
    }
  }
  // No `class`, no `style`, no `on*` — ever. Dropping the fragment's own styling is not a limitation here, it
  // is the point: whatever page it came from, it lands in this sheet's typography and in the live theme.
  for(const ch of Array.from(node.childNodes)){
    const c = cleanNode(ch, depth + 1);
    if(c) out.appendChild(c);
  }
  return out;
}

function htmlInto(root, src){
  let body = null;
  try{ body = new DOMParser().parseFromString(String(src||""), "text/html").body; }catch(_){ body = null; }
  if(!body){ root.appendChild(el("p", null, String(src||""))); return root; }
  for(const n of Array.from(body.childNodes)){
    const c = cleanNode(n, 0);
    if(c) root.appendChild(c);
  }
  return root;
}

// ── the card ─────────────────────────────────────────────────────────────────────────────────────────────
const KIND_LABEL = { markdown:"documento", html:"documento", pdf:"pdf" };

function blank(root){
  const box = root.appendChild(el("div","hbd-blank"));
  box.appendChild(el("div","hbd-mark"));
  box.appendChild(el("b", null, "Hoja en blanco"));
  box.appendChild(el("span", null, "Aquí va lo que sea para leer: una receta, un informe, unas instrucciones o un PDF."));
}

export function render(root, data, ctx){
  injectStyles();
  root.className = "hbd-doc";
  root.textContent = "";
  const d = data || {};

  if(d.error){
    const box = root.appendChild(el("div","hbd-blank"));
    box.appendChild(el("b", null, "No se pudo abrir el documento"));
    box.appendChild(el("span", null, String(d.error)));
    return;
  }

  const title = String(d.title||"").trim();
  const subtitle = String(d.subtitle||"").trim();
  const source = String(d.source||"").trim();
  const kind = KIND_LABEL[d.kind] ? d.kind : "markdown";
  const empty = !!d.empty || (!String(d.body||"").trim() && !String(d.src||"").trim());

  // The card header already carries the title when the host asked for a live title; repeating it there and
  // here is the same sentence twice, on the two lines that are hardest to ignore.
  const ownTitle = root.dataset.hostTitle !== "1" && !!title;
  if(ownTitle || subtitle || source || !empty){
    const head = root.appendChild(el("div","hbd-head"));
    if(ownTitle) head.appendChild(el("h3","hbd-title", title));
    if(subtitle) head.appendChild(el("p","hbd-sub", subtitle));
    if(!empty){
      const meta = head.appendChild(el("div","hbd-meta"));
      meta.appendChild(el("span","hbd-kind", KIND_LABEL[kind]));
      if(source) meta.appendChild(el("span","hbd-src", source));
    }
  }

  if(empty){ blank(root); return; }

  if(kind === "pdf"){
    const frame = el("iframe","hbd-pdf");
    frame.setAttribute("title", title || "documento");
    frame.src = String(d.src||"");
    root.appendChild(frame);
    return;
  }

  const sheet = root.appendChild(el("div","hbd-sheet"));
  if(kind === "html") htmlInto(sheet, d.body);
  else markdownInto(sheet, d.body);
}
