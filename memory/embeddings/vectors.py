"""Vector arithmetic every backend shares: the deterministic hashing embedding, dimension fitting, L2 norm."""
from __future__ import annotations

import hashlib
import math
import re

from ..schema import EMBED_DIM

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _hash_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Feature-hashing bag-of-words → a deterministic `dim`-wide vector. Lexical signal, no deps, no network."""
    vec = [0.0] * dim
    for tok in _TOKEN_RE.findall(text.lower()):
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if (h[4] & 1) else -1.0
        vec[idx] += sign
    return vec


def _fit_dim(vec: list[float], dim: int = EMBED_DIM) -> list[float]:
    if len(vec) == dim:
        return vec
    if len(vec) > dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))


def _l2_normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    if n <= 1e-12:
        return vec
    return [x / n for x in vec]
