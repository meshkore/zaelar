# V2-043 — Área de configuración FULL-SCREEN (API/modelo por pieza) + alertas de SALDO

**Origen (operador, 2026-07-16):** al revisar el dashboard de AIMLAPI («no veo falta de crédito en AIML, ¿dónde no
tenemos? ¿grok? ¿voz?») pidió **(1)** un **área de configuración que ocupe toda la pantalla** para elegir las APIs
que usa **cada pieza** y poder modificar todo lo necesario por parte del usuario — «lo que definimos en el wizard»,
pero permanente y granular; **(2)** en el **icono de estado** (◉), además de servicios arriba/con problema, ver
**alertas de SALDO**; los importes/datos extendidos en una **pantalla resumen** de las APIs/servicios dentro de la
configuración.

Aclaración del crédito: **no faltaba crédito en AIMLAPI** — su key vive en `.env` (que `server/common.py` carga) y
tiene saldo; el fallo de voz del 2026-07-15 fue solo `config/v2.json`→Ollama 14b. El área de config + resumen de APIs
hace este estado VISIBLE de un vistazo en vez de adivinarlo.

## Qué se construyó

**Backend**
- **`config/balances.py`** — saldo de APIs externas, doble naturaleza honesta:
  - PROACTIVO donde el proveedor lo expone: **ElevenLabs** `/v1/user/subscription` (caracteres usados/límite →
    barra + estado ok/warn/error). Cache TTL 5 min, fail-open. (AIMLAPI/xAI/Groq/buscadores NO exponen saldo.)
  - REACTIVO para el resto: el último error clasificado (`voice/health_state` + `voice/llm_health.classify` →
    `credit`→«SIN SALDO», `auth`→«credencial», `outage`→«no responde»).
  - `summary()` funde presencia-de-key (doctor) + saldo + último error por servicio; `alerts()` = subconjunto
    warn/error. NUNCA expone la key.
- **`server/config_api.py`** (router always-on): `GET /api/config` (vista agregada REDACTADA: v2 fast/code_agent/
  memory/flags + voz + conectores + spotify + credenciales + **catálogo de proveedores por pieza** + APIs),
  `POST /api/config/v2 {section,patch}` (elige proveedor/modelo por pieza — antes `code_agent` no tenía NINGUNA vía
  UI y `fast`/`memory` solo por el perfil coordinado), `POST /api/config/credential {key|provider,value}` (resuelve
  provider→env por doctor), `GET /api/config/apis` (resumen+alertas de saldo). Los cambios de v2 son POR INVOCACIÓN
  → aplican sin reconectar.
- **`nucleo.py`**: el error del FlashBrain se CLASIFICA (`llm_health.classify`) al registrarlo en `health_state` →
  el estado puede mostrar «SIN SALDO/cuota» real en vez de un genérico «no responde». (`llm_health` estaba huérfano.)

**Frontend**
- **`ConfigPanel.js`** — overlay a PANTALLA COMPLETA (patrón `MemoryMap`), abierto por el ⚙ del TopBar (sustituye al
  modal pequeño de voz; `SettingsModal` queda huérfano/sin montar). Tarjetas por pieza: Cerebro rápido · Agente de
  código · Memoria · Voz (reusa `/api/settings`, reconecta si hace falta) · Búsqueda web (keys por capas) · Música
  (Spotify) · **Resumen de APIs con saldo**. Las API keys por pieza se guardan en la **ENV del proveedor** (coherente
  con la resolución por endpoint del `fast_client`). Redactado: solo presencia de key, nunca el valor.
- **`StatusPanel`** — sección «APIs · saldo» con las alertas warn/error; los importes completos viven en la config.
  `status.js` sondea también `/api/config/apis` (cacheado) → alertas aunque la config esté cerrada.
- `store.js`: `configOpen` + `apiSummary` + `apiAlerts`. `api.js`: `getConfig`/`saveConfigV2`/`saveConfigCredential`/
  `getApiSummary`. CSS `.cfgfull` (temático `--hb-*`).

## Relación con el WIZARD (V2-040)
El wizard sigue siendo el **onboarding de primer arranque** (elige un PRESET local/cloud + credenciales +
instaladores). El área de config es el **superset permanente y granular** (qué API/modelo usa cada pieza). Comparten
backend (`config/*`, `doctor`, `credentials`).

## Invariantes
- Config gestionada por la UI; el store MANDA sobre `.env`. **Ninguna key sale al frontend** (vista redactada
  `<key>_set`). Loopback. Cambios de v2 sin reconectar (por invocación); voz reconecta.
- Saldo proactivo solo donde el proveedor lo expone (hoy ElevenLabs); el resto, reactivo por error clasificado.
  Fail-open: una sonda caída = `unknown`, nunca rompe el estado ni la voz.

## Bitácora
- **2026-07-16** — Construido backend (balances + config_api + clasificación de error) y frontend (ConfigPanel
  full-screen + alertas en el estado). Verificado en vivo: `/api/config` agrega todo; `/api/config/apis` detectó
  **ElevenLabs 401** (key caducada) → alerta real de saldo. Commits en `feat/v2-041-music-connector`.
  **Pendiente:** balance proactivo de más proveedores si exponen API de uso (xAI/Groq — hoy no estándar); test e2e UI.
