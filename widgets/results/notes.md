- Petición: buscar motos Naked de 2ª mano en Bilbao y mostrar precio/modelo/año/estado aquí, asegurando que sea una búsqueda REAL (no un espejo local con datos inventados). Este widget NUNCA busca por su cuenta (lo dice su propio contrato) — la búsqueda real la ejecuta el cerebro vía navegador/worker y empuja los datos con `[[push:results]]`; el fallback `view_data()` de aquí NO debe rellenarse con motos falsas. Cambio hecho: añadido campo opcional `price` a los items (badge junto al título, `.hr-head`/`.hr-price`) para que precio quede siempre visible y no enterrado en subtitle/lines; modelo=título, año/estado siguen yendo en subtitle/lines como ya soportaba el esquema genérico.
- Petición: asegurar que la acción REAL de obtención y presentación de datos se refleje correctamente en la interfaz (no que el widget busque — sigue SIN buscar, la búsqueda real la ejecuta el cerebro/worker/navegador y pushea con `[[push:results]]`). Cambio quirúrgico en `widget.js/render`: se conserva el recuento REAL de items pusheados (`total`) antes del `slice(0,24)` y, si hay más de los que se pintan, se muestra un pie ("Mostrando 24 de N resultados.") reutilizando el estilo `.hr-sub` — así una búsqueda real con muchos resultados nunca se recorta en silencio y el operador ve el volumen verdadero de lo obtenido. Nada más tocado (CSS/layout/choose/fallback intactos).
- Petición: tras una búsqueda activa (p.ej. nombres de producto disponibles), que el operador pueda ELEGIR uno de los resultados mostrados aquí. Este widget sigue SIN buscar por su cuenta (la búsqueda real la hace el cerebro y pushea los items); solo se añadió la capacidad de SELECCIÓN sobre lo ya mostrado: `data.choosable:true` hace clicables los items sin `url`, con acción `choose({title})` (declarada en manifest, no-confirm, reversible). La selección se marca EN CLIENTE (widget.js usa el valor devuelto por `ctx.action`, sin re-render), a propósito: `apply_action("choose",…)` NO llama a `store.save()` porque los datos pusheados son efímeros (nunca pasan por `data.py`) y disparar la señal SSE de refresco solo recargaría el fallback estático de `view_data()` (Proyectos), borrando la lista real de pantalla. No se añadió `ref_index()`: `data.py` no tiene visibilidad de los items realmente pusheados (por diseño), así que un índice aquí solo listaría el fallback y desorientaría al cerebro — el título exacto mostrado en pantalla basta para resolver la elección.
- Petición: finalizar y mostrar el informe de la búsqueda ampliada de piscinas/hoteles/campings cerca de Tarragona INCLUYENDO FOTOS. Sigue SIN buscar (contrato de arriba): la búsqueda REAL la hace el cerebro vía worker/navegador y empuja con `[[push:results]]`; el fallback `view_data()` NO se rellena con datos inventados de Tarragona (igual que ya se descartó con las motos de Bilbao). Cambio quirúrgico = soporte de FOTO: los items pueden llevar `image` (URL) y se pinta como `<img>` de portada (`object-fit:cover`, esquina redondeada, `referrerPolicy=no-referrer`+`loading=lazy`, self-remove en `error` si el enlace cae) encima del título, reutilizando layout/CSS existentes — choose/price/columns/recuento/fallback INTACTOS. Añadidos alias `Informe`/`Informes` y keyword `fotos` (el operador lo llama "widget de informes") para que el cerebro enrute aquí "muéstrame el informe con fotos".
- **2026-08-02 — CORRECCIÓN DE FONDO: las 4 notas de arriba parten de una premisa FALSA.** Todas dicen que los datos
  "los empuja el cerebro con `[[push:results]]`". **Ese canal nunca ha funcionado**: el provider de voz
  (`voice/engine/llm/providers/nucleo.py`) trata `push` igual que `create`/`modify` — lo BLOQUEA y lo convierte en
  una escalada ("intentó [[push]] — bloqueado, escalando"). Es decir, este widget llevaba tiempo sin ninguna vía
  real de relleno: un Brain Worker con el informe terminado en la mano no tenía por dónde entregarlo, y
  `view_data()` devolvía una lista DEMO de proyectos del operador (Pricewaterhouse/Mage Core/…), así que abrir la
  tarjeta para una búsqueda de piscinas pintaba "Proyectos". El operador lo vivió entero el 2026-08-02: 3 workers,
  ~9 min, 0 resultados en pantalla.
  **Rediseño (el widget es ahora la SUPERFICIE GENÉRICA DE PRESENTACIÓN):**
  · `view_data()` devuelve lo ÚLTIMO ENTREGADO, persistido en `widgets/_data/results.json` (`store`). Sin nada
    entregado = hoja EN BLANCO. Fuera la lista demo: una superficie de presentación no tiene contenido propio.
  · Se entrega por ACCIONES DECLARADAS —`present` (conjunto completo), `append` (ir llenando según llegan,
    deduplica por title+url), `clear`— que reutilizan el camino ya probado `hbwidget → /api/worker/act widget_data
    → brain_action → apply_action → store.save → SSE → re-render`. Cero protocolo nuevo. Las tres son FAST.
  · `choose` ya SÍ persiste (la lista es persistente; el motivo que había para no llamar a `store.save()` era
    justamente la efimeridad del push, que ya no existe).
  · Añadido `ref_index()` — que la nota 3 descartó a propósito con el modelo viejo: ahora `data.py` SÍ ve los items
    reales. Sirve para elegir por lenguaje natural y, sobre todo, para que el cerebro DISTINGA "abierto con datos"
    de "abierto y vacío" (`widgets/refs.items_line`) y deje de decir "aquí lo tienes" sobre una tarjeta en blanco.
  · `usage`/`actions` del manifest enseñan el contrato COMPLETO de la tarjeta (title/subtitle/price/lines/badge/
    url/image/primary) y que el payload va **por fichero** (`hbwidget data results present @informe.json`): pegar
    4 KB de JSON en la línea de comandos rompe el quoting y deja al worker esperando una aprobación que no llega.
  · `widget.js` NO se tocó en este cambio (el soporte de `image` de la nota 4 se conserva tal cual).
  Verificado en vivo de punta a punta: petición → worker real → búsqueda web → `present @fichero` → `show` →
  4 parques acuáticos con precio, horario, enlace y foto en pantalla (~5 min).
- **2026-08-03 — el widget ya podía; el cerebro no sabía pedírselo (+ un cap real de sobra).** Petición
  "muéstrame una foto de un plato de quinoa": el cerebro llamó a `web_search` (solo TEXTO — nunca una foto real)
  y acabó DESCRIBIENDO de palabra la imagen que no podía traer; 6 turnos de disculpas antes de rendirse. El
  esquema de este widget YA aceptaba un item con solo `image` (una foto sola, sin url/price), pero nada en las
  descripciones de `router.py` decía que ESO había que escalarlo. Fix real en `nucleo/flash/router.py`: `web_search`
  ahora dice explícitamente "solo trae TEXTO, nunca una foto real"; `escalate_to_slowbrain` incluye "conseguir una
  foto/imagen REAL para enseñarla" en su lista de SÍ. Nada tocado aquí en el contrato — solo se subió el cap de
  `lines` (4→80 líneas, 300 chars cada una sigue igual) porque una petición real ("muéstrame la letra de una
  canción") necesita un bloque de texto completo, no 4 bullets — mismo esquema, un tope menos artificialmente
  corto. `manifest.json.usage` y `keywords` (imagen/letra/canción) actualizados para que el cerebro sepa que este
  widget cubre también esos casos.
- **2026-08-12 — la hoja pasa a tener CUATRO PESTAÑAS, ficha DINÁMICA y tamaño manejable.** Petición del operador
  (literal, con el porqué): «este widget va a ser utilizado de forma genérica para multitud de búsquedas complejas,
  y entonces siempre vamos a seguir más o menos los mismos patrones». De ahí las cuatro cosas de este cambio.
  · **ESCALABLE.** La hoja tenía **620px fijos** en su propio CSS, así que «ponlo a pantalla completa» dejaba una
    columna estrecha en medio de la pantalla: el ancho no era del canvas, era de aquí. Ahora es `width:100%` y el
    reparto en columnas lo hace el CSS por el ANCHO REAL (`auto-fill` + `minmax` con mínimo por riqueza de tarjeta
    y TOPE de columnas), así que reflowea sola al arrastrar. La maquinaria de tamaño es del CANVAS porque sirve a
    todo widget (ver `frontend/app/widgets/desktop.js`): ocho tiradores (4 esquinas + 4 bordes), botón ⤢ de
    maximizar/restaurar, y la geometría VIAJA en `_layout()` — antes solo se guardaba la posición, así que agrandar
    la hoja y recargar la devolvía a su tamaño de fábrica. El tamaño preferido lo declara el manifest (`size`),
    porque una superficie de ancho fluido no puede deducirlo de su contenido.
  · **CUATRO PESTAÑAS** (`tab` persistida, como `view`/`focus` — la mueve el clic Y la voz): RESULTADOS ·
    SUMARIO (estado, cuántos explorados/descartados, bitácora de lo hecho) · FUENTES (cada web y QUÉ PASÓ ahí:
    entró · le limitaron a 50 · pedía login · bloqueó · error) · CRITERIOS (el encargo tal y como se ejecuta, con
    las correcciones del operador). Acciones nuevas `tab`/`sources`/`progress`/`criteria`, todas FAST.
    **Las FUENTES son la pieza que faltaba para poder auditar una búsqueda:** hasta hoy «no encontré nada» y
    «Wallapop me pedía login» se veían exactamente igual, así que el operador no podía saber si convenía entrar
    él a mano. Los CRITERIOS **se siembran solos** desde el brief (`nucleo/research.py::to_criteria` llamado en
    el pre-vuelo de `dispatch`): si dependieran de que el worker se acuerde de escribirlos, faltarían justo en
    las búsquedas que peor van. El `goal` hace de firma del encargo → una investigación DISTINTA vacía la hoja de
    la anterior (una ronda 2 conserva el objetivo, así que «sigue buscando» no borra nada).
  · **FICHA DINÁMICA (`blocks`).** El operador pidió «una ficha HTML para cada resultado diferente». HTML crudo de
    un worker que acaba de leer la web abierta es una inyección esperando a ocurrir, así que se resolvió con un
    vocabulario CERRADO de bloques de composición —`text`/`facts`/`chips`/`gallery`/`meter`/`table`/`link`/
    `section`— que dan la misma libertad de forma y se pintan con `textContent`. Un `kind` desconocido se descarta
    ENTERO (no se degrada a texto: sería colar contenido de un tercero por otra puerta).
  · **LA VALORACIÓN por fin se ve.** `score` estaba en el esquema desde el 2026-08-09 y **no se pintaba en ningún
    sitio**: se guardaba y se perdía. Ahora sale como etiqueta en la tarjeta y desplegada con su barra y su
    **porqué** en el expediente — una nota sin el porqué no se puede discutir ni corregir.
  Dos hallazgos de paso, ninguno buscado: (1) un `widget.js` hace `el.className="…"` y **se lleva por delante la
  clase `hb-body`** de su raíz, así que cualquier regla del canvas sobre ella no aplicaba a nadie → el scroll pasa
  a un envoltorio propio (`.hb-scroll`) y las pestañas se quedan fijas (`position:sticky`) al recorrer una lista
  larga; (2) «pantalla completa» eran DOS cosas y solo existía la nativa, que tapa el orbe y el chat — pésimo
  justo aquí, donde el operador agranda la hoja PARA seguir corrigiendo la búsqueda por voz. Ahora por defecto se
  maximiza dentro de la app y la nativa la pide el widget en su manifest (`"fullscreen":"native"`, el vídeo).
- **2026-08-12 (2º pase) — pulido de vista, diseño gráfico y DOC AL MÍNIMO para embeber.** Petición del operador:
  «márgenes, padding, detalles, optimización de la vista… asegúrate de que la doc está optimizada para que la use
  el sistema, todo al mínimo para embeberlo… dale un toque de diseño gráfico».
  · **DOC PARTIDA EN DOS AUDIENCIAS, medido.** `widgets/brief.py::for_prompt` mete el `usage` COMPLETO en el prompt
    de CADA turno mientras el widget está abierto — y esta hoja está abierta justo durante una investigación larga,
    que es cuando el operador más habla. El `usage` del primer pase eran **4.868 chars** (~1,2k tokens por «¿cómo
    va?»), exactamente el despilfarro que prohíbe la norma «las tools, de menos a más». Ahora: `usage` = 526 chars
    (solo lo que el CEREBRO no puede deducir: las cuatro pestañas y su disparador, el ordinal del detalle, y que una
    hoja vacía no es un resultado) y el contrato de relleno entero se muda a **`worker_guide`**, que viaja SOLO en
    `read_widget` — bajo demanda, una vez por tarea, a quien lo necesita. **Coste de tener la hoja abierta: 5.000 →
    740 chars de prompt.** Con techo en test (`test_reset_blank_surfaces.py`) para que añadir doc obligue a recortar.
  · **DIGEST con techo propio** y ORDENADO POR IRREEMPLAZABILIDAD. El encabezado (sumario+fuentes+criterios) va
    delante del listado, así que sin límite unos criterios largos empujaban los RESULTADOS fuera del recorte: el
    cerebro sabría con qué se busca pero no qué se ha encontrado. Ahora 620 chars de techo, las fuentes ANTES que
    los criterios (el estado de una fuente solo lo sabe esta pantalla; los criterios se dijeron en voz alta y el
    cerebro los tiene en la conversación) y, dentro de las fuentes, las FALLIDAS primero.
  · **LA LISTA SE BARRE, EL EXPEDIENTE SE LEE.** Visto en pantalla: con las fichas pintando todos sus bloques, UNA
    tarjeta llenaba la hoja entera — y desde que la entrega por defecto son DIEZ resultados eso hace la lista
    irrecorrible. La lista se queda con los bloques ligeros (`chips`) más, como excepción, un `text` de tono AVISO
    (una salvedad importante detrás de un clic es justo lo que prohíbe la regla de presentación); lo pesado —tabla,
    galería, sección, medidor— es lo que uno va a buscar al abrir. El `badge` sube a la fila del título: al pie
    acababa junto a «Ver detalle» y se leía como un segundo botón. Y la valoración sube en el expediente: es el
    VEREDICTO, no un dato al final.
  · **SISTEMA en vez de números sueltos.** Había trece tamaños de letra y márgenes de 3/5/6/7/8/9/10/11px elegidos
    uno a uno. Ahora una escala de cuatro pasos + rejilla de 4px en variables locales, con un test que acota las
    magnitudes crudas. Toque de diseño: **cifras tabulares** en todo lo que se compara (precio, nota, recuentos,
    tablas) —dígitos de anchura distinta obligan a releer para saber cuál es mayor—, el subtítulo deja de ser
    turquesa y en negrita (competía con el precio: en una ficha solo puede ganar un dato), el filete de acento se
    queda SOLO en la destacada (diez barras azules son un código de barras), la unidad repetida de las fuentes baja
    a minúscula (seis «RESULTADOS» en versalitas gritaban más que los números) y las fuentes sin aprovechar tienen
    su propia casilla en color de aviso, que es el único dato del sumario que pide una decisión.
  · Dos fallos propios cazados por herramientas y no a ojo: `node --check` pilló **acentos graves dentro del
    template literal** del CSS (cerraban la cadena), y el banco de pruebas pintaba el dict CRUDO sin cruzar
    `data.py` — así que no veía que `facts` se escribe como objeto y se guarda como lista. El banco ahora sanea el
    fixture por `apply_action`/`view_data`, como en vivo.
- **2026-08-12 (3er pase, CIERRE) — la cabecera dice LA TAREA, no el nombre de la pieza.** Petición del operador,
  literal: «no hace falta que la gente sepa que eso es el visor o que eso es la muestra de resultados, sino es lo
  que le hemos pedido puesto ahí». En una superficie GENÉRICA el nombre del catálogo («Resultados») no identifica
  nada: lo que identifica esa tarjeta es el ENCARGO que está mostrando.
  · **`live_title` en el manifest** (opt-in POR widget, no global — el reloj y la agenda sí se identifican por su
    nombre y cambiárselo a todos sería una regresión). El canvas lo lee del índice compacto y pone `data.title` en
    la cabecera de la tarjeta, alineado a la izquierda y con elipsis; el nombre canónico —cómo se dirige por voz—
    NO se pierde: queda en el tooltip y en el panel de alias (⚙). Sigue a los datos también al REFRESCAR, porque
    una búsqueda nueva cambia el título y dejar el viejo es un rótulo que miente sobre lo que hay debajo.
  · **El título se dice UNA vez.** El canvas marca el div de montaje con `data-host-title` ANTES de pintar, y el
    widget omite su propio `hr-hd`: repetirlo en cuerpo mayor era el mismo texto dos veces a 4px de diferencia y
    una línea perdida en la cabecera pegajosa, que es el sitio más caro de la hoja. Se conserva el pintado propio
    como respaldo por si algún día esta superficie se monta sin la cabecera del canvas.
  · **Alto acotado**: el subtítulo real llegaba a tres líneas; se limita a DOS en pantalla (`-webkit-line-clamp`) y
    el texto íntegro va al tooltip — controlar el espacio no es lo mismo que recortar el dato.
  **Tres fallos reales cazados en este pase, ninguno a ojo:**
  1. El `widget.js` estaba **ROTO en producción**: un comentario nuevo con acentos graves dentro del template
     literal del CSS cerraba la cadena → el módulo no importaba y la tarjeta habría dicho «no se pudo cargar». Es
     la SEGUNDA vez en un día, así que ahora hay un guard permanente para TODO el catálogo
     (`tests/browser/unit/widgets/test_widget_js_parses.py`: `node --check` por fichero + un test que señala el
     acento grave con fichero y línea, porque el SyntaxError del stdin no dice dónde está).
  2. `.hb-head` acababa en `right:40px` cuando los botones de la derecha son DOS desde que existe ⤢ (ocupa de 38 a
     64): un título largo se le metía por debajo. Invisible con un rótulo corto y centrado, evidente con una frase.
  3. **El hueco de la rejilla tenía dos fuentes de verdad y costó una columna.** Al subir la escala de espaciado de
     12 a 14px, `gridStyle` siguió restando 12: el suelo de cada pista quedaba 2px por encima de lo que cabía y
     `auto-fill` bajaba de dos columnas a UNA en una hoja de 1.420px — se ve como «maximizar ya no aprovecha el
     ancho» y no se deduce leyendo el diff. Ahora el cálculo lee `var(--s3)`, la misma variable que lo pinta.
  Y de paso: el título de la ficha destacada llevaba `15.5px` crudo de cuando el cuerpo era 14, así que con la
  escala nueva quedó **más pequeño** que el de sus hermanas. Un número fuera de la escala no se entera de que la
  escala cambió: hereda, y ya destaca por fondo, borde y badge. Hay techo en test para los tamaños crudos.
