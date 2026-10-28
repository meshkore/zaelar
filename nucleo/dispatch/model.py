"""Which model and which tools a worker of each kind runs with, and how many run at once.
Every package name is read through `_d`, so a patch of `dispatch.<name>` reaches the code here."""
from __future__ import annotations

import os

from nucleo import dispatch as _d


def _model_for(kind: str) -> str:
    """Worker model — TIED TO THE PROVIDER TIER that will be used, not to the global configuration.

    `code_agent.model` (p.ej. `glm-5.2`) only exists in SU proveedor. Al relevar a another escalon there is that relevar
    also the name of the model: with the cuota of Z.AI agotada, the relevo a the licencia local seguia pidiendo
    `glm-5.2` and the CLI moria al instante with «There's an issue with the selected model (glm-5.2)» — a relevo that
    no releva. Con the licencia (or any escalon without model declarado) is returns "" and the CLI usa su default."""
    def _configured() -> str:
        try:
            from config import v2 as _v2
            key = kind if kind in ("web", "code", "memory") else "generic"
            return _v2.code_agent_model(key)
        except Exception:
            return ""

    # La cadena of relevo es of CLAUDE CODE (escalones `ANTHROPIC_BASE_URL`-compatible). Otro backend —Codex— is
    # autentica with SU own cuenta and esos escalones no significan nothing for el: leave that the cadena decidiera su
    # model TIRABA the model configurado (2026-08-12, measured). El caso real: with `base_url` apuntando aun a Z.AI of
    # when the proveedor era claude_code, and Z.AI in cooldown by cuota, `relayed()` daba True → is devolvia the
    # model of the escalon of relevo (empty) → Codex caia a su own `config.toml` (`gpt-5.6-sol`, that the API no
    # sirve) and the worker moria in 2,8 s with a 400. El `gpt-5.5` that the operator habia elegido no llegaba never.
    try:
        from nucleo.workers import registry as _reg
        if _reg._provider_for(kind) != "claude_code":
            return _configured()
    except Exception:
        pass
    try:
        from nucleo.workers import providers as _prov
        if not _prov.relayed():
            return _configured()                    # sin relevo, manda el modelo por invocación de siempre
        tier = _prov.pick() or {}
    except Exception:
        return _configured()
    return str(tier.get("model") or "")              # relevado: el modelo del escalón, o el default del proveedor


def _tools_for(kind: str, trusted: bool, may_write: bool = False) -> list[str] | None:
    """Allowlist of worker tools by type. An untrusted turn never reaches here (deny_tools in the spec).

    NUNCA a `"Bash"` pelado (auditoria 2026-07-14): the Bash of the worker queda acotado a the CLIs bridge
    (`_BRIDGE_TOOLS` of `claude_session`, that is anaden solos) — a Bash abierto permitiria a a worker
    inducido by contenido web hostil open the SQLite in paralelo (`sqlite3 memory/_data/zaelar.db …`) and
    romper the ESCRITOR ÚNICO. Es the invariante documentado in CLAUDE.md («Bash SOLO a esos CLIs»)."""
    if not trusted:
        return []
    # V2-655: `Write`/`Edit` los da `may_write`, no el kind. Un `code` que no es el generador de widgets
    # —la rama `architect`— pedía escritura sobre el motor y la recibía por llamarse igual.
    if kind == "code" and may_write:
        return ["Read", "Write", "Edit", "WebSearch", "WebFetch"]
    if kind == "code":                      # V2-655 — a `code` errand that is not the widget generator
        return ["Read", "WebSearch", "WebFetch"]   # works on the ENGINE: it never writes
    # `Write` for every other trusted errand: the prompt hands every bridge payload through a relative file it
    # writes itself (see `claude_session._DEFAULT_TOOLS`, 2026-08-28). This list REPLACES that default, and it
    # never had it — demo pass 2026-09-28: «No such tool available: Write», a `printf` blocked over «$400», and a
    # monitor errand whose verified results never reached the sheet.
    return ["Read", "Write", "WebSearch", "WebFetch"]


def _max_parallel() -> int:
    try:
        v = os.getenv("CODE_AGENT_MAX_PARALLEL")
        if v:
            return max(1, int(v))
    except Exception:
        pass
    try:
        from config import v2 as _v2
        return max(1, int(_v2.get("code_agent").get("max_parallel", 2)))
    except Exception:
        return 2          # V2-771 — two at a time, the rest queued (see config/v2.py §code_agent)
