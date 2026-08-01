# V2-083 — Configuración en 3 pestañas + registro único de conectores + origin de widgets

> Estado: **IMPLEMENTADO** (2026-08-01, v2.83). Sucede a [[V2-082]] (nombres+alias de widgets).
> Autor: sesión 2026-08-01.

## Objetivo (pedido del operador)

El área de Configuración full-screen (⚙, `ConfigPanel.js`, superficie de sistema) pasa a **3 pestañas
principales**:
1. **Ajustes** — lo de siempre (API/modelo por pieza, voz, idioma, saldos): el menú lateral de 7 secciones intacto.
2. **Conectores** — TODOS los conectores del sistema, con estado conectado/autenticado o no, y **conectar/revocar
   desde ahí mismo** (en los dos sitios: aquí + el widget de mensajería). También por voz (follow-up aparte).
3. **Widgets** — una sola lista alfabética con badge por línea: **«de serie»** (vienen con el agente) vs **«tuyo»**
   (creados por el usuario). Solo lectura.

**Invariante duro del operador:** los conectores son NATIVOS y **toda su configuración/credenciales es DINÁMICA,
visible, revocable y autenticable desde el frontend — NADA en `.env`** (env solo fallback power-user). El código de
conexión vive en `connectors/<x>/`; los datos (tokens de cluster, token de Architect, etc.) viven en el store del
agente, gestionables desde la pestaña.

## Piezas

### Backend
- **`connectors/registry.py`** (NUEVO) — inventario ÚNICO y tipado: `descriptors()` → por conector
  `{id, label, family (mensajería|música|infra), auth (qr|app-password|oauth|token|cluster), connected, status,
  detail, config REDACTADA, [clusters]}`. Agrega mensajería (config+estado vivo del store), Spotify (`auth.status`),
  Architect (`configured`), MeshKore (`manager.clusters`). Read-only; cada fuente aislada (un conector roto no tumba
  el registro).
- **Tokens de infra DINÁMICOS (no `.env`):** `config/connectors.py::_DEFAULTS` gana `architect: {enabled, token, url}`
  (`token` secreto → redactado). `connectors/architect/client.py::token()/base_url()` leen el store PRIMERO, `.env`
  solo fallback. MeshKore ya tenía store dinámico (`store.stage/resolve/save_cluster`).
- **Endpoints** (`server/config_api.py`): `GET /api/connectors` (el registro) + `POST /api/connectors/architect/
  connect|disconnect` (fijar/revocar token). Mensajería/Spotify/MeshKore reusan sus endpoints existentes
  (`/api/messaging/{p}/connect|disconnect`, `/api/spotify/*`, `/api/meshkore/stage|connect|disconnect`).
- **Widget origin:** `widgets/registry.py::origin_of` → `builtin` (lista curada `_BUILTINS` = 10 core de serie) |
  `user`. `origin` explícito del manifest manda; el **generador estampa `origin:"user"`** en lo que crea. Propagado a
  `registry()`/`project_state()` → `GET /widgets/registry` + `state.widget_registry`.

### Frontend
- **`ConfigPanel.js`**: barra de pestañas `.cf-tabs` (Ajustes/Conectores/Widgets) sobre el `.cf-tabpane`. La pestaña
  Conectores pinta tarjetas por familia con las cajitas de conexión (QR WhatsApp/Telegram, app-password Email, OAuth
  Spotify, token Architect, cluster MeshKore) llamando directo a los endpoints REST (poll tras conectar para pillar el
  QR). La pestaña Widgets = lista alfabética con badge de-serie/tuyo. `api.js` gana los helpers; `styles.css` los
  estilos (`.cf-tabs/.cf-tab/.cf-tabpane/.cf-btn/.cf-fam/.cf-wrow/.cf-wbadge`).

## Split builtin/user inicial (editable en `registry._BUILTINS`)
- **De serie:** agenda, clock, timer, search, results, navegador, mensajeria, musica, youtube, cluster-registro.
- **Tuyo:** meteo-soria, meteo-tarragona-grafico, futbol-champions, personalizado-reproduzca-video,
  temporizador-pomodoro-ayudar, juego-serpiente-snake.

## Pendiente / follow-up
- **Conectar por voz** ("conéctame el WhatsApp") = una tool que dispare el connect — aparte, tras validar la UI.
- El QR de WhatsApp/Telegram en la pestaña se refresca por poll corto tras conectar; podría escuchar el SSE de
  mensajería como el widget para ser instantáneo.
