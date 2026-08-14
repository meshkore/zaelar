#
# perms.py — translation of the per-cluster PERMISSION PROFILE (V2-076) into the FlashBrain action catalog and
# escalation context. This coupling piece lets the cluster turn REUSE the FlashBrain tunnels (router.TOOLS +
# escalate + dispatch) WITHOUT duplicating anything: the profile only decides WHICH subset of the catalog is offered
# and with which BOUNDS escalation runs. Zero permission -> empty set -> the cluster turn remains EXACTLY as it is
# today (bare complete, no tools) = zero regression.
#
# Closed vocabulary; a permission only EXPANDS what the OPERATOR grants that cluster, never what the peer requests.
#

# Which tools from the FlashBrain catalog (router.TOOLS) may be offered to a cluster turn, according to the profile.
# The agent-to-agent channel does NOT receive canvas/music/operator-memory tools — only the PATH TO WORKER
# (escalate) and, if workers are allowed, in-turn search. Actual execution is bounded by `dispatch` (sandboxed dev
# worker).
def gated_tool_names(perms: dict) -> set[str]:
    perms = perms or {}
    names: set[str] = set()
    if perms.get("code") or perms.get("workers"):
        names.add("escalate_to_slowbrain")          # the GATEWAY to a bounded brainworker
    if perms.get("workers"):
        names.add("web_search")                      # in-turn research (cheap, no worker)
    return names


def any_capability(perms: dict) -> bool:
    """Does the cluster have ANY permission that justifies offering a catalog? If not, the turn stays tool-free."""
    return bool(gated_tool_names(perms))


def gate_dev_by_objective(ctx: dict, objective: str | None) -> dict:
    """OBJECTIVE OWNERSHIP guard (2026-07-26 audit): the `code` permission granted to a cluster is not enough by
    itself to trigger a dev-worker — the OPERATOR must have set the relationship objective (`capsule.objective`,
    which the peer can never write). Without an objective, a peer with `code` permission could unilaterally steer
    collaboration toward any code task inside the authorized repo. Returns the SAME dict if there is nothing to
    downgrade (allowing the caller to compare by identity)."""
    if ctx and ctx.get("dev") and not (objective or "").strip():
        return dict(ctx, dev=False)
    return ctx


def escalate_context(cluster: str, perms: dict) -> dict:
    """Context carried by an escalation ORIGINATED in a cluster turn. NEVER `trusted=True` (it is not the operator):
    carries the BOUNDED capabilities the profile grants, so `dispatch` can mount a sandboxed dev worker with the
    exact scope (code yes/no, authorized repo, execute yes/no, deploy yes/no)."""
    perms = perms or {}
    return {
        "src": "cluster",
        "cluster": cluster,
        "trusted": False,                            # a cluster escalation never inherits operator trust
        "dev": bool(perms.get("code")),              # enables the bounded dev worker (code + git to authorized repo)
        "repo": perms.get("repo"),                   # git push ONLY to this repo
        "execute": bool(perms.get("execute")),       # execute in the sandbox (Part B)
        "deploy": bool(perms.get("deploy")),
    }
