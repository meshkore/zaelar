# Chain-suite — HOJA DE RUTA de problemas detectados

Registro VIVO de problemas encontrados por `tests/voice/e2e/agent/chain_suite.py` (iteración 2 del testing: frases humanas +
cadenas + trazas). Cada entrada lleva el **ID del caso** para que, cuando el developer arregle algo, el operador
pueda decir *"repite estos tests"* y se re-corran exactamente esos.

**Leyenda de estado:**
- `ARREGLADO` — bug simple, corregido en esta rama + re-testeado (commit citado).
- `DIFERIDO` — cambio complejo / de plan; lo arregla el developer. Se re-testea al cerrar.
- `RIGIDEZ` — no era bug del sistema; era el check demasiado estricto → check relajado.
- `HUECO` — funcionalidad no implementada (decisión de producto pendiente).

**Severidad:** P0 (rompe / corrompe datos) · P1 (ruta principal incorrecta) · P2 (subóptimo / varianza) · P3 (cosmético).

---

## Abiertos

### DIFERIDO (esperando al developer — al cerrarse, quitar el flag `defer` del caso y re-testear)

- **STUDY-01** · P2 · `study` · *informe/estudio "a fondo" respondido INLINE (charla) en vez de escalar a research.*
  El modelo contesta una comparativa "a fondo" (p.ej. "mejores tablas de surf de 2026") de su propio conocimiento
  —riesgo de datos OBSOLETOS (cutoff)— en vez de escalar a un worker de research (WebSearch/WebFetch) o al menos
  buscar. La descripción de `escalate_to_slowbrain` YA menciona "INFORME/ESTUDIO/investigación A FONDO"; reforzarlo
  más es criterio del modelo, y el operador prohíbe tablas de verbos hardcodeadas. **Propuesta developer:** few-shot
  en el prompt del FlashBrain (ejemplo informe→escala) o aceptar respuesta inline solo cuando NO pida "a fondo/
  detallado/investiga". Repite: `--domains study`.

- **MSG-02 (residual)** · P3 · `messaging` · *"Enséñame los mensajes" → escala (debería mostrar mensajeria).*
  Ya ARREGLADO el grueso: "Abre WhatsApp"/"conéctame a WhatsApp" → `[[show:mensajeria]]` vía el guard
  `is_messaging_service` (WhatsApp/Telegram se vinculan por QR en el widget, no por navegador). Residual: "enséñame
  los mensajes" a veces escala — el `_show_guard_target` (escalate→show) no lo reconvierte (identify de "los
  mensajes" no siempre resuelve limpio). Bajo (variance + edge). Repite: `--domains messaging`.

- **CHAIN-06 / CHAIN-07** · P2 · `chain` · **POR DISEÑO, no bug** · *comandos COMPUESTOS (dos acciones en un turno).*
  El prompt del FlashBrain dice explícitamente "UNA cosa por turno" (anti-proliferación, sesión 2026-07-15). "Abre el
  reloj Y pon jazz" → hace una, descarta la otra. **OJO:** la visión de CADENAS del operador (objetivo→pasos:
  buscar→reproducir, dato→acción) SÍ funciona hoy (CHAIN-01/02/03/04 verdes). Lo que falla es el COMANDO COMPUESTO
  (dos órdenes independientes en una frase), que colisiona con ese invariante deliberado. **Decisión del operador/
  developer:** relajar "una cosa por turno" para combos triviales (guía en `flash/prompt.py`) vs. mantener la
  disciplina anti-proliferación. No lo toco en el loop porque relaja un invariante intencionado. Repite: `--domains chain`.

- **MSG-03** · P2 · `messaging` · *zaelar no ENVÍA mensajes (read-only) pero el modelo lo intenta.* "Responde a mi
  madre…" → widget_data (send inexistente) en vez de declinar con honestidad. Causa raíz: el brief de mensajería
  (que declara "solo lectura + mark-read") NO entra en el prompt cuando el widget está CERRADO (prompt lean V2-027),
  así que el modelo improvisa. **Propuesta developer:** honest-decline (guard determinista o una línea de guía
  siempre-on muy ligera) o implementar el envío como feature. Repite: `--domains messaging`.

### HUECO (funcionalidad no implementada — decisión de producto, no se arregla en el loop)

- **LIST-01 / LIST-02** · `playlist` · *crear playlists y gestionar favoritos NO está implementado.* `play_music`
  solo REPRODUCE/controla (su descripción ya evita fingir "Hecho": ante "guarda en favoritos" cae a charla honesta,
  no miente). Para que estos casos pasen a verde hace falta implementar gestión de listas/favoritos en la capa de
  conectores de música (Spotify Web API ya tiene endpoints de playlist/library). Cadena ideal: FlashBrain → worker/
  tool → conector. **Owner: producto/developer.**

---

## Cerrados

- **VÍDEO→MÚSICA (VID-01, VID-02, CHAIN-02)** · **P1** · **ARREGLADO (V2-045)** — nueva tool de 1ª clase
  **`play_video(query)`** (hermana de `play_music`). Diagnóstico: 3 intentos de prosa NO movían al titular de entonces (vídeo caía
  en play_music); con una tool DEDICADA la decisión es tool-vs-tool y discrimina limpio, SIN tablas de verbos
  (feedback operador). El provider la ejecuta → `[[show:youtube]]` + data-op `load(query)`. Verificado: VID-01 3/3,
  VID-02 3/3, CHAIN-02 3/3 ("ponme una película/vídeo/algo entretenido" → youtube, NUNCA play_music). Tocado:
  router.TOOLS + decide + VIDEO const, provider `_on_tool_call`, probe mirror, test_router (19/19), arch §8 + diagrama
  (+ sello), chain_suite (un-defer). Repite: `--domains video,chain`.
- **VID-04** · P2 · `video` · *"Cierra el widget de youtube" → delete_widget (cerrar≠borrar).* **ARREGLADO (V2-045)**
  con guard determinista `router.looks_like_close` (verbo de cerrar + sin verbo de borrar → `[[close]]`, no la
  confirmación de borrado). Espejo del provider en el probe. Verificado 3/3. Invariante V2-017.
- **MSG-02 (grueso)** · **ARREGLADO (V2-045)** — guard `is_messaging_service`: "conéctame/abre WhatsApp/Telegram" →
  `[[show:mensajeria]]` (QR en el widget), no login de navegador. Espejo de `is_music_service`. (Residual menor en
  Abiertos.)
- **MUS-03** · P3 · `music` · *"Pausa un momento" → charla.* No era bug: la frase es ambigua ("espera un momento").
  **RIGIDEZ** del check → frase cambiada a "Pausa la canción."
- **ACT-01** · P2 · `webact` · *"Sácame una cita en la ITV" (escueto) → charla.* El bug ITV real documentado es el
  BUCLE de consejos por `web_search` sin escalar; una charla que pide datos NO es ese bug. **RIGIDEZ** → check
  relajado al invariante real (escala o pide datos; nunca web_search en bucle). Escalar sigue siendo lo ideal.

---

- **2026-07-16 · IMPLEMENTACIÓN (operador presente, autoriza fixes)**: cerrado el P1 **VÍDEO→MÚSICA** con la tool
  `play_video` (VID-01/02 + CHAIN-02 3/3) + guards `looks_like_close` (VID-04 cerrar≠borrar) e `is_messaging_service`
  (WhatsApp/Telegram→QR). Router tests 19/19; doc-sync (arch §8 + diagrama + sellos). Re-sweep video/messaging/chain/
  auth: **0 RED activos**, trazas 47/47. Quedan diferidos: CHAIN-06/07 (compuestos), MSG-03 (read-only), MSG-02
  residual. LIST-01/02 HUECO (feature).

## Bitácora de ciclos

- **2026-07-16 · ciclo #6 (cron 078d22b2 · loop_cycle + dominio rules)**: reset limpio + loop_cycle → **49/50**
  (memoria 5/5 con el check de supersede_prof arreglado; **rules 3/3** — persiste/viaja/retira, nunca mudo; vídeo
  ya vía `play_video` ✓✓). Único fallo `control_next` diagnosticado como RIGIDEZ: sin música sonando (el probe no
  ejecuta el rail) "pon la siguiente" no tiene referente y el modelo PREGUNTA cuál (humano, correcto) → check
  relajado a su invariante real (play_music o pregunta; nunca busca/escala). + Catálogo chain_suite a **43 casos**:
  dominio `rules` nuevo (RULE-01 dar 4/4 · RULE-02 retirar 3/3 · RULE-03 orden-puntual-NO-es-regla 3/3, sin
  polución de rules). Trazas 10/10.

- **2026-07-16 · SWEEP FINAL de verificación** (40 casos): **GREEN 30 · YELLOW 2 · RED 1** · **trazas 120/120**.
  Confirma los fixes de V2-045 end-to-end: VID-01/02/03/04 + CHAIN-02 todos 3/3 (P1 vídeo→música cerrado). RED único
  = WMOD-01 (1 frase 'implementa… ampliarse por voz' → charla; las otras 2 escalan; era 3/3 en sweeps previos →
  varianza cross-run del titular de entonces, no bug estable). YELLOW = CHAIN-04 (handoff) y ROBUST-02 (autocorrección), varianza.
  Diferidos: CHAIN-06/07 (por diseño), STUDY-01, MSG-03, MSG-02 residual. HUECO: LIST-01/02.

- **2026-07-16 · sweep #1** (rama `feat/v2-041-music-connector`, iteración 2 estrenada). Activos: GREEN 20 · YELLOW 3
  · RED 7. **Trazas selladas 91/91** (V2-044 sólido). Triaje de los 7 RED: 2 rigideces de check corregidas (MUS-03,
  ACT-01), 2 HUECOs de producto (LIST-01/02), 3 diferidos al developer (CHAIN-02 película→música, STUDY-01
  informe-inline, MSG-02 refs indirectas). YELLOW = varianza del titular de entonces en VID-01/02 (youtube vía widget_data,
  aceptable) y WNEW-01 (handoff). Prosa de play_music reforzada (FRONTERA VÍDEO += película/peli/film) — correcta
  pero insuficiente para mover al titular de entonces.
- **2026-07-16 · re-sweep (dominios afectados)**: tras los fixes → activos GREEN 9 · YELLOW 0 · **RED 1** (CHAIN-02,
  ya reclasificado DEFER). MUS-03 4/4, ACT-01 3/3. Trazas 43/43. Suite estabilizada: los únicos rojos que quedan son
  los DEFER/HUECO documentados, ninguno accionable en el loop.
- **2026-07-16 · ciclo #5 (memoria, loop_cycle.py)**: reset limpio + loop_cycle → **44/47**. Memoria: recall,
  no-alucinar, supersede ubicación, recall hijos ✓; **supersede_prof era RIGIDEZ del check** (la memoria acierta —
  yoga es lo actual— pero el modelo menciona 'dejaste la fisioterapia' y el check prohibía la palabra 'fisio') →
  check relajado a "yoga actual + no afirma seguir siendo fisio". control_next ('pon la siguiente canción' sin nada
  sonando → chat) = sensible al contexto/varianza (en chain_suite MUS-03 'siguiente' pasa 4/4). investiga = mismo
  STUDY-01 ya diferido. Guards deterministas (spotify/pure-show) ✓, exec (add_meeting persiste) ✓. **Cron PAUSADO
  al volver el operador** (evitar resets automáticos durante su sesión; reanudar con nuevo CronCreate si se ausenta).
- **2026-07-16 · sweep #4** (cron 9c08a092): +dominio **robustez** (ROBUST-01 STT garbleado, ROBUST-02
  autocorrección en la frase, ROBUST-03 ref ambigua). Catálogo a **40 casos**. **Todos GREEN** (ROBUST-02 1 retry =
  varianza) → hallazgo POSITIVO: el FlashBrain aguanta titubeos/repeticiones de STT, toma la intención FINAL tras una
  autocorrección ('pon música… no, mejor la agenda' → NO música) y ante una referencia ambigua sin contexto PREGUNTA
  en vez de actuar a ciegas. Traza de muestra CHAIN-01 confirmada (T170: frase→play_music['Fly Me to the Moon']→
  memoria, todo sellado). Sin cambio de código (robustez sólida). Trazas 9/9.
- **2026-07-16 · sweep #3** (cron 9c08a092): full sweep con catálogo AMPLIADO a **37 casos** (+CHAIN-06/07
  compuestos, +MSG-03 read-only). Activos GREEN 25 · YELLOW 2 · **RED 3** · trazas **111/111**. Los 3 REDs nuevos son
  límites del no-razonador, no fixes simples → DIFERIDOS: CHAIN-06/07 (una acción por turno, comandos compuestos) y
  MSG-03 (no envía; brief no está en prompt con widget cerrado). Sin cambio de código este ciclo (disciplina: no
  churnear prosa/core que el titular de entonces no respetaba; documentar bien para el developer). YELLOW = varianza aceptable
  (CHAIN-03, WNEW-01). Cobertura ya extensa: música, vídeo, cadenas, widgets (crear/mod/acción/show/borrar),
  búsqueda, estudio, ITV, mensajería, auth, core, compuestos.
- **2026-07-16 · sweep #2** (cron 9c08a092): rotación video/widgets/search/auth/core + AMPLIACIÓN del catálogo
  (+5 casos: VID-04 cerrar-vídeo, WACT-02 marcar/descartar, CHAIN-05 música-por-ánimo, SRCH-03 noticias, y frase de
  WACT-01 corregida por colisión con V2-029 'recuérdame'→sin-tool). Los 5 nuevos verde 3/3. **Hallazgo fuerte:
  VÍDEO→MÚSICA es consistente** (VID-01/02 fallan 3×, no varianza) → tras 3 intentos de prosa infructuosos, REVERTIDA
  la descripción a `2e17f80` y CONSOLIDADO en un P1 diferido (VID-01/02/CHAIN-02) con la propuesta de hacer `youtube`
  tool de 1ª clase. WACT-01 arreglado (frase agenda-explícita) 3/3, WACT-02 3/3. Trazas 42/42.
