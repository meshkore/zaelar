# V2-082 — Nombres + alias de widgets, certeza 100% en el enrutamiento

> Estado: **PLAN, sin implementar** — pendiente de aprobación del operador.
> Autor: sesión 2026-08-01. Sucede a [[V2-081]] (mostrar≠construir) y [[V2-078]] (acotación open>recent).

## 0. Problema y objetivo

Hoy un widget se identifica por `id` (carpeta) + `title` + `keywords[]`, todo resuelto por
**matching léxico DIFUSO** (`widgets/runtime.py::identify`, difflib cutoff 0.84) que además puntúa por
**solape con `description`/`whenToUse`**. Está diseñado para acertar aunque el nombre sea aproximado.
Eso es la causa raíz de las confusiones entre widgets: uno puede ganar sin que se haya dicho su nombre.

El operador quiere lo contrario y con garantía dura:

- Cada widget tiene un **NOMBRE canónico** (se muestra como botón en el header) + una **lista de ALIAS**.
- **Si no dices el nombre o un alias, el widget NO se abre.** Certeza 100% — con solo ~10 widgets es
  inaceptable confundirlos.
- `chat` → siempre el chat principal (superficie de sistema). `mensajería / WhatsApp / Telegram / X /
  Twitter / correo` → el widget `mensajeria`. Sin ambigüedad.
- Botón de configuración (icono) en el header de TODOS los widgets → despliega los alias, **editables por
  el usuario por voz y por texto** ("añade el alias WhatsApp al widget de mensajería" lo interpreta el
  FlashBrain, sin regenerar código).
- Un **catálogo de estado** con todos los widgets y sus alias.
- Concepto **limpio y sin mezclar**: widget vs superficie de sistema vs tool vs acción/data-op vs embedding.

## 1. Modelo conceptual (fuente única, sin mezclar)

Se fija de forma explícita en código + doc para acabar con la confusión:

| Concepto | Qué es | Dónde vive (fuente de verdad) | ¿Tiene nombre+alias? |
|---|---|---|---|
| **Widget** | UI del canvas, full-stack | carpeta `widgets/<id>/` (manifest+widget.js+data.py) | **SÍ** (nuevo) |
| **Superficie de sistema** | Nativo intocable (mic/cam, orbe, chat, debug, config…) | `frontend/app/core/system-surfaces.js` (V2-080) + espejo backend | **SÍ** (nuevo) |
| **Tool** | Función OpenAI que invoca el FlashBrain | `nucleo/flash/router.py::TOOLS` | NO — no es identidad de usuario |
| **Acción / data-op** | Capacidad declarada de UN widget (lo más cercano a "skill") | `manifest.json["actions"]` + `data.py::apply_action` | NO — pertenece al widget |
| **Embedding** | Vector semántico | `memory/` exclusivamente | NO — los widgets NO tienen vector |

**"Skill" no existe** como concepto en el código y NO lo introducimos. La palabra funcional "skill" ≡ las
`actions` de un widget. Se documenta así en `CLAUDE.md` + `zaelar-architecture.md` para que no se vuelva a mezclar.

## 2. Modelo de datos: `name` + `aliases[]`

### 2.1 Widgets (manifest.json)

Se añade contrato de identidad canónica:

- **`name`** (string): nombre canónico humano = lo que se muestra en el botón del header y el primer
  término hablado. Default = `title` si falta.
- **`aliases`** (string[]): nombres alternativos hablados, **editables por el usuario**. Es la lista que
  aparece en el desplegable de config del header.

Migración de `keywords[]`: hoy `keywords[]` ya cumple de facto el rol de alias. En la primera carga de un
widget sin `aliases[]`, se **siembran** `aliases` desde `keywords` (dedup, normalizado). `aliases[]` pasa
a ser el ÚNICO campo de escritura e identidad; `keywords[]` queda deprecado (se sigue leyendo como semilla,
no se escribe). Así hay **una sola lista de identidad**, no dos.

### 2.2 Superficies de sistema (system-surfaces.js + espejo backend)

Cada entrada de `SYSTEM_SURFACES` gana `name` + `aliases[]`. Ejemplos:
- `chat`: name "Chat", aliases `["chat","muro","muro de texto","escribirte","háblame por texto"]`.
- `config`: name "Configuración", aliases `["config","ajustes","preferencias","settings"]`.
- `debug`: name "Debug", aliases `["debug","depuración","logs","trazas"]`.
- `orb`, `camera`, etc. igual.

**La fuente de verdad de los alias de sistema es el FRONT** (`system-surfaces.js`), hardcodeada y **NO
editable por el usuario**: el front es "el cuerpo", su genética viene programada; si el usuario quiere
referirse a esas piezas con otras k-words, da igual — son las que son. Como el resolver vive en backend
(`runtime`), se añade un **espejo backend** (`widgets/system_surfaces.py`) mantenido en sincronía por un
test que falla si divergen. Así el resolver unifica widgets de usuario + superficies de sistema en un solo
espacio de nombres; `chat` (sistema) y `mensajeria` (usuario) conviven → desambiguación garantizada.

### 2.3 Catálogo de estado (proyección, NO segunda fuente de verdad)

El operador quiere "ver el catálogo con todos los alias en el estado". Se hace como `rails.project()`:
un **read-model proyectado** `widgets/registry.py::registry()` que devuelve, para cada entrada:

```
{ "id", "name", "aliases": [...], "surface": "user" | "system" }
```

Se proyecta una versión compacta a `memory/state.py` bajo `state["widget_registry"]` (solo lectura/visibilidad,
regenerada, nunca editada a mano) y se expone por `GET /widgets/registry`. La **fuente de verdad sigue siendo
el manifest** (usuario) y `system-surfaces` (sistema); el estado es solo el espejo visible.

## 3. Motor de resolución: de "difuso tolerante" a "por nombre, con certeza"

### 3.0 La palabra "widget" (y el nombre de sistema) es un SELECTOR de espacio de nombres

Antes de puntuar, la propia frase acota el espacio de búsqueda — refuerzo clave de la certeza:

- Si la frase contiene **"widget"** (o sus sinónimos `_WIDGET_SYN`: panel/gadget/tablero/contador/…), el
  usuario se refiere a una **pieza construida por él** → se resuelve SOLO contra el espacio de **widgets de
  usuario**. "abre el widget de mensajería" → nunca puede caer en una superficie de sistema.
- Si la frase nombra un **objeto de sistema** ("el chat", "la lista del cron", "la lista de tareas",
  "config", "debug") → superficie de sistema. Para el operador, el sistema tiene sus piezas pero **no son
  widgets**.
- Si la frase **no dice "widget" ni nombra un objeto de sistema** ("abre los mensajes") → se resuelve por
  k-word/alias contra AMBOS espacios; el prompt acota con la lista de widgets para intentar el match con
  certeza; si no hay match claro → se pregunta (§3.4).

### 3.1 Jerarquía de resolución

`widgets/runtime.py::identify` se reescribe con esta jerarquía (para widgets + superficies de sistema):

1. **Match por NOMBRE/ALIAS (k-word)** — única señal de apertura. Se normaliza acento/caso. Se tolera
   erratas de voz con difflib **SOLO sobre los tokens de nombre/alias** (no sobre descripción). Frase de
   alias completa alineada a palabra = match fuerte. (Para el operador, k-word ≡ alias: son las palabras
   que responden para identificar la pieza.)
2. **La `description`/`whenToUse` deja de abrir nada.** Puede seguir usándose para el brief del prompt, pero
   NO como señal de match. Esto elimina la clase entera de "abrió por parecido temático".
3. **Desempate por contexto** (se conserva de V2-078): ante empate real de alias, prioridad
   **abiertos > recientes**; si sigue ambiguo → `ambiguous=True`.
4. **Sin match de nombre/alias → NO abre.** Devuelve `None`. El llamante trata "None" como conversación
   normal → el FlashBrain **pregunta con una frase natural y distinta** que venga a cuento ("perdona, no
   localizo ese widget, ¿cuál quieres?"), **nunca** auto-abre el "más parecido" ni usa una cadena enlatada.

Resultado: un show/open sucede **solo** cuando se pronuncia un nombre/alias registrado. Con ~10 widgets, la
colisión es imposible por diseño (ver §6, guard de unicidad de alias).

Se aplica en las DOS rutas (deben quedar en paridad): provider real `voice/engine/llm/providers/nucleo.py`
(`_identify`, handler `show_widget`) y canal de prueba `nucleo/flash/probe.py` (`_identify_ctx`, branch show).

## 4. Editar alias por voz y por texto (tool nueva, sin regenerar código)

Hoy cualquier cambio de manifest pasa por `generator.modify_widget` (reescribe el widget entero con un agente).
Eso es carísimo y arriesgado para "añade un alias". Se crea una vía determinista:

- **Tool nueva** en `router.TOOLS`: `manage_widget_alias(widget_id, alias, op="add"|"remove")` con descripción
  rica en sinónimos ("añade/quita/pon/borra un alias/nombre/apodo a/de un widget"). Gating situacional
  `has_widgets`. Se añade a `decide()` (nuevo kind `ALIAS`, prioridad media) + handlers en `nucleo.py` y
  `probe.py`.
- **Escritura quirúrgica del manifest**: `widgets/aliases.py::add/remove` reescribe SOLO `manifest["aliases"]`
  atómicamente (tmp+rename), valida colisión (§6), llama `runtime.invalidate()` y emite SSE
  `kind:"widget", action:"alias"` para que el frontend refresque.
- El resolver del propio FlashBrain interpreta la orden: "añade el alias WhatsApp al widget de mensajería"
  → `manage_widget_alias("mensajeria","WhatsApp","add")`. Funciona igual por voz o por texto (misma tool).
- **Endpoints REST** para la edición desde el header (texto/click): `POST /widgets/{id}/aliases`,
  `DELETE /widgets/{id}/aliases/{alias}`. Mismo `widgets/aliases.py` por debajo.

Las superficies de sistema: sus alias son **fijos** (definidos en `system-surfaces.js`); el desplegable de
config los muestra en modo lectura (no editables), porque son parte del contrato nativo intocable (V2-080).
(Decisión abierta D2 abajo.)

## 5. Frontend: header con nombre + desplegable de alias

Hoy el "chrome" de cada widget lo dibuja el wrapper común `frontend/app/widgets/desktop.js:158-173` (grip +
× flotando sobre una franja de 30px, sin header ni título). Se añade un **header real** en ese único sitio
(no se toca ningún `widget.js` individual):

- **Botón-nombre**: muestra `_meta[id].name || title`. Es el nombre por el que se reconoce el widget.
- **Icono config (▾/⚙)**: abre un overlay host-level (patrón `.hb-confirm` ya existente en `desktop.js:315-344`)
  que lista los alias con:
  - añadir alias (input de texto → `POST /widgets/{id}/aliases`),
  - quitar alias (× por chip → `DELETE …`),
  - para superficies de sistema: solo lectura.
- CSS nuevo en `desktop.js::injectStyles()` (donde vive todo el chrome). El drag del grip debe ignorar clicks
  en los botones nuevos (igual que el ChatWall ignora `.cw-x`/`.cw-tab`).
- **Reactividad**: se añade señal de store `widgetRegistry` (poblada de `GET /widgets/registry`) para que el
  nombre/alias del header reflejen en vivo los cambios por voz; el SSE `action:"alias"` refresca la señal.

## 6. Unicidad e integridad (el guard que da la certeza)

- **Colisión de alias entre widgets = rechazo.** Se generaliza `generator.py::_keyword_collisions` a un
  validador compartido `widgets/aliases.py::check_collision(id, alias, registry)`: un alias no puede
  pertenecer a dos entradas (widget o superficie). Al añadir por voz/texto, si colisiona → no se añade y
  Zaelar lo dice ("ese nombre ya lo usa X").
- **Colisión con superficie de sistema** también se rechaza (no puedes aliasar un widget como "chat").
- El generador de widgets nuevos exige `name` + al menos 1 alias y valida colisión al crear (extiende
  `_validate`).

## 7. Migración de los widgets existentes

Script `widgets/migrate_aliases.py` (idempotente, corre una vez): para cada widget REAL (no el detritus de
tests) → set `name` = `title`, `aliases` = dedup(`keywords`), reporta colisiones para resolución manual.
Widgets reales a migrar: `agenda, clock, mensajeria, meteo-soria, meteo-tarragona-grafico, musica, navegador,
results, search, timer, temporizador-pomodoro-ayudar, youtube, futbol-champions, juego-serpiente-snake,
cluster-registro`. El detritus generado por tests (`ejecuta-*`, `realiza-*`, `cancela-*`, `reserva-*`,
`tarea-navegador`, `gestiona-*`, `personalizado-*`) NO se migra ni se commitea (limpieza previa).

Curación manual clave: `mensajeria.aliases` debe incluir `whatsapp, wasap, telegram, x, twitter, correo,
email, mail`; y garantizar que `chat` (sistema) NO comparte ninguno → caso de aceptación del operador.

## 8. Testing

- Unit `widgets/test_resolver_certainty.py`: (a) frase sin nombre/alias registrado → `None` (no hijack);
  (b) alias exacto → ese widget; (c) errata de voz sobre alias ("wasap") → mensajeria; (d) chat vs mensajeria
  desambiguados; (e) empate open>recent.
- Unit `widgets/test_aliases.py`: add/remove, colisión rechazada, colisión con sistema rechazada,
  invalidación de caché.
- `test_router.py`: nueva tool `manage_widget_alias` en el set esperado.
- Paridad provider/probe: escenario en `tester/scenarios.py` ("aliases") + "abre por nombre/alias".
- `make test-widgets` (golden) + los 201 existentes verdes.

## 9. Docs

`CLAUDE.md` (§frontend/§widgets) + `zaelar-architecture.md §8` (tools) + este doc: fijar el modelo de 5
conceptos, el contrato `name`+`aliases`, la regla dura "sin nombre/alias no se abre", y la tool nueva.

## 10. Fases de implementación (orden propuesto)

1. **Datos + registro**: contrato `name`/`aliases` en manifest, `widgets/system_surfaces.py` (espejo),
   `widgets/registry.py`, proyección a estado, migración de existentes. (Sin cambiar comportamiento aún.)
2. **Resolver con certeza**: reescribir `runtime.identify` (nombre/alias only, no descripción, None si nada).
   Cablear en nucleo.py + probe.py. Tests de certeza. ← el cambio de comportamiento gordo.
3. **Tool de alias por voz/texto**: `manage_widget_alias` + `widgets/aliases.py` + endpoints REST + SSE.
4. **Frontend**: header con nombre + desplegable de config editable + señal de store + reactividad SSE.
5. **Docs + release**.

## Decisiones (CONFIRMADAS por el operador 2026-08-01)

- **D1 — `keywords` ≡ `aliases`** ✅: unificar en una sola lista de identidad. Para el operador son lo mismo:
  k-words que responden para identificar la pieza. `keywords` se lee solo como semilla de migración.
- **D2 — alias de superficies de sistema FIJOS** ✅: hardcodeados en el front (`system-surfaces.js`), NO
  editables. El front es "el cuerpo", su genética viene programada; se muestran en solo-lectura.
- **D3 — cuando nada matchea, PREGUNTAR** ✅: el FlashBrain responde con una frase natural y distinta que
  venga a cuento ("no localizo ese widget, ¿me lo explicas mejor?"), nunca abre el más parecido ni usa una
  cadena enlatada. Base de la certeza 100%.
- **D4 — la palabra "widget" acota el espacio** ✅ (§3.0): "widget" → solo widgets de usuario; nombre de
  objeto de sistema → superficie de sistema; sin ninguna de las dos → k-word contra ambos + pregunta si no
  hay match claro.
