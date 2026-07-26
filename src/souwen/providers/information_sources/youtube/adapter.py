from __future__ import annotations

import re
from hashlib import sha256
from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit
from souwen.platform.provider_spi import (
    PageInfo,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)
from souwen.platform.provider_spec import LegacySearchProvider, LegacySearchSpec


class YouTubeClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10, *, enrich: bool = False) -> Any: ...
    async def close(self) -> None: ...


class YouTubeSearchProvider(LegacySearchProvider):
    def __init__(self, client: YouTubeClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit, enrich=False)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "youtube"
        or getattr(response, "page", None) != 1
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid YouTube response")
    items = []
    for rank, item in enumerate(results, 1):
        url = getattr(item, "url", None)
        p = urlsplit(url or "")
        query = parse_qs(p.query, keep_blank_values=True)
        if (
            getattr(item, "source", None) != "youtube"
            or not isinstance(getattr(item, "title", None), str)
            or not item.title.strip()
            or p.scheme != "https"
            or p.hostname != "www.youtube.com"
            or p.username is not None
            or p.password is not None
            or p.port is not None
            or p.path != "/watch"
            or p.fragment
            or set(query) != {"v"}
            or len(query["v"]) != 1
            or _VIDEO_ID.fullmatch(query["v"][0]) is None
        ):
            raise ValueError("invalid YouTube item")
        canonical_url = f"https://www.youtube.com/watch?v={query['v'][0]}"
        key = sha256(canonical_url.encode()).hexdigest()
        items.append(
            SearchItem(
                id=f"youtube:{key}",
                title=item.title.strip(),
                url=canonical_url,
                snippet=getattr(item, "snippet", None) or None,
                rank=rank,
                provenance=(Provenance(provider="youtube", attempt=1, outcome="success"),),
                attributes=SearchAttributes(
                    identifiers=(SearchIdentifier(scheme="youtube", value=key),)
                ),
            )
        )
    return SearchPage(
        items=tuple(items),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("youtube",), succeeded=("youtube",)),
        context=context,
    )


_SPEC = LegacySearchSpec("youtube", "videos", _invoke, _project)
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
