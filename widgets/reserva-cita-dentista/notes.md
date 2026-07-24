- Pedido inicial: reservar la cita con el dentista para mañana a las 17:00 "en el sistema real de agenda" y
  reflejarla en el widget. Diseño elegido por aislamiento (widgets/AGENTS.md, "no cross-widget calls"): este
  widget guarda SU PROPIA reserva (título/fecha/hora/estado) en su store aislado — es la tarjeta de
  confirmación de este trámite concreto, NO reimplementa la agenda. El asiento real en la agenda lo pone el
  cerebro llamando TAMBIÉN a `agenda.add_meeting` (ya existe, `widgets/agenda/manifest.json`) — composición
  brain-mediated, no una llamada directa entre widgets. Si en el futuro se pide "que la cita del dentista
  aparezca también en el widget de agenda", la solución es que el cerebro dispare ambas acciones (esta +
  `add_meeting`), no acoplar el código de los dos widgets.
- `reservar` acepta fecha/hora en lenguaje natural (mañana, a las cinco) igual que `agenda.add_meeting`.
  `cancelar` lleva `confirm:true` porque anula un compromiso real (dentista), no un simple descarte de UI.
- 2026-07-22: petición "reserva la cita para mañana a las 17:00 en el sistema real de agenda y actualiza el
  widget para reflejar la confirmación" — SIN cambio de código: `reservar` con `{date:"mañana",time:"17:00"}`
  ya resuelve fecha/hora reales y pone `status:"confirmed"`, y `widget.js` ya pinta la tarjeta confirmada. El
  asiento real en la agenda (`agenda.add_meeting`) lo dispara el cerebro aparte (ver composición brain-mediated
  arriba); ejecutar la acción es un dato en runtime, no un edit de este código.
