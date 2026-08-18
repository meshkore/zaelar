// ============================================================================
// test_mobile_host_contract.mjs — THE CONTRACT THAT MAKES THE MOBILE SPLIT SAFE TO KEEP (V2-124).
//
// What this protects, and why it is the RIGHT thing to test:
//
// The mobile shell (frontend/mobile/) is a second host for two contracts that services/sse.js and every widget
// already speak. It works today. The question this file answers is whether it will still work in three months,
// when someone adds a method to sse.js's host protocol, or renames one, or deletes a Deck method that looked
// unused — with the DESKTOP staying green the whole time, because the desktop has its own host.
//
// So the assertions are DERIVED FROM THE SOURCE OF TRUTH, never a hand-copied list:
//   1. every `desktop.<method>` that sse.js actually calls must exist on Deck  → a method added there fails here
//   2. plus setRunning (main.js) and _reportOpen (session-lk.js), the two the bridges call directly
//   3. no `/api/...` or `/widgets/...` endpoint invented by the Deck that the desktop host does not also use
//      — the mobile shell adds NO backend surface, and a typo'd URL is a feature that fails silently at runtime
//   4. the palette/veil stylesheets are SHARED, not forked (a second copy of the --hb-* tokens would not fail
//      loudly: it would make a widget paint wrong colors in one shell only)
//   5. the desktop layout stylesheet is NOT loaded by the mobile shell, which is the entire point of the split
//
// A test that hard-coded the 13 method names would pass forever while the phone silently ignored the brain.
// Run: node tests/browser/unit/mobile/test_mobile_host_contract.mjs
// ============================================================================

import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ENGINE = join(HERE, "..", "..", "..", "..");
const read = (...p) => readFileSync(join(ENGINE, ...p), "utf8");

const SSE = read("frontend", "app", "services", "sse.js");
const SESSION_LK = read("frontend", "app", "services", "session-lk.js");
const DESKTOP = read("frontend", "app", "widgets", "desktop.js");
const DECK = read("frontend", "mobile", "app", "shell", "Deck.js");
const MOBILE_MAIN = read("frontend", "mobile", "app", "main.js");
const MOBILE_HTML = read("frontend", "mobile", "index.html");
const DESKTOP_HTML = read("frontend", "index.html");
const MOBILE_CSS = read("frontend", "mobile", "app", "styles.css");
const PALETTE = read("frontend", "app", "core", "palette.css");
const SW = read("frontend", "mobile", "sw.js");
const INGRESS = read("server", "ingress.py");
const DOCKBAR = read("frontend", "mobile", "app", "shell", "DockBar.js");
const ORBMINI = read("frontend", "mobile", "app", "shell", "OrbMini.js");
const ORB_JS = read("frontend", "app", "components", "Orb.js");

let failures = 0;
function check(name, ok, detail = "") {
  if (ok) { console.log(`  ok   ${name}`); return; }
  failures++;
  console.log(`  FAIL ${name}${detail ? "\n       " + detail : ""}`);
}

// ── 1+2. THE HOST CONTRACT, read out of the bridges themselves ────────────────────────────────────────────────
const sseCalls = [...new Set([...SSE.matchAll(/\bdesktop\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g)].map((m) => m[1]))];
check("sse.js exposes a non-trivial host protocol", sseCalls.length >= 10,
  `found only ${sseCalls.length}: ${sseCalls.join(", ")} — if sse.js was refactored, this test is reading the wrong thing`);

const bridgeCalls = [...new Set([...SESSION_LK.matchAll(/__zaelarDesktop\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g)].map((m) => m[1]))];
const mainCalls = [...new Set([...MOBILE_MAIN.matchAll(/\bdeck\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g)].map((m) => m[1]))];
const required = [...new Set([...sseCalls, ...bridgeCalls, ...mainCalls, "setRunning"])];

// A method on a class body: `name(` or `async name(` at the start of an indented line.
const deckMethods = new Set([...DECK.matchAll(/^\s{2}(?:async\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/gm)].map((m) => m[1])
  .concat([...DECK.matchAll(/^\s{2}(?:get|set)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/gm)].map((m) => m[1])));

const missing = required.filter((m) => !deckMethods.has(m));
check("Deck implements every method the bridges call", missing.length === 0,
  `missing on Deck: ${missing.join(", ")}\n       required (derived from sse.js + session-lk.js + mobile main.js): ${required.join(", ")}`);

// The desktop host must satisfy the same protocol — if it stops, the protocol changed and BOTH hosts need looking at.
const desktopMethods = new Set([...DESKTOP.matchAll(/^\s{2}(?:async\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/gm)].map((m) => m[1]));
const desktopMissing = sseCalls.filter((m) => !desktopMethods.has(m));
check("the desktop host still satisfies the same protocol (sanity check on how this test reads code)",
  desktopMissing.length === 0, `missing on Desktop: ${desktopMissing.join(", ")}`);

// ── 3. EVERY ENDPOINT THE DECK FETCHES MUST REALLY EXIST ──────────────────────────────────────────────────────
// Checked against the ROUTE DECLARATIONS in Python, not against what the desktop host happens to use — the Deck
// legitimately calls one route the desktop does not (`/widgets/identify`, the server-side name resolver), and a
// test phrased as "whatever the desktop does" would have forced a worse Deck to stay green.
//
// This is the failure mode worth catching: a mistyped or invented URL 404s inside a best-effort fetch, the catch
// swallows it, and the feature silently does nothing. Nothing else in this repo would notice.
const urlsIn = (src) => [...src.matchAll(/["'`](\/(?:api|widgets)\/[a-zA-Z0-9_\-./{}$]*)/g)].map((m) => m[1]);
// A route pattern and a call site have different shapes: `/widgets/{wid}/data` vs `/widgets/${baseId}/data`.
// Both collapse to `/widgets/:p/data` so they can be compared at all.
const norm = (u) => u
  .replace(/\$\{[^}]*\}/g, ":p")       // JS template interpolation
  .replace(/\{[^}]*\}/g, ":p")          // FastAPI path parameter
  .replace(/\?.*$/, "")                 // query string is not part of the route
  .replace(/\/+$/, "");
const PY_SOURCES = ["widgets/server_api.py", "server/pages.py", "server/config_api.py", "server/voice_api.py",
                    "nucleo/worker_api.py", "nucleo/cron_api.py", "memory/server_api.py", "server/livekit_api.py",
                    "server/feedback_api.py", "server/i18n_api.py"];
const declared = new Set();
for (const f of PY_SOURCES) {
  let src = "";
  try { src = read(...f.split("/")); } catch { continue; }
  for (const m of src.matchAll(/@(?:router|app)\.(?:get|post|put|delete|patch)\(\s*["']([^"']+)["']/g)) declared.add(norm(m[1]));
}
// `/api/canvas/state`, `/api/client-log`, `/api/desktop/epoch` and friends are declared in server/__init__.py,
// which is 31 KB of app wiring — scanned too rather than special-cased, so this list needs no maintenance.
for (const m of read("server", "__init__.py").matchAll(/@app\.(?:get|post|put|delete|patch)\(\s*["']([^"']+)["']/g)) declared.add(norm(m[1]));

check("the route scan found the real API surface", declared.size >= 40,
  `only ${declared.size} routes found — the decorator scan is reading the wrong files, so the check below proves nothing`);

const deckUrls = [...new Set(urlsIn(DECK).map(norm))];
const unknown = deckUrls.filter((u) => !declared.has(u));
check("every endpoint the Deck fetches is a declared backend route", unknown.length === 0,
  `not declared anywhere: ${unknown.join(", ")}\n       (the Deck fetches: ${deckUrls.join(", ")})`);

// ── 4. SHARED PALETTE, NOT A FORK ─────────────────────────────────────────────────────────────────────────────
check("palette.css owns the --hb-* color contract", /--hb-bg\s*:/.test(PALETTE) && /--hb-accent\s*:/.test(PALETTE));
check("both shells link palette.css",
  /core\/palette\.css/.test(MOBILE_HTML) && /core\/palette\.css/.test(DESKTOP_HTML));
check("both shells link shared-surfaces.css (the veils/banner they both mount)",
  /core\/shared-surfaces\.css/.test(MOBILE_HTML) && /core\/shared-surfaces\.css/.test(DESKTOP_HTML));
// The forked-palette failure mode: mobile CSS defining tokens instead of consuming them.
const mobileDefinesTokens = /^\s*--hb-[a-z0-9-]+\s*:/m.test(MOBILE_CSS);
check("the mobile stylesheet CONSUMES the palette and does not redefine it", !mobileDefinesTokens,
  "mobile/app/styles.css defines an --hb-* token; it must come from app/core/palette.css or the two shells will drift");

// ── 5. THE SPLIT IS REAL ──────────────────────────────────────────────────────────────────────────────────────
// Match only real <link href=...> values: the surrounding prose in that file NAMES app/styles.css to explain why
// it is absent, and a substring test would fail on the explanation. Assertions must read markup, not comments.
const linkedCss = [...MOBILE_HTML.matchAll(/<link[^>]+href=["']([^"']+)["']/g)].map((m) => m[1]);
check("the mobile shell does NOT load the desktop layout stylesheet",
  // Anchored at /static/app/: the mobile shell's OWN stylesheet is /static/mobile/app/styles.css, which a looser
  // pattern matches too — the check would then fail on the very file it is meant to require.
  !linkedCss.some((h) => /^\/static\/app\/styles\.css/.test(h)),
  `mobile/index.html links the desktop stylesheet (${linkedCss.join(", ")}) — that ~90 KB of 3-column canvas is exactly what this shell exists to avoid`);
check("nothing in the desktop app imports from mobile/",
  !/mobile\//.test(DESKTOP) && !/mobile\//.test(SSE),
  "the dependency must point one way only: mobile may import shared app/ code, never the reverse");
check("the mobile shell shares the STORE (one truth about the agent, not two)",
  /app\/core\/store\.js/.test(MOBILE_MAIN),
  "a mobile-only store would be a second truth about power/energy/chat — the failure mode this codebase has paid for repeatedly");

// ── the service worker must stay almost empty ──────────────────────────────────────────────────────────────────
// A cached module is a stale agent. The engine serves `/` with no-store precisely to prevent that, so a SW that
// grew a cache would silently undo it — and the symptom would be a phone running an agent version that no longer
// exists. These two assertions are the ratchet on that.
check("the service worker only intercepts navigations",
  /\.mode\s*!==\s*["']navigate["']/.test(SW),
  "sw.js must bail out for anything that is not a navigation — /api/*, /events (SSE) and /widgets/* must never pass through it");
check("the service worker never stores a response",
  !/\.put\s*\(/.test(SW),
  "sw.js calls cache.put — the shell must never be stored, or a reload can serve stale JavaScript");

// ── the PWA's three root paths must be in the admission allowlist, or they 401 on a routing Machine ────────────
for (const path of ["/m", "/manifest.webmanifest", "/sw.js"]) {
  check(`ingress.py allowlists ${path}`, INGRESS.includes(`"${path}"`),
    `server/ingress.py's PUBLIC_EXACT does not list ${path}; a browser would get 401 before any session exists`);
}


// ── THE DOCK: the orb is the CENTRE, and it is also the switch ─────────────────────────────────────────────────
// Operator's design (2026-08-18): «un orbe en el centro del footer… y en los laterales del orbe, el resto de
// botones», with the orb doubling as stop. Three assertions, because three different things can quietly break it.
const zones = [...DOCKBAR.matchAll(/class:\s*"(zm-side|zm-centre)"/g)].map((m) => m[1]);
check("the dock is side / centre / side, in that order",
  zones.join(",") === "zm-side,zm-centre,zm-side",
  `the dock's zones are [${zones}] — the orb must sit in a zm-centre BETWEEN two zm-side groups`);
// minmax(0, 1fr) and NOT a bare `1fr`: `1fr` means minmax(AUTO, 1fr), so the 3-button side grows its own track
// past its fair share and shoves the orb off centre — measured at 8px before this was pinned (2026-08-18).
check("the CSS centres the orb on the SCREEN, not between its neighbours",
  /grid-template-columns:\s*minmax\(\s*0\s*,\s*1fr\s*\)\s+auto\s+minmax\(\s*0\s*,\s*1fr\s*\)/.test(MOBILE_CSS),
  "the side tracks must have a 0 floor, or the wider side pushes the orb off centre");

// ONE power handler, shared by both faces of the centre slot. Two handlers is how the ⏻ and the orb start
// disagreeing about what stopped means — and since V2-092 the switch is the SERVER's state, so a mobile-only
// path that flipped a local signal would show "stopped" while the agent kept working.
const onClicks = [...DOCKBAR.matchAll(/onClick:\s*togglePower\b/g)].length;
check("the ⏻ and the orb share ONE power handler", onClicks === 2,
  `found ${onClicks} onClick: togglePower — both the stopped-state ⏻ and the running orb must call the same one`);
// Assert the CALL, not the substring: `includes("api.runStop")` also matches a renamed `api.runStopX`, so it
// would stay green through exactly the drift it exists to catch (found by breaking it on purpose).
for (const seam of [/api\.runStop\s*\(/, /api\.runStart\s*\(/, /store\.markPowerCommand\s*\(/]) {
  check(`the power handler goes through ${seam.source}`, seam.test(DOCKBAR),
    "that is the seam the desktop ⏻ uses; a parallel path desynchronises the phone from the server");
}

// The orb is wrapped in a <button> by the dock, so OrbMini must not be one itself. Nested buttons are invalid
// HTML and browsers disagree about which tap wins — one honours the outer, another the inner.
check("OrbMini is purely visual (no nested button inside the dock's orb button)",
  !/role:\s*["']button["']/.test(ORBMINI) && !/onClick/.test(ORBMINI),
  "OrbMini declares a role=button or an onClick; the dock already wraps it in a real <button>");

// The orb must be built ONCE, OUTSIDE the reactive tree. main.js hands its <canvas> to the visualiser a single
// time at boot, so anything that RE-CREATES the orb leaves the visualiser drawing into a detached node: the render
// loop keeps running (measured: 741 frames) and the dock shows an empty hole where zaelar's face should be, with no
// error anywhere. Written `() => cond ? h(...) : h(..., OrbMini())` this is the natural, wrong shape (2026-08-18).
const orbCalls = [...DOCKBAR.matchAll(/OrbMini\s*\(\)/g)].length;
check("the orb is constructed exactly once", orbCalls === 1,
  `OrbMini() appears ${orbCalls} times in DockBar.js — it must be built once and held`);
check("the orb is built outside the reactive tree", /const\s+ORB\s*=\s*OrbMini\(\)/.test(DOCKBAR),
  "OrbMini() must be assigned to a const in DockBar's body, not called inside a reactive child function");
check("no reactive branch re-creates the orb",
  !/=>[^\n]*OrbMini\s*\(\)/.test(DOCKBAR),
  "OrbMini() is called inside an arrow function; every state change would mint a new canvas and detach the live one");
// Both faces of the centre slot are therefore always mounted, and swapped by VISIBILITY.
check("the centre slot swaps its two faces by visibility, not by rebuilding",
  /zm-hide/.test(DOCKBAR) && /\.zm-hide\s*\{[^}]*display:\s*none/.test(MOBILE_CSS),
  "the hidden face must be display:none so it takes no space and catches no taps");

// ── the mobile glyphs ARE the desktop's, derived from Orb.js rather than eyeballed ──────────────────────────────
// The claim in DockBar.js's header is that an operator who knows one shell reads the other. That is only true
// while the shapes match, and a comment cannot enforce it: if the desktop redraws its mic, this goes red and
// somebody has to decide, instead of the two shells drifting apart unnoticed.
for (const name of ["MIC_ICON", "SPK_ON", "SPK_OFF", "CAP_ICON", "CHAT_ICON", "PWR_ICON"]) {
  const m = ORB_JS.match(new RegExp(`const ${name}\\s*=\\s*\`([^\`]*)\``));
  check(`Orb.js still defines ${name} (this test reads it as the source of truth)`, !!m);
  if (!m) continue;
  const shapes = [...m[1].matchAll(/<(?:path\s+d|rect\s+x)="[^"]+"/g)].map((x) => x[0]);
  const absent = shapes.filter((sh) => !DOCKBAR.includes(sh));
  check(`the mobile dock draws the same ${name} as the desktop`, absent.length === 0,
    `these shapes from Orb.js's ${name} are not in DockBar.js: ${absent.join(" | ")}`);
}

// ── every t() key the mobile shell uses must EXIST in both bundles ──────────────────────────────────────────────
// This is the ratchet on the bug that shipped once already: core/i18n.js's t() returns the KEY when a string is
// missing, and a key is TRUTHY — so `t("x") || "fallback"` is dead code that READS like a working fallback, and
// the phone renders a literal `mobile.empty_title` on screen. Checking the base bundle also covers GENERATED
// languages, since i18n init diffs against English.
const EN = JSON.parse(read("i18n", "bundles", "en.json"));
const ES = JSON.parse(read("i18n", "bundles", "es.json"));
const shellFiles = readdirSync(join(ENGINE, "frontend", "mobile", "app", "shell"))
  .filter((f) => f.endsWith(".js"))
  .map((f) => ["frontend", "mobile", "app", "shell", f]);
const usedKeys = new Set();
for (const parts of [...shellFiles, ["frontend", "mobile", "app", "main.js"]]) {
  for (const m of read(...parts).matchAll(/\bt\(\s*["']([a-zA-Z0-9_.]+)["']\s*\)/g)) usedKeys.add(m[1]);
}
check("the key scan actually found the shell's strings", usedKeys.size >= 15,
  `only ${usedKeys.size} t() keys found — the regex probably stopped matching`);
const missingEn = [...usedKeys].filter((k) => !(k in EN));
const missingEs = [...usedKeys].filter((k) => !(k in ES));
check("every string the mobile shell asks for exists in en.json", missingEn.length === 0,
  `missing from en.json (would render as the literal key): ${missingEn.join(", ")}`);
check("every string the mobile shell asks for exists in es.json", missingEs.length === 0,
  `missing from es.json: ${missingEs.join(", ")}`);
check("no fake `t(...) || fallback` dead code in the mobile shell",
  ![...shellFiles, ["frontend", "mobile", "app", "main.js"]]
    .some((parts) => /\bt\([^)]*\)\s*\|\|/.test(read(...parts))),
  "t() returns the key on a miss, which is truthy — an `|| fallback` after it can never run");

// ── one module, one ?v= ────────────────────────────────────────────────────────────────────────────────────────
// V2-087, the hard way: a different query string is a DIFFERENT MODULE INSTANCE in the browser. Two copies of
// services/session.js meant one of them held room=null, so every UI call that touched the room was a silent
// no-op. It cost a whole session to find, and the second copy was invisible in review.
const versions = new Map();
for (const parts of [...shellFiles, ["frontend", "mobile", "app", "main.js"]]) {
  for (const m of read(...parts).matchAll(/from\s+["']([^"'?]+)(\?v=\d+)?["']/g)) {
    const spec = m[1].replace(/^.*\/app\//, "app/").replace(/^\.\//, "shell/");
    if (!versions.has(spec)) versions.set(spec, new Set());
    versions.get(spec).add(m[2] || "(none)");
  }
}
const split = [...versions].filter(([, v]) => v.size > 1);
check("the mobile shell imports each module at ONE version", split.length === 0,
  split.map(([k, v]) => `${k} imported as ${[...v].join(" and ")}`).join("; "));


console.log(failures === 0 ? "\nALL OK" : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
