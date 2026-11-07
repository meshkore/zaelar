"""V2-858 T549 — the deep-sleep phase that folds concept hubs meaning the same into one.

Memory imports no brain: the fold itself is deterministic and lives in `memory/concepts.py`; this registers it as a
REM phase with the model that decides which labels are the same category injected (an LLM may write, never read).
"""
from __future__ import annotations

from loguru import logger


def rem_pass() -> dict:
    from memory import api as memory
    from nucleo.memory_agent.processor import llm_tasks
    return memory.fold_concepts(llm_tasks.group_concepts)


def _register() -> None:
    try:
        from memory import api as memory
        memory.register_sleep_phase("concepts", rem_pass)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"memory_agent.concept_fold: REM phase not registered ({e!r})")


_register()
