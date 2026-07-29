# V2-041 — Conectores de MÚSICA (seam agnóstico + Spotify), reproducción por voz

**Origen (operador, 2026-07-15):** «necesitamos conectores de música — 'pon música', 'ponme a Frank Sinatra', hay
que poder reproducirlo». Preferencia explícita: **APIs / conectores / MCPs / algo RÁPIDO**, no scraping frágil.
Aclaración clave: **esto es un CONECTOR**; el **widget** de música (mostrar canción, listas, controles) es una
pieza SEPARADA y posterior — y ese widget «funcionará con CUALQUIER conector que sepa hacer streaming».

## Diseño — un SEAM agnóstico + proveedores

Igual que `connectors/messaging/` es la capa compartida de WhatsApp+Telegram, la música tiene un **seam único** y
proveedores intercambiables detrás. El FlashBrain (y el futuro widget) hablan SIEMPRE con el seam, nunca con un
proveedor concreto.

### `connectors/music/` — el contrato agnóstico
- `base.py` — `MusicProvider` (ABC: `connected/search/play/pause/resume/next/previous/set_volume/now_playing/
  status`) + tipos normalizados `Track` / `NowPlaying` / `MusicResult` (con frase HABLABLE lista).
- `registry.py` — registro PEREZOSO de proveedores (`_BUILTIN` por símbolo; no acopla el import del seam a ningún
  conector). `active()` = el primer proveedor CONECTADO (preferencia opcional).
- `__init__.py` — **fachada** `control(action, query)` / `now_playing()` / `status()`. Fail-safe (nunca lanza);
  mensajes hablables por idioma del operador (es/en, monolingüe V2-013).

### `connectors/spotify/` — 1er proveedor (Spotify Web API)
- `client.py` — cliente REST httpx SÍNCRONO: `search` + control del reproductor (`/me/player/*`) con **recuperación
  de NO_ACTIVE_DEVICE** (busca un dispositivo Spotify Connect y le pasa el `device_id`). Códigos de error estables
  (`no_device`/`premium`/`auth`/`rate_limit`).
- `auth.py` — **OAuth 2.0 Authorization Code + PKCE** (S256, sin client-secret). `client_id` en el credential store
  (`config/credentials.py`); **tokens** en `.meshkore/credentials/spotify.json` (chmod 600, atómico, refresco
  automático con skew). El callback lo sirve el propio servidor (no un hilo HTTP aparte como en el donante Hermes).
- `provider.py` — implementa `MusicProvider` sobre client+auth; mapea a `Track`/`NowPlaying` y frases hablables.
- Portado (adaptado y podado) del plugin Spotify del retirado agente Hermes (`~/.hermes/.../plugins/spotify/`).
- ⚠️ Reproducir exige **Spotify Premium + un dispositivo activo**. Sin dispositivo → aviso hablable «abre Spotify».

### FlashBrain — tool `play_music` (ruta LIGERA en el turno)
- `nucleo/flash/router.py`: nuevo kind `MUSIC` + tool `play_music(query, action)` (siempre ofrecida, capacidad de
  1er nivel como `web_search`) + `decide()` + prioridad (por debajo de las ops de worker, por encima de search/chat).
- `voice/engine/llm/providers/nucleo.py`: ejecuta la acción **fuera del event loop** (`asyncio.to_thread`, respeta
  V2-011) contra `connectors.music.control` y dice el mensaje del conector (nunca mudo; corrige si falló).
- `nucleo/flash/probe.py`: espejo del clasificador (impl PARALELA — cablear en AMBOS) → reporta `action="music"`.
- `nucleo/flash/prompt.py`: una línea TERSA de recursos (play_music vs web_search).

### `server/spotify_api.py` — plano de control OAuth (config-UI, montado SIEMPRE)
`/api/spotify/{status,connect,callback,disconnect}` + `/api/music/state` (para el widget futuro). `connect` guarda el
client_id y devuelve la URL de autorización; `callback` canjea el code y muestra una página de cierre.

### Config / docs
- `config/doctor.py`: credencial `spotify` (`SPOTIFY_CLIENT_ID`) en el catálogo del wizard (V2-040).
- `config/.env.example`: bloque Spotify (fallback power-user; incluye la Redirect URI exacta a registrar).
- `cluster.yaml` (módulo `connectors` ampliado), `zaelar-architecture.md §8` (tool catalog) + diagrama
  `/architecture` (fila de la tabla + caption + sello), `zaelar-modules.md §Connectors`.

## Invariantes / cuidado
- El widget de música es OTRA pieza; NO se toca aquí. El seam es la costura que ese widget consumirá.
- Reproducir I/O de red → SIEMPRE off-hot-path (`to_thread`), como `web_search` (V2-011).
- Config gestionada por la UI: client_id + OAuth desde la interfaz; secretos nunca al frontend (redacción).
- Fail-safe: un fallo de música NUNCA rompe la voz (fachada + provider capturan y devuelven frase hablable).
- Cerebro NO-razonador intacto (play_music es function-calling, no razonamiento).

## Decisiones (aclaraciones del operador, 2026-07-15)

- **Auth — el camino MÁS CORTO**: el client_id de PKCE NO es secreto → zaelar puede traer UN client_id propio
  (`SPOTIFY_DEFAULT_CLIENT_ID`) y el usuario solo INICIA SESIÓN (un clic), sin registrar app de developer. Fallback:
  "usa tu propia app" (pega tu client_id). Zero-setup real = el fallback gratis de YouTube. (Spotify dev-mode = 25
  usuarios hasta Extended Quota; para SaaS se pide review.)
- **El widget de música es SUYO y va AHORA** (no una fase lejana): igual que la tarjeta de `mensajeria` guía la
  conexión, `musica` guía la de Spotify. **`musica` ≠ `youtube`**: uno es MÚSICA, otro VÍDEO; NO se mezclan.
- **Fallback sin Spotify = audio de un vídeo OCULTO DENTRO de `musica`** (no el widget de YouTube): resuelve la
  canción a un `videoId` y reproduce solo el AUDIO en un iframe oculto de la propia tarjeta de música.

## Fases
1. **Seam + Spotify + tool play_music + config + tests + docs** — hecho (2026-07-15).
2. **Widget `musica` + fallback GRATIS (YouTube-audio)** — hecho (2026-07-15, mismo día): la tarjeta guía la
   conexión de Spotify y reproduce; sin Spotify, `connectors/music/youtube_audio.py` resuelve la canción a un vídeo
   y suena su AUDIO oculto en la propia tarjeta. Widget separado del de YouTube.
3. **Más proveedores** (slots): Apple / radio-stream / YouTube Music oficial, cada uno como `MusicProvider`.

## Bitácora
- **2026-07-15 · Fase 1** — Seam `connectors/music/` (base+registry+fachada) + conector `connectors/spotify/`
  (client+auth PKCE+provider) + tool `play_music` (router/provider/probe/prompt) + `server/spotify_api.py` (montado
  siempre) + config (doctor+.env.example) + cluster.yaml + `zaelar-architecture.md §8` + diagrama `/architecture`.
  Tests: 34 verdes (music seam, spotify auth/PKCE/token-store, provider NO_ACTIVE_DEVICE, router). Suite flash 73
  verdes. **Pendiente del operador:** registrar la app en developer.spotify.com (Redirect URI
  `http://127.0.0.1:8473/api/spotify/callback`) y conectar desde la UI; requiere Premium + dispositivo activo.
- **2026-07-15 · Fase 2** — widget `musica` (manifest+data.py+widget.js): tarjeta guía de conexión de Spotify
  (`ctx.action("connect")` → URL de login → `window.open`; el callback guarda tokens), player de Spotify (now-playing
  + controles) al conectar, y **fallback GRATIS**: `connectors/music/youtube_audio.py` (proveedor siempre disponible;
  resuelve canción→videoId por YouTube Data API/scrape; reproduce el AUDIO en un **iframe OCULTO reusado** dentro de
  `musica`, NO el widget de YouTube). `auth.py`: `SPOTIFY_DEFAULT_CLIENT_ID` → conectar con UN CLIC. `nucleo.py`
  muestra `musica` cuando la reproducción es en-navegador (surface=widget). Registro prioriza Spotify>YouTube. Tool
  `play_music` + prompt: "suena siempre". Tests: 48 verdes. **Pendiente:** revisión de alineación formal; probar en
  vivo (Spotify + autoplay del iframe con la sesión de voz).
