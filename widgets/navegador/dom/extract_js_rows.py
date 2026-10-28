"""The second half of the in-page listing extractor's text (`dom/extract_js.py` joins both halves into
`_JS_EXTRACT`): the walk over the page's links, the ad/listing filter, and the rows it returns."""

_JS_EXTRACT_ROWS = r"""  const AD=/(doubleclick|googlead|googlesyndication|adservice|adnxs|criteo|taboola|outbrain|\/ads?\/|utm_source=|banner)/i;
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
    // A `tel:` (or `mailto:`) is a way to CONTACT the listing, not the listing itself. Without this, a business
    // card appeared TWICE—once for its link and once for its phone—and in a directory that duplicates the page.
    if(/^(tel:|mailto:|sms:)/i.test(href)) continue;
    if(a.closest('ins, iframe, [class*="ad-" i], [id*="google_ads" i], [aria-label*="anuncio" i]')) continue;
    const img=a.querySelector('img');
    const text=(a.innerText||'').trim();
    // dedup key: the LISTING (pathname without query) → 30 links to the same listing = 1
    let key, path=''; try{ const u=new URL(href); key=u.origin+u.pathname; path=u.pathname; }catch(_){ key=href; }
    if(path && _porRuta[path] > 8) continue;      // V2-334: SHARED destination (redirect, policy, or the page itself)
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
    if(!price && !tel) continue;                        // neither an amount to pay nor a number to call → not a listing
    // A price fragment is NOT a name: require at least one letter. Otherwise «169» became the title of a
    // €169.00 monitor and the note to the model said «169 — 00 € — …», exactly what the run described.
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
        if(prices>1) break;                      // this is already the grid: anything here names several listings
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
  const list = (items.length ? items : cands).map(({_item, ...c})=>c);   // `_alts` is removed below
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
    // V2-324 — BEFORE CLEARING, CHECK WHETHER WE HAVE ANOTHER NAME FOR THIS SAME LISTING. Several anchors point
    // to the same listing and only one names it; which one is correct cannot be known above—it depends on which
    // text repeats across listings, counted just here—so all were saved and the choice is made now. On autoscout24,
    // the 19 rows had no name because «Abrir detalles del anuncio» won (repeated 19 times and rightly cleared),
    // while «Skoda Octavia 2.0TDI Selection 85kW» had been discarded above as a duplicate.
    const otro = (c._alts||[]).find(t=>!generico((t||'').trim()));
    c.title = otro ? otro.slice(0,90) : '';
    delete c._alts;
  }
  return list.slice(0, limit);
}
"""

