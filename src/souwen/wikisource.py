"""Registry-backed public Wikisource page-detail facade."""

from __future__ import annotations

from typing import Literal

from souwen.core.exceptions import SourceUnavailableError
from souwen.models import WikisourcePage
from souwen.search import search_by_capability


async def get_wikisource_page_detail(
    title: str,
    *,
    language: str = "zh",
    revision_id: int | None = None,
    content_format: Literal["wikitext", "text", "html"] = "wikitext",
    max_content_chars: int = 100_000,
    include_subpages: bool = False,
    subpage_limit: int = 10,
) -> WikisourcePage:
    """Read one allowlisted Wikisource page through its canonical registry adapter."""

    responses = await search_by_capability(
        title,
        "get_detail",
        sources=["wikisource"],
        title=title,
        language=language,
        revision_id=revision_id,
        content_format=content_format,
        max_content_chars=max_content_chars,
        include_subpages=include_subpages,
        subpage_limit=subpage_limit,
    )
    if len(responses) != 1 or not isinstance(responses[0], WikisourcePage):
        raise SourceUnavailableError("Wikisource page detail 不可用")
    return responses[0]


__all__ = ["get_wikisource_page_detail"]
