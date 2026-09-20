// markdown-lite.js — dependency-free, XSS-safe formatter for chat messages. Cluster peers and worker output
// (Claude Code and friends) send markdown-flavoured text (bold, lists, inline code) that used to render as raw
// text with literal asterisks/dashes. Escapes HTML FIRST, then only introduces safe tags from the escaped
// string — a peer typing "<script>" ends up as inert "&lt;script&gt;" text, never a real element.
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };
const escapeHtml = (s) => String(s).replace(/[&<>]/g, (c) => ESC[c]);

// V2-736 — a link in the conversation is a LINK. The operator asked the agent to leave him the public
// guide in the chat («te dejo ahí la web para que veas más información»), and until now that arrived as
// plain text he would have had to select and copy by hand — the message said «here it is» and there was
// nothing to click. Autolinking runs LAST, over already-escaped text, and only matches a literal
// `http://` or `https://`: nothing else can become an anchor, so a peer writing `javascript:` or an
// `onclick=` gets inert text exactly as before.
//
// Trailing punctuation is left OUT of the href on purpose: «mira zaelar.com/guide.» ends a sentence far
// more often than it names a path, and a link that 404s on a full stop is worse than one that stops a
// character early. A closing bracket only leaves the link when it is unbalanced, so a URL that really
// contains one survives.
// Quotes are EXCLUDED from the match and the escaped angle brackets end it. `escapeHtml` does not touch
// `"`, so a URL containing one would close the href and everything after it would be markup we did not
// write — measured while writing this: `<a href="https://evil.example">click</a>` escapes to text whose
// URL run swallows `"&gt;click&lt;/a&gt`, and the anchor built from it broke out of its own attribute.
// And an escaped `&lt;`/`&gt;`/`&quot;` inside a URL run is always a character the author wrote literally,
// never part of an address: cut there.
const URL_RE = /\bhttps?:\/\/[^\s<>"']+/g;
const CUTS = ["&lt;", "&gt;", "&quot;", "&#39;"];

function autolink(html) {
  return html.replace(URL_RE, (raw) => {
    let url = raw, tail = "";
    for (const c of CUTS) {
      const i = url.indexOf(c);
      if (i >= 0) { tail = url.slice(i) + tail; url = url.slice(0, i); }
    }
    if (!/^https?:\/\/[^\s]/.test(url)) return raw;     // nothing left that is an address
    while (url.length > 1) {
      const last = url[url.length - 1];
      if (".,;:!?'".includes(last)) { tail = last + tail; url = url.slice(0, -1); continue; }
      if (last === ")" && (url.match(/\(/g) || []).length < (url.match(/\)/g) || []).length) {
        tail = last + tail; url = url.slice(0, -1); continue;
      }
      break;
    }
    // Belt and braces on top of the character class: a quote can never reach the attribute.
    if (/["'<>]/.test(url)) return raw;
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>${tail}`;
  });
}

function inline(line) {
  return autolink(
    escapeHtml(line)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>"));
}

export function renderMarkdownLite(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let list = null; // "ol" | "ul" | null while inside a list run
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const line of lines) {
    const num = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const bul = !num && line.match(/^\s*[-*•]\s+(.*)$/);
    if (num || bul) {
      const type = num ? "ol" : "ul";
      if (list !== type) { closeList(); out.push(`<${type}>`); list = type; }
      out.push(`<li>${inline((num || bul)[1])}</li>`);
    } else {
      closeList();
      out.push(inline(line));
    }
  }
  closeList();
  return out.join("\n");
}
