"""Moved to `nucleo/turn/prompt/` (refactor2710-08): this name re-exports it until its importers land there."""
from nucleo.flash.live_blocks import _STALLED_S, _cron_line, _found_candidates, _short_note, _site_of  # noqa: F401
from nucleo.flash.recall_heuristics import compose_recent_block, needs_recall, needs_recent  # noqa: F401
from nucleo.turn.prompt.builder import (  # noqa: F401
    _directive_block, _lang_lock, _people_block, build_cluster_system, build_flash_system)
from nucleo.turn.prompt.live_state import _open_widget_ids, _recent_widget_ids, live_state, screen_line  # noqa: F401
from nucleo.turn.prompt.operating import (  # noqa: F401
    _connector_briefs, _flash_layer, _rails_directive, _workers_directive)
from nucleo.turn.prompt.recall import _observability_on, compose_recall  # noqa: F401
