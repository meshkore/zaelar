"""widgets/navegador/dom.py — DOM/accessibility snapshot + human-like input primitives (split out of owner.py,
2026-08-17 modularization pass). Page-parametric functions with no module-global coupling: `page`/`h`/`mouse`
are always passed explicitly by the caller (TaskBrowser, in owner.py). The one thing that made this NOT a clean
move before this session's `owner.py` dead-code deletion: `_human_move`/`_human_click_at` used to fall back to
owner.py's module-level `_mouse` when `mouse` was omitted — a fallback only the now-deleted module-level
`agent_act()` ever relied on. With that gone, every surviving caller already passes `mouse` explicitly, so the
parameter is required here and this file has zero dependency on owner.py.

Re-exported from owner.py, since TaskBrowser's methods (which stay there) reference these as bare names.

A package since refactor2710-12: `describe` (the snapshot), `human` (mouse and keyboard) and `extract_js` (the
listing extractor run in the page). This facade re-exports every name."""
from __future__ import annotations

import asyncio
import random
import re

# IRREVERSIBLE actions that require operator OK before execution (confirm-gate). Intentionally conservative
# (do not gate normal navigation): only explicit purchase/payment/publishing/deletion.
_DANGER_RE = re.compile(
    r"\b(comprar|pagar|pagó|finalizar compra|realizar pedido|tramitar pedido|confirmar pedido|confirmar compra|"
    r"proceder al pago|publicar|eliminar cuenta|borrar cuenta|eliminar|borrar|checkout|buy now|buy|pay|purchase|"
    r"place order|confirm order|complete purchase|publish|delete account|delete)\b", re.I)

# ── Automator: accessibility snapshot + human input + action executor (agent.py) ────────────────────────────
_INTERACTIVE = ("a, button, input, textarea, select, [role=button], [role=link], [role=textbox], "
                "[role=checkbox], [role=radio], [role=tab], [role=menuitem], [role=combobox], [role=option]")

from widgets.navegador.dom.extract_js import (  # noqa: E402,F401 — re-export
    _JS_EXTRACT)
from widgets.navegador.dom.describe import (  # noqa: E402,F401 — re-export
    _describe_el, _JS_DESCRIBE, _bulk_metas, _snapshot_lines)
from widgets.navegador.dom.human import (  # noqa: E402,F401 — re-export
    _human_move, _human_click_handle, _human_type_handle, _human_click_at)
