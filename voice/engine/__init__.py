"""zaelar LiveKit voice engine (INI-012).

Ported from voice-lab-2 (LiveKit Agents 1.6.4). Runs EMBEDDED in the zaelar web
server process via ``AgentServer(job_executor_type=JobExecutorType.THREAD)`` so
the voice job shares process state with the brain. See ``pipeline/agent.py``.
"""
