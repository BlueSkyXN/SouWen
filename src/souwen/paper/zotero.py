"""Zotero 个人文献库搜索客户端

官方文档: https://www.zotero.org/support/dev/web_api/v3/start
鉴权: Zotero-API-Key 请求头，需要在 https://www.zotero.org/settings/keys 创建
限流: 服务端可能返回 Backoff / Retry-After 头，客户端应遵守

文件用途：Zotero 个人/群组文献库搜索客户端，支持全文搜索、标签过滤、
         元数据获取、全文提取、集合列表等功能。

函数/类清单：
    ZoteroClient（类）
        - 功能：Zotero 文献库搜索客户端，支持用户/群组两种库类型
        - 关键属性：api_key (str) API Key, library_id (str) 库 ID,
                   library_type (str) 库类型 (user/group),
                   _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器

    search(query, qmode, tag, limit, start) -> SearchResponse
        - 功能：搜索文献库中的条目
        - 输入：query 搜索关键词, qmode 搜索模式, tag 标签过滤, limit/start 分页
        - 输出：SearchResponse 包含 PaperResult 列表

    get_item(item_key) -> PaperResult
        - 功能：通过 key 获取单条文献元数据

    get_fulltext(item_key) -> dict
        - 功能：获取文献的全文内容（PDF/HTML 提取文本）

    list_collections() -> list[dict]
        - 功能：列出所有文献集合

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - safe_parse_date: 安全日期解析工具
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from souwen._parsing import safe_parse_date
from souwen.config import get_config
from souwen.exceptions import ConfigError, NotFoundError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.zotero.org"

# Zotero 推荐速率（保守设定）
_DEFAULT_RPS = 8.0

# 需要排除的非文献条目类型
_SKIP_ITEM_TYPES = frozenset({"note", "attachment", "annotation"})

# 可提取全文的附件链接模式
_IMPORTABLE_LINK_MODES = frozenset({"imported_file", "imported_url"})

# Zotero Key 注册页面
_REGISTER_URL = "https://www.zotero.org/settings/keys"


class ZoteroClient:
    """Zotero 个人/群组文献库搜索客户端。

    Attributes:
        api_key: Zotero API Key。
        library_id: 文献库 ID（用户 ID 或群组 ID）。
        library_type: 库类型，``"user"`` 或 ``"group"``。
    """

    def __init__(
        self,
        api_key: str | None = None,
        library_id: str | None = None,
        library_type: str | None = None,
    ) -> None:
        cfg = get_config()
        self.api_key: str | None = api_key or cfg.resolve_api_key(
            "zotero", "zotero_api_key"
        )
        self.library_id: str | None = library_id or getattr(
            cfg, "zotero_library_id", None
        )
        self.library_type: str = (
            library_type
            or getattr(cfg, "zotero_library_type", None)
            or "user"
        )

        if not self.api_key:
            raise ConfigError(
                key="zotero_api_key",
                service="Zotero",
                register_url=_REGISTER_URL,
            )
        if not self.library_id:
            raise ConfigError(
                key="zotero_library_id",
                service="Zotero",
                register_url="https://www.zotero.org/settings",
            )

        # 去除用户复制粘贴可能带来的空格
        self.library_id = str(self.library_id).strip()

        headers: dict[str, str] = {"Zotero-API-Key": self.api_key}
        self._client = SouWenHttpClient(
            base_url=_BASE_URL, headers=headers, source_name="zotero"
        )
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ZoteroClient:
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

    @property
    def _base_path(self) -> str:
        """构建库前缀路径。"""
        if self.library_type == "group":
            return f"/groups/{self.library_id}"
        return f"/users/{self.library_id}"

    async def _respect_backoff(self, resp: Any) -> None:
        """遵守 Zotero 服务端的 Backoff / Retry-After 头。"""
        backoff = resp.headers.get("Backoff") or resp.headers.get("Retry-After")
        if backoff:
            try:
                delay = float(backoff)
                if 0 < delay <= 60:
                    logger.info("Zotero Backoff: 等待 %.1f 秒", delay)
                    await asyncio.sleep(delay)
            except (ValueError, TypeError):
                pass

    @staticmethod
    def _is_paper_type(item: dict[str, Any]) -> bool:
        """判断是否为文献条目（排除笔记、附件、注释）。"""
        return item.get("data", {}).get("itemType", "") not in _SKIP_ITEM_TYPES

    def _parse_item(self, item: dict[str, Any]) -> PaperResult:
        """将 Zotero 条目转换为 PaperResult。

        Args:
            item: Zotero API 返回的单条 item JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            data = item.get("data", {})

            # 提取作者列表
            creators = data.get("creators", [])
            authors: list[Author] = []
            for c in creators:
                if "lastName" in c:
                    name = f"{c.get('firstName', '')} {c['lastName']}".strip()
                else:
                    name = c.get("name", "")
                if name:
                    authors.append(Author(name=name))

            # 提取 DOI
            doi: str | None = (data.get("DOI") or "").strip() or None

            # 提取日期和年份（调用一次，复用结果）
            pub_date = safe_parse_date(data.get("date"))
            year: int | None = pub_date.year if pub_date else None

            # 构建 source_url
            item_key = item.get("key", "")
            url = data.get("url", "")
            if not url and doi:
                url = f"https://doi.org/{doi}"
            if not url:
                url = f"{_BASE_URL}{self._base_path}/items/{item_key}"

            # 提取标签
            tags = [
                t.get("tag", "")
                for t in data.get("tags", [])
                if t.get("tag")
            ]

            return PaperResult(
                source=SourceType.ZOTERO,
                title=data.get("title", ""),
                authors=authors,
                abstract=data.get("abstractNote", "") or None,
                doi=doi,
                year=year,
                publication_date=pub_date,
                journal=(
                    data.get("publicationTitle")
                    or data.get("bookTitle")
                    or None
                ),
                venue=(
                    data.get("conferenceName")
                    or data.get("proceedingsTitle")
                    or None
                ),
                source_url=url,
                raw={
                    "item_key": item_key,
                    "item_type": data.get("itemType"),
                    "tags": tags,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Zotero item 失败: {exc}") from exc

    @staticmethod
    def _pick_best_attachment(children: list[dict[str, Any]]) -> str | None:
        """从子条目中选择最佳可提取全文的附件。

        优先级: imported PDF > imported HTML > 其他 imported
        在同类中按 dateAdded 倒序选取最新的。
        """
        candidates: list[dict[str, Any]] = []
        for child in children:
            d = child.get("data", {})
            link_mode = d.get("linkMode", "")
            if link_mode not in _IMPORTABLE_LINK_MODES:
                continue
            candidates.append(child)

        if not candidates:
            return None

        # 分类：PDF / HTML / 其他
        pdfs = [
            c for c in candidates
            if c["data"].get("contentType") == "application/pdf"
        ]
        htmls = [
            c for c in candidates
            if (c["data"].get("contentType") or "").startswith("text/html")
        ]
        others = [
            c for c in candidates
            if c not in pdfs and c not in htmls
        ]

        # 每组按 dateAdded 倒序
        def _sort_key(c: dict[str, Any]) -> str:
            return c.get("data", {}).get("dateAdded", "")

        for group in [pdfs, htmls, others]:
            if group:
                group.sort(key=_sort_key, reverse=True)
                return group[0].get("key", "")

        return None

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        qmode: str = "everything",
        tag: str | None = None,
        limit: int = 10,
        start: int = 0,
    ) -> SearchResponse:
        """搜索文献库中的条目。

        Args:
            query: 搜索关键词。
            qmode: 搜索模式，``"titleCreatorYear"`` 或 ``"everything"``（全文）。
            tag: 标签过滤（支持布尔语法，如 ``"tag1 || tag2"``、``"-exclude"``）。
            limit: 返回条数，上限 100。
            start: 起始偏移量。

        Returns:
            SearchResponse 包含 PaperResult 列表。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "q": query,
            "qmode": qmode,
            "limit": min(limit, 100),
            "start": start,
            "itemType": "-note || -attachment || -annotation",
        }
        if tag:
            params["tag"] = tag

        resp = await self._client.get(
            f"{self._base_path}/items", params=params
        )
        await self._respect_backoff(resp)

        # Zotero 通过 Total-Results 头返回总数
        total = int(resp.headers.get("Total-Results", "0"))
        items: list[dict[str, Any]] = resp.json()

        results = [
            self._parse_item(item)
            for item in items
            if self._is_paper_type(item)
        ]

        return SearchResponse(
            query=query,
            source=SourceType.ZOTERO,
            total_results=total,
            results=results,
            page=(start // max(limit, 1)) + 1,
            per_page=limit,
        )

    async def get_item(self, item_key: str) -> PaperResult:
        """通过 key 获取单条文献元数据。

        Args:
            item_key: Zotero item key（如 ``"ABCD1234"``）。

        Returns:
            PaperResult 模型。

        Raises:
            NotFoundError: 条目不存在。
        """
        await self._limiter.acquire()
        resp = await self._client.get(
            f"{self._base_path}/items/{item_key}"
        )
        await self._respect_backoff(resp)

        if resp.status_code == 404:
            raise NotFoundError(f"Zotero 未找到条目: {item_key}")

        return self._parse_item(resp.json())

    async def get_fulltext(self, item_key: str) -> dict[str, Any]:
        """获取文献的全文内容。

        如果 item_key 指向一个父条目（非附件），会自动查找最佳附件。
        全文来自 Zotero 服务端的索引（PDF 需已被 Zotero 索引）。

        Args:
            item_key: Zotero item key。

        Returns:
            包含 ``content``、``word_count``、``indexed_pages`` 等信息的字典。

        Raises:
            NotFoundError: 找不到可提取全文的附件，或附件未被索引。
        """
        await self._limiter.acquire()

        # 获取条目信息
        resp = await self._client.get(
            f"{self._base_path}/items/{item_key}"
        )
        await self._respect_backoff(resp)

        if resp.status_code == 404:
            raise NotFoundError(f"Zotero 未找到条目: {item_key}")

        item = resp.json()
        item_type = item.get("data", {}).get("itemType", "")

        # 如果不是附件，查找最佳子附件
        attachment_key = item_key
        if item_type != "attachment":
            await self._limiter.acquire()
            children_resp = await self._client.get(
                f"{self._base_path}/items/{item_key}/children"
            )
            await self._respect_backoff(children_resp)

            children: list[dict[str, Any]] = children_resp.json()
            best = self._pick_best_attachment(children)
            if not best:
                raise NotFoundError(
                    f"Zotero 条目 {item_key} 没有可提取全文的附件"
                )
            attachment_key = best

        # 获取全文
        await self._limiter.acquire()
        try:
            ft_resp = await self._client.get(
                f"{self._base_path}/items/{attachment_key}/fulltext"
            )
            await self._respect_backoff(ft_resp)
        except Exception:
            raise NotFoundError(
                f"Zotero 附件 {attachment_key} 的全文未被索引（需 Zotero 7.1+）"
            )

        if ft_resp.status_code == 404:
            raise NotFoundError(
                f"Zotero 附件 {attachment_key} 的全文未被索引"
            )

        data = ft_resp.json()
        content = data.get("content", "")

        return {
            "item_key": item_key,
            "attachment_key": attachment_key,
            "content": content,
            "word_count": len(content.split()) if content else 0,
            "indexed_pages": data.get("indexedPages"),
            "total_pages": data.get("totalPages"),
            "indexed_chars": data.get("indexedChars"),
            "total_chars": data.get("totalChars"),
        }

    async def list_collections(self) -> list[dict[str, Any]]:
        """列出文献库中的所有集合。

        Returns:
            集合列表，每项包含 ``key``、``name``、``parent`` 字段。
        """
        await self._limiter.acquire()
        resp = await self._client.get(
            f"{self._base_path}/collections"
        )
        await self._respect_backoff(resp)

        return [
            {
                "key": c.get("key", ""),
                "name": c.get("data", {}).get("name", ""),
                "parent": c.get("data", {}).get("parentCollection"),
                "num_items": c.get("meta", {}).get("numItems", 0),
            }
            for c in resp.json()
        ]
