// markdown-lite.js — dependency-free, XSS-safe formatter for chat messages. Cluster peers and worker output
// (Claude Code and friends) send markdown-flavoured text (bold, lists, inline code) that used to render as raw
// text with literal asterisks/dashes. Escapes HTML FIRST, then only introduces safe tags from the escaped
// string — a peer typing "<script>" ends up as inert "&lt;script&gt;" text, never a real element.
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };
const escapeHtml = (s) => String(s).replace(/[&<>]/g, (c) => ESC[c]);

function inline(line) {
  return escapeHtml(line)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>");
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
