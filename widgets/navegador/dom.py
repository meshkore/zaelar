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
  const out=[], seen=new Map();   // key de ficha → SU FILA (V2-324: la segunda ancla completa, no se tira)
  // La COMA es el separador decimal en media Europa, y faltaba de la clase de caracteres: sobre «169,00 €» el
  // patrón viejo empezaba a casar en «00» y devolvía «00 €», o sea un monitor de 169 € anunciado como de 0 €.
  // Medido el 2026-08-21 sobre una tarjeta con la forma de Amazon (precio partido en spans, con el importe
  // completo repetido en un nodo fuera de pantalla): title:"" price:"00 €" en las dos filas.
  // …y el ENTERO y los CÉNTIMOS pueden venir en nodos distintos, que `innerText` separa con un salto de línea
  // («169\n00 €»): sin el grupo opcional, el patrón empezaba a casar en «00» y se dejaba fuera el 169.
  // NO se reconstruye el separador decimal: se colapsa el espacio y se entrega «169 00 €» tal cual. Meter una
  // coma sería adivinar —hay sitios que separan los MILES con espacio («1 234 €»)— y adivinar mal ahí cambia
  // un precio por cien. Lo que se ve es lo que la página puso; el nombre y el enlace acompañan al importe.
  const priceRe=/(\d[\d.,]{0,12}(?:\s\d{1,2})?\s*€)|(€\s*\d[\d.,]{0,12})|(\d[\d.,]{0,12}\s?(EUR|eur)\b)/;
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
  // `maxPaths` — cuántos listados DISTINTOS puede abarcar el ancestro y seguir contando como la tarjeta. El
  // nombre y el teléfono admiten 4 (una tarjeta puede enlazar al vendedor, a su tienda, a una categoría) y el
  // encabezado se desempata además por el enlace que apunta a ESTA misma ficha. El PRECIO no tiene ese
  // desempate y no puede permitirse el error, así que pide 1: solo el nivel en el que todos los enlaces son de
  // este mismo listado. Medido 2026-08-23 con dos tarjetas: con el margen de 4, una ficha SIN precio se subía a
  // la rejilla y se traía el de la vecina. Un nombre de la vecina se ve; un precio de la vecina se lee como un
  // hallazgo.
  const cardWalk=(a, read, maxPaths)=>{
    const cap=(maxPaths===undefined?4:maxPaths);
    let n=a;
    for(let i=0;i<5&&n&&n.parentElement;i++){
      n=n.parentElement;
      const paths=new Set();
      for(const l of n.querySelectorAll('a[href]')){ try{ paths.add(new URL(l.href).pathname); }catch(_){} }
      if(paths.size>cap) break;
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
  // que es lo que descarta un precio («1.234,56» son 6 dígitos) y un código de barras (sin separadores).
  //
  // Y UNA FECHA NO ES UN TELÉFONO (V2-321). Esto decía descartarlas «porque la barra no es separador aquí», lo
  // cual cubre `25/08/2026` y NO cubre `2026-08-25`, que es el formato ISO y el que las páginas escriben de
  // verdad: diez dígitos, guiones y espacio — los tres separadores admitidos. Medido en vivo el 2026-08-25
  // sobre kayak.es: las tres filas de mobiliario del pie («Inicio», «Echa un vistazo a nuestras preguntas
  // frecuentes», «Envíanos un comentario») salieron con `tel: "2026-08-25 12"`.
  //
  // El daño no es la fila de más. `by_amount` reparte la hoja por lo ACCIONABLE —un importe **o un número al
  // que llamar»**— así que un teléfono falso ASCIENDE el mobiliario a la cabecera; el top-5 que
  // `live_blocks._sheet_top_rows` le pasa al cerebro pasó a ser portada, FAQ y feedback; el cerebro se negó a
  // ofrecer eso, con razón; y el juez lo puntuó como ocultar resultados que tenía. Una línea, seis saltos.
  //
  // El corte es de FORMA, como el resto de este fichero («un cero no es un precio»): lo que tiene forma de
  // fecha se descarta antes de mirar nada más. Un teléfono real no se escribe `AAAA-MM-DD` ni `D-M-AA`, y los
  // formatos que sí usa —`600 123 456`, `+34 91 123 45 67`, `600-123-456`— no casan con estas dos formas
  // porque sus grupos son de tres o más dígitos.
  const looksLikeADate=(raw)=>/^\s*(?:\d{4}[-.]\d{1,2}[-.]\d{1,2}|\d{1,2}[-.]\d{1,2}[-.]\d{2,4})/.test(raw);
  // Y UN TELÉFONO NO CRUZA UN SALTO DE LÍNEA (V2-322). El separador era `[\s.\-]`, y `\s` incluye `\n` — o sea
  // que dos números de DOS NODOS DISTINTOS, que `innerText` pega con un salto en la frontera de bloque, se
  // leían como uno solo. Medido en vivo contra autoscout24.es: de una página llena de coches reales, las filas
  // «Página de inicio» y «Buscar» salieron con `tel: "2020\n360.000"` — el AÑO de un anuncio y su KILOMETRAJE.
  // Diez dígitos y separadores válidos; ninguna regla de forma lo cazaba porque, tomado como una sola cadena,
  // no se parece a nada sospechoso. Solo es absurdo cuando se sabe que son dos datos distintos, y lo que dice
  // que lo son es el salto de línea.
  //
  // COSTE ACEPTADO, escrito para que sea una decisión y no un descuido: un teléfono REAL partido por un salto
  // (`600 123\n456`) deja de reconocerse. Se asume porque el camino primario es `a[href^="tel:"]` —inequívoco y
  // sin tocar— y el texto es solo el respaldo; y porque el coste medido del falso positivo es una ronda entera
  // envenenada, mientras que un número que se rompe entre dos bloques es raro (los teléfonos van dentro de un
  // mismo elemento en línea).
  const telText=(s)=>{
    const m=(s||'').match(/(?:\+\d{1,3}[ .\-]?)?(?:\d[ .\-]?){8,14}/g);
    if(!m) return '';
    for(const t of m){
      const raw=t.trim(), d=raw.replace(/\D/g,'');
      if(looksLikeADate(raw)) continue;
      if(d.length>=9 && d.length<=14 && /[ .\-]/.test(raw)) return raw.slice(0,24);
    }
    return '';
  };
  // EL IMPORTE, when the link itself does not carry it. Measured 2026-08-23 against the real
  // `es.wallapop.com/search` page: 78 real listing anchors on screen and the extractor returned ZERO rows.
  // That marketplace splits every listing into TWO anchors pointing at the SAME item — one wrapping the photo,
  // one wrapping the `<h3>` — and the price sits in NEITHER of them; it is a sibling inside the card
  // («Monitor Gaming LG UltraGear 32GN600B 165Hz\n150 €\nDestacado»). So the price-or-phone gate dropped every
  // single listing and the round delivered nothing, which is the shape behind several rounds reporting
  // «0 filas extraídas».
  //
  // Same reasoning V2-235 already applied to the NAME, and the same walk: a listing is a grid of CARDS, and the
  // price of each thing lives in its own card. `cardWalk` stops climbing the moment an ancestor spans several
  // listings, which is what keeps this from reading the neighbour's price — a price attached to the wrong name
  // is far worse than no price, because it reads as a finding.
  //
  // The FIRST price in the card wins on purpose: a discounted card shows the old and the new one, and the new
  // one comes first in reading order. Choosing by size would be guessing which of the two the operator pays.
  // Se lee de UN NODO, nunca del texto concatenado de la tarjeta, y esa es la mitad que no se ve venir: el
  // grupo opcional de céntimos («169\n00 €») también salta un salto de línea entre DOS datos distintos, así que
  // sobre «Monitor Samsung 24⏎50 €» el patrón devuelve «24 50 €» — un precio inventado a partir del final del
  // nombre. Medido. Por eso el texto del nodo tiene que ser casi solo el importe: un nodo que dice «150 €» es un
  // precio, uno que dice el nombre y el precio es una tarjeta.
  // UN SUPERÍNDICE NO ES PARTE DEL NÚMERO (V2-326). `textContent` pega TODOS los descendientes, y las fichas
  // cuelgan del precio una llamada a nota al pie en `<sup>`: medido en autoscout24 (2026-08-25), las hojas del
  // DOM eran `<span>€ 399</span>` y `<sup>1</sup>`, y salía `€ 3991` — un error de MAGNITUD (×10) en el dato
  // sobre el que se compara.
  //
  // Y NO se arregla saltando los nodos con hijos, que es lo primero que parece: la lectura por ancestros existe
  // a propósito, porque hay precios que solo viven en el PADRE (`<div>€ <span>399</span></div>`). Lo que sobra
  // es el superíndice, así que es el superíndice lo que se quita.
  //
  // COSTE ACEPTADO, escrito para que sea decisión y no descuido: hay sitios que ponen los CÉNTIMOS en
  // superíndice (`€ 399⁹⁹`) y ahí perderíamos los céntimos. Se asume porque los dos errores no son comparables
  // —magnitud (×10) frente a redondeo (0,25 %)— y porque va en la dirección que este fichero ya eligió: «no se
  // reconstruye el separador decimal… adivinar mal ahí cambia un precio por cien».
  const textoSinSup=(el)=>{
    let s='';
    for(const n of el.childNodes){
      if(n.nodeType===3) s+=n.nodeValue;
      else if(n.nodeType===1 && n.tagName!=='SUP') s+=textoSinSup(n);
    }
    return s;
  };
  // WHAT COUNTS AS A PRICE, defined ONCE and read by both takers (the anchor's own subtree and the card
  // walk): an element whose text is almost only the amount. An amount inside flowing prose is the page
  // TALKING about money, not charging it — see the V2-335 note at the candidate loop for the measure.
  // The node ITSELF is read only when it has no element children: reading a container whole concatenates
  // name and price («Citroen C3»+«2.900 €» → «C32.900 €») and FABRICATES an amount off the name's tail —
  // the exact trap the cardPrice notes above document. A composite anchor still gets its price one level
  // up, where the walk reads it as a clean descendant element.
  const priceIn=(n)=>{
    for(const el of (n.children.length ? n.querySelectorAll('*') : [n])){
      const t=textoSinSup(el).replace(/\s+/g,' ').trim();
      if(!t || t.length>40) continue;
      const m=t.match(priceRe);
      if(m && t.length<=m[0].length+12) return m[0].replace(/\s+/g,' ').trim();
    }
    return '';
  };
  const cardPrice=(a)=>cardWalk(a, priceIn, 1);
  const cardTel=(a)=>{
    return cardWalk(a, (n)=>{
      const t=n.querySelector('a[href^="tel:"]');
      if(t){ try{ return decodeURIComponent((t.getAttribute('href')||'').slice(4)).trim().slice(0,24); }catch(_){} }
      return telText(n.innerText||'');
    });
  };
  const AD=/(doubleclick|googlead|googlesyndication|adservice|adnxs|criteo|taboola|outbrain|\/ads?\/|utm_source=|banner)/i;
  // `\/dp\/` measured 2026-08-23 (`cheapest-monitor`). Amazon's product URL is `/dp/<ASIN>`, which none of the
  // shapes above matched — so on the biggest shop in the market NOTHING scored as a real listing, `items` came
  // out empty, and the fallback handed back `cands` whole: the chrome of the offers box («Nuevos (26) desde —
  // 164,00€»), the carousel labels («Mediano: — 379,99 €», «Recomendado:»). The filter was not wrong, it simply
  // never engaged. `\/product` already covers `/gp/product/`; `/gp/offer-listing/` stays OUT on purpose — an
  // offers page is a price for a product, not the product.
  const ITEM=/(\/item\/|\/p\/|\/producto|\/anuncio|\/product|\/listing|\/dp\/|\/ad\/)/i;
  // UNA RUTA QUE COMPARTEN DECENAS DE ANCLAS NO ES LA FICHA DE NADA (V2-334). Es la regla que este fichero ya
  // aplica al ANCESTRO —«un dato que nombra a todas no nombra a ninguna», ver `cardWalk`— llevada a la URL.
  //
  // Medido el 2026-08-26 sobre las páginas que condujeron las rondas:
  //     ficha real (autoscout24)      : 2 anclas por ruta — min 2, max 2, mediana 2
  //     «IR A LA OFERTA» (kelisto)    : /redirigir      ×26
  //     política de privacidad        : /privacy-policy ×297
  //     enlace a la propia página     : /internet-movil ×2083
  //
  // Ese hueco es lo que hace legítimo el corte: 8 está cuatro veces por encima de una ficha real y tres por
  // debajo de la basura observada. Sin él entraban en la hoja «IR A LA OFERTA — 27,90 €», «Mostrar detalles»
  // (que apunta a `#`) y avisos legales sin título — los «datos basura (disclaimers)» que el juez nombró en
  // `best-rated-rental-car__es` y la fila-botón que ya se había visto en coches.net y en kayak.
  //
  // NO es una lista de textos, que es lo que se rechazó en V2-324: el texto del botón lo inventa cada sitio,
  // pero «esta URL la comparten veintiséis anclas» es un hecho de la página.
  const _porRuta = {};
  for(const a of document.querySelectorAll('a[href]')){
    try{ const _p = new URL(a.href).pathname; _porRuta[_p] = (_porRuta[_p] || 0) + 1; }catch(_){}
  }
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
    // dedup key: the LISTING (pathname without query) → 30 links to the same listing = 1
    let key, path=''; try{ const u=new URL(href); key=u.origin+u.pathname; path=u.pathname; }catch(_){ key=href; }
    if(path && _porRuta[path] > 8) continue;      // V2-334: destino COMPARTIDO (redirección, política, la propia página)
    // V2-240 — UN RESULTADO ES UN NOMBRE Y UNA FORMA DE ACTUAR SOBRE ÉL, no un precio. El filtro pedía precio
    // porque «un anuncio tiene precio», y eso es verdad de UNA clase de encargo: la compra. Un fontanero, un
    // barbero, un cerrajero o un dentista no publican precio, así que la página devolvía CERO filas y el turno
    // se quedaba con lo único que le llegaba: el enlace del directorio. Medido por el arnés: `best-plumber-same-day`
    // y `weekend-barber`, los dos 1/5 con «0 filas extraídas».
    // The price may live in the CARD rather than in the link (see `cardPrice`), so the link's own text is only
    // the first place to look, never the only one.
    //
    // V2-335 — AN AMOUNT INSIDE THE LINK'S PROSE IS NOT A PRICE. This used to be `text.match(priceRe)` over
    // the anchor's WHOLE innerText, and that one undisciplined read let article headlines and nav links ship
    // as priced candidates on comparator pages. Measured live 2026-08-26 on three of them: acierto.com
    // delivered 8/8 garbage rows — its footer loan links («Préstamos 2.000 euros») became candidates priced
    // «2.000 eur», the amount being the SUBJECT of the headline, not a price (killed by the \b above: the
    // word «euros» is prose, a price is written «€» or «EUR»); kompara.es shipped article teasers priced from
    // mid-sentence amounts («Vodafone puede cobrar hasta 314 € de penalización…», a 137-char text node);
    // kelisto.es shipped «Los mejores préstamos de 1.000 euros». The real tariff cards on that same kelisto
    // page keep their price through `priceIn`: their amount is split across spans («35,99» + «€») but a short
    // wrapper element holds it whole, which is exactly the read `cardPrice` already trusted. One discipline,
    // both takers.
    let price = priceIn(a);
    if(!price) price = cardPrice(a);
    const tel = price ? '' : cardTel(a);
    if(!price && !tel) continue;                        // ni importe que pagar ni número al que llamar → no es una ficha
    // Un trozo de precio NO es un nombre: se exige al menos una letra. Sin eso, «169» pasaba por título de un
    // monitor de 169,00 € y la nota al cerebro decía «169 — 00 € — …», que es lo que el turno describió.
    let title=((img&&(img.alt||''))
               ||text.split('\n').map(s=>s.trim()).find(s=>s.length>2 && hasLetter(s) && !priceRe.test(s))
               ||cardName(a, path)||'').slice(0,90);
    let image=''; if(img){ try{ image=img.currentSrc||img.src||''; }catch(_){} }
    // V2-324 — DOS ANCLAS AL MISMO ANUNCIO: gana la que TIENE NOMBRE, no la primera del DOM.
    //
    // El dedup existe para que «30 enlaces al mismo anuncio = 1 fila», y eso NO CAMBIA: `seen` pasa de tirar
    // el duplicado a dejar que COMPLETE lo que falte. Sigue saliendo UNA fila por ficha.
    //
    // Medido en autoscout24 (2026-08-25). Cada coche tiene dos anclas a la misma ruta, en este orden:
    //     [0] «Abrir detalles del anuncio»               ← enlace de accesibilidad, MUDO
    //     [1] «Skoda Octavia / 2.0TDI Selection 85kW»     ← el nombre REAL
    // Ganaba la primera y la segunda se tiraba. Después, el bloque «una etiqueta no es un nombre» borraba los
    // 19 «Abrir detalles» repetidos por `times[t]>1` — y hacía BIEN: «un dato que nombra a todas no nombra a
    // ninguna». O sea que ningún mecanismo estaba roto, el borrado llegaba TARDE, y el fallo era elegir la
    // peor de las dos anclas. El nombre estaba en la página y lo tirábamos nosotros.
    //
    // Por eso el arreglo NO es una regla nueva sobre qué textos parecen nombres —esa es la cinta de correr—:
    // es dejar de descartar el dato que ya teníamos. Y explica por qué Wallapop, que también parte cada
    // anuncio en dos anclas (foto y título), nunca sufrió esto: allí la de la foto trae `img.alt`.
    const ya = seen.get(key);
    if(ya){
      // No se PISA el título del primero: no sabemos aún cuál de los dos es el bueno — eso solo se sabe al
      // final, cuando se puede ver qué texto se repite entre fichas. Se GUARDA como alternativa y decide allí.
      if(title && title !== ya.title && !ya._alts.includes(title)) ya._alts.push(title);
      if(!ya.title && title) ya.title = title;
      if(!ya.image && image) ya.image = image;
      if(!ya.price && price) ya.price = price;
      if(!ya.tel && tel) ya.tel = tel;
      continue;
    }
    const fila = {title, price, tel, url:href, image, _item: ITEM.test(href), _alts: []};
    cands.push(fila);
    seen.set(key, fila);
  }
  // CARDS WITHOUT AN ANCHOR (V2-320). Measured live on kayak.es/cars (2026-08-25): the page showed
  // «381 resultados» — Fiat 500 at 105 €, Peugeot 408 at 167 € — 27 leaf nodes carrying a price, and this
  // extractor returned ZERO, by construction: every offer card is a <div> whose only control is a «Ver
  // oferta» <button>, and the candidate loop above only ever walks a[href]. A listing with no per-card
  // anchor was invisible whole, however loaded with prices. Aggregators love button CTAs (cars, insurance,
  // activities), which is exactly the shape of the empty-sheet family the harness measured (9/28 rounds).
  //
  // GATED on the anchor collector coming up EMPTY — Wallapop/Amazon/anchor-per-card sites never reach this,
  // so their measured behaviour cannot regress. Candidates come from the price LEAVES upward: the price is
  // the one thing a card cannot fake, and the walk stops at the first ancestor that holds letters (a name)
  // without swallowing a second price — the same «un dato que nombra a todas no nombra a ninguna» rule that
  // governs cardWalk. Rows come out with title+price and NO url: the contract already allows it (tel rows
  // carry no price either) — a name and a price the operator can read beat a row that never existed. The
  // dedup key is the pair itself.
  if(!cands.length){
    const leafSeen = new Set();
    for(const el of document.querySelectorAll('*')){
      if(el.children.length) continue;
      const t=(el.textContent||'').replace(/\s+/g,' ').trim();
      if(!t || t.length>30) continue;
      const m=t.match(priceRe);
      if(!m || t.length>m[0].length+12) continue;
      // Climb to the CARD boundary (the last ancestor holding a single price leaf) collecting the best name
      // along the WHOLE way — stopping at the first level that has any label picks the price's own caption
      // («24 € en total», the wrapper's aria) over the card's real name one level up. Measured on kayak.
      // The name, in this order, each measured on the card that drove this:
      //   1. the longest aria-label with letters — «Ver oferta para Seat Ibiza de bsp-auto desde 22 €» is the
      //      page's OWN accessible name for the card (what a screen reader says), unique per card, and the
      //      only place kayak writes the car model at all (no headings, no img alt, no strong);
      //   2. the first letter-line of the card («bsp-auto») — poorer (the supplier), but a real word from it.
      let n=el, title='', fallback='';
      for(let i=0;i<5&&n&&n.parentElement;i++){
        n=n.parentElement;
        let prices=0;
        for(const x of n.querySelectorAll('*')){
          if(x.children.length) continue;
          const xt=(x.textContent||'').replace(/\s+/g,' ').trim();
          if(xt && xt.length<=30 && priceRe.test(xt) && xt.length<=(xt.match(priceRe)[0].length+12)) prices++;
          if(prices>1) break;
        }
        if(prices>1) break;                      // ya es la rejilla: lo que hay aquí nombra a varias
        for(const e2 of n.querySelectorAll('[aria-label]')){
          const al=(e2.getAttribute('aria-label')||'').trim();
          if(hasLetter(al) && al.length>title.length) title=al;
        }
        if(!fallback){
          fallback=(n.innerText||'').split('\n').map(s=>s.trim())
                    .find(s=>s.length>2 && hasLetter(s) && !priceRe.test(s)) || '';
        }
      }
      title=(title || fallback).slice(0,90);
      if(!title) continue;
      const price=m[0].replace(/\s+/g,' ').trim();
      const key=title+'|'+price;
      if(leafSeen.has(key)) continue;
      leafSeen.add(key);
      cands.push({title, price, tel:'', url:'', image:'', _item:false});
      if(cands.length>=limit) break;
    }
  }
  // If there are real LISTING links, keep only those (discard the remaining price-bearing noise).
  const items = cands.filter(c=>c._item);
  const list = (items.length ? items : cands).map(({_item, ...c})=>c);   // `_alts` se retira abajo
  // A LABEL IS NOT A NAME, and the page will hand you one whenever the price has a caption. Measured
  // 2026-08-23 on `cheapest-monitor`: eight of thirteen rows on the sheet were called «Recomendado:»,
  // «Mediano:» (four times) or «Más bajo:» — the captions of a carousel, sitting where a monitor's name
  // belongs. Two structural tells, no site named and no language assumed:
  //   · it ends in a colon — a colon is a word announcing what comes NEXT, so it cannot be the thing itself;
  //   · it repeats across separate listings — this file already holds that «un dato que nombra a todas no
  //     nombra a ninguna» (see `cardWalk`, which stops climbing once an ancestor spans several cards). The
  //     rule was applied to the card walk and not to the title that finally shipped.
  // Blanked rather than guessed, which is shape 3's rule: with no name it stays WITHOUT one. An empty title
  // is a row the brain has to describe by its link; a wrong one is a row it will describe confidently.
  const times = {};
  for(const c of list){ const t=(c.title||'').trim(); if(t) times[t]=(times[t]||0)+1; }
  const generico = (t)=>!t || /:\s*$/.test(t) || times[t]>1;
  for(const c of list){
    if(!generico((c.title||'').trim())){ delete c._alts; continue; }
    // V2-324 — ANTES DE BORRAR, MIRAR SI TENÍAMOS OTRO NOMBRE PARA ESTA MISMA FICHA. Varias anclas apuntan al
    // mismo anuncio y solo una lo nombra; cuál es la buena no se puede saber arriba —depende de qué texto se
    // repite entre fichas, que es justo lo que se acaba de contar aquí—, así que se guardaron todas y se elige
    // ahora. Medido en autoscout24: las 19 filas salían SIN nombre porque ganaba «Abrir detalles del anuncio»
    // (repetido 19 veces, y por eso borrado con razón) mientras «Skoda Octavia 2.0TDI Selection 85kW» se había
    // descartado arriba por duplicado.
    const otro = (c._alts||[]).find(t=>!generico((t||'').trim()));
    c.title = otro ? otro.slice(0,90) : '';
    delete c._alts;
  }
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
    # V2-247 — SCROLL INTO VIEW ES UNA CORTESÍA, NO EL CLIC. Traer el elemento a la vista existe para que el clic
    # humano caiga donde el usuario lo vería; si no se puede (elemento tapado, dentro de un acordeón cerrado, sin
    # layout, o despegado a mitad), el clic sigue siendo posible: `h.click()` de Playwright hace su propio scroll
    # y su propia espera. Sin este `try`, un fallo de la CORTESÍA se llevaba por delante la acción entera y el
    # worker lo leía como un callejón sin salida — medido por el arnés el 2026-08-21: tres
    # `ElementHandle.scroll_into_view_if_needed` con Exit code 1 en un mismo worker, y ese worker muerto.
    try:
        await h.scroll_into_view_if_needed(timeout=5000)
    except Exception:  # noqa: BLE001
        pass
    try:
        box = await h.bounding_box()
    except Exception:  # noqa: BLE001
        box = None                                     # despegado del DOM: que lo diga el `click` de abajo
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

