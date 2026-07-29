# V2-058 — Widget de música potente estilo Spotify (conducido por brain workers)

**Origen (operador, 2026-07-21):** «coge el widget de música (Spotify o YouTube sin vídeo) y dale la estética lo
más parecida a Spotify: listas que se crean por voz y donde añadir canciones, controles manuales Y por voz
("pon música", "quita esto", "pausa", "ponme a Bruce/Madonna"), varias vistas, práctico. El FlashBrain tiene que
saber que existe el widget y, cuando esté abierto, que las órdenes de voz van a él. "Hazme una lista random de
música disco" → el sistema la prepara con el FlashBrain + un cloud-code worker. La pantalla se adapta a lo que
suena (si reproduzco un disco, se ve el disco; volver atrás → home con listas/más escuchadas).» Es un **test real
de brain workers**: conducidos por el agente, guiados, para verlos evolucionar el widget en vivo.

Estado: **EN CONSTRUCCIÓN** — rama `feat/musica-spotify` (se fusiona a main al terminar; no queda suelta).

---

## Arquitectura (invariantes)
- `musica` es un **widget de SISTEMA hand-built** (importa el core: `connectors.music` + `connectors.spotify` +
  `config.credentials`; corre en el proceso del server). El **generador** NO puede tocarlo (genera sandbox
  stdlib-only) → lo evoluciona un **brain worker `kind=code`** (Read/Write/Edit) guiado, o a mano. No convertir
  `musica` en widget generado.
- **Reproducción = el conector existente** (`connectors/music/`): Spotify cuando hay cuenta conectada;
  **YouTube-audio GRATIS por defecto** (funciona sin conectar nada, player oculto en el navegador). NO reinventar
  el backend: el widget es la CARA + las LISTAS + las VISTAS; la reproducción va por `connectors.music.control()`
  y por la tool `play_music` del FlashBrain.
- **Latencia**: leer estado del widget = µs (state.json). Curar una lista (worker) = off-hot-path, asíncrono.
- **Persistencia**: las listas viven en el estado del widget (`widgets/_data/musica/state.json`), separado del
  código (regla V2-017). Nunca se pierden al regenerar/modificar.

## Modelo de datos (state.json)
```
{
  "connected": bool, "provider": "spotify|youtube", "mode": "spotify|youtube|idle",
  "now_playing": {title, artist, album, art, playing, videoId|uri, source_list},
  "view": {"kind": "home|playlist|album|artist|nowplaying", "id": ""},   # qué pinta la tarjeta AHORA
  "playlists": [ {"id","name","art","tracks":[{title,artist,album,art,uri|videoId,dur}]} ],
  "recent":   [ {track...} ],        # últimas reproducidas (cap ~30)
  "top":      [ {track..., "count"} ] # más escuchadas (derivado de recent)
}
```

## Vistas (la tarjeta se adapta)
- **Home**: cabecera + fila "Tus listas" (portadas) + "Más escuchadas" + "Recientes". Barra de reproducción abajo.
- **Playlist**: portada grande + nombre + tracklist con play por fila; botón ▶ "Reproducir lista".
- **Álbum**: disco + tracklist (cuando se pide "el disco X de Y").
- **Artista**: top canciones del artista + botón reproducir.
- **Now-playing**: portada grande de lo que suena + controles + progreso; ← vuelve a `home`.
- Navegación por click Y por voz. `view` en el estado manda lo que se ve; play_music / data-ops la cambian.

## Acciones del widget (manifest `actions`, data-ops FAST del FlashBrain)
- `create_playlist {name}` · `add_to_playlist {playlist, track|query}` · `remove_from_playlist {playlist, item}`
- `play_playlist {playlist}` · `play_album {album, artist}` · `play_artist {artist}`
- `open_view {kind, id}` (home/playlist/album/artist/nowplaying) · `back`
- control (ya existe): play/pause/resume/next/previous/volume/queue/ended
- `set_tracks {playlist, tracks[]}` (lo usa el WORKER de curación para poblar una lista)

## Voz (FlashBrain)
- El widget declara `keywords` + `usage` → el FlashBrain sabe que existe. Cuando está ABIERTO (en `open_widgets`),
  las órdenes de música se resuelven CONTRA él (data-ops), no crean otro ni escalan.
- `play_music` sigue siendo la tool de reproducción (difusa/artista/canción). Se AMPLÍA la guía para: reproducir
  una LISTA propia ("reproduce mi lista X" → `play_playlist`), un ÁLBUM ("el disco X de Y" → `play_album`),
  un ARTISTA ("ponme a Bruce" → `play_artist`), y crear/añadir (`create_playlist`/`add_to_playlist`).
- **Curación = escalada**: "hazme una lista random de música disco / para concentrarme / lo mejor de los 80" →
  `escalate_to_slowbrain` → worker cura N tracks (WebSearch) → `set_tracks` puebla la lista → aviso por voz+UI.

## Fases (conducidas por brain worker, guiadas, con reinicio+verificación entre cada una)
1. **Datos + Home + controles**: modelo de listas/recent/top en `data.py` + acciones create/add/play_playlist +
   `widget.js` con estética Spotify (home + barra de reproducción) sobre el player/estado que ya existe.
2. **Vistas** playlist/álbum/artista/now-playing + navegación (click+`open_view`/`back`) + pantalla adaptativa.
3. **Routing de voz**: guía de `play_music` (lista/álbum/artista/crear/añadir) + data-ops contra el widget abierto
   + paridad probe/provider + tests del router.
4. **Curación por worker**: guía de escalada + acción `set_tracks` + demo "lista random disco" e2e.

## Bitácora
- **2026-07-21** · **Fase 1 construida por un BRAIN WORKER** (kind=code, guiado por la spec de esta iniciativa): data.py con modelo playlists/recent/top + acciones create_playlist/add_to_playlist/remove_from_playlist/play_playlist/open_view/back + ref_index; widget.js con estética Spotify (HOME: Tus listas · Más escuchadas · Recientes + barra de reproducción) y vista PLAYLIST; manifest actualizado. Validado: view_data OK, crear/abrir/volver funcionan, YouTube-audio y Spotify preservados. Vistas álbum/artista/now-playing (Fase 2) caen a home hasta implementarlas. LECCIÓN (→ V2-059): sin observabilidad estructurada costó ver el avance del worker + una nota vieja del susurro contaminó un 1er intento (creó un widget basura «sistema-susurro-repara», borrado); el 2º intento limpio salió bien.
- **2026-07-21** · Creada. Feature-list + arquitectura + fases como brief para conducir a los brain workers.
