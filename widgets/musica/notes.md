# musica — notes

- **Widget de SISTEMA hand-built** (no generado): importa el core (connectors.music/spotify, config.credentials).
  El generador NO puede tocarlo. Evolucionarlo a mano o con un brain worker `kind=code` guiado (V2-058).
- **V2-041 (base):** cara de conexión de Spotify (botón → login en ventana; avanzado = client_id propio) +
  control de reproducción por botones (ctx.action → connectors.music.control). La reproducción por VOZ va por la
  tool `play_music` del FlashBrain, NO por widget_data.
- **Reproducción GRATIS por defecto = YouTube-audio OCULTO** (iframe sin vídeo, bloque `yt` en el store, controlado
  por postMessage). ARRANQUE GARANTIZADO: mute=1 → unMute por API; onReady/onStateChange(ENDED) por handshake
  `listening`. NO recargar el iframe salvo cambio de videoId (recargarlo reinicia la canción). NO tocar el core.
- **V2-058 Fase 1 (2026-07-21):** estética SPOTIFY + LISTAS. `data.py` añade modelo persistido en el store
  (`playlists`, `recent`, `counts`→`top` derivadas, `view`) + acciones `create_playlist`, `add_to_playlist`,
  `remove_from_playlist`, `play_playlist`, `open_view`, `back` + `ref_index` (listas referenciables por nombre).
  `widget.js` reescrito: vista HOME (Tus listas + Más escuchadas + Recientes + barra de reproducción abajo) y vista
  PLAYLIST (portada + tracklist con play/quitar por fila + ▶ Reproducir lista). Clases propias `hb-mus2-*`.
  - **Invariante de persistencia:** view_data compone {db persistido} + {vivo: connected/mode/now_playing} + top.
    Guardar SIEMPRE el compuesto (`_persist`) para no pisar `yt`/playlists/counts. youtube_audio hace RMW del `yt`.
  - **Player oculto persistente:** `el._ytHost` NO se reconstruye al re-render (navegar entre vistas no corta la
    música); solo `el._viewHost` se rebuilda. `syncYtPlayer` recrea el iframe solo si cambia el videoId.
  - **Aesthetic:** verde Spotify fijo `--sp-green:#1DB954` SOLO para botones de play (color de marca, igual en
    ambos temas, como los KIND fijos de agenda); TODO lo demás con variables `--hb-*` (tema claro/oscuro).
  - **play_playlist:** la 1ª canción suena ya (control play), el resto a la cola (control queue). Registra
    reciente/más-escuchada la 1ª. `top` se deriva de `counts` (nº de reproducciones desde el widget). La voz
    (play_music) NO pasa por apply_action → en Fase 1 no alimenta recientes; pendiente para fase de routing de voz.
  - Fases pendientes (V2-058): 2 = vistas álbum/artista/now-playing + navegación adaptativa; 3 = routing de voz
    (guía play_music lista/álbum/artista/crear/añadir + paridad probe/provider); 4 = curación por worker (set_tracks).
