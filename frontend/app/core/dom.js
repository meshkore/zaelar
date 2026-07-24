// ============================================================================
// dom.js — tiny hyperscript element factory. The JSX-equivalent for this build.
//
// MIGRATION: in Solid these h() calls become JSX, 1:1:
//     h("div", {class:"x", onClick:f}, child)   <->   <div class="x" onClick={f}>{child}</div>
// A FUNCTION passed as an attribute value or as a child is a reactive binding
// (Solid: {signal()} ). Static values are set once.
// ============================================================================
import { createEffect } from "./reactive.js?v=2";

function bind(v, apply) {
  if (typeof v === "function") createEffect(() => apply(v())); else apply(v);
}

function toNode(v) {
  if (v == null || v === false) return null;
  if (v instanceof Node) return v;
  return document.createTextNode(String(v));
}

function appendChildren(el, children) {
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    if (c instanceof Node) { el.appendChild(c); continue; }
    if (typeof c === "function") {
      // Reactive child. The function may return text, a single Node, or an ARRAY of Nodes
      // (e.g. list.map(row)). We anchor with a trailing comment and re-render between the
      // last-inserted nodes and the anchor, so `textContent = [node, node]` (which would
      // stringify to "[object HTMLDivElement],…") never happens.
      const anchor = document.createComment("");
      el.appendChild(anchor);
      let rendered = [];
      createEffect(() => {
        for (const n of rendered) if (n.parentNode) n.parentNode.removeChild(n);
        rendered = [];
        const val = c();
        for (const item of (Array.isArray(val) ? val : [val])) {
          const node = toNode(item);
          if (!node) continue;
          anchor.parentNode.insertBefore(node, anchor);
          rendered.push(node);
        }
      });
    } else {
      el.appendChild(document.createTextNode(String(c)));
    }
  }
}

export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) {
    if (k === "ref" && typeof v === "function") v(el);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "class" || k === "className") bind(v, (val) => { el.className = val ?? ""; });
    else if (k === "html") bind(v, (val) => { el.innerHTML = val ?? ""; });
    else if (k === "style" && typeof v === "object") for (const [sk, sv] of Object.entries(v)) bind(sv, (val) => { el.style[sk] = val; });
    else bind(v, (val) => {
      if (val === false || val == null) el.removeAttribute(k);
      else if (val === true) el.setAttribute(k, "");
      else el.setAttribute(k, val);
    });
  }
  appendChildren(el, children);
  return el;
}

// Raw SVG/HTML markup → element. Used to port the icon SVGs verbatim from the old markup.
export function raw(markup) {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export function mount(node, parent = document.body) { parent.appendChild(node); return node; }
