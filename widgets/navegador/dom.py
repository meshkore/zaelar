"""widgets/navegador/dom.py — DOM/accessibility snapshot + human-like input primitives (split out of owner.py,
2026-08-17 modularization pass). Page-parametric functions with no module-global coupling: `page`/`h`/`mouse`
are always passed explicitly by the caller (TaskBrowser, in owner.py). The one thing that made this NOT a clean
move before this session's `owner.py` dead-code deletion: `_human_move`/`_human_click_at` used to fall back to
owner.py's module-level `_mouse` when `mouse` was omitted — a fallback only the now-deleted module-level
`agent_act()` ever relied on. With that gone, every surviving caller already passes `mouse` explicitly, so the
parameter is required here and this file has zero dependency on owner.py.

Re-exported from owner.py, since TaskBrowser's methods (which stay there) reference these as bare names."""
from __future__ import annotations

import asyncio
import random
import re

# IRREVERSIBLE actions that require operator OK before execution (confirm-gate). Intentionally conservative
# (do not gate normal navigation): only explicit purchase/payment/publishing/deletion.
_DANGER_RE = re.compile(
    r"\b(comprar|pagar|pagó|finalizar compra|realizar pedido|tramitar pedido|confirmar pedido|confirmar compra|"
    r"proceder al pago|publicar|eliminar cuenta|borrar cuenta|eliminar|borrar|checkout|buy now|buy|pay|purchase|"
    r"place order|confirm order|complete purchase|publish|delete account|delete)\b", re.I)

# ── Automator: accessibility snapshot + human input + action executor (agent.py) ────────────────────────────
_INTERACTIVE = ("a, button, input, textarea, select, [role=button], [role=link], [role=textbox], "
                "[role=checkbox], [role=radio], [role=tab], [role=menuitem], [role=combobox], [role=option]")

# Extractor for real LISTINGS from a results grid (runs in the page) → {title,price,tel,url,image}.
# Hardened (TASK 4): REQUIRE an actionable datum (see V2-240 — it used to require a PRICE, which is what a
# SHOPPING errand leaves behind and nothing else does), EXCLUDE ads/tracking
# (doubleclick/googleads/.../campaign utm), and **dedup by LISTING** (same /item/ or same pathname → 1 only, so
# 30 links to the same listing collapse into one). Prioritize listing links (/item/, /p/, /producto, /anuncio).
# The FINE relevance filtering (this is an enduro bike, not a "Moto G" phone) is done by the model in summarize.
_JS_EXTRACT = r"""
(limit) => {
  const out=[], seen=new Set();
  // La COMA es el separador decimal en media Europa, y faltaba de la clase de caracteres: sobre «169,00 €» el
  // patrón viejo empezaba a casar en «00» y devolvía «00 €», o sea un monitor de 169 € anunciado como de 0 €.
  // Medido el 2026-08-21 sobre una tarjeta con la forma de Amazon (precio partido en spans, con el importe
  // completo repetido en un nodo fuera de pantalla): title:"" price:"00 €" en las dos filas.
  // …y el ENTERO y los CÉNTIMOS pueden venir en nodos distintos, que `innerText` separa con un salto de línea
  // («169\n00 €»): sin el grupo opcional, el patrón empezaba a casar en «00» y se dejaba fuera el 169.
  // NO se reconstruye el separador decimal: se colapsa el espacio y se entrega «169 00 €» tal cual. Meter una
  // coma sería adivinar —hay sitios que separan los MILES con espacio («1 234 €»)— y adivinar mal ahí cambia
  // un precio por cien. Lo que se ve es lo que la página puso; el nombre y el enlace acompañan al importe.
  const priceRe=/(\d[\d.,]{0,12}(?:\s\d{1,2})?\s*€)|(€\s*\d[\d.,]{0,12})|(\d[\d.,]{0,12}\s?(EUR|eur))/;
  const hasLetter=s=>/[a-zA-ZÀ-ÿ\u0100-\u024f\u0370-\u1fff\u3040-\u9fff]/.test(s||'');
  // El NOMBRE de lo que se anuncia cuando el propio enlace no lo lleva dentro. Un listado es una rejilla de
  // TARJETAS y el nombre de cada cosa es el encabezado de su tarjeta: vale para un producto, un piso, un hotel
  // o una entrada, y no nombra ningún sitio. Se sube como mucho cinco niveles —más arriba ya no es la tarjeta,
  // es la sección, y devolvería «Resultados» para todas— y se prefiere el encabezado que apunta a ESTA misma
  // ficha, que es la señal fuerte de que la nombra a ella y no a la vecina.
  // QUÉ ES LA TARJETA, definido UNA vez y leído por los dos que la necesitan (el nombre y el teléfono). Se sube
  // como mucho cinco niveles y solo mientras el ancestro siga siendo UNA ficha: en cuanto abarca varias es la
  // REJILLA, y lo que hay ahí vale para todas — un dato que nombra a todas no nombra a ninguna. Tenerlo en dos
  // sitios sería tener dos definiciones de «tarjeta» que se separan sin avisar.
  const cardWalk=(a, read)=>{
    let n=a;
    for(let i=0;i<5&&n&&n.parentElement;i++){
      n=n.parentElement;
      const paths=new Set();
      for(const l of n.querySelectorAll('a[href]')){ try{ paths.add(new URL(l.href).pathname); }catch(_){} }
      if(paths.size>4) break;
      const got=read(n);
      if(got) return got;
    }
    return '';
  };
  const cardName=(a, path)=>cardWalk(a, (n)=>{
    const hs=[...n.querySelectorAll('h1,h2,h3,h4,[role=heading]')];
    if(!hs.length) return '';
    let best=null;
    for(const h of hs){
      const t=(h.innerText||'').trim();
      if(!t || t.length<3 || !hasLetter(t) || priceRe.test(t)) continue;
      const link=h.querySelector('a[href]')||h.closest('a[href]');
      let same=false; if(link){ try{ same=new URL(link.href).pathname===path; }catch(_){} }
      // el encabezado que apunta a ESTA misma ficha es la señal fuerte de que la nombra a ella y no a la vecina
      if(same) return t.slice(0,90);
      if(!best) best=t;
    }
    return best ? best.slice(0,90) : '';
  });
  // UN NÚMERO AL QUE LLAMAR. Un `tel:` es inequívoco; en texto se exige que sean 9-14 dígitos CON separadores,
  // que es lo que descarta un precio («1.234,56» son 6 dígitos), un código de barras (sin separadores) y una
  // fecha (la barra no es separador aquí).
  const telText=(s)=>{
    const m=(s||'').match(/(?:\+\d{1,3}[\s.\-]?)?(?:\d[\s.\-]?){8,14}/g);
    if(!m) return '';
    for(const t of m){
      const raw=t.trim(), d=raw.replace(/\D/g,'');
      if(d.length>=9 && d.length<=14 && /[\s.\-]/.test(raw)) return raw.slice(0,24);
    }
    return '';
  };
  const cardTel=(a)=>{
    return cardWalk(a, (n)=>{
      const t=n.querySelector('a[href^="tel:"]');
      if(t){ try{ return decodeURIComponent((t.getAttribute('href')||'').slice(4)).trim().slice(0,24); }catch(_){} }
      return telText(n.innerText||'');
    });
  };
  const AD=/(doubleclick|googlead|googlesyndication|adservice|adnxs|criteo|taboola|outbrain|\/ads?\/|utm_source=|banner)/i;
  const ITEM=/(\/item\/|\/p\/|\/producto|\/anuncio|\/product|\/listing|\/ad\/)/i;
  const cands=[];
  for(const a of document.querySelectorAll('a[href]')){
    let href; try{ href=a.href; }catch(_){ continue; }
    if(!href || href.startsWith('javascript:') || AD.test(href)) continue;
    // Un `tel:` (o un `mailto:`) es una forma de CONTACTAR con la ficha, no la ficha. Sin esto, la tarjeta de un
    // negocio salía DOS veces —una por su enlace y otra por su teléfono— y en un directorio eso es duplicar
    // entera la página.
    if(/^(tel:|mailto:|sms:)/i.test(href)) continue;
    if(a.closest('ins, iframe, [class*="ad-" i], [id*="google_ads" i], [aria-label*="anuncio" i]')) continue;
    const img=a.querySelector('img');
    const text=(a.innerText||'').trim();
    const pm=text.match(priceRe);
    // dedup key: the LISTING (pathname without query) → 30 links to the same listing = 1
    let key, path=''; try{ const u=new URL(href); key=u.origin+u.pathname; path=u.pathname; }catch(_){ key=href; }
    // V2-240 — UN RESULTADO ES UN NOMBRE Y UNA FORMA DE ACTUAR SOBRE ÉL, no un precio. El filtro pedía precio
    // porque «un anuncio tiene precio», y eso es verdad de UNA clase de encargo: la compra. Un fontanero, un
    // barbero, un cerrajero o un dentista no publican precio, así que la página devolvía CERO filas y el turno
    // se quedaba con lo único que le llegaba: el enlace del directorio. Medido por el arnés: `best-plumber-same-day`
    // y `weekend-barber`, los dos 1/5 con «0 filas extraídas».
    const tel = pm ? '' : cardTel(a);
    if(!pm && !tel) continue;                           // ni importe que pagar ni número al que llamar → no es una ficha
    // Un trozo de precio NO es un nombre: se exige al menos una letra. Sin eso, «169» pasaba por título de un
    // monitor de 169,00 € y la nota al cerebro decía «169 — 00 € — …», que es lo que el turno describió.
    let title=((img&&(img.alt||''))
               ||text.split('\n').map(s=>s.trim()).find(s=>s.length>2 && hasLetter(s) && !priceRe.test(s))
               ||cardName(a, path)||'').slice(0,90);
    if(seen.has(key)) continue;
    let image=''; if(img){ try{ image=img.currentSrc||img.src||''; }catch(_){} }
    cands.push({title, price: pm ? pm[0].replace(/\s+/g,' ').trim() : '', tel, url:href, image,
                _item: ITEM.test(href)});
    seen.add(key);
  }
  // If there are real LISTING links, keep only those (discard the remaining price-bearing noise).
  const items = cands.filter(c=>c._item);
  const list = (items.length ? items : cands).map(({_item, ...c})=>c);
  return list.slice(0, limit);
}
"""


async def _describe_el(h) -> tuple[str, str]:
    """Role + accessible name for an element, for the text snapshot read by the model."""
    tag = (await h.evaluate("e => e.tagName ? e.tagName.toLowerCase() : ''")) or ""
    role = await h.get_attribute("role")
    typ = (await h.get_attribute("type") or "").lower()
    if not role:
        if tag == "a":
            role = "link"
        elif tag == "button" or typ in ("button", "submit"):
            role = "button"
        elif tag == "input":
            role = "checkbox" if typ in ("checkbox", "radio") else "textbox"
        elif tag == "textarea":
            role = "textbox"
        elif tag == "select":
            role = "combobox"
        else:
            role = tag or "element"
    name = (await h.get_attribute("aria-label")) or (await h.get_attribute("placeholder")) or ""
    if not name:
        try:
            name = (await h.inner_text()) or ""
        except Exception:
            name = ""
    if not name:
        name = (await h.get_attribute("value")) or (await h.get_attribute("name")) \
            or (await h.get_attribute("title")) or ""
    return role, " ".join((name or "").split())


# BULK description (V2-036, performance fix #1): per-element `_describe_el` did ~7 `await`s each × up to 60 = hundreds
# of round trips that HELD the GIL in the uvicorn loop → starving the voice audio pump (choppy). This JS computes
# role+name+visibility for ALL interactive elements in ONE call.
_JS_DESCRIBE = r"""
els => els.map(e => {
  const tag = e.tagName ? e.tagName.toLowerCase() : '';
  const typ = (e.getAttribute('type')||'').toLowerCase();
  let role = e.getAttribute('role');
  if(!role){
    if(tag==='a') role='link';
    else if(tag==='button'||typ==='button'||typ==='submit') role='button';
    else if(tag==='input') role=(typ==='checkbox'||typ==='radio')?'checkbox':'textbox';
    else if(tag==='textarea') role='textbox';
    else if(tag==='select') role='combobox';
    else role = tag || 'element';
  }
  let name = e.getAttribute('aria-label') || e.getAttribute('placeholder') || '';
  if(!name) name = (e.innerText||'').trim();
  if(!name) name = e.getAttribute('value') || e.getAttribute('name') || e.getAttribute('title') || '';
  const r = e.getBoundingClientRect();
  const cs = window.getComputedStyle(e);
  const vis = !!(r.width>0 && r.height>0) && cs.visibility!=='hidden' && cs.display!=='none';
  return {role, name:(name||'').replace(/\s+/g,' ').trim(), vis};
})
"""


async def _bulk_metas(page) -> list:
    """role+name+visible for all interactive elements in ONE call, aligned by index with
    query_selector_all(_INTERACTIVE) (same selector → same document order). Fail-open to []."""
    try:
        return await page.eval_on_selector_all(_INTERACTIVE, _JS_DESCRIBE)
    except Exception:
        return []


def _snapshot_lines(handles: list, metas: list, refmap: dict) -> list:
    """Compose [ref] role \"name\" lines from handles + their bulk metadata, and fill refmap (ref→handle) so
    agent_act resolves this step's ref. Cap at 60. No awaits (all I/O is already done)."""
    lines: list = []
    ref = 0
    for i, h in enumerate(handles):
        m = metas[i] if i < len(metas) else None
        if not m or not m.get("vis"):
            continue
        role = m.get("role") or "element"
        name = m.get("name") or ""
        if not name and role not in ("textbox", "combobox", "checkbox", "radio"):
            continue
        ref += 1
        refmap[ref] = h
        lines.append(f'[{ref}] {role} "{name[:80]}"')
        if ref >= 60:
            break
    return lines



async def _human_move(page, tx: float, ty: float, mouse: dict) -> None:
    """Move the mouse from its current position to (tx,ty) along a Bezier curve with jitter and micro-pauses — it looks
    human and costs NO tokens (lives here, not in the model). `mouse` = position dict PER TAB (each task has its
    own mouse; the caller always passes it explicitly)."""
    m = mouse
    sx, sy = m["x"], m["y"]
    steps = random.randint(8, 18)
    cx = (sx + tx) / 2 + random.uniform(-60, 60)       # random control point → curved trajectory
    cy = (sy + ty) / 2 + random.uniform(-40, 40)
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * tx
        y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * ty
        try:
            await page.mouse.move(x, y)
        except Exception:
            break
        await asyncio.sleep(random.uniform(0.006, 0.02))
    m["x"], m["y"] = tx, ty


async def _human_click_handle(page, h, mouse: dict) -> None:
    await h.scroll_into_view_if_needed(timeout=5000)
    box = await h.bounding_box()
    if box:
        tx = box["x"] + box["width"] / 2 + random.uniform(-4, 4)
        ty = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
        await _human_move(page, tx, ty, mouse)
        await asyncio.sleep(random.uniform(0.05, 0.18))
        await page.mouse.click(tx, ty, delay=random.randint(40, 110))
    else:
        await h.click(timeout=5000)                    # fallback if there is no box (element without layout)


async def _human_type_handle(page, h, text: str, submit: bool, mouse: dict) -> None:
    await _human_click_handle(page, h, mouse)          # focus by clicking, like a human
    try:
        await h.fill("")                               # clear the field before typing
    except Exception:
        pass
    await page.keyboard.type(text, delay=random.randint(40, 120))   # typing with jitter
    if submit:
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await page.keyboard.press("Enter")



async def _human_click_at(page, x: float, y: float, mouse: dict) -> None:
    """Human click at ABSOLUTE viewport coordinates (vision mode: the model sees the screenshot and returns pixels)."""
    m = mouse
    await _human_move(page, x + random.uniform(-3, 3), y + random.uniform(-3, 3), m)
    await asyncio.sleep(random.uniform(0.05, 0.18))
    await page.mouse.click(m["x"], m["y"], delay=random.randint(40, 110))

