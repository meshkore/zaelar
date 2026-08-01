# V2-057 — Verificación y certeza en las acciones (no ejecutar a ciegas)

**Origen (operador, 2026-07-20, sesión de voz e2e ~10 min):** zaelar **deduce la acción del texto y la ejecuta
a ciegas**, sin certificar el resultado. Episodio detonante: *"reproduce el último vídeo de José Luis Cárpatos"* →
zaelar reprodujo **uno de hace más de un mes** (búsqueda por relevancia, no por fecha) y ni siquiera dio la fecha
para poder comprobarlo; el operador tuvo que corregirle *"estamos a 20 de julio, hace dos días salió el último"*.

> **Doctrina del operador (cita):** *"las acciones necesitan verificación... no puedes simplemente deducir del texto
> cuál es la acción y ejecutar de cualquier manera; necesitas asegurarte de que esa acción es correcta y estructurar
> los pasos... incorporar SIEMPRE al final la parte de verificación e iteración. Si no podemos comprobar cuál es el
> último vídeo, nunca podremos estar seguros de que estamos ejecutando a la perfección esa acción. Y esto vale para
> un widget, para buscar información y para cualquier acción — p. ej. el tiempo en Tarragona de hoy: hay que saber la
> fecha de hoy, dar el tiempo de ahora en adelante. Todo eso es una inteligencia que lo tiene que CERTIFICAR."*

Estado: **EN CURSO** — rama `feat/v2-057-verificacion-acciones` (desde main, sin tocar la de memoria).

---

## Principio

Ninguna acción con una **restricción comprobable** (el último / el más reciente / el actual / el de hoy / el de
tal fecha / la cifra vigente) se ejecuta por pura deducción del texto: se **certifica contra la realidad** y se
ancla a la **fecha real de hoy** antes de darla por buena.

## Diseño — 3 capas (barato → caro; respeta la latencia)

**Capa 1 · Fast/widget — verificación barata IN-LINE (sin worker, sin latencia extra).** Cubre los casos comunes.
- **Vídeo** (`widgets/youtube/data.py`): «el último/más reciente» → orden por **fecha de subida** (`sp=CAI%3D`);
  `_search_id` extrae además **canal + fecha de publicación** del `videoRenderer` → la tarjeta muestra
  «canal · más reciente · hace 2 días» → resultado **comprobable de un vistazo**. Verificado: «el último de
  Cárpatos» → *hace 2 días*, canal correcto (lo que dijo el operador).
- **web_search sensible a fecha** (`providers/nucleo.py` sys2): el 2º pase de síntesis lleva **HOY** (fecha real) +
  regla de dar el dato **vigente y de ahora en adelante** (el tiempo/una cotización/un resultado «de hoy»), nunca
  uno caducado; avisa si los resultados no son de la fecha correcta.

**Capa 2 · Router — no adivinar.** La verificación barata de la capa 1 cubre los casos comunes SIN un clasificador
nuevo de verbos (evita regresiones, doctrina anti-tabla-de-verbos). Las gestiones multi-paso genuinas ya escalan por
`escalate_to_slowbrain` → entran en la capa 3. (Si en el futuro hiciera falta forzar escalada por restricción
comprobable que el fast path no certifica, sería aquí — hoy NO es necesario.)

**Capa 3 · Worker prompts — método OBLIGATORIO** (`nucleo/dispatch.py`, compartido por `_build_prompt` genérico y
`_web_prompt`):
- **`_today_block()`**: la FECHA/HORA REAL de hoy (el FlashBrain la llevaba en `live_state`; el worker **no** la
  recibía) para anclar toda restricción temporal.
- **`_METHOD_BLOCK` / paso 7 web**: **ENTENDER** (incl. restricciones IMPLÍCITAS: último = más reciente por fecha;
  hoy = fecha real, now-forward; tal día = esa fecha; cifra = la vigente) → **PLANIFICAR** → **EJECUTAR** →
  **VERIFICAR** con comprobación REAL (¿es de verdad el más reciente? ¿el dato es de hoy y sigue vigente? ¿es
  exactamente lo pedido?) → **ITERAR** hasta certificar. Nunca «hecho» sin verificar; si no se puede certificar,
  decirlo con honestidad.

## Hecho
- [x] Widget youtube: orden por fecha + metadatos verificables (canal/fecha) en la tarjeta.
- [x] Worker scaffold entender→planificar→ejecutar→verificar→iterar + fecha de hoy (genérico y web).
- [x] Síntesis de web_search anclada a HOY + now-forward.
- [x] Tests + dominio nuevo del mar de testing.

## Abierto (siguiente)
- [ ] El **Susurro** ya cazó ambos fallos de la sesión (findings `[P1·routing]` reproducción + `[P1·widget]`
      incompleto) → cerrar el lazo dev-loop confirmando que estos fixes los resuelven.
- [ ] Extender la verificación a más widgets con datos del mundo (tiempo/bolsa como widget backed con `tick`).
- [ ] Evaluar si merece una **tool `verify`** de 1ª clase que el worker invoque explícitamente (hoy es método en
      prompt) para dejar traza observable de la verificación.

## Bitácora
- **2026-07-21** · **Set de testing a fondo por dominios** (petición del operador) + fixes de lo que destapó.
  `tests/voice/e2e/agent/domain_sea.py` ampliado a 16 dominios (incl. `market`: idealista/coches.net/autoscout/wallapop/
  milanuncios/amazon → navegador; `create`/`modify` de widgets; `latest` V2-057). `tests/voice/e2e/agent/deep_nav.py` nuevo =
  ejecución REAL (escala con `execute=true` → worker conduce el navegador contra el sitio vivo). El mar (188
  turnos) destapó 19 fallos → arreglados los GENERALIZABLES (sin tabla de verbos): sinónimos de widget
  (panel/gadget) en `_CREATE_WIDGET_RE`; el backstop de promesa mira también la RESPUESTA; guard determinista
  `looks_like_marketplace_nav` (sitio nombrado + verbo → navegar, no web_search); guard `looks_like_modify_widget`
  (cambiar color/columna/estilo de un widget → generador, no data-op). Resultado: modify 1→10/10, market 78→98%,
  create 8→14/15, deep 100%; show/web/mem 100% (sin regresión). Residuo (fraseo de deseo sin verbo, código-vs-dato
  sutil) = territorio Susurro.
- **2026-07-20** · Creada tras la sesión de voz e2e. 3 capas implementadas y verificadas. Incorporado el fix
  quirúrgico que el worker en vivo dejó a medias en el widget youtube (orden por fecha) y completado (metadatos
  verificables). El banner «Cerebro rápido caído» de esa sesión fue un fallo transitorio del FlashBrain, ya
  recuperado (última respuesta real gpt-4o-mini ttft 970ms) — no un fallo de config.
