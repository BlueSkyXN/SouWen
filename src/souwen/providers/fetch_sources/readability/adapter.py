from __future__ import annotations

from typing import Any, Protocol

from souwen.platform.provider_spi import FetchResult, FetchTargetRequest, RequestContext
from souwen.platform.provider_spec import ClientFetchProvider, ClientFetchSpec
from souwen.platform.provider_spec.public_fetch import (
    project_public_fetch_receipt,
    public_fetch_target,
)

from .spec import READABILITY_FETCH_PROFILE


class ReadabilityClientProtocol(Protocol):
    async def fetch(self, url: str, timeout: float = 30.0) -> Any: ...
    async def close(self) -> None: ...


class ReadabilityFetchProvider(ClientFetchProvider):
    def __init__(self, client: ReadabilityClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _FETCH_SPEC, enabled=enabled)


async def _invoke(client: Any, request: FetchTargetRequest) -> Any:
    return await client.fetch(
        public_fetch_target(request, READABILITY_FETCH_PROFILE.provider_id), timeout=30.0
    )


def _project(receipt: Any, request: FetchTargetRequest, _context: RequestContext) -> FetchResult:
    return project_public_fetch_receipt(receipt, request, READABILITY_FETCH_PROFILE.provider_id)


_FETCH_SPEC = ClientFetchSpec(READABILITY_FETCH_PROFILE.provider_id, _invoke, _project)

__all__ = ["ReadabilityClientProtocol", "ReadabilityFetchProvider"]
