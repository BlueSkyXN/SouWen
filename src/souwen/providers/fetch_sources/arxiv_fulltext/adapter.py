"""Source-specific arXiv full-text bridge over the existing existing client."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlsplit

from souwen.platform.provider_spi import (
    ContentMetadata,
    FetchResult,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
)
from souwen.platform.provider_spec import ClientFetchProvider, ClientFetchSpec

from .spec import ARXIV_FULLTEXT_FETCH_PROFILE

_PAPER_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z0-9.-]*/\d{7})(?:v\d+)?$")
_ACCEPTED_PATHS = ("/abs/", "/html/")


class ArxivFulltextClientProtocol(Protocol):
    async def get_fulltext(self, paper_id: str) -> Any: ...
    async def close(self) -> None: ...


class ArxivFulltextFetchProvider(ClientFetchProvider):
    """Fetch one reviewed arXiv target without broadening the source scope."""

    capability = "fetch"

    def __init__(self, client: ArxivFulltextClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _FETCH_SPEC, enabled=enabled)


async def _invoke(client: Any, request: FetchTargetRequest) -> Any:
    return await client.get_fulltext(_paper_id(request))


def _project(receipt: Any, request: FetchTargetRequest, context: RequestContext) -> FetchResult:
    del context
    provider_id = ARXIV_FULLTEXT_FETCH_PROFILE.provider_id
    if getattr(receipt, "source", None) != provider_id:
        raise ValueError("unexpected existing arXiv source")
    if getattr(receipt, "error", None):
        raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE, provider_id=provider_id)
    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("invalid arXiv full-text receipt")
    final_url = _final_url(receipt, _paper_id(request))
    retrieved_at = datetime.now(timezone.utc)
    return FetchResult(
        target=request.target,
        final_url=final_url,
        status="success",
        title=getattr(receipt, "title", None) or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type="text/plain",
            retrieved_at=retrieved_at,
            truncated=False,
            content_length=len(content.encode()),
            quality="low" if len(content.strip()) <= 63 else "high",
        ),
        provenance=(
            Provenance(
                provider=provider_id, attempt=1, outcome="success", retrieved_at=retrieved_at
            ),
        ),
    )


def _paper_id(request: FetchTargetRequest) -> str:
    target = urlsplit(str(request.target))
    prefix = next((item for item in _ACCEPTED_PATHS if target.path.startswith(item)), None)
    paper_id = target.path[len(prefix) :] if prefix is not None else ""
    if (
        target.scheme != "https"
        or target.hostname != ARXIV_FULLTEXT_FETCH_PROFILE.transport.host
        or target.username is not None
        or target.password is not None
        or target.port is not None
        or target.query
        or target.fragment
        or _PAPER_ID.fullmatch(paper_id) is None
    ):
        raise ProviderError(
            ProviderErrorCode.POLICY_BLOCKED,
            provider_id=ARXIV_FULLTEXT_FETCH_PROFILE.provider_id,
        )
    return paper_id


def _final_url(receipt: Any, paper_id: str) -> str:
    final_url = urlsplit(str(getattr(receipt, "final_url", "")))
    if (
        final_url.scheme != "https"
        or final_url.hostname != ARXIV_FULLTEXT_FETCH_PROFILE.transport.host
        or final_url.username is not None
        or final_url.password is not None
        or final_url.port is not None
        or final_url.path != f"/html/{paper_id}"
        or final_url.query
        or final_url.fragment
    ):
        raise ValueError("invalid arXiv final URL")
    return f"https://arxiv.org/html/{paper_id}"


_FETCH_SPEC = ClientFetchSpec(ARXIV_FULLTEXT_FETCH_PROFILE.provider_id, _invoke, _project)

__all__ = ["ArxivFulltextClientProtocol", "ArxivFulltextFetchProvider"]
