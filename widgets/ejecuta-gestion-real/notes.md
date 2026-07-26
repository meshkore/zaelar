- Encargo original: "ejecuta la gestión real de la aparición del nuevo agente en el sistema, asegurando que se
  registre y actualice correctamente en la base de datos y no solo en el widget visual" — por eso TODA alta/estado/
  baja de agente pasa por `store.load/save` (widgets/_data/ejecuta-gestion-real/state.json), nunca solo estado en
  memoria del DOM/widget.js. Acciones: `register_agent` (alta), `update_status` (activo/inactivo/error, ciclo por
  clic en el punto de color), `remove_agent` (confirm:true, irreversible). `ref_index()` expone los agentes vivos
  para que el cerebro resuelva `agentId` por nombre hablado.
