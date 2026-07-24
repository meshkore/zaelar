"""config/credentials.py — ESCRITOR del credential store (V2-040, sensible).

Hasta ahora `.meshkore/credentials/zaelar.env` solo se LEÍA (`server/common.py` lo carga con `override=True`, así
MANDA sobre `.env`). El wizard necesita ESCRIBIR ahí las API keys que el usuario introduce, sin que el usuario
edite ficheros a mano (invariante de producto «config gestionada por la UI»). Este módulo es el único escritor.

Reglas DURAS:
  · El fichero es gitignored y se guarda con **chmod 600** (solo el dueño lo lee) — nunca en el repo, nunca al log.
  · La vista pública devuelve **solo presencia** (`<clave>_set: bool`), JAMÁS el valor (misma redacción que v2/
    connectors). Un `get()` con el valor es para uso INTERNO.
  · `set_key` aplica el valor **en caliente** a `os.environ` además de persistirlo → surte efecto sin reiniciar
    (igual que el store MANDA sobre `.env`). Solo se aceptan nombres de clave con forma de env var.
  · Escritura ATÓMICA (tmp + os.replace) preservando el resto de líneas del fichero (comentarios incluidos).
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
    # `ZAELAR_WORKSPACE` SET (Fase 3, real cloud Machine on its own mounted volume) → the store moves
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

# Nombre de clave válido = env var (LETRAS/dígitos/_ , empieza por letra). Evita inyección de líneas/rutas raras.
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
# Una clave es SECRETO (nunca sale su valor) si termina en estos sufijos o es una key conocida. Alineado con la
# convención de config/v2 (`endswith('api_key')`), ampliado a los nombres reales del store (…_KEY/_TOKEN/_SECRET…).
_SECRET_SUFFIX = ("_KEY", "_TOKEN", "_SECRET", "_HASH", "_PASSWORD", "API_KEY")


def is_secret(key: str) -> bool:
    k = (key or "").upper()
    return any(k.endswith(s) for s in _SECRET_SUFFIX)


def _parse(text: str) -> "list[tuple[str, str | None]]":
    """Devuelve las líneas del .env como pares (clave, valor) preservando comentarios/blancos como (None, línea)."""
    out: list[tuple[str, str | None]] = []
    for raw in (text or "").splitlines():
        line = raw.rstrip("\n")
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            out.append((None, line))            # comentario/blanco → se preserva verbatim
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
    """Pares clave→valor efectivos del STORE (solo del fichero; uso interno)."""
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
    """Fija/actualiza una credencial (persistente + en caliente). Devuelve {ok, key, set}. Nunca el valor.
    value vacío = BORRA la clave del store (para 'quitar' una key). NUNCA lanza al llamante (fail-safe)."""
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
                        continue                 # borrar → omite la línea
                    new.append(f"{name}={_quote(value)}")
                else:
                    new.append(f"{k}={v}" if v is not None else k)
            if not found and value != "":
                new.append(f"{name}={_quote(value)}")
            content = "\n".join(new).rstrip("\n") + "\n"
            tmp = str(STORE) + ".tmp"
            Path(tmp).write_text(content, encoding="utf-8")
            os.chmod(tmp, 0o600)                 # secreto: solo el dueño (antes del replace, sin ventana 644)
            os.replace(tmp, STORE)
            try:
                os.chmod(STORE, 0o600)
            except Exception:
                pass
            # aplica en caliente: el store MANDA sobre .env (server/common override=True) → surte efecto sin reiniciar
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
    """Valor EFECTIVO de una credencial (store → entorno). USO INTERNO — nunca exponer al frontend."""
    name = (name or "").strip()
    return _values().get(name) or (os.getenv(name) or "")


def status(names: "list[str] | None" = None) -> dict:
    """Vista PÚBLICA redactada: `{clave: {set: bool, secret: bool}}` para las claves pedidas (o todas las del
    store). SOLO presencia — el valor NUNCA sale. `set` mira store Y entorno (una key puede venir de .env)."""
    vals = _values()
    keys = list(names) if names else sorted(vals.keys())
    out = {}
    for k in keys:
        present = bool((vals.get(k) or "").strip()) or bool((os.getenv(k) or "").strip())
        out[k] = {"set": present, "secret": is_secret(k)}
    return out
