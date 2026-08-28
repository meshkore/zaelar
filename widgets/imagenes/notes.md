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
