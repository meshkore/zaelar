# Bridge vendorizado — procedencia

Este directorio es una **copia** (vendoring) del bridge WhatsApp/Baileys de Hermes. zaelar lo **posee** para
poder parchearlo y para blindarlo ante `hermes update` (que hace `git pull` + auto-stash sobre
`~/.hermes/hermes-agent` y reescribiría cualquier edición in-place). Ver
`.meshkore/docs/architecture/zaelar-hermes-federation.md`.

## Origen

- **Repo upstream**: `~/.hermes/hermes-agent` (git)
- **Commit vendorizado**: `190e1ffac976ee5fc41c9f1845ba8fd886a827b1` (v0.17.0, 2026.6.19)
- **Ruta upstream**: `scripts/whatsapp-bridge/`
- **Pin de Baileys** (de `package.json`): `WhiskeySockets/Baileys#01047debd81beb20da7b7779b08edcb06aa03770`
- **Fecha de vendoring**: 2026-07-06

## Archivos

Copiados tal cual: `bridge.js`, `allowlist.js`, `allowlist.test.mjs`, `package.json`, `package-lock.json`.
NO se copia `node_modules/` — se regenera con `npm install` en esta carpeta (deps propias, desacopladas de Hermes).

## Parches de zaelar

Todos los cambios sobre el upstream van marcados con el comentario `// ZAELAR-PATCH:` para localizarlos por grep
y reaplicarlos tras un re-vendor. Parches actuales (INI-014):

1. **`POST /mark-read`** — marca conversaciones como leídas (`sock.readMessages`). Upstream no lo tiene.
2. **Modo `observe`** (`--mode observe` / `WHATSAPP_MODE=observe`) — reenvía TODO lo entrante (no-`fromMe`) a
   `/messages` sin responder ni depender de allowlist, para triaje. Upstream solo tiene `self-chat`/`bot`.
3. **QR como data-URI** — `connection.update` genera el QR también como PNG data-URI (dep nueva `qrcode`), lo
   guarda en `currentQR` y lo expone en `GET /health` (`qr`), para pintarlo en el widget del canvas (el operador
   escanea ahí, no en un terminal). Se limpia al conectar. Upstream solo lo imprime en la terminal.

## Re-vendoring (adoptar mejoras de upstream)

1. `make wa-bridge-check` — diff contra `~/.hermes/hermes-agent/scripts/whatsapp-bridge/bridge.js`.
2. Si upstream ya aporta lo que parcheamos → retirar el `// ZAELAR-PATCH:` y re-vendorizar limpio.
3. Si no → re-vendorizar base nueva y reaplicar los `// ZAELAR-PATCH:`.
4. Actualizar este archivo con el nuevo commit.

Candidato a PR upstream: `mark-read` + modo `observe` son features limpias y genéricas.
