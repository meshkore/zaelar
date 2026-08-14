#
# triage_agent.py: the messaging widget TRIAGER (V2-008). In the v2 architecture, triage stops living in connectors
# and becomes a WIDGET AGENT: given a batch of incoming messages from any platform, already published on the bus as
# connector.msg, it decides whether each one deserves the operator's attention and whether it is addressed to the
# operator. Encapsulates the classification that previously lived loose in connectors/messaging (the design's loose
# "qwen2.5:3b").
#
# PRIVACY (hard invariant): triage runs with a LOCAL model by default (Ollama), so nothing personal leaves the
# machine. The classifier implementation (prompt + few-shot + defensive parsing) remains in
# connectors/messaging/triage.py as a STATELESS, platform-agnostic utility; this agent invokes it. Physically moving
# the file into the widget is deferred until burial (V2-009), by strangler-fig, because today's duo/hermes path still
# uses it. Using a CLOUD CodeAgent (Claude Code) for triage is an OPEN product decision that collides with this
# privacy invariant; see the V2-008 log.
#


async def classify(messages: list[dict], operator_name: str | None = None) -> list[dict]:
    """Triage a batch. Return the list enriched with {importante, dirigido_a_mi, urgencia, motivo}, aligned by
    index. Best-effort: on model failure, the classifier marks everything uncertain (fail-open toward the operator)
    and never raises."""
    from connectors.messaging import triage as _classifier
    return await _classifier.classify(messages, operator_name)
