"""config/credentials.py — credential-store WRITER (V2-040, sensitive).

Until now `.meshkore/credentials/zaelar.env` was only READ (`server/common.py` loads it with `override=True`, so it
WINS over `.env`). The wizard needs to WRITE the API keys the user enters there, without the user manually editing
files (product invariant: "config managed by the UI"). This module is the only writer.

HARD rules:
  · The file is gitignored and stored with **chmod 600** (owner-readable only) — never in the repo, never in logs.
  · The public view returns **presence only** (`<key>_set: bool`), NEVER the value (same redaction as v2/connectors).
    A value-returning `get()` is for INTERNAL use.
  · `set_key` applies the value **live** to `os.environ` in addition to persisting it → takes effect without restart
    (same idea: the store WINS over `.env`). Only env-var-shaped key names are accepted.
  · ATOMIC write (tmp + os.replace), preserving the rest of the file lines (comments included).
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from nucleo import workspace as _workspace

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent


def _store_path() -> Path:
    # `ZAELAR_WORKSPACE` SET (Phase 3, real cloud machine on its own mounted volume) → the store moves
    # to `<workspace>/credentials/zaelar.env`, dropping the `.meshkore` segment entirely: a deployed
    # container never has the dev-only `engine/.meshkore -> ../.meshkore` symlink this path used to
    # depend on (see root CLAUDE.md — that symlink only makes sense for the local monorepo layout).
    # UNSET (self-host, the operator's own machine, every install today) → byte-identical to the
    # path this module has always used — do not disturb a real, currently-loaded credential store.
    if os.getenv("ZAELAR_WORKSPACE"):
        return _workspace.root() / "credentials" / "zaelar.env"
    return _ROOT / ".meshkore" / "credentials" / "zaelar.env"


STORE = _store_path()

_lock = threading.Lock()

# Valid key name = env var (LETTERS/digits/_, starts with a letter). Prevents odd line/path injection.
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
# A key is SECRET (its value never leaves) if it ends with one of these suffixes, case-insensitive. Canonical
# for the whole codebase — config/v2.py's redaction imports this instead of keeping its own narrower copy
# (audit V2-098: the two had drifted, v2.py only caught "api_key" and would have leaked a future *_token/
# *_secret config key in its public() view).
SECRET_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_HASH", "_PASSWORD", "API_KEY")


def is_secret(key: str) -> bool:
    k = (key or "").upper()
    return any(k.endswith(s) for s in SECRET_SUFFIXES)


def _parse(text: str) -> "list[tuple[str, str | None]]":
    """Return .env lines as pairs (key, value), preserving comments/blanks as (None, line)."""
    out: list[tuple[str, str | None]] = []
    for raw in (text or "").splitlines():
        line = raw.rstrip("\n")
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            out.append((None, line))            # comment/blank → preserved verbatim
            continue
        k, v = line.split("=", 1)
        out.append((k.strip(), v))
    return out


def _read_text() -> str:
    try:
        return STORE.read_text(encoding="utf-8")
    except Exception:
        return ""


def _values() -> dict[str, str]:
    """Effective key→value pairs from the STORE (file only; internal use)."""
    d: dict[str, str] = {}
    for k, v in _parse(_read_text()):
        if k is not None:
            d[k] = _unquote((v or "").strip())
    return d


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _needs_quote(v: str) -> bool:
    return bool(re.search(r"[\s#'\"]", v or ""))


def set_key(name: str, value: str) -> dict:
    """Set/update a credential (persistent + live). Returns {ok, key, set}. Never the value.
    Empty value = DELETE the key from the store (to "remove" a key). NEVER raises to the caller (fail-safe)."""
    name = (name or "").strip()
    if not _KEY_RE.match(name):
        return {"ok": False, "error": "nombre de clave inválido"}
    value = value if value is not None else ""
    with _lock:
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            pairs = _parse(_read_text())
            found = False
            new: list[str] = []
            for k, v in pairs:
                if k is None:
                    new.append(v if v is not None else "")
                    continue
                if k == name:
                    found = True
                    if value == "":
                        continue                 # delete → omit the line
                    new.append(f"{name}={_quote(value)}")
                else:
                    new.append(f"{k}={v}" if v is not None else k)
            if not found and value != "":
                new.append(f"{name}={_quote(value)}")
            content = "\n".join(new).rstrip("\n") + "\n"
            tmp = str(STORE) + ".tmp"
            Path(tmp).write_text(content, encoding="utf-8")
            os.chmod(tmp, 0o600)                 # secret: owner only (before replace, no 644 window)
            os.replace(tmp, STORE)
            try:
                os.chmod(STORE, 0o600)
            except Exception:
                pass
            # apply live: the store WINS over .env (server/common override=True) → takes effect without restart
            if value == "":
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
            return {"ok": True, "key": name, "set": value != ""}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:200]}


def _quote(v: str) -> str:
    return f'"{v}"' if _needs_quote(v) else v


def get(name: str) -> str:
    """EFFECTIVE value of a credential (store → environment). INTERNAL USE — never expose to the frontend."""
    name = (name or "").strip()
    return _values().get(name) or (os.getenv(name) or "")


def status(names: "list[str] | None" = None) -> dict:
    """REDACTED PUBLIC view: `{key: {set: bool, secret: bool}}` for requested keys (or all store keys). Presence
    ONLY — the value NEVER leaves. `set` checks store AND environment (a key can come from .env)."""
    vals = _values()
    keys = list(names) if names else sorted(vals.keys())
    out = {}
    for k in keys:
        present = bool((vals.get(k) or "").strip()) or bool((os.getenv(k) or "").strip())
        out[k] = {"set": present, "secret": is_secret(k)}
    return out
