# personalizado-reproduzca-video — notas

- 2026-07-23: pedido por el operador — widget PERSONALIZADO dedicado en exclusiva a reproducir el vídeo del gol
  de la "Mano de Dios" de Maradona (Argentina 2-1 Inglaterra, México 86). Constraint explícita: "el widget debe
  estar listo para reproducir el vídeo cuando se abra" → videoId fijo (`uq6IJTtsz_Q`, hardcoded en `data.py`),
  autoplay inmediato (en silencio, por la política del navegador — "quita el silencio" para oírlo). A diferencia
  del widget genérico `youtube` (que admite `load` para cargar cualquier vídeo por URL/búsqueda), este NO admite
  cambiar de vídeo — solo controlar la reproducción (play/pause/mute/unmute/volume_up/volume_down/set_volume/
  restart). Nota: sus keywords ("mano de dios", "gol de maradona"…) se solapan a propósito con las del widget
  `youtube` (que ya trae este mismo vídeo sembrado por defecto) — es el mismo contenido, dos widgets distintos;
  no se ha tocado `youtube` para no salirse del encargo.
