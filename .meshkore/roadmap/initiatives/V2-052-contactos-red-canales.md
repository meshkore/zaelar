# V2-052 — Contactos como memoria + envío-a-persona + red de canales (y de agentes)

**Estado:** 📋 BACKLOG · DISEÑO CERRADO (2026-07-17) — decisiones tomadas, NO planificado aún · **Ancla:** EPIC-v2-colmena
**Depende de:** V2-051 (conector email + responder genérico por canal) — la costura de envío ya existe.

> Iniciativa de DISEÑO. Recoge la visión del operador (2026-07-17). **No se construye hasta cerrar las decisiones
> abiertas** (§Decisiones a cerrar). El envío-a-una-respuesta ya está (V2-051); esto es el envío-a-una-PERSONA.

## El problema (palabras del operador)

Tenemos un buzón que recibe de Telegram, WhatsApp y ahora email. Pero si el operador dice **«mándale un mensaje a
Pablo Sabin»**:
- Hay que **saber quién es Pablo Sabin** (contacto).
- Saber **qué canales tenemos abiertos con esa persona** (WhatsApp / Telegram / email) y **cuál es el predeterminado**.
- Las primeras veces quizá haya que **preguntarlo**; o **deducirlo por el volumen** de mensajes que llegan por cada canal.
- Hay que **identificar TODOS los contactos**. Idealmente con **conectores a Contactos de Apple y de Google** para
  meterlos en la memoria — si no, a cada contacto habría que preguntarle su cuenta de Telegram o su teléfono. Algunos
  se pueden encontrar por los conectores, pero no será muy preciso.
- **Los contactos NO son datos de widget: son datos de la PERSONA** (del mundo del operador). Esto forma parte de un
  plan más amplio del widget + los conectores + cómo trabaja la memoria.
- Los contactos sirven para **tejer redes**: cada contacto tiene unos canales de comunicación y, algún día, **un
  agente** — cuando lo tenga, comunicaremos **agente a agente**. Por eso los contactos deben estar **bien colocados en
  la memoria**, cada uno asociado a sus canales. Es una **memoria jerárquica** (que ya tenemos).
- Probablemente haga falta un **RAIL para manejar contactos** (es algo bastante primario del sistema).

## Propuesta (borrador, a validar)

### 1. El contacto = ENTIDAD de primera clase en la MEMORIA CENTRAL (no en el widget)

Coherente con «los contactos son datos de la persona». Reusamos la memoria jerárquica que YA existe (`memory/`):
píldoras con `slot` (supersede/dedup exacto) + grafo de conceptos + capas. Un contacto se modela como:

- **Píldora-entidad** con `slot="contact:<id>"` (id canónico estable, p.ej. `contact:pablo-sabin`), `kind="contact"`,
  texto canónico = nombre + alias conocidos. Nace del registro de slots (`memory/slots.py`) → una capa que no diverge.
- **Canales** por contacto: `slot="contact:<id>:channel:<platform>"` con `value = {handle/address, confidence,
  source, last_seen, volume}`. `platform ∈ {whatsapp, telegram, email, …}`. El **volumen** se refuerza cada vez que
  llega/mandamos un mensaje por ese canal (write-side, off-hot-path).
- **Canal predeterminado**: derivado (mayor volumen · más reciente) PERO **sticky si el operador lo fija una vez**
  (`slot="contact:<id>:default_channel"`). La primera vez que sea ambiguo, se PREGUNTA y la respuesta manda.
- **Grafo**: el contacto es un NODO; aristas a sus canales, a temas (proyectos, familia…) y —futuro— a su agente.
  El visor 🧠 gana una vista de contactos (o los pinta como nodos-entidad en el mapa de conceptos).

Lectura en la ruta caliente = DIRECTA (µs, sin LLM): resolver «Pablo» → `contact:*` por match difuso del nombre/alias
(como `widgets/refs.py` pero sobre entidades de memoria). El envío nunca dispara el retriever pesado.

### 2. Ingesta de contactos — dos vías (misma entidad)

- **(A) PASIVA (gratis, ya casi tenemos)**: cada mensaje entrante ya lleva identidad por canal (`source`+`entity`,
  V2-021). Extendemos el write-back para **crear/reforzar la entidad-contacto + su canal + volumen** al triar. Así los
  contactos con los que YA hablas se auto-construyen sin pedir nada. Impreciso pero real (nombre visible + handle).
- **(B) CONECTORES DE AGENDA (precisos)**: importadores one-shot/periódicos que vuelcan la libreta a memoria:
  - **Apple Contacts** (macOS, LOCAL, sin OAuth): `Contacts.framework` vía PyObjC o lectura del `AddressBook` sqlite /
    `osascript`. Nombre + teléfonos + emails + (a veces) handles.
  - **Google Contacts** (People API, OAuth — mismo patrón que Spotify V2-041): nombre + teléfonos + emails.
  - Cross-referencia con lo observado (A): el teléfono de la agenda casa el chat de WhatsApp; el email casa el buzón.
  - Nuevo escritor de credenciales (como los demás conectores; UI-managed, redactado).

### 3. Envío-a-persona — tool `send_message` + RAIL de contactos

- Tool FlashBrain **`send_message(contact, text, channel?)`** (distinta de `reply_message`, que responde a un
  entrante). Resuelve `contact` → entidad; elige canal (default deducido, o `channel` explícito); **confirm-gate**
  lee el borrador + el canal («Le escribo a Pablo por WhatsApp: «…». ¿Lo envío?») antes de mandar.
- Reusa la **costura de envío de V2-051**: cola outbound + `msg.reply`/`ReplyInbox` por conector (email ya envía;
  WhatsApp/Telegram necesitan su `send` — hoy son solo-lectura, es trabajo nuevo por conector).
- **RAIL de contactos** (patrón V2-042, `nucleo/rails.py`): cadena EN CÓDIGO resolver-contacto → resolver-canal →
  (preguntar si falta/ambiguo, doctrina «no hardcodear, preguntar el dato que falta») → confirmar → enviar; runs
  vivos en `state.rails`; writeback (refuerza canal/decisión aprendida). Es primario → merece rail propio.

### 4. Red de agentes (futuro, placeholder)

Cuando un contacto tenga un AGENTE, su «canal» preferente pasa a ser agente↔agente por el canal de cluster
(`connectors/meshkore/`). La entidad-contacto ya tendrá el sitio para ese canal (`contact:<id>:channel:agent`).
Nunca se transmiten memoria/credenciales/user-rules del operador (invariante de seguridad del cluster).

## Decisiones (CERRADAS con el operador, 2026-07-17)

1. **Dónde viven los contactos** → ✅ **Entidad en la MEMORIA CENTRAL** (`slot contact:<id>` + canales +
   nodo del grafo). No datos de widget. (Un widget-cara opcional podría añadirse luego, la verdad vive en memoria.)
2. **Canal predeterminado** → ✅ **Deducir por volumen/recencia + confirmar la 1ª vez ambigua (sticky)**. Aprende
   solo; la respuesta del operador queda fijada en `contact:<id>:default_channel`.
3. **Primer origen de contactos** → ✅ **PASIVA primero** (construir contactos+canales+volumen de los mensajes que
   ya llegan; gratis, sin OAuth, inmediato). Conectores de agenda (Apple local · Google People API) = DESPUÉS.
4. **`send` en WhatsApp/Telegram**: hoy solo-lectura. Email ya envía (V2-051) → **Fase 1 = email**; habilitar envío
   en WhatsApp (Baileys `sendMessage`) / Telegram (Telethon `send_message`) = fase posterior.
5. **Alcance/tiempo** → ✅ **Queda en DISEÑO por ahora**. El conector email + responder (V2-051) ya está entregado;
   V2-052 se construye en una tanda dedicada, revisando el diseño con el operador, no encima de V2-051.

### Orden de construcción propuesto (cuando se retome)

- **Fase 1** — contactos PASIVOS en memoria (entidad + canales + volumen desde el triaje) + tool `send_message` +
  rail de contactos + confirm-gate, enviando por **email** (ya sabe). Deducción de canal + confirm sticky.
- **Fase 2** — `send` en WhatsApp/Telegram (por conector).
- **Fase 3** — conectores de agenda (Apple Contacts local; Google People API OAuth) → cruce con lo observado.
- **Fase 4** — canal `agent` por contacto (red agente-a-agente vía cluster).

## Notas de seguridad/privacidad

- La agenda es dato personal SENSIBLE → import LOCAL, memoria local, credenciales redactadas. Google People = OAuth
  con scope mínimo (solo lectura de contactos).
- El `send_message` a un contacto es outbound irreversible → SIEMPRE confirm-gate (como el reply de V2-051).
- Match de contacto ambiguo → PREGUNTAR, nunca enviar al contacto equivocado (espejo de `refs.py`).

## Bitácora

- **2026-07-17** — Diseño inicial a partir de la visión del operador (envío-a-persona multicanal + contactos en
  memoria jerárquica + conectores de agenda + red de agentes). Pendiente de cerrar decisiones §.
