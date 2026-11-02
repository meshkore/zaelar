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
- **favorite_current (2026-07-26):** nueva acción sin payload que guarda la canción sonando AHORA (Spotify o
  YouTube-audio, vía `_current_track`) en la lista "Favoritos de Manolo" (la crea si no existe, dedup por
  título+artista). Botón ♥ en la barra de reproducción (`playbackBar`, solo si hay `now_playing`). El nombre de la
  lista queda hardcodeado — zaelar es single-operator, no hay concepto de "usuarios" múltiples; si se pide
  generalizar a "el operador" en vez de un nombre fijo, hay que revisar esto.
- 2026-08-27 (V2-384, medido por el arnés): «guárdamelo en una lista que se llame Curro» → «Hecho.» y nada
  detrás. El modelo emite UNA data-op y el caso exigía dos (create + add) — y add_to_playlist además fallaba
  con lista inexistente y exigía canción explícita. Ahora: `_find_or_create_playlist` compartido,
  `add_to_playlist {playlist}` crea la lista si falta y sin canción guarda LA QUE SUENA (resuelta antes de
  crear nada — un guardado fallido no deja lista vacía); `favorite_current {playlist}` acepta destino nombrado.
  Dedup por título+artista. En el mismo V2-366/384: el listener de `ended` filtrado por id `hb-musica`
  (cross-talk con el widget de youtube) y los favoritos dejan de llamarse «Favoritos de Manolo».
- 2026-09-09 (V2-629): real cover art, fast then cached. YouTube-audio tracks get a FREE thumbnail the
  instant a videoId resolves (`connectors/music/youtube_audio.py::_yt_thumb`, zero extra network call);
  anything else asks iTunes lazily, once per song ever (`_enrich_art`, cached in `art_cache`, stripped from
  what `view_data()` returns to the wire). Every emoji control became an inline SVG matching the app shell's
  icon language; the heart reflects `data.fav_current`. Real bug found by rendering, not reading: `_SW` +
  an appended `fill="currentColor"` never overrides — the HTML parser keeps the first duplicate attribute —
  so the "solid" play/pause icons were rendering as hairline outlines; fixed with a separate solid attribute
  set (`_SF`). Coordinated with memoria-dev over the cluster about a future listening-preference path; no
  memory code touched here.

## 2026-09-09 — V2-630/V2-631 (canvas + connector, not this widget's code)
- `manifest.json` declares `"size": {"w": 468}`: the card's deterministic first footprint. The canvas now
  FREEZES every card's size after its first render (V2-630, `desktop.js::_freezeSize`) — the bar's long
  titles ellipsize inside a stable card instead of resizing it per song.
- The free source skips now: `connectors/music/youtube_audio.py` implements `next()`/`previous()` over the
  queue + a bounded history; the canned «no puedo saltar de canción» refusal is gone (V2-631).
- **V2-650 (2026-09-10) — `play_playlist` keeps the playback the provider started.** The action loaded
  its db snapshot, called the provider (which resolves the first track and writes `yt.videoId` + the
  queue into the store through its own load/save — the read-modify-write contract the header already
  states), then persisted the STALE snapshot, erasing the playback it had just created: nothing sounded,
  `ok: True` reported, `yt` left `{}` (measured live, the «True Blue» errand). Now a non-local first
  track gets no db (the connector owns the store during play/queue) and the final persist runs on a
  FRESH load. A local first track keeps the old single-writer flow untouched. The dedupe half of the
  same incident (three explicit «reproduce la lista»/«dale al play» replays eaten as context-bleed)
  lives in `nucleo/flash/canvas_license.py::replay_license`.

## 2026-09-12 — V2-678: the pinned-frame fix had to be REDONE, plus a real visual pass
- The V2-667 fix (idle playback-bar state + pinned header/footer) described above never actually shipped:
  its `widget.js` edit was uncommitted and got lost — the file on disk still carried the pre-fix code (no
  `.hb-mus2-headfix`, `max-height:60vh` instead of a flex fill, "Nada sonando" still hardcoded), even though
  the testmap entry and the test file survived. Rebuilt the same mechanism from scratch, this time landing
  it (see the commit for this batch).
- **A NEW bug found while rebuilding it, worth keeping**: the three-zone CSS looked complete
  (`.hb-mus2-root{height:100%}`, `.hb-mus2{height:100%}`) and still silently no-opped — a 30-track playlist
  in a 420px card rendered at its full, un-clipped ~1922px natural height. Cause: `render()`'s persistent
  `el._viewHost` (kept unrebuilt across re-renders so the hidden YouTube/local-audio player never restarts)
  is created as a bare, UNCLASSED `<div>` sitting between `.hb-mus2-root` and the visible `.hb-mus2` card.
  With no rule of its own it defaults to `height:auto`, and a percentage height on its child resolves
  against "auto" exactly as if no height were set — the fix was internally consistent and did nothing.
  Fixed with `.hb-mus2-viewhost{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}` plus giving
  that div the class in `render()`. Caught by a live Playwright layout probe (`getComputedStyle` at every
  level of the chain), not by reading — reading the CSS gave no reason to suspect the one unclassed div in
  the middle of it.
- **Operator's second round of feedback, same widget, with a screenshot of a track actually playing**: the
  bottom bar "looks bad" — a plain dark rectangle with a stray horizontal bar floating under a large empty
  void, no visual structure "como Spotify o Amazon Music", and the track title needs to be "un pixel o dos"
  bigger. Addressed as a visual pass on top of the (re-fixed) structural one:
  - The transport bar is now visually LIFTED off the content above it — its own background tone
    (`--hb-bg-soft`), a top divider, AND a soft upward `box-shadow` (the exact cue both reference apps use
    so a player never reads as "a line drawn across a flat rectangle") — bigger padding, bigger cover art
    (46px→52px), bigger round main button (36px→40px) with its own shadow.
  - Track title 13px→15px per the operator's literal ask; artist line 11.5px→12.5px.
  - The header band (`.hb-mus2-headfix`) gets a tonal background + bottom border of its own too, so the
    screen reads as three distinct bands (header / scrolling middle / footer) instead of one undifferentiated
    dark field with text floating on it — the operator's "tiene que haber diferentes apartados en la
    pantalla".
- Tests: same node 4.3 file, all 5 cases green; 3 of 5 disarmed red against the pre-redo widget.js (idle-bar
  shape + both pin cases — the same disarm ratio as the original V2-667 attempt, now actually landed).
  `make test-widgets` 15/15, musica unit suite 66/66, music connector suite 21/21.
  **NOT verified live** — needs an engine restart and a page reload.

## 2026-09-17 — V2-717: ONE box, and the song IS the screen

His order, with a screenshot of the card open while a track was playing and the whole middle of it empty:

1. **One box.** «Has puesto como un contenedor exterior en el que hay un título arriba del todo que pone
   music y los botones del sistema operativo… y dentro has metido otra caja como si eso fuera el widget de
   música. Y yo solo quiero UNA caja encima del escritorio.» `.hb-mus2` lost its border, its radius and its
   background: the canvas window IS the frame. What separates the three bands is tone and a hairline.
2. **One bar.** The V2-715 amendment applied here: the window already says «Música», so «Tu música» under
   it was the same sentence twice. What is left is the row that could not live anywhere else — the view
   switch and the source chip. The switch is DERIVED, like the contacts rail: «Sonando» is only drawn while
   something sounds, because a switch with one side is a label.
3. **AHORA SUENA.** «Me gustaría ver la canción en toda la pantalla del widget… la imagen de la música más
   grande, el nombre de la canción, el nombre del artista, la duración, una barra de progreso para que yo
   la pueda mover… y sin nada más, es decir, la canción igualmente la manejo abajo.» So the middle is the
   ficha and the transport stays at the foot — the duplication is his, asked for out loud. `home` is the
   ADAPTIVE face: the song when something sounds, the library when nothing does; `now`/`library` pin either.
4. **An empty library says something.** «Está un poco triste al verse tan vacía.» A hero with three chips
   that actually play, and the way into a new list still in reach.
5. **The sources screen.** The Spotify block used to sit in the middle of the library, first thing the eye
   met on a card nobody had asked anything yet. It is behind the source chip now (`open_view {kind:connect}`).

### The playhead belongs to whoever makes the sound

There is no position in the store, and there must not be one. A local file and the hidden YouTube iframe
play in the operator's PAGE and hold their own clock — the card reads them directly and a drag seeks them
with no server in the loop. Spotify plays on a device in another room, so its `progress_ms` is a photograph
the card advances with its own clock and a drag is a round trip (`connectors/spotify` gained `seek` +
`progress_ms`; the contract's `MusicProvider.seek` is deliberately NOT abstract, so a provider that can do
neither keeps the honest «unsupported»).

A seek asked by VOICE travels the other way: `seek {to|by}` leaves a numbered command in the store
(`yt.seek` / `local.seek`) and the page applies it. Three things that are load-bearing there:

- ⚠️ **the counter is the seek's OWN, never `cmd_seq`** — riding the shared sequence would re-apply the last
  seek on the next pause or volume command, i.e. a song that jumps backwards when you touch the volume;
- ⚠️ **`_bump(yt, "load")` drops a pending seek** — a new video is loaded IN PLACE in the same block, so an
  unapplied command would cross over and move the NEXT song by the seconds meant for the last one (the local
  block is rebuilt from scratch on every play and needs no equivalent);
- ⚠️ **a seek must not bump `local.seq`** — `seq` means «start this file again» (V2-638), so a seek that
  bumped it would restart the very song it was asked to move inside.

### The clock the free player already had

The `listening` handshake that has delivered onReady/ENDED since V2-047 also delivers `infoDelivery` frames
with `currentTime` and `duration`. Nothing extra is asked of the embed and no request of ours is involved.
Kept as a STAMPED sample so the bar interpolates between frames instead of stepping, thrown away when the
video changes, and filtered by the handshake id — the youtube widget's player emits on the same window
(the V2-366 cross-talk), and without the filter its clock would become this card's position.

Until a frame arrives there is NO scrubber: a bar pinned at zero that cannot be moved is worse than no bar
(his own rule for the batch — what is not finished looks disabled, is absent, or is clear). It appears on
its own when the clock lands, through the card's 250 ms local tick; the tick never repaints while the finger
is down, and a drag asks the player ONCE, on release.

### Two things measured, not reasoned

- ⚠️ **A rail asking for `width:100%` of a slot with no width of its own is 0 pixels wide** — present in the
  DOM, correct-looking, and impossible to drag. In a centred flex column a bare div shrinks to its content.
- ⚠️ **A flex column that CENTRES its content overflows at both ends, and that overflow is CLIPPED, not
  scrollable** — `scrollHeight` stays equal to `clientHeight` while the ficha is being cut in half. The
  geometry test measures CONTAINMENT (the cover's top, the scrubber's bottom) for that reason; the first
  version of it passed against a layout that was losing both ends of the screen. The EMPTY library had the
  same bug and no test saw it — found by rendering the three faces and LOOKING at them, with the hero disc
  sliced in half by the bar above it. Both centred regions use `justify-content: safe center` now, which
  falls back to start exactly when centring would clip, and the case is guarded.
- ⚠️ And the oldest trap in this file, met again while writing the comment that explains the fix above: a
  BACKTICK inside the injected `<style>` template ends the literal and kills the whole module. Two of them,
  in prose quoting a CSS keyword. `node --check` catches it; nothing at runtime does.

## 2026-10-24 — V2-795: the card does what a player does, and the content is sectioned

The ask: «more or less what Spotify does, not 100 % but what's reasonable», and a quiet visual pass («boxed or
sectioned, shadowed, subtle, elegant, dark mode»). Gap list and the parity table live in the local initiative.

- **New declared ops** (all through the generic widget door; prompt cost paid by shortening `whenToUse`/`usage`, so
  the composed prompt is SMALLER than before): `rename_playlist`, `delete_playlist` (confirm + `confirm_q`: a whole
  list is a sweep), `move_track`, `shuffle`, `repeat`, `queue_remove`, `queue_move`, `queue_clear`, `search` (view),
  `play_album`; payload extensions `play_playlist {from, shuffle}`, `set_volume {mute}`, `open_view {kind: queue |
  search | artist | album}`. `played` is INTERNAL: the card reports a song it shows sounding, so a song started by
  voice reaches Recent/Most played (deduped against the head of Recent).
- **Where things live:** `player.py` (modes, queue view/edit, mute, `played`), `browse.py` (search, artist/album pages,
  `play_album`), `actions.play_sequence` (the one «first now, rest queued» road a list and an album share — the V2-650
  fresh-load rule moved there intact). The catalogue door is `connectors/music/catalog.py`: the connected account's
  own catalogue (Spotify `search_catalog`/`artist_page`/`album_page`), else the free iTunes metadata
  (`connectors/music/itunes.py`, also the art enrichment's client now), played by WORDS.
- **Provider limits are said, not faked:** Spotify's Web API cannot remove, reorder or clear its queue → read-only
  on the card, `unsupported` from the op. Liked songs / recently played / own playlists from Spotify would need new
  scopes (a new consent) — not done; «Favoritos» is the liked list and every row has a heart.
- **Free player modes:** repeat one = a seek to 0 + a play command on the SAME video (never a reload); repeat all = the
  finished song goes to the back of the queue; shuffle = the next queued song at random; a manual `next` ignores
  repeat one.
- **Visual:** each shelf is a panel on `--hb-bg-soft` with a subtle hairline and `--hb-shadow-1`; list cards on
  `--hb-bubble` with a 2x2 cover MOSAIC; «Nueva» is a pill in the panel head; rows have hover actions (heart, queue,
  add to a list); the bar holds shuffle/prev/play/next/repeat + heart + mute (+ a slider from 600 px wide, via a
  container query — the validator reads a `min-width:600px` declaration as a fixed width, so the range syntax is
  used) and a thin progress line on its top edge that waits for the clock like the big scrubber.
- A double-click on a song in a list now plays the LIST from that song (`play_playlist {from}`), like any player.
- **One state model for every row** (`rowState`): `current` = the song the player holds (green title + green edge,
  no fill), `playing` = it is SOUNDING per the player's own report — the only state that animates (row meter, bar
  badge). A paused current song shows a still note. Hover is a neutral tone and never resembles current.
- **The transport is two rows**: art · title · transport · heart, then elapsed · rail · total · mute · volume bar.
  The rail and times wait for the clock (no bar pinned at zero); a click or a drag seeks ONCE on release; the volume
  bar is `data.volume.level` (the provider's level that voice volume_up/down/set_volume move). A short card hides the
  now-view facts line (container query on the band's height) so the cover keeps its room.
- The skip fix that preceded this pass (3a3bb199): a list goes to Spotify as ONE context, a skip names the new song or
  says nothing changed, and `next`/`previous`/volume/`seek` are declared `"repeatable"`.

## 2026-11-02 — the responsive pass: one app, a desktop face and a phone face

The ask: the same music, lists, queue and playback on two surfaces, with navigation and controls that belong to
each — not a scaled-down desktop on the phone. Everything new is PRESENTATION; the data model did not change.

- **The arrangement is read from the card's real box** (`js/layout.js::layoutOf`), on every draw, and a
  `ResizeObserver` redraws from the SAME data when a threshold is crossed: `wide` ≥1100 (sidebar, collapsible —
  the flag is per-viewer `localStorage`; queue panel beside the song), `compact` 700-1099 (icon rail; the queue is a
  drawer), `narrow` <700 (the destinations as a tab strip in the one bar; a small desktop card cannot spend 50 px on
  a bottom bar — measured: the cover fell under 88 px at 360x400), `mobile` = inside the phone shell (`.zm-scroll`)
  or a small coarse-pointer screen (bottom navigation, a 64 px mini-player, the expanded player, the queue as a
  bottom sheet; `land` puts the navigation on a left rail). A tablet-sized shell card (both sides ≥700) is
  `compact`. A resize never asks the server for anything and never touches the player hosts.
- **Destinations**: Home = `library` (continue listening · your lists · recently played · favourites; an empty
  shelf is not drawn), Search = `search`, Your music = `collection` (NEW face, card-internal: `id` = the open tab,
  playlists/favorites/top/recent; deliberately NOT declared to the model — a sentence reaches the same lists through
  `library` and `playlist`), Playing = `now`. `home` stays ADAPTIVE (V2-717) and lights the tab it is showing.
- **The queue off the wide card is a LAYER** (`kind: queue` → the player underneath + `queueOverlay`); its close is
  `open_view {kind: now}`. Reorder works three ways: HTML5 drag (mouse), a pointer drag on the grip (touch — HTML5
  drag never starts from a finger) and «up»/«down» in the row's ⋯ menu (no dragging at all).
- **Touch**: a tap on a row PLAYS on a hover-less screen, and everything a pointer would reveal (heart, queue, add to
  a list, remove, the facts a narrow row leaves out) is in its ⋯ menu; every button is ≥44 px under `(hover:none)`.
- **The phone's expanded player** is one column sized by the HEIGHT that is there (`clamp(…, 100cqh - 296px, …)`
  on the cover), so play never leaves the screen at 320x568; the five transport buttons are `transport()` in
  `js/controls.js`, the same builder the desktop bar uses. Volume is a popover (the device keys stay the main one).
- **YouTube on screen** (`views.js::placeVideo`): on the song face the persistent embed is laid OVER the cover slot
  (never re-parented — that reloads it and restarts the song) when the slot is ≥200x200, YouTube's floor for an
  embedded player. ⚠️ OPEN: on every other face, and on a slot under 200 px, the embed is still the hidden 1 px one —
  the free source is hidden-audio playback, which the provider's terms do not allow. Closing that is a product
  decision (keep a visible player somewhere on every face, or stop the free source when the song face is left).
- The new glyphs (home, library, more, up/down, sidebar) live in `frontend/app/lib/icons.js` with the rest; the new
  labels are `widgets.musica.*` keys in both genesis bundles (ES + EN).
- Manifest `size` 468x540 → 760x580: the first footprint on the canvas is now the compact desktop arrangement.
