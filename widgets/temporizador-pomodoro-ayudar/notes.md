# notes — temporizador-pomodoro-ayudar

- 2026-07-17 (creación): temporizador Pomodoro para gestionar bloques de trabajo/descanso. Fases: **concentración
  25 min → descanso corto 5 min**, y **descanso largo 15 min tras cada 4 pomodoros**. Cuenta atrás circular (SVG
  inline, sin libs), contador de pomodoros completados y 4 puntos que muestran el progreso hacia el descanso largo.
  Acciones (data-op del FlashBrain, todas reversibles, sin payload): `start` (iniciar/reanudar), `pause`, `reset`
  (reinicia la fase actual a su duración completa), `skip` (salta a la fase siguiente). Al salir de una fase de
  concentración se cuenta un pomodoro.
- Diseño de estado: se persiste la SESIÓN, no el segundo a segundo — `ends_at` (epoch) marca el fin de la fase en
  marcha y `remaining` se deriva; al pausar se congela `remaining`. La cuenta atrás visible la lleva `widget.js`
  con un `setInterval` LOCAL (cosmético, no es polling) y, al llegar a 0 en pantalla, dispara `skip` una sola vez.
- Background `every:30s` + `tick(ctx)`: liquida una fase que venció con la tarjeta cerrada y, SOLO en marcha,
  vuelca el estado a memoria (`slot=temporizador-pomodoro-ayudar:estado`) para que una pregunta por voz
  («¿cuánto queda del pomodoro?») responda con datos frescos aunque no se haya abierto el widget.
- Constraint: duraciones fijas 25/5/15 y descanso largo cada 4 (técnica Pomodoro clásica) — no regresar a otro
  esquema salvo que el operador lo pida.
