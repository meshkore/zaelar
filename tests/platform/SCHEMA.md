# Test Map Contract · schema 2

El Observatory, el CLI, Codex, Claude Code y CI consumen el mismo árbol:

La guía operativa para agentes es `tests/README.md`; este documento define solamente el contrato de datos y
ejecución que deben respetar el catálogo, el servidor y los runners.

```text
suite
└── steps[]             orden funcional visible (1.1, 1.2, 1.3…)
    ├── order
    ├── depends_on[]    dependencias explícitas cuando existan
    └── case_groups[]   pytest, corpus, escenarios, personas…
        ├── execution   ejecución ordenada del grupo
        └── cases[]
            ├── id      estable y único
            ├── locale  "es" | "us" | ""   ← ÍNDICE PRIMARIO del visor
            ├── theme   agrupador temático (casos de uso); "" si la suite no tiene
            ├── plan[]  [{id,label}] lo que se va a hacer, en orden, ANTES de hacerlo
            ├── input / expected / verification
            ├── consumes[] / produces[]   productos causales para recorridos stateful
            ├── execution_path / source / raw
            └── execution
```

## Reglas

1. Cada tipo principal vive en `tests/<suite>/suite.json` y declara sus pasos en orden.
2. Pytest se adapta automáticamente a casos schema 2 usando las rutas del mapa numerado.
3. Un corpus rico declara `catalog_provider` en su paso. El proveedor devuelve grupos y casos; el dashboard no
   contiene lógica específica de memoria, voz, headless o widgets.
4. Toda acción se resuelve de nuevo en servidor por su ID. El navegador nunca envía comandos arbitrarios.
5. `execution.kind=pytest` ejecuta uno o varios nodeids; `execution.kind=command` usa un argv declarado por el
   proveedor. `{python}` se sustituye por el intérprete activo.
6. Una suite determinista recorre los paths en orden de paso. Un botón de grupo recorre sus casos en el orden del
   catálogo. Los corpus stateful declaran esa condición y pueden usar tandas.
   Un caso cronológico aislado declara `replay_prefix=true`: antes de verificarlo reconstruye desde el paso 1 la
   misma BD, por lo que nunca consulta datos que no hayan sido insertados previamente.
7. Todo runner escribe el protocolo durable en `tests/runs/<run-id>/events.jsonl`. Los runners ricos deberían emitir
   `test.discovered`, `test.started`, `interaction.input/output`, `test.finished` y scores del juez.
   Un runner cuyos casos son MÁS DE UNA ACCIÓN declara además un **plan** y lo va marcando (V2-709):
   `plan` en `test.discovered`/`test.started`, `step.started` / `step.finished` (`{test_id, step, status}`)
   según avanza, y `watchdog.verdict` para una opinión que no es el estado de un paso. Un paso que el caso
   no ejecuta se marca `skipped`, nunca se omite: una casilla que falta deja de ser una lista.
10. **El idioma es un índice, no un filtro.** `locale` selecciona un CONJUNTO de casos (`es` y `us` no son
    el mismo producto: aquí Wallapop, allí otro mercado). Un caso sin `locale` — un nodo de pytest, un
    corpus de memoria — pertenece a TODOS los conjuntos, que es lo correcto porque genuinamente es el mismo
    test. El `theme` agrupa por DE QUÉ VA el caso; el `tier` sigue siendo dificultad y no agrupa nada.
    Tabla de familias e idiomas: `tests/platform/families.py`; temas: `tests/use_cases/themes.py`.
8. Cualquier pytest sin propietario aparece como paso `unmapped`; la auditoría de plataforma exige cero huecos.
9. `--no-open` no desactiva el Observatory: únicamente evita que el proceso del agente abra el navegador. El run
   sigue disponible en el puerto fijo 8765 y conserva el mismo exit code.
11. **El servidor está atado a la RAÍZ de runs, no a un run** (V2-709). `/api/runs` lista todos (vivos primero,
    los abandonados marcados `stale`); `/events` multiplexa los VIVOS y etiqueta cada línea con su `run_id`;
    `/events?run=<id>` sigue a uno solo. Un run nuevo se UNE al visor que ya está en pie — antes lo mataba, y con
    dos agentes probando a la vez el segundo borraba al primero de la pantalla. `<id>` es un nombre de directorio
    y nunca una ruta: `..` se rechaza.
12. **El Observatory no lanza nada.** No hay botón de play ni endpoint de lanzamiento: los tests los conducen los
    agentes. Pedir una corrida es pedírsela a un agente.
10. Solo hay un Observatory activo por workspace. El handoff reemplaza el visor anterior; los agentes no deben
    solapar procesos de test porque ocultarían el run previo sin detener necesariamente su carga de trabajo.
11. Un recorrido cronológico debe declarar `consumes`/`produces`, validar el orden antes de arrancar y comprobar
    cada efecto antes de publicarlo. Ejecutar un caso posterior reconstruye su prefijo en un workspace aislado.

## Añadir una suite o corpus

- Añadir/editar `tests/<suite>/suite.json`.
- Para pytest, asociar sus rutas al paso numerado del mapa.
- Para casos ricos, crear una función `platform_groups()` o equivalente y referenciarla como
  `modulo:funcion` en `catalog_provider`.
- Cada caso debe describir entrada, expectativa, verificación, ruta interna, fuente y acción.
- Ejecutar `./.venv/bin/pytest -q tests/platform/tests` y comprobar `/api/catalog/<suite>`.

Ejemplos:

```bash
./.venv/bin/python -m tests run browser
./.venv/bin/python -m tests run journey
./.venv/bin/python -m tests run voice --case voice::scenario::agenda
./.venv/bin/python -m tests run memory --case memory::v1::0000
```
