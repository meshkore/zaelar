# imagenes — notas

- **2026-08-28 · nace (V2-457).** Pedido por el operador tras probar a mano «una foto real del Ferrari Amalfi»:
  el resultado acabó en la hoja genérica de `results`, que es una tabla, no un visor. Lo que pidió, literal:
  «una imagen a tamaño completo, debajo del todo la lista de miniaturas, controles para ir a derecha e
  izquierda, que al seleccionar una miniatura se ponga en grande, todo manejable por voz, y arriba un título de
  qué fotografías estamos viendo incluso con la fuente».
- **Es un VISOR, no un editor.** Rechazado a propósito: recorte, filtros, descarga, presentación automática.
  «Sin grandes virguerías... un previsualizador, sin edición, sin funciones extrañas.»
- **No busca.** `data.py` es stdlib y sin red por contrato de widget; las imágenes se las da quien llama
  (`show_images` en el turno rápido, o un worker cuando hay que curar). Si alguna vez parece que el visor
  «debería buscar solo», eso va en `nucleo/flash/image_turn.py`, no aquí.
- **La foto actual es un ÍNDICE, no una copia de la fila.** Guardar el item duplicado hace que la grande y la
  miniatura marcada se separen en cuanto el conjunto se reordena o se recarga.
- **`show` vacío NO borra lo que hay en pantalla**: devuelve `ok:false`. Dejar el visor en blanco porque una
  búsqueda no encontró nada le quita al operador lo que sí tenía.
- **Fuente visible siempre**: se nombra el SITIO y se enlaza la PÁGINA, nunca solo la URL de la imagen (una URL
  de CDN dice `cdn.ferrari.com` pero no quién lo publicó).
- **Imágenes locales**: `local` lee `widgets/_data/imagenes/` y las sirve por `/widgets/imagenes/asset/<name>`
  (ruta ya existente, path-safe). `.svg` queda fuera a propósito: es un documento que puede llevar script.
- **2026-09-03 · el escenario cae a la copia del BUSCADOR (V2-563).** Cada fila trae DOS direcciones de la
  misma foto: el fichero del editor (`url`) y la copia del índice (`thumb`). Solo la primera puede morir, y
  muere: medido en «moto de cross», la foto 1 de 12 era un **404** en enduro21.com mientras el índice servía
  esa MISMA foto como un JPEG vivo de 480×290 — por eso la tira de abajo se veía llena y el escenario decía
  que la imagen ya no carga. **La foto nunca faltó; faltaba nuestra copia.** Se pide el original, se cae a la
  copia y solo entonces se da por perdida. El cambio se DICE («· vista previa») y el marcador se RETIRA si la
  copia también está muerta: anunciar una vista previa al lado de «no carga nada» es peor que cualquiera de
  los dos mensajes por separado.
- **Las dimensiones que se pintan son del FICHERO, no de la miniatura.** El DOM de Yandex entrega el tamaño de
  la baldosa, así que `parse_yandex_rows` ya no las publica (0, como la pata de Bing). Una foto anunciada como
  «480×290» cuyo original era un 404, y una «213×320» cuyo original era un PNG de 2,2 MB. Un tamaño
  desconocido se ve desconocido; uno equivocado no.

