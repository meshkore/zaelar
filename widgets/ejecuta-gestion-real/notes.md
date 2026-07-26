- Encargo original: "ejecuta la gestión real de la aparición del nuevo agente en el sistema, asegurando que se
  registre y actualice correctamente en la base de datos y no solo en el widget visual" — por eso TODA alta/estado/
  baja de agente pasa por `store.load/save` (widgets/_data/ejecuta-gestion-real/state.json), nunca solo estado en
  memoria del DOM/widget.js. Acciones: `register_agent` (alta), `update_status` (activo/inactivo/error, ciclo por
  clic en el punto de color), `remove_agent` (confirm:true, irreversible). `ref_index()` expone los agentes vivos
  para que el cerebro resuelva `agentId` por nombre hablado.
- **FIX 2026-07-26 (auditoría, hallazgo P2 — solapamiento con `ejecuta-sistema-real`):** este widget y
  `ejecuta-sistema-real` se generaron por separado para, en esencia, el mismo encargo ("da de alta un agente
  nuevo") — mismo concepto, dos stores SIN sincronizar. Auditado: NO se fusionan (fusionar arriesgaría perder
  datos de producción de cualquiera de los dos stores sin que el operador lo decidiera explícitamente). En su
  lugar se DIFERENCIARON los `whenToUse`/keywords para que el enrutado no sea ambiguo: **este** widget es la vista
  de GESTIÓN de agentes ya conocidos (estado/consulta/baja) + un alta RÁPIDA manual sin verificación;
  `ejecuta-sistema-real` es el flujo CANÓNICO para dar de alta un agente NUEVO (con verificación paso a paso y
  reintento). Si en el futuro se decide fusionarlos de verdad, hace falta migrar ambos stores a uno solo con el
  operador delante.
