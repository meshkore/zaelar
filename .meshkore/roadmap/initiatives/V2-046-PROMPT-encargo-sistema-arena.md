# V2-046 · PROMPT DE ENCARGO — "Sistema arena": rails/widgets/tools auto-generados, genética y reglas

> Este fichero es el **encargo del operador** (2026-07-16) a un agente de análisis (Fable 5). El entregable del
> agente será la iniciativa `V2-046-sistema-arena.md` con el plan. Se conserva el prompt aquí para re-lanzarlo o
> auditarlo. — preparado por el agente de sesión a petición del operador.

---

## Quién eres y qué te pido

Eres un agente de diseño/arquitectura trabajando sobre **zaelar** (asistente personal por voz, repo en el que
estás). Tu encargo: **analizar cómo encaja la visión de abajo en la arquitectura ACTUAL** y devolver un **plan
PEQUEÑO y priorizado** (resumen, no un tomo): qué conviene cambiar YA, qué se deja para el futuro, y qué queda
solo como PLACEHOLDER documentado. Si algo encaja bien, el operador te pedirá extenderlo después — no te
adelantes. **Regla de oro: nada de lo que propongas puede romper lo que funciona** — solo adaptar/ampliar con
garantías. No escribas código en este encargo: análisis + iniciativa + roadmap + placeholders en docs/diagramas.

## Contexto: qué acaba de pasar (el detonante)

Hoy se cerró un bug P1 añadiendo **`play_video` como tool nativa de 1ª clase** del FlashBrain (V2-045, hermana de
`play_music`): el modelo no-razonador confundía "pon el vídeo de X" con música, la prosa no lo arreglaba, y una
tool dedicada (decisión tool-vs-tool) sí. Fix táctico CORRECTO — pero estratégicamente destapa el problema:
**cada capacidad nueva ha necesitado que un desarrollador hardcodee una tool + su rail + sus reglas.** El operador
ve música y vídeo porque son SUS casos; otra persona inventará jugar a las cartas, un parchís, vender por Twitter,
hablar con los colegas. **No podemos hardcodear un rail por caso de uso.**

## La visión del operador (depurada, en sus términos)

1. **"Como la arena"**: un sistema que se adapta a cualquier caso de uso como la arena al recipiente. `play_music`
   y `play_video` no deberían ser, a largo plazo, tools nativas: deberían ser **WIDGETS** que traen consigo su
   **RAIL auto-generado y auto-entrenado por el uso**. Cada caso de uso inventado por un usuario = un widget
   (código + storage) + su rail (cadena de conducción) + sus reglas + sus instrucciones de uso — **todo generado
   sobre la marcha** por el propio agente (los workers Claude Code ya generan/modifican widgets hoy).
2. **Convivencia**: decidir si conviven rails de tools nativas (los "instintos") con rails de widgets/tools
   generados por el usuario — y cómo. Ambas cosas deben tener cabida.
3. **Widgets incompletos = el agente los completa**: el widget de música no genera playlists, al de vídeo le
   faltan botones (ampliar/reducir)… Todo eso debe poder añadirse **desde el propio agente** (modificación de
   widgets por voz), no solo desde desarrollo. El operador NO va a hardcodear rails ni comportamientos.
4. **Instintos vs aprendido**: el agente nace con una base mínima ("instintos" = genética primigenia) y TODO lo
   demás se forma con el uso, por las instrucciones de cada usuario e incluso colectivamente (unos usuarios
   forman a otros). Las **instrucciones de los rails pueden vivir en la MEMORIA** (ya tenemos memoria central con
   estado/corto/largo, slots, y `state.rails` con runs vivos).
5. **GENÉTICA transmisible (placeholder, futuro en red)**: cuando los agentes personales se conecten en red
   (canal MeshKore ya existe), podrán **transmitirse "genética"**: reglas de rails, widgets, tools, widgets
   mejorados por cada usuario. Requisitos que deben quedar al menos como placeholder de diseño:
   - Transferencia inicialmente SOLO entre individuos que se conocen y han consentido conectarse.
   - Control de privacidad: qué datos pueden cruzar de un agente a otro (conocimientos, agendas… por permisos).
   - TODO lo que entre pasa tests de **prompt-injection** y validación de seguridad (ya existe la postura de
     cuarentena `trust=untrusted` del canal de cluster — apoyarse en ella).
6. **BRAIN RULES y USER RULES (esto sí es candidato a AHORA):**
   - **`brain rules`** = la genética primigenia HARDCODEADA: las reglas básicas de comportamiento del cerebro que
     ya existen (el system prompt del FlashBrain, la capa de operación V2-027, los guards). Solo hay que
     NOMBRARLAS y tratarlas como concepto de primera clase.
   - **`user rules`** = reglas que el USUARIO impone y que viven en el **ESTADO** (memoria): "no me contestes con
     tanto texto", "responde solo sí o no", "cuando te pida una acción ejecútala sin responder". El agente viene
     EN BLANCO de user rules y cada usuario lo personaliza hablándole. El FlashBrain debe **reconocer en cada
     request** cuándo le están dando una instrucción que es una regla de usuario (vs una orden puntual) y
     persistirla. OJO: ya existen piezas — `set_style_directive` (directiva de SESIÓN, no persiste),
     `memory.compose_state()` (el ESTADO que viaja en cada prompt), el CORAZÓN `mem_processor` (destila cada
     turno), los slots. Mapea user-rules sobre esas costuras en vez de inventar un sistema paralelo.

## Qué debes leer antes de opinar (docs canónicas del repo)

- `CLAUDE.md` (contexto completo; especialmente decisiones V2-025/026/027, V2-036/038, V2-041/042/044/045).
- `.meshkore/roadmap/initiatives/V2-042-rails-comportamientos-conducidos.md` — el patrón RAIL canónico (los
  widgets son "el rail FUNDACIONAL"; taxonomía). Es LA pieza que la visión quiere generalizar.
- `nucleo/rails.py` + `nucleo/flash/music_flow.py` (rail vivo) · `nucleo/flash/router.py` (TOOLS; play_music /
  play_video V2-045) · `nucleo/flash/prompt.py` (capa V2-027 = las brain rules de facto).
- `widgets/generator.py` (+ `_CONTRACT`), `widgets/actions.py`, `widgets/background.py`, `widgets/brief.py` — el
  sistema de widgets ya genera código+storage+acciones+usage declarativos sobre la marcha.
- `.meshkore/docs/architecture/zaelar-architecture.md` (§8 catálogo de tools) y `zaelar-memory.md` (ESTADO,
  slots, `compose_state`).
- `frontend/pages/architecture.html` (diagramas: Arquitectura/FlashBrain/Memoria/Widgets — habrá que tocarlos).
- Seguridad de cluster: `connectors/meshkore/security.py` + `zaelar-security.md` (base para la genética en red).
- Visión cloud/comercial (secundario, para el roadmap futuro): `~/.meshkore/tmp/zaelar-cloud-*.html`.
- Feedback duro del operador: **NADA de tablas de verbos/keywords hardcodeadas para routing** (enseñar al modelo
  + guards de invariante deterministas, sí; diccionarios de comportamiento, no).

## Invariantes que NO se tocan

- FlashBrain = NO-razonador, latencia sub-segundo, memoria FUERA del turno síncrono (V2-011).
- Escritor ÚNICO de memoria; workers escriben por `remember_external` con gates.
- Un widget nunca rompe el resto; validación del generador; storage separado del código.
- MeshKore Standard v27 (docs en `.meshkore/docs/`, iniciativas ancladas, cluster.yaml).
- Entrada no confiable del cluster → cuarentena, allowlist de tags, prompt-injection hardening.

## Entregables (pequeños, esta pasada)

1. **`.meshkore/roadmap/initiatives/V2-046-sistema-arena.md`** — la iniciativa: análisis de encaje (qué piezas
   actuales YA son la visión a medias: generator, rails, state, brief declarativo, set_style_directive), y el plan
   en tres cubos: **AHORA** (pequeño y sin riesgo; p.ej. user rules en el ESTADO + naming brain rules; criterios
   para cuándo una capacidad merece tool nativa vs widget+rail), **DESPUÉS** (rails auto-generados por widget:
   contrato de manifest para declarar un rail, aprendizaje por uso), **PLACEHOLDER** (genética en red: permisos,
   privacidad, validación anti-injection, transmisión entre conocidos).
2. Ajustes MÍNIMOS de contexto si procede: una entrada en `CLAUDE.md` §Decisiones (breve, estilo puntero),
   mención en `zaelar-architecture.md` y placeholder en el diagrama — SOLO si tu análisis concluye que va.
3. Veredicto claro: ¿implementar algo YA? ¿qué exactamente y por qué no rompe nada? Con estimación de tamaño.

Commitea tu trabajo (mensaje claro) y push a la rama actual (política del operador: repos siempre al día). No
toques código de producción en este encargo.
