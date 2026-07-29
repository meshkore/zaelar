# V2-051 — Conector de email (IMAP/SMTP) integrado en `mensajeria`

**Estado:** ✅ HECHO (2026-07-17) · **Ancla:** EPIC-v2-colmena · mensajería unificada (INI-015)
**Commits:** `2521493` (conector + responder) · rama `feat/v2-051-conector-email` (pusheada)

## Problema / objetivo

Tenemos conectores de mensajería personal para **WhatsApp** y **Telegram**, pero falta el más importante para
mucha gente: el **email**. El operador (y sus usuarios) tienen Gmail, Outlook u otros proveedores IMAP/SMTP.
zaelar debe **leer** el correo (triado, como los otros canales) y aceptar **órdenes del operador** para
**responder** un mensaje. Las auto-respuestas automáticas quedan **fuera de alcance** (flag OFF por defecto).

Todo se integra en el **widget `mensajeria` existente** (no un widget propio — invariante de producto: un canal
nuevo se añade DENTRO de mensajería), reutilizando la capa compartida `connectors/messaging`.

## Decisiones (operador, 2026-07-17)

1. **Auth = IMAP/SMTP + app-password** con presets (Gmail / Outlook / IMAP genérico "otros"). OAuth2 (XOAUTH2)
   queda como Fase 2 posterior; la costura de auth se deja abierta para añadirlo sin reescribir.
2. **Responder = CON confirm-gate** — zaelar lee el borrador y pide OK antes de enviar (reusa el CONFIRM de
   V2-025). Enviar un email no se deshace.
3. **Alcance = todo**: conector (leer+triar+memoria) + tarjeta en el widget + responder. Auto-respuesta OFF.

## Reutilización (fuente Hermes)

El adaptador `~/.hermes/hermes-agent/plugins/platforms/email/adapter.py` es **stdlib puro** (`imaplib`/`smtplib`)
y ya resuelve lo difícil. NO se importa (depende de clases internas de Hermes); se **vendoriza + adapta** su
lógica pura a `connectors/email/mailbox.py`:
- Poll IMAP con dedup por UID (`_seen_uids`, cap + trim).
- Extracción de texto (multipart, HTML→texto), decode de headers RFC2047.
- Filtro de remitentes automáticos/`noreply` + headers de bulk (`_NOREPLY_PATTERNS`, `_AUTOMATED_HEADERS`).
- Verificación **SPF/DKIM/DMARC** (`Authentication-Results`) → marca `authenticated` (metadato de confianza).
- Envío SMTP con threading correcto (`In-Reply-To`/`References`, `Re:` del asunto), retry IPv4.

(OpenCloud NO está en la máquina; solo Hermes. La skill `himalaya` se descarta: mete un binario Rust externo.)

## Arquitectura (encaje en `connectors/messaging`)

`connectors/email/` es el conector más LIMPIO de los tres: **sin bridge Node (WhatsApp) ni lib de terceros
(Telethon)** — solo stdlib. Mismo patrón que Telegram (`service.py` = tarea asyncio en el lifespan, gated por la
UI). Camino de PRODUCCIÓN = v2 stateless (`BRAIN=nucleo`): el conector **publica** `connector.msg`/`connector.status`
al bus y **drena** `msg.mark_read` (marca `\\Seen` en IMAP) + **`msg.reply`** (envía por SMTP). El triaje y el
store viven en el owner del widget `mensajeria` (modelo LOCAL, privacidad). También soporta el camino directo
duo/hermes (fallback) como los otros.

- `connectors/email/config.py` — knobs (store UI-managed gana sobre `.env`): `email_address`, `email_password`
  (SECRETO, redactado), `imap_host`/`imap_port`/`smtp_host`/`smtp_port`, `provider` (preset), `autoreply` (OFF).
- `connectors/email/mailbox.py` — la lógica IMAP/SMTP pura (vendorizada de Hermes, stdlib, testeable sin red).
- `connectors/email/service.py` — motor asyncio: login IMAP/SMTP → poll → normaliza → publica al bus / triaje
  directo; drena mark_read (IMAP STORE \\Seen) y reply (SMTP). `start()/stop()` idempotentes.

### Costuras nuevas en la capa compartida

- `store.PLATFORMS` += `email`; `_empty()`/`load()` cubren email; **`pending_reply`** (cola simétrica a
  `pending_read`: `{platform, chatId, to, messageId, subject, text}`). Los items de email llevan `subject` +
  `msgid` para el threading.
- `ingest`: `publish_status`/`publish_msg` ya sirven; nuevos `publish_reply(key)` + `ReplyInbox(platform)`
  (espejo de `MarkReadInbox`).
- `control.PLATFORMS` += `email`; `validate_connect`/`apply_connect`/`apply_disconnect` cubren email (persiste
  credenciales en `config/connectors.json`, arranca/para en caliente). `_forget_session` borra `_seen`.
- `config/connectors.py`: entrada `email` en `_DEFAULTS`, `email_password` en `_SECRET_KEYS`, `EMAIL_ENABLED` en
  `_ENABLED_ENV`.
- `brief.py`: email en `_platform_states` (ya está en `_LABEL`).

### Responder (capacidad NUEVA — mensajería era solo-lectura)

- Tool FlashBrain **`reply_message(n, text)`** (function-calling, fiable — V2-026; NO tag inline). El provider la
  mapea a `_apply_widget_data("mensajeria", "reply", {n, text})` → reutiliza el gate CONFIRM (V2-025) → lee el
  borrador y pide OK → al "sí" despacha la data-op `reply`.
- Manifest de `mensajeria`: acción declarada `reply` con `"confirm": true` (irreversible: enviar no se deshace).
- `data.apply_action("reply", {n,text})` → localiza el item n → encola en `pending_reply` (con `to`/`msgid`/
  `subject`) y marca leído. `owner.handle` drena `pending_reply` → `ingest.publish_reply` al bus. El conector
  email drena `ReplyInbox("email")` → SMTP `In-Reply-To`/`References`.
- Diseñado GENÉRICO: WhatsApp/Telegram podrán heredar `reply` después (su conector drena la misma cola).

### Auto-respuesta (DIFERIDA, OFF)

Flag `autoreply: false` en la config del conector (placeholder, sin lógica). Es una opción futura, siempre OFF
por defecto.

## Seguridad / privacidad

- Credenciales SOLO en `config/connectors.json` (gitignored, redactado: `email_password_set: bool`) — igual que
  el `api_hash` de Telegram. `.env` = fallback power-user.
- Triaje LOCAL (nada personal sale de la máquina), como WhatsApp/Telegram.
- Se conserva el filtro anti-`noreply`/bulk + la verificación SPF/DKIM/DMARC de Hermes (metadato de confianza;
  no es un gate de autorización porque leemos el BUZÓN PROPIO del operador, no aceptamos órdenes de remitentes).

## Tests

- `connectors/email/test_mailbox.py` — parsers puros (decode headers, HTML→texto, noreply, auth-results) sin red.
- `connectors/messaging/test_reply.py` — `pending_reply` end-to-end (apply_action reply → owner drain → bus).

## Pasos del operador (UI, sin `.env`)

1. Abrir el widget Mensajería → tarjeta **Email** → elegir proveedor (Gmail/Outlook/otro).
2. Introducir dirección + **app-password** (Gmail/Outlook requieren 2FA + app-password; "otro" pide IMAP/SMTP).
3. Conectar. El conector arranca en caliente y empieza a triar el buzón.

## Bitácora

- **2026-07-17** — Diseño + build inicial (conector + integración messaging + responder con confirm-gate +
  tarjeta en widget + docs + tests). Fuente reutilizada: adaptador email de Hermes (stdlib IMAP/SMTP).
- **2026-07-17 (tarde)** — Rediseño del widget `mensajeria` (feedback del operador tras probar en vivo): (1) el
  primer intento de conectar email se quedaba en "Conectando…" ETERNO — causa: el server corría código VIEJO (no
  se había reiniciado tras el build) → la orden de conectar email se caía en silencio; **reiniciado y verificado en
  vivo** (email ya es canal reconocido). (2) UX: el estado de conexión gana `detail` (mensaje humano) + estado
  `error`; loaders (spinner) + info en cada fase; card de error con motivo accionable + reintentar (fin del spinner
  eterno). (3) Widget genérico de fábrica: **arranca VACÍO** (0 conectados → "Canales disponibles"), con ≥1 parte de
  la lista de mensajes; header solo con iconos CONECTADOS + botón 🔌 de conectores; **desconectar con confirmación**
  (borra credenciales), vía única. (4) "conéctame a Gmail/correo" → widget mensajeria (no navegador). Commits
  `899ed7e` (widget) sobre `2521493`.

### Revisión de alineación — conector email V2-051 (2026-07-17)
- **Código/arranque:** limpio (sin legacy nuevo; grep de símbolos = solo lo vigente). Imports OK en contexto del
  server; server vivo responde `{"brain":"nucleo"}`, voz NO activa. Boot en vivo del stack completo NO forzado (el
  conector es INERTE hasta que el operador lo conecta desde la UI, `enabled=False` por defecto) → verificación de
  boot en caliente queda a un `make run` del operador; imports + tests cubren el resto.
- **Tests:** 111 passed (connectors/ + widgets/mensajeria/). Nuevos: `test_mailbox.py` (parsers puros IMAP/SMTP),
  `test_reply.py` (flujo responder end-to-end). Superficie observable (responder por voz) = escenario tester
  `email_reply` añadido (ejercicio en vivo pendiente de correo conectado).
- **CLAUDE.md:** conectores + decisión de mensajería actualizadas (email + responder + puntero a V2-052).
- **Docs canónicas:** `zaelar-architecture.md §8` (tool `reply_message`), `zaelar-modules.md §Connectors`
  (connectors/email + costura de responder), `cluster.yaml`. Sin legacy.
- **Diagramas HTML:** tabla de TOOLS (fila `reply_message`) + sello «Actualizado: 2026-07-17» (pestaña FlashBrain);
  `node --check` del JS embebido OK.
- **Roadmap:** V2-051 → HECHO (esta iniciativa, con commits + bitácora). V2-052 abierta como DISEÑO/backlog. No se
  editó `state.json`.
- **Regla de oro:** código ↔ contexto ↔ docs ↔ diagrama alineados: **sí**.
- **Abiertas:** (1) boot en caliente del stack a criterio del operador (inerte por defecto); (2) `send` en
  WhatsApp/Telegram y envío-a-persona por nombre = **V2-052** (backlog, decisiones cerradas); (3) auto-respuesta
  automática = flag OFF, diferida.
