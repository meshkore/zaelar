// «Cierra la pantalla completa» IS NOT A CLOSE-ALL — the CLIENT copy of the rule (V2-600 → V2-601 T-07).
//
// V2-600 measured it live (session 3050e623): the operator asked the video OUT of fullscreen, the STT rendered
// «…completamente», and the whole canvas closed. The veto (`attention.mentions_fullscreen`) landed in the two
// server backstops — and `voiceCommands.js`, the third, client-side copy of the close rule, kept matching
// CLOSE_RE("cierr") + ALL_RE("la pantalla") on that exact sentence and calling desktop.closeAll(). This drives
// the REAL module (api.js stubbed at the import line, nothing else touched) with the measured sentences.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");

let src = readFileSync(path.join(root, "frontend/app/services/voiceCommands.js"), "utf8");
const importLine = /import \{ identifyWidget \} from "\.\/api\.js[^"]*";/;
assert.ok(importLine.test(src), "the api.js import moved — repoint the stub");
src = src.replace(importLine, "const identifyWidget = async () => null;");   // no server in this test
// A FRESH module per case: the real module dedupes identical actions for 2.5 s at module scope
// (`_lastVoiceAct`), so two legitimate closeAll cases in one import would hide the second.
let _n = 0;
const freshMod = () => import("data:text/javascript," + encodeURIComponent(src + "\n// " + (_n++)));

function fakeDesktop() {
  const calls = [];
  return {
    calls,
    closeAll: () => calls.push("closeAll"),
    close: id => calls.push("close:" + id),
    show: id => calls.push("show:" + id),
    move: (id, w) => calls.push("move:" + id + ":" + w),
    list: () => ["youtube"],
  };
}

// The two measured phrasings (the second is what the STT actually heard) must NOT touch the canvas.
for (const heard of ["Cierra la pantalla completa.", "Cierra la pantalla completamente.",
                     "close the fullscreen", "quita el full screen"]) {
  const d = fakeDesktop();
  const mod = await freshMod();
  await mod.handleWidgetVoice(d, heard, true);
  assert.deepEqual(d.calls.filter(c => c.startsWith("close")), [],
    `«${heard}» is a screen-state order and closed: ${d.calls}`);
}

// Counterweight: a REAL close-all still closes — the veto must not eat the order it sits next to.
{
  const d = fakeDesktop();
  const mod = await freshMod();
  await mod.handleWidgetVoice(d, "Cierra todos los widgets.", true);
  assert.deepEqual(d.calls, ["closeAll"], `close-all lost: ${d.calls}`);
}
// …and «cierra la pantalla» WITHOUT the fullscreen word keeps its historical meaning (the whole canvas).
{
  const d = fakeDesktop();
  const mod = await freshMod();
  await mod.handleWidgetVoice(d, "Cierra la pantalla.", true);
  assert.deepEqual(d.calls, ["closeAll"], `bare «cierra la pantalla» changed meaning: ${d.calls}`);
}

console.log("close-all fullscreen veto: OK");
