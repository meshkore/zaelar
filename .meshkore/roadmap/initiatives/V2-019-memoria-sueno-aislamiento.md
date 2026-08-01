---
id: V2-019
title: Memoria — el SUEÑO (consolidación CORTO→LARGO + olvido) + aislamiento del tester + limpieza de la BD
epic: v2-colmena
status: next
priority: high
owner: ricart
modules: [memory, nucleo, tester]
depends_on: [V2-013]
wall_order: 19
created: 2026-07-10
updated: 2026-07-10
---

## Goal

V2-013 construye el CORAZÓN que ESCRIBE bien (destila, decide, no duplica). Esta iniciativa cierra el **ciclo de
vida** de ese dato: el **"sueño"** (consolidación CORTO→LARGO por TTL/peso, decay, eviction) cableado al loop
orquestador, y la **higiene**: que el tester no contamine el perfil real y que la BD contaminada de hoy quede
limpia. Sin esto, el CORTO limpio de V2-013 (T131, `kind='conv'` con TTL) nunca se poda y el mapa se vuelve a
ensuciar; y sin aislar el tester no se puede MEDIR "basura descartada vs. hecho reforzado" (aceptación de V2-013).

## Encaje con lo YA construido

- `memory/consolidator.py` **YA** tiene `promote` (corto→mid→long por edad), `dedup` (texto idéntico), `decay`
  (Ebbinghaus) y `evict` (por peso, respeta pinned). **Falta**: (a) que lo **dispare el loop orquestador**
  (`nucleo/loop.py`) a intervalos; (b) promoción por **TTL/peso** (no solo edad) para el `kind='conv'` de V2-013;
  (c) que el `evict`/`decay` estén calibrados para un solo usuario.
- `ZAELAR_DB` **YA** existe como override de ruta (`memory/db.py::db_path`). **Falta**: cablearlo en el arranque del
  tester para que zaelar corra con una BD separada durante las pruebas.

## Qué se construye

1. **El SUEÑO cableado**: el loop orquestador (`nucleo/loop.py`) dispara `memory.consolidate()` a intervalos (por
   tiempo y/o por tamaño), sin prisa, off-hot-path. Emite pulsos de observabilidad (V2-014).
2. **Promoción CORTO→LARGO por TTL/peso**: el `kind='conv'` de CORTO (V2-013 T131) caduca por TTL; lo que ganó peso
   (se usó/reforzó) o que el corazón marcó relevante **sube** a LARGO; lo demás se descarta. No solo por edad.
3. **Calibración de decay/eviction** para un usuario doméstico (λ por tipo de memoria, límite de almacenamiento
   razonable, pinned intocable).
4. **Aislamiento del tester**: el arranque del tester (o su `guard.sh`) lanza zaelar con `ZAELAR_DB` a una BD de
   test separada (`memory/_data/zaelar.test.db`) → cero contaminación del perfil real. Documentar el flujo.
5. **Limpieza de la BD contaminada**: snapshot + purga de las filas basura actuales (≈240 filas, ~144 a 0.3 del
   write crudo, `state` vacío). Script idempotente y NO destructivo (respeta pinned real, si lo hubiera).

## Tareas

- [ ] T132 — El SUEÑO cableado: `nucleo/loop.py` dispara `memory.consolidate()` a intervalos (tiempo + tamaño), off-hot-path, con pulsos de observabilidad.
- [ ] T149 — COMPRESIÓN JERÁRQUICA con pérdida de detalle por antigüedad (resumen de recencia): el consolidador procesa el histórico reciente y produce resúmenes en cascada — últimos minutos casi literales · última hora → resumen breve · ayer → titular · más atrás → nada (o promovido a LARGO si fue significativo). Puebla/mantiene el dígest de recencia (`state.topics`/`state.recent`, ver V2-013 T148). El detalle se desvanece hacia atrás; lo significativo sube a LARGO. Aplica a conversación + actividad (ficheros subidos/bajados, widgets abiertos/cambiados).
- [ ] T133 — Promoción CORTO→LARGO por TTL/peso (no solo edad): el `kind='conv'` caduca; lo reforzado/relevante sube a LARGO.
- [ ] T144 — Calibrar decay (λ por tipo) + eviction (límite doméstico) + confirmar que pinned nunca se toca.
- [ ] T127 — Aislamiento del tester: arranque con `ZAELAR_DB` a `zaelar.test.db`; documentar en INI-013 / zaelar-observability.
- [ ] T145 — Limpieza de la BD contaminada: snapshot + purga idempotente no destructiva de la basura del tests/voice/e2e/agent/chat crudo.
- [ ] T150 — RECALL por VOCABULARIO-GAP (techo del embedding local): una pregunta que no comparte léxico con el hecho y exige conocimiento del mundo ("¿qué **instrumento** toco?" → "toco la **guitarra**") falla porque embeddinggemma da similitudes PLANAS en español (~0.5–0.95: "recuérdame sacar la basura" puntúa 0.955 para "instrumento" y "toca la guitarra" 0.512) y el FTS exige tokens exactos ("toco"≠"toca"). Detectado por el test bot (BATCH_10 #97). Opciones: expansión de query (sinónimos/hiperónimos SIN LLM en el read path — p. ej. tabla de sinónimos o un índice de conceptos del grafo), mejor modelo de embedding, o stemming/prefijo en FTS. No falsear el recall — subir la calidad de la recuperación.
- [~] T151 — RECUPERACIÓN TEMPORAL / conciencia CRONOLÓGICA (gap del SOTA) — AVANCE parcial (2026-07-10): el GRAFO
  DE CONCEPTOS (T126) ya resuelve la mitad de CO-RECUPERACIÓN cuando los eventos fechados comparten concepto
  ("¿mi trayectoria en el trabajo?" → 2016 becario + 2021 jefe afloran juntos por el nodo 'trabajo'; validado
  BATCH_18 #172). El ORDEN entre ellos lo hace el LLM del turno leyendo los años del texto. FALTA: aristas
  temporales explícitas `antes/después` para ordenar eventos SIN concepto común. Detalle original: responder "¿qué fue ANTES, X o Y?" exige CO-recuperar AMBOS eventos fechados y ordenarlos por fecha; hoy el retriever semántico solo trae con fiabilidad el evento de solape léxico fuerte (el otro queda fuera del top-8). LongMemEval sitúa a los mejores modelos en 0.20–0.29 de "chronological awareness". Detectado por el bot (BATCH_12 #112). Propuesta: (a) detectar intención temporal-comparativa (antes/después/qué fue primero/cuándo) SIN LLM (regex) y (b) una ruta de recuperación por TIEMPO — traer los eventos fechados/episódicos ordenados por `created`/`meta.said_at` en la ventana relevante, no solo por similitud. La recencia/tiempo debe ser señal de primera clase (SOTA). Encaja con la capa episódica y con T149 (compresión jerárquica temporal).
- [ ] T147 — Verificación + **revisión de alineación**: tras hablar, el CORTO se poda solo; el tester no toca el perfil real; la BD queda limpia; el LARGO conserva lo relevante.

## Aceptación

- El CORTO (`kind='conv'`) se poda solo por TTL; lo relevante sube a LARGO; el mapa no se re-ensucia con charla.
- El tester corre contra su propia BD → el perfil real del operador queda intacto tras una oleada de pruebas.
- La BD actual queda limpia (basura fuera), con un snapshot previo por si acaso.
- pinned nunca se borra; el query sigue rápido.

## Riesgos

- Consolidación demasiado agresiva → se pierde contexto útil del CORTO antes de tiempo. TTL/peso conservadores + calibrar.
- Purga destructiva → snapshot obligatorio antes; script idempotente y reversible.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
</parameter>
