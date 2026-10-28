"""The in-page extractor of real LISTINGS from a results grid (`_JS_EXTRACT`), moved out of `dom.py`.

It is ONE arrow function run in the page. Its text is held in two literals joined back into the same string: the
card helpers (name, price, phone) here, the walk over the page's links and the row filter in `extract_js_rows.py`.
"""
from __future__ import annotations

from widgets.navegador.dom.extract_js_rows import _JS_EXTRACT_ROWS

# Extractor for real LISTINGS from a results grid (runs in the page) → {title,price,tel,url,image}.
# Hardened (TASK 4): REQUIRE an actionable datum (see V2-240 — it used to require a PRICE, which is what a
# SHOPPING errand leaves behind and nothing else does), EXCLUDE ads/tracking
# (doubleclick/googleads/.../campaign utm), and **dedup by LISTING** (same /item/ or same pathname → 1 only, so
# 30 links to the same listing collapse into one). Prioritize listing links (/item/, /p/, /producto, /anuncio).
# The FINE relevance filtering (this is an enduro bike, not a "Moto G" phone) is done by the model in summarize.
_JS_EXTRACT_HELPERS = r"""
(limit) => {
  const out=[], seen=new Map();   // listing key → ITS ROW (V2-324: keep the second complete anchor)
  // La COMA es el separador decimal en media Europa, y faltaba de la clase de caracteres: sobre «169,00 €» el
  // patrón viejo empezaba a casar en «00» y devolvía «00 €», o sea un monitor de 169 € anunciado como de 0 €.
  // Medido el 2026-08-21 sobre una tarjeta con la forma de Amazon (precio partido en spans, con el importe
  // completo repetido en un nodo fuera de pantalla): title:"" price:"00 €" en las dos filas.
  // …y el ENTERO y los CÉNTIMOS pueden venir en nodos distintos, que `innerText` separa con un salto de línea
  // («169\n00 €»): sin el grupo opcional, el patrón empezaba a casar en «00» y se dejaba fuera el 169.
  // NO se reconstruye el separador decimal: se colapsa el espacio y se entrega «169 00 €» tal cual. Meter una
  // coma sería adivinar —hay sitios que separan los MILES con espacio («1 234 €»)— y adivinar mal ahí cambia
  // un precio por cien. Lo que se ve es lo que la página puso; el nombre y el enlace acompañan al importe.
  // V2-776 — the pattern knew ONE currency. On a US store («$249.99», eBay's «US $199.00») no node was a price,
  // so `extract` answered 0 rows on Newegg and a priceless row on eBay, and the monitors worker of the v2 demo
  // spent eight minutes hunting for a page the tool could read (2026-09-30). Dollar and pound join the euro;
  // the amount grammar is unchanged.
  const priceRe=/(\d[\d.,]{0,12}(?:\s\d{1,2})?\s*[€£])|([€£$]\s*\d[\d.,]{0,12})|(\d[\d.,]{0,12}\s?(EUR|eur|USD|usd|GBP|gbp)\b)/;
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
  const cardWalk=(a, read, maxPaths, itemBound)=>{
    const cap=(maxPaths===undefined?4:maxPaths);
    // V2-347 — RUTAS no es FICHAS. Measured on the saved autoscout24.es listing (2026-08-26): the card is an
    // <article> holding exactly TWO paths — the listing («/anuncios/…», twice: accessibility anchor + naming
    // anchor) and the DEALER («/profesionales/…») — with the price node «€ 11.900» right there at level 1.
    // maxPaths=1 read «2 paths» as «this spans two cards» and broke the walk at the FIRST level, so no listing
    // ever got a price, every anchored candidate died, and the price-leaf fallback shipped 12 rows titled with
    // the dealer link and NO url — the worker could not open a single detail page and degraded to reading
    // screenshots (~14 s per cycle). The boundary the 2026-08-23 measurement actually needed is «a level that
    // spans several LISTINGS», so when the anchor ITSELF is listing-class (ITEM), only listing-class paths
    // count toward the cap: the dealer/chrome link no longer closes the card, and the grid (19+ listing paths
    // one level up) still breaks the walk exactly as before. Non-ITEM anchors keep the raw count — on pages
    // like kelisto the price already lives INSIDE the anchor (`priceIn`) and the walk stays conservative.
    let mine=''; try{ mine=new URL(a.href).pathname; }catch(_){}
    const scoped = !!itemBound && ITEM.test(mine);
    let n=a;
    for(let i=0;i<5&&n&&n.parentElement;i++){
      n=n.parentElement;
      const paths=new Set();
      for(const l of n.querySelectorAll('a[href]')){
        try{ const p=new URL(l.href).pathname; if(!scoped || ITEM.test(p)) paths.add(p); }catch(_){}
      }
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
      // A heading pointing to THIS same listing is the strong signal that it names this one, not its neighbor.
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
  const cardPrice=(a)=>cardWalk(a, priceIn, 1, true);   // V2-347: the price cap counts LISTINGS, not links
  const cardTel=(a)=>{
    return cardWalk(a, (n)=>{
      const t=n.querySelector('a[href^="tel:"]');
      if(t){ try{ return decodeURIComponent((t.getAttribute('href')||'').slice(4)).trim().slice(0,24); }catch(_){} }
      return telText(n.innerText||'');
    });
  };
"""

_JS_EXTRACT = _JS_EXTRACT_HELPERS + _JS_EXTRACT_ROWS
