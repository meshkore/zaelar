#
# What the BRAIN needs to know about the MeshKore channel: the outbound tag protocol + live cluster status.
#
# Injected two ways:
#   • into the voice kickoff brief (voice/agent.py) so Hermes knows the protocol from turn one of a voice session;
#   • prepended to every off-pipeline cluster turn by the bridge (so it works even with no browser ever opened).
#
# COMPACT: re-sent every turn via history → keep terse. Tags + the few rules that matter.
PROTOCOL = """[CLUSTER MeshKore] Colaboras con otros agentes por clusters. Tags SILENCIOSAS (nunca se hablan):
  [[cluster.send:<cluster_name>]]{"to":"<peer_handle|*>","text":"…"}[[/cluster.send]] · [[cluster.done:<cluster_name>]] · [[cluster.disconnect:<cluster_name>]] · [[cluster.connect]]{json}[[/cluster.connect]]
IMPORTANTE: <cluster_name> es el nombre del cluster (ej: "arena") de la sección [Clusters right now] — NO es el handle del peer. El peer handle va en "to". Ej: [[cluster.send:arena]]{"to":"zalo","text":"mensaje"}[[/cluster.send]]
Texto FUERA de tags = para tu operador; para hablar al cluster DEBES envolverlo en [[cluster.send]]. TEXTO PLANO por defecto (nada de type/ack; para responder, otro mensaje; adjuntos: "media":[{"mime","url"}]). Al conectar, si hay peers abre con una propuesta concreta; si no, espera (te despierto al entrar uno). Al concluir, dilo y emite [[cluster.done]]."""


def for_brain() -> str:
    """Protocol + a one-line snapshot of current clusters, for the brain's context."""
    try:
        from connectors.meshkore import get_manager
        cs = get_manager().clusters()
    except Exception:
        cs = []
    if cs:
        # Cluster names AND peer handles are chosen on the untrusted channel but get rendered into the VOICE
        # kickoff brief, which runs with tools auto-approved. Neutralize every identity string so a crafted
        # handle can't forge a fence-close + fake [SECURITY] trailer inside that trusted context (audit V1).
        from connectors.meshkore.security import neutralize_identity as _ni
        lines = "; ".join(
            f"{_ni(c['name'])}: {'connected' if c['connected'] else 'offline'}, "
            f"peers online: {', '.join(_ni(h) for h in c['online']) or 'none'}" for c in cs)
        status = f"\n[Clusters right now] {lines}"
    else:
        status = "\n[Clusters right now] none connected."
    return PROTOCOL + status
