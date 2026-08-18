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

import { readFileSync } from "node:fs";
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

console.log(failures === 0 ? "\nALL OK" : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
