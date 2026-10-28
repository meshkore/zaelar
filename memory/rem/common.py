"""Small pieces every REM phase shares: the memory clock, vector unpacking, cosine, and the number pattern."""
import re as _re
import struct


def _now() -> int:
    from ..clock import now
    return now()


def _unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _cos(a: list[float], b: list[float]) -> float:
    # vectors are ALREADY L2-normalised on insert → cosine = dot product
    return sum(x * y for x, y in zip(a, b))


_NUM_RE = _re.compile(r"\d+(?:[.,:]\d+)*")
