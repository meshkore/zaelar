# Catálogo del test bot de memoria (registro de requests + expectativas)

> Generado desde `cases4.py` (`python -m tests.memory.e2e.bot.runner --corpus v4 --catalog`). NO editar a mano.
> Cada **save/extract** dice qué dice el operador y qué debe extraerse, descartarse o actualizarse. Cada **query**
> simula una pregunta como la haría el FlashBrain y qué datos debe devolver la lectura DIRECTA (sin LLM):
> ESTADO + perfil durable + CORTO (cacheado) y, si el gate `needs_recall` dispara, el recall del LARGO.

**Total de casos definidos:** 15 (objetivo 1000, en tandas de 10).

| # | tipo | el operador dice / pregunta | esperamos | por qué |
|--:|:--|:--|:--|:--|
| 0 | extract | 🗣️ Hola, ¿qué tal? Bueno, nada, aquí estamos. | **DESCARTE**: cero píldoras | saludo y muletillas: cero píldoras, cero basura durable |
| 1 | extract | 🗣️ Pues mira, estaba en el trabajo y tuvimos que apagar un incendio bastante feo. Soy bombero. Me gustaba mucho cuando vivía en Mallorca, pero ahora vivo en Madrid y espero quedarme aquí un par de años. Luego quizá me vaya a Barcelona o Menorca, o vuelva a Mallorca; todavía no lo sé. | ≥3 píldoras; extraer `Mallorca`, `incendio`; estado `location=Madrid`, `job=bombero` | un solo turno contiene trabajo, evento, residencia histórica, residencia vigente e intenciones inciertas |
| 2 | extract | 🗣️ Lo del incendio me dejó pensando. Cada vez me interesa más estudiar arquitectura, sobre todo cómo se diseñan edificios seguros; no es una tarea para hoy, es algo que quiero aprender en serio. | ≥1 píldoras; extraer `arquitectura` | interés latente y objetivo durable extraídos de una reflexión, no de un formulario |
| 3 | extract | 🗣️ Esta mañana me tomé un café al salir de guardia y ahora estoy bastante cansado, pero mañana seguro que ya estoy bien. | ≤2 píldoras; extraer alguno de `café`, `cansado` | actividad y estado del día: puede recordarse brevemente, nunca convertirse en identidad durable |
| 4 | extract | 🗣️ Por cierto, cuando cenamos fuera hay que acordarse de que soy alérgico a la penicilina. No venía mucho a cuento, pero prefiero que no se pierda ese dato. | ≥1 píldoras; extraer `penicilina`; pinned `penicilina` | dato médico crítico enterrado dentro de charla lateral |
| 5 | extract | 🗣️ Oye, ¿qué tiempo va a hacer mañana en Bilbao? Si llueve ya veremos qué hacemos. | **DESCARTE**: cero píldoras | pregunta al asistente: no inventar una preferencia ni memorizar la meteorología solicitada |
| 6 | extract | 🗣️ Antes te he dicho Madrid por inercia, pero no: me mudé a Valencia hace unas semanas. Madrid fue la ciudad anterior; ahora vivo en Valencia. | ≥1 píldoras; estado `location=Valencia`; slots `operator.location=Valencia` | corrección natural: el slot vigente cambia y el dato previo queda histórico |
| 7 | extract | 🗣️ Y otra precisión: cuando digo que soy bombero simplifico demasiado. Dejé ese puesto; ahora trabajo como coordinador de emergencias. | ≥1 píldoras; estado `job=coordinador`; slots `operator.job=coordinador` | cambio profesional expresado como rectificación conversacional |
| 8 | extract | 🗣️ Mi hermana Laura me llamó mientras trabajaba: la operación de mi padre será el jueves y me pidió que la acompañe al hospital. | ≥1 píldoras; extraer `jueves`, `hospital` | tercero, parentesco, evento médico y compromiso futuro en una sola frase |
| 9 | extract | 🗣️ No sé si te lo había contado: de pequeño pasaba los veranos en Segovia con mis abuelos. Recuerdo especialmente el olor de la panadería de la plaza. | ≥1 píldoras; extraer `Segovia` | recuerdo autobiográfico narrado con detalle sensorial |
| 10 | extract | 🗣️ Vale, gracias, cierra eso y no me muestres nada más ahora. | **DESCARTE**: cero píldoras | orden efímera de UI: se ejecuta en el turno, no contamina la memoria |
| 11 | query | ❓ ¿Dónde vivo ahora? | devolver: `Valencia` (fuente esperada: ESTADO (siempre en prompt)) | el valor vigente responde y la ubicación superseded no se filtra como actual |
| 12 | query | ❓ ¿En qué trabajo actualmente? | devolver: `coordinador`, `emergencias` (fuente esperada: ESTADO (siempre en prompt)) | la ocupación corregida manda sobre la simplificación inicial |
| 13 | query | ❓ ¿Qué asunto familiar importante tengo el jueves? | devolver: `hospital`, `jueves` (fuente esperada: LARGO (durable)) | recuperación diferida de compromiso extraído de diálogo complejo |
| 14 | query | ❓ ¿Qué quiero aprender en serio? | devolver: `arquitectura` (fuente esperada: LARGO (durable)) | recuperación de un interés inferido, no declarado como campo |
