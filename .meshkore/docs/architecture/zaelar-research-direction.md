---
title: Zaelar — Cómo se DIRIGE una investigación (brief, embudo, propuestas compuestas)
category: architecture
updated: 2026-08-09
owner: ricart
status: current
---

# Dirigir una investigación

> Doc NARRATIVA. Complementa `zaelar-architecture.md` (qué pieza es cada cosa) respondiendo a otra pregunta: **si
> el operador pide «las mejores vacaciones» y espera algo que un profesional firmaría, qué tiene que pasar entre
> su frase y la pantalla, en qué orden, y por qué en ese orden.**

## 0. El fallo que motiva todo esto

Petición real del operador (2026-08-09), resumida en su propia frase:

> «Entrar en una web, poner los filtros, darle al botón y dar los tres primeros resultados lo hace cualquiera.»

Eso era, literalmente, lo que hacía el sistema. Y no por falta de herramientas: el Brain Worker ya sabía conducir
un Chromium real, leer, extraer, y verificar. Lo que **nadie le decía** era cuán ancho buscar ni con qué baremo
juzgar — recibía prosa libre y se autoimponía el criterio mínimo que satisfacía la frase literal. Encima, el
prompt del worker web llevaba escrito el atajo culpable: *«concluye con los 2-3 que mejor encajan»* — correcto
para «tráeme el precio de X», ruinoso para «elige lo mejor».

Había un segundo fallo, del lado de la entrega: una propuesta de viaje **no es una lista de hoteles**. Es un
paquete (este hotel + ese ferry + tal restaurante) que se compara y se elige como un todo. La superficie de
resultados era plana —1 tarjeta = 1 cosa— así que un paquete solo cabía disuelto en prosa, que es justo lo que
impide compararlo.

## 1. Las tres piezas

| Pieza | Fichero | Qué resuelve |
|---|---|---|
| **Director de investigación** | `nucleo/research.py` | Convierte la petición cruda en un BRIEF: qué descalifica, qué puntúa, qué añade un experto, cuán ancho buscar, cómo se juzga la calidad, qué forma tiene la entrega. |
| **Propuestas compuestas + 2ª página** | `widgets/results/` | Un resultado puede estar hecho de PIEZAS (`parts`), llevar datos duros consultables (`facts`) y fotos reales (`images`); y la hoja tiene una vista de DETALLE de un item. |
| **El cerebro ve la pantalla** | `widgets/refs.py::prompt_digest` | Hook genérico: un widget publica un resumen de su contenido y el FlashBrain lo lleva en el prompt → puede RESPONDER sobre lo que hay en pantalla, no solo nombrarlo. |

## 2. El orden, y por qué

```
frase del operador
      │
      ▼
FlashBrain (nucleo/flash/) ── responde YA («recibido, empiezo a buscar») ── milisegundos, ruta de VOZ
      │  escalate_to_slowbrain(request)
      ▼
PRE-VUELO ASÍNCRONO  ← aquí, y solo aquí, se puede PENSAR
  nucleo/dispatch.py::_compose_brief
      │  · ¿es una investigación? (lo decide el modelo, no una tabla de verbos)
      │  · ¿había una ronda anterior con este objetivo? → expand() en vez de recomponer
      ▼
  nucleo/research.py::compose  → BRIEF estructurado (techo 30s, fail-open)
      │  research.save(task_id)  +  research.remember_round(goal_key)
      ▼
prompt del worker = petición literal + BRIEF (to_prompt_block)
      │
      ▼
Brain Worker (Claude Code + Chromium real)
      │  embudo: reunir ≥N → filtrar duros → puntuar blandos → VERIFICAR finalistas
      │  hbnote plan/progress/phase   → el operador ve avanzar
      │  hbnote considered N --kept M → la selección queda AUDITABLE
      │  widget_cli data results append → la hoja se llena EN VIVO, propuesta a propuesta
      ▼
widgets/results  ── lista comparable ──▶ (voz: «detalle de la 1») ──▶ expediente completo
      │
      ▼
refs.prompt_digest → el FlashBrain sabe qué hay en pantalla → responde «¿tiene wifi?» sin re-buscar
```

**Por qué el brief se compone en el PRE-VUELO y no en el turno de voz.** Separar criterios duros de blandos,
deducir lo que hará falta y no se pidió, fijar la amplitud y el baremo es trabajo de razonamiento. El FlashBrain
de voz tiene que contestar en milisegundos: ahí no cabe. La escalada, en cambio, ya es asíncrona y el operador
sabe que tarda — es el único punto del sistema donde se puede pensar antes de empezar a trabajar.

**Por qué el brief va DESPUÉS de la petición literal en el prompt.** Es la dirección de *cómo* hacerlo bien, y se
lee mejor sabiendo ya *qué* se pide. Sin brief (una acción concreta: cancelar una cita) el bloque no aparece y el
worker sale exactamente como salía antes.

## 3. El embudo, que es la pieza que de verdad cambia el resultado

```
1) REÚNE   ≥ min_candidates candidatos reales — ANTES de descartar ninguno
2) FILTRA  por los criterios DUROS (incumplir = fuera, sin excepción)
3) PUNTÚA  los supervivientes con los BLANDOS + los enriquecimientos
4) VERIFICA A FONDO solo a los finalistas, contra el BAREMO ← aquí se gasta el esfuerzo
5) ENTREGA las n_final mejores, con sus datos verificados
```

`min_candidates` tiene un **suelo de 25** en código (`_MIN_CANDIDATES_FLOOR`). Existe porque el sesgo del modelo,
si le dejas el número, es pedir «10 candidatos» — la búsqueda superficial con otro nombre. Elegir «el mejor» entre
8 no es elegir, es conformarse. En la primera corrida real el modelo pidió 50 por su cuenta; el suelo está para
cuando no lo haga.

Los **ángulos** importan tanto como el número: por un solo camino (un agregador) siempre ves el mismo subconjunto,
así que 40 candidatos de una sola fuente son 40 candidatos falsos.

## 4. Qué es «genérico» aquí y por qué no es un buscador de hoteles

Nada en `research.py` sabe de hoteles, ferries ni precios. El compositor pregunta: *¿qué añadiría un experto de
ESTE dominio, cuán ancho hay que buscar, cómo se juzga la calidad?* — y esa pregunta tiene la misma forma para una
tesis de física cuántica (¿cuántos papers antes de concluir? ¿qué hace sólida a una fuente?), para documentarse
para escribir un libro, o para elegir una librería. El **dominio lo nombra el propio brief**; la ESTRUCTURA de
dirigir una investigación es la misma. Un test lo guarda: si el prompt del sistema se especializa en un dominio, o
si aparece el vocabulario del caso que motivó la pieza, falla.

Lo mismo del lado de la pantalla: `parts` son ROLES («Alojamiento», «Transporte», «Fuente», «Capítulo»,
«Servidor»), no campos de un viaje.

## 5. Rondas: «esos no me valen, sigue buscando»

La segunda frase del operador **nunca menciona la primera**. Por eso la continuidad se casa por FIRMA DEL OBJETIVO
(solape de palabras de contenido ≥0,5, el mismo umbral que la reanudación web), no por texto exacto ni por id de
tarea:

- `remember_round(goal_key, brief)` al lanzar → registro acotado (40 vivos, TTL 6h).
- `previous_round(goal_key)` al llegar una petición nueva → si casa, `expand()`: **ronda+1, amplitud doblada,
  criterios intactos** y el motivo del rechazo dentro del brief.

Reabrir los criterios sería empezar OTRA búsqueda; doblar la amplitud es continuar ESTA. Sin esto, «busca más» se
recomponía desde cero con la misma amplitud y devolvía lo que el operador acababa de rechazar.

**Decisión deliberada:** pedir dos veces lo mismo dentro del TTL se trata como continuación, no como búsqueda
nueva. Pedirlo dos veces significa que la primera respuesta no sirvió.

## 6. Auditabilidad: `considered`

`hbnote considered <N> --kept <M>` → `dispatch.session_considered` → `SessionRecord.considered/kept` →
`active_sessions()` / `pending_summaries()` → prompt del FlashBrain y `/api/tasks`.

Sin este dato, «te traigo las 3 mejores» es **indistinguible** de «te copio las 3 primeras», y ni el operador ni
el cerebro pueden juzgar si conviene seguir. `-1` significa NO APLICA (una tarea que no es una investigación no ha
«considerado 0 candidatos»).

## 7. Lo que NO hace, a propósito

- **No compromete nada.** El worker tiene prohibido reservar, comprar, pagar, contratar o enviar en nombre del
  operador, aunque encuentre la opción perfecta. Nació de un defecto real: el primer brief convirtió «busca» en
  «encontrar y RESERVAR» — dinero irreversible por una palabra que nadie dijo. Doble red: el director no puede
  añadir acciones no pedidas, y el bloque que lee el worker se lo repite. (Tercera red preexistente: el
  confirm-gate de irreversibles en `nucleo/danger.py`.)
- **No bloquea por un dato menor.** Si falta algo para poder buscar, se ASUME con el valor razonable y se anota en
  `assumed` — y el worker debe mencionarlo al entregar. Inventar un dato que falta está bien; ocultar que lo has
  inventado, no.
- **No presume de lo que no verificó.** Una propuesta con un dato sin confirmar y AVISADO vale; una con un dato
  inventado, no.

## 8. Kill-switch y fail-open

`§research.enabled` (UI) + `ZAELAR_RESEARCH=0` (env), mismo patrón que el Susurro. Y fail-open **en todos los
caminos**: sin proveedor, con error, o vencido el techo de 30s, el worker sale SIN brief — como salía antes — pero
**con aviso en el log**. Un fail-open silencioso aquí esconderría que TODAS las búsquedas volvieron a ser
superficiales, que es el fallo que esto viene a cerrar.

En la sesión de test el kill-switch va apagado (`conftest.py`): «busca un piso» es una investigación, así que el
despacho se ponía a llamar al modelo de verdad y colgaba un test que no tenía nada que ver.

## 9. Hallazgos de la verificación en vivo (por qué se prueba en vivo y no solo con tests)

Estos cuatro NO los habría encontrado ningún test de este repo; salieron de conducir la app real con Playwright:

1. **Los widgets se actualizaban en vivo solo si la voz estaba levantada.** `openSSE` se llamaba únicamente dentro
   del arranque de la sesión de voz, y `stop()` lo cerraba → sin micrófono, o con la voz parada a mano (⏻), una
   tarjeta abierta se quedaba **congelada en la foto de su primer render**, sin ningún síntoma. Justo lo contrario
   de «ver llenarse el informe en vivo». Ahora el canal lo abre `main.js` en el arranque y su vida es la de la
   aplicación. *Trampa asociada:* con el motor LiveKit se sirve `session-lk.js` EN la URL de `session.js` — editar
   `session.js` no cambia nada en ejecución (el test comprueba los dos ficheros).
2. **`_raise_with_body` se llamaba sin `await`** en `_complete_zai`: un 429 de Z.AI pasaba por bueno y reventaba
   más tarde como error de parseo, sin clasificar la cuota y por tanto sin relevo de proveedor.
3. **El objetivo derivaba a «reservar»** (ver §7).
4. **Los roles llegaban como frases descriptivas** en vez de etiquetas, y se pintan en una insignia. El prompt lo
   pide corto; ahora un cap lo garantiza, cortando por PALABRA (por caracteres daba «Tarifa de ferry para 4
   pasaj»).

## 10. Referencias

- `nucleo/research.py` — el director (compose/parse/expand/to_prompt_block/rondas).
- `nucleo/dispatch.py::_compose_brief`, `_build_prompt`, `_web_prompt`, `session_considered`.
- `widgets/results/{data,widget}.js|py` + `manifest.json` — esquema compuesto, `facts`/`images`, `detail`/`list`.
- `widgets/refs.py::prompt_digest` + `widgets/brief.py` — el hook genérico de «qué hay en pantalla».
- `config/v2.py §research` — modelo y kill-switch.
- Tests: `tests/agent_headless/unit/test_research.py`, `tests/agent_headless/unit/test_dispatch.py`,
  `tests/browser/unit/widgets/test_results_presentation.py`,
  `tests/browser/unit/widgets/test_live_updates_independent_of_voice.py`.

## 11. Estado de verificación (2026-08-10)

Honestidad sobre qué está probado y con qué:

| Eslabón | Cómo se verificó | Estado |
|---|---|---|
| El compositor produce un brief de calidad experta | Dos corridas REALES contra la petición literal del operador con el modelo de razonamiento (Z.AI glm-5.2 por la cadena) | ✅ verificado |
| El brief llega al prompt del worker (ruta genérica y ruta web) y suprime el atajo de cierre rápido | Tests deterministas | ✅ verificado |
| Amplitud, duros/blandos, baremo, rondas, `considered`, kill-switch, fail-open | 35 tests | ✅ verificado |
| El FlashBrain contesta al instante y escala | `POST /api/flash/say` con la petición real → «Vale, dame un momento que lo miro» + `tool_calls: escalate_to_slowbrain, show_widget` | ✅ verificado |
| La hoja pinta propuestas compuestas, el detalle por ordinal, y se vuelve a la lista | Playwright contra el server real, con capturas | ✅ verificado |
| El canal de eventos actualiza la pantalla sin voz | Playwright (era un bug; ver §9.1) | ✅ verificado |
| **Un Brain Worker REAL ejecutando el brief contra webs reales y llenando la hoja** | — | ⏳ **PENDIENTE** |

### Por qué el último eslabón quedó sin cerrar

Dos obstáculos de TESTABILIDAD (ninguno del mecanismo en sí):

1. **El chat de la UI no tiene transporte sin micrófono.** `submitChat` → `session.sendText` publica por el canal de
   datos de LiveKit; sin sala, el texto se encola en `_pendingText` y espera. Correcto para un navegador real (el
   operador tiene micro), inviable en headless.
2. **La escalada emitida desde `POST /api/flash/say` no llegó al dispatcher.** El bus es IN-PROCESS y
   `dispatch.start()` se monta en dos procesos (uvicorn y el worker del agente LiveKit) pero solo uno registra
   «listener de escalados arrancado». El turno de voz/chat nace en el proceso del agente —el mismo que tiene el
   listener— así que la ruta del operador no está afectada; la del probe headless, sí.
   *Comprobado:* `/api/tasks` vacío y sin entrada nueva en `/api/workers/history` tras una escalada confirmada por
   `tool_calls`.
3. Lanzar el worker desde un proceso APARTE tampoco vale: los puentes (`hbnote`, `widget_cli`) se autentican con un
   token por-tarea que vive en el registro del server, así que un worker fuera de ese proceso no puede reportar ni
   pintar.

### Cómo cerrarlo

Por voz o por chat en un navegador con micrófono (la prueba que el operador iba a hacer de todos modos): la petición
nace en el proceso del agente, que es donde está el listener. Hitos a mirar en la columna de observabilidad:
`task/plan` → `task/progress` → `widget/data` (la hoja llenándose) → `task/considered`.

Pendiente de añadir a `tests/`: un caso que ejercite la escalada COMPLETA sin depender del transporte del
navegador — el hueco de E2E que ya documenta `.meshkore/docs/ops/zaelar-testing.md`.
