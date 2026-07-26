- Creado (2026-07-24): el operador pidió que la incorporación de un agente nuevo se EJECUTE de verdad en el
  sistema, no solo que el cerebro rápido actualice el widget local sin efecto real — motivo: FlashBrain había
  modificado un widget dejando el dato como si el alta hubiera ocurrido, sin ninguna acción real detrás. Este
  widget ejecuta `onboard_agent` con pasos que tienen efecto PERSISTENTE y VERIFICABLE en disco (crear
  registro → releerlo para comprobar integridad → activar), nunca una animación de mentira con temporizadores.
  Si un paso falla el agente queda `incompleto` y se puede reintentar (`retry`); `remove_agent` da de baja y
  pide confirmación (irreversible-ish). No transient: debe quedarse en pantalla como registro consultable.
- (2026-07-25): añadido `tick()` + `"background":"1m"` — la acción pendiente (agente en estado `incompleto`)
  se reintenta sola en background hasta completarse de verdad en el sistema (sin esperar a que el operador pulse
  "Reintentar"), y al completarse vuelca un aviso a memoria (`slot=ejecuta-sistema-real:<id>`) vía `ctx.remember`
  para que una pregunta por voz refleje el resultado real aunque el widget no se haya abierto.
- (2026-07-25): gap encontrado — un alta que Manolo pidió y el cerebro rápido no procesó de verdad quedaba
  ejecutada+visible en la tarjeta al instante (`apply_action` es stdlib-only, sin acceso a memoria) pero SIN
  volcarse nunca a memoria salvo que hubiera pasado antes por `incompleto`→reintento. `tick()` ahora también
  revisa cualquier agente `activo` sin `remembered` (no solo los que veníamos reintentando) y lo vuelca en el
  siguiente ciclo — así toda gestión real ejecutada, inmediata o recuperada, queda en memoria como máximo 1m
  después, sin exponer voz/memoria síncrona en `apply_action`.
- **FIX 2026-07-26 (auditoría, hallazgo P2 — solapamiento con `ejecuta-gestion-real`):** ambos widgets nacieron
  del mismo concepto ("da de alta un agente") en sesiones separadas — sus keywords/`whenToUse` se pisaban y el
  enrutado podía coger cualquiera de los dos. NO se fusionaron (stores separados, sin decisión del operador de
  por medio para migrar datos). Diferenciados: **este** widget queda como el flujo CANÓNICO de alta de un agente
  NUEVO (con verificación real paso a paso + reintento en background); `ejecuta-gestion-real` es la vista de
  GESTIÓN de agentes ya conocidos (cambiar estado/consultar/eliminar), con un alta rápida manual como opción
  secundaria sin la verificación de aquí.
