// ============================================================================
// test_a_report_says_what_kind_it_is.mjs — V2-695, node 4.33.
//
// The operator's ask, in his words: «I want people communicate errors or desires… whether something
// they tried failed, or maybe they have an idea, something they want to do, and they send it to us».
// One box could never tell those apart, so neither could whoever reads the inbox.
//
// Two levels here, and the picture budget is the reason the file is worth its own node: `prepare()`
// needs a browser (canvas, createImageBitmap), but every DECISION around it is arithmetic — how many
// fit, what is left, which limit a refusal hit — and arithmetic runs under Node. That is what lets
// the budget have a ratchet instead of a comment.
// ============================================================================
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = resolve(HERE, "../../../../frontend/app");
const MOBILE = resolve(HERE, "../../../../frontend/mobile/app");

const shots = await import(resolve(APP, "services/feedback-images.js"));

// --- 1. the budget, and a refusal that NAMES the limit it hit -----------------------------------
//
// A picture dropped in silence is a picture the person believes they sent — so `refusal` returns the
// REASON key rather than a bare boolean, and the caller can say which of the two ceilings was reached.
{
  const L = shots.LIMITS;
  assert.equal(shots.refusal([], 1000), "", "an empty form takes a small picture");

  const full = Array.from({ length: L.maxShots }, () => ({ bytes: 1000 }));
  assert.equal(shots.refusal(full, 1000), "feedback.tooManyShots");

  const heavy = [{ bytes: L.maxTotalBytes - 500 }];
  assert.equal(shots.refusal(heavy, 1000), "feedback.shotsTooBig");
  assert.equal(shots.refusal(heavy, 400), "", "what still fits in the budget is taken");

  assert.equal(shots.budgetLeft([{ bytes: L.maxTotalBytes + 9999 }]), 0,
    "the budget never goes negative — a refusal must not turn into an invitation");
  assert.equal(shots.spent([{ bytes: 10 }, { bytes: "x" }, null]), 10,
    "an unreadable size counts as nothing rather than crashing the form");
}

// --- 2. the box a picture is fitted into, and the one it is NOT -----------------------------------
{
  assert.deepEqual(shots.targetSize(3200, 1800, 1280), { w: 1280, h: 720 },
    "the longest side lands on the cap and the shape is kept");
  assert.deepEqual(shots.targetSize(1800, 3200, 1280), { w: 720, h: 1280 });
  assert.deepEqual(shots.targetSize(640, 480, 1280), { w: 640, h: 480 },
    "a small picture is never ENLARGED — that only costs bytes");
}

// --- 3. only images -------------------------------------------------------------------------------
{
  assert.equal(shots.isImage({ type: "image/png" }), true);
  assert.equal(shots.isImage({ type: "text/plain" }), false, "he asked for images only");
  assert.equal(shots.isImage(null), false);
  assert.equal(shots.dataUrl({ mime: "image/webp", data: "AAA" }), "data:image/webp;base64,AAA");
  assert.equal(shots.dataUrl(null), "", "a shot with no bytes points at nothing, never at 'undefined'");
}

// --- 4. THE WIRING: both surfaces say what kind of report they are sending -------------------------
//
// V2-252's rule: a decision applied in one channel stops existing in the other. The desktop panel and
// the phone's ☰ sheet share `feedback-api.js`, so they inherit the transport for free — what they do
// NOT inherit is remembering to fill the new field.
const SURFACES = [
  ["FeedbackWidget.js", readFileSync(resolve(APP, "components/FeedbackWidget.js"), "utf8")],
  ["MenuSheet.js", readFileSync(resolve(MOBILE, "shell/MenuSheet.js"), "utf8")],
];

for (const [name, src] of SURFACES) {
  assert.ok(/kind:\s*\w+\(\)/.test(src), `${name}: the report travels without saying what kind it is`);
  assert.ok(/feedback\.kindIssue/.test(src) && /feedback\.kindIdea/.test(src),
    `${name}: both options have to exist, or there is nothing to choose between`);
  assert.ok(/createSignal\(\s*"issue"\s*\)/.test(src),
    `${name}: one option is always picked — an unset selector sends an unlabelled report`);
}

// The API wrapper is the ONE door (a test at tests/run_testmap.py already pins that both surfaces go
// through it rather than calling fetch inline) — so the field has to be in its body, not only in a
// caller's argument list.
{
  const api = readFileSync(resolve(APP, "services/feedback-api.js"), "utf8");
  assert.ok(/JSON\.stringify\(\{[^}]*\bkind\b/s.test(api), "feedback-api.js drops `kind` on the floor");
  assert.ok(/JSON\.stringify\(\{[^}]*\bshots\b/s.test(api), "feedback-api.js drops the pictures");
}

// --- 5. the paste trap ----------------------------------------------------------------------------
//
// `main.js` installs a WINDOW-level paste handler that grabs any image on the clipboard and uploads it
// to the episodic memory inbox — its own comment says it does that even while focus is in an input.
// Without stopPropagation, pasting a screenshot into the feedback box files it somewhere nobody asked
// for and the report goes out with nothing attached. Node 4.34 measures it in a real browser; this is
// the cheap guard that fires on every suite.
{
  const src = SURFACES[0][1];
  const onPaste = src.slice(src.indexOf("const onPaste"), src.indexOf("const onDrop"));
  assert.ok(/stopPropagation\(\)/.test(onPaste),
    "the panel's paste must not reach main.js, or the screenshot lands in episodic memory instead");
  assert.ok(/if\s*\(!files\.length\)\s*return/.test(onPaste),
    "a plain TEXT paste has to pass through untouched");
}

console.log("ok");
