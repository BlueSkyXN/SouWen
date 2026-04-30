"""bioRxiv / medRxiv content API 客户端

官方文档: https://api.biorxiv.org
鉴权: 无需 Key
限流: 保守 1 req/s
返回: JSON（collection[]）

文件用途：使用 bioRxiv content details API 获取近期 bioRxiv/medRxiv 预印本，
并在本地按标题与摘要进行关键词过滤。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.biorxiv.org"
_DEFAULT_RPS = 1.0
_DEFAULT_LOOKBACK_DAYS = 7
_MAX_FETCHED = 1000
# bioRxiv has no server-side search; we fetch recent preprints and filter locally.
# To limit API calls, only the last 7 days are scanned by default.
_MAX_API_REQUESTS = 34
_VALID_SERVERS = {"biorxiv", "medrxiv"}
_BIORXIV_LIMITER = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)


class BioRxivClient:
    """bioRxiv / medRxiv 生物医学预印本搜索客户端。

    bioRxiv 官方 API 没有全文搜索端点，本客户端拉取最近 7 天内容详情，
    再按 query 在 title / abstract 中做大小写不敏感过滤。
    """

    def __init__(self) -> None:
        """初始化 bioRxiv API 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="biorxiv")
        self._limiter = _BIORXIV_LIMITER

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> BioRxivClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_result(item: dict[str, Any]) -> PaperResult:
        """将 bioRxiv content API 单条 collection 记录转换为 PaperResult。

        Args:
            item: ``collection[]`` 中的单条预印本元数据。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            doi = str(item.get("doi") or "").strip() or None
            title = str(item.get("title") or "")
            abstract = str(item.get("abstract") or "")

            raw_authors = item.get("authors") or ""
            authors: list[Author] = []
            if isinstance(raw_authors, str):
                authors = [
                    Author(name=name.strip()) for name in raw_authors.split(";") if name.strip()
                ]
            elif isinstance(raw_authors, list):
                authors = [
                    Author(name=str(name).strip()) for name in raw_authors if str(name).strip()
                ]

            pub_date = str(item.get("date") or "").strip() or None
            year: int | None = None
            if pub_date:
                try:
                    year = int(pub_date[:4])
                except (TypeError, ValueError):
                    year = None

            server = str(item.get("server") or "biorxiv").lower()
            if server not in _VALID_SERVERS:
                server = "biorxiv"
            server_label = "medRxiv" if server == "medrxiv" else "bioRxiv"

            source_url = f"https://doi.org/{doi}" if doi else "https://www.biorxiv.org/"
            category = str(item.get("category") or "").strip() or None
            journal = server_label

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.BIORXIV,
                source_url=source_url,
                journal=journal,
                venue=category,
                citation_count=None,
                raw={
                    "server": server,
                    "category": category,
                    "version": item.get("version") or None,
                    "type": item.get("type") or None,
                    "license": item.get("license") or None,
                    "jatsxml": item.get("jatsxml") or None,
                    "published": item.get("published") or None,
                    "author_corresponding": item.get("author_corresponding") or None,
                    "author_corresponding_institution": item.get("author_corresponding_institution")
                    or None,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 bioRxiv/medRxiv result 失败: {exc}") from exc

    @staticmethod
    def _matches_query(item: dict[str, Any], query: str) -> bool:
        """按 title / abstract 做简单大小写不敏感关键词匹配。"""
        normalized_query = query.strip().lower()
        if not normalized_query:
            return True

        haystack = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("abstract") or ""),
            ]
        ).lower()
        terms = normalized_query.split()
        return all(term in haystack for term in terms)

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        """将 bioRxiv API 元数据中的数字字段安全转换为 int。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        per_page: int = 10,
        server: str = "biorxiv",
    ) -> SearchResponse:
        """搜索近期 bioRxiv / medRxiv 预印本。

        Args:
            query: 本地过滤关键词，匹配 title / abstract。
            per_page: 返回结果数量。
            server: ``"biorxiv"`` 或 ``"medrxiv"``。

        Returns:
            SearchResponse 包含本地过滤后的预印本结果。
        """
        normalized_server = server.lower().strip()
        if normalized_server not in _VALID_SERVERS:
            raise ValueError("server must be 'biorxiv' or 'medrxiv'")

        page_size = min(max(per_page, 1), _MAX_FETCHED)
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=_DEFAULT_LOOKBACK_DAYS)
        interval = f"{start_date.isoformat()}/{end_date.isoformat()}"

        results: list[PaperResult] = []
        fetched = 0
        cursor = 0
        requests_made = 0

        while (
            len(results) < page_size
            and fetched < _MAX_FETCHED
            and requests_made < _MAX_API_REQUESTS
        ):
            await self._limiter.acquire()
            resp = await self._client.get(f"/details/{normalized_server}/{interval}/{cursor}/json")
            requests_made += 1
            data: dict[str, Any] = resp.json()
            items = data.get("collection") or []
            if not isinstance(items, list) or not items:
                break

            messages = data.get("messages") or []
            metadata = messages[0] if isinstance(messages, list) and messages else {}
            if not isinstance(metadata, dict):
                metadata = {}
            total = self._int_or_none(metadata.get("total"))
            count = self._int_or_none(metadata.get("count"))
            current_cursor = self._int_or_none(metadata.get("cursor"))
            if count is None:
                count = len(items)
            if current_cursor is None:
                current_cursor = cursor

            fetched += len(items)
            for item in items:
                if not isinstance(item, dict) or not self._matches_query(item, query):
                    continue
                try:
                    results.append(self._parse_result(item))
                except ParseError as exc:
                    logger.debug("跳过解析失败的 bioRxiv/medRxiv 论文: %s", exc)
                if len(results) >= page_size:
                    break

            next_cursor = current_cursor + count
            if total is None or next_cursor >= total or next_cursor <= cursor:
                break
            cursor = next_cursor

        return SearchResponse(
            query=query,
            total_results=len(results),
            page=1,
            per_page=per_page,
            results=results,
            source=SourceType.BIORXIV,
        )
