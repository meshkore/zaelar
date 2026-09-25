// ============================================================================
// test_a_first_run_does_not_wear_the_previous_install.mjs — V2-735, node 4.195.
//
// THE OPERATOR'S REPORT (2026-09-20, on a freshly reset install): «cuando el
// sistema arranca, no quiero que por defecto el orbe esté metido en la barra
// inferior. Quiero que el orbe esté desplegado y que se vea el orbe grande con
// el pulso y todo… totalmente arrancado, porque la voz tiene que empezar a
// sonar enseguida.»
//
// And by default it IS: `store.orbDock` defaults to "eye", `store.powerOff` to
// false. What he was looking at was the PREVIOUS install's `hb_orb_dock=bar`
// and `hb_power_off=1`, still in the browser — a factory reset starts the agent
// over and cannot reach localStorage.
//
// Run: node tests/browser/unit/arranque/test_a_first_run_does_not_wear_the_previous_install.mjs
// ============================================================================
import assert from "node:assert/strict";

function fakeStorage(seed = {}) {
  const m = new Map(Object.entries(seed));
  return {
    get length() { return m.size; },
    key: (i) => [...m.keys()][i] ?? null,
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    _keys: () => [...m.keys()],
  };
}

const { takeoverOnFirstRun, clearInheritedViewState, isOurs } =
  await import("../../../../frontend/app/core/first-run.js?v=1");

// ── 1. the operator's own case: the shape of the install before this one ────────────────────────────────
{
  const local = fakeStorage({
    hb_orb_dock: "bar",            // the orb docked in the bottom bar
    hb_power_off: "1",             // and the voice off, so nothing ever speaks
    hb_desktop: '{"cards":[1,2]}', // somebody else's cards
    hb_lang: "de",
    zaelar_mic: "some-device",
    unrelated_key: "keep me",      // not ours: another app on the same origin
  });
  const session = fakeStorage();
  let reloaded = 0;
  const took = takeoverOnFirstRun({ local, session, reload: () => reloaded++ });

  assert.equal(took, true, "THE BUG: a first run came up wearing the previous install's state");
  assert.equal(reloaded, 1, "the signals are seeded at import — only a reload can undo them");
  assert.deepEqual(local._keys(), ["unrelated_key"],
    `our namespace must be gone and nothing else touched — ${local._keys()}`);
}

// ── 2. a genuinely new browser: nothing to clear, nothing to reload ─────────────────────────────────────
{
  const local = fakeStorage({ unrelated_key: "x" });
  const session = fakeStorage();
  let reloaded = 0;
  assert.equal(takeoverOnFirstRun({ local, session, reload: () => reloaded++ }), false);
  assert.equal(reloaded, 0, "a clean install must not blink through an extra page load");
  assert.deepEqual(local._keys(), ["unrelated_key"]);
}

// ── 3. never twice in one tab, whatever gets rewritten in between ───────────────────────────────────────
{
  const local = fakeStorage({ hb_orb_dock: "bar" });
  const session = fakeStorage();
  let reloaded = 0;
  const reload = () => { reloaded++; local.setItem("hb_lang", "es"); };   // boot rewrites a key of ours
  assert.equal(takeoverOnFirstRun({ local, session, reload }), true);
  assert.equal(takeoverOnFirstRun({ local, session, reload }), false,
    "a second attempt in the same tab is how this becomes a reload loop");
  assert.equal(reloaded, 1);
}

// ── 4. no sessionStorage → no guard → do not risk a loop ────────────────────────────────────────────────
{
  const local = fakeStorage({ hb_orb_dock: "bar" });
  const blind = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  let reloaded = 0;
  assert.equal(takeoverOnFirstRun({ local, session: blind, reload: () => reloaded++ }), false);
  assert.equal(reloaded, 0, "without a guard a reload could repeat forever — do nothing instead");
}

// ── 5. what counts as ours ──────────────────────────────────────────────────────────────────────────────
for (const k of ["hb_theme", "hb_orb_dock", "zaelar_mic"]) assert.ok(isOurs(k), k);
for (const k of ["theme", "lang", "", null, "myapp_hb_theme"]) assert.ok(!isOurs(k), String(k));

// ── 6. a storage that throws mid-sweep leaves the boot alone ────────────────────────────────────────────
{
  const angry = { get length() { throw new Error("private window"); } };
  assert.deepEqual(clearInheritedViewState(angry), [], "a blocked store has nothing to inherit either");
}

// ── 7. ANY reset, not only a first run (operator, 2026-09-25) ───────────────────────────────────────────
// «en cuanto hago un reset, todas esas variables de estado pasan al estado inicial». A reset that keeps the
// language never reaches takeoverOnFirstRun, so the mic and speaker came back muted. The reset's EPOCH does.
{
  const { takeoverOnReset } = await import("../../../../frontend/app/core/first-run.js?v=1");
  const local = fakeStorage({ hb_wipe: "100", hb_mic_muted: "1", hb_bot_muted: "1", hb_orb_dock: "bar",
                              unrelated_key: "keep me" });
  const session = fakeStorage();
  let reloaded = 0;
  const took = await takeoverOnReset({ fetchEpoch: async () => 200, local, session, reload: () => reloaded++ });
  assert.equal(took, true, "THE BUG: a reset left the previous mute switches in the browser");
  assert.equal(reloaded, 1);
  assert.deepEqual(local._keys().sort(), ["hb_wipe", "unrelated_key"], local._keys());
  assert.equal(local.getItem("hb_wipe"), "200", "the epoch obeyed is remembered, so it happens once");

  // the same epoch again (next page load): nothing
  local.setItem("hb_mic_muted", "1");            // he mutes on purpose AFTER the reset
  assert.equal(await takeoverOnReset({ fetchEpoch: async () => 200, local, session: fakeStorage(),
                                       reload: () => reloaded++ }), false);
  assert.equal(local.getItem("hb_mic_muted"), "1", "a choice made after the reset is his, and it stays");
  assert.equal(reloaded, 1);
}
{
  const { takeoverOnReset } = await import("../../../../frontend/app/core/first-run.js?v=1");
  // a brand-new browser: records the epoch, wipes nothing, never blinks
  const local = fakeStorage({ unrelated_key: "x" });
  let reloaded = 0;
  assert.equal(await takeoverOnReset({ fetchEpoch: async () => 300, local, session: fakeStorage(),
                                       reload: () => reloaded++ }), false);
  assert.equal(reloaded, 0);
  assert.equal(local.getItem("hb_wipe"), "300");
  // no epoch served, or the engine unreachable: nothing happens
  const l2 = fakeStorage({ hb_mic_muted: "1" });
  assert.equal(await takeoverOnReset({ fetchEpoch: async () => 0, local: l2, session: fakeStorage(), reload() {} }), false);
  assert.equal(await takeoverOnReset({ fetchEpoch: async () => { throw new Error("down"); }, local: l2,
                                       session: fakeStorage(), reload() {} }), false);
  assert.equal(l2.getItem("hb_mic_muted"), "1");
}

console.log("ok: a first run does not wear the previous install");
