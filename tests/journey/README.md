# Viaje integral cronológico

`journey` verifica que Zaelar conserva una sola historia causal al cruzar memoria, conversación, canvas, agenda,
Brain Workers, navegador, observabilidad, conectores y cluster. No sustituye las suites de dominio: las enlaza.

## Ejecutar

```bash
./.venv/bin/python -m tests run journey --no-open
# caso N: reconstruye desde J001 hasta N, nunca empieza con estado inventado
./.venv/bin/python -m tests run journey --case journey::whole-system-v1::0015 --no-open
# diagnóstico directo del runner
./.venv/bin/python -m tests.journey.runner --validate
./.venv/bin/python -m tests.journey.runner --all
```

El Observatory permanece en `http://127.0.0.1:8765`. El runner levanta otro engine mediante
**`tests/platform/sandbox_engine.py`** —el mismo helper que usa `use_cases`— en un puerto efímero y con
workspace, base de datos y **directorio de eventos** temporales. Los 29 pasos comparten ese estado aislado
durante el run; nunca leen ni escriben la memoria del operador. Al terminar, el proceso y el workspace se
destruyen, y el helper borra además el código de los widgets que ese motor haya generado.

> **Por qué no levanta el suyo (2026-08-20).** Lo levantaba: su propio puerto libre, su propio tempdir, su
> propia lista de variables. Y a esa copia le faltaba `ZAELAR_LOG_DIR` — que `voice/observer.py` resuelve
> desde la RAÍZ del repo, no desde el workspace —, así que **cada corrida de `journey` escribía sus eventos
> en el `.meshkore/logs/timeline-latest.jsonl` real del operador**: el incidente del 2026-07-25 (eventos de
> test leídos como sesión viva). El helper salió de ESTE fichero y llevaba meses con una nota escrita sobre
> esta fuga exacta. Dos aislamientos mantenidos por separado, y el agujero estaba en el que nadie releía.
> Levantar el motor no es lo que hace que `journey` sea `journey` —eso es el plan causal—, así que el
> arranque es compartido y la fuga se cierra para todo el que lo use.
>
> El único ajuste propio que queda es `BROWSER_SEARCH=1` (hay pasos que buscan de verdad). `ZAELAR_ENGINE`
> era aquí `headless` y en el helper es `off`: **es la misma rama** — `server/__init__.py` solo bifurca en
> `== "livekit"` —, así que no se añade una tercera forma de escribir lo mismo.

## Modelo de cada caso

La fuente es `journey.json`. Cada caso declara `phase`, `channel`, `op`, `input`, `expected`, `consumes` y
`produces`. El runner rechaza un plan que consuma un producto antes de producirlo. Una ejecución individual
reproduce todo su prefijo causal. Los eventos del Observatory incluyen entrada, expectativa, ruta, prerequisitos,
salida completa, productos y duración.

La historia actual hace, por orden: arranque aislado; catálogo de widgets; estado del bridge MeshKore; extracción
natural de identidad/objetivo; pérdida de ventana y recall durable; tiempo por ubicación implícita; resolución de
«muéstramelo» y canvas; modificación contextual; cita natural y mutación real de Agenda; pregunta elíptica;
búsqueda Wallapop de una única moto enduro con restricciones; proceso visible y refinado sin duplicarlo; traza;
conectores; turno de peer con protección de identidad; corrección Valencia→Castellón; nuevo reset; recall cruzado;
y checkpoint final de memoria, canvas, agenda, worker y observabilidad.

## Qué demuestra y qué no

Demuestra el comportamiento compartido del engine real por HTTP/headless, el registro vivo de workers, contratos
de widgets, control plane MeshKore y el motor de diálogo de cluster. Ejecuta búsquedas/workers reales cuando el
caso lo declara.

No afirma haber probado el micrófono, audio WebRTC, VAD, STT/TTS, una sesión LiveKit completa, render píxel a píxel
ni un peer remoto atravesando un WebSocket físico. Esas fronteras siguen perteneciendo a `voice`, `browser`,
`infrastructure` y `cluster --live`. La razón es deliberada: no deben compartir ni contaminar la identidad real del
operador. Para un release, ejecutar el viaje y después las fronteras vivas afectadas.

## `journey` frente a `use_cases` — se parecen y no hacen lo mismo

Las dos son las únicas suites que ejercitan un motor real completo, así que la confusión es razonable. La
diferencia está en la PREGUNTA:

| | `journey` | `use_cases` |
|---|---|---|
| pregunta | ¿el estado **sobrevive y se encadena** bien? | ¿una persona real **obtiene lo que pidió**? |
| historia | UNA, causal: 29 pasos, `consumes`/`produces` validados; el paso 15 reconstruye del 1 al 14 | una conversación INDEPENDIENTE por caso |
| entrada | llamadas HTTP declaradas | un modelo hace de persona que pide mal las cosas y se adapta |
| veredicto | `expected` **duro** (`widget_ids`, `equals`) → rojo o verde | un juez puntúa 5 ejes contra el mecanismo real |
| coste | segundos por paso: se corre en cada cambio | 3-6 min y varias llamadas a modelo POR CASO |

Por eso no se fusionan, y no es una cuestión de gusto:

- **Fusionar mataría el trinquete.** Si el catálogo de widgets pierde `agenda`, `journey` se pone rojo
  siempre, sin que opine nadie. Una suite de regresión cuyo rojo depende de un modelo no es una suite de
  regresión — y hay evidencia medida de que el evaluador se equivoca (el 2026-08-20 el juez de `use_cases`
  se contradijo con su propio informe de mecanismo, escribió parte de un hallazgo en chino, y puntuó como
  defecto del producto una contaminación del arnés).
- **Los requisitos de estado son OPUESTOS.** `journey` NECESITA estado acumulado. `use_cases` necesita su
  ausencia: la memoria compartida entre casos de una tanda es un contaminante conocido del que hay que
  avisar al juez explícitamente.
- **Y el coste.** Fusionarlas haría que la regresión barata costara como la aceptación, y entonces dejaría
  de correrse en cada cambio, que es justo donde vale.

Lo que sí es compartido, y desde el 2026-08-20 de verdad, es la FONTANERÍA: un solo `sandbox_engine`.

## Extender

Añadir el caso en el punto temporal correcto, declarar productos reales y expectativas observables. No usar sleeps
arbitrarios: si una escritura es asíncrona, crear una barrera que consulte el efecto. No marcar como producido un
estado que no se haya verificado. Validar `--validate`, el caso (que reconstruirá su prefijo), la suite completa y
`tests/platform/tests`.
