"""Thin generic Provider v2 binding for HuggingFace Papers."""

from __future__ import annotations
from typing import Any, Protocol

from souwen.platform.provider_spec import RestJsonSearchProvider
from .spec import HUGGINGFACE_REST_SPEC


class HuggingFaceClientProtocol(Protocol):
    async def search(self, query: str, top_n: int = 10) -> Any: ...
    async def close(self) -> None: ...


class HuggingFaceSearchProvider(RestJsonSearchProvider):
    def __init__(self, client: HuggingFaceClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, HUGGINGFACE_REST_SPEC, enabled=enabled)
