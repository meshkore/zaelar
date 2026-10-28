// RECONCILE on reconnect (V2-825 F5, refactor2710-04 T-04) — one rule for every host (the desktop, the phone's Deck).
//
// The screen adopts the engine's list of cards, never the reverse. A card in the DOM that the host's own registry
// does not own is an orphan the engine cannot name — he saw two `documento` while the canvas report listed one — so
// it goes; a card the engine does not list closes; a card it lists that is not on screen opens beside, without focus.
// Returns the drift (null when the engine did not answer) and reports it, so the timeline says how far off it was.

export async function reconcileScreen(host, { registry, selector, device }) {
  let lay;
  try {
    lay = await fetch(`/api/canvas/layout?dev=${encodeURIComponent(device || "")}`, { cache: "no-store" })
      .then((r) => r.json());
  } catch (_) { return null; }
  const want = new Set(((lay && lay.items) || []).map((it) => String(it.id || "")).filter(Boolean));
  const orphans = [...host.stage.querySelectorAll(selector)]
    .filter((c) => (registry.get(c.dataset.wid) || {}).card !== c);
  orphans.forEach((c) => c.remove());
  const extra = [...registry.keys()].filter((id) => !want.has(id));
  extra.forEach((id) => host.close(id, { by: "restore" }));
  const missing = [...want].filter((id) => !registry.has(id));
  for (const id of missing) { try { await host.show(id, { background: true, by: "restore" }); } catch (_) { /* next */ } }
  const drift = { orphans: orphans.map((c) => c.dataset.wid), extra, missing };
  if (orphans.length || extra.length || missing.length) {
    fetch("/api/canvas/reconcile", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(drift) }).catch(() => {});
  }
  return drift;
}
