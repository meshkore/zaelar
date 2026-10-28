// The messaging card's stylesheet, first half: the card frame, header, settings, profiles, the mail client's rail,
// crumb and draft screen. Moved verbatim out of `injectStyles()` in widget.js, which keeps the <style> guard.
import { READING_CSS } from "./style_reading.js";

export const CSS = `
  /* Fluid width, ANCHORED to the parent card (V2-615, same fix as youtube's V2-597): the old
     width:min(480px,92vw) capped the readable column at 480px FOREVER, even on a card the operator had
     deliberately dragged much wider to read a long line (a tracking URL, a long subject) — the card grew,
     the text column inside it did not. The CARD decides the width now; box-sizing keeps padding from
     overflowing it. */
  .hb-msg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--hb-ink,#0d1622);width:100%;box-sizing:border-box}
  /* V2-680 — a READING screen (an open mail, an open thread) takes the whole card and scrolls INSIDE it,
     the way any mail client does: the message body gets every spare pixel and the reply box is pinned to
     the bottom edge where it can always be reached. The operator's report was that a three-page mail was
     shown through a keyhole while the card around it sat mostly empty.
     Only these two screens opt in (the .full class): the dashboard and the connector wizard are stacks of
     boxes that legitimately scroll as one page, and giving them a fixed height would only pin their own
     headers against a short card.
     NOTE — this deliberately does NOT disable the host's own scroller the way the video and agenda widgets
     do. Measured on the real card chrome: with the height chain in place the widget is exactly the card's
     height and the host never scrolls, so the rule would change nothing; and in the one case it COULD
     change something — the height failing to resolve — it would clip the mail with no scrollbar at all,
     which is strictly worse than a card that scrolls. */
  .hb-msg.full{height:100%;display:flex;flex-direction:column;min-height:0;container-type:inline-size}
  .hb-msg.full > .thread{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
  .hb-msg.full > .thread > .thd{flex:0 0 auto}
  /* The body is the ONE part that grows and scrolls; everything else keeps its natural height. */
  .hb-msg.full > .thread > .mdet,
  .hb-msg.full > .thread > .tl{flex:1 1 auto;min-height:0;overflow:auto;max-height:none}
  .hb-msg.full > .thread > .compose{flex:0 0 auto}
  /* V2-611 redesign — the header is its OWN band, visually separated from the content below it (the
     operator's ask: "que se delimiten mejor las secciones"), and every icon in it is a real, bigger button
     with its own hover/click target — not a bare glyph floating in the row. */
  .hb-msg .hd{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 0 14px;padding:2px 2px 14px;
    border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-msg .hd b{font-size:17px} .hb-msg .hd .sub{font-size:12px;color:var(--hb-muted-2,#7d8a9c)}
  .hb-msg .hdtitle{cursor:pointer;border-radius:8px;padding:4px 7px;margin:-4px -7px}
  .hb-msg .hdtitle:hover{background:var(--hb-hover,#eef3f9)}
  .hb-msg .dots{display:flex;gap:4px;margin-left:auto}
  /* V2-616 — a second cluster (connectors ⚙/🔌/Limpiar), set apart from the channel dots by a divider and
     its own left padding rather than sharing the plain .hd gap every other pair of icons uses. */
  .hb-msg .hdactions{display:flex;align-items:center;gap:4px;padding-left:10px;margin-left:6px;
    border-left:1px solid var(--hb-line,#e3e8f0)}
  .hb-msg .picon{display:inline-flex;align-items:center;justify-content:center;opacity:.4;flex:0 0 auto;
    width:34px;height:34px;border-radius:10px;cursor:pointer}
  .hb-msg .picon svg{width:20px;height:20px}
  .hb-msg .picon:hover{background:var(--hb-hover,#eef3f9);opacity:.7}
  .hb-msg .picon.on{opacity:1}
  .hb-msg .picon.on:hover{opacity:1;background:var(--hb-hover,#eef3f9)}
  .hb-msg .picon.filt{background:var(--hb-hover,#eef3f9);box-shadow:inset 0 0 0 1.5px currentColor}
  .hb-msg .pdot{width:18px;height:18px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
    font-size:9.5px;font-weight:700;color:#fff;background:var(--hb-neutral,#3a4a5c);opacity:.5;flex:0 0 auto}
  .hb-msg .pdot.on{opacity:1;background:var(--hb-accent2,#16B8A6)}
  .hb-msg .gear{border:0;background:transparent;color:var(--hb-muted,#3a4757);cursor:pointer;font-size:17px;
    width:34px;height:34px;border-radius:10px;line-height:1}
  .hb-msg .gear:hover,.hb-msg .gear.active{background:var(--hb-hover,#eef3f9);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .clr{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:8px;padding:6px 11px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#3a4757)}
  .hb-msg .clr:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}

  /* Settings. */
  .hb-msg .settings{border:1px solid var(--hb-line,#eef1f6);border-radius:11px;padding:11px 12px;margin-bottom:11px;background:var(--hb-bg-soft,#fbfdff)}
  .hb-msg .stitle{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--hb-muted-2,#9aa7b8);margin:9px 0 6px}
  .hb-msg .stitle:first-child{margin-top:0}
  .hb-msg .seg{display:inline-flex;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;overflow:hidden}
  .hb-msg .segbtn{border:0;background:var(--hb-bg,#fff);color:var(--hb-muted,#5b6b82);font-size:12px;padding:6px 13px;cursor:pointer}
  .hb-msg .segbtn+.segbtn{border-left:1px solid var(--hb-line,#e3e8f0)}
  .hb-msg .segbtn.active{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216)}

  /* COMPLETE profile (original). */
  .hb-msg .list{display:flex;flex-direction:column;gap:7px;max-height:52vh;overflow:auto}
  .hb-msg .row{display:flex;gap:9px;align-items:flex-start;padding:9px 10px;border:1px solid var(--hb-line,#eef1f6);border-radius:11px;background:var(--hb-bg,#fff)}
  .hb-msg .row.mine{background:var(--hb-warn-bg,#fff7e8);border-color:var(--hb-warn-border,#f2dca6)}
  .hb-msg .dot{width:8px;height:8px;border-radius:50%;margin-top:5px;flex:0 0 auto}
  .hb-msg .body{flex:1;min-width:0}
  .hb-msg .from{font-size:13px;font-weight:600;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .hb-msg .from .grp{font-weight:400;color:var(--hb-muted-2,#7d8a9c);font-size:11px}
  .hb-msg .badge{font-size:10px;font-weight:700;color:#fff;border-radius:6px;padding:1px 6px;letter-spacing:.02em}
  .hb-msg .from .tag{font-size:10px;font-weight:600;color:var(--hb-warn-ink,#9a6a00);background:var(--hb-warn-bg,#fff3d6);border:1px solid var(--hb-warn-border,#f2dca6);border-radius:6px;padding:0 5px}
  .hb-msg .msg{font-size:13px;color:var(--hb-ink,#0d1622);margin-top:2px;white-space:pre-wrap;word-break:break-word}
  .hb-msg .why{font-size:11px;color:var(--hb-muted,#6b7b92);margin-top:3px;font-style:italic}
  .hb-msg .acts{display:flex;flex-direction:column;gap:4px;flex:0 0 auto}
  .hb-msg .acts button{border:1px solid var(--hb-line,#e3e8f0);background:var(--hb-bg,#fff);border-radius:8px;width:30px;height:26px;font-size:13px;cursor:pointer;color:var(--hb-muted,#3a4757);line-height:1}
  .hb-msg .acts button:hover{border-color:var(--hb-accent2,#16B8A6);color:#0f766e}
  .hb-msg .acts .mute{font-size:11px;color:var(--hb-muted-2,#9aa7b8)}
  .hb-msg .acts .mute:hover{border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}

  /* SIMPLE profile: minimal timeline, Claude Code / VS Code style. */
  .hb-msg .tl{display:flex;flex-direction:column;max-height:56vh;overflow:auto}
  .hb-msg .trow{display:flex;gap:10px;align-items:flex-start;padding:11px 2px;border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-msg .trow:last-child{border-bottom:0}
  .hb-msg .trow:hover .tacts{opacity:1}
  .hb-msg .tlead{width:7px;height:7px;border-radius:50%;margin-top:8px;flex:0 0 auto;background:transparent}
  .hb-msg .tmain{flex:1;min-width:0}
  .hb-msg .thead{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:3px}
  .hb-msg .pchip{width:19px;height:19px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
    font-size:10px;font-weight:700;color:#fff;flex:0 0 auto}
  .hb-msg .tfrom{font-size:14.5px;font-weight:600;color:var(--hb-ink,#0d1622)}
  .hb-msg .tpara{font-size:12.5px;color:var(--hb-muted,#6b7b92);font-weight:400}
  .hb-msg .more{display:inline-block;margin-top:4px;font-size:12.5px;color:var(--hb-accent,#3D6FE0);cursor:pointer}
  .hb-msg .more:hover{text-decoration:underline}
  .hb-msg .tacts{display:flex;gap:2px;flex:0 0 auto;opacity:.3;transition:opacity .12s}
  .hb-msg .tacts button{border:0;background:transparent;border-radius:7px;width:26px;height:24px;font-size:12.5px;cursor:pointer;color:var(--hb-muted,#5b6b82);line-height:1}
  .hb-msg .tacts button:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}
  /* Action buttons carry inline SVG (never emoji): a glyph font renders each emoji
     differently per machine (the operator read the mute button as a subwoofer). */
  .hb-msg .acts button,.hb-msg .tacts button{display:inline-flex;align-items:center;justify-content:center}
  .hb-msg .acts button svg,.hb-msg .tacts button svg{width:14px;height:14px;display:block}

  /* EMAIL default view (V2-610): a Gmail-style compact row — sender + subject in two lines, no body — and
     its detail screen. Reuses .tlead/.thd/.tacts from the shapes above so urgency, the back-crumb and the
     action buttons stay visually consistent across every screen of this widget. */
  .hb-msg .mrow{display:flex;gap:10px;align-items:flex-start;padding:10px 2px;border-bottom:1px solid var(--hb-line,#eef1f6);cursor:pointer}
  .hb-msg .mrow:last-child{border-bottom:0}
  .hb-msg .mrow:hover{background:var(--hb-hover,#eef3f9)}
  .hb-msg .mrow:hover .tacts{opacity:1}
  .hb-msg .mmain{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}
  .hb-msg .mline1{display:flex;align-items:baseline;gap:8px}
  .hb-msg .mfrom{font-size:14.5px;font-weight:600;color:var(--hb-ink,#0d1622);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60%}
  .hb-msg .mwhen{margin-left:auto;font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);flex:0 0 auto}
  .hb-msg .msubj{font-size:13.5px;color:var(--hb-muted,#5f6b7c);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-msg .mdet{padding:2px 2px 10px}
  /* WHERE AM I (2026-10-26): the house + title are lit on the home; inside a section they dim and the
     section's name follows as the current crumb. Outline icons, the same stroke as every action icon. */
  .hb-msg .homebtn{border:0;background:transparent;color:var(--hb-muted-2,#7d8a9c);width:32px;height:32px;
    border-radius:9px;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;margin-right:-4px}
  .hb-msg .homebtn svg{width:18px;height:18px}
  .hb-msg .homebtn:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}
  .hb-msg .homebtn.on{color:var(--hb-accent,#3D6FE0);background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 14%,transparent)}
  .hb-msg .hd .hdtitle{color:var(--hb-muted,#5f6b7c);font-weight:600}
  .hb-msg .hd .hdtitle.on{color:var(--hb-accent,#3D6FE0);font-weight:700}
  .hb-msg .hdsep,.hb-msg .msep{color:var(--hb-muted-2,#9aa7b8);font-size:14px}
  .hb-msg .hd .hdsec{font-size:17px;color:var(--hb-ink,#0d1622)}
  .hb-msg .hd .hdcur{font-size:14px;font-weight:600;color:var(--hb-muted,#5f6b7c)}
  /* The MAIL CLIENT (V2-807 T-01): ONE left rail — Compose, the Inbox opening into the categories the provider
     sorts it by, every other folder — each with the provider's own unread figure; the list beside it. The rail
     reads the card's OWN width (a container query, not the screen's): a narrow card folds it to icons, a phone-
     narrow one to a drawer behind the button that names where he is. */
  .hb-msg.full > .mclient{flex:1 1 auto;min-height:0}
  .hb-msg .mclient{container-type:inline-size;position:relative;min-height:0}
  .hb-msg .mcgrid{display:grid;grid-template-columns:208px minmax(0,1fr);gap:14px;height:100%;min-height:0}
  .hb-msg .mrail{display:flex;flex-direction:column;gap:1px;min-width:0;min-height:0;overflow:auto;
    padding-right:10px;border-right:1px solid var(--hb-line-subtle,#eef1f6)}
  .hb-msg .mpanel{min-width:0;min-height:0;overflow:auto;display:flex;flex-direction:column}
  .hb-msg .mcompose{height:36px;padding:0 14px;gap:8px;flex:0 0 auto;margin:0 0 10px;align-self:flex-start}
  .hb-msg .mcompose svg{width:15px;height:15px}
  .hb-msg .mnav{display:flex;align-items:center;gap:10px;border:0;background:transparent;color:var(--hb-muted,#5b6b82);
    font:inherit;font-size:13.5px;font-weight:600;padding:0 10px;min-height:32px;border-radius:999px;cursor:pointer;
    text-align:left;width:100%;box-sizing:border-box;position:relative;flex:0 0 auto}
  .hb-msg .mnav svg{width:16px;height:16px;flex:0 0 auto}
  .hb-msg .mnav .mnl{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-msg .mnav.sub{padding-left:26px;font-weight:500;font-size:13px;min-height:30px}
  .hb-msg .mnav:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}
  .hb-msg .mnav.on{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 16%,transparent);color:var(--hb-accent,#3D6FE0)}
  .hb-msg .mnav.on .mfn{background:var(--hb-accent,#3D6FE0);color:var(--canvas,#fff)}
  .hb-msg .mfn{font-size:11px;font-weight:700;min-width:16px;height:16px;padding:0 5px;border-radius:999px;flex:0 0 auto;
    display:inline-flex;align-items:center;justify-content:center;background:var(--hb-neutral,#3a4a5c);color:var(--hb-ink,#fff)}
  .hb-msg .mrules{margin-top:10px;padding:8px 6px 0;border-top:1px solid var(--hb-line-subtle,#eef1f6);
    display:flex;flex-direction:column;gap:2px;flex:0 0 auto}
  .hb-msg .mruleshd{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
    color:var(--hb-muted-2,#7d8a9c);padding:0 4px 4px}
  .hb-msg .mrule{display:flex;align-items:flex-start;gap:4px;font-size:12.5px;color:var(--hb-muted,#5b6b82);
    padding:3px 0 3px 4px;line-height:1.35}
  .hb-msg .mrulet{flex:1 1 auto;min-width:0;overflow-wrap:anywhere}
  .hb-msg .mrulex{border:0;background:transparent;color:var(--hb-muted-2,#7d8a9c);width:24px;height:24px;
    border-radius:7px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto}
  .hb-msg .mrulex:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-risk,#e5484d)}
  .hb-msg .mrailsep{height:1px;background:var(--hb-line-subtle,#eef1f6);margin:8px 6px;flex:0 0 auto}
  .hb-msg .mdrawerbtn{display:none;align-items:center;gap:8px;border:1px solid var(--hb-line,#e3e8f0);
    background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);font:inherit;font-size:13.5px;font-weight:600;
    border-radius:999px;padding:0 12px;min-height:34px;cursor:pointer;align-self:flex-start;margin:0 0 8px}
  .hb-msg .mdrawerbtn svg{width:16px;height:16px}
  @container (max-width:600px){
    .hb-msg .mcgrid{grid-template-columns:52px minmax(0,1fr);gap:10px}
    .hb-msg .mrail{padding-right:6px;align-items:center}
    .hb-msg .mnav,.hb-msg .mnav.sub{justify-content:center;padding:0;width:40px;min-height:36px}
    .hb-msg .mnav .mnl,.hb-msg .mcompose .mnl{display:none}
    .hb-msg .mnav .mfn{position:absolute;top:0;right:-4px;min-width:14px;height:14px;font-size:9.5px;padding:0 3px}
    .hb-msg .mcompose{width:40px;padding:0;justify-content:center;align-self:center}
    .hb-msg .mrules{display:none}
  }
  @container (max-width:440px){
    .hb-msg .mcgrid{grid-template-columns:minmax(0,1fr)}
    .hb-msg .mrail{display:none}
    .hb-msg .mdrawerbtn{display:inline-flex}
    .hb-msg .mcgrid.open .mrail{display:flex;position:absolute;z-index:3;top:42px;left:0;bottom:0;width:232px;
      align-items:stretch;padding:8px;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#e3e8f0);
      border-radius:12px;box-shadow:var(--hb-shadow-2,0 12px 32px rgba(0,0,0,.18))}
    .hb-msg .mcgrid.open .mnav{justify-content:flex-start;padding:0 10px;width:100%}
    .hb-msg .mcgrid.open .mnav.sub{padding-left:26px}
    .hb-msg .mcgrid.open .mnav .mnl,.hb-msg .mcgrid.open .mcompose .mnl{display:inline}
    .hb-msg .mcgrid.open .mnav .mfn{position:static}
    .hb-msg .mcgrid.open .mcompose{width:auto;padding:0 14px;align-self:flex-start}
    .hb-msg .mcgrid.open .mrules{display:flex}
  }
  .hb-msg .mlist{max-height:none}
  .hb-msg .mdptr{display:flex;align-items:center;gap:9px;width:100%;box-sizing:border-box;margin:0 0 6px;padding:0 12px;
    min-height:36px;border:1px dashed var(--hb-line-strong,#cfd6e0);border-radius:10px;background:transparent;
    color:var(--hb-ink,#0d1622);font:inherit;font-size:13px;cursor:pointer;text-align:left;flex:0 0 auto}
  .hb-msg .mdptr svg{width:15px;height:15px;color:var(--hb-accent,#3D6FE0);flex:0 0 auto}
  .hb-msg .mdptr .mdptrt{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hb-msg .mdptr .mdptro{color:var(--hb-accent,#3D6FE0);font-weight:600;flex:0 0 auto}
  .hb-msg .mdptr:hover{border-style:solid;border-color:var(--hb-accent,#3D6FE0)}
  .hb-msg .mrow.seen .mfrom{font-weight:500;color:var(--hb-muted,#5f6b7c)}
  .hb-msg .mrow.unseen .msubj{color:var(--hb-ink,#0d1622)}
  .hb-msg .mtag{font-size:11px;color:var(--hb-accent,#3D6FE0);font-weight:600;flex:0 0 auto}
  .hb-msg .mdtag{font-size:11px;font-weight:700;color:var(--hb-risk,#e5484d);flex:0 0 auto}
  .hb-msg .mgroup{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
    color:var(--hb-muted-2,#9aa7b8);padding:14px 2px 4px}
  .hb-msg .mmore{align-self:flex-start;margin:10px 0 2px}
  .hb-msg .mnote{font-size:12.5px;color:var(--hb-muted,#5b6b82);margin:4px 2px 8px}
  /* Navigation bar of a mail screen: ⌂ › Correo › Recibidos › <subject> … ← Recibidos. */
  .hb-msg .mcrumb{gap:6px;min-width:0}
  .hb-msg .mchome{border:0;background:transparent;color:var(--hb-muted-2,#7d8a9c);width:28px;height:28px;border-radius:8px;
    display:inline-flex;align-items:center;justify-content:center;cursor:pointer;flex:0 0 auto}
  .hb-msg .mchome svg{width:16px;height:16px}
  .hb-msg .mchome:hover{background:var(--hb-hover,#eef3f9);color:var(--hb-ink,#0d1622)}
  .hb-msg .mcr{border:0;background:transparent;font-size:13px;color:var(--hb-muted,#5b6b82);padding:3px 4px;border-radius:6px;
    cursor:pointer;white-space:nowrap;flex:0 0 auto}
  .hb-msg .mcr:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-msg .mcr.cur{color:var(--hb-ink,#0d1622);cursor:default;font-weight:700;overflow:hidden;text-overflow:ellipsis;
    flex:0 1 auto;min-width:0}
  /* A DRAFT over the whole card: the fields, the text growing into every spare pixel, the buttons pinned below. */
  .hb-msg.full > .thread > .dfoot{flex:0 0 auto}
  .hb-msg .mdform{gap:0;padding:4px 14px 12px}
  .hb-msg .mdf{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--hb-line,#eef1f6);padding:6px 0}
  .hb-msg .mdk{font-size:12.5px;color:var(--hb-muted-2,#9aa7b8);width:56px;flex:0 0 auto}
  .hb-msg .mdin{flex:1;min-width:0;border:0;background:transparent;font:inherit;font-size:14px;color:var(--hb-ink,#0d1622);
    padding:6px 0;outline:none}
  .hb-msg .mdin[readonly]{color:var(--hb-muted,#5b6b82)}
  .hb-msg .mdbody{flex:1 1 auto;min-height:160px;border:0;background:transparent;resize:none;outline:none;font:inherit;
    font-size:14.5px;line-height:1.6;color:var(--hb-ink,#0d1622);padding:12px 0 0}
  .hb-msg .mdfiles{font-size:12.5px;color:var(--hb-muted,#5b6b82)}
  .hb-msg .dfoot{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:12px}
  .hb-msg .mddel:hover:not(:disabled){border-color:var(--hb-risk,#e5484d);color:var(--hb-risk,#e5484d)}
  .hb-msg .mdnote{font-size:12px;color:var(--hb-muted,#5b6b82)}
  /* On a narrow CARD (its own width, not the screen's — a narrow card on a wide desktop overflowed) the crumb keeps
     the house, what is open and the way back; the middle steps are the ← button. */
  @container (max-width:560px){
    .hb-msg .mcrumb .mcr:not(.cur),.hb-msg .mcrumb .msep{display:none}
  }
` + READING_CSS;
