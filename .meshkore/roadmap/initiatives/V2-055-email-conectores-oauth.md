# V2-055 — Conectores de email al máximo: OAuth2 + los 3 proveedores más populares

**Estado:** EN CURSO (2026-07-17) · Fase 0 HECHA · **Ancla:** EPIC-v2-colmena · mensajería unificada
**Depende de:** V2-051 (conector email IMAP/SMTP + responder). **Rama:** `feat/v2-055-email-connectors`.

## Objetivo

Llevar el módulo de email de zaelar a su **máximo**: no solo IMAP/SMTP con app-password (V2-051), sino **OAuth2**
(la vía moderna y, para Outlook, **obligatoria**). Entregar como mínimo los **3 conectores de email más populares**
del mercado, cada uno con el mejor método de auth disponible. Todos viven en una **lista única de conectores de
email** (`connectors/email/providers.py`).

### Los 3 (+2) más populares → la LISTA (`providers.py`)

| Proveedor | Cuota (aprox) | Auth recomendada | Estado |
|---|---|---|---|
| **Gmail** | ~1.8B | **OAuth2** (o app-password con 2FA) | núcleo OAuth listo; falta app + UX + verificación |
| **Outlook / Microsoft 365** | ~400M | **OAuth2 (ÚNICA — basic-auth deshabilitada sep-2024)** | núcleo OAuth listo; falta app + UX + verificación |
| **Yahoo Mail** | ~225M | app-password | funciona ya (V2-051, preset) |
| iCloud Mail | — | app-specific password | funciona ya (preset) |
| Otro (IMAP/SMTP genérico) | cola larga | app-password (Fastmail, Proton Bridge, corporativo) | funciona ya |

**Decisión técnica clave:** transporte **XOAUTH2 sobre IMAP/SMTP** para OAuth (no las APIs REST Gmail/Graph) →
Gmail y Outlook reusan el MISMO `mailbox.py` (el token sustituye a la contraseña). Un solo transporte, dos
proveedores de identidad. (Las APIs REST se dejan como opción futura si se quiere push/labels nativos.)

## Inventario reutilizable (buscado en Hermes, OpenClaw, independientes)

- **IMAP/SMTP core** → adaptador de email de Hermes (stdlib). **YA vendorizado** en V2-051 (`mailbox.py`).
- **OAuth Google (authorization-code + refresh + token store + CLI)** → Hermes
  `plugins/platforms/google_chat/oauth.py` (patrón); **nuestro** `connectors/spotify/auth.py` (V2-041, PKCE +
  callback servido por el server) = plantilla in-repo directa.
- **OAuth Microsoft** → Hermes `tools/microsoft_graph_auth.py` (token URL/authority de `login.microsoftonline.com`;
  es app-only → adaptamos a delegated auth-code). Graph mail NO está en Hermes → usamos XOAUTH2-over-IMAP.
- **OpenClaw** (`~/.openclaw`) → NO tiene conector de email (solo `plugins`, sin IMAP/SMTP/OAuth de correo).
- **himalaya** (skill de Hermes) → CLI Rust externo; DESCARTADO (mete dependencia binaria; nuestro core es stdlib).
- Librerías independientes (si se necesitan): `msal` (Microsoft), `google-auth`; se EVITAN mientras XOAUTH2 manual
  baste (cero deps nuevas, coherente con "el más limpio de los tres").

## Fase 0 — Fundación (HECHA, esta rama)

- [x] **Registro de proveedores** `connectors/email/providers.py` — la LISTA: id/label/hosts/`auth_methods`/`oauth`
      (authority/authorize/token/scopes/pkce) + deducción por dominio + vista pública redactada. `PRESETS` legacy
      re-exportado. (tests: `test_providers.py`)
- [x] **Transporte XOAUTH2** en `mailbox.py` — `Mailbox(auth_mode="oauth", token=…)` + `xoauth2_sasl()`
      (RFC 7628) en IMAP (`authenticate XOAUTH2`) y SMTP (`AUTH XOAUTH2`). Password intacto. (tests: `test_mailbox.py`)
- [x] **Núcleo OAuth** `connectors/email/oauth.py` — PKCE S256, `authorize_url()` (stashea state+verifier),
      `exchange_code()`, `access_token()` (refresh automático), token store `.meshkore/credentials/email_oauth.json`
      (chmod 600, gitignored), `configured()`/`tokens_present()`/`forget()`. Model-agnóstico por `OAuthSpec`.
      DORMANTE hasta registrar app (como Spotify). (tests: `test_oauth.py`)
- [x] **Wiring** `config.mailbox()` OAuth-aware (`auth_method()`: oauth si hay app+token, si no password;
      `resolved_provider_id()` por elección/dominio). 25 tests verdes; suite adyacente 128 verdes.

## Fase 1 — Gmail OAuth end-to-end (PRIORIDAD)

- [ ] **T1.1** — Registrar la app OAuth de zaelar en Google Cloud (operador): proyecto → OAuth consent screen
      (External, scope `https://mail.google.com/`) → credenciales "Desktop"/"Web" con redirect
      `http://127.0.0.1:8473/api/email/callback` → `client_id` (+ secret si "Web") al credential store como
      `EMAIL_GMAIL_CLIENT_ID` / `EMAIL_GMAIL_CLIENT_SECRET`.
- [ ] **T1.2** — `server/email_api.py`: `POST /api/email/oauth/connect {provider,address}` → `authorize_url()`;
      `GET /api/email/callback?code&state` → `exchange_code()` → activa el conector (config.set enabled + provider)
      → página de éxito. Espejo de `server/spotify_api.py`. Registrar el router en `server/__init__.py`.
- [ ] **T1.3** — Widget `mensajeria`: en el canal Gmail, si `oauth.configured("gmail")`, mostrar **"Iniciar sesión
      con Google"** (abre la URL de consentimiento; el server drena el callback → SSE `connector.status`). Mantener
      "usar app-password" como alternativa. Reflejar el mismo patrón de apertura de consentimiento que usa `musica`
      (Spotify) — verificar cómo abre la URL desde el canvas.
- [ ] **T1.4** — Verificación EN VIVO: conectar la cuenta real del operador → leer bandeja (IMAP XOAUTH2) → triaje →
      responder por voz (SMTP XOAUTH2 con threading) → confirmar refresh de token tras >1h.
- [ ] **T1.5** — Manejo de errores OAuth en la UI (consent denegado, scope insuficiente, token revocado → re-login).

## Fase 2 — Outlook / Microsoft 365 OAuth

- [ ] **T2.1** — Registrar app en Microsoft Entra (operador): "Mobile and desktop" (public client + PKCE, sin
      secret) → scopes delegados `IMAP.AccessAsUser.All`, `SMTP.Send`, `offline_access` → redirect
      `http://127.0.0.1:8473/api/email/callback` → `EMAIL_OUTLOOK_CLIENT_ID`.
- [ ] **T2.2** — Verificar el flujo con `login.microsoftonline.com/common` (multi-tenant + cuentas personales).
- [ ] **T2.3** — Widget: **"Iniciar sesión con Microsoft"** en el canal Outlook (sin opción password: la lista ya
      marca `auth_methods=("oauth",)`). Verificar IMAP/SMTP XOAUTH2 contra `outlook.office365.com`.
- [ ] **T2.4** — Verificación en vivo (leer + responder). Fallback documentado si Microsoft exige app "Web" + secret.

## Fase 3 — Yahoo + IMAP genérico (endurecer)

- [ ] **T3.1** — Pulir la UX de app-password de Yahoo/iCloud (enlaces a dónde generarla, validación del error).
- [ ] **T3.2** — "Otro (IMAP/SMTP)": autodetección de puertos (993/143, 465/587), STARTTLS vs SSL, notas para
      Fastmail / ProtonMail Bridge / correo corporativo.

## Fase 4 — Tests, docs, observabilidad

- [ ] **T4.1** — Tests del server callback (mock del token endpoint) + del wiring OAuth de `config.mailbox()`.
- [ ] **T4.2** — Escenario de tester `email_oauth` (conectar por OAuth simulado / o marcar como manual).
- [ ] **T4.3** — Docs: `zaelar-modules.md §Connectors` (registro + OAuth), `cluster.yaml`, diagrama `/architecture`
      (nota de OAuth por proveedor), `zaelar-conventions §Configuration is UI-managed` (apps OAuth = setup guiado).
- [ ] **T4.4** — Revisión de alineación + cierre.

## Pasos del operador (una vez por proveedor)

1. **Gmail**: crear proyecto en Google Cloud + OAuth consent + credencial → pegar `client_id` en la config (⚙) o
   credential store. (Mientras no exista, Gmail sigue conectando por app-password.)
2. **Outlook**: registrar app en Microsoft Entra (public client) → `client_id`. (Sin esto, Outlook NO conecta —
   Microsoft no admite app-password.)
3. Yahoo/iCloud/otros: nada — app-password desde el widget.

## Bitácora

- **2026-07-17** — Fase 0 construida (registro de proveedores + XOAUTH2 + núcleo OAuth + wiring + 25 tests).
  Inventario reutilizable documentado (Hermes google_chat/oauth + microsoft_graph_auth + spotify/auth; OpenClaw sin
  aporte; himalaya descartado). Decisión: XOAUTH2-over-IMAP reusa `mailbox.py` para Gmail y Outlook. Fases 1-4 =
  registro de apps (operador) + callback/UX + verificación en vivo.
