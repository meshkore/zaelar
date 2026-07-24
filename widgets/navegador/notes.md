# navegador — notas de contexto

Navegador web dentro de zaelar. **Primer widget `kind:"backed"`** (INI-016) — estrena la infraestructura de
widget-apps con backend vivo diseñada en `zaelar-modules.md §Widget-apps`.

## Por qué un backend (no un iframe)
Casi ninguna web se deja incrustar en un `<iframe>` (X-Frame-Options / CSP `frame-ancestors`): Google, Wallapop,
la RAE, tiendas… Por eso el navegador REAL vive en `owner.py` = un **Chromium headless (Playwright)** en el
servidor. Navega de verdad, **fotografía** la viewport (1280×800) y el widget muestra esa captura. Los
clics/scroll del operador se mapean a coordenadas de página → Chromium → nueva captura.

## Piezas
- `owner.py` — backend vivo. **Único escritor** de `_data/navegador/` (state.json + `shot.png`). Arranque
  perezoso: Chromium se lanza en la primera orden. Órdenes: `open/search/youtube/back/forward/reload/scroll/
  click/type/press`. Lo gobierna `widgets/supervisor.py` (buzón + restart con backoff + desactivación tras N
  fallos). Emite observabilidad `kind:"navegador"` (navigate/screenshot/youtube/click/nav_error…) a `/debug`.
- `data.py` — **solo lectura** (`view_data`). `apply_action` es red de seguridad: en un backed widget el host
  encola en el buzón del owner ANTES de tocar data.py (`server_api._route_backed`).
- `widget.js` — barra de direcciones + atrás/adelante/recargar, viewport (captura clicable con scroll, o
  reproductor **YouTube embed** cuando `mode==="youtube"`), y estado inicial con atajos.
- `manifest.json` — `kind:"backed"`, `backend.owner`. Navegación (`open/search/youtube/back/forward/reload/
  scroll`) es `safe:true` → la capa rápida de voz la conduce. `click/type/press` es `safe:false` → automatización
  dentro de una web (rellenar formularios) la escala Hermes.

## YouTube
Excepción: una captura no reproduce vídeo/audio → el owner resuelve el `videoId` (raspa el HTML de resultados,
sin API key) y el widget monta el reproductor embed real (`youtube-nocookie`). `open` detecta URLs de YouTube.

## Autenticación — sesiones con la cuenta del operador (INI-016)
Muchas tareas necesitan la cuenta del operador (sacar una API key en Google Cloud, comprar en Wallapop, leer un
mail). El Chromium headless arranca **sin sesión**. Solución (perfil propio + login manual una vez, NO copiar las
cookies del Chrome del sistema — cifradas por el Keychain, frágiles):

- **Detección** (`agent.py::_looks_like_login`): DETERMINISTA (URL de login conocida + campo password en el
  snapshot) **antes** de dejar actuar al modelo. El bucle **NUNCA teclea credenciales inventadas** (bug 2026-07-10:
  tecleó `user@gmail.com` en el login de Google y giró en círculos). También hay la acción `need_login` por si el
  modelo detecta un login que la URL no delata.
- **Ventana real** (`owner.py::_begin_login`→`_authenticate`): relanza el MISMO Chromium **visible** en la página
  de login (`_visible_override`), la tarjeta muestra «Ya he iniciado sesión», y avisa por voz. El operador entra a
  mano → la sesión (cookies) se guarda SOLA en el **perfil persistente** (`_data/navegador/profile/`).
- **Vuelta** (`_auth_done`, por el botón o el tool de voz `login_done`): **sonda post-login** (¿la sesión cuajó o
  rebota al login?), vuelve a headless y **reanuda automático** la(s) tarea(s) pausada(s).
- **Bajo control**: una sola ventana → un login a la vez (pausa+reanuda las otras tareas, porque `stop()` mata sus
  pestañas); **timeout 10 min** sin terminar → recordatorio, nunca mata la tarea; **crash/reinicio** → miga durable
  en memoria (`auth_memory.checkpoint_auth_pending`) → al arrancar recuerda «dejaste el login de X a medias».
- **Memoria** (`auth_memory.py`, vía fachada `memory.write`/`set_state`): el SECRETO (cookies) NUNCA entra en
  memoria (vive en el perfil, cifrado por el SO); solo el **hecho** de la sesión (`record_session_established`,
  `slot=navegador.session.<sitio>` → supersede) y el **checkpoint** recuperable. Calca `widgets/lifecycle.py`
  (ALTA) y `nucleo/reset.py` (congelar→registrar).
- **FlashBrain**: tools `authenticate_web(site)` (abre el login a petición: «conéctame a Wallapop») y `login_done`
  («ya estoy dentro»). Operator-only por construcción (el reasoner de cluster no tiene tools). Confirm-gate de
  acciones irreversibles (comprar/pagar/publicar) sigue en `nucleo/danger.py`.

## Estado / futuro
- v0.1.0: abrir web, buscar en Google, reproducir YouTube, clic/scroll sobre la captura, atrás/adelante. Base
  para la visión: **conducir la navegación por voz y automatizar** ("abre Wallapop y búscame una moto <5000€ de
  2020 para arriba") — se apoya en las acciones `click/type/press` + escalado a Hermes.
- Chromium queda vivo tras el primer uso (reabrir es instantáneo). Futuro: cerrar por inactividad para liberar
  RAM; navegación semántica ("haz clic en el segundo resultado") vía Hermes leyendo el DOM.
