# V2-061 — Acciones ENCADENADAS realidad ↔ widgets ↔ memoria + inteligencia ASERTIVA de dos velocidades

**Estado:** CONSTRUIDA (3 capas, 2026-07-21) — detonada por un fallo en vivo el mismo día. Verificado e2e por probe.
**Ancla:** EPIC-v2-colmena. Hermana de V2-057 (verificación/certeza) y V2-053 (Susurro).

## ✅ CONSTRUIDO (2026-07-21, en `main`)

- **Capa 1 (cc74e56 + af803d4):** guard del pronombre suelto (`router.looks_like_bare_ref` + provider + probe) +
  **calidad de prompt** — la descripción de `escalate` ya NO dice «cancelar una cita de la agenda es widget_data»;
  distingue gestionar la LISTA local (widget_data) de EJECUTAR/DESHACER un COMPROMISO real (escala; el widget es
  espejo) + línea de CONTINUIDAD en `flash/prompt.py`. **VERIFICADO:** «hay que cancelarlo» y «cancela la cita de la
  ITV» → `escalate` (antes: widget_data «Hecho» falso); reloj→show, tiempo→chat, charla→chat sin regresión.
- **Capa 2 (c4df08d):** **Susurro que DEDUCE y ACTÚA (F2)** — `friction.risky_decision` (gate barato: acción de
  widget sin escalar = turno de riesgo → audita ANTES de la queja) + `worker_action` en el catálogo (re-ruteo:
  dispara el worker correcto vía `escalate`, dedup vs sesiones vivas, before/after) + prompt del auditor con el
  fallo real-world-como-tweak-local. Invariante intacto (nunca toca BRAIN RULES). +5 tests.
- **Capa 3 (8346db1):** puente genérico **`hbwidget`** (`nucleo/widget_cli.py` + `worker_api` acción `widget_data`
  con gate del catálogo canónico + provenance worker) + `_METHOD_BLOCK` ampliado (entender-plano → localizar-memoria
  → ejecutar-real → REFLEJAR en widgets/memoria → verificar todos los planos → iterar).
- **Testing:** escenario `accion_real_encadenada` (`tests/voice/e2e/agent/scenarios.py`, canal chat). 286 pytest verdes.

Pendiente (fase futura, no bloqueante): user_rule/state_patch/memory_fix como acciones de Susurro (hoy → finding);
verificación en vivo por voz del ciclo completo con una cita real cancelable.

## El detonante (caso ITV, chat, voz OFF, 2026-07-21)

Conversación real (trace `T291`/`T292`, `timeline-latest.jsonl`):

```
operador: «¿qué día tengo la ITV?»
zaelar:   «Tienes la ITV programada para el jueves 23 de julio de 2026.»   ✅ (dato correcto, de memoria)
operador: «hay que cancelarlo»
zaelar:   «¿Cuál exactamente? Tengo Revisar obligaciones de empresa, Estabilizar el daemon…»   ❌
```

El contexto SÍ estaba (la ventana tenía los 3 turnos, la ITV incluida). El fallo NO es de contexto: gpt-4o-mini
enganchó el verbo «cancelar» con la data-op `drop` del widget de **agenda** (cerrado y NO nombrado), y como el
pronombre «lo» no casaba con ningún item, listó items AJENOS de la agenda.

## Qué DEBIÓ pasar — el circuito lógico (visión del operador)

Cancelar la ITV es una **acción del MUNDO REAL encadenada**, no un tweak de agenda. La agenda es solo un ESPEJO de la
realidad; el reflejo local no es lo importante. El circuito correcto (un **rail**):

1. **ENTENDER** — «cancela la ITV» = cancelar una cita/reserva real.
2. **LOCALIZAR** en memoria cómo/dónde la reservamos (la web de la ITV, ya guardado hace tiempo).
3. **EJECUTAR de verdad** — ir a la web de la ITV, cancelar la cita real.
4. **REFLEJAR** — borrar el appointment de la agenda (el espejo local).
5. **CONFIRMAR + VERIFICAR** — comprobar que reality + agenda + memoria quedaron coherentes.

Esto probablemente exige un **brain worker** (web + memoria + widget + verificación en el tiempo). El FlashBrain solo
tenía que **detectar el path correcto y dispararlo con el contexto adecuado**.

## El patrón GENERAL (por qué es «muy muy muy importante»)

No es un caso aislado. Muchísimas órdenes necesitan su **reflejo en tres planos que hay que mantener coherentes y
verificar en el tiempo**:

| Plano | Ejemplo (ITV) | Ejemplo (suscripción) | Ejemplo (pedido) |
|---|---|---|---|
| **Realidad** (web/API externa) | cancelar cita en itevelesa | dar de baja Netflix en su web | cancelar pedido en Amazon |
| **Datos locales** (widget) | borrar appointment de agenda | quitar tarjeta de gasto recurrente | actualizar widget de pedidos |
| **Memoria** | actualizar el hecho «ITV reservada» | olvidar credencial/estado | registrar la cancelación |

Son **acciones encadenadas** (una depende de la anterior) y la MÁS importante casi nunca es el widget local.

## El diagnóstico REAL — capacidad del modelo (medido)

Probe (`/api/flash/say`, gpt-4o-mini, estado real con la ITV en memoria):

| Turno | Acción del mini | Correcto sería |
|---|---|---|
| «¿qué día tengo la ITV?» | `canvas:close:agenda` («cerrando todo…») ❌ | responder el dato (chat) |
| «hay que cancelarlo» | `widget_data` → **«Hecho.»** ❌ | escalar (acción real) |
| «cancela la cita de la ITV» (explícito, SIN pronombre) | `widget_data` → **«Hecho.»** ❌ | escalar (acción real) |

**Conclusión:** el mini NO entiende la clase «acción del mundo real encadenada». Mapea «cancelar»→`drop` de agenda y
dice «Hecho» sin hacer NADA real — **falsa confirmación** (viola además la doctrina de verificación de V2-057). Falla
igual con la orden EXPLÍCITA → no es solo resolución de pronombre, es techo de capacidad + prompting.

## La tensión central: VELOCIDAD vs INTELIGENCIA/ASERTIVIDAD

Por chat/voz el turno rápido (mini) es veloz y eficiente, pero **sin la inteligencia/asertividad necesarias**. Un
razonador en el camino caliente mataría la latencia (regla dura: FlashBrain NO-razonador). La resolución tiene que ser
una **inteligencia de DOS VELOCIDADES**: el turno rápido responde ya; una capa MÁS LISTA, FUERA del camino caliente,
detecta el mis-ruteo y **dispara la acción/worker correctos** sin frenar el turno. El operador señaló **«Susurro»**
como esa capa («no le dimos tiempo a intervenir y darse cuenta de que la estábamos liando»).

## Lo ya hecho en este cierre (arreglo determinista LIMPIO, no chapuza)

Guard del PRONOMBRE SUELTO (provider `nucleo.py` + espejo probe + helper `router.looks_like_bare_ref`, tests verdes):
un item que es pronombre deíctico suelto/vacío («lo/eso/esto/it/that») sobre un widget **ni abierto ni nombrado** en
el turno = mis-ruteo por verbo → **escala el turno crudo** (el worker recibe la ventana reciente verbatim con la ITV),
en vez de operar/listar items de un widget cerrado. Es reconocimiento GRAMATICAL de pronombre, no una tabla de verbos.
**LÍMITE HONESTO:** NO cubre el caso EXPLÍCITO que sí casa un item real («cancela la cita de la ITV» con la agenda
teniendo ese appointment) → sigue haciendo `drop` local + «Hecho». Ese caso EXIGE la capa de inteligencia (abajo).

## Condiciones del operador (2026-07-21, marco de la solución)

- **Precio NO es límite** ahora; **latencia SÍ** debe ser buena.
- **Situaciones INFINITAS, CERO cableado** — nada de tablas de caso ni rails por-caso. El sistema debe ENTENDER
  cualquier tarea que el usuario esté haciendo y llevarlo al mejor camino. Sistemas flexibles y auto-dimensionables.
- **Más inteligencia mejor, pero NO un modelo lento en CADA turno** — tiene que haber CAPAS que DETECTEN la actividad.
- Le parece **obvio y simple**: en una charla de 3 líneas sobre la ITV, «cancélala» se refiere a esas 3 líneas. La
  continuidad conversacional es el default; la EXCEPCIÓN es una petición explícita y AJENA («abre el widget del
  tiempo»), y **eso el modelo simple SÍ debe distinguirlo**.
- Crítica concreta: **los widgets/rails interfieren en el texto, están demasiado ávidos** de interactuar → es un
  problema de **calidad de prompts y enrutadores**: darse cuenta de si el turno afecta a un widget o NO.
- Lanzar el brain worker correcto: «ahí no se puede ayudar» — hay que **deducir** el path en el momento, no cablearlo.

## Propuesta MEJORADA (elegida) — tres CAPAS de inteligencia crecientes, sin cableado

Principio: el sistema **DEDUCE por comprensión**, no reconoce patrones. La capa lenta NO corre en cada turno.

### Capa 1 — RÁPIDA (FlashBrain/mini): mejor DISCRIMINACIÓN, sin cablear
- Sesgo por defecto = **conversación + widgets ABIERTOS/nombrados**. NUNCA meter mano en un widget cerrado y no
  nombrado (empezado ya con el guard del pronombre suelto).
- **Continuidad conversacional como default**: charla corta → pronombre/orden breve se refiere a lo hablado; la
  EXCEPCIÓN es una petición explícita que NOMBRA un widget sin relación con la conversación.
- **Enseñar como CONCEPTO** (en la descripción de `escalate_to_slowbrain`, NO lista de verbos): una acción que cambia
  el MUNDO (reserva/cita/baja/pedido/pago) —no solo anotar/ver— se ESCALA para ejecutar y verificar; agenda/widgets
  son ESPEJOS, no la acción.
- **Bajar la ansiedad de widget** en el prompt (su crítica): menos incentivo a `widget_data`; ante DUDA, no adivina →
  defiere (escala o deja pasar a la capa lista).

### Capa 2 — LISTA async: «Susurro» que DEDUCE y ACTÚA (F2/F3) — modelo potente, OFF-hot-path
- Ya observa **TODOS** los turnos (`turn.completed`) con modelo potente fuera del camino de voz → latencia del turno
  intacta (la corrección llega un instante después: «darle tiempo a Susurro a intervenir»).
- Se AMPLÍA el disparo: además de la fricción explícita, se auto-audita el turno de **RIESGO/baja-confianza** (fast
  dijo «Hecho» sobre op destructiva en widget ausente; mis-ruteo; contradice la conversación). La detección es por
  **COMPRENSIÓN del modelo potente** (lee turno + decisión del fast + conversación + estado y juzga «¿fue el path
  correcto?»), **NO por reglas**.
- Si el path fue erróneo: (i) corrige al operador con naturalidad y (ii) **DISPARA el worker correcto con contexto
  completo**. Precio no es límite → usa el modelo potente sin reparo.
- Invariante intacto: **NUNCA modifica BRAIN RULES en runtime**; corrige la capa mutable + dispara acción con gates.

### Capa 3 — PROFUNDA: worker con MÉTODO general (NO rails por caso)
- El worker **deduce el plan de CUALQUIER tarea** y ejecuta el método V2-057: entender → localizar en memoria →
  ejecutar en la realidad → **reflejar en los widgets** → confirmar → **verificar en el tiempo**.
- Única infra «de soporte» y es GENÉRICA: **puente worker→widget `hbwidget`** (data-op sobre cualquier widget) — HOY
  NO EXISTE; lo pide también V2-058 F4 (curar la lista de música). Sin él, un worker no puede reflejar en la agenda.
- **NADA de «rail de ITV»**. El caso ITV es una instancia del método general.

### Por qué cumple sus condiciones
Precio libre → la capa lista usa el potente. Latencia → toda la inteligencia va async/off-hot-path; el turno rápido no
se toca. Infinitas situaciones sin cablear → la capa lista DEDUCE por comprensión y la profunda aplica un método
general; cero tablas de caso. Más inteligencia con capas que detectan → tres capas crecientes, la lenta solo cuando
hace falta.

## Plan de construcción (tras OK del operador)

1. **Capa 1** — reescritura de calidad del prompt del FlashBrain (`flash/prompt.py`) + descripciones de tools
   (`router.TOOLS`, concepto real-world→escalate) + medir con probe/domain_sea que baja la ansiedad de widget sin
   romper las 6 rutas. (Toca camino caliente → cuidado, medir latencia.)
2. **Capa 2** — Susurro F2/F3: ampliar el disparo a turnos de riesgo/baja-confianza (juicio del modelo potente) +
   catálogo de acción `dispatch_worker`/`repair_say` con gates + observabilidad total (payload/respuesta/antes-después).
3. **Capa 3** — puente genérico worker→widget `hbwidget` (data-op con confirm-gate, provenance, token por-tarea) +
   método V2-057 con reflejo-en-widgets explícito.
4. **Testing** — escenario `accion_real_encadenada` en `tests/voice/e2e/agent/scenarios.py` (cancelar cita / baja de suscripción /
   cancelar pedido): verificar realidad + widget + memoria COHERENTES, no solo el «Hecho».
