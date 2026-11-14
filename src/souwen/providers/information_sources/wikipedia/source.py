"""wikipedia（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Sequence, Mapping
from hashlib import sha256
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.common_runtime.provider_support.exceptions import ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import (
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
    ClientSearchProvider,
    ClientSearchSpec,
)
from souwen.platform.provider_spec.models import HttpOperation
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
from souwen.providers.runtime_clients.models import WebSearchResponse, WebSearchResult
from typing import Any, Protocol
from urllib.parse import quote, urlsplit, urlunsplit


from souwen.platform.manifest_registry import ProviderManifest

WIKIPEDIA_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "wikipedia",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "wikipedia-search",
                "capability": "search",
                "export": "WikipediaSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "wikipedia-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["zh.wikipedia.org"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["wikipedia-provider-config-v1"],
        },
    }
)


WIKIPEDIA_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="wikipedia",
    adapter_id="wikipedia-search",
    domain="wiki",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="zh.wikipedia.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/w/api.php"),),
    ),
    configuration_keys=("enabled",),
)


logger = logging.getLogger("souwen.providers.runtime_clients.web.wikipedia")

_HTML_TAG_RE = re.compile(r"<[^>]+>")

_WS_RE = re.compile(r"\s+")


def _clean_html(text: str) -> str:
    """剥离 MediaWiki snippet 中的 HTML 标签并解码实体。

    MediaWiki 返回的 snippet 形如：
        '...这是<span class="searchmatch">关键词</span>所在的句子...'
    本函数去除标签、解码 ``&amp;`` 等实体、折叠空白，输出干净文本。
    """
    if not text:
        return ""
    no_tag = _HTML_TAG_RE.sub("", text)
    decoded = html.unescape(no_tag)
    return _WS_RE.sub(" ", decoded).strip()


class WikipediaClient(SouWenHttpClient):
    """Wikipedia 搜索客户端（MediaWiki Action API）

    通过维基百科公开的 ``action=query&list=search`` 接口检索条目，
    无需任何 API Key 或登录。支持按语言切换子站点（zh / en / ja / ...）。

    Example:
        async with WikipediaClient(lang="zh") as c:
            resp = await c.search("人工智能", max_results=5)
            for r in resp.results:
                print(r.title, r.url)

        # 临时切换到英文站
        async with WikipediaClient() as c:
            resp = await c.search("Quantum computing", lang="en")
    """

    ENGINE_NAME = "wikipedia"
    BASE_URL = "https://zh.wikipedia.org"
    API_PATH = "/w/api.php"
    # MediaWiki 普通用户 srlimit 上限
    MAX_LIMIT = 50

    def __init__(self, lang: str = "zh"):
        # 维基媒体 API 礼仪：必须自定义带项目身份的 User-Agent
        base_url = f"https://{lang}.wikipedia.org"
        super().__init__(
            base_url=base_url,
            headers={
                "User-Agent": (
                    "SouWen/1.0 (Academic & Patent Search Tool; "
                    "+https://github.com/BlueSkyXN/SouWen)"
                ),
                "Accept": "application/json",
            },
            source_name="wikipedia",
        )
        self._lang = lang

    async def search(
        self,
        query: str,
        max_results: int = 10,
        lang: str | None = None,
    ) -> WebSearchResponse:
        """通过 MediaWiki Action API 搜索维基百科条目。

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（默认 10，MediaWiki 单页上限 50）
            lang: 临时覆盖语言子站点（None 表示沿用实例 ``__init__`` 时的 lang）

        Returns:
            WebSearchResponse 包含归一化后的搜索结果

        Raises:
            ParseError: MediaWiki 响应非 JSON 或缺少 query.search 结构
        """
        # 单次调用允许临时覆盖 lang，便于复用同一个 client 跨语言查询
        effective_lang = lang or self._lang

        # MediaWiki srlimit 上限 50；下限 1 防止请求被拒
        limit = max(1, min(max_results, self.MAX_LIMIT))

        params: dict[str, Any] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
            # 显式声明所需字段，避免依赖 MediaWiki 默认值漂移
            "srprop": "snippet|titlesnippet|timestamp|wordcount|size",
            # 让 MediaWiki 直接返回 utf-8，不做 \u 转义
            "utf8": 1,
        }

        # 当 lang 临时覆盖且与实例不同，需指向对应子站点的完整 URL；
        # 否则使用相对路径让 httpx 拼接实例 base_url
        if lang and lang != self._lang:
            target = f"https://{effective_lang}.wikipedia.org{self.API_PATH}"
        else:
            target = self.API_PATH

        resp = await self.get(target, params=params)

        try:
            data = resp.json()
        except Exception as e:
            raise ParseError(f"Wikipedia 响应解析失败: {e}") from e

        # MediaWiki 错误响应形如 {"error": {"code": ..., "info": ...}}
        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            info = err.get("info") if isinstance(err, dict) else str(err)
            raise ParseError(f"Wikipedia API 错误: {info}")

        try:
            search_items = data["query"]["search"]
        except (KeyError, TypeError) as e:
            raise ParseError(f"Wikipedia 响应缺少 query.search 字段: {data!r}") from e

        if not isinstance(search_items, list):
            raise ParseError(f"Wikipedia query.search 不是列表: {type(search_items).__name__}")

        results: list[WebSearchResult] = []
        for item in search_items:
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()
            if not title:
                # 缺标题的不完整记录直接跳过
                continue

            # 维基条目 URL 命名约定：空格 → 下划线，再做 percent-encoding；
            # 保留 ``:`` ``/`` 等维基命名空间分隔符
            url_title = quote(title.replace(" ", "_"), safe=":/()")
            url = f"https://{effective_lang}.wikipedia.org/wiki/{url_title}"

            snippet = _clean_html(item.get("snippet", ""))

            raw: dict[str, Any] = {
                "pageid": item.get("pageid"),
                "wordcount": item.get("wordcount"),
                "size": item.get("size"),
                "timestamp": item.get("timestamp"),
                "titlesnippet": item.get("titlesnippet"),
                "lang": effective_lang,
            }

            results.append(
                WebSearchResult(
                    source="wikipedia",
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

            if len(results) >= max_results:
                break

        logger.info(
            "Wikipedia 返回 %d 条结果 (query=%s, lang=%s)",
            len(results),
            query,
            effective_lang,
        )

        return WebSearchResponse(
            query=query,
            source="wikipedia",
            results=results,
            total_results=len(results),
        )


_PROVIDER_ID = "wikipedia"


class WikipediaClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...


class WikipediaSearchProvider(ClientSearchProvider):
    def __init__(self, client: WikipediaClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != _PROVIDER_ID
        or getattr(response, "page", None) != 1
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid existing web search response")
    return SearchPage(
        items=tuple(_item(result, rank) for rank, result in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(result: Any, rank: int) -> SearchItem:
    if (
        getattr(result, "source", None) != _PROVIDER_ID
        or not isinstance(getattr(result, "title", None), str)
        or not result.title.strip()
    ):
        raise ValueError("invalid existing web result")
    url = _canonical_url(getattr(result, "url", None))
    identifier = sha256(url.encode("utf-8")).hexdigest()
    return SearchItem(
        id=f"{_PROVIDER_ID}:{identifier}",
        title=result.title.strip(),
        url=url,
        snippet=_optional_text(getattr(result, "snippet", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            identifiers=(SearchIdentifier(scheme=_PROVIDER_ID, value=identifier),)
        ),
    )


def _canonical_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing record URL")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("invalid record URL")
    host = parsed.hostname.lower()
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid snippet")
    return value.strip() or None


_SPEC = ClientSearchSpec(_PROVIDER_ID, "wiki", _invoke, _project)

__all__ = ["WikipediaClientProtocol", "WikipediaSearchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = WikipediaClient()
    return WikipediaSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = WIKIPEDIA_PROVIDER_MANIFEST
SPEC = WIKIPEDIA_PROVIDER_SPEC
PROVIDER_TYPE = WikipediaSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
