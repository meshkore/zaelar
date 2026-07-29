# V2-037 — Observabilidad de RENDIMIENTO (ver el sistema por dentro para cazar cortes/cargas)

**Origen (operador, 2026-07-13):** la voz aún se percibe entrecortada a partir de la 2ª-3ª frase; estamos ADIVINANDO
la causa. Hay que poder VER cada carga del sistema en la observabilidad, con filtros, para diagnosticar de verdad.

## Diagnóstico hasta ahora (medido)
- El fix#1 (V2-036, snapshot del navegador en bloque + off-thread + orphan sweep) **funcionó**: TTSMetrics ANTES del
  fix (18:34–18:45) = STARVED (`dur≈audio`, p.ej. 6.73/11.78); DESPUÉS (20:16–20:20) = SANAS (`dur<<audio`, 1.76/9.82).
- El corte residual **NO está en la emisión del TTS** (dur sano post-fix). Candidato fuerte por el interleaving: el
  **CORAZÓN de memoria `mem_processor` (LLM LOCAL qwen en Ollama)** dispara JUNTO al habla → contención de GPU con el
  STT whisper-mlx y/o bloqueo del event-loop. Hay que INSTRUMENTARLO para confirmarlo (esta iniciativa).
- **Reinicio: NO hace falta** — el fix ya está activo.

## Tareas (lo que pidió el operador)

1. **Instrumentar TODO lo que sea carga**, no solo los eventos principales: cada iteración, ciclo, función, callback,
   llamada a modelo/HTTP/DB, y las cosas tipo "las ~420 llamadas del snapshot" que detectamos — que sean VISIBLES en
   la observabilidad (con su duración cuando aplique). Marcar los que puedan amenazar el rendimiento.
2. **Etiquetar por CATEGORÍA** para el filtro (pocas, no 200):
   - **Principales** (por defecto ON): `task`, `metric`, `state`, `transcript`, `bot_speech`, `tts`, `stt`, `widget`.
   - **Memoria** (interacciones con la memoria: recall/remember/CORAZÓN/embeddings/queue).
   - **FlashBrain** (orquestación/turno/tools).
   - **Navegador** (act/snapshot/capturas/extract).
   - **System/Code Events** (por defecto OFF — al activarlo salen DOCENAS): llamadas internas, callbacks, ciclos,
     funciones, cualquier amenaza de rendimiento (p.ej. cada round-trip Playwright, cada escritura, cada tick).
3. **Selector ARRIBA del todo** del visor de observabilidad (una 2ª barrita de filtros): chips/toggles por categoría;
   por defecto todo lo Principal ON y **System/Code Events OFF**. Todo va en la MISMA lista, ordenado, con
   **hora:minuto:milisegundo**, para ver la secuencia real del sistema.
4. **Renombrar "Brain"**: ya NO hay un cerebro aparte — solo el FlashBrain ORQUESTADOR + procesos que lanza. Cambiar
   la etiqueta/categoría `brain` a algo como "Orquestador" / "FlashBrain" y los eventos de worker a su categoría.
5. **Agrupadores extra si faltan datos** (a confirmar durante la implementación): campo de **MÓDULO/pieza** (voz,
   memoria, navegador, worker…) y de **FUNCIÓN/rutina** en cada evento, para saber DÓNDE sucede cada cosa. Si al
   instrumentar veo que falta, lo añado y aviso.

## Pieza a tocar
- Backend: `voice/observer.py::emit` (añadir `category` + `module`/`func` al evento; nuevas llamadas de
  instrumentación en los puntos calientes: `mem_processor`, `queue`/writer, embeddings, `owner` Playwright acts,
  `dispatch`, `nucleo.py` turno). Cuidado: la instrumentación NO debe volver a cargar el hilo de voz — el `emit` ya
  escribe off-thread (V2-036); los eventos System/Code deben ser baratos de emitir (y filtrables sin coste).
- Frontend: el visor `/debug` (o el componente de observabilidad) — 2ª barra de filtros por categoría + orden por
  ts con ms + relabel.

## Siguiente diagnóstico (con la instrumentación puesta)
Confirmar si el CORAZÓN (`mem_processor`, qwen local) o los embeddings bloquean el loop/GPU durante el habla; si es
así, moverlos de verdad off-hot-path (cola dedicada / prioridad / GPU aparte) o abaratar el modelo local.
