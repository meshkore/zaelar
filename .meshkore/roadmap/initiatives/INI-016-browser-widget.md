---
id: INI-016
title: Widget navegador (browser dentro de zaelar) + kind "backed"
status: done
owner: ricart
modules: [widgets, server, voice]
updated: 2026-07-08
---

## Goal

Que zaelar tenga un **navegador web propio dentro de la interfaz** — un widget que abre cualquier página (Google,
Wallapop, la RAE, una receta, una tienda) y reproduce vídeos de YouTube, con la web viviendo DENTRO del sistema
(no una pestaña suelta del SO) para que la **voz** pueda conducir la navegación y, más adelante, **automatizarla**
("abre Wallapop y búscame una moto por menos de 5000€ del 2020 en adelante"). Go-ahead del operador 2026-07-08.

Requisito derivado: casi ninguna web se deja incrustar en un `<iframe>` (X-Frame-Options / CSP `frame-ancestors`).
El navegador REAL tiene que correr en el servidor (Chromium headless) y renderizarse como **captura en vivo**. Eso
es un widget-app con **backend propio** = el *kind* `backed` que `zaelar-modules.md §Widget-apps` tenía diseñado
pero SIN construir. INI-016 lo construye (primer implementador).

## Qué se construye

### 1. Infraestructura genérica de widgets "backed" (reutilizable)
- `manifest.json` admite `"kind": "passive" | "backed"` (default passive; los 9 widgets existentes intactos). Un
  backed añade `"backend": {"owner": "owner.py"}`.
- `widgets/supervisor.py` — arrancado en el lifespan de `server/__init__.py` (MISMO loop que la voz): escanea el
  catálogo por `kind=="backed"`, importa cada `owner.py` y lo corre bajo tarea supervisada — **buzón**
  (asyncio.Queue), **reinicio con backoff** al caer, **desactivación tras N fallos** (`WIDGETS_BACKED_MAX_FAILS`=4,
  degrada al último estado congelado). Todo trazado por `voice/observer.py` (`kind:"backed"`).
- Contrato del owner: `async start()/stop()/handle(action, payload)`; es el **ÚNICO escritor** de
  `widgets/_data/<id>/`. La cara (`data.py`+`widget.js`) pasa a READ + ENCOLAR:
  `widgets/server_api.py:_route_backed()` mete el comando en el buzón en vez de aplicar `apply_action` inline
  (misma ruta para `POST /widgets/{id}/action` y el `[[widget.data]]` de Hermes).
- Endpoint genérico nuevo `GET /widgets/{id}/asset/{name}` — sirve un binario (la captura) desde el `data_dir()`
  del widget, path-safe + `no-cache`. Refresco por el MISMO `store.save()`→SSE (sin cambios).

### 2. El widget `navegador` (`widgets/navegador/`, primer backed)
- `owner.py`: **Chromium headless (Playwright)**, arranque perezoso (Chromium se lanza al primer comando). Navega,
  hace captura del viewport (1280×800) → `shot.png`; clic/scroll del operador sobre la captura se mapean a
  coordenadas de página → Chromium → nueva captura. Órdenes: `open/search/youtube/back/forward/reload/scroll/
  click/type/press`.
- **YouTube = excepción**: una captura no reproduce vídeo → el owner resuelve el `videoId` (scrape del HTML, sin API
  key) y el widget monta el reproductor embebido real (`youtube-nocookie`).
- **Buscador = Bing por defecto** (`NAVEGADOR_SEARCH`): Google CAPTCHEA a Chromium headless (/sorry/index) y
  DuckDuckGo lo bloquea (418); Bing renderiza bien. Google sigue accesible con `open google.com`.
- **Gobernanza**: navegar (`open/search/youtube/back/forward/reload/scroll`) es `"safe":true` → la capa rápida del
  duo lo conduce por voz; `click/type/press` es `"safe":false` → la automatización dentro de una web escala a
  Hermes (mismo invariante de gobernanza de widgets).
- **Dep**: `playwright>=1.61` + `python -m playwright install chromium`.

### 3. Automatizador HÍBRIDO DOM-first (`agent.py`, Milestone 2, decidido con el operador 2026-07-08)
Un bucle goal-driven que conduce el navegador solo para cumplir un objetivo en lenguaje natural. Enfoque elegido
por el operador: **híbrido DOM-first** + **modelo barato dedicado** (no visión pura, no local).
- **DOM-first (barato):** cada paso pasa al modelo un SNAPSHOT DE TEXTO de los elementos interactivos visibles
  (árbol de accesibilidad → `[7] textbox "¿Qué buscas?"`, cap 60 elementos) — NO una captura. El modelo elige la
  siguiente acción por **function-calling** (`click/type/scroll/navigate/press/done/need_vision`). Solo tokens de
  texto → céntimos por tarea.
- **Comportamiento HUMANO en Playwright (gratis, sin tokens):** `owner._human_move` (curva Bézier + micro-pausas),
  clic con offset aleatorio, tecleo con jitter. Siempre activo — es lo que hace que las webs "vayan bien".
- **Cerebro = modelo barato dedicado** por el MISMO enrutado AIMLAPI del duo (UA-spoof anti-Cloudflare), por
  defecto `anthropic/claude-haiku-4.5`; configurable por env `NAVEGADOR_AGENT_{BASE_URL,MODEL,API_KEY,MAX_STEPS}`.
  NO usa el agente Hermes (el bucle es mecánico y barato; Hermes solo decide escalar).
- **Acción `automate`** (`safe:false` → la escala Hermes, gobernanza de widgets). Corre en el buzón del owner;
  resultado asíncrono → nota `[SISTEMA]` + aviso proactivo (voz+UI), mismo circuito que la generación de widgets.
- **Visión bajo demanda:** si el modelo no resuelve por DOM emite `need_vision` — en M2 es un STUB honesto (informa
  que necesitaría ver); la fase de visión se cablea en M3.

## Estado (2026-07-08)

- **M1 — navegador base:** v0.1.0 construido y validado e2e contra el sistema vivo (BRAIN=duo): abrir web (RAE
  renderiza, captura 517KB), buscar (Bing), reproducir YouTube (id resuelto), atrás/adelante, clic/scroll, asset
  endpoint, identify por voz sin ambigüedad, eventos de debug fluyendo.
- **M2 — automatizador DOM-first:** construido y validado. Local: condujo Bing (navigate→type+submit→click→scroll)
  antes de pedir visión. Live: `automate "abre la RAE"` → navigate + done honesto en ~11s, trazado en `/debug`.
  Mecanismo (bucle, snapshot, input humano, modelo barato, function-calling, reporte al brain) probado en vivo.
- **M2.1 — puente VOZ→navegador (fix, 2026-07-08):** en la primera prueba de voz en vivo el navegador NO cargaba.
  Causa (timeline `/debug`): la capa rápida (duo) decía *"te abro Wallapop"* pero NO emitía ninguna tag — y aunque
  hubiera emitido `[[show:navegador]]`, eso solo enseña un navegador VACÍO (Chromium arranca al primer COMANDO, no
  al mostrar). Para cargar una página habría que emitir `[[widget.data:navegador]]{...json...}`, justo el patrón
  bloque+JSON que los modelos rápidos débiles fallan (misma razón por la que la escalada dejó de ser una tag de
  texto). **Fix:** una FUNCIÓN dedicada `browse_web(action, target)` en la capa rápida (`voice/engine/llm/providers/
  duo.py::_TOOLS` + `_on_tool_call`), el mecanismo fiable y agnóstico del idioma — ENSEÑA el navegador Y lo navega
  en un paso, despachando por el MISMO `brain_action`→buzón del owner que ya funcionaba. Solo cubre las acciones
  `"safe":true` (open/search/youtube/back/forward/reload; verificado contra el manifest, fail-closed); automatizar
  (`automate`/click/type) sigue escalando a Hermes por gobernanza. Prompt (`brains/duo/prompt.py`) actualizado:
  bloque NAVEGADOR + ejemplos, con regla dura "es la ÚNICA forma de cargar una página; nunca digas 'te abro X' sin
  llamar a la función". Guarda anti-mudo: un turno tool-only (el modelo solo llama la función, sin hablar) dice una
  frase de espera en vez de quedarse mudo. **Verificado e2e** con el modelo real (`qwen2.5:14b`): emite browse_web
  con action/target correctos para web/búsqueda/YouTube y sigue usando `[[show:agenda]]` para widgets pasivos; el
  despacho carga Wallapop de verdad (mode=page, título correcto). Reinicio aplicado → vivo para los testers.
- **M3 — orquestación por voz + automatizador HÍBRIDO DOM+visión (2026-07-08):** decidido con el operador
  (visión híbrida + "Flash orquesta · Hermes planifica · bucle ejecuta"). Antes, "búscame una moto en Wallapop"
  se mapeaba a `browse_web(search)` → una búsqueda en **Bing** (no dentro de Wallapop): el flash brain no
  distinguía "buscar EN internet" de "hacer una TAREA en esta web".
  - **Orquestación (voz):** nueva función `automate_web(goal)` en la capa rápida (`duo.py::_TOOLS`). El flash brain
    RECONOCE la tarea de navegador y la LANZA (no la ejecuta); habla una frase de espera. Prompt actualizado con la
    distinción browse_web (abrir/buscar en internet) vs automate_web (hacer algo dentro de una web) + ejemplos.
  - **Reparto de roles (`duo.py::_orchestrate_automation`, background, off voice-path):** (1) Hermes PLANIFICA el
    objetivo a alto nivel sobre la página abierta (best-effort, timeout 45s; si cae, el bucle corre sin plan);
    (2) se encola `automate` {goal, plan} al buzón del owner → el bucle dedicado EJECUTA. Resultado por
    proactive+[SISTEMA]. Hermes no ejecuta clics (no bloquea la voz ni cuesta un turno ACP por paso).
  - **Bucle híbrido (`agent.py`):** DOM-first barato + **VISIÓN real** (M3, ya no stub): cuando el DOM no basta o
    el loop se atasca, adjunta la CAPTURA (verificado multimodal contra AIMLAPI con `anthropic/claude-haiku-4.5`) y
    actúa por COORDENADAS (`click_at`/`type_at`, ejecutadas con ratón humano en `owner.py`). Se paga la imagen solo
    en el paso que lo pide.
  - **Robustez anti-atasco:** empieza SIEMPRE en la página actual (regla "no te vayas a un buscador externo"),
    detecta atasco por (página no cambia | acción repetida) → auto-escala a VISIÓN; anti-wander (quédate en los
    resultados, llama a done); giveup honesto si ni con visión avanza.
  - **Hardening del puente de tools:** `duo.py` recupera una tool call que el modelo TECLEA como JSON
    (`{"name","arguments"}`) en vez de emitirla — enruta por el mismo `_on_tool_call` (salva browse_web/automate_web/
    escalate/style ante qwen2.5:14b + prompt grande).
  - **Validado e2e (vía HTTP, mismo camino que la voz):** abrir Wallapop → automate "busca motos <5000€" → el bucle
    se queda en Wallapop, se atasca en el DOM (cookies/buscador), pasa a VISIÓN, teclea "moto" en el buscador real
    → `/search?keywords=moto`, y se mantiene en resultados. La aplicación fina del filtro de precio en la UI
    compleja de Wallapop es aún irregular (límite del modelo barato + snapshot) → tuning iterativo, no un hueco
    estructural.
- **Pendiente / siguiente:** afinar la aplicación de filtros en sitios complejos (mejor snapshot / set-of-marks /
  feedback de paso); confirm-gate para acciones irreversibles (comprar/publicar/cambiar bio) antes de ejecutarlas;
  aceptación de conducción por voz en vivo (mic); reflejar el automatizador en el diagrama `architecture.html`.
- Aceptación de conducción por voz en vivo (mic) y una tarea Wallapop completa: pendientes del operador / tester.

## M4 — VENTANA REAL (headed) con perfil persistente (2026-07-08, go-ahead del operador)

Decisión clave con el operador: NO quiere "capturas de un Chromium headless", quiere un **navegador funcional de
verdad** que él también pueda tocar. Evaluadas 3 vías y elegida la ventana real:
- **iframe descartado** (muro doble): las webs reales prohíben ser incrustadas (X-Frame-Options / CSP
  frame-ancestors) Y la política de mismo-origen impediría conducir su interior por código. Callejón sin salida.
- **Ventana real (headed) — ELEGIDA**: como zaelar corre en la máquina del operador, `owner._ensure_page()` usa
  `chromium.launch_persistent_context(profile_dir, headless=False)` → un **Chrome de verdad** en el escritorio que
  el operador ve y controla (teclea credenciales, autentica, mueve, minimiza, toma el mando) mientras zaelar lo
  conduce con Playwright. Degrada a headless si no hay display (`ZAELAR_NAVEGADOR_HEADLESS=1` lo fuerza).
- **Streaming CDP embebido en el canvas**: alternativa futura si se quiere dentro de la tarjeta; más ingeniería.

Invariantes de arquitectura pedidos por el operador (metidos desde el inicio):
- **UNA sola ventana, sin basura**: contexto persistente único, reutiliza la pestaña existente (nunca abre una
  ventana por petición). Acción `close` (voz: "cierra el navegador" → `browse_web(action="close")`) cierra la
  ventana y deja el escritorio limpio (verificado: 0 procesos Chromium tras cerrar). Multi-pestaña real = futuro.
- **Sesión persistente**: perfil en `widgets/_data/navegador/profile/` (gitignored) → cookies/logins se guardan;
  no re-autenticar cada vez. Sinergia con el auto-accept de cookies: aceptado una vez, queda guardado.
- **Aislado de la máquina del operador**: perfil e instancia propios; NO toca su Chrome ni su automatización del
  9222/9200 (Playwright usa pipe; puerto de debug opcional por `NAVEGADOR_REMOTE_PORT`, nunca 9222/9200).

Validado: abrir Wallapop → ventana real + perfil persistente + cookies auto-aceptadas; cerrar → escritorio limpio.
Pendiente de docs-sync: actualizar el bullet del navegador en CLAUDE.md (dice "headless") y el diagrama
`architecture.html` para reflejar "ventana real / computer-use local".

## Fases 0-5 — TAREAS PARALELAS con tarjeta independiente por tarea (2026-07-08)

Go-ahead del operador: no quiere capturas de un headless sino un navegador funcional de verdad, y varias TAREAS a
la vez, cada una con su tarjeta (mini-navegador arriba + feed de progreso/resultados abajo). Decidido: **una tarjeta
independiente por tarea** + **ventana real headed** (ver M4). Correspondencia 1:1 **tarjeta(canvas) ↔ pestaña(Chrome)
↔ tarea(registro)**.

- **Fase 0 — `tasks.py`**: registro de tareas (id/estado/eventos/resultados/pregunta), propiedad del orquestador;
  cada cambio refresca SOLO su tarjeta (SSE `widget/data` con id de instancia `navegador::<taskid>`). En memoria.
- **Fase 1 — `owner.py::TaskBrowser`**: una pestaña por tarea (page/ratón/refs propios), misma ventana (contexto
  persistente); expone la interfaz de `agent.py`. `handle("automate")` **spawnea** (no await) → el buzón serial no
  bloquea → **N tareas en paralelo**; lock de captura entre tabs; `cancel_task` cierra la pestaña; `_human_*` con
  ratón por-pestaña. Validado: 2 tareas interleaved (Wallapop + Bing), 2 pestañas, 2 capturas, 2 estados.
- **Fase 2 — orquestador (`duo.py`)**: `automate_web` → `_orchestrate_automation` crea la tarea, abre su tarjeta,
  Hermes planifica, despacha `automate` con `task_id`. Flash orquesta · Hermes planifica · bucle ejecuta.
- **Fase 3 — canvas (`desktop.js` + `widget.js`)**: ids de INSTANCIA (`navegador::<taskid>`) → N tarjetas del mismo
  widget base (código+datos de `navegador`, datos por `?q=<taskid>`); arrastrables/redimensionables (reusa el resize
  heredado); cerrar tarjeta → cierra pestaña; tarjetas de tarea NO se persisten (efímeras). `widget.js` pinta la
  tarjeta de tarea (estado, mini-navegador, feed, resultados, pregunta) además de la vista clásica.
- **Fase 4 — resultados ricos**: `extract_listings()` (raspado genérico title/price/url/image) + `summarize_results()`
  (modelo barato → mejores + conclusión) → `task.results` → tarjeta con fotos/precio/enlace. Validado en Wallapop
  (extrae 14, rankea e ignora ruido).
- **Fase 5 — confirm-gate + Q&A por voz**: antes de una acción IRREVERSIBLE (`_DANGER_RE`) la tarea PARA y pide OK
  (feed+voz, timeout→no ejecuta); `answer_web_task` enruta la respuesta del operador a la tarea que espera (sirve
  también a "me falta el precio/los metros"). El prompt del flash inyecta las tareas en curso + cuál espera.

**Estado:** núcleo (paralelismo + tarjetas + resultados + confirm-gate) construido y validado por backend. Pendiente:
prueba en vivo por VOZ de varias tarjetas simultáneas (mic); afinar convergencia del bucle en webs complejas (el
modelo barato divaga con los filtros de Wallapop — tuning de snapshot/prompt); imágenes externas en la tarjeta
sujetas al CSP del front.

## MOTOR DE ESTUDIO — orquestación barata en tokens (TASK 1, plan 2026-07-08, PENDIENTE)

Petición del operador: un estudio ("analiza los 50 mejores anuncios, mira cada ficha, saca características, valora,
investiga marcas/motos, busca en internet, guarda el estudio y al final dime los 3 mejores") gasta MUCHOS tokens si
cada paso usa un modelo externo de pago. No hay prisa → es una tarea SECUENCIAL. Objetivo: ahorrar tokens + aislar
la tarea con su propia memoria.

**Decisión de arquitectura (recomendada):**
- **El orquestador del estudio vive en la TAREA del navegador (su bucle), NO en Hermes.** Hermes es Opus-class, de
  pago y serializa con la voz → NO debe conducir cada paso. Ya tenemos aislamiento por tarea con estado propio
  (`tasks.py`) = la "memoria propia" pedida; se extiende a un ESTUDIO estructurado (hallazgos acumulados, persistido
  a disco porque un estudio es largo).
- **Escalonado de modelos para ahorrar (el núcleo):**
  - Parsear página / extraer características de una ficha → **modelo LOCAL** (Ollama, gratis) o raspado DOM puro
    (sin modelo). Trabajo en bloque, simple → gratis.
  - Valoración por ficha (¿buen precio? notas) → **modelo LOCAL** (gratis).
  - Investigar marca/moto en internet (si hace falta) → fetch + resumen **LOCAL** (gratis).
  - **"Cuál es la mejor" FINAL** → UNA llamada a un modelo LISTO (Sonnet/Opus vía AIMLAPI, o Hermes) sobre los
    análisis individuales ya compilados. UNA llamada de pago, no N.
- **Cómo corre**: secuencial, sin prisa. Por cada ficha: abrir → parsear (local) → valorar (local) → GUARDAR en el
  estudio → cerrar pestaña (ya hecho, TASK 3) → siguiente. Feed: "analizando 3/20…". Al final: modelo listo → ranking
  → resultados en la tarjeta + voz.
- **Hermes**: opcional para PLANIFICAR el estudio y/o el juicio FINAL; NO el trabajo por-paso. Lever aparte: que
  Hermes enrute SU trabajo barato (parsings) al modelo LOCAL en vez del LLM por defecto (config del lado de Hermes).
- **Reusa lo existente** (TaskBrowser + bucle) — el "agente de estudio" es delgado (un driver), no un framework.

**Milestone a construir:** tipo de tarea `study`; recolectar URLs de fichas (extract_listings) → por cada una
(secuencial) abrir/parsear-local/valorar-local/guardar/cerrar → juicio final con modelo listo; estado del estudio
persistido por tarea; cap N + ritmo pausado. Config: `NAVEGADOR_STUDY_MODEL` (local) + `_model_strong()` (juicio).
**Decisiones pendientes del operador:** (a) modelo local del bulk (qwen 14b / 3b); (b) modelo listo del juicio final
(Sonnet vía AIMLAPI / Hermes); (c) si Hermes debe enrutar su trabajo barato al local (tarea de config de Hermes).

## TASK 2/3 (hechos 2026-07-08)
- **Headless por defecto** (no roba el foco/cursor del operador; bastan las capturas). Visible opt-in
  (`navegador_visible`/`ZAELAR_NAVEGADOR_VISIBLE=1`). Quitados los `bring_to_front`. Tarjeta más ancha (560px).
  Pendiente UI: botón headless/visible bajo el control del navegador (hoy configurable por store/env).
- **No acumular pestañas** (`_reap_popups`): tras cada clic cierra popups y absorbe la ficha en la misma pestaña.

## AUTENTICACIÓN en páginas (login) — CONSTRUIDO (2026-07-08)

Implementado: `authenticate_web(site)` [voz] / acción `authenticate` → relanza el navegador VISIBLE en la web de
login (override runtime `_visible_override`), tarjeta con botón «Ya he iniciado sesión»; el operador entra a mano en
la ventana real. `auth_done` (botón o voz "ya estoy dentro" vía `answer_web_task`) → vuelve a HEADLESS; la sesión
queda en el PERFIL PERSISTENTE → tareas siguientes autenticadas (su cuenta, su ubicación, contactar vendedores).
**NO se heredan cookies del Chrome del sistema** (cifradas por Keychain, frágil): se usa nuestro perfil.
Verificado: cookie PERSISTENTE + localStorage sobreviven headed→headless (lo que usan los logins reales). Caveat:
las cookies de SESIÓN pura (sin expiración) no persisten al cerrar — caso menos común; si algún sitio lo necesita,
mantener la ventana viva o "continue where you left off" (futuro).

### Plan original (referencia)

Problema: en headless el operador no puede loguearse en webs que lo requieren (LinkedIn, banca…). Buena noticia:
**ya tenemos perfil PERSISTENTE** (`widgets/_data/navegador/profile/`) = tarro de cookies/sesión en disco → NO hay
que capturar/inyectar cookies a mano. Flujo:
- Acción `authenticate(url)`: **relanza el navegador VISIBLE** (headed) en la página de login → ventana real en el
  Mac; el operador se loguea a mano; la sesión se guarda sola en el perfil; se vuelve a **headless** y las tareas
  reutilizan la sesión (mismo perfil).
- **Detección automática de muros de login**: si una tarea topa con login, PAUSA (como el confirm-gate) y pide por
  voz "necesito que te loguees en X" → abre visible → el operador entra → reanuda (misma Q&A por voz).
- Matiz: alternar headless↔visible exige RELANZAR Chromium (no en caliente); el perfil persistente lo hace
  transparente. Cuidar no interrumpir tareas en curso (hacerlo sin tareas activas o avisar).
- Decisión pendiente del operador: construir ahora o junto al motor de estudio (martes).

## Próximos pasos

- **M3 — visión fallback:** cuando el agente emite `need_vision`, adjuntar la captura (los modelos Claude son
  multimodales) para desatascar tareas que el DOM no resuelve; controlar coste (imagen solo en ese paso).
- Afinar el snapshot (set-of-marks, coordenadas) y el prompt para tareas complejas reales (Wallapop con filtros).
- Cerrar Chromium por inactividad para liberar RAM (hoy queda vivo tras el primer uso).
- Reflejar el automatizador en el diagrama vivo `architecture.html` (pendiente; se hará junto al M3 para no
  re-tocar el SVG en cada iteración).
- Evaluar migrar `mensajeria` al kind `backed` (dueño único por buzón — elimina la carrera de dos escritores).
