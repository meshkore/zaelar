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

El Observatory permanece en `http://127.0.0.1:8765`. El runner levanta otro engine headless en un puerto efímero,
con `ZAELAR_WORKSPACE` y `ZAELAR_DB` temporales. Los 26 pasos comparten ese estado aislado durante el run; nunca
leen ni escriben la memoria del operador. Al terminar, el proceso y el workspace temporal se destruyen.

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

## Extender

Añadir el caso en el punto temporal correcto, declarar productos reales y expectativas observables. No usar sleeps
arbitrarios: si una escritura es asíncrona, crear una barrera que consulte el efecto. No marcar como producido un
estado que no se haya verificado. Validar `--validate`, el caso (que reconstruirá su prefijo), la suite completa y
`tests/platform/tests`.
