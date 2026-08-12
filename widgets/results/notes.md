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
