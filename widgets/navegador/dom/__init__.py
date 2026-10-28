"""widgets/navegador/dom — DOM/accessibility snapshot + human-like input primitives. Page-parametric, with no
module-global coupling: `page`/`h`/`mouse` are always passed explicitly by the caller (TaskBrowser, in owner.py),
so this package has zero dependency on owner.py, which re-exports these names as bare names.

Modules: `describe` (the snapshot), `human` (mouse and keyboard) and `extract_js` (the listing extractor run in the
page). This facade re-exports every name."""
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
