"""Facebook/Meta Graph API 搜索客户端

文件用途：
    Facebook/Meta Graph API 官方搜索客户端。通过 App Access Token
    调用 ``GET /search`` 端点搜索公开 Facebook 页面和地点（Pages、Places），
    将结果归一化为统一 ``WebSearchResult`` 模型。需要 Facebook App ID 和
    App Secret（在 Meta 开发者后台创建应用后获取）。

    注意：Facebook Graph API 的搜索功能自 2018 年 Cambridge Analytica
    事件后受到严格限制。当前可用的搜索类型：
      - page：公开 Facebook 页面（品牌、组织、名人等）
      - place：包含地理位置信息的地点页面

    以下搜索类型已被弃用或需要特殊权限审核：
      - post：公开帖子搜索（已弃用）
      - group：群组搜索（需 Group API 访问权限审核）
      - event：公开活动搜索（已严格限制）

函数/类清单：
    FacebookClient（类）
        - 功能：Facebook Graph API 搜索客户端
        - 继承：SouWenHttpClient（HTTP 客户端基类，提供重试 / 代理 / 异常映射）
        - 关键属性：
            ENGINE_NAME = "facebook"
            BASE_URL = "https://graph.facebook.com"
            API_VERSION = "v19.0"
            VALID_TYPES = {"page", "place"}
        - 主要方法：
            * search(query, search_type, max_results, fields) → WebSearchResponse

    FacebookClient.__init__(app_id=None, app_secret=None, access_token=None)
        - 功能：初始化 Facebook 客户端，通过 App ID + Secret 生成 App Access Token，
                或直接使用已有的 Access Token
        - 输入：
            app_id (str|None) — Meta App ID，从参数 / SOUWEN_FACEBOOK_APP_ID
                                环境变量 / config.facebook_app_id 读取
            app_secret (str|None) — Meta App Secret，从参数 /
                                    SOUWEN_FACEBOOK_APP_SECRET /
                                    config.facebook_app_secret 读取
            access_token (str|None) — 已有的 Access Token（优先级最高），
                                      格式为 "{app_id}|{app_secret}"（App Token）
                                      或用户 Access Token
        - 异常：ConfigError — App ID / Secret 或 Access Token 均未配置时抛出

    FacebookClient.search(query, search_type="page", max_results=10,
                          fields=None) → WebSearchResponse
        - 功能：调用 GET /{version}/search 搜索 Facebook 公开页面或地点
        - 输入：
            query (str) — 搜索关键词（支持页面名称、品牌名等）
            search_type (str) — 搜索类型：page / place
            max_results (int) — 最大返回结果数（API 默认分页，最多 25 条）
            fields (list[str]|None) — 要返回的字段列表；None 时使用默认字段集
        - 输出：WebSearchResponse 包含 WebSearchResult 列表
        - 异常：
            ValueError — search_type 不在允许集合中
            ParseError — API 响应非 JSON 或结构异常
        - 字段映射（page 类型）：
            * source   = SourceType.WEB_FACEBOOK
            * title    = item["name"]（页面名称）
            * url      = "https://www.facebook.com/{id}"（页面链接）
            * snippet  = category + "：" + description（分类 + 简介）
            * engine   = "facebook"
            * raw      = { page_id, category, fan_count, website, about }
        - 字段映射（place 类型）：
            * source   = SourceType.WEB_FACEBOOK
            * title    = item["name"]（地点名称）
            * url      = "https://www.facebook.com/{id}"
            * snippet  = 地址字段拼接
            * raw      = { place_id, location, overall_star_rating,
                           checkins, phone }

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: get_config 读取配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：GET https://graph.facebook.com/v19.0/search
    - 鉴权：通过 query string 参数 ``access_token`` 传递
    - App Access Token 格式：``{app_id}|{app_secret}``（无需用户登录）
    - 单页最多 25 条结果；分页通过 ``after`` 游标实现（本实现只取首页）
    - 页面搜索不需要特殊权限审核，App Token 即可访问
    - 文档：https://developers.facebook.com/docs/graph-api/using-graph-api/
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.facebook")

# page 搜索的默认返回字段
_PAGE_DEFAULT_FIELDS = "id,name,category,fan_count,description,link,website,about"
# place 搜索的默认返回字段
_PLACE_DEFAULT_FIELDS = "id,name,location,overall_star_rating,checkins,phone,link,description"


class FacebookClient(SouWenHttpClient):
    """Facebook/Meta Graph API 搜索客户端

    使用 App Access Token（app_id + app_secret 生成）或已有的 Access Token
    调用 Graph API 搜索公开 Facebook 页面和地点。

    注意：公开帖子搜索已在 Graph API 中弃用，本客户端仅支持 page 和 place 类型。

    Example:
        async with FacebookClient() as c:
            # 搜索页面
            resp = await c.search("OpenAI", search_type="page", max_results=10)
            for r in resp.results:
                print(r.title, r.url)

            # 搜索地点
            resp = await c.search("Starbucks", search_type="place", max_results=10)
            for r in resp.results:
                print(r.title, r.snippet)
    """

    ENGINE_NAME = "facebook"
    BASE_URL = "https://graph.facebook.com"
    API_VERSION = "v19.0"

    VALID_TYPES = frozenset({"page", "place"})

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        access_token: str | None = None,
    ):
        """初始化 Facebook Graph API 搜索客户端

        Args:
            app_id: Meta App ID，从参数 / ``SOUWEN_FACEBOOK_APP_ID`` 环境变量 /
                    config.facebook_app_id 读取
            app_secret: Meta App Secret，从参数 / ``SOUWEN_FACEBOOK_APP_SECRET``
                        环境变量 / config.facebook_app_secret 读取
            access_token: 已有的 Access Token（优先级最高）；如不传，则通过
                          app_id + app_secret 构造 App Access Token
                          （格式：``{app_id}|{app_secret}``）

        Raises:
            ConfigError: App ID + Secret 与 Access Token 均未配置时抛出
        """
        config = get_config()

        if access_token:
            self._access_token = access_token
        else:
            # 尝试从配置解析 App ID 和 Secret
            resolved_app_id = app_id or config.resolve_api_key("facebook", "facebook_app_id")
            resolved_app_secret = app_secret or config.facebook_app_secret
            if not resolved_app_id or not resolved_app_secret:
                raise ConfigError(
                    "facebook_app_id / facebook_app_secret",
                    "Facebook",
                    "https://developers.facebook.com/apps/",
                )
            # App Access Token = "{app_id}|{app_secret}"，无需用户登录
            self._access_token = f"{resolved_app_id}|{resolved_app_secret}"

        super().__init__(
            base_url=self.BASE_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._access_token}",
            },
            source_name="facebook",
        )

    async def search(
        self,
        query: str,
        search_type: str = "page",
        max_results: int = 10,
        fields: list[str] | None = None,
    ) -> WebSearchResponse:
        """通过 Facebook Graph API 搜索公开页面或地点

        Args:
            query: 搜索关键词（页面名称、品牌名、地点名等）
            search_type: 搜索类型 — ``page``（页面）/ ``place``（地点）
            max_results: 最大返回结果数（Graph API 单页上限约 25 条）
            fields: 要返回的字段列表；None 时使用默认字段集

        Returns:
            WebSearchResponse 包含归一化后的搜索结果

        Raises:
            ValueError: search_type 不在允许集合中
            ParseError: API 响应非 JSON 或结构异常
        """
        if search_type not in self.VALID_TYPES:
            raise ValueError(
                f"无效的 search_type: {search_type!r}，可选值: {sorted(self.VALID_TYPES)}"
            )

        # 选取默认字段集
        if fields:
            fields_str = ",".join(fields)
        elif search_type == "page":
            fields_str = _PAGE_DEFAULT_FIELDS
        else:
            fields_str = _PLACE_DEFAULT_FIELDS

        # Graph API 单页最多 25 条，限制请求数量
        limit = max(1, min(max_results, 25))

        params: dict[str, Any] = {
            "q": query,
            "fields": fields_str,
            "limit": limit,
        }

        # Facebook 页面搜索使用 /pages/search，地点搜索使用 /search?type=place
        if search_type == "page":
            endpoint = f"/{self.API_VERSION}/pages/search"
        else:
            endpoint = f"/{self.API_VERSION}/search"
            params["type"] = search_type
        resp = await self.get(endpoint, params=params)

        try:
            data = resp.json()
        except Exception as e:
            raise ParseError(f"Facebook API 响应解析失败: {e}") from e

        items = data.get("data") or []
        results: list[WebSearchResult] = []

        for item in items:
            if len(results) >= max_results:
                break
            if not isinstance(item, dict):
                continue

            item_id = (item.get("id") or "").strip()
            name = (item.get("name") or "").strip()
            if not item_id or not name:
                continue

            # 优先使用接口返回的 link 字段；否则构造基础 URL
            link = (item.get("link") or "").strip()
            url = link if link else f"https://www.facebook.com/{item_id}"

            if search_type == "page":
                raw, snippet = self._parse_page(item)
            else:
                raw, snippet = self._parse_place(item)

            results.append(
                WebSearchResult(
                    source=SourceType.WEB_FACEBOOK,
                    title=name,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info(
            "Facebook 返回 %d 条结果 (query=%s, type=%s)",
            len(results),
            query,
            search_type,
        )

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_FACEBOOK,
            results=results,
            total_results=len(results),
        )

    @staticmethod
    def _parse_page(item: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """解析 page 类型条目，返回 (raw, snippet)"""
        category = (item.get("category") or "").strip()
        description = (item.get("description") or item.get("about") or "").strip()

        # 拼接 snippet：分类 + 简介（用于摘要展示）
        parts: list[str] = []
        if category:
            parts.append(category)
        if description:
            parts.append(description[:200])
        snippet = "；".join(parts)

        raw: dict[str, Any] = {
            "page_id": item.get("id"),
            "category": category or None,
            "fan_count": item.get("fan_count"),
            "website": item.get("website"),
            "about": item.get("about"),
            "description": description or None,
        }
        return raw, snippet

    @staticmethod
    def _parse_place(item: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """解析 place 类型条目，返回 (raw, snippet)"""
        location = item.get("location") or {}

        # 拼接地址字段作 snippet
        addr_parts: list[str] = []
        for field in ("street", "city", "state", "country"):
            val = location.get(field)
            if val:
                addr_parts.append(str(val))
        description = (item.get("description") or "").strip()
        if description and len(addr_parts) < 4:
            addr_parts.append(description[:100])
        snippet = ", ".join(addr_parts)

        raw: dict[str, Any] = {
            "place_id": item.get("id"),
            "location": location or None,
            "overall_star_rating": item.get("overall_star_rating"),
            "checkins": item.get("checkins"),
            "phone": item.get("phone"),
        }
        return raw, snippet
