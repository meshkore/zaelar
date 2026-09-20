// ============================================================================
// test_a_link_in_the_conversation_is_a_link.mjs — V2-736, node 4.196.
//
// THE OPERATOR'S ASK (2026-09-20, about the first conversation): «puedes
// publicar el enlace de la web en el chat y dársela para decir: mira, te dejo
// ahí la web para que veas más información o acceso a la documentación
// pública».
//
// Measured before writing a line of prompt: `markdown-lite.js` rendered bold,
// code and lists and NOTHING about URLs, so the message said «here it is» and
// left him text to select and copy by hand. Telling the agent to publish a link
// into a surface that cannot show one is the «capacidad sin declarar» failure
// with the halves swapped.
//
// The safety half matters as much: this renderer exists because peers and
// workers send text we did not write. Escaping happens FIRST and autolinking
// only ever matches a literal http(s) scheme, so nothing else can become an
// anchor.
//
// Run: node tests/browser/unit/chat/test_a_link_in_the_conversation_is_a_link.mjs
// ============================================================================
import assert from "node:assert/strict";

const { renderMarkdownLite } = await import("../../../../frontend/app/lib/markdown-lite.js");
const html = (s) => renderMarkdownLite(s);

// Everything this renderer is allowed to emit. Anything else in the output came from the message.
const OURS = new Set(["a", "/a", "strong", "/strong", "code", "/code", "em", "/em",
                      "ul", "/ul", "ol", "/ol", "li", "/li"]);
const tagsIn = (s) => [...s.matchAll(/<(\/?[a-zA-Z][^\s>]*)/g)].map(m => m[1].toLowerCase());

// Every anchor we emit must be EXACTLY the one shape we build. `escapeHtml` does not touch quotes, so a
// quote reaching the href closes the attribute early and whatever follows becomes markup we did not
// write — measured while building this: `<a href="https://evil.example">click</a>` escapes to text whose
// URL run swallows `"&gt;click&lt;/a&gt`, and the anchor built from it broke out of its own attribute.
// Asserting «no foreign element» does NOT catch that (nothing new is created, the tag is merely
// malformed), which is why the shape is pinned here instead.
function anchorsAreWellFormed(out) {
  for (const m of out.matchAll(/<a\b[^>]*>/g)) {
    if (!/^<a href="[^"'<>\s]+" target="_blank" rel="noopener noreferrer">$/.test(m[0])) return m[0];
  }
  return "";
}

// ── 1. the operator's own case ──────────────────────────────────────────────────────────────────────────
{
  const out = html("Te dejo la guía: https://zaelar.com/guide");
  assert.ok(out.includes('<a href="https://zaelar.com/guide"'),
    `THE BUG: the link arrived as text he had to copy by hand — ${out}`);
  assert.ok(out.includes('target="_blank"') && out.includes('rel="noopener noreferrer"'),
    "a link out of the conversation opens beside it, and never hands over the opener");
  assert.ok(out.includes(">https://zaelar.com/guide</a>"), "and it still READS as the address it is");
}

// ── 2. punctuation belongs to the sentence, not to the URL ──────────────────────────────────────────────
for (const [line, href] of [
  ["Mira https://zaelar.com/guide.", "https://zaelar.com/guide"],
  ["¿Has visto https://zaelar.com/guide?", "https://zaelar.com/guide"],
  ["(ver https://zaelar.com/guide/examples)", "https://zaelar.com/guide/examples"],
  ["https://en.wikipedia.org/wiki/Spain_(disambiguation)", "https://en.wikipedia.org/wiki/Spain_(disambiguation)"],
]) {
  const out = html(line);
  assert.ok(out.includes(`href="${href}"`), `${line} → ${out}`);
}

// ── 3. a query string survives being escaped ────────────────────────────────────────────────────────────
{
  const out = html("https://x.com/a?b=1&c=2");
  assert.ok(out.includes('href="https://x.com/a?b=1&amp;c=2"'), out);
}

// ── 4. NOTHING but http(s) becomes a link, and the escaping still comes first ───────────────────────────
for (const hostile of [
  "javascript:alert(1)",
  "data:text/html;base64,PHNjcmlwdD4=",
  '<a href="https://evil.example">click</a>',
  "<script>alert(1)</script>",
  '<img src=x onerror="alert(1)">',
  "file:///etc/passwd",
]) {
  const out = html(hostile);
  // The renderer may only ever produce tags from its own short list. `onerror="…"` as visible TEXT is
  // fine and is exactly what escaping is for — what must not exist is an ELEMENT nobody here wrote.
  assert.deepEqual(tagsIn(out).filter(t => !OURS.has(t)), [], `an element appeared: ${out}`);
  assert.ok(!/<a href="(?!https?:\/\/)/.test(out), `only http(s) may become an href: ${out}`);
  assert.equal(anchorsAreWellFormed(out), "", `a malformed anchor is an attribute boundary escaping: ${out}`);
}
{
  // Somebody's own <a> tag stays INERT TEXT; the addresses in the message are linked by us, and the
  // anchor we build can never carry anything but an http(s) href.
  const out = html('mira <a href="https://evil.example">esto</a> y https://zaelar.com');
  assert.ok(out.includes("&lt;a href="), "their markup stays inert text");
  assert.ok(out.includes('<a href="https://zaelar.com"'), "and the address in the message is a link");
  assert.ok(!/<a href="(?!https?:\/\/)/.test(out), out);
  assert.equal(anchorsAreWellFormed(out), "",
    `THE HOLE: their quote closed our href and the rest became markup — ${out}`);
  assert.ok(!out.includes('">click</a>') && !out.includes('">esto</a>'),
    "no element of theirs survives — only text");
}

// ── 5. everything the renderer already did still works ──────────────────────────────────────────────────
assert.ok(html("**fuerte**").includes("<strong>fuerte</strong>"));
assert.ok(html("`code`").includes("<code>code</code>"));
assert.ok(html("- uno\n- dos").includes("<ul>"));
assert.ok(html("1. uno").includes("<ol>"));

console.log("ok: a link in the conversation is a link, and nothing else is");
