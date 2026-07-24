# tarea-navegador — notas de contexto

Panel lateral vertical (máx 200px de ancho) para mostrar el progreso de tareas
automáticas del navegador (búsquedas, automatizaciones).

## Diseño

- **Arriba**: miniatura del navegador (última captura del widget navegador)
- **Abajo**: 10–12 líneas de estado/progreso de la tarea actual
- **Redimensionable**: el usuario puede arrastrar el borde derecho para ajustar
  el ancho (100–200px)
- **Título** de la tarea y contador de progreso opcional

## Datos

El cerebro (Hermes) empuja las líneas de progreso mediante el protocolo de
widgets (`[[push:tarea-navegador]]{...}[[/push]]`). También puede usar
`[[widget.data:tarea-navegador]]{"action":"push_lines","payload":{...}}[[/widget.data]]`.

El navegador (owner.py de `navegador`) también puede notificar su progreso
escribiendo directamente en el store de `tarea-navegador` mediante
`store.save("tarea-navegador", db)`.

## Acciones

| Acción | Payload | Uso |
|---|---|---|
| `push_lines` | `{ "lines": ["paso 1...", "paso 2..."] }` | Añadir líneas de progreso |
| `set_title` | `{ "title": "Buscando en Wallapop" }` | Cambiar título de la tarea |
| `set_progress` | `{ "progress": "3/6" }` | Actualizar contador de progreso |
| `clear` | `{}` | Limpiar todo el panel |

## Tema

Sigue el contrato `--hb-*` para heredar el tema claro/oscuro automáticamente.
