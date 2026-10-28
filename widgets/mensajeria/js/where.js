// js/where.js — WHERE HE IS survives a repaint (V2-819): scroll, focus and caret captured before a paint and restored after it.
// Moved verbatim out of widget.js (refactor2710-12).

// ── WHERE HE IS survives a repaint (V2-819) ─────────────────────────────────────────────────────────────────
// The host repaints this card on EVERY store write (desktop.js `refreshData`), and this card writes the store
// itself while he types: the composer's autosave (`draft`, half a second after the last key). Each repaint rebuilt
// the card from nothing, so the thread's list came back scrolled to its top and the box he was typing in lost its
// focus — measured by the operator in a WhatsApp chat: he scrolled to the latest message, started writing, and
// the conversation jumped up under his hands. The class is «a repaint moves him», so it is fixed at the one door
// every repaint goes through, not in the composer:
//   · a scroller says what it is (`data-scroll-key`) and how it OPENS (`data-open="bottom"`: a chat opens on its
//     latest message); a repaint of the SAME scroller keeps him where he was — on the bottom if he was there
//     (new messages then stay in view), else on the same row (`data-row-key`) at the same offset;
//   · a text field that should keep its focus says so (`data-keep`): the focused one gets focus and caret back.
//     Its VALUE is each field's own buffer's job (`_draftLocal`, `_chatQuery`, `S.newMail`), never restored here —
//     except where a field has no buffer of its own (`data-keep-value`).
export const _PIN_PX = 24;

export function _captureWhere(root){
  const w = {focus: null, scroll: {}};
  try{
    const a = document.activeElement;
    if(a && root.contains(a) && a.dataset && a.dataset.keep){
      w.focus = {key: a.dataset.keep, s: a.selectionStart, e: a.selectionEnd, top: a.scrollTop,
                  value: a.dataset.keepValue != null ? a.value : null};
    }
    root.querySelectorAll("[data-scroll-key]").forEach(sc => {
      const atBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight <= _PIN_PX;
      let anchor = null;
      if(!atBottom){
        const top = sc.getBoundingClientRect().top;
        for(const r of sc.querySelectorAll("[data-row-key]")){
          const b = r.getBoundingClientRect();
          if(b.bottom > top){ anchor = {key: r.dataset.rowKey, off: b.top - top}; break; }
        }
      }
      w.scroll[sc.dataset.scrollKey] = {top: sc.scrollTop, atBottom, anchor};
    });
  }catch(_){ /* a capture that fails leaves the repaint as it always was */ }
  return w;
}

// A scroller that opened (or stayed) on its bottom follows what grows under it — a picture that finishes loading,
// a voice note whose length arrives — until HE scrolls away from the bottom.
export function _followBottom(sc){
  sc.__hbPinned = true;
  sc.scrollTop = sc.scrollHeight;
  if(sc.__hbFollow) return;
  sc.__hbFollow = true;
  sc.addEventListener("scroll", () => {
    if(sc.__hbPinning) return;
    sc.__hbPinned = sc.scrollHeight - sc.scrollTop - sc.clientHeight <= _PIN_PX;
  }, {passive: true});
  const repin = () => { if(sc.__hbPinned){ sc.__hbPinning = true; sc.scrollTop = sc.scrollHeight;
    requestAnimationFrame(() => { sc.__hbPinning = false; }); } };
  sc.addEventListener("load", repin, true);
  sc.addEventListener("loadedmetadata", repin, true);
  requestAnimationFrame(repin);            // a card painted before its first layout has no height to scroll yet
}

export function _restoreWhere(root, w){
  try{
    root.querySelectorAll("[data-scroll-key]").forEach(sc => {
      const was = w.scroll[sc.dataset.scrollKey];
      if(was ? was.atBottom : sc.dataset.open === "bottom"){ _followBottom(sc); return; }
      if(!was) return;
      if(was.anchor){
        const r = Array.from(sc.querySelectorAll("[data-row-key]")).find(x => x.dataset.rowKey === was.anchor.key);
        if(r){ sc.scrollTop += (r.getBoundingClientRect().top - sc.getBoundingClientRect().top) - was.anchor.off; return; }
      }
      sc.scrollTop = was.top;
    });
    if(w.focus){
      const f = Array.from(root.querySelectorAll("[data-keep]")).find(x => x.dataset.keep === w.focus.key);
      if(f){
        if(w.focus.value != null && f.value !== w.focus.value) f.value = w.focus.value;
        f.focus({preventScroll: true});
        try{ if(w.focus.s != null) f.setSelectionRange(Math.min(w.focus.s, f.value.length), Math.min(w.focus.e, f.value.length)); }catch(_){}
        f.scrollTop = w.focus.top || 0;
      }
    }
  }catch(_){ /* never let bookkeeping break the card */ }
}
