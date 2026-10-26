// mobile/app/shell/keyboard.js — the on-screen keyboard, for every card and every sheet at once (V2-813, V2-815).
//
// Measured on an iPhone 14 and a Pixel 7 (2026-10-26): with a text field focused inside a card, the keyboard took
// the bottom ~330px and the dock stayed on top of what was left, so the agenda's «Nueva cita» lost its Save and
// Cancel, and every editor in every card had the same shape. Both browsers now resize only the VISUAL viewport
// (iOS always, Chrome on Android since 108), so nothing in the layout moves on its own: the deck kept its full
// height and its bottom half sat under the keyboard.
//
// The same evening, typing in the CHAT on the iPhone: the sheet sat on the dock, the dock sat on the keyboard's
// accessory row, and the keys came under that — composer, a bar of seven controls nobody can press while typing,
// the «^ v Done» row, then the keyboard. Half the screen of chrome around one text field.
//
// So one rule, here and not in sixteen widgets: while a text field INSIDE A CARD or INSIDE A SHEET has focus and
// the visual viewport is clearly shorter than the screen, the root wears `zm-kbd` with `data-kbd` naming which
// (`deck` | `sheet`), the surface that holds the field is laid over the visible part only (`--zm-vvh`/`--zm-vvt`),
// the dock and the pips step aside, and the focused field is brought into view. The iOS accessory row is the
// system's and cannot be removed from a web page; what can be removed is everything of ours around it.

const MIN_KEYBOARD_PX = 120;     // a shorter shrink is browser chrome sliding, not a keyboard

function editable(el) {
  if (!el || !el.closest) return false;
  if (el.isContentEditable) return true;
  if (el.tagName === "TEXTAREA") return true;
  if (el.tagName !== "INPUT") return false;
  return !/^(checkbox|radio|range|button|submit|reset|file|color)$/i.test(el.type || "");
}

/** Which surface the focused field belongs to: "deck", "sheet", or "" (none of ours). */
export function surfaceOf(el) {
  if (!editable(el)) return "";
  if (el.closest(".zm-deck")) return "deck";
  if (el.closest(".zm-sheet")) return "sheet";
  return "";
}

export function initKeyboard() {
  const vv = window.visualViewport;
  if (!vv) return;
  const root = document.documentElement;
  let full = Math.max(window.innerHeight, vv.height);

  const apply = () => {
    if (!root.classList.contains("zm-kbd")) full = Math.max(full, window.innerHeight, vv.height);
    const where = surfaceOf(document.activeElement);
    const open = !!where && vv.height < full - MIN_KEYBOARD_PX;
    root.classList.toggle("zm-kbd", open);
    if (open) {
      root.dataset.kbd = where;
      root.style.setProperty("--zm-vvh", vv.height + "px");
      root.style.setProperty("--zm-vvt", vv.offsetTop + "px");
      const el = document.activeElement;
      requestAnimationFrame(() => { try { el.scrollIntoView({ block: "nearest" }); } catch (_) { /* detached */ } });
    } else {
      delete root.dataset.kbd;
    }
  };
  vv.addEventListener("resize", apply);
  vv.addEventListener("scroll", apply);
  window.addEventListener("resize", apply);
  document.addEventListener("focusin", () => setTimeout(apply, 50));
  document.addEventListener("focusout", () => setTimeout(apply, 50));
  window.addEventListener("orientationchange", () => { full = 0; setTimeout(apply, 300); });
}
