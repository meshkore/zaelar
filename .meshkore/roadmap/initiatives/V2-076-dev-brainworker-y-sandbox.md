# V2-076 — Dev brainworker (crear/probar/subir código) + sandbox de ejecución

**Estado:** F0 CONSTRUIDO Y VERDE (todas las partes; activa al próximo `make run`). 2026-07-26. Commits en engine;
mapa de tests TODO VERDE (nodos 2.9 sandbox, 2.10 git+dev, 6.8 permisos).
**Hecho:** A (permisos por-cluster en store + conceder al CONECTAR por lenguaje natural→tool→confirm→persist) ·
C (turno de cluster reusa el catálogo del FlashBrain gated por permisos, sin duplicar) · B (sandbox subproceso ligero
cross-platform) · puente git acotado (`nucleo/git_cli.py`, solo repo autorizado) · dev worker acotado en `dispatch`
(cwd temporal + git por puente + sin bridges de memoria). Cero regresión verificada. Susurro sigue OFF (incidente aparte).

---
_(Plan original, ya implementado en F0:)_

**Estado (histórico):** PLAN (mapeando la base para acoplar sin duplicar). 2026-07-26. Petición del operador tras el bloqueo
"zaelar no puede subir al repo". Refinado con 3 precisiones del operador (permisos-por-cluster al conectar, el cluster
pasa por los túneles del FlashBrain gated por permisos, sandbox ligero cross-platform). **Regla dura del operador:
entender bien la base LIMPIA actual y modificar SOLO lo necesario — nada de duplicados, módulos parcheados ni alterar
a peor; el resto de canales/casos de uso debe seguir funcionando igual.**

## Permisos por-CLUSTER, preguntados al CONECTAR (precisión del operador)

Por defecto un cluster nuevo = **seguridad máxima** (sin brainworkers, sin ejecución de código, tools denegadas). Pero
al **crear/conectar** un cluster (cuando se activa el rail connect/create de meshcore), se **pregunta al operador su
PERFIL DE PERMISOS inmediatamente** → así el operador fija de una vez "puedes esto, esto y esto" y se olvida. Cada
cluster/canal/relación agente-agente lleva asociados: sus **convenciones/reglas** (el PACTO, V2-072) **+ su PERFIL DE
PERMISOS** (esta pieza). Escalar preguntas puntuales al operador está bien, pero por defecto lo más automático posible
sin comprometer. El perfil vive con la entidad del cluster/relación (junto al pacto), no hardcodeado.

## Principio (decisión del operador)

La arquitectura ya tiene las dos piezas clave: **FlashBrain** (orquesta la conversación) y **brainworkers** (crean
código, widgets, ejecutan comandos, desarrollan). **No hay que construir piezas nuevas para la Parte 1** — solo
**enrutar bien y acotar**. El FlashBrain **NO escribe código** (salvo con un razonador potente); cuando una
conversación se vuelve compleja (desarrollo, investigación tipo "motos en Wallapop", crear un algoritmo) **hace de
GATEWAY**: escala a un brainworker y orquesta. Lo mismo aplica a una conversación de cluster que deriva en código.

Separar en DOS partes:
- **Parte 1 (rápida, sin complicar):** que el brainworker pueda hacer el trabajo de dev (código + comandos + git) de
  forma ACOTADA y gobernada por permisos. Reusa lo que ya hay.
- **Parte 2 (futuro, no urgente):** el SANDBOX para EJECUTAR ese código con certeza de que no compromete el host.

---

## PARTE 1 — FlashBrain gateway → dev brainworker acotado (rápida, reusa lo existente)

**Qué existe hoy:** el turno del OPERADOR (trusted) → FlashBrain → `escalate_to_slowbrain` → `nucleo/dispatch.py` →
brainworker Claude Code (`nucleo/workers/claude_session.py`) que escribe ficheros y corre Bash **acotado a los CLIs
internos** (`_BRIDGE_TOOLS`: mem_cli/nav_cli/widget_cli…; "NUNCA un Bash pelado"). El canal de **cluster** (untrusted)
va con `deny_tools` → sin tools. **Falta:** que exista un MODO de worker de dev con capacidad de git/build en un
directorio de trabajo, gobernado por permiso del operador.

**El plan (ajuste de enrutado + acotado, sin arquitectura nueva):**

1. **FlashBrain = gateway, no escribe código.** Reforzar el enrutado: toda petición de DESARROLLO (operador, o
   conversación de cluster que se vuelve compleja, o investigación) **escala a un brainworker**; el FlashBrain
   orquesta/reenvía. Es prompt + routing (la tool `escalate_to_slowbrain` ya existe).

2. **Un `kind` de worker "dev" con toolset ACOTADO** (relajación CONTROLADA del invariante "Bash solo CLIs internos",
   en `dispatch._tools_for` + `claude_session`):
   - Trabaja en un **directorio de trabajo dedicado** (scratch/temporal), NUNCA la raíz del proyecto ni el FS abierto.
   - `--allowedTools`: escribir ficheros DENTRO del work dir + `Bash(git:*)` acotado + runners de build/test
     concretos. **Nunca un Bash abierto.**
   - **Acotado en recursos**: tope de tiempo/CPU/mem (no saturar el host), sin acceso a secretos/memoria más allá de
     lo concedido, red limitada.
   - **git push acotado al REPO autorizado** (deploy key / credencial de grano fino; allowlist de repos).

3. **Gate de PERMISOS (la frontera de seguridad):**
   - **Operator-only:** el dev worker solo se dispara desde un turno del OPERADOR o desde su **política pre-seteada**.
     El canal de **cluster untrusted NUNCA** lo dispara directamente (sigue `deny_tools`): el peer **propone**, y el
     FlashBrain (lado operador) hace de gateway y escala **con la autorización del operador**. Untrusted → gateway →
     worker acotado. Así un agente hostil no puede hacernos ejecutar/subir código malicioso.
   - **Permisos PRE-SETEADOS** (no molestar al operador cada vez): el operador autoriza UNA vez "repo X / colaboración
     Y → dev worker permitido"; dentro de ese ámbito el worker actúa solo; pregunta al operador SOLO al salirse
     (repo nuevo, deploy, acción irreversible).

**Esto resuelve el caso de zalo:** operador pre-autoriza el repo del algoritmo → el FlashBrain hace de gateway y
escala la tarea de código al dev worker → el worker escribe/prueba/sube en su work dir → zalo ve código real. El
AGENTE lo hace; el operador solo autoriza. Hasta la Parte 2, el aislamiento es: work dir dedicado + tools acotadas
(git, no Bash abierto) + gate operator-only + topes de recursos.

**Esfuerzo estimado:** pequeño-medio — un `kind` de worker + su `_tools_for` + el work dir + la política de permisos.
Sin piezas nuevas de arquitectura.

### Parte 1C — el turno de CLUSTER pasa por los túneles del FlashBrain + catálogo de acciones (gated)

Precisión del operador: ya tenemos código que **identifica acciones** y mucho más; el turno agente-agente **debe poder
pasar por esos mismos túneles del FlashBrain y responder al CATÁLOGO DE ACCIONES**, siempre que **se respeten los
permisos del cluster**. Es la culminación natural de V2-069 «una sola mente»: hoy el turno de cluster corre por un
camino MÍNIMO (`cluster.respond` = `FastClient.complete` identidad-safe con **tools apagadas en duro**); el cambio es
que ese perfil UNTRUSTED deje de tener las tools apagadas EN DURO y pase a estar **gobernado por el PERFIL DE PERMISOS
del cluster**:
- **Por defecto (permiso cero): idéntico a hoy** — sin catálogo de acciones, identidad-safe. Cero regresión.
- **Con permisos concedidos por el operador:** el turno de cluster se enruta por los MISMOS túneles del FlashBrain
  (misma identificación de acciones / catálogo `router.TOOLS` / `escalate` / dispatch) pero **filtrado al subconjunto
  de acciones que el perfil permite** (p. ej. solo "escalar código a un dev worker para el repo X"). El peer no elige
  tools; el catálogo disponible lo fija el perfil de permisos que puso el operador.
- **Sin duplicar:** se REUSA el catálogo y el dispatch existentes; el punto de acoplamiento es el gate que hoy es
  binario (tools on/off, `deny_tools`) y pasa a leer el perfil de permisos del cluster. (El seam exacto lo confirma el
  mapeo de la base en curso.)

Así, "una sola mente" es literal: el mismo motor y los mismos túneles atienden operador y agentes; lo único que cambia
por interlocutor es **QUIÉN** (confianza) → **qué permisos/acciones** hay disponibles.

---

## PARTE 2 — Sandbox de EJECUCIÓN (avanzar diseño, NO urgente)

**Problema:** ejecutar código creado (Python/Rust, montar SQLite interno, etc.) —pedido por el operador o **derivado
de una conversación de cluster**— con CERTEZA de que no compromete el host ni lo satura. Los **widgets ya están bajo
control** (corren local, datos aislados, Chromium headless); el hueco es el código **no-widget** (scripts/algoritmos).

**Requisitos:** correr en **Windows y Mac**, hacer el máximo de cosas de forma controlada, sin saturar el host, "no
hipercomplejo de momento". Aislamiento del disco/secretos/red + topes de recursos + efímero + observabilidad para
auditar lo ejecutado.

**Direcciones a evaluar:**
- **A. Sandbox nativo del SO + topes** (lo más ligero, sin runtime extra): macOS Seatbelt (`sandbox-exec`) + Windows
  AppContainer/Job Objects + work dir temporal + sin red por defecto + límites CPU/mem/tiempo. Contra: perfiles
  distintos por SO, Seatbelt está semi-deprecado.
- **B. Runtime de contenedor rootless efímero** (punto medio pragmático, **recomendado para avanzar**): Podman/Docker
  rootless, `--network none`, montaje de solo-lectura + un work dir efímero, límites `--cpus/--memory`, contenedor de
  usar y tirar. Cross-platform (Win+Mac). Precedente: el proyecto YA permite Docker para el **tester** (el core sigue
  sin Docker; esto es un add-on opt-in de ejecución de dev). Aislamiento fuerte + control de recursos "de fábrica".
- **C. micro-VM / VM ligera** (aislamiento máximo, más setup): Lima/Krunkit (Mac), WSL2 (Win). Para el nivel más alto
  o la versión cloud.

**DECISIÓN del operador (2026-07-26): el más FÁCIL y LIGERO, no el más potente.** Cross-platform Win/Mac, arranque
muy fácil, operación sencilla, soporta Python + SQLite + básicos. **Docker NO por defecto** (consume mucho, va mal,
"se cuela") — disponible solo como fallback cuando haga falta algo más complejo.

→ **Elección por defecto: SUBPROCESO AISLADO (sin runtime extra, arranque instantáneo, cross-platform).** El código
corre en un **proceso Python nuevo** con: **cwd = directorio temporal dedicado** (solo ve ese dir), **entorno
SCRUBBEADO** (sin secretos ni env del operador), **sin red por defecto**, **topes de recursos** (CPU/mem/ficheros/
procesos vía `resource.setrlimit` en Mac/Linux; Job Objects/timeout en Windows) y **timeout de pared** (mata el grupo).
Python + SQLite salen de fábrica (stdlib). Ligerísimo, cero infra, fácil de operar. No es aislamiento de kernel a
prueba de balas, pero con cwd temporal + env limpio + sin red + topes + sin secretos es un primer sandbox razonable.
**Fallback: Docker** (opt-in) cuando se requiera aislamiento fuerte o dependencias pesadas — el core sigue sin
depender de Docker (precedente: el tester ya lo permite). **C (micro-VM)** queda para el nivel máximo/cloud. Rust:
más adelante (compilar+ejecutar dentro del mismo sandbox de subproceso o Docker si hace falta toolchain).

---

## Seguridad (invariante que NO se toca)

- El canal de **cluster untrusted** NUNCA obtiene tools directamente (sigue `deny_tools`). La única vía a un worker
  con capacidad es el **gateway del operador** (turno o política pre-seteada). Untrusted → gateway → worker acotado →
  (Parte 2) sandbox.
- El dev worker sin sandbox (Parte 1) queda acotado por work dir + tools + gate + topes; el sandbox (Parte 2) lo
  endurece a "aunque el código sea maligno, no toca el host".

## Progreso (2026-07-26)

- **F0a HECHO** (commit): permisos por-cluster en `store.py` (get/set, deny por defecto) + contrato `perms.py`
  (perfil→subconjunto del catálogo + contexto de escalada acotado). Aditivo, cero regresión. Tests: `test_perms.py`,
  nodo 6.8.
- **F0b HECHO** (commit): el turno de cluster REUSA el catálogo del FlashBrain gated por permisos (seams 1-2):
  `fast_client.complete` con function-calling no-streaming; `cluster.respond(tool_names, escalate_ctx)`;
  `brain`/`bridge._brain_turn` cargan y pasan los permisos. **Default (sin permisos) = idéntico a hoy, verificado
  (222 tests verdes).** La arquitectura "una sola mente gated por permisos" YA está en pie.
- **HECHO (commits posteriores, mismo día):** las 3 piezas que este bloque listaba como pendientes se completaron:
  (1) confirm de permisos al conectar (Parte A ask, commit `0c59c1a`); (2) sandbox POC subproceso (Parte B, commit
  `720eadf`, `nucleo/sandbox.py`); (3) dev worker acotado en `dispatch` + puente git (commit `1cc862a`,
  `nucleo/git_cli.py`). Este párrafo quedó de un borrador anterior sin actualizar — el encabezado del documento
  ("F0 CONSTRUIDO Y VERDE") es el que refleja el estado real; corregido en la auditoría 2026-07-26.
  **Nota de la auditoría 2026-07-26 (importante, no estaba prevista en el plan original):** el sandbox de la Parte 2
  quedó CONSTRUIDO pero **NO cableado** al proceso interactivo del dev worker (`nucleo/dispatch.py` lanza el
  `claude` del worker directo, sin pasar por `nucleo/sandbox.py`) — el orden "sandbox ANTES que ejecutar" de más
  abajo no se cumplió del todo: el dev worker puede Read/Write/Edit y ejecutar `git_cli` hoy sin que el sandbox de
  rlimits/env-scrubbed intervenga; su jail de filesystem es solo convención de prompt. Además se cerró un guard que
  el plan original no preveía explícitamente: `perms.gate_dev_by_objective` — el permiso `code` concedido no basta
  por sí solo, hace falta que el operador haya fijado un objetivo para esa relación (`capsule.objective`, que nunca
  se escribía en ningún sitio hasta este fix). Ambos quedan como tareas P0/P1 en
  `.meshkore/roadmap/initiatives/INI-0XX-audit-remediation.md`. **Cruce con V2-010** (seguridad-tester-v2, abierta
  desde 2026-07-09): su alcance ("sandbox del CodeAgent, deny-tools por defecto para input no confiable") es lo que
  esta iniciativa construyó en versión permission-gated — ver la nota añadida en `V2-010-seguridad-tester-v2.md`.

## Orden (revisado — dependencia clave)

El **sandbox (Parte B) va ANTES que la capacidad de EJECUTAR** del dev worker: ejecutar código creado (sobre todo si
lo deriva una conversación de cluster) sin aislamiento es justo el riesgo que el operador señaló. Git PUSH (escribir
al repo) es menos peligroso que ejecutar. Orden:
1. **Confirm de permisos al conectar** (A ask) — para que el operador conceda. Aditivo, bajo riesgo.
2. **Sandbox POC** (B) — subproceso aislado (cwd temporal + env limpio + sin red + topes). Ligero, cross-platform.
3. **Dev worker acotado** (`dispatch`): git push al repo autorizado + ejecución DENTRO del sandbox. La escalada de
   cluster (`context.dev/repo/execute`) monta este worker con el alcance del perfil. Es el paso que de verdad
   "sube y ejecuta"; por eso va el último, sobre el sandbox.
