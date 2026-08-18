// ============================================================================
// sw.js — THE SERVICE WORKER, AND IT IS ALMOST EMPTY ON PURPOSE.  DO NOT TURN THIS INTO A CACHE.
//
// WHY. This is a live agent, and A CACHED MODULE IS A STALE AGENT. The engine already fights that battle on two
// fronts: server/pages.py serves the app shell with `Cache-Control: no-store` specifically so a reload can never
// execute yesterday's JavaScript, and every ES import in both shells carries a `?v=` query so an edited module is a
// different URL. A service worker that "helpfully" cached /static would silently undo both, and the symptom would
// not be an error — it would be a phone running a version of the agent that no longer exists, answering with a
// widget contract the backend has moved on from. That is the worst class of bug this file could create.
//
// SO WHAT DOES IT DO. Two things, and nothing else:
//   1. it makes the app INSTALLABLE on Android — Chrome requires a manifest AND a service worker with a fetch
//      handler before it will offer "Install app". iOS does not need it at all (see the apple-* meta tags in
//      mobile/index.html), but Android is half the phones.
//   2. it answers a NAVIGATION that has no network with offline.html, so a subway tunnel shows a card that explains
//      itself instead of the browser's dinosaur.
//
// THE RULE THAT KEEPS IT HONEST: only `request.mode === "navigate"` is intercepted. Everything else — /api/*,
// /events (SSE), /widgets/*, /static/* — is not touched at all: no cache read, no cache write, not even a
// pass-through fetch() of our own, because respondWith() on a streaming SSE response is a good way to break it.
// The precache holds exactly two things: the offline page and the icons.
// ============================================================================

// Bump on any change to THIS file or to offline.html. Nothing else is cached, so nothing else needs a version.
const CACHE = "zaelar-shell-v1";
const OFFLINE = "/static/mobile/offline.html";
const PRECACHE = [
  OFFLINE,
  "/static/mobile/icons/icon-192.png",
  "/static/mobile/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      // addAll() is all-or-nothing: one 404 among the icons would abort the whole install and leave the app
      // uninstallable for a missing PNG. Each entry is added on its own and a failure is survivable.
      .then((c) => Promise.all(PRECACHE.map((u) => c.add(u).catch(() => {}))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // NOT A NAVIGATION → we are not involved. Returning without calling respondWith() lets the browser do exactly
  // what it would have done with no service worker installed, which is the entire intent for every API call, every
  // widget module and the SSE stream.
  if (req.mode !== "navigate" || req.method !== "GET") return;

  // NETWORK FIRST, always. The shell must come from the server whenever the server is reachable — the cache is a
  // last resort for a dead network, never a speed optimisation. Note what is NOT here: no `caches.put` of the
  // response. The shell is never stored, so it can never be served stale.
  event.respondWith(
    fetch(req).catch(() =>
      caches.match(OFFLINE).then((r) => r || new Response(
        "<h1>zaelar</h1><p>No connection.</p>",
        { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } },
      )),
    ),
  );
});
