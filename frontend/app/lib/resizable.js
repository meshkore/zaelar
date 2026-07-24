// ============================================================================
// resizable.js — adds 8 edge/corner resize handles (n·s·e·w·ne·nw·se·sw) to a
// fixed-positioned, TOP-LEFT-anchored box. N/W edges move the origin while S/E
// grow the size, so a box can be stretched from ANY side (native CSS `resize`
// only gives the bottom-right corner). Clamps to the viewport and a min size.
//
// It does NOT persist anything itself: it calls onChange(rect, dir) at the end of
// each drag so the caller decides what to store (a floating window persists pos+
// size; a docked column persists only its width). While dragging it adds
// `hb-dragging` (transition:none!important) so the box tracks the pointer 1:1.
// ============================================================================
const EDGES = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];

export function makeResizable(el, { minW = 260, minH = 200, onChange } = {}) {
  const handles = {};
  for (const dir of EDGES) {
    const g = document.createElement("div");
    g.className = "hb-rz hb-rz-" + dir;
    g.style.touchAction = "none";
    el.appendChild(g);
    handles[dir] = g;

    let sx, sy, r0, pid, live = false;
    g.addEventListener("pointerdown", e => {
      e.preventDefault(); e.stopPropagation();      // never let the header-drag see this
      live = true; r0 = el.getBoundingClientRect(); sx = e.clientX; sy = e.clientY; pid = e.pointerId;
      el.classList.add("hb-dragging");
      try { g.setPointerCapture(pid); } catch (_) {}
    });
    g.addEventListener("pointermove", e => {
      if (!live) return;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      let left = r0.left, top = r0.top, w = r0.width, h = r0.height;
      if (dir.includes("e")) w = r0.width + dx;
      if (dir.includes("s")) h = r0.height + dy;
      if (dir.includes("w")) { w = r0.width - dx; left = r0.left + dx; }
      if (dir.includes("n")) { h = r0.height - dy; top = r0.top + dy; }
      // enforce min while keeping the OPPOSITE edge fixed when pulling from n/w
      if (w < minW) { if (dir.includes("w")) left = r0.right - minW; w = minW; }
      if (h < minH) { if (dir.includes("n")) top = r0.bottom - minH; h = minH; }
      // clamp inside the viewport
      left = Math.max(0, left); top = Math.max(0, top);
      w = Math.min(w, innerWidth - left); h = Math.min(h, innerHeight - top);
      el.style.right = "auto"; el.style.bottom = "auto";
      el.style.left = left + "px"; el.style.top = top + "px";
      el.style.width = w + "px"; el.style.height = h + "px";
    });
    const end = () => {
      if (!live) return; live = false; el.classList.remove("hb-dragging");
      try { g.releasePointerCapture(pid); } catch (_) {}
      try { onChange && onChange(el.getBoundingClientRect(), dir); } catch (_) {}
    };
    g.addEventListener("pointerup", end);
    g.addEventListener("pointercancel", end);
  }
  return handles;
}
