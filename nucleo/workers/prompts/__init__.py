"""The briefs a Brain Worker reads (refactor2710-08 T-04): `build` (generic) and `web` (browser) compose `context`,
`surfaces`, `drawer` and `research`. The voice turn's prompt (`nucleo/turn/prompt/`) never imports them (node 2.891)."""
from nucleo.workers.prompts.build import _build_prompt  # noqa: F401
from nucleo.workers.prompts.context import (  # noqa: F401
    _METHOD_BLOCK, _known_route_line, _mesh_first_block, _recent_conversation_block, _sources_line, _today_block)
from nucleo.workers.prompts.drawer import (  # noqa: F401
    _HUMAN_NAV_GUIDE, _category_lead, _drawer_rules, _with_interpreter, _with_presentation)
from nucleo.workers.prompts.surfaces import (  # noqa: F401
    DOC_SURFACE_BLOCK, errand_block, library_block, trusted_blocks, worker_language_block)
from nucleo.workers.prompts.web import _web_prompt  # noqa: F401
