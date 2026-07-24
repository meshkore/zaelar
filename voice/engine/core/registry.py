"""Generic provider registry — the common core shared by every component family.

Each family (LLM, STT, TTS, VAD, turn) owns one ``Registry`` instance. A provider
is just a builder function decorated with ``@registry.register("name")``; the
family's ``build_*`` resolves the configured name and calls the builder with
family-appropriate kwargs. Adding a provider = drop a file + one decorator.
"""
from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


class Registry:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._builders: dict[str, Callable[..., object]] = {}

    def register(self, name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        def deco(fn: Callable[..., T]) -> Callable[..., T]:
            self._builders[name] = fn
            return fn

        return deco

    def create(self, name: str, **kwargs: object) -> object:
        try:
            builder = self._builders[name]
        except KeyError:
            raise KeyError(
                f"unknown {self.kind} provider {name!r}; available: "
                f"{', '.join(self.names()) or '(none)'}"
            ) from None
        return builder(**kwargs)

    def names(self) -> list[str]:
        return sorted(self._builders)
