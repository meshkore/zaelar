---
id: INI-015
title: Telegram Triage Connector + Unified Messaging Widget
status: done
owner: ricart
modules: [connectors, brains, voice, widgets]
updated: 2026-07-07
---

## Goal

Que zaelar **lea el Telegram personal del operador** y lo tríe **igual que ya hace con WhatsApp** (INI-014), y que
la interfaz se **unifique en UN SOLO widget de "mensajería"** que muestra mensajes de CUALQUIER plataforma
(WhatsApp, Telegram y, a futuro, email) en un mismo sitio. El brain sigue siendo dueño de la decisión ("¿esto
importa?"); los conectores son el transporte + el motor de triaje; la capa `connectors/messaging/` es lo común.

Decisiones del operador (2026-07-07, todas tomadas de antemano — implementación de corrido):
- **Telegram = USERBOT (Telethon)**, cuenta PERSONAL, NO la Bot API — es la única forma de leer chats personales.
  Python puro in-process (asyncio), sin bridge Node, sin nada de Hermes que vendorizar.
- **Auth = LOGIN POR QR** (`client.qr_login()`), QR pintado EN EL WIDGET (data-URI PNG con `segno`).
- **Config MANEJADA POR LA INTERFAZ (invariante de producto)**: el usuario instala UNA vez y luego lo maneja TODO
  desde la UI — **nunca edita `.env`**. Al decir "conéctame Telegram" (o abrir el widget), el widget le **guía paso
  a paso**: formulario de credenciales (`api_id`/`api_hash` de my.telegram.org, con pasos en lenguaje llano y
  enlace) → QR → conectado. Las credenciales + flags de activación se guardan en `config/connectors.json`
  (gitignored, escrito por el widget vía `config/connectors.py`); **el store MANDA sobre `.env`** (env = fallback de
  power-user). WhatsApp igual: botón "Conectar WhatsApp" → QR. Doc canónica: `zaelar-conventions.md §Configuration
  is UI-managed`.
- **Clasificador = el LOCAL existente PROMOVIDO** a `connectors/messaging/triage.py` (qwen2.5:3b vía Ollama, nada
  personal sale de la máquina, fallback remoto por env). Agnóstico de plataforma; NO pasa por el agente Hermes.
- **Widget ÚNICO** `widgets/mensajeria/` (id `mensajeria`) que **sustituye a `widgets/whatsapp/`** (borrado).
- **Read-only + mark-read** (como WhatsApp). Autorespondedor fuera de alcance.

## Contexto: qué reutilizamos de Hermes (y qué NO)

- Telegram: **NADA de Hermes**. Hermes solo trae la **Bot API** (no userbot/MTProto), que no lee chats personales.
  Por eso Telegram es **"black-box lib"** (Telethon), sin dependencia ni vendoring — el modo de acoplamiento más
  limpio de la regla de decisión de la federación (§5 de `zaelar-hermes-federation.md`).
- WhatsApp: se conserva el **bridge Baileys vendorizado** (INI-014) tal cual; solo se re-apunta su `service.py` para
  escribir el **store unificado** en vez de su store propio.

**Frontera de propiedad y seguridad ante `hermes update`**: sin cambios respecto a INI-014. Telegram no toca
`~/.hermes/hermes-agent/`; su sesión de login vive en `connectors/telegram/_session/` (gitignored). Contrato
completo en la doc canónica **`.meshkore/docs/architecture/zaelar-hermes-federation.md`** (§6, nueva).

## Arquitectura

```
 WhatsApp servers                      Telegram (MTProto)
     │ (bridge Baileys vendorizado)         │ (userbot Telethon, in-process)
     ▼                                       ▼
 connectors/whatsapp/service.py         connectors/telegram/service.py
     │  (QR del bridge)                      │  (qr_login → QR data-URI con segno)
     └──────────────┬────────────────────────┘
                    ▼
     connectors/messaging/  (capa COMPARTIDA)
       · triage.py  — clasificador LOCAL agnóstico de plataforma (NO pasa por Hermes)
       · store.py   — store UNIFICADO widgets/_data/mensajeria.json
       · notify.py  — aviso proactivo (voz + [SISTEMA]), throttle compartido
       · brief.py   — brief NUMERADO combinado para el brain
       · dispatch_tag([[msg.*]]) — enruta por item.platform
                    │
        ┌───────────┼───────────────────────────┐
        ▼           ▼                            ▼
 widgets/mensajeria/ (widget único)   voice/proactive + [SISTEMA]   [[msg.read/dismiss/clear:N]]
   lista plana por urgencia,          (aviso de cualquier app)      (voz; enruta al conector correcto)
   badge por plataforma, QRs inline
```

Store unificado (`widgets/_data/mensajeria.json`, gitignored):
`{platforms:{whatsapp:{status,qr},telegram:{status,qr}}, updated, items:[{n,platform,from,group,isGroup,body,urgencia,dirigido_a_mi,motivo,messageId,chatId,senderId}], pending_read:[{platform,chatId,messageId,senderId}]}`

## Puntos de integración (exactos)

- `connectors/messaging/` — `config.py`, `triage.py` (promovido), `store.py` (helpers síncronos read-modify-write:
  `upsert_items`, `set_platform_status`, `take_pending_read`, `requeue_pending_read`, `remove_item`, `clear`),
  `notify.py` (`surface` + `announce`), `brief.py` (`for_brain`), `__init__.py` (`dispatch_tag`).
- **Config UI-managed** — `config/connectors.py` + `config/connectors.json` (gitignored): store frontend-managed de
  flags de activación + credenciales, con vista pública redactada. `connectors/messaging/server_api.py` = API
  `POST /api/messaging/{plataforma}/connect|disconnect` + `GET /api/messaging/state` (escribe el store + arranca/
  para el conector en caliente); montada en `server/__init__.py`. `widgets/mensajeria/widget.js` hace `fetch` a
  esta API (flujo de conexión guiado). `telegram/config.py` y `whatsapp/service.enabled()` leen el store (env
  fallback).
- `connectors/telegram/` — `config.py` (store→env), `service.py` (Telethon: `qr_login`+segno, `events.NewMessage`,
  triaje al store unificado, `send_read_acknowledge` al drenar `pending_read`; auto-instala deps si faltan),
  `__init__.py`.
- `connectors/whatsapp/service.py` — re-apuntado al store unificado (platform="whatsapp") vía
  `connectors/messaging`. Bridge/patches/vendoring intactos. `whatsapp/triage.py` y `whatsapp/brief.py` borrados
  (promovidos a `messaging`).
- `widgets/mensajeria/` — `manifest.json`, `data.py` (**stdlib + `widgets` only**: lee/muta el store unificado vía
  `widgets.store`, encola `pending_read` con `platform`), `widget.js` (lista con badges + QRs por plataforma,
  `textContent` para todo cuerpo → anti-XSS), `notes.md`, `__init__.py`. `widgets/whatsapp/` **borrado**.
- `voice/tag_protocol.py` — `[[msg.(read|dismiss|clear)(:N)?]]` (self-closing) reemplaza `[[wa.*]]`.
- `voice/engine/llm/providers/{hermes,duo}.py` — branch `action.startswith("msg.")` → `messaging.dispatch_tag`
  (retirado el de `wa.`; añadido también al camino `deep` del duo).
- `voice/engine/pipeline/agent.py` y `brains/duo/prompt.py` — inyectan `connectors.messaging.brief.for_brain()`.
- `server/__init__.py` — el lifespan arranca `connectors.telegram.service.start()` (gated TG_ENABLED) junto al de
  WhatsApp, y su `stop()` en el `finally`.
- `Makefile` — `install-telegram` (pip telethon+segno). `requirements.txt` — telethon, segno. `config/.env.example`
  y `.env` — bloque Telegram (TG_ENABLED, TG_API_ID/HASH, TG_MY_NAME) + MSG_TRIAGE_*. `.gitignore` —
  `connectors/telegram/_session/` + `widgets/_data/mensajeria.json`.

## Estado — IMPLEMENTADO y VERIFICADO (2026-07-07)

Verificado sin login real (no requiere el teléfono del operador):
- **Sintaxis**: `ast.parse` de los 20 .py nuevos/tocados + `node --check` del widget.js → OK.
- **Imports sin ciclos**: todos los módulos nuevos importan limpio (telethon se importa lazy en el service).
- **Telethon + segno**: `TelegramClient` se construye; `qr_login` existe; `segno` produce el QR data-URI PNG.
- **Clasificador local**: smoke contra `qwen2.5:3b` con mensajes mixtos WhatsApp/Telegram → distingue
  importante/dirigido-a-mí/urgencia y generaliza fuera del few-shot.
- **Store unificado**: round-trip — WhatsApp y Telegram COEXISTEN en una lista numerada por urgencia;
  `apply_action('read')` quita y encola en `pending_read` con su `platform`; cada conector drena solo lo suyo;
  `dismiss` no encola read.
- **Tags**: `[[msg.read:2]]`/`[[msg.clear]]`/`[[show:mensajeria]]` emiten y NO se hablan; `[[wa.*]]` ya no se
  parsea; hold de tag partido en streaming OK.
- **Brief + dispatch**: brief numerado combinado con badge por plataforma + estados de vínculo; `dispatch_tag`
  muta el store correcto.
- **App**: `make test` (build FastAPI + prompt) OK; `make test-widgets` → 9/9 (mensajeria pasa contract/golden/
  render); `mensajeria` aparece en el catálogo (`GET /widgets`); `whatsapp` ya no; `make help` muestra
  `install-telegram`.

**Paso del usuario (todo desde la UI, sin tocar ficheros)**: `make run` → decir "conéctame Telegram" (o abrir el
widget de mensajería) → el widget muestra el formulario guiado (sacar `api_id`/`api_hash` de my.telegram.org, con
los pasos escritos) → pegar los dos datos y pulsar Conectar → **escanear el QR de Telegram** que aparece en el
canvas (una vez; luego la sesión persiste). WhatsApp: "conéctame WhatsApp" → Conectar → escanear QR. Cero edición
de `.env`.

## Seguridad y privacidad

- **Read-only + mark-read**: ni WhatsApp ni Telegram llaman a `/send`. Sin ruta de escritura, sin injection que
  dispare un envío.
- **Operator-only**: las tags `[[msg.*]]` quedan fuera de la allow-list del bridge de cluster → un peer no
  confiable jamás dispara un digest ni ve mensajes.
- **Privacidad del clasificador**: LOCAL por defecto (Ollama), NUNCA pasa por el agente Hermes → preserva el
  invariante ACP de voz y no saca nada personal de la máquina.
- **Sesiones y store**: `connectors/telegram/_session/`, `connectors/whatsapp/_session/` y
  `widgets/_data/mensajeria.json` están gitignored (credenciales personales + cuerpos de mensajes).

## Fuera de alcance

- **Autorespondedor** (cualquier plataforma) — diferido, con su propio go-ahead (como la Fase 4 de INI-014).
- **2FA de Telegram por QR**: si la cuenta tiene contraseña, el login por QR no la cubre → el service lo registra
  y pide al operador un login manual único (luego la sesión persiste).
- **Email**: slot futuro — el store, el widget y el brief ya lo contemplan como plataforma; falta el conector.
