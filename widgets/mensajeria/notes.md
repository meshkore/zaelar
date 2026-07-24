# Mensajería widget — contexto / decisiones (INI-015)

Widget **único, de primera clase, hand-built** (como `agenda`) que unifica la mensajería personal del operador:
**WhatsApp + Telegram** hoy, **email** como slot futuro. Sustituye al antiguo widget `whatsapp` (borrado). NO lo
genera el Claude Code local — su backend son los motores de los conectores, no código generable a demanda.

## Arquitectura (frontera)
- **Motores**: `connectors/whatsapp/service.py` (bridge Baileys vendorizado) y `connectors/telegram/service.py`
  (userbot Telethon, in-process) corren en el lifespan del server (gated `WA_ENABLED` / `TG_ENABLED`, siempre-on).
  **AMBOS escriben el MISMO store** `widgets/_data/mensajeria.json` vía `connectors/messaging/store.py`
  (platform="whatsapp" / "telegram").
- **Capa común** `connectors/messaging/`: `triage.py` (clasificador LOCAL agnóstico de plataforma), `store.py`
  (store unificado), `notify.py` (aviso proactivo), `brief.py` (brief numerado combinado), `dispatch_tag` ([[msg.*]]).
- **Widget**: `data.py` solo LEE el store unificado (vía `messaging.store`, nunca lanza). `widget.js` pinta. El
  desktop auto-refresca (`GET /widgets/mensajeria/data`) → QRs en vivo y mensajes nuevos aparecen solos.
- **QR por plataforma**: WhatsApp lo genera el bridge (data-URI PNG, ZAELAR-PATCH #3); Telegram lo genera el
  servicio con `segno` a partir del `tg://login` URL de `client.qr_login()`. Ambos viajan en el store
  (`platforms.<p>.qr`), el widget los pinta `<img>` en su tarjeta de conexión.

## Store schema (`widgets/_data/mensajeria.json`, lo escriben los conectores)
`{platforms:{whatsapp:{status,qr},telegram:{status,qr}}, updated, items:[{n,platform,from,group,isGroup,body,urgencia,dirigido_a_mi,motivo,messageId,chatId,senderId}], pending_read:[{platform,chatId,messageId,senderId}]}`
- `status` por plataforma: off | no_creds | starting | connecting | connected.
- Acciones (`apply_action`): `read` (marca leído en su app → encola key con `platform` en `pending_read`; el
  conector correcto lo drena), `dismiss` (solo oculta), `clear` (todo leído).

## Decisiones
- **Lista plana combinada por urgencia** (no agrupada por conversación ni por app); cada fila lleva un **badge de
  plataforma** (WhatsApp/Telegram/✉). Lo `dirigido_a_mi` se resalta en **amarillo** (fila `.me`, `--hb-warn-*`).
- Cuando una plataforma NO está vinculada (status connecting/no_creds/starting) → **tarjeta de conexión con su QR
  inline**. Si el conector está `off` (desactivado) → se omite (no es ruido).
- Cuerpos = **no confiables** → SIEMPRE `textContent` (anti-XSS, invariante del sistema de widgets).
- Voz: `[[show:mensajeria]]` abre; `[[msg.read:N]]`/`[[msg.dismiss:N]]`/`[[msg.clear]]` controlan la lista
  combinada (la acción enruta al conector correcto según `item.platform`).

## Rediseño 2026-07-08 — perfil "simple" por defecto
- Operador: "un amasijo de texto", demasiado colorista, quiere algo tipo Apple Messages / Claude Code — timeline
  vertical sin borde por mensaje, fuentes más grandes, sin duplicar título/canal, menos iconos y pills.
- **Dos perfiles, elegidos por el usuario, cosméticos únicamente** (localStorage `hb-msg-profile`, NUNCA toca el
  store ni pasa por Hermes): `simple` (nuevo, por defecto — timeline sin bordes, `.tl`/`.trow`) y `completo` (el
  diseño original con tarjetas y badges de color, código intacto en `richList()`). Ambos perfiles pintan los
  MISMOS datos — el perfil decide solo la presentación.
- Cabecera: título + un punto por plataforma (verde `--hb-accent2` = conectada, gris `--hb-neutral` = no) +
  icono ⚙ que abre/cierra un panel de Ajustes (perfil + plataformas conectadas + canales silenciados). El pie
  fijo con chips "conectado/desvincular" que estaba SIEMPRE visible se sustituyó por este panel bajo demanda.
- Perfil simple: badge de plataforma = círculo con la inicial (T azul, W verde) en vez de pill con el nombre.
  Mensajes largos (>220 caracteres o >4 líneas) se clampan a 3 líneas (`-webkit-line-clamp`) con un enlace
  "mostrar más/menos" (estado en memoria `_expanded`, por `messageId`). URLs del cuerpo se enlazan con `linkify()`
  construyendo nodos DOM (textContent/createTextNode, NUNCA innerHTML — los cuerpos siguen siendo no confiables).
  `cleanBody()` colapsa 3+ saltos de línea seguidos a 2, sin tocar emojis/enlaces.
- **Fix de bug arrastrado**: `unhide` enviaba siempre `chatId:null` → nunca reactivaba un canal silenciado
  (`data.py` exige `chat_id is not None`). Ahora se reenvía `m.chatId` desde `data.muted_channels`.
- **Fix de bug visual**: cuando `from` y `group` coinciden (típico en canales de Telegram tipo "Serenity Markets
  (News) · Serenity Markets (News)") ya no se duplica — el `group` solo se pinta si es distinto de `from`. Aplica
  a ambos perfiles.
- Rechazado explícitamente: fondo amber/warning de fila para "dirigido a ti" en el perfil simple (demasiado
  colorista) — se sustituyó por un punto de color a la izquierda de la fila (rojo=urgente, azul=para ti).

## Ajuste 2026-07-08 (mismo día) — logos reales arriba + separar título/cuerpo
- Operador: en la cabecera quiere los ICONOS reales de WhatsApp/Telegram (no solo un punto de color); confirma
  que el badge POR MENSAJE con una letra (T/W) en azul/verde SÍ vale tal cual. También: hace falta diferenciar
  visualmente el nombre del canal (from) del "título" que trae el propio mensaje, y ese título del resto del texto.
- **Logos**: trazo oficial de simple-icons.org (CC0) embebido como `<path>` inline (`BRAND_SVG`, `brandIcon()`) —
  sigue siendo self-contained (nada de red/CDN en runtime, el SVG vive en el propio `widget.js`). Coloreados con
  `currentColor` + `var(--hb-accent2)`/`var(--hb-accent)` (mismos tokens que ya usaban los chips), NO el hex de
  marca real, para no meter una tercera paleta. Solo en la cabecera — el badge por mensaje sigue siendo letra.
  Estado no-conectado = mismo icono atenuado (opacity), no un gris distinto (se sigue reconociendo la app).
  `.pdot`/`miniDot()` se queda para el panel de Ajustes (lista de conectados), sin tocar.
  **Idea aparcada**: si algún día compensa, `web/svg-brand-icons` puede volver a auditarse contra la fuente
  cuando `simple-icons` publique un rediseño — de momento congelado, no re-sincronizar automáticamente.
- **Título vs cuerpo** (`splitBody()`): muchos mensajes triados llegan como `"Título corto\n\nResto del texto"`
  (p.ej. "Visión semanal\n\nEn el siguiente vídeo..."). Si se detecta ese patrón (línea corta + línea en blanco),
  el título se pinta en semibold (`.ttitle`) y el resto en un tono más apagado (`.tbody.sub`); si el mensaje es
  un bloque único sin ese patrón (p.ej. "$REKR big blocks going off"), no se separa nada y se pinta como antes.
  El clamp de 3 líneas + "mostrar más" ahora mide solo el RESTO (el título casi siempre cabe en una línea).

## Rediseño 2026-07-08 (mismo día) — agrupado por CHAT + hilo abierto (drill-in) + voz
- Operador: 30 mensajes sueltos en un día es demasiado ruido; quiere ver CHATS (uno por conversación, con cuántos
  pendientes tiene) y solo entrar al hilo completo cuando le interesa — por clic O por voz ("enséñame el chat de
  Telegram de X"). Pidió también una vista ANCHA (dos columnas, lista + hilo) "si fuera más ancho".
- **Agrupado (perfil simple, solo lista): `_group_chats()` en `data.py`** — agrupa la lista plana YA renumerada
  por `(platform, chatId)`, preservando el orden de aparición (no hay timestamp en el store: el "último mensaje"
  es el último EN ORDEN DE APARICIÓN, no por reloj). Cada chat lleva su PROPIO `n` — un addressing space DISTINTO
  del de `items` — con urgencia = la más grave de sus mensajes y `dirigido_a_mi` = si CUALQUIERA de ellos lo es.
- **Hilo abierto = estado de SERVIDOR, no solo de cliente** (`db["active_chat"] = {platform,chatId}`,
  `widgets/mensajeria/data.py`): así un clic en el widget y una orden de voz ([[msg.open:N]]) convergen en el
  MISMO sitio — el widget nunca guarda su propio estado de navegación en JS, siempre lee `data.active_chat`/
  `data.active_items` de `view_data()`. Auto-cierre cuando el hilo se queda sin mensajes (se leyeron todos) —
  evita un hilo vacío esperando "volver" Y evita que resucite si llega un mensaje nuevo mucho después en ese
  mismo chat, cuando el operador ya lo daba por cerrado.
- **Nuevas tags** (`voice/tag_protocol.py` `MSG_RE`, dispatch genérico sin cambios — ver `connectors/messaging/
  __init__.py::dispatch_tag`, ya enrutaba por prefijo `msg.` para CUALQUIER verbo): `[[msg.open:N]]` / `[[msg.close]]`
  (abrir/cerrar un hilo) y `[[msg.readchat:N]]` (marcar un chat ENTERO leído sin abrirlo). Disponibles tanto al
  fast/duo layer como a Hermes de igual manera que `msg.read/dismiss/clear` — NO pasan por el gate de `"safe"` de
  `widget.data` (ese gate es un mecanismo aparte, solo para acciones `[[widget.data:ID]]`).
- **Doble numeración, mismo patrón ya usado por read/dismiss**: sin chat abierto, N direcciona la lista de CHATS
  (`msg.open`/`msg.readchat`); con un chat abierto, N direcciona la lista de MENSAJES de ese chat (`msg.read`/
  `msg.dismiss`) — nunca las dos a la vez. `hide` (ya existente, vía `[[widget.data:mensajeria]]`) hereda la MISMA
  dualidad: sin chat abierto interpreta N como chat, con chat abierto como mensaje — mismo criterio, un solo lugar
  donde memorizarlo. `brief.py` cambia su texto según haya o no chat abierto, para que el brain vea EXACTAMENTE
  la misma numeración que el widget.
- **`brief.py` reescrito** para reflejar chats agrupados (antes: lista plana de mensajes). Sigue siendo la única
  fuente de vocabulario `[[msg.*]]` para el brain (inyectada vía `brains/duo/prompt.py::_briefs()` cada turno).
- Rechazado por alcance (no implementado esta vez): resize real por drag del widget — **no existe ningún mecanismo
  de resize en el canvas hoy** (solo mover, `[[move:ID:where]]`); construirlo sería un cambio de `desktop.js` para
  TODOS los widgets, no de este. La "vista ancha" (dos columnas) queda pendiente como toggle cosmético futuro en
  Ajustes si hace falta — de momento perfil simple = una sola columna con "← volver", perfil completo intacto.
- Perfil completo (tarjetas con borde) NO se tocó: sigue siendo la lista plana original, sin agrupar, sin hilo.
