# youtube — notas

- 2026-07-20 (susurro): el operador (Ricart) pidió "el último vídeo de José Luis Cárpatos" y el widget traía
  el PRIMER resultado por relevancia (no el más reciente). Fix quirúrgico en `data.py::_search_id`: si la frase
  pide el vídeo MÁS RECIENTE (`_LATEST_RE`: último/reciente/nuevo/latest/…) se ordena por fecha de subida
  (`&sp=CAI%3D`). Intención clave del operador: "el último de <persona>" = su vídeo más nuevo, no uno cualquiera.
- 2026-07-23: pidió el último vídeo de "las cuatro claves de la semana" de José Luis Cárpatos. La búsqueda+
  reproducción ya la resolvió el sistema en vivo (`_search_id` + `apply_action("load")`, sin cambio de código).
  Actualizada la `_SEED` por defecto a este vídeo ("Momento Kimi para la IA…", `6V2lKeUE8YA`) como el que se
  muestra al operador, sustituyendo la semilla anterior (gol de Maradona).
- 2026-07-23 (repetición): nueva petición de "busca y carga el vídeo solicitado por Ricart" sin id/URL concretos
  en el ticket — de nuevo la resuelve el flujo en vivo existente (`load` → `_search_id` si no hay URL/id →
  `apply_action` actualiza `videoId`/título/canal/`published` y el widget recarga el iframe). No hace falta
  ningún cambio de código: el mecanismo de búsqueda+carga+verificación (canal/fecha en pantalla, V2-057) ya
  cubre este caso; no tocar `data.py`/`widget.js` sin un vídeo concreto que difiera del comportamiento actual.
- 2026-07-23 (sin sonido en el dispositivo de Ricart): causa raíz — el vídeo arranca `muted=1` (autoplay lo exige)
  y el "unmute" pedido POR VOZ no lleva ningún gesto real de usuario en la página; Chrome puede bloquear el audio
  al desmutear por script sin gesto y el widget queda mostrando "🔊 Sonido" mientras el vídeo sigue mudo de verdad
  (estado engañoso). Fix quirúrgico en `widget.js`: (1) el botón "🔇 Silencio"/"🔊 Sonido" ahora dispara el
  `postMessage` de `unMute`+`setVolume` DIRECTO en el propio handler de click (gesto real, no espera al roundtrip
  de `ctx.action`) — audio garantizado al pulsarlo; (2) nuevo overlay "🔊 Toca para activar el sonido" sobre el
  frame, visible SOLO mientras `data.muted` es true, con el mismo click directo — cubre el caso "unmute" pedido
  por voz: el operador ve el aviso y con un toque real se oye. No se tocó `data.py` (el estado/comandos servidor
  ya eran correctos); es puramente el gesto de usuario que exige el navegador para audio no-mudo.
- 2026-07-23 (arranque en blanco): pedido explícito de Ricart — el reproductor NO debe traer ningún vídeo
  precargado al abrirse por primera vez. Fix quirúrgico en `data.py::_SEED`: videoId/title/url/channel/published
  vacíos, `latest=False`, `paused=True`, `last_cmd=""` (antes traía semilla fija "Momento Kimi…"). `widget.js` no
  necesitó cambios: ya pintaba el estado vacío ("No hay ningún vídeo cargado. Dime qué quieres ver.") cuando
  `videoId` está vacío. Un store existente con un vídeo ya cargado no se resetea (`store.load` solo aplica la
  semilla si no hay estado previo); esto afecta a instalaciones NUEVAS o tras borrar el widget.
- 2026-07-23 (aplicación real, para Ricart): el fix de `_SEED` de arriba no bastaba porque el store PERSISTIDO
  (`widgets/_data/youtube/state.json`) ya tenía cargado "Las 4 claves de la semana" (`6V2lKeUE8YA`) de la petición
  anterior — `store.load` no reaplica la semilla sobre un estado existente. Se limpió a mano ese `state.json` a
  los mismos valores en blanco de `_SEED` (videoId/title/url/channel/published vacíos, `muted=true`,
  `paused=true`, `last_cmd=""`) para que el canvas de Ricart muestre YA el estado vacío ("No hay ningún vídeo
  cargado…") sin esperar a una reinstalación. No se tocó código: `data.py`/`widget.js`/`manifest.json` sin cambios.
- 2026-07-23 (verificación): re-solicitud del mismo cambio ("que el reproductor empiece en blanco, reflejado en
  la config real"). Verificado: `data.py::_SEED` ya en blanco Y `widgets/_data/youtube/state.json` ya coincide
  (`videoId/title/url/channel/published` vacíos, `paused=true`, `muted=true`, `cmd_seq` conservado) — ambos fixes
  de arriba siguen en pie, no hacía falta ningún cambio adicional de código ni de estado.
- 2026-07-23 (re-verificación, 2ª vuelta): tercera petición idéntica ("quita el vídeo por defecto, arranca en
  blanco en la plataforma real"). Confirmado de nuevo: `_SEED` sin vídeo por defecto Y `state.json` persistido
  ya reflejan el estado en blanco — NO hacía falta tocar código ni datos, ya cumplido desde las dos entradas
  anteriores. Si una futura sesión ve un vídeo precargado en el canvas real, sospechar de OTRA escritura
  posterior (una carga por voz/tool) sobreescribiendo el estado, no de una regresión de esta semilla.
- 2026-07-23 (Opel Frontera): petición de "busca y carga el vídeo del Opel Frontera pedido por el operador,
  asegurando que se reproduzca correctamente". Igual que las entradas anteriores de búsqueda-por-nombre: el
  mecanismo ya existente (`apply_action("load", {"query": "..."})` → `_search_id` resuelve el id + título/canal/
  fecha → `_bump` marca `paused=False` y sube `cmd_seq` → `widget.js` reconstruye el `<iframe>` con el nuevo
  `videoId` y aplica el estado tras el `load` del iframe) ya cubre esta carga y su reproducción sin ningún cambio
  de código. No se tocó `data.py`/`widget.js`/`manifest.json`: no había un vídeo/id concreto en el ticket que
  exigiera lógica nueva, y el flujo de carga+autoplay+verificación (canal/fecha en pantalla) es genérico para
  cualquier búsqueda, incluida "Opel Frontera".
- 2026-07-23 (activar sonido, Ricardo): petición de "activa el sonido y confirma que se refleja en el widget"
  sobre el vídeo del Opel Frontera ya cargado. Verificado en `widgets/_data/youtube/state.json`: `muted=false`,
  `volume=70`, `last_cmd="unmute"`, `cmd_seq=9` — el `unmute` ya se aplicó (vía `apply_action("unmute")`, el
  mismo flujo de siempre) y `widget.js` ya lo refleja con el estado actual: botón "🔊 Sonido", overlay
  "toca para activar el sonido" oculto (`E.unmuteHint.style.display` solo se muestra con `data.muted`) y
  `vol 70` en vez de "silencio". No hizo falta ningún cambio de código: `data.py`/`widget.js`/`manifest.json`
  sin tocar — el mecanismo de unmute+reflejo de estado ya cubre este caso.
- 2026-07-23 (nueva acción "close"): pedido explícito de cerrar el vídeo cargado, asegurando que se detenga DE
  VERDAD en el navegador (no solo cambiar datos locales/el "espejo"). No existía ninguna data-op para descargar
  el vídeo ya cargado (solo play/pause/mute/…/restart). Añadida `apply_action("close")` en `data.py` (vacía
  videoId/title/url/channel/published/latest, fuerza `paused=true`/`muted=true`, `_bump` con `cmd="close"`) +
  entrada `"close"` en `manifest.json` `actions` (+ mención en `usage` + keywords "cierra el vídeo"/"cierra el
  video"/"quita el vídeo"/"detén el vídeo"). NO hizo falta tocar `widget.js`: al vaciarse `videoId`, `render()`
  ya detecta `st.id !== id` y RECONSTRUYE la tarjeta sin `<iframe>` (el elemento del reproductor se destruye →
  el vídeo deja de reproducirse de verdad, no un efecto solo local) y pinta el estado vacío ya existente ("No hay
  ningún vídeo cargado. Dime qué quieres ver."). Mismo mecanismo que "arranque en blanco" de más arriba, ahora
  accesible como acción explícita en cualquier momento, no solo como semilla inicial.
- 2026-07-23 (Madonna → Dirty Dancing): petición de cerrar el vídeo de Madonna cargado y poner el de Dirty
  Dancing. Verificado en `widgets/_data/youtube/state.json`: `videoId="XINddkzfTzM"` ("The Time of My Life -
  Dirty Dancing (12/12) Movie CLIP", canal Movieclips, `paused=false`, `last_cmd="load"`, `cmd_seq=13`) — el
  `load` (con `query`/URL de Dirty Dancing) YA reemplaza directamente el vídeo anterior sin necesitar un `close`
  intermedio (cargar uno nuevo siempre reconstruye el `<iframe>` con el `videoId` nuevo, exactamente igual que
  cerrar+cargar). No hizo falta ningún cambio de código: `data.py`/`widget.js`/`manifest.json` sin tocar — el
  mecanismo genérico de `load` (búsqueda o URL/id directo) ya cubre sustituir un vídeo por otro.
- 2026-07-23 (Madonna → Dirty Dancing, re-verificación): repetición de la misma petición. Confirmado de nuevo en
  `widgets/_data/youtube/state.json`: `videoId="XINddkzfTzM"` (Dirty Dancing, canal Movieclips), `paused=false`,
  `last_cmd="load"`, `cmd_seq=13` — el estado real YA refleja Dirty Dancing cargado y en reproducción (Madonna ya
  no está); nada de Madonna queda en el reproductor. Sin cambios de código: `data.py`/`widget.js`/`manifest.json`
  intactos, el mecanismo `load` ya cubrió el reemplazo en la vuelta anterior.
- 2026-07-23 (corrección de spelling en la búsqueda): petición de buscar y reproducir el videoclip correcto de
  "Dirty Dancing", corrigiendo un error de spelling detectado en la petición original (variante mal escrita del
  título). Verificado en `widgets/_data/youtube/state.json`: `videoId="XINddkzfTzM"`, `title="The Time of My Life
  - Dirty Dancing (12/12) Movie CLIP (1987) HD"`, `channel="Movieclips"`, `published="hace 14 años"`,
  `paused=false` — el mecanismo genérico `load`→`_search_id` ya normaliza/corrige la query de búsqueda hacia el
  título real de YouTube (la búsqueda no depende de que el operador escriba el título con spelling exacto) y ya
  entregó el clip correcto y verificable (canal+fecha en pantalla, V2-057). No hizo falta ningún cambio de código:
  `data.py`/`widget.js`/`manifest.json` sin tocar — no había una variante de spelling concreta en el ticket que
  exigiera lógica nueva de normalización más allá de la búsqueda existente.
