// ============================================================================
// draggable.js — draggable + position-PERSISTED chrome (camera unit, voice orb,
// chat wall). Ported from the original assistant inline script.
//
// The box tracks the pointer 1:1 (no easing/inertia). While dragging we add the
// `hb-dragging` class, which forces `transition:none !important` — this DEFEATS any
// CSS transition on the element (e.g. `.me { transition:top .2s }`, added for the
// update-banner shift), which would otherwise make the box lag behind like it's on
// an elastic. Position is committed to left/top(/bottom) live and persisted on release.
//
//   mode "tl" = anchor by top/left ; mode "bl" = anchor by bottom/left (the orb,
//   so its activity rail grows UP). makeDraggable returns moved() so a click
//   handler can tell a drag from a tap (the orb: tap = cycle voice, drag = move).
// ============================================================================

export function makeDraggable(el, handle, key, mode) {
  const apply = p => {
    if (!p) return; el.style.transform = "none"; el.style.right = "auto";
    if (p.left != null) el.style.left = p.left + "px";
    if (mode === "bl") { el.style.top = "auto"; if (p.bottom != null) el.style.bottom = p.bottom + "px"; }
    else { el.style.bottom = "auto"; if (p.top != null) el.style.top = p.top + "px"; }
  };
  try { apply(JSON.parse(localStorage.getItem(key) || "null")); } catch (_) {}
  let sx, sy, ox, oy, drag = false, moved = false, r0 = null, pid = null;
  handle.style.touchAction = "none";
  // Only PIN + capture once the pointer actually MOVES (>4px). A pure tap never captures, so a click on the handle
  // (e.g. tap the orb to cycle voice) still fires. moved() lets those handlers ignore drags.
  handle.addEventListener("pointerdown", e => {
    drag = true; moved = false; r0 = el.getBoundingClientRect(); pid = e.pointerId;
    sx = e.clientX; sy = e.clientY; ox = r0.left; oy = r0.top;
  });
  handle.addEventListener("pointermove", e => {
    if (!drag) return;
    const ddx = e.clientX - sx, ddy = e.clientY - sy;
    if (!moved) {
      if (Math.abs(ddx) + Math.abs(ddy) <= 4) return;          // still a tap → don't hijack the click
      moved = true;                                            // first real movement → become a drag
      el.classList.add("hb-dragging");                         // transition:none!important → no easing/inertia while dragging
      el.style.transform = "none"; el.style.right = "auto"; el.style.left = ox + "px";
      if (mode === "bl") el.style.top = "auto"; else el.style.bottom = "auto";
      try { handle.setPointerCapture(pid); } catch (_) {}
    }
    const x = Math.max(0, Math.min(ox + ddx, innerWidth - el.offsetWidth));
    const y = Math.max(0, Math.min(oy + ddy, innerHeight - el.offsetHeight));
    el.style.left = x + "px";
    if (mode === "bl") el.style.bottom = Math.max(0, innerHeight - y - el.offsetHeight) + "px";
    else el.style.top = y + "px";
  });
  const end = () => {
    if (!drag) return; drag = false; el.classList.remove("hb-dragging");
    if (!moved) return;                                         // pure tap → nothing moved, nothing to persist
    const r = el.getBoundingClientRect();
    const p = mode === "bl" ? { left: Math.round(r.left), bottom: Math.round(innerHeight - r.bottom) }
                            : { left: Math.round(r.left), top: Math.round(r.top) };
    try { localStorage.setItem(key, JSON.stringify(p)); } catch (_) {}
  };
  handle.addEventListener("pointerup", end); handle.addEventListener("pointercancel", end);
  return () => moved;
}
