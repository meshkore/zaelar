// Results widget — LA SUPERFICIE GENÉRICA donde zaelar enseña lo que ha encontrado. La rellena quien hizo el
// trabajo (un Brain Worker, el navegador, el cerebro) con acciones declaradas; esto solo PINTA. Nunca busca nada.
//
// CUATRO PESTAÑAS (2026-08-12) — porque una búsqueda compleja no es solo su resultado:
//   · RESULTADOS — las fichas, y el expediente completo de una al abrirla (segunda página, con su "volver").
//   · SUMARIO    — en qué punto va, cuántos candidatos ha explorado, cuántos quedan, y qué ha hecho.
//   · FUENTES    — en qué webs ha entrado y QUÉ PASÓ en cada una (entró · le limitaron a 50 · pedía login · error).
//   · CRITERIOS  — el encargo tal y como se está ejecutando, con las correcciones que el operador fue soltando.
// La pestaña activa vive en el payload PERSISTIDO (como `view`/`focus`), no en una variable de este fichero: por
// eso «enséñame de dónde has sacado esto» —una frase de voz, que llega por el cerebro— mueve la pantalla, y por
// eso la hoja sobrevive a un re-render, a reconectar y a reiniciar. El clic local se pinta YA y además persiste,
// así que la pestaña no parpadea esperando al servidor pero tampoco se pierde.
//
// FICHA DINÁMICA. Un barco no se lee como un paper ni como un correo: además de los campos fijos, un item puede
// traer `blocks` — una lista de piezas de composición de vocabulario CERRADO (text · facts · chips · gallery ·
// meter · table · link · section). Es la libertad de "una ficha HTML distinta por tipo de resultado" SIN aceptar
// HTML de un tercero: este payload viene de la web abierta, y todo se pinta con textContent.
//
// ANCHO FLUIDO. La hoja ya no tiene ancho propio (antes: 620px fijos, así que ponerla a pantalla completa dejaba
// una columna estrecha en medio de la pantalla). Ocupa el 100% de su tarjeta y el reparto en columnas lo hace el
// CSS por el ANCHO REAL disponible — con un mínimo por tipo de tarjeta y un TOPE de columnas, así que ni se
// estrangula al encogerla ni se convierte en ocho columnas de confeti al maximizarla.
//
// SECURITY: item text is web/3rd-party-sourced → built with textContent ONLY (never innerHTML).

const TABS = [
  {id: "results",  label: "Resultados"},
  {id: "summary",  label: "Sumario"},
  {id: "sources",  label: "Fuentes"},
  {id: "criteria", label: "Criterios"},
];

// Estado de una fuente → cómo se dice y de qué color. El vocabulario es cerrado en el backend; aquí solo se
// traduce. La distinción importa: «no pude entrar» y «entré pero me cortó a 50» son resultados MUY distintos.
const SOURCE_STATUS = {
  ok:      {label: "Entró",              cls: "ok"},
  partial: {label: "Entró con límite",   cls: "warn"},
  auth:    {label: "Pedía autenticación", cls: "warn"},
  blocked: {label: "Acceso bloqueado",   cls: "bad"},
  error:   {label: "Error",              cls: "bad"},
  pending: {label: "En curso",           cls: "idle"},
};

const CRIT_SECTIONS = [
  {key: "hard",        label: "Criterios duros",     note: "incumplirlos descalifica"},
  {key: "soft",        label: "Preferencias",        note: "puntúan, no descalifican"},
  {key: "enrichments", label: "Añadido por criterio propio", note: ""},
  {key: "assumed",     label: "Datos asumidos",      note: "no los dijiste — corrígelos si no van"},
  {key: "quality_bar", label: "Baremo de calidad",   note: "qué hay que verificar de verdad"},
  {key: "changes",     label: "Tus correcciones",    note: "lo que fuiste ajustando por el camino"},
];

function injectStyles(){
  if(document.getElementById("hb-results-css"))return;
  const s=document.createElement("style"); s.id="hb-results-css"; s.textContent=`
  /* ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
     SISTEMA, no números sueltos. La versión anterior acumulaba trece tamaños de letra (10.5, 11, 11.5, 12, 12.5,
     13, 13.5, 14, 15, 15.5, 18, 21…) y márgenes de 3, 5, 6, 7, 8, 9, 10, 11px elegidos uno a uno: eso no se lee
     como una superficie, se lee como parches. Aquí hay UNA escala tipográfica de cuatro pasos y UNA rejilla de
     espaciado de 4px, en variables locales, así que todo cae en el mismo ritmo y un cambio de densidad es una
     línea. El resto del CSS ya no lleva magnitudes crudas.
     Los COLORES son todos del contrato --hb-* del tema (nunca hex): la tarjeta se repinta sola al cambiar de tema.
     OJO al editar: esto es un template literal — nada de acentos graves aquí dentro.
     ───────────────────────────────────────────────────────────────────────────────────────────────────────────── */
  .hb-results{
    --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px;      /* rejilla de 4 */
    --f-micro:10.5px;                                          /* rótulos en versal, con tracking */
    --f-sm:11.5px;                                             /* metadatos, estados */
    --f-body:12.5px;                                           /* el cuerpo de todo */
    --f-md:14px;                                               /* título de ficha */
    --f-lg:17px; --f-xl:21px;                                  /* expediente y cifras del sumario */
    --r-sm:7px; --r-md:10px; --r-lg:13px; --r-pill:99px;       /* radios */
    --line:1px solid var(--hb-line,#e3e8f0);
    font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    color:var(--hb-ink,#0d1622);font-size:var(--f-body);line-height:1.45;
    width:100%;min-width:0;display:flex;flex-direction:column}
  /* Toda cifra que se COMPARA va en cifras tabulares. En una superficie cuyo trabajo es poner precios y notas
     unos debajo de otros, dígitos de anchura distinta obligan a releer para saber cuál es mayor. */
  .hb-results .hr-price,.hb-results .hr-score,.hb-results .hr-pp,.hb-results .hr-n,
  .hb-results .hr-stat b,.hb-results .hr-sn,.hb-results .hr-tbl td,.hb-results .hr-dprice{
    font-variant-numeric:tabular-nums}
  .hb-results .hr-bt,.hb-results .hr-cgt,.hb-results .hr-pk,.hb-results .hr-stat span{
    font-size:var(--f-micro);font-weight:700;letter-spacing:.06em;text-transform:uppercase;
    color:var(--hb-muted-2,#9aa7b8)}

  /* ── CABECERA FIJA ──────────────────────────────────────────────────────────────────────────────────────────
     Una hoja de diez resultados se recorre con scroll, y con la cabecera en el flujo las pestañas se iban por
     arriba justo cuando más falta hacen (mirar la última ficha y saltar a Fuentes). El scroll lo pone la tarjeta
     (.hb-scroll del canvas); aquí solo nos pegamos a su borde. El fondo OPACO no es decoración: sin él las fichas
     se leerían por debajo del título al desplazar. */
  .hb-results .hr-top{position:sticky;top:0;z-index:5;background:var(--hb-bg,#fff);
    padding-top:2px;margin:-2px 0 0}
  .hb-results .hr-hd{font-size:var(--f-md);font-weight:650;letter-spacing:-.01em;margin:0;word-break:break-word}
  .hb-results .hr-sub{font-size:var(--f-sm);color:var(--hb-muted-2,#9aa7b8);margin:var(--s1) 0 0}
  /* Un subtítulo suelto dentro de un panel necesita aire POR DEBAJO: sin él, la línea de contexto («náutica de
     recreo · amplitud mínima 40») quedaba pegada al rótulo siguiente y se leían como una sola cosa. */
  .hb-results .hr-panel>.hr-sub{margin-bottom:var(--s4)}
  .hb-results .hr-panel>.hr-why{margin-bottom:var(--s4)}

  /* ── PESTAÑAS ── el subrayado activo hace de continuación de la línea inferior, no de caja aparte. */
  .hb-results .hr-tabs{display:flex;gap:2px;border-bottom:var(--line);margin:var(--s3) 0 var(--s4);
    overflow-x:auto;scrollbar-width:none}
  .hb-results .hr-tabs::-webkit-scrollbar{display:none}
  .hb-results .hr-tab{flex:none;display:inline-flex;align-items:center;gap:var(--s1);border:none;background:none;
    cursor:pointer;font:600 var(--f-body)/1 inherit;color:var(--hb-muted,#5f6b7c);
    padding:var(--s2) var(--s3) 9px;border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;
    transition:color .14s}
  .hb-results .hr-tab:hover{color:var(--hb-ink,#0d1622)}
  .hb-results .hr-tab.on{color:var(--hb-accent,#3D6FE0);border-bottom-color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-tab .hr-n{font-size:var(--f-micro);font-weight:700;padding:1.5px 6px;border-radius:var(--r-pill);
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5f6b7c);line-height:1.4}
  .hb-results .hr-tab.on .hr-n{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 16%,transparent);
    color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-tab .hr-n.bad{background:color-mix(in srgb,var(--hb-risk,#e5484d) 15%,transparent);
    color:var(--hb-risk,#e5484d)}

  /* ── REJILLA Y FICHAS ───────────────────────────────────────────────────────────────────────────────────────
     El filete de acento se queda SOLO en la destacada. Con diez resultados —el nuevo defecto de entrega— diez
     barras azules en vertical se leen como un código de barras y dejan de destacar nada: si todo grita, no grita
     nadie. Las demás llevan un hilo de 1px y se levantan al pasar por encima solo si el clic hace algo. */
  .hb-results .hr-grid{display:grid;gap:var(--s3);min-width:0}
  .hb-results .hr-grid + .hr-grid{margin-top:var(--s3)}
  .hb-results .hr-card{position:relative;display:block;text-decoration:none;color:inherit;
    border:var(--line);border-radius:var(--r-lg);padding:var(--s3) var(--s4);background:var(--hb-bg,#fff);
    min-width:0;transition:border-color .15s,box-shadow .15s,transform .15s}
  /* La destacada se marca con borde y fondo, y punto. Se probó además un filete de color asomando por arriba
     («pestaña de etiqueta»): con el radio de la tarjeta quedaba como un guion suelto FLOTANDO sobre el borde, o
     sea un defecto de maquetación. El fondo templado + el borde turquesa + su badge ya la distinguen de nueve
     hermanas; un adorno más no destacaba mejor, solo añadía algo que podía verse roto. */
  .hb-results .hr-card.primary{border-color:color-mix(in srgb,var(--hb-accent2,#16B8A6) 42%,var(--hb-line,#e3e8f0));
    background:var(--hb-bg-soft,#fbfdff)}
  .hb-results a.hr-card:hover,.hb-results .hr-card.choosable:hover{border-color:var(--hb-accent,#3D6FE0);
    box-shadow:var(--hb-shadow-1,0 8px 30px rgba(13,22,34,.12));transform:translateY(-1px)}
  .hb-results .hr-img{display:block;width:100%;height:128px;object-fit:cover;border-radius:var(--r-md);
    margin:0 0 var(--s3);background:var(--hb-bubble,#f1f4f9)}
  .hb-results .hr-card.primary .hr-img{height:168px}
  .hb-results .hr-head{display:flex;align-items:baseline;justify-content:space-between;gap:var(--s1) var(--s2);
    flex-wrap:wrap}
  .hb-results .hr-t{font-size:var(--f-md);font-weight:650;line-height:1.3;letter-spacing:-.01em;
    word-break:break-word;flex:1 1 8em;min-width:0}
  .hb-results .hr-card.primary .hr-t{font-size:15.5px}
  .hb-results .hr-price{flex:none;font-size:var(--f-md);font-weight:700;color:var(--hb-ink,#0d1622);
    white-space:nowrap;letter-spacing:-.01em}
  /* El subtítulo DEJA de ser turquesa y en negrita: competía con el precio por la atención y en una ficha solo
     puede haber un dato que gane. Es contexto, y el contexto se lee en segundo plano. */
  .hb-results .hr-s{font-size:var(--f-sm);color:var(--hb-muted,#5f6b7c)}
  /* Subtítulo y badge en la MISMA línea, alineados por su base: es la fila de metadatos del resultado. */
  .hb-results .hr-metarow{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s1) var(--s2);
    margin-top:5px}
  .hb-results .hr-ln{font-size:var(--f-body);color:var(--hb-muted,#5f6b7c);margin-top:var(--s1);
    overflow-wrap:break-word}
  .hb-results .hr-ln.strong{color:var(--hb-ink,#0d1622);font-weight:600}
  .hb-results .hr-ln.warn{color:var(--hb-warn-ink,#9a5b1b)}
  .hb-results .hr-badge{display:inline-block;font-size:var(--f-micro);font-weight:700;letter-spacing:.04em;
    text-transform:uppercase;color:var(--hb-accent,#3D6FE0);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 10%,transparent);
    border-radius:var(--r-sm);padding:2.5px 7px}
  .hb-results .hr-empty{color:var(--hb-muted,#5f6b7c);font-size:var(--f-body);padding:var(--s5) 0;
    max-width:52ch;line-height:1.6}
  .hb-results .hr-card.chosen{border-color:var(--hb-accent2,#16B8A6);
    box-shadow:0 0 0 1px var(--hb-accent2,#16B8A6) inset;cursor:default;transform:none}
  .hb-results .hr-chosen-tag{display:inline-block;font-size:var(--f-sm);font-weight:700;
    color:var(--hb-accent2,#16B8A6);margin-top:var(--s2)}

  /* ── PIEZAS de una propuesta compuesta ── una fila etiquetada cada una, para comparar propuesta a propuesta. */
  .hb-results .hr-parts{margin-top:var(--s3);padding-top:var(--s3);border-top:var(--line);display:grid;gap:var(--s2)}
  /* wrap + min-width: en una ficha estrecha el precio (nowrap, empujado a la derecha) estrangulaba el título
     hasta partirlo letra a letra («Valenci / a → / Palma»). Con wrap el precio baja de línea entero. */
  .hb-results .hr-part{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--s1) var(--s2);
    font-size:var(--f-body);line-height:1.4}
  .hb-results .hr-pk{flex:none;background:var(--hb-bubble,#f1f4f9);border-radius:var(--r-sm);padding:2px 6px;
    color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-pt{flex:1 1 7em;min-width:7em;color:var(--hb-ink,#0d1622);overflow-wrap:break-word}
  .hb-results .hr-pp{flex:0 0 auto;margin-left:auto;font-weight:600;color:var(--hb-ink,#0d1622);white-space:nowrap}
  .hb-results .hr-more{margin-top:var(--s3);display:inline-flex;align-items:center;gap:5px;font:600 var(--f-sm)/1 inherit;
    color:var(--hb-accent,#3D6FE0);background:none;border:var(--line);border-radius:var(--r-sm);
    padding:6px 10px;cursor:pointer;transition:.14s}
  .hb-results .hr-more:hover{border-color:var(--hb-accent,#3D6FE0);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 8%,transparent)}

  /* ── VALORACIÓN ── la nota junto al título; el porqué, en el expediente. Sin el porqué no se puede discutir. */
  .hb-results .hr-score{flex:none;display:inline-flex;align-items:baseline;gap:1px;font-weight:700;
    font-size:var(--f-sm);color:var(--hb-accent,#3D6FE0);
    background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 10%,transparent);
    border-radius:var(--r-pill);padding:2.5px var(--s2)}
  .hb-results .hr-score small{font-weight:600;font-size:var(--f-micro);opacity:.7}
  .hb-results .hr-bar{height:4px;border-radius:var(--r-pill);background:var(--hb-bubble,#f1f4f9);
    margin:var(--s2) 0 var(--s1);overflow:hidden}
  .hb-results .hr-bar i{display:block;height:100%;border-radius:var(--r-pill);
    background:linear-gradient(90deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6))}
  .hb-results .hr-why{font-size:var(--f-body);color:var(--hb-muted,#5f6b7c)}

  /* ── BLOQUES de la ficha a medida ── */
  .hb-results .hr-blocks{display:grid;gap:var(--s3);margin-top:var(--s3)}
  .hb-results .hr-bt{margin-bottom:var(--s1)}
  .hb-results .hr-chips{display:flex;flex-wrap:wrap;gap:5px}
  .hb-results .hr-chip{font-size:var(--f-sm);padding:2.5px var(--s2);border-radius:var(--r-pill);
    background:var(--hb-bubble,#f1f4f9);color:var(--hb-muted,#5f6b7c)}
  .hb-results .hr-strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(84px,1fr));gap:5px}
  .hb-results .hr-strip img{width:100%;height:62px;object-fit:cover;border-radius:var(--r-sm);
    background:var(--hb-bubble,#f1f4f9)}
  /* La tabla va en su PROPIO contenedor con scroll: hacerla display:block para que desbordara le quitaba su
     comportamiento de tabla (las columnas dejaban de alinearse entre filas, que es todo lo que aporta). */
  .hb-results .hr-tblwrap{overflow-x:auto;scrollbar-width:thin}
  .hb-results .hr-tbl{border-collapse:collapse;font-size:var(--f-body);min-width:100%}
  .hb-results .hr-tbl th,.hb-results .hr-tbl td{text-align:left;padding:5px var(--s3) 5px 0;
    border-bottom:var(--line);white-space:nowrap}
  .hb-results .hr-tbl tr:last-child td{border-bottom:none}
  .hb-results .hr-tbl th{font-size:var(--f-micro);font-weight:700;letter-spacing:.06em;text-transform:uppercase;
    color:var(--hb-muted-2,#9aa7b8)}
  .hb-results .hr-tbl td:last-child,.hb-results .hr-tbl th:last-child{padding-right:0;text-align:right}
  .hb-results .hr-sub-sec{border-left:2px solid var(--hb-line,#e3e8f0);padding-left:var(--s3);display:grid;
    gap:var(--s2)}

  /* ── FICHA DE DATOS (compartida por tarjeta, expediente y bloques) ── */
  .hb-results .hr-facts{display:grid;grid-template-columns:auto 1fr;gap:var(--s1) var(--s3);
    margin:var(--s3) 0;font-size:var(--f-body);min-width:0}
  .hb-results .hr-fl{color:var(--hb-muted-2,#9aa7b8)}
  .hb-results .hr-fv{color:var(--hb-ink,#0d1622);word-break:break-word}

  /* ── EXPEDIENTE (página 2) ── */
  .hb-results .hr-back{display:inline-flex;align-items:center;gap:5px;font:600 var(--f-sm)/1 inherit;
    color:var(--hb-muted,#5f6b7c);background:none;border:none;padding:0 0 var(--s3);cursor:pointer}
  .hb-results .hr-back:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-dt{font-size:var(--f-lg);font-weight:700;line-height:1.25;letter-spacing:-.015em;
    word-break:break-word}
  .hb-results .hr-dprice{font-size:var(--f-md);font-weight:700;color:var(--hb-ink,#0d1622);margin-top:2px}
  .hb-results .hr-gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:var(--s1);
    margin:var(--s3) 0}
  .hb-results .hr-gal img{width:100%;height:100px;object-fit:cover;border-radius:var(--r-md);
    background:var(--hb-bubble,#f1f4f9)}
  .hb-results .hr-sec{border:var(--line);border-radius:var(--r-lg);padding:var(--s3) var(--s4);
    margin-top:var(--s3);background:var(--hb-bg,#fff)}
  .hb-results .hr-sec .hr-pk{margin-bottom:var(--s1);display:inline-block}
  .hb-results .hr-sect{font-size:var(--f-md);font-weight:650;margin-top:2px;word-break:break-word}
  .hb-results .hr-link{display:inline-block;margin-top:var(--s2);font-size:var(--f-sm);font-weight:600;
    color:var(--hb-accent,#3D6FE0);text-decoration:none;word-break:break-all}
  .hb-results .hr-link:hover{text-decoration:underline}

  /* ── SUMARIO ── */
  .hb-results .hr-state{display:inline-flex;align-items:center;gap:var(--s2);font-size:var(--f-body);
    font-weight:600;margin-bottom:var(--s3)}
  .hb-results .hr-dot{width:7px;height:7px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:none}
  .hb-results .hr-dot.ok{background:var(--hb-ok,#1f9d55)}
  .hb-results .hr-dot.warn{background:var(--hb-warn,#c98a00)}
  .hb-results .hr-dot.bad{background:var(--hb-risk,#e5484d)}
  .hb-results .hr-dot.idle{background:var(--hb-accent,#3D6FE0);animation:hrpulse 1.8s ease-in-out infinite}
  @keyframes hrpulse{0%,100%{opacity:1}50%{opacity:.3}}
  .hb-results .hr-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:var(--s2);
    margin-bottom:var(--s4)}
  .hb-results .hr-stat{border:var(--line);border-radius:var(--r-md);padding:var(--s2) var(--s3) 9px;
    background:var(--hb-bg,#fff)}
  .hb-results .hr-stat b{display:block;font-size:var(--f-xl);line-height:1.1;font-weight:700;letter-spacing:-.02em;
    color:var(--hb-ink,#0d1622)}
  .hb-results .hr-stat span{display:block;margin-top:var(--s1);line-height:1.35;letter-spacing:.04em}
  .hb-results .hr-stat.dim b{color:var(--hb-muted-2,#9aa7b8)}
  .hb-results .hr-stat.warn{border-color:color-mix(in srgb,var(--hb-warn,#c98a00) 34%,var(--hb-line,#e3e8f0))}
  .hb-results .hr-stat.warn b{color:var(--hb-warn-ink,#9a5b1b)}
  /* Bitácora: una línea de tiempo con el hito ACTUAL marcado — leer «por dónde va» no debería exigir contar. */
  .hb-results .hr-steps{list-style:none;margin:var(--s2) 0 0;padding:0;display:grid}
  .hb-results .hr-steps li{position:relative;padding:0 0 var(--s3) var(--s4);color:var(--hb-muted,#5f6b7c)}
  .hb-results .hr-steps li::before{content:"";position:absolute;left:2px;top:6px;width:6px;height:6px;
    border-radius:50%;background:var(--hb-neutral,#c2ccda)}
  .hb-results .hr-steps li::after{content:"";position:absolute;left:4.5px;top:var(--s3);bottom:0;width:1px;
    background:var(--hb-line,#e3e8f0)}
  .hb-results .hr-steps li:last-child{padding-bottom:0;color:var(--hb-ink,#0d1622);font-weight:600}
  .hb-results .hr-steps li:last-child::after{display:none}
  .hb-results .hr-steps li:last-child::before{background:var(--hb-accent,#3D6FE0);
    box-shadow:0 0 0 3px color-mix(in srgb,var(--hb-accent,#3D6FE0) 18%,transparent)}

  /* ── FUENTES ── el punto de color da el veredicto antes de leer; el recuento va a la derecha, alineado. */
  .hb-results .hr-srcs{display:grid;gap:var(--s2)}
  .hb-results .hr-src{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;
    gap:var(--s2) var(--s3);padding:var(--s3) var(--s4);border:var(--line);border-radius:var(--r-md);
    background:var(--hb-bg,#fff)}
  .hb-results .hr-src .hr-dot{margin-top:6px}
  .hb-results .hr-src.bad{border-color:color-mix(in srgb,var(--hb-risk,#e5484d) 30%,var(--hb-line,#e3e8f0))}
  .hb-results .hr-src.warn{border-color:color-mix(in srgb,var(--hb-warn,#c98a00) 34%,var(--hb-line,#e3e8f0))}
  .hb-results .hr-sname{font-size:var(--f-body);font-weight:650;word-break:break-word}
  .hb-results .hr-sname a{color:inherit;text-decoration:none}
  .hb-results .hr-sname a:hover{color:var(--hb-accent,#3D6FE0);text-decoration:underline}
  .hb-results .hr-sst{font-size:var(--f-sm);font-weight:600;color:var(--hb-muted,#5f6b7c);margin-top:1px}
  .hb-results .hr-sst.warn{color:var(--hb-warn-ink,#9a5b1b)}
  .hb-results .hr-sst.bad{color:var(--hb-risk,#e5484d)}
  .hb-results .hr-sd{font-size:var(--f-body);color:var(--hb-muted,#5f6b7c);margin-top:var(--s1);
    overflow-wrap:break-word}
  .hb-results .hr-sn{text-align:right;font-size:var(--f-md);font-weight:700;color:var(--hb-ink,#0d1622);
    white-space:nowrap;line-height:1.2}
  .hb-results .hr-sn.zero{color:var(--hb-muted-2,#9aa7b8)}
  /* La unidad se repite en cada fila, así que va en minúscula y sin tracking: en versalitas competía en peso con
     la propia cifra y seis «RESULTADOS» seguidos gritaban más que los números, que es lo que hay que leer. */
  .hb-results .hr-sn small{display:block;font-size:var(--f-micro);font-weight:500;
    color:var(--hb-muted-2,#9aa7b8);margin-top:1px}

  /* ── CRITERIOS ── */
  .hb-results .hr-goal{font-size:var(--f-body);line-height:1.55;padding:var(--s3) var(--s4);
    border-radius:var(--r-md);background:var(--hb-bg-soft,#fbfdff);border:var(--line);
    border-left:2px solid var(--hb-accent,#3D6FE0);margin-bottom:var(--s3);word-break:break-word}
  .hb-results .hr-cgrp{margin-bottom:var(--s4)}
  .hb-results .hr-cgrp:last-child{margin-bottom:0}
  .hb-results .hr-cgt{margin-bottom:var(--s2)}
  .hb-results .hr-cgt em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:500;
    color:var(--hb-muted-2,#9aa7b8);opacity:.85}
  .hb-results .hr-clist{list-style:none;margin:0;padding:0;display:grid;gap:5px}
  .hb-results .hr-clist li{position:relative;padding-left:var(--s3);line-height:1.5;color:var(--hb-ink,#0d1622);
    overflow-wrap:break-word}
  .hb-results .hr-clist li::before{content:"";position:absolute;left:0;top:7px;width:4px;height:4px;
    border-radius:50%;background:var(--hb-neutral,#c2ccda)}
  .hb-results .hr-cgrp.hard .hr-clist li::before{background:var(--hb-accent,#3D6FE0)}
  .hb-results .hr-cgrp.changes .hr-clist li::before{background:var(--hb-accent2,#16B8A6)}
  `; document.head.appendChild(s);
}

// ── primitivas seguras ────────────────────────────────────────────────────────────────────────────────────────
function elem(tag, cls, text){
  const e=document.createElement(tag);
  if(cls) e.className=cls;
  if(text!=null) e.textContent=String(text);
  return e;
}

function photo(url, alt, cls){
  const img=document.createElement("img"); img.className=cls||"";
  img.src=url; img.alt=alt||""; img.loading="lazy"; img.referrerPolicy="no-referrer";
  img.addEventListener("error",()=>img.remove());   // dead photo link → drop silently, never break the card
  return img;
}

function factsTable(facts){
  const box=elem("div","hr-facts");
  (Array.isArray(facts)?facts:[]).forEach(f=>{
    if(!f || !f.label) return;
    box.append(elem("div","hr-fl",f.label), elem("div","hr-fv",f.value==null?"":f.value));
  });
  return box.childElementCount ? box : null;
}

function pct(v, max){
  const m=Number(max)||10, n=Number(v);
  if(!isFinite(n) || m<=0) return 0;
  return Math.max(0, Math.min(100, (n/m)*100));
}

// La VALORACIÓN como etiqueta compacta (para la cabecera de una tarjeta).
function scoreTag(score){
  if(!score) return null;
  if(score.value == null) return score.label ? elem("span","hr-score",score.label) : null;
  const tag=elem("span","hr-score", String(score.value));
  tag.appendChild(elem("small","", "/"+(score.max||10)));
  if(score.label) tag.title=score.label;
  return tag;
}

// …y como bloque explicado (para el expediente): la nota, la barra y EL PORQUÉ.
function scoreBlock(score){
  if(!score || (score.value==null && !score.label && !score.why)) return null;
  const box=elem("div","");
  box.appendChild(elem("div","hr-bt","Valoración"));
  if(score.value != null){
    const row=elem("div","hr-head");
    row.appendChild(elem("div","hr-t", `${score.value} / ${score.max||10}`));
    if(score.label) row.appendChild(elem("div","hr-price",score.label));
    box.appendChild(row);
    const bar=elem("div","hr-bar"); const fill=elem("i");
    fill.style.width=pct(score.value, score.max)+"%"; bar.appendChild(fill); box.appendChild(bar);
  } else if(score.label){
    box.appendChild(elem("div","hr-t",score.label));
  }
  if(score.why) box.appendChild(elem("div","hr-why",score.why));
  return box;
}

// ── FICHA DINÁMICA: los bloques ───────────────────────────────────────────────────────────────────────────────
// Vocabulario cerrado, saneado ya en data.py. Cada bloque se pinta con primitivas nuestras: el worker compone la
// ficha que necesita su tipo de resultado, pero no aporta ni una etiqueta de HTML.
function renderBlock(b, depth){
  if(!b || !b.kind) return null;
  const wrap=elem("div","");
  if(b.title) wrap.appendChild(elem("div","hr-bt",b.title));
  switch(b.kind){
    case "text":
      (b.lines||[]).forEach(l=>wrap.appendChild(elem("div","hr-ln"+(b.tone?" "+b.tone:""), l)));
      break;
    case "facts": {
      const ft=factsTable(b.facts); if(ft){ ft.style.margin="0"; wrap.appendChild(ft); }
      break;
    }
    case "chips": {
      const row=elem("div","hr-chips");
      (b.chips||[]).forEach(c=>row.appendChild(elem("span","hr-chip",c)));
      wrap.appendChild(row);
      break;
    }
    case "gallery": {
      const strip=elem("div","hr-strip");
      (b.images||[]).forEach(u=>strip.appendChild(photo(u, b.title||"", "")));
      wrap.appendChild(strip);
      break;
    }
    case "meter": {
      const bar=elem("div","hr-bar"); const fill=elem("i");
      fill.style.width=pct(b.value, b.max)+"%"; bar.appendChild(fill); wrap.appendChild(bar);
      wrap.appendChild(elem("div","hr-why", (b.caption ? b.caption+" · " : "") + `${b.value} / ${b.max||10}`));
      break;
    }
    case "table": {
      // La tabla vive en su PROPIO contenedor con scroll. Antes se le ponía `display:block` para que desbordara,
      // y eso le quita su comportamiento de tabla: las columnas dejan de alinearse entre filas, que es lo único
      // que aporta una tabla sobre una lista.
      const box=elem("div","hr-tblwrap");
      const t=elem("table","hr-tbl");
      if(b.columns && b.columns.length){
        const tr=elem("tr"); b.columns.forEach(c=>tr.appendChild(elem("th","",c)));
        const thead=elem("thead"); thead.appendChild(tr); t.appendChild(thead);
      }
      const tb=elem("tbody");
      (b.rows||[]).forEach(r=>{ const tr=elem("tr"); (r||[]).forEach(c=>tr.appendChild(elem("td","",c))); tb.appendChild(tr); });
      t.appendChild(tb); box.appendChild(t); wrap.appendChild(box);
      break;
    }
    case "link": {
      const a=elem("a","hr-link",b.label||b.url);
      a.href=b.url; a.target="_blank"; a.rel="noopener noreferrer";
      a.style.marginTop="0"; wrap.appendChild(a);
      break;
    }
    case "section": {
      const inner=elem("div","hr-sub-sec");
      (b.blocks||[]).forEach(x=>{ const e=renderBlock(x, (depth||0)+1); if(e) inner.appendChild(e); });
      if(!inner.childElementCount) return null;
      wrap.appendChild(inner);
      break;
    }
    default: return null;
  }
  return wrap.childElementCount ? wrap : null;
}

// En la LISTA no cabe el expediente. Visto en pantalla: una ficha con su tabla de costes, su medidor y su sección
// de documentación ocupaba la tarjeta ENTERA, y con diez resultados —el defecto de entrega desde el 2026-08-12— la
// lista deja de poder BARRERSE, que es lo único que una lista tiene que saber hacer. Así que la lista se queda con
// los bloques LIGEROS y el resto es lo que uno va a buscar al abrir la ficha.
// La excepción es un `text` con tono de AVISO: una salvedad importante escondida detrás de un clic es justo lo que
// prohíbe la regla de presentación («nada importante al final de un campo largo»).
const LIGHT_BLOCKS = new Set(["chips"]);
function isLight(b){
  if(!b) return false;
  if(LIGHT_BLOCKS.has(b.kind)) return true;
  return b.kind === "text" && b.tone === "warn";
}

function renderBlocks(blocks, {compact = false} = {}){
  let list = Array.isArray(blocks) ? blocks : [];
  if(compact) list = list.filter(isLight).slice(0, 2);
  const box=elem("div","hr-blocks");
  list.forEach(b=>{ const e=renderBlock(b,0); if(e) box.appendChild(e); });
  return box.childElementCount ? box : null;
}

// ── reparto en columnas: lo decide el ANCHO REAL, no un parámetro adivinado ────────────────────────────────────
// Antes la hoja tenía 620px fijos y el nº de columnas se calculaba a ojo desde la forma del contenido. Ahora la
// tarjeta es redimensionable (y puede ir a pantalla completa), así que quien manda es el ancho disponible: cada
// columna tiene un MÍNIMO según lo rica que sea la tarjeta y hay un TOPE de columnas para que maximizar no
// produzca ocho columnas de confeti. Se expresa en CSS puro (`auto-fill` + `minmax` con un suelo de 100%/tope),
// así que reflowea sola al arrastrar la esquina — sin medir nada desde JS ni escuchar resizes.
function gridStyle(items, cap){
  const rich = items.some(it => it && (
    (it.parts && it.parts.length) ||
    (it.blocks && it.blocks.length) ||
    (it.facts && it.facts.length > 3) ||
    (it.images && it.images.length) ||
    (it.lines && it.lines.length > 4)
  ));
  const medium = !rich && items.some(it => it && ((it.lines && it.lines.length) || it.image || it.facts));
  const min = rich ? 400 : medium ? 300 : 230;
  let maxCols = rich ? 2 : medium ? 3 : 4;
  const n = Number(cap);
  if(Number.isFinite(n) && n >= 1) maxCols = Math.min(maxCols, Math.floor(n));
  maxCols = Math.max(1, maxCols);
  const gap = 12;
  const floor = `calc((100% - ${(maxCols-1)*gap}px) / ${maxCols})`;
  return `repeat(auto-fill,minmax(max(min(100%,${min}px),${floor}),1fr))`;
}

// ── una tarjeta ───────────────────────────────────────────────────────────────────────────────────────────────
function makeCard(it, isPrimary, choose, ctx){
  const parts = Array.isArray(it.parts) ? it.parts : [];
  const blocks = Array.isArray(it.blocks) ? it.blocks : [];
  const hasDetail = parts.length || blocks.length || it.score
                    || (Array.isArray(it.images) && it.images.length)
                    || (Array.isArray(it.facts) && it.facts.length);
  // A composite card owns interactive children (per-piece links, "ver detalle") so it can't be an <a> — nesting
  // links/buttons inside an anchor is invalid and swallows their clicks into the outer navigation.
  const asLink = it.url && !hasDetail;
  const card = document.createElement(asLink ? "a" : "div");
  card.className = "hr-card" + (isPrimary ? " primary" : "");
  if(asLink){ card.href = it.url; card.target = "_blank"; card.rel = "noopener noreferrer"; }
  if(it.image) card.appendChild(photo(it.image, it.title, "hr-img"));
  const head = elem("div","hr-head");
  head.appendChild(elem("div","hr-t", it.title || ""));
  const sc = scoreTag(it.score); if(sc) head.appendChild(sc);
  if(it.price) head.appendChild(elem("div","hr-price", it.price));
  card.appendChild(head);
  // El BADGE va con el título, no al pie. Es una etiqueta que CALIFICA el resultado («Mejor conjunto»), y abajo
  // acababa junto al botón de detalle, donde se leía como un segundo botón.
  const meta = elem("div","hr-metarow");
  if(it.subtitle) meta.appendChild(elem("span","hr-s", it.subtitle));
  if(it.badge) meta.appendChild(elem("span","hr-badge", it.badge));
  if(meta.childElementCount) card.appendChild(meta);
  // 80 lines (data.py's cap) so a full block of text — e.g. a song's lyrics — fits in one item's body, not just
  // a handful of spec-sheet bullets (2026-08-03). En la lista se acotan: el bloque entero es del expediente.
  (Array.isArray(it.lines) ? it.lines : []).slice(0, hasDetail ? 3 : 80)
    .forEach(l=>card.appendChild(elem("div","hr-ln", l)));

  const bl = renderBlocks(blocks, {compact: true}); if(bl) card.appendChild(bl);

  // the pieces of a composite result, so three proposals stay comparable at a glance
  if(parts.length){
    const box=elem("div","hr-parts");
    parts.forEach(p=>{
      const row=elem("div","hr-part");
      if(p.kind) row.appendChild(elem("span","hr-pk", p.kind));
      row.appendChild(elem("span","hr-pt", p.title||""));
      if(p.price) row.appendChild(elem("span","hr-pp", p.price));
      box.appendChild(row);
    });
    card.appendChild(box);
  }

  if(hasDetail && ctx){
    const btn=elem("button","hr-more","Ver detalle →"); btn.type="button";
    btn.addEventListener("click", async (e)=>{ e.preventDefault(); e.stopPropagation();
      await ctx.action("detail", { title: it.title || "" }); });
    card.appendChild(btn);
  }

  if(choose && !asLink){
    card.classList.add("choosable");
    const tagOf=()=>elem("span","hr-chosen-tag","✓ Elegido");
    if(choose.chosenTitle && it.title === choose.chosenTitle){ card.classList.add("chosen"); card.appendChild(tagOf()); }
    card.addEventListener("click", async () => {
      if(card.classList.contains("chosen")) return;
      choose.root.querySelectorAll(".hr-card.chosen").forEach(c => { c.classList.remove("chosen"); const t=c.querySelector(".hr-chosen-tag"); if(t)t.remove(); });
      card.classList.add("chosen"); card.appendChild(tagOf());
      await choose.ctx.action("choose", { title: it.title || "" });
    });
  }
  return card;
}

// ── página 2: UN item, en full ────────────────────────────────────────────────────────────────────────────────
// Esto es lo que pinta "enséñame en detalle la propuesta uno": cada foto, cada dato, LA VALORACIÓN con su porqué,
// la ficha dinámica entera y cada pieza del paquete desplegada con su precio, horarios y enlace real.
function renderDetail(panel, it, ctx){
  const back=elem("button","hr-back","← Volver a la lista"); back.type="button";
  back.addEventListener("click", async ()=>{ await ctx.action("list", {}); });
  panel.appendChild(back);

  panel.appendChild(elem("div","hr-dt", it.title||""));
  if(it.price) panel.appendChild(elem("div","hr-dprice", it.price));
  const dmeta = elem("div","hr-metarow");
  if(it.subtitle) dmeta.appendChild(elem("span","hr-s", it.subtitle));
  if(it.badge) dmeta.appendChild(elem("span","hr-badge", it.badge));
  if(dmeta.childElementCount) panel.appendChild(dmeta);

  // LA VALORACIÓN va ARRIBA, antes de las fotos: es el VEREDICTO. Debajo de la galería se leía como un dato más
  // al final de la ficha, cuando es justo lo que responde «¿por qué esta y no otra?».
  const sb=scoreBlock(it.score);
  if(sb){ const sec=elem("div","hr-sec"); sec.appendChild(sb); panel.appendChild(sec); }

  const gallery = Array.isArray(it.images) && it.images.length ? it.images : (it.image ? [it.image] : []);
  if(gallery.length){
    const g=elem("div","hr-gal");
    gallery.forEach(u=>g.appendChild(photo(u, it.title, "")));
    panel.appendChild(g);
  }

  (Array.isArray(it.lines)?it.lines:[]).slice(0,80).forEach(l=>panel.appendChild(elem("div","hr-ln", l)));

  const ft=factsTable(it.facts); if(ft) panel.appendChild(ft);
  const bl=renderBlocks(it.blocks); if(bl) panel.appendChild(bl);

  if(it.url){
    const a=elem("a","hr-link", it.url);
    a.href=it.url; a.target="_blank"; a.rel="noopener noreferrer"; panel.appendChild(a);
  }

  (Array.isArray(it.parts)?it.parts:[]).forEach(p=>{
    const sec=elem("div","hr-sec");
    if(p.kind) sec.appendChild(elem("span","hr-pk", p.kind));
    sec.appendChild(elem("div","hr-sect", p.title||""));
    if(p.price) sec.appendChild(elem("div","hr-dprice", p.price));
    if(p.subtitle) sec.appendChild(elem("div","hr-s", p.subtitle));
    if(p.image) sec.appendChild(photo(p.image, p.title, "hr-img"));
    (Array.isArray(p.lines)?p.lines:[]).forEach(l=>sec.appendChild(elem("div","hr-ln", l)));
    const pf=factsTable(p.facts); if(pf) sec.appendChild(pf);
    if(p.url){
      const a=elem("a","hr-link", p.url);
      a.href=p.url; a.target="_blank"; a.rel="noopener noreferrer"; sec.appendChild(a);
    }
    panel.appendChild(sec);
  });
}

function findFocused(items, focus){
  const f=String(focus||"").trim().toLowerCase();
  if(!f) return null;
  return items.find(it=>String(it&&it.title||"").trim().toLowerCase()===f)
      || items.find(it=>String(it&&it.title||"").trim().toLowerCase().includes(f))
      || null;
}

// ── PESTAÑA 1 · RESULTADOS ────────────────────────────────────────────────────────────────────────────────────
function paintResults(panel, data, ctx){
  const items = Array.isArray(data.items) ? data.items : [];

  if(data.view === "detail"){
    const it = findFocused(items, data.focus);
    if(it){ renderDetail(panel, it, ctx); return; }
    // focus pointing at nothing (list replaced under it) → fall through to the list, never a blank screen
  }

  const total = items.length;
  const all = items.slice(0, 24);
  if(!all.length){
    panel.appendChild(elem("div","hr-empty", data.note || "Sin resultados todavía."));
    return;
  }

  const primary = all.filter(it => it && it.primary);
  const rest = all.filter(it => !it || !it.primary);
  const choose = data.choosable ? { root: panel, ctx, chosenTitle: data.chosen } : null;

  // primary items: comparten la fila de arriba y mandan sobre el ancho (una destacada ocupa la hoja entera).
  if(primary.length){
    const pgrid = elem("div","hr-grid");
    pgrid.style.gridTemplateColumns = gridStyle(primary, primary.length === 1 ? 1 : 2);
    panel.appendChild(pgrid);
    primary.forEach(it => pgrid.appendChild(makeCard(it, true, choose, ctx)));
  }

  if(rest.length){
    const sgrid = elem("div","hr-grid");
    sgrid.style.gridTemplateColumns = gridStyle(rest, primary.length ? 2 : data.columns);
    panel.appendChild(sgrid);
    rest.forEach(it => sgrid.appendChild(makeCard(it, false, choose, ctx)));
  }

  // Faithful count: if the real pushed results exceed what we render, say so — never silently drop
  // obtained data (the operator asked for a REAL search; the interface must reflect its true size).
  if(total > all.length){
    const more = elem("div","hr-sub", `Mostrando ${all.length} de ${total} resultados.`);
    more.style.marginTop = "10px";
    panel.appendChild(more);
  }
}

// ── PESTAÑA 2 · SUMARIO ───────────────────────────────────────────────────────────────────────────────────────
// Lo REPORTADO y lo DERIVADO se pintan por separado a propósito: «explorados» solo lo sabe quien trabajó, y si
// nadie lo dijo la pestaña lo DICE en vez de enseñar el número de tarjetas como si fuera la amplitud.
function paintSummary(panel, data){
  const s = data.summary || {}, c = data.counts || {};
  const hasAny = Object.keys(s).length || c.shown || c.sources;
  if(!hasAny){
    panel.appendChild(elem("div","hr-empty",
      "Todavía no hay nada que resumir. Esta pestaña se llena mientras se trabaja: estado, cuántos candidatos se "
      + "han explorado y qué se ha ido haciendo."));
    return;
  }
  if(s.state){
    const row=elem("div","hr-state");
    const done=/termin|complet|listo|entregad|finaliz/i.test(s.state);
    row.appendChild(elem("span","hr-dot "+(done?"ok":"idle")));
    row.appendChild(elem("span","", s.state));
    panel.appendChild(row);
  }
  const stats=elem("div","hr-stats");
  const add=(value, label, tone)=>{
    const box=elem("div","hr-stat"+(tone?" "+tone:""));
    box.appendChild(elem("b","", value));
    box.appendChild(elem("span","", label));
    stats.appendChild(box);
  };
  const noBreadth = s.explored == null;
  add(noBreadth ? "—" : s.explored, noBreadth ? "sin reportar" : "explorados", noBreadth ? "dim" : "");
  add(c.shown || 0, "en pantalla");
  if(s.discarded != null) add(s.discarded, "descartados");
  if(c.sources) add(c.sources, "fuentes");
  // Las fuentes con problema van en su PROPIA casilla y en color de aviso. Metidas en la etiqueta de «fuentes»
  // hacían un rótulo de dos líneas («FUENTES · 3 CON / PROBLEMA») que rompía la fila, y además escondían dentro
  // del pie de otro número el único dato de aquí que pide una decisión del operador.
  if(c.sources_failed) add(c.sources_failed, "sin aprovechar", "warn");
  if(s.round && s.round > 1) add(s.round, "ronda");
  panel.appendChild(stats);

  if(s.note) panel.appendChild(elem("div","hr-why", s.note));

  if(Array.isArray(s.steps) && s.steps.length){
    panel.appendChild(elem("div","hr-cgt","Lo que se ha hecho"));
    const ul=elem("ul","hr-steps");
    s.steps.forEach(st=>ul.appendChild(elem("li","", st)));
    panel.appendChild(ul);
  }
}

// ── PESTAÑA 3 · FUENTES ───────────────────────────────────────────────────────────────────────────────────────
// De dónde salen los datos y QUÉ pasó en cada sitio. Es lo que convierte un «no he encontrado nada» en un dato
// que se puede auditar y corregir («entra tú en esa, que pide login»).
function paintSources(panel, data){
  const src = Array.isArray(data.sources) ? data.sources : [];
  if(!src.length){
    panel.appendChild(elem("div","hr-empty",
      "Nadie ha reportado fuentes todavía. Aquí aparecerá cada web que se consulte y qué pasó en ella: si entró, "
      + "si le limitaron los resultados, si pedía autenticación o si dio error."));
    return;
  }
  const c = data.counts || {};
  panel.appendChild(elem("div","hr-sub",
    `${src.length} fuente${src.length===1?"":"s"}`
    + (c.sources_failed ? ` · ${c.sources_failed} sin poder aprovechar` : "")
    + (c.from_sources ? ` · ${c.from_sources} resultados reunidos` : "")));
  // Las que NO se pudieron aprovechar, PRIMERO. Son las que piden una decisión del operador («esa pide login,
  // entro yo»); las que fueron bien solo necesitan estar contadas. Orden estable dentro de cada grupo.
  const rank = {bad: 0, warn: 1, idle: 2, ok: 3};
  const ordered = src.map((s, i) => [s, i]).sort((a, b) => {
    const ra = rank[(SOURCE_STATUS[a[0].status] || SOURCE_STATUS.ok).cls] ?? 3;
    const rb = rank[(SOURCE_STATUS[b[0].status] || SOURCE_STATUS.ok).cls] ?? 3;
    return ra - rb || a[1] - b[1];
  }).map(x => x[0]);

  const list=elem("div","hr-srcs");
  ordered.forEach(s=>{
    const st = SOURCE_STATUS[s.status] || SOURCE_STATUS.ok;
    const row=elem("div","hr-src"+(st.cls==="bad"||st.cls==="warn" ? " "+st.cls : ""));
    row.appendChild(elem("span","hr-dot "+st.cls));
    const mid=elem("div","");
    const name=elem("div","hr-sname");
    if(s.url){
      const a=elem("a","", s.name); a.href=s.url; a.target="_blank"; a.rel="noopener noreferrer"; name.appendChild(a);
    } else name.textContent = s.name;
    mid.appendChild(name);
    mid.appendChild(elem("div","hr-sst "+st.cls, st.label));
    if(s.detail) mid.appendChild(elem("div","hr-sd", s.detail));
    row.appendChild(mid);
    if(s.found != null){
      const n=elem("div","hr-sn"+(s.found ? "" : " zero"), String(s.found));
      n.appendChild(elem("small","", s.found === 1 ? "resultado" : "resultados"));
      row.appendChild(n);
    } else row.appendChild(elem("div",""));
    list.appendChild(row);
  });
  panel.appendChild(list);
}

// ── PESTAÑA 4 · CRITERIOS ─────────────────────────────────────────────────────────────────────────────────────
// El encargo tal y como se está ejecutando AHORA. No es el histórico de la conversación: es con qué se está
// buscando en este momento, para poder verlo y corregirlo («que sean de 42 a 49 pies»).
function paintCriteria(panel, data){
  const c = data.criteria || {};
  const any = c.goal || CRIT_SECTIONS.some(s=>Array.isArray(c[s.key]) && c[s.key].length);
  if(!any){
    panel.appendChild(elem("div","hr-empty",
      "Todavía no hay criterios fijados. En cuanto se dirija una búsqueda aparecerán aquí el objetivo, los "
      + "requisitos que descalifican, las preferencias y lo que se haya dado por supuesto — y podrás corregirlos "
      + "hablando."));
    return;
  }
  if(c.goal) panel.appendChild(elem("div","hr-goal", c.goal));
  const meta=[];
  if(c.domain) meta.push(c.domain);
  if(c.min_candidates) meta.push(`amplitud mínima: ${c.min_candidates} candidatos`);
  if(c.n_final) meta.push(`entrega: ${c.n_final} finalistas`);
  if(meta.length) panel.appendChild(elem("div","hr-sub", meta.join(" · ")));

  CRIT_SECTIONS.forEach(sec=>{
    const list = c[sec.key];
    if(!Array.isArray(list) || !list.length) return;
    const grp=elem("div","hr-cgrp "+sec.key);
    const t=elem("div","hr-cgt", sec.label);
    if(sec.note){ t.appendChild(document.createTextNode(" ")); t.appendChild(elem("em","","— "+sec.note)); }
    grp.appendChild(t);
    const ul=elem("ul","hr-clist");
    list.forEach(x=>ul.appendChild(elem("li","", x)));
    grp.appendChild(ul);
    panel.appendChild(grp);
  });
}

const PAINT = {results: paintResults, summary: paintSummary, sources: paintSources, criteria: paintCriteria};

// ¿Esta pintada es una NAVEGACIÓN o un refresco de datos? Importa para el scroll: «Ver detalle →» vive al final
// de una tarjeta, así que sin volver arriba el expediente se abre por la mitad (y saltar de pestaña te dejaba a
// media lista). Pero un `append` del worker mientras el operador lee NO puede moverle la página. Se compara solo
// la posición en la hoja —pestaña y página—, nunca el contenido. WeakMap: si la tarjeta muere, esto se va con ella.
const WHERE = new WeakMap();
function navigated(el, data, cur){
  const now = [cur, data.view || "list", data.focus || ""].join("|");
  const was = WHERE.get(el);
  WHERE.set(el, now);
  return was !== undefined && was !== now;
}

// Contador que se pinta en cada pestaña. Solo cuando dice algo: un «0» en cuatro pestañas es ruido, y un número
// rojo en Fuentes es justo lo que hace mirar («3 webs no me dejaron entrar»).
function tabCount(id, data){
  const c = data.counts || {}, s = data.summary || {};
  if(id === "results") return c.shown ? {n: c.shown} : null;
  if(id === "sources") return c.sources ? {n: c.sources, bad: !!c.sources_failed} : null;
  if(id === "criteria"){
    const crit=data.criteria||{};
    const n=CRIT_SECTIONS.reduce((a,x)=>a+((crit[x.key]||[]).length),0);
    return n ? {n} : null;
  }
  if(id === "summary") return s.explored ? {n: s.explored} : null;
  return null;
}

export function render(el, data, ctx){
  injectStyles();
  data = data || {};
  el.className = "hb-results";
  el.textContent = "";

  // Título y pestañas van juntos en una cabecera PEGAJOSA: con varias decenas de resultados la hoja se recorre
  // con scroll y las pestañas tienen que seguir ahí (mirar la última ficha y saltar a Fuentes es un caso normal).
  const top = elem("div","hr-top");
  top.appendChild(elem("div","hr-hd", data.title || "Resultados"));
  if(data.subtitle) top.appendChild(elem("div","hr-sub", data.subtitle));

  let cur = TABS.some(t=>t.id===data.tab) ? data.tab : "results";
  const bar = elem("div","hr-tabs");
  const panel = elem("div","hr-panel");

  const paint = (moved)=>{
    panel.textContent="";
    (PAINT[cur] || paintResults)(panel, data, ctx);
    bar.querySelectorAll(".hr-tab").forEach(b=>b.classList.toggle("on", b.dataset.tab===cur));
    if(moved && ctx && ctx.top) ctx.top();
  };

  TABS.forEach(t=>{
    const b=elem("button","hr-tab"); b.type="button"; b.dataset.tab=t.id;
    b.appendChild(document.createTextNode(t.label));
    const c=tabCount(t.id, data);
    if(c) b.appendChild(elem("span","hr-n"+(c.bad?" bad":""), String(c.n)));
    b.addEventListener("click", ()=>{
      if(cur===t.id) return;
      cur=t.id;
      // Se pinta YA (la pestaña no puede parpadear esperando al servidor) y ADEMÁS se persiste, porque el estado
      // de esta hoja no vive en el navegador: así el cerebro sabe qué está mirando el operador y una recarga o un
      // «vuelve a los resultados» por voz siguen cuadrando con la pantalla.
      paint(true);
      if(ctx && ctx.action) ctx.action("tab", {tab: t.id});
    });
    bar.appendChild(b);
  });

  top.appendChild(bar);
  el.append(top, panel);
  paint(navigated(el, data, cur));
}
