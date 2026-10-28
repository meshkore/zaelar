// The messaging card's stylesheet, second half: reading a mail, the chat list and thread, the compose bar, media,
// the activity bar, narrow screens and the shared buttons. Concatenated after `CSS` in style.js, verbatim.
export const READING_CSS = `  /* V2-680 retired .mdsubj/.mdmeta/.mdfrom/.mdwhen/.mdbody: the detail screen draws the same LETTER the
     thread does now (.mltr below), so keeping a second set of rules for the same thing is how two
     renderings of one screen start to drift. */

  /* V2-680 — READING A MAIL, shaped like a mail client and not like a chat. The operator, looking at an
     email rendered as a chat bubble: «quita esa barrita roja de la izquierda… quiero ver el asunto, quién
     lo envía, quién está en copia y el texto en el medio… un cuadro bien delimitado… no quiero botones de
     mostrar más, lo quiero todo entero».
     So: a bordered PANE with its own scrollbar (he asked for it explicitly — «un scroll a la derecha») and
     a visible boundary, so he can see how much of it the content occupies; inside it, one bordered letter
     per message with a real envelope header; the body complete, never clamped. The urgency bar is GONE
     here on purpose — urgency belongs to the inbox list, which is where triage happens; inside an open
     letter it was a red stripe on the one thing he had already chosen to read. */
  .hb-msg .mpane{border:1px solid var(--hb-line,#e3e8f0);border-radius:12px;background:var(--hb-bg-soft,#fbfdff);
    padding:12px;display:flex;flex-direction:column;gap:12px}
  /* Deliberately NO overflow:hidden on a letter, and the rendered test caught why: it was here for the
     rounded corners, and a letter taller than the pane got its body CUT — everything still "rendered",
     nothing readable, which is the exact failure this screen exists to end. The only thing clipping can
     do to a tall letter is hide the end of it. The letter keeps its full height (a flex item's default
     min-height:auto already refuses to shrink below its content) and the PANE scrolls past it. */
  .hb-msg .mltr{border:1px solid var(--hb-line,#e3e8f0);border-radius:10px;background:var(--hb-bg,#fff);
    padding:14px 16px}
  .hb-msg .mltr.out{background:var(--hb-hover,#eef3f9)}
  .hb-msg .mltrsubj{font-size:16px;font-weight:700;color:var(--hb-ink,#0d1622);word-break:break-word;
    margin:0 0 9px;line-height:1.3}
  /* The envelope block: a label column and a value column, the shape every mail client uses. */
  .hb-msg .menv{display:grid;grid-template-columns:auto 1fr;gap:3px 10px;align-items:baseline;
    padding-bottom:11px;margin-bottom:12px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-msg .menvk{font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;
    color:var(--hb-muted-2,#9aa7b8);white-space:nowrap}
  .hb-msg .menvv{font-size:13px;color:var(--hb-ink,#0d1622);word-break:break-word;min-width:0}
  .hb-msg .menvv .addr{color:var(--hb-muted,#6b7b92)}
  .hb-msg .mltrbody{font-size:14.5px;line-height:1.65;color:var(--hb-ink,#0d1622);
    white-space:pre-wrap;word-break:break-word}
  .hb-msg .mltrbody a.lnk{color:var(--hb-accent,#3D6FE0);text-decoration:underline}
  .hb-msg .mltr .tacts{opacity:.55;margin-top:12px}
  .hb-msg .mltr:hover .tacts{opacity:1}

  /* Grouped CHAT list + open thread. */
  .hb-msg .chatrow{cursor:pointer;margin:0 -8px;padding-left:8px;padding-right:8px;border-radius:9px}
  .hb-msg .chatrow:hover{background:var(--hb-hover,#eef3f9)}
  .hb-msg .tcount{background:var(--hb-neutral,#3a4a5c);color:#fff;font-size:10.5px;font-weight:700;border-radius:999px;
    min-width:17px;height:17px;padding:0 5px;display:inline-flex;align-items:center;justify-content:center}
  .hb-msg .tprev{font-size:13.5px;color:var(--hb-muted,#5f6b7c);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-msg .thd{display:flex;align-items:center;gap:9px;margin:0 0 10px;padding-bottom:9px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  /* V2-616 F3 — a real button, in the corner, never a bare underlined link: the operator's own words
     ("estas flechas así largas que se subraya... no me gusta nada"). margin-left:auto on the LAST child
     pushes it to the far right while the name (appended first) stays left, same pattern the connector list
     used for its own back link — now sharing the SAME visual language instead of two different ones. */
  .hb-msg .thd .back{margin-left:auto;flex:0 0 auto;border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);
    color:var(--hb-muted,#5b6b82);cursor:pointer;font-size:12.5px;font-weight:600;padding:6px 12px;border-radius:8px}
  .hb-msg .thd .back:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0);background:var(--hb-hover,#eef3f9)}
  .hb-msg .thdname{font-size:15px}
  /* COMPOSE BAR (V2-611): dictate or type, see it, then send — by button or by a later voice order.
     .bt/.bt-primary etc. are already declared below (the wizard's own buttons) — reused as-is. */
  .hb-msg .compose{margin-top:12px;padding-top:10px;border-top:1px solid var(--hb-line,#eef1f6)}
  /* V2-680 — the box is at least FIVE rows (the operator's own minimum: a reply is written, not tweeted),
     and the send button sits to its RIGHT rather than on a row underneath, so growing the box never pushes
     the button off the bottom of the card. */
  .hb-msg .composemain{display:flex;gap:9px;align-items:stretch}
  /* V2-819 — a send that did not leave says so where he wrote it; his text stays in the box. */
  .hb-msg .composeerr{color:var(--hb-risk,#e5484d);font-size:12.5px;margin:0 0 7px}
  .hb-msg .cxava{width:22px;height:22px;border-radius:50%;object-fit:cover;flex:0 0 auto;margin-right:6px;vertical-align:middle}
  .hb-msg .composebox{flex:1 1 auto;min-width:0;box-sizing:border-box;resize:vertical;min-height:112px;
    font:inherit;font-size:14px;line-height:1.45;color:var(--hb-ink,#0d1622);background:var(--hb-hover,#eef3f9);
    border:1px solid var(--hb-line,#eef1f6);border-radius:10px;padding:9px 11px}
  .hb-msg .composebox:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .thread.plat-whatsapp .composebox:focus{border-color:#16B8A6}
  .hb-msg .thread.plat-telegram .composebox:focus{border-color:#2AABEE}
  .hb-msg .thread.plat-email .composebox:focus{border-color:#D8452D}
  .hb-msg .composeside{display:flex;flex-direction:column;gap:6px;flex:0 0 auto;justify-content:flex-end}
  .hb-msg .composeside .bt{white-space:nowrap}
  .hb-msg .pending{display:flex;flex-direction:column;gap:6px;margin:6px 0}
  .hb-msg .prow{display:flex;flex-direction:column;gap:4px;align-items:flex-start;padding:8px;border-radius:8px;background:var(--surface-2, rgba(127,127,127,.08))}
  .hb-msg .prow .pbody{white-space:pre-wrap;max-height:7.5em;overflow:auto;opacity:.85}
  /* Attachments picked in the card: a row of chips (a thumbnail for a picture), each removable. */
  .hb-msg .attrow{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}
  .hb-msg .attchip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--hb-line,#e3e8f0);
    border-radius:8px;padding:3px 6px;font-size:12px;max-width:220px;background:var(--hb-bg,#fff)}
  .hb-msg .attchip img{width:32px;height:32px;object-fit:cover;border-radius:4px}
  .hb-msg .attchip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-msg .attchip button{border:0;background:transparent;cursor:pointer;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .attbtn{display:inline-flex;align-items:center;padding:5px 9px;color:var(--hb-muted,#6b7b92)}
  .hb-msg .composemain > .attbtn{flex:0 0 auto;align-self:flex-end}
  /* A picture waiting to be sent is a thumbnail above the box, its ✕ in the corner. */
  .hb-msg .attchip.attthumb{position:relative;padding:0;border-radius:10px;overflow:hidden;width:72px;height:72px;max-width:none}
  .hb-msg .attchip.attthumb img{width:72px;height:72px;border-radius:0;display:block}
  .hb-msg .attchip.attthumb button{position:absolute;top:3px;right:3px;width:20px;height:20px;padding:0;border-radius:50%;
    background:rgba(0,0,0,.55);color:#fff;font-size:11px;line-height:20px}
  .hb-msg .attbtn.busy{opacity:.5}
  .hb-msg .cxtag svg{vertical-align:-2px}
  .hb-msg .newform{display:flex;flex-direction:column;gap:6px;border:1px solid var(--hb-line,#e3e8f0);
    border-radius:10px;padding:10px;margin:0 0 8px}
  .hb-msg .newform input,.hb-msg .newform textarea{box-sizing:border-box;width:100%;border:1px solid var(--hb-line,#e3e8f0);
    border-radius:8px;padding:6px 10px;font:inherit;font-size:13px;background:var(--hb-bg,#fff);color:var(--hb-ink,#26313d)}
  .hb-msg .newform .row{display:flex;gap:6px;justify-content:flex-end;align-items:center}
  .hb-msg .newerr{color:var(--hb-risk,#e5484d);font-size:12px}
  /* The reply / reply-all selector, ABOVE the box (email only — the other platforms have no second
     recipient to include). A segmented control, the same .seg language the settings panel already uses. */
  .hb-msg .composetop{display:flex;align-items:center;gap:9px;margin-bottom:7px;flex-wrap:wrap}
  .hb-msg .composehint{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8)}
  /* V2-616 — the open thread as LEFT/RIGHT bubbles, not an indented copy of the same row (V2-546's old
     shape). His report, verbatim in spirit: in a 1:1 chat the sender's name on every line is noise (the
     header above already names who this is), and his own replies need to read apart from theirs at a
     glance, the ordinary chat convention. isGroup (V2-616, thread.py) is the only reason a bubble still
     carries a name — a group has no single "who this is" for the header to say once.
     NOTE: this whole block is inside a JS template literal, so a backtick here ENDS it — write prose here
     without one, ever (it broke this exact widget once already). */
  .hb-msg .tbrow{display:flex;padding:3px 2px;justify-content:flex-start}
  .hb-msg .tbrow.out{justify-content:flex-end}
  .hb-msg .tbrow:hover .tacts{opacity:1}
  .hb-msg .tbstack{display:flex;flex-direction:column;max-width:78%;gap:3px}
  .hb-msg .tbrow:not(.out) .tbstack{align-items:flex-start}
  .hb-msg .tbrow.out .tbstack{align-items:flex-end}
  .hb-msg .tbubble{padding:8px 12px;border-radius:16px;background:var(--hb-bubble,#eef1f6);color:var(--hb-ink,#0d1622)}
  .hb-msg .tbrow:not(.out) .tbubble{border-bottom-left-radius:4px}
  .hb-msg .tbrow.out .tbubble{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);border-bottom-right-radius:4px}
  .hb-msg .tbubble.urg{box-shadow:inset 3px 0 0 var(--hb-risk,#e5484d)}
  /* V2-616 F4 — WhatsApp reads as WhatsApp, Telegram as Telegram, email as email: his own reply's bubble and
     the compose button take the OPEN thread's platform color (.thread.plat-ID, set once in threadView/
     mailDetail) instead of the one generic accent blue every platform shared before. Literal hex, matching
     PLAT[pl].bg exactly — the same identity, not a second palette that can drift from it. */
  .hb-msg .thread.plat-whatsapp .tbrow.out .tbubble,
  .hb-msg .thread.plat-whatsapp .composeside .bt-primary,
  .hb-msg .thread.plat-whatsapp .dfoot .bt-primary{background:#16B8A6}
  .hb-msg .thread.plat-telegram .tbrow.out .tbubble,
  .hb-msg .thread.plat-telegram .composeside .bt-primary,
  .hb-msg .thread.plat-telegram .dfoot .bt-primary{background:#2AABEE}
  .hb-msg .thread.plat-email .tbrow.out .tbubble,
  .hb-msg .thread.plat-email .composeside .bt-primary,
  .hb-msg .thread.plat-email .dfoot .bt-primary{background:#D8452D}
  .hb-msg .compose .bt-primary.pressing{transform:scale(.92);box-shadow:0 0 0 5px rgba(42,171,238,.35);transition:transform .12s,box-shadow .12s}
  .hb-msg .compose .bt-primary.sent{opacity:.85}
  .hb-msg .tbfrom{font-size:12px;font-weight:700;margin-bottom:2px;color:var(--hb-accent,#3D6FE0)}
  .hb-msg .tbtitle{font-size:14px;font-weight:600;margin:0 0 3px}
  .hb-msg .tbbody{font-size:14px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
  .hb-msg .tbbody.clamp{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .hb-msg .tbbody a.lnk{color:inherit;text-decoration:underline}
  .hb-msg .tbrow.out .more{color:#fff}
  .hb-msg .tbwhen{display:block;margin-top:3px;font-size:10.5px;text-align:right;opacity:.6}
  .hb-msg .tbrow.out .tbwhen{color:rgba(255,255,255,.85)}
  .hb-msg .tstart{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;
                  padding:8px 2px 12px}
  .hb-msg .tsl{font-size:11.5px;color:var(--hb-muted,#7b879c)}
  .hb-msg .tsbtn{border:1px solid var(--hb-line,#eef1f6);background:transparent;color:var(--hb-accent,#3D6FE0);
                 border-radius:999px;padding:3px 11px;font-size:11.5px;cursor:pointer}
  .hb-msg .tsbtn:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .tsbtn:disabled{color:var(--hb-muted,#7b879c);cursor:default;border-color:var(--hb-line,#eef1f6)}

  /* Media previews (V2-543): same-origin asset route only, elements not requests (isolation contract). */
  .hb-msg .mediaw{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
  .hb-msg .mediaw .matt{max-width:220px;max-height:170px;border-radius:10px;border:1px solid var(--hb-line,#e3e8f0);display:block}
  .hb-msg .mediaw video.mvid{max-width:260px;max-height:200px;border-radius:10px;background:#000}
  /* V2-616 F5 — the custom player: wide, FIXED width whatever the clip's length (fixed bar COUNT, not one
     derived from duration), a real drag-to-seek surface instead of the tiny native scrubber. */
  .hb-msg .maudio{display:flex;flex-direction:column;align-items:stretch;gap:4px;width:100%;min-width:220px;box-sizing:border-box}
  .hb-msg .mameta{display:flex;align-items:center;gap:8px}
  .hb-msg .mawhen{margin-left:auto;font-size:10.5px;opacity:.6;font-variant-numeric:tabular-nums}
  .hb-msg .tbrow.out .mawhen{color:rgba(255,255,255,.85);opacity:1}
  .hb-msg .tbubble.hasaudio{min-width:240px}
  .hb-msg .mapbtn{flex:0 0 auto;width:32px;height:32px;border-radius:50%;border:0;cursor:pointer;
    background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);font-size:12px;display:flex;align-items:center;justify-content:center}
  .hb-msg .mapbtn:hover{filter:brightness(1.08)}
  .hb-msg .mawave{flex:0 0 auto;width:100%;min-width:0;height:30px;display:flex;align-items:center;gap:2.5px;cursor:pointer;touch-action:none}
  .hb-msg .mabar{flex:1 1 0;min-width:2px;border-radius:2px;background:var(--hb-muted-2,#9aa7b8);opacity:.5}
  .hb-msg .mabar.played{background:var(--hb-accent,#3D6FE0);opacity:1}
  .hb-msg .matime{flex:0 0 auto;font-size:11px;color:var(--hb-muted-2,#9aa7b8);font-variant-numeric:tabular-nums}
  .hb-msg .tbrow.out .mapbtn{background:rgba(255,255,255,.28)}
  .hb-msg .tbrow.out .mabar{background:rgba(255,255,255,.4)}
  .hb-msg .tbrow.out .mabar.played{background:#fff;opacity:.95}
  .hb-msg .tbrow.out .matime{color:rgba(255,255,255,.85)}
  .hb-msg .thread.plat-whatsapp .mapbtn,.hb-msg .thread.plat-whatsapp .mabar.played{background:#16B8A6}
  .hb-msg .thread.plat-telegram .mapbtn,.hb-msg .thread.plat-telegram .mabar.played{background:#2AABEE}
  .hb-msg .thread.plat-email .mapbtn,.hb-msg .thread.plat-email .mabar.played{background:#D8452D}
  .hb-msg .thread.plat-whatsapp .tbrow.out .mabar.played,
  .hb-msg .thread.plat-telegram .tbrow.out .mabar.played,
  .hb-msg .thread.plat-email .tbrow.out .mabar.played{background:#fff}
  .hb-msg .mediaw a.mdoc,.hb-msg .mediaw span.mdoc{font-size:12.5px;color:var(--hb-accent,#3D6FE0);text-decoration:none;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;padding:4px 9px}
  .hb-msg .mediaw a.mdoc:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .twhen{font-size:11px;color:var(--hb-muted-2,#9aa7b8);margin-left:auto;flex:0 0 auto}

  .hb-msg .empty{text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:13px;padding:22px 0}
  .hb-msg .rest{text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:11px;opacity:.75;padding:8px 0 2px}

  /* ACTIVITY criterion bar (V2-624): the per-platform view criterion the operator set, always visible with
     its own off switch — a lens in a mode he cannot see is a lens that lies. */
  .hb-msg .critbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:2px 0 8px;
    padding:6px 10px;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;
    background:var(--hb-hover,#eef3f9)}
  .hb-msg .critlbl{font-size:12px;font-weight:600;color:var(--hb-ink,#26313d)}
  .hb-msg .critfetch{margin-left:auto;font-size:12px;padding:3px 8px}
  .hb-msg .critoff{flex:0 0 auto;border:0;background:transparent;cursor:pointer;font-size:13px;
    color:var(--hb-muted-2,#9aa7b8);padding:2px 4px}
  .hb-msg .critoff:hover{color:var(--hb-risk,#e5484d)}

  /* CHAT LIST of a platform: what the real app shows first — every conversation, newest first, a kind filter,
     a name search and «Cargar más». */
  /* V2-831 T-04 — ONE toolbar row: search pill · kind chips · new chat/group icons; wraps only on a narrow card. */
  .hb-msg .cxbar{display:flex;align-items:center;flex-wrap:wrap;gap:var(--sp-2,8px);margin:0 0 var(--sp-2,8px)}
  .hb-msg .cxsearch{flex:1 1 180px;min-width:140px;max-width:300px;box-sizing:border-box;height:32px;
    border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:0 12px;font-size:13px;
    background:var(--hb-bg-soft,#fbfdff);color:var(--hb-ink,#26313d)}
  .hb-msg .cxsearch:focus{outline:none;border-color:var(--hb-accent,#3D6FE0)}  /* selected chip: accent tint + ring */
  .hb-msg .cxchips{display:flex;gap:4px;flex-wrap:wrap}
  .hb-msg .cxchip{border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-muted,#6b7b92);
    border-radius:999px;font-size:12px;height:28px;padding:0 11px;cursor:pointer}
  .hb-msg .cxchip:hover{color:var(--hb-ink,#26313d)}
  .hb-msg .cxchip.on{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 18%,transparent);border-color:transparent;
    box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--hb-accent,#3D6FE0) 55%,transparent);color:var(--hb-ink,#26313d)}
  .hb-msg .cxnew{display:flex;gap:2px;margin-left:auto}
  .hb-msg .cxnewbt{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;padding:0;border:0;
    border-radius:9px;background:transparent;color:var(--hb-muted,#3a4757);cursor:pointer}
  .hb-msg .cxnewbt svg{width:18px;height:18px;display:block}
  .hb-msg .cxnewbt:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .cxtag{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);font-weight:400}
  .hb-msg .trow.cxarch{opacity:.6}
  .hb-msg .cxmore{display:block;margin:8px auto 2px;font-size:12.5px;padding:5px 14px}
  .hb-msg .snote{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);margin:4px 0 8px}
  .hb-msg .cxnote{text-align:center;color:var(--hb-muted-2,#9aa7b8);font-size:12px;padding:8px 0 2px}

  /* NARROW SCREENS (V2-559). MEASURED FIRST, and the measurement removed most of what was written here:
     rendered at 375px in six states (connect panel with three failures, both wizards, the QR, the chat list
     and an open thread), NOTHING was clipped and nothing left the viewport, and the wrap rules drafted for the
     channel row only made every row twice as tall for a defect that does not exist (the long statuses and the
     action button never co-occur). What is left is the part that IS an improvement on a phone: let a received
     photo use the whole card instead of a 220px thumbnail taken from the desktop (the root's own width is
     fluid now, V2-615, so it needs no override here). */
  @media (max-width: 430px){
    .hb-msg .mediaw .matt,.hb-msg .mediaw video.mvid{max-width:100%;max-height:none}
  }

  /* The «connect a channel» prompt of an empty card. */
  .hb-msg .wbody{font-size:13.5px;color:var(--hb-muted,#4a5a70);line-height:1.6}
  .hb-msg .wbody b{color:var(--hb-ink,#0d1622)}
  /* Homogeneous buttons (V2-570): one scale for every action of the card, instead of the .btn/.cbtn/.dbtn set
     that had grown three different heights and paddings. */
  .hb-msg .bt{height:38px;padding:0 18px;border-radius:10px;font-size:13.5px;font-weight:600;cursor:pointer;
    display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;
    /* A bare .bt (Save draft, attach) is the quiet button: without these it wore the browser's own light-grey
       face on the dark card, and the attach icon drew black on grey (V2-813, iPhone 14). */
    border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-ink,#0d1622)}
  .hb-msg .bt:hover:not(:disabled){border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .bt:disabled{opacity:.6;cursor:default}
  .hb-msg .bt-primary{border:0;color:var(--canvas,#101216);background:var(--hb-accent,#3D6FE0)}
  .hb-msg .bt-primary:hover:not(:disabled){filter:brightness(1.06)}
  .hb-msg .bt-ghost{border:1px solid var(--hb-line,#e3e8f0);background:transparent;color:var(--hb-muted,#5b6b82)}
  .hb-msg .bt-ghost:hover:not(:disabled){border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  /* The grid of channel icons (the «connect a channel» prompt): compact with 3 connectors or 20. */
  .hb-msg .igrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:12px}
  .hb-msg .ibox{display:flex;flex-direction:column;align-items:center;gap:7px;padding:16px 10px;
    border:1px solid var(--hb-line,#e3e8f0);border-radius:13px;background:var(--hb-bg,#fff);cursor:pointer;
    font:inherit;color:inherit}
  .hb-msg .ibox:hover{border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .ibox.sel{border-color:var(--hb-accent,#3D6FE0);background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 6%,transparent)}
  .hb-msg .ibox.conn{border-color:var(--hb-accent2,#16B8A6)}
  .hb-msg .ibox.conn .isub{color:var(--hb-accent2,#16B8A6);font-weight:600}
  .hb-msg .ibox .iicon{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .ibox .iicon .picon{opacity:1}
  .hb-msg .ibox .iicon svg{width:24px;height:24px}
  .hb-msg .ibox .ilabel{font-size:13px;font-weight:600;color:var(--hb-ink,#0d1622);text-align:center}
  .hb-msg .ibox .isub{font-size:11px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .conns{display:flex;flex-wrap:wrap;gap:6px}
  .hb-msg .conns .ok{font-size:11px;color:var(--hb-muted,#5b6b82);display:flex;align-items:center;gap:5px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:3px 9px}
  .hb-msg .conns .ok .lk{color:var(--hb-muted-2,#9aa7b8);cursor:pointer;text-decoration:underline}
  .hb-msg .conns .ok .lk:hover{color:var(--hb-risk,#e5484d)}
  `;
