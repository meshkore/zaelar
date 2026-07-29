---
title: Zaelar Deploy
category: deploy
updated: 2026-07-09
owner: ricart
status: current
---

# zaelar — Deploy reference

Estado actual: **sin deploy en producción**. Se ejecuta en local.
Las apps de Fly.io (`zaelar`, `asimovia-cdg`, `asimovia-ams`) fueron destruidas por ahorro de costes.

---

## Ejecución local (modo actual)

```bash
cd /Users/ricartjuncadella/Documents/Prj/asimovia/zaelar
make run                 # → http://localhost:43917  (BRAIN=nucleo, el cerebro propio)
```

Levanta el servidor LiveKit nativo (binario `livekit-server`, sin Docker) + el web con el worker embebido.

Abre en **Chrome** (WebRTC + Web Speech API requieren localhost o HTTPS).

**TURN no hace falta en local**: STUN de Google (default) es suficiente. Omite `CF_TURN_KEY_ID` / `CF_TURN_API_TOKEN` en tu `.env`.

---

## Deploy en Fly.io (cuando lo necesites)

### Prerequisitos
```bash
brew install flyctl
flyctl auth login          # cuenta personal Fly.io
```

### Pasos

```bash
cd /Users/ricartjuncadella/Documents/Prj/asimovia/zaelar

# 1. Crear la app (solo la primera vez; luego salta al paso 3)
flyctl apps create zaelar --org personal

# 2. Asignar una IPv4 dedicada (necesaria para WebRTC UDP/ICE)
flyctl ips allocate-v4 --app zaelar --shared   # o --dedicated si el shared no funciona con ICE

# 3. Secrets (solo la primera vez o cuando cambien)
flyctl secrets set --app zaelar \
  AIMLAPI_KEY="<tu-key>" \
  DEEPGRAM_API_KEY="<tu-key>" \
  CARTESIA_API_KEY="<tu-key>" \
  ELEVENLABS_API_KEY="<tu-key>" \
  GEMINI_API_KEY="<tu-key>" \
  WEBRTC_HOST="zaelar.fly.dev" \
  CF_TURN_KEY_ID="<cloudflare-key-id>" \
  CF_TURN_API_TOKEN="<cloudflare-api-token>"

# 4. Deploy
flyctl deploy --app zaelar --remote-only

# 5. Verificar
flyctl status --app zaelar
flyctl logs --app zaelar
```

El `fly.toml` ya está en la raíz del repo con la config correcta (`shared-cpu-2x`, region `cdg`, scale-to-zero).

### CloudFlare TURN — cómo configurarlo desde cero

TURN es necesario en producción para clientes detrás de NAT de operador (móviles).
En local **no hace falta**.

1. **Ir a Cloudflare Dashboard**: [dash.cloudflare.com](https://dash.cloudflare.com)
2. En el menú lateral: **Workers & Pages → Real-Time Communications → TURN Keys**
   (o directo: `https://dash.cloudflare.com/<tu-account-id>/workers/real-time-communications/turn`)
3. **Create a new TURN key** → dale un nombre (p.ej. `zaelar-prod`)
4. Copia los valores:
   - `Key ID` → `CF_TURN_KEY_ID`
   - `API Token` → `CF_TURN_API_TOKEN`
5. Configúralos como secrets de Fly.io (paso 3 arriba) o en tu `.env` local

El servidor los usa en `server/voice_api.py::_cloudflare_turn()` para generar credenciales ICE dinámicas
via `https://rtc.live.cloudflare.com/v1/turn/keys/{kid}/credentials/generate` (caché de 24h).

> **Cleanup (ya hecho, 2026-06-30):** la TURN key usada en `asimovia-cdg` / `zaelar` (Fly) ya no está en
> producción. Si todavía aparece en tu Cloudflare dashboard → TURN Keys, bórrala para evitar costes.

### Cleanup del deploy anterior (ya hecho)

```bash
flyctl apps destroy zaelar --yes
flyctl apps destroy asimovia-cdg --yes
flyctl apps destroy asimovia-ams --yes
```

---

## Deploy del servicio de entrevistas (prototype_interviewer)

El servicio de entrevistas **también fue destruido** (2026-06-30). Si quieres volver a desplegarlo:

```bash
cd /Users/ricartjuncadella/Documents/Prj/asimovia/other/vala.voice/prototype_interviewer

# Crear app nueva (el nombre asimovia-cdg ya no existe, elige uno nuevo)
flyctl apps create asimovia-entrevista --org personal
flyctl ips allocate-v4 --app asimovia-entrevista --shared

flyctl secrets set --app asimovia-entrevista \
  AIMLAPI_KEY="<tu-key>" \
  DEEPGRAM_API_KEY="<tu-key>" \
  CARTESIA_API_KEY="<tu-key>" \
  ELEVENLABS_API_KEY="<tu-key>" \
  GEMINI_API_KEY="<tu-key>" \
  WEBRTC_HOST="asimovia-entrevista.fly.dev" \
  CF_TURN_KEY_ID="<cloudflare-key-id>" \
  CF_TURN_API_TOKEN="<cloudflare-api-token>"

flyctl deploy --app asimovia-entrevista --remote-only
```

Actualiza `prototype_interviewer/fly.toml` con el nuevo nombre de app antes de hacer deploy.

---

## Variables de entorno (resumen)

> **Proceso desplegado:** el contenedor arranca con `BRAIN=nucleo` (el cerebro propio). El routing de modelos
> (capa rápida FlashBrain + CodeAgent de SlowBrain) vive en `config/v2.json`, gestionado desde la UI.

| Variable | Obligatoria | Descripción |
|---|---|---|
| `AIMLAPI_KEY` | sí (FlashBrain/STT) | AIML API — modelo de la capa rápida + STT opt-in |
| `DEEPGRAM_API_KEY` | recomendada | TTS Aura-2 + STT fallback |
| `WEBRTC_HOST` | solo en prod | hostname público (p.ej. `zaelar.fly.dev`) |
| `CF_TURN_KEY_ID` | solo en prod | Cloudflare TURN (NAT traversal) |
| `CF_TURN_API_TOKEN` | solo en prod | Cloudflare TURN |
| `CARTESIA_API_KEY` | opcional | TTS alternativo |
| `ELEVENLABS_API_KEY` | opcional | TTS alternativo |
| `STT_PROVIDER` | no | `auto`\|`whisper`\|`browser`\|`deepgram`\|`groq`\|`aiml` |
| `TTS_PROVIDER` | no | `deepgram`\|`kokoro`\|`cartesia`\|`elevenlabs` |
| `BRAIN` | no | `nucleo` (default)\|`direct`\|`local` |

Todos los valores no-secretos están documentados en `config/.env.example`.
