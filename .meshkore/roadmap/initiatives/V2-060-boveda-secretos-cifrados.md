# V2-060 — Bóveda de secretos del operador (cifrado end-to-end + passkeys)

**Estado:** ✅ CONSTRUIDO (2026-07-21) — rama `feat/v2-060-boveda-secretos-cifrados`. **F0·F1·F2·F3 hechos y
verdes** (server + cerebro + frontend + passkeys). Pendiente: modo ESTRICTO zero-knowledge (descifrado en el
NAVEGADOR con libsodium-WASM) + diagrama `/architecture` → al MERGE / F4 (cloud). Ver §14.
**Ancla:** EPIC-v2-colmena · **Se cruza con:** V2-052 (entidades/contactos en memoria), `project_cloud_saas`
(cripto dual-mode zero-knowledge), V2-046 (USER RULES / sistema arena)

> Iniciativa de DISEÑO. Recoge la visión del operador (2026-07-21). **No se construye hasta cerrar las decisiones
> abiertas** (§9). Toca a la vez la **memoria** (nuevo gate de clasificación + storage partido), la **seguridad**
> (bóveda cifrada + WebAuthn) y la **configuración de frontend** (área ⚙ de seguridad + comandos de voz + user
> rules duras). Por eso vive documentada también en `zaelar-security.md`, `zaelar-memory.md` y
> `zaelar-conventions.md` — el contexto tiene que estar claro en los tres.

## 1. El problema (palabras del operador)

Queremos poder decirle a zaelar cosas como **«guárdame la contraseña de Netflix, es esta»**, o darle **números de
cuenta de Ethereum/Solana** para calcular un balance, o **tarjetas, IBANs, o la private key de un wallet**. Sería
brutal que, cuando lo necesite, le diga *«dame el usuario y contraseña de Netflix»* y me lo sirva sin tener que
buscarlo ni recordar dónde está. **PERO** esa información **no puede estar en claro** — ni en local ni en la nube.

Entonces: el **light brain / sistema de memoria**, al ir a guardar un dato, debe **evaluar si es susceptible de ser
privado/protegido** y, si lo es, guardarlo **cifrado**. Cuando pida un dato cifrado, la memoria le indica al
FlashBrain que **debe solicitar el desbloqueo al usuario**. Dos modelos de seguridad, seleccionables por grado del
dato **o** por preferencia del usuario:

- **Cómodo:** desbloqueas una vez y la clave vive en RAM mientras dura la sesión → la memoria puede servir esos datos
  sin volver a pedir.
- **Máxima seguridad (zero-retention):** cada acceso pide desbloqueo, descifra en el navegador, y **borra la clave al
  instante** — no la guarda en ningún momento, ni en el estado.

Idea del operador para el desbloqueo: **passphrase** simple + integrar **passkeys** (Touch ID / Face ID / Windows
Hello / huella del móvil). Cuando pida un dato, «te lo pongo aquí / te lo digo, pero antes pon tu passkey» → pongo
el dedito y funciona; si no tengo passkey disponible, la passphrase a mano como equivalente/segunda vía de
recuperación. Debe funcionar en **Windows y Mac** (Linux, si se puede, bonus).

## 2. Decisiones tomadas (operador, 2026-07-21)

| Eje | Decisión |
|---|---|
| **Modelo cripto** | **Asimétrico con UNA passphrase** (no dos palabras literales). *Guardar no pide clave; leer sí.* |
| **Passkeys** | **SÍ, primarias.** Si el aparato soporta passkey (WebAuthn) → desbloqueo por biometría; passphrase = **recuperación / fallback** (y vía Linux). Cross-platform vía navegador. |
| **Retención por defecto** | **Máxima seguridad: pedir SIEMPRE** (no cachear la clave). Con passkey esto es indoloro (un toque de huella por acceso). El modo «clave en RAM la sesión» queda como opción. |
| **Salida (voz/texto)** | **De momento relajado:** se dice por voz o texto tras desbloquear. PERO *«no me lo digas por voz»* es una **USER RULE DURA** que se aplica a rajatabla (§7). |

## 3. El modelo cripto — asimétrico + sobre (envelope) con N desbloqueos

### 3a. Por qué asimétrico (resuelve «guardar también pediría la clave»)

Con cifrado **simétrico** (una clave que cifra y descifra) habría que pedir la passphrase **cada vez que se guarda**
un secreto — incordio en una conversación de voz. Con **asimétrico** no:

- Un **par de claves**: **pública `PK`** (se guarda EN CLARO en la BD; no es secreta) + **privada `SK`** (secreta).
- **Escribir** un secreto = `sellar(PK, texto)` → **no requiere desbloqueo**. zaelar puede cifrar y guardar un
  secreto nuevo en cualquier momento, en mitad de la charla, sin pedir nada. *(Esto resuelve la preocupación del
  operador.)*
- **Leer** un secreto = necesita `SK` → **requiere desbloqueo**.

Primitiva: **sealed box** de libsodium (`crypto_box_seal`/`crypto_box_seal_open`) — cifrado a una clave pública sin
que el emisor tenga la privada. (`age` es una alternativa equivalente si se prefiere formato de fichero.)

### 3b. La privada `SK` se guarda ENVUELTA por N métodos de desbloqueo (key-wrapping)

Hay **una sola clave de datos** (`SK`). No se memoriza ninguna clave: `SK` se guarda **cifrada** (envuelta) por
**uno o más KEK** (key-encryption-keys) independientes. Cada método de desbloqueo = un sobre distinto que cifra la
MISMA `SK`:

- **Sobre A — passphrase (siempre existe):** `KEK_pass = Argon2id(passphrase, salt)` (salt en claro).
  `wrap_A = AEAD(KEK_pass, SK)`. Es la **red de recuperación** y la vía en Linux.
- **Sobre B — passkey (cuando el aparato lo soporta):** `KEK_pk = HKDF(PRF_output)` donde `PRF_output` los devuelve
  el autenticador (§4). `wrap_B = AEAD(KEK_pk, SK)`.
- **Más aparatos = más sobres.** Pierdes el móvil → la passphrase sigue abriendo. Añades un portátil → un sobre
  nuevo, **sin re-cifrar ningún secreto**.

**Desbloquear** = obtener cualquier `KEK` (por passphrase o passkey) → desenvolver `SK` → desellar el ciphertext del
secreto pedido. **Rotar la passphrase** = re-cifrar SOLO `wrap_A` (los secretos y `PK`/`SK` no se tocan → barato).
Passphrase equivocada → el AEAD del sobre falla → «contraseña incorrecta» limpio, sin exponer nada.

Librería sugerida: **PyNaCl (libsodium)** — `SealedBox` (sellar/desellar), `pwhash.argon2id` (KDF), `SecretBox`
(envolver `SK`). Dep pequeña, sin Docker. Del lado navegador (§4/§6): **libsodium-wrappers (WASM)**.

## 4. Passkeys — WebAuthn `prf`, cross-platform por el navegador

Las passkeys autentican, no cifran… salvo por la extensión **`prf`** de WebAuthn (sobre el `hmac-secret` de FIDO2):
el autenticador devuelve un **secreto estable de 32 bytes** derivado del credencial + un salt, y **solo lo suelta
tras el gesto biométrico** (Touch ID / Face ID / Windows Hello / huella / PIN). Ese secreto deriva `KEK_pk` (sobre B).

- **Registro** (una vez por aparato, tras verificar con la passphrase): `navigator.credentials.create(...)` con la
  extensión `prf`; se guarda el `credentialId` (no secreto) y se añade `wrap_B`.
- **Desbloqueo:** `navigator.credentials.get({ publicKey: { ..., extensions: { prf: { eval: { first: salt }}}}})` →
  `getClientExtensionResults().prf.results.first` = 32 bytes → `KEK_pk` → desenvuelve `SK`.
- **Cross-platform SIN código nativo:** es WebAuthn del **navegador** (la app ya corre en Chrome) → funciona igual
  en **Windows (Hello)** y **Mac (Touch ID)**, y en móvil. **Linux:** los autenticadores de plataforma con biometría
  son irregulares → **passphrase** cubre Linux (o una llave FIDO2 física).
- **`localhost` vs cloud:** las passkeys son **por origen** (RP-ID). En local RP-ID = `localhost` (contexto seguro,
  funciona); en la versión cloud = el dominio → enrolamientos distintos. La **passphrase es el puente común** entre
  ambos. (Detalle de implementación, no cambia la forma.)

**Sinergia con «pedir siempre»:** como el defecto es no cachear la clave, cada acceso pide desbloqueo — y con passkey
eso es **un toque de huella**. Máxima seguridad y comodidad a la vez; el modo «clave en RAM la sesión» casi sobra.

## 5. Clasificación al escribir — gate FAIL-CLOSED en el CORAZÓN

El **CORAZÓN de escritura** (`nucleo/mem_processor.py`), al destilar cada turno, además de DESCARTAR/ESTADO/CORTO/
LARGO decide **¿es un SECRETO?** (contraseña, PIN, IBAN, nº tarjeta, seed phrase BIP-39, private key, API key,
número de cuenta cripto). Si lo es → va a la **bóveda cifrada**, nunca a una píldora en claro.

**Regla invertida respecto al resto de la memoria: FAIL-CLOSED.** Un secreto que se cuele en claro = privacidad
rota, así que aquí NO vale el fail-open habitual:

- **Backstop determinista por patrón** (barato, corre siempre): Luhn de tarjeta, formato IBAN, 12/24 palabras
  BIP-39, `0x…` de 64 hex (private key EVM), claves `sk-…`/tokens, marcadores «contraseña/password/PIN de …».
- **+ clasificación del LLM** para lo que el patrón no ve («mi número de cuenta de Coinbase es…»).
- Ante la duda → **tratar como secreto** (cifrar). Un falso positivo (cifrar algo que no hacía falta) es barato; un
  falso negativo (dejar un secreto en claro) es inaceptable.

El operador también puede **forzar** por voz: «guárdame esto CIFRADO / en la bóveda» → salta el clasificador.

## 6. Almacenamiento partido — etiqueta buscable / valor opaco

Una píldora de bóveda separa **qué es** (buscable) de **el valor** (cifrado):

- **Etiqueta en claro y buscable**: «contraseña de Netflix», «wallet Ethereum principal», «IBAN de la nómina». Se
  embebe/indexa/rerankea NORMAL (para que «dame la de Netflix» la encuentre). Puede llevar `slot` (supersede) como
  `secret:netflix:password`.
- **Valor = blob cifrado opaco** (`sellar(PK, valor)`), `meta.vault=1` + `meta.sensitivity` (grado). **NUNCA** se
  embebe, se loguea, entra en el prompt, ni en un worker.

**Lectura:** el retriever encuentra por etiqueta y devuelve al FlashBrain la señal **«esto está sellado»** (nunca el
texto). Eso dispara el flujo del operador: la memoria indica al FlashBrain que **pida el desbloqueo**. Tras
passkey/passphrase:
- **salida por voz/texto permitida** (defecto): se descifra (navegador desenvuelve `SK`, desella; en modo relajado
  puede mandar el texto al servidor un instante para TTS) y se sirve.
- **user rule «solo pantalla»** (§7): se descifra **solo en el navegador**, se muestra, el servidor **jamás** ve el
  texto plano, no se sintetiza en voz.

## 7. USER RULES — blandas (estilo) vs DURAS (seguridad/config)

Hoy solo existe una clase de user rule (V2-046: `state.rules`, `set_style_directive`, cap 8) que **guía por prompt**.
Este diseño añade una **segunda clase**:

- **Rules BLANDAS (estilo):** las de V2-046. Guían al FlashBrain por prompt. Si una se ignora un turno, no pasa nada.
- **Rules DURAS (seguridad/configuración):** p.ej. *«nunca digas secretos por voz»*, *«pide passkey siempre»*,
  *«modo máxima seguridad»*. **NO pueden vivir solo en el prompt** (un no-razonador podría saltárselas) → se aplican
  en un **GATE DETERMINISTA EN CÓDIGO** en el punto de salida (antes de mandar nada al TTS / de servir un secreto).
  Son **inviolables**, **no cuentan** contra el cap de 8, no se desactivan por una frase casual, y solo cambian por:
  - **comando explícito** (voz reconocida por el gate como cambio-de-config), o
  - el **icono ⚙** (área de configuración).

Es decir: un subconjunto de user rules que **son configuración**. El enforcement de una regla de seguridad vive en
código, no en la buena voluntad del modelo.

## 8. Superficie de CONFIGURACIÓN de frontend (área ⚙ + voz) — «UI-managed»

Coherente con el invariante «instala una vez, todo desde la UI» (`zaelar-conventions.md §Configuration`). La bóveda
añade una **sección de SEGURIDAD** en el área de configuración full-screen (⚙, V2-043) y comandos de voz
equivalentes:

- **Estado de la bóveda:** creada / bloqueada / desbloqueada; nº de secretos; métodos de desbloqueo registrados.
- **Passphrase:** crear / cambiar (rota `wrap_A`) / recuperación.
- **Passkeys:** **enrolar este aparato** (flujo «añade este dispositivo» tras verificar con passphrase) · listar ·
  revocar un aparato (quita su sobre).
- **Política por defecto:** retención (pedir siempre ↔ RAM sesión) · salida (voz+texto ↔ solo pantalla) · grado a
  partir del cual un dato se considera secreto.
- **User rules duras (seguridad):** ver / añadir / quitar (con el mismo gate: solo por orden explícita o aquí).
- **Comandos de voz que tocan config:** «modo máxima seguridad», «no me digas secretos por voz», «pide siempre la
  huella» → el gate los reconoce como **cambio de configuración** (no charla) y los persiste como user rule dura +
  reflejo en el ⚙. El usuario puede revertir por voz o por ⚙.

Todo por el patrón habitual: store gitignored + módulo dueño + vista pública **redactada** (la passphrase/`SK`/PRF
**jamás** se devuelven al frontend; el store solo expone presencia/estado). **Nada de esto en `.env`** salvo
fallback power-user.

## 9. Invariantes de SEGURIDAD (duros)

La **passphrase**, la **clave privada `SK`** y el **PRF de la passkey** JAMÁS:

- entran en un **prompt de LLM** (ni el destilador ni el FlashBrain ni un worker),
- entran en un **worker** (ya vetados de identidad → extender el veto a la bóveda: un worker puede *escribir* un
  secreto —cifra con `PK`— pero **nunca descifrar**),
- se **loguean** (redacción dura en `observer` + journal + SSE; reusar `store.redact` y ampliarlo),
- se guardan en **`state`**, en una **píldora**, ni en el **caché** de `memory_cache`,
- en modo «solo pantalla», el **texto plano del secreto no toca el servidor** (descifrado en navegador).

El **valor cifrado** puede persistir donde sea (BD, backup, nube) porque es opaco sin `SK`.

## 10. Módulos afectados (para cuando se construya)

- **NUEVO `memory/vault.py`** — bóveda: keypair, sobres (wrap/unwrap), sellar/desellar, estado bloqueada/desbloqueada,
  clave en RAM opcional (modo cómodo). Substrato local; el descifrado real puede vivir en el navegador (modo estricto).
- **`nucleo/mem_processor.py`** — gate de clasificación FAIL-CLOSED (§5) + patrones deterministas.
- **`memory/schema.py` / `memory/slots.py`** — `meta.vault`/`meta.sensitivity`; slots `secret:*`; storage partido.
- **`nucleo/flash/router.py` + `prompt.py`** — señal «sellado → pide desbloqueo»; tool para servir un secreto tras
  desbloqueo; NUNCA el valor en el prompt.
- **`memory/state.py` (rules)** — segunda clase de user rules (duras/config) + registro separado del cap-8.
- **Gate de salida (voz)** — enforcement determinista de las rules de seguridad antes del TTS.
- **Frontend** — `frontend/app/components/ConfigPanel.js` (sección Seguridad) + un componente de bóveda +
  **WebAuthn/PRF en JS** + **libsodium-wrappers (WASM)** para el descifrado en navegador (modo estricto).
- **`config/`** — store de política de bóveda (owner + vista redactada) por el patrón UI-managed.
- **Docs** — `zaelar-security.md` (modelo), `zaelar-memory.md` (gate + storage), `zaelar-conventions.md` (config),
  CLAUDE.md (puntero de diseño), y el diagrama `/architecture` **cuando se construya** (hoy NO: es diseño).

## 11. Decisiones a cerrar (antes de planificar)

1. **Dónde vive el descifrado por defecto:** ¿navegador siempre (zero-knowledge puro, encaja con cloud) o servidor
   en modo cómodo (más simple para voz local)? El diseño soporta ambos; falta fijar el defecto de arranque.
2. **Recuperación si se pierde passphrase Y todos los aparatos:** ¿código de recuperación imprimible al crear la
   bóveda (sobre C)? Sin él, perder todo = perder los secretos (que es lo correcto en seguridad, pero hay que
   decidirlo conscientemente).
3. **Cloud:** ¿la nube guarda solo ciphertext (zero-knowledge, el server nunca puede descifrar) o hay un modo KMS
   24/7? (Ya apuntado en `project_cloud_saas` como dual-mode.)
4. **Cripto de wallet:** ¿la private key de un wallet se trata igual que cualquier secreto, o merece un aviso/gate
   extra al leerla (es la de mayor impacto)?
5. **Relación con el credential store del sistema** (`.meshkore/credentials/zaelar.env`): ese es para claves del
   SISTEMA (APIs de zaelar). La bóveda es para secretos del USUARIO (Netflix, wallet). Son cosas distintas; confirmar
   que no se mezclan.

## 12. Fases

- **F0 ✅ HECHO** — `memory/vault.py` (sealed box + sobre passphrase + storage partido + modos cómodo/estricto) +
  `memory/secrets.py` (gate FAIL-CLOSED + redact) + `memory/schema.py` v3 + `memory/vault_api.py` (HTTP) + tests
  (`tests/unit/memory/test_vault.py` + `test_secrets.py` + `tests/integration/test_vault_api.py`, 29 verdes). Ya
  cifra, guarda y sirve por passphrase; el valor jamás en claro en `memories`/ciphertext (verificado en test).
- **F1** — auto-vaulting conversacional + flujo de LECTURA end-to-end: `ingest_utterance` redacta+vaultea; el
  retriever/recall señala «sellado»; tool `reveal_secret` del FlashBrain; **inyección OUT-OF-BAND del valor** (§13);
  si bloqueada → pide passphrase (evento al modal). Modos de retención + salida.
- **F2** — user rules DURAS (segunda clase + gate de salida determinista + comandos de voz de config + ⚙).
- **F3** — WebAuthn `prf` + sobre passkey + enrolar/revocar aparato + descifrado en navegador (modo estricto,
  libsodium WASM) + **modal nativo de passphrase**.
- **F4** — cloud/zero-knowledge + recuperación + backups de ciphertext + diagrama `/architecture`.

## 13. Testabilidad (dominio nuevo del tester: «seguridad de datos») — DECISIÓN DEL OPERADOR

El sistema de testing (INI-013) **no puede usar biometría** (Touch ID/Face ID/Windows Hello son hardware). Por eso:

- **La passphrase es el camino TESTABLE.** El modal nativo del frontend pide la passphrase y la POSTea a
  `/api/vault/unlock`; el **tester conduce ESE MISMO endpoint** (o `reveal` con `passphrase` en modo estricto). Un
  usuario que no quiera passkeys elige el sistema de passphrase → es equivalente, no un parche de test.
- **Passkeys + modal = NATIVOS del frontend**, no un widget variable. La lógica WebAuthn `prf` y el modal de
  passphrase viven en `frontend/app/` y en el **motor de memoria** (server), nunca en `widgets/`.
- **Dominio nuevo `seguridad-datos`** (`tester/scenarios.py` + `zaelar-testing.md`): (1) «guárdame la contraseña de
  Netflix, es X» → verifica que se cifró (NO hay X en claro en la BD) + zaelar no la repite en voz; (2) «dame la
  contraseña de Netflix» con bóveda bloqueada → zaelar **pide la passphrase** (el tester la provee vía la API); (3)
  desbloqueo → zaelar **sirve** el dato; (4) comprobación del JUEZ: el valor nunca apareció en un evento/log en
  claro. Cubre encriptar → pedir → desencriptar, como pediste.

## 14. Estado de construcción (bitácora)

- **2026-07-21 — F0 + API (rama `feat/v2-060-boveda-secretos-cifrados`, desde main):**
  - `memory/vault.py`: bóveda asimétrica (PyNaCl sealed box), sobre passphrase (Argon2id+SecretBox), storage
    partido, modos cómodo (clave en RAM, TTL) / estricto (transitorio), supersede por slot, rotación, `status()`
    redactado. Escribir NO pide desbloqueo (clave pública); leer sí.
  - `memory/secrets.py`: detección FAIL-CLOSED es/en (marcadores + estructurales Luhn/IBAN/EVM-key/API-key/seed) +
    `redact()` (el LLM ve «secreto guardado», nunca el valor).
  - `memory/schema.py`: v2→v3, tablas `vault_meta`/`vault_secrets` (idempotente).
  - `memory/vault_api.py` + montaje en `server/__init__.py`: `/api/vault/*` (loopback-only en lo sensible; `reveal`
    devuelve 423 si bloqueada → abre modal).
  - **Tests: 29 verdes** (unit vault 12 + secrets 13 + integración HTTP 4), sin red. Verificado que el valor no
    aparece en claro en `memories` ni en el ciphertext. `PyNaCl==1.6.2` en requirements.
- **2026-07-21 — F1a (auto-vaulting) + F1b (lectura):**
  - F1a: hook en `nucleo/memory_agent.ingest_utterance` — el gate de secretos corre LO PRIMERO; cifra+redacta
    off-loop antes del destilador; sin bóveda → `secret_needs_vault`. +3 tests.
  - F1b: `nucleo/flash/vault_flow.py` (resuelve etiqueta→secreto, desenlaces) + tool `reveal_secret` en el router +
    cableado en el provider `nucleo.py` Y el probe `probe.py` (impls PARALELAS). El valor se entrega OUT-OF-BAND:
    NUNCA al modelo ni al observer/logs; el frontend/tester lo piden a `/api/vault/reveal`. Plantillas es/en en
    `langs`. +6 tests (vault_flow) + router. **207 verdes en total**, sin regresión.
  - **Testing:** dominio `seguridad_datos` en `tester/scenarios.py` + prioridad nº8 y Paso-0 en `zaelar-testing.md`
    (passphrase = camino del tester; FAIL DURO si un valor aparece en claro).
- **2026-07-21 — F2 (reglas duras + lectura por voz) + F3 (frontend + passkeys):**
  - F2: `memory/state.py` gana `state.security` (2ª clase de user rules, DURA, aplicada en código, fuera del cap de
    estilo) + `security_flag`/`set_security_flag`. `nucleo/flash/vault_rules.py` detecta comandos de config es/en
    («no me digas los secretos por voz» / «modo máxima seguridad» / «léemelos por voz») → persiste + confirma.
    Cableado en provider Y probe (short-circuit sin modelo). ENFORCEMENT en el reveal: modo cómodo (default, el
    operador lo pidió) DICE el valor por voz; `secrets_voice=False` → solo pantalla. +13 tests.
  - F3: server passkeys (WebAuthn PRF, cripto server-side = modo cómodo) — `add_passkey/unlock_with_prf/
    remove_passkey/passkey_meta` (salt del PRF derivado de la pública, sin schema nuevo) + `/api/vault/passkey/*`.
    Frontend NATIVO: `services/vault.js` (REST + WebAuthn `prf` enroll/unlock), `components/VaultModal.js` (crear/
    desbloquear por passphrase O huella / mostrar valor / gestionar), `sse.js` (eventos `secret`→abre el modal),
    `store.js` señales, `main.js` monta + `window.zaelar.vault()`, `styles.css` `.vault-*`. +4 tests (server+HTTP).
  - **Verificación global: 764 pytest verdes** (1 fallo AJENO — fuga de `DEEPGRAM_API_KEY` entre tests de
    `config/test_credentials.py`, pasa aislado; no toca V2-060). node --check OK en el JS nuevo.
  - **Pendiente (documentado):** modo ESTRICTO zero-knowledge = descifrar en el NAVEGADOR (vendorizar
    libsodium-wrappers WASM; hoy el descifrado es server-side, el modo cómodo elegido por el operador) → F4/cloud
    junto con recuperación + backups de ciphertext + zero-knowledge cloud. Diagrama `/architecture`: al MERGE
    (el diagrama es espejo del sistema VIVO en `main`; esta rama aún no está mergeada).
