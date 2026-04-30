"""IEEE Xplore Metadata API 客户端

官方文档: https://developer.ieee.org/docs/read/Metadata_API_details
鉴权: 需 IEEE Xplore API Key（query 参数 ``apikey``）
限流: 免费层 200 requests/day，客户端侧保守限制约 3 req/s
返回: JSON（articles[]）
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://ieeexploreapi.ieee.org/api/v1"
_REGISTER_URL = "https://developer.ieee.org/"
_DEFAULT_RPS = 3.0


def _safe_int(v: Any, default: int = 0) -> int:
    """Parse any value as int, return default on failure."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _parse_year(v: Any) -> int | None:
    """Extract a 4-digit year from a value. Returns None on failure."""
    s = str(v).strip()[:4]
    try:
        year = int(s)
        return year if 1900 <= year <= 2100 else None
    except (TypeError, ValueError):
        return None


def _parse_publication_date(value: Any) -> str | None:
    """Normalize common IEEE dates to ISO date strings accepted by PaperResult."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%d %B %Y", "%B %Y", "%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%B %Y":
            return f"{parsed.year:04d}-{parsed.month:02d}-01"
        if fmt == "%Y":
            return f"{parsed.year:04d}-01-01"
        return parsed.date().isoformat()

    return text


def _terms_list(index_terms: dict[str, Any], key: str) -> list[str]:
    bucket = index_terms.get(key) if isinstance(index_terms, dict) else None
    terms = bucket.get("terms", []) if isinstance(bucket, dict) else []
    if isinstance(terms, list):
        return [str(term) for term in terms if term]
    if terms:
        return [str(terms)]
    return []


class IeeeXploreClient:
    """IEEE Xplore 电气电子工程文献搜索客户端。

    Raises:
        ConfigError: 未配置 ieee_api_key 时抛出。
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 IEEE Xplore 客户端。

        Args:
            api_key: IEEE Xplore API Key。未提供时从全局配置读取。

        Raises:
            ConfigError: API Key 未配置。
        """
        cfg = get_config()
        self.api_key: str = api_key or cfg.resolve_api_key("ieee_xplore", "ieee_api_key") or ""
        if not self.api_key:
            raise ConfigError(
                key="ieee_api_key",
                service="IEEE Xplore",
                register_url=_REGISTER_URL,
            )

        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="ieee_xplore")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    async def __aenter__(self) -> IeeeXploreClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def _parse_article(article: dict[str, Any]) -> PaperResult:
        """将 IEEE Xplore article 对象转换为统一的 PaperResult。"""
        try:
            article_number = str(article.get("article_number") or "").strip()
            doi = article.get("doi") or None
            html_url = article.get("html_url") or None

            authors: list[Author] = []
            authors_obj = article.get("authors") or {}
            raw_authors = authors_obj.get("authors", []) if isinstance(authors_obj, dict) else []
            for item in raw_authors or []:
                if isinstance(item, dict):
                    name = item.get("full_name") or item.get("name") or ""
                    affiliation = item.get("affiliation") or None
                else:
                    name = str(item)
                    affiliation = None
                if name:
                    authors.append(Author(name=name, affiliation=affiliation))

            year = _parse_year(article.get("publication_year"))
            publication_date = _parse_publication_date(article.get("publication_date"))

            citation_count = _safe_int(article.get("citing_paper_count"))
            index_terms = article.get("index_terms") or {}
            ieee_terms = _terms_list(index_terms, "ieee_terms")
            author_terms = _terms_list(index_terms, "author_terms")

            if doi:
                source_url = f"https://doi.org/{doi}"
            elif html_url:
                source_url = html_url
            elif article_number:
                source_url = f"https://ieeexplore.ieee.org/document/{article_number}"
            else:
                source_url = "https://ieeexplore.ieee.org/"

            access_type = article.get("access_type", article.get("accessType", ""))
            is_open_access = "open" in str(access_type).lower()

            return PaperResult(
                title=article.get("title", "") or "",
                authors=authors,
                abstract=article.get("abstract") or None,
                doi=doi,
                year=year,
                publication_date=publication_date,
                source=SourceType.IEEE_XPLORE,
                source_url=source_url,
                pdf_url=article.get("pdf_url") or None,
                citation_count=citation_count,
                journal=article.get("publication_title") or None,
                venue=article.get("publication_title") or None,
                open_access_url=html_url if is_open_access else None,
                raw={
                    "article_number": article_number or None,
                    "html_url": html_url,
                    "content_type": article.get("content_type"),
                    "publisher": article.get("publisher"),
                    "is_open_access": is_open_access,
                    "start_page": _safe_int(article.get("start_page")),
                    "end_page": _safe_int(article.get("end_page")),
                    "ieee_terms": ieee_terms,
                    "author_terms": author_terms,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 IEEE Xplore article 失败: {exc}") from exc

    async def search(
        self,
        query: str,
        max_results: int = 10,
        start_record: int = 1,
    ) -> SearchResponse:
        """使用 IEEE Xplore Metadata API 检索文献。"""
        await self._limiter.acquire()

        limit = min(max(max_results, 1), 200)
        start = max(start_record, 1)
        params: dict[str, str | int] = {
            "apikey": self.api_key,
            "querytext": query,
            "max_records": limit,
            "start_record": start,
            "format": "json",
        }

        # NOTE: IEEE Xplore (Mashery) may return 403 for rate-limit/quota errors.
        # The shared HTTP client maps these to AuthError; a Mashery-specific handler
        # would need to inspect X-Mashery-Error-Code headers to distinguish auth vs rate-limit.
        resp = await self._client.get("/search/articles", params=params)
        data: dict[str, Any] = resp.json()

        results: list[PaperResult] = []
        for article in data.get("articles", []) or []:
            try:
                results.append(self._parse_article(article))
            except ParseError as exc:
                logger.debug("跳过解析失败的 IEEE Xplore article: %s", exc)

        total = _safe_int(data.get("total_records")) or len(results)

        return SearchResponse(
            query=query,
            total_results=total,
            page=((start - 1) // limit) + 1,
            per_page=limit,
            results=results,
            source=SourceType.IEEE_XPLORE,
        )
