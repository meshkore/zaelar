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
8. Cualquier pytest sin propietario aparece como paso `unmapped`; la auditoría de plataforma exige cero huecos.
9. `--no-open` no desactiva el Observatory: únicamente evita que el proceso del agente abra el navegador. El run
   sigue disponible en el puerto fijo 8765 y conserva el mismo exit code.
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
