#
# perms.py — traducción del PERFIL DE PERMISOS por-cluster (V2-076) al catálogo de acciones del FlashBrain y al
# contexto de escalada. Es la pieza de acoplamiento que hace que el turno de cluster REUSE los túneles del FlashBrain
# (router.TOOLS + escalate + dispatch) SIN duplicar nada: el perfil solo decide QUÉ subconjunto del catálogo se
# ofrece y con qué ACOTACIÓN se escala. Permiso cero → conjunto vacío → el turno de cluster se queda EXACTAMENTE como
# hoy (bare complete, sin tools) = cero regresión.
#
# Vocabulario cerrado; un permiso solo AMPLÍA lo que el OPERADOR concede a ese cluster, nunca lo que el peer pide.
#

# Qué tools del catálogo del FlashBrain (router.TOOLS) puede ofrecerse un turno de cluster, según el perfil. El
# canal agente-agente NO recibe tools de canvas/música/memoria-del-operador — solo la VÍA A WORKER (escalate) y, si
# hay workers permitidos, la búsqueda en turno. La ejecución real la acota `dispatch` (worker dev sandboxeado).
def gated_tool_names(perms: dict) -> set[str]:
    perms = perms or {}
    names: set[str] = set()
    if perms.get("code") or perms.get("workers"):
        names.add("escalate_to_slowbrain")          # el GATEWAY a un brainworker acotado
    if perms.get("workers"):
        names.add("web_search")                      # investigación en turno (barata, sin worker)
    return names


def any_capability(perms: dict) -> bool:
    """¿El cluster tiene ALGÚN permiso que justifique ofrecer catálogo? Si no, el turno se queda como hoy (sin tools)."""
    return bool(gated_tool_names(perms))


def gate_dev_by_objective(ctx: dict, objective: str | None) -> dict:
    """Guard de PROPIEDAD DEL OBJETIVO (auditoría 2026-07-26): el permiso `code` concedido a un cluster no basta
    por sí solo para disparar un dev-worker — hace falta que el OPERADOR haya fijado el objetivo de la relación
    (`capsule.objective`, que el peer nunca puede escribir). Sin objetivo, un peer con permiso `code` podría
    dirigir unilateralmente la colaboración hacia cualquier tarea de código dentro del repo autorizado. Devuelve
    el MISMO dict si no hay nada que degradar (permite comparar por identidad en el llamador)."""
    if ctx and ctx.get("dev") and not (objective or "").strip():
        return dict(ctx, dev=False)
    return ctx


def escalate_context(cluster: str, perms: dict) -> dict:
    """Contexto que viaja con una escalada ORIGINADA en un turno de cluster. NUNCA `trusted=True` (no es el operador):
    lleva las capacidades ACOTADAS que el perfil concede, para que `dispatch` monte un worker dev sandboxeado con el
    alcance justo (código sí/no, repo autorizado, ejecutar sí/no, deploy sí/no)."""
    perms = perms or {}
    return {
        "src": "cluster",
        "cluster": cluster,
        "trusted": False,                            # una escalada de cluster jamás hereda la confianza del operador
        "dev": bool(perms.get("code")),              # habilita el worker dev acotado (código + git al repo autorizado)
        "repo": perms.get("repo"),                   # git push SOLO a este repo
        "execute": bool(perms.get("execute")),       # ejecutar en el sandbox (Parte B)
        "deploy": bool(perms.get("deploy")),
    }
