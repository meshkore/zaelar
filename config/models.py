"""config/models.py — THE READER for `models.default.json`, the single model table (V2-500).

One place for the default allocation. This module makes no decisions: it reads the file and translates it into the
form expected by each consumer (`config/v2.py`, `provider_chain`, `workers/providers`, the voice engine, and both
cloud surfaces). All the policy—and the reason for each row—lives in the JSON, which is public and human-readable.

It fails LOUDLY on purpose: if the file is missing or cannot be parsed, startup must say so. A fail-open here
would return an empty table and the engine would start with “no provider” without anyone knowing why—which is
exactly the kind of silence this table exists to eliminate.
"""
from __future__ import annotations

import json
import os
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_HERE, "models.default.json")
_CACHE: dict[str, Any] = {}


def _table() -> dict:
    if "t" not in _CACHE:
        with open(_PATH, encoding="utf-8") as fh:
            _CACHE["t"] = json.load(fh)
    return _CACHE["t"]


def services() -> dict:
    return dict(_table().get("services") or {})


def service(name: str) -> dict:
    s = services().get(name)
    if not s:
        raise KeyError(f"«{name}» no está en models.default.json — añádelo ahí, no en el código")
    return s


def titular(name: str) -> dict:
    return dict(service(name).get("titular") or {})


def failover(name: str) -> dict | None:
    f = service(name).get("failover")
    return dict(f) if f else None


def rungs(name: str) -> list[dict]:
    """Primary + backup, in order, skipping any that do not exist. **At most TWO**—operator rule: one
    failover per service, because a chain of four cannot be reasoned about or debugged."""
    out = [titular(name)]
    f = failover(name)
    if f:
        out.append(f)
    return [r for r in out if r.get("provider")]


def chain_for(name: str, *, names: tuple[str, str] = ("", "")) -> list[dict]:
    """Los escalones en la forma que consumen `provider_chain` y `workers/providers`.

    `names` da el nombre visible de cada escalón (el que sale en los avisos y en el panel); sin él se compone
    del proveedor, que es lo bastante claro para los servicios de una sola fila.
    """
    out = []
    for i, r in enumerate(rungs(name)):
        etiqueta = (names[i] if i < len(names) and names[i] else r.get("provider") or "")
        fila = {"name": etiqueta, "base_url": r.get("base_url") or "",
                "model": r.get("model") or "", "provider": r.get("provider") or ""}
        if r.get("key_env"):
            fila["env"] = [r["key_env"]]
        if "vision" in r:
            fila["vision"] = r["vision"]
        out.append(fila)
    return out


def enabled(name: str, default: bool = True) -> bool:
    v = service(name).get("enabled")
    return default if v is None else bool(v)


def retired() -> dict:
    """What was removed and why. Exposed so a guard can verify that it has not returned."""
    return {k: v for k, v in (_table().get("retired") or {}).items() if k != "_"}
