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

// The box `el.style.left/top/bottom` actually resolve against. These elements are `position:fixed`, and a
// fixed element's containing block is NOT always the viewport: a transformed ancestor claims it — and #desk
// carries `transform: translate3d(0,0,0)` for exactly that reason (V2-062: when the chat takes a column,
// the whole desktop shifts as one unit, dragged orb and camera included). So for the orb/camera the numbers
// we write are DESK pixels, while pointer events arrive in VIEWPORT pixels. Mixing the two is the measured
// V2-608 bug, in both directions: writing a viewport number into a desk `left` teleports the element right
// by the column width on the FIRST move of every drag (and off the screen by the second), and clamping a
// desk number against `innerWidth` lets it leave the desk. Everything below converts through this box; an
// element mounted outside any transformed ancestor (feedback widget, floating chat) gets the viewport box
// and behaves exactly as before.
function containerBox(el) {
  for (let n = el.parentElement; n; n = n.parentElement) {
    const s = getComputedStyle(n);
    if (s.transform !== "none" || s.perspective !== "none" || s.filter !== "none"
        || (s.willChange || "").includes("transform")) return n.getBoundingClientRect();
  }
  return { left: 0, top: 0, right: innerWidth, bottom: innerHeight, width: innerWidth, height: innerHeight };
}

export function makeDraggable(el, handle, key, mode) {
  const apply = p => {
    if (!p) return; el.style.transform = "none"; el.style.right = "auto";
    if (p.left != null) el.style.left = p.left + "px";
    if (mode === "bl") { el.style.top = "auto"; if (p.bottom != null) el.style.bottom = p.bottom + "px"; }
    else { el.style.bottom = "auto"; if (p.top != null) el.style.top = p.top + "px"; }
  };
  try { apply(JSON.parse(localStorage.getItem(key) || "null")); } catch (_) {}
  let sx, sy, ox, oy, drag = false, moved = false, r0 = null, pid = null, bx = null;
  handle.style.touchAction = "none";
  // The move/up listeners live on the WINDOW, added per drag — the V2-608 F6 lesson from the widget grips:
  // handle-bound listeners stop firing the instant the pointer leaves the handle, so any drag faster than
  // the handle is wide simply dies (measured on the cards: 0px applied for a 120px drag). No pointer
  // capture: a pure tap (>4px never exceeded) must keep firing the handle's own click handlers, and
  // capture would retarget them. moved() lets those handlers ignore real drags.
  const onMove = e => {
    if (!drag || e.pointerId !== pid) return;
    const ddx = e.clientX - sx, ddy = e.clientY - sy;
    if (!moved) {
      if (Math.abs(ddx) + Math.abs(ddy) <= 4) return;          // still a tap → don't hijack the click
      moved = true;                                            // first real movement → become a drag
      el.classList.add("hb-dragging");                         // transition:none!important → no easing/inertia while dragging
      el.style.transform = "none"; el.style.right = "auto"; el.style.left = (ox - bx.left) + "px";
      if (mode === "bl") el.style.top = "auto"; else el.style.bottom = "auto";
    }
    // Clamp in VIEWPORT space against the CONTAINER's box (the element may not leave its container — for the
    // orb that is «the orb never leaves the visible desk»), then write container-relative numbers.
    const x = Math.max(bx.left, Math.min(ox + ddx, bx.right - el.offsetWidth));
    const y = Math.max(bx.top, Math.min(oy + ddy, bx.bottom - el.offsetHeight));
    el.style.left = (x - bx.left) + "px";
    if (mode === "bl") el.style.bottom = Math.max(0, bx.bottom - y - el.offsetHeight) + "px";
    else el.style.top = (y - bx.top) + "px";
  };
  const end = e => {
    if (!drag || (e && e.pointerId !== pid)) return;
    drag = false; el.classList.remove("hb-dragging");
    removeEventListener("pointermove", onMove);
    removeEventListener("pointerup", end); removeEventListener("pointercancel", end);
    if (!moved) return;                                         // pure tap → nothing moved, nothing to persist
    // Persist CONTAINER-relative numbers — the same space apply() writes them back into on the next load.
    // The old shape stored viewport pixels here, so a position saved with a chat column docked came back
    // shifted by the column width on every later visit.
    const r = el.getBoundingClientRect();
    const p = mode === "bl" ? { left: Math.round(r.left - bx.left), bottom: Math.round(bx.bottom - r.bottom) }
                            : { left: Math.round(r.left - bx.left), top: Math.round(r.top - bx.top) };
    try { localStorage.setItem(key, JSON.stringify(p)); } catch (_) {}
  };
  handle.addEventListener("pointerdown", e => {
    drag = true; moved = false; r0 = el.getBoundingClientRect(); pid = e.pointerId;
    bx = containerBox(el);                                     // the coordinate space this drag writes into
    sx = e.clientX; sy = e.clientY; ox = r0.left; oy = r0.top;
    addEventListener("pointermove", onMove);
    addEventListener("pointerup", end); addEventListener("pointercancel", end);
  });
  return () => moved;
}

// The UNDO of makeDraggable: forget the persisted position and drop every inline style a drag wrote
// (left/right/top/bottom/transform), so the element's own CSS rule places it again — its birthplace.
// Both halves matter: clearing only the styles leaves the old position in storage, and the next page
// load would put the element right back where the reset just removed it from (apply() above reads it).
export function resetDraggable(el, key) {
  try { localStorage.removeItem(key); } catch (_) {}
  if (!el) return;
  for (const prop of ["left", "right", "top", "bottom", "transform"]) el.style[prop] = "";
}
