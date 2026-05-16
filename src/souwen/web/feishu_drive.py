"""飞书云文档搜索客户端

文件用途：
    飞书（Feishu/Lark）开放平台云文档搜索客户端。通过调用飞书服务端
    API（POST /open-apis/suite/docs-api/search/object）根据关键词搜索
    当前应用可见的云文档，支持文档、电子表格、幻灯片、多维表格、思维笔记、
    文件等多种类型，将结果统一归一化为 SouWen 的 WebSearchResult 模型。

    鉴权方式：
        使用自建应用的 app_id + app_secret 通过 client_credentials 模式
        获取 tenant_access_token，再以 Bearer Token 调用搜索接口。
        Token 有效期约 7200 秒（2 小时），本客户端在过期前 60 秒自动刷新。

函数/类清单：
    FeishuDriveClient（类）
        - 功能：飞书云文档搜索客户端
        - 继承：SouWenHttpClient
        - 关键属性：ENGINE_NAME = "feishu_drive",
                   BASE_URL = "https://open.feishu.cn",
                   TOKEN_URL = "/open-apis/auth/v3/tenant_access_token/internal"
        - 主要方法：
            search(query, max_results, docs_types) -> WebSearchResponse
            _ensure_token() -> str

    FeishuDriveClient.__init__(app_id, app_secret)
        - 功能：初始化客户端，从参数或配置读取 app_id / app_secret
        - 输入：app_id (str|None)、app_secret (str|None)
        - 异常：缺少凭证时从 ConfigError 降级（由 _search_source 捕获并跳过）

    FeishuDriveClient.search(query, max_results=10, docs_types=None)
            -> WebSearchResponse
        - 功能：调用飞书云文档搜索 API 检索当前应用可见的文档
        - 输入：
            query        关键词；
            max_results  最多返回条数（API 单次上限 50）；
            docs_types   文件类型列表，例如 ["doc","sheet"]；默认不过滤
        - 输出：WebSearchResponse，results 为 WebSearchResult 列表
        - 异常：ConfigError 缺少凭证；其余异常被调用框架捕获不中断聚合

模块依赖：
    - asyncio：异步 I/O
    - logging：日志
    - time：Token 过期判断
    - typing：类型注解
    - souwen.config：获取 app_id / app_secret
    - souwen.core.exceptions：ConfigError
    - souwen.core.http_client：SouWenHttpClient
    - souwen.models：WebSearchResult / WebSearchResponse

技术要点：
    - Token 端点：POST /open-apis/auth/v3/tenant_access_token/internal
    - 搜索端点：POST /open-apis/suite/docs-api/search/object
    - 文档 URL 规则：通过 docs_type + docs_token 拼接：
        doc / docx  → https://docs.feishu.cn/docs/{token}（向后兼容旧格式）
        sheet       → https://docs.feishu.cn/sheets/{token}
        slides      → https://docs.feishu.cn/slides/{token}
        bitable     → https://docs.feishu.cn/base/{token}
        mindnote    → https://docs.feishu.cn/mindnotes/{token}
        file        → https://docs.feishu.cn/drive/file/{token}
    - count 参数范围 [0, 50]，max_results 超出 50 时截断为 50
    - API 地址：https://open.feishu.cn
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from souwen.config import get_config
from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.feishu_drive")

# 飞书 API 各文档类型对应的 URL 前缀
_DOCS_TYPE_URL_PREFIX: dict[str, str] = {
    "doc": "https://docs.feishu.cn/docs",
    "docx": "https://docs.feishu.cn/docs",
    "sheet": "https://docs.feishu.cn/sheets",
    "slides": "https://docs.feishu.cn/slides",
    "bitable": "https://docs.feishu.cn/base",
    "mindnote": "https://docs.feishu.cn/mindnotes",
    "file": "https://docs.feishu.cn/drive/file",
}

# 搜索 API 单次最大返回数
_MAX_COUNT = 50

# Token 提前刷新的秒数（过期前 60s 刷新）
_TOKEN_REFRESH_AHEAD = 60


class FeishuDriveClient(SouWenHttpClient):
    """飞书云文档搜索客户端

    使用飞书自建应用的 app_id + app_secret 完成 OAuth 2.0 client_credentials
    认证，然后通过「搜索云文档」API 检索当前应用可见的文档。

    API 文档：https://open.feishu.cn/document/server-docs/docs/drive-v1/search/document-search

    Args:
        app_id: 飞书应用 App ID；默认从 SOUWEN_FEISHU_APP_ID /
                config.feishu_app_id 读取
        app_secret: 飞书应用 App Secret；默认从 SOUWEN_FEISHU_APP_SECRET /
                    config.feishu_app_secret 读取
    """

    ENGINE_NAME = "feishu_drive"
    BASE_URL = "https://open.feishu.cn"
    TOKEN_URL = "/open-apis/auth/v3/tenant_access_token/internal"
    SEARCH_URL = "/open-apis/suite/docs-api/search/object"

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        config = get_config()
        self.app_id = app_id or config.resolve_api_key("feishu_drive", "feishu_app_id")
        self.app_secret = app_secret or config.feishu_app_secret

        if not self.app_id or not self.app_secret:
            from souwen.core.exceptions import ConfigError

            raise ConfigError(
                key="feishu_app_id / feishu_app_secret",
                service="飞书云文档搜索",
                register_url="https://open.feishu.cn/",
            )

        super().__init__(
            base_url=self.BASE_URL,
            headers={"Content-Type": "application/json; charset=utf-8"},
            source_name="feishu_drive",
        )

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock: asyncio.Lock | None = None

    def _get_token_lock(self) -> asyncio.Lock:
        """获取或创建 Token 刷新锁（懒加载，避免绑定错误的 event loop）"""
        if self._token_lock is None:
            self._token_lock = asyncio.Lock()
        return self._token_lock

    async def _ensure_token(self) -> str:
        """确保拥有有效的 tenant_access_token，过期则自动刷新。

        使用二次检查锁（double-checked locking）避免并发重复刷新。

        Returns:
            有效的 tenant_access_token 字符串

        Raises:
            AuthError: Token 获取或解析失败
        """
        if self._access_token and time.monotonic() < self._token_expires_at - _TOKEN_REFRESH_AHEAD:
            return self._access_token

        async with self._get_token_lock():
            # 二次检查，防止并发时重复刷新
            if (
                self._access_token
                and time.monotonic() < self._token_expires_at - _TOKEN_REFRESH_AHEAD
            ):
                return self._access_token

            logger.debug("正在获取飞书 tenant_access_token")
            resp = await self._client.post(
                self.TOKEN_URL,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )

            if resp.status_code != 200:
                from souwen.core.exceptions import AuthError

                raise AuthError(f"飞书 Token 获取失败: HTTP {resp.status_code} {resp.text[:200]}")

            try:
                data = resp.json()
            except Exception as e:
                from souwen.core.exceptions import AuthError

                raise AuthError(f"飞书 Token 响应解析失败: {e}") from e

            code = data.get("code")
            if code != 0:
                from souwen.core.exceptions import AuthError

                raise AuthError(f"飞书 Token 接口返回错误 code={code}: {data.get('msg', '')}")

            token = data.get("tenant_access_token")
            if not token:
                from souwen.core.exceptions import AuthError

                raise AuthError("飞书 Token 响应缺少 tenant_access_token 字段")

            expires_in = int(data.get("expire", 7200))
            self._access_token = token
            self._token_expires_at = time.monotonic() + expires_in
            logger.debug("飞书 Token 获取成功，有效期 %ds", expires_in)
            return self._access_token

    @staticmethod
    def _build_doc_url(docs_type: str, docs_token: str) -> str:
        """根据文档类型和 Token 拼接飞书文档访问 URL。

        Args:
            docs_type: 飞书文档类型（doc/sheet/slides/bitable/mindnote/file）
            docs_token: 文档 Token

        Returns:
            可访问的文档 URL；未知类型回退到飞书云空间根目录并记录警告
        """
        prefix = _DOCS_TYPE_URL_PREFIX.get(docs_type.lower())
        if prefix is None:
            logger.warning(
                "未知飞书文档类型 %r，URL 回退到通用云空间页面 (token=%s)",
                docs_type,
                docs_token,
            )
            prefix = "https://docs.feishu.cn/drive"
        return f"{prefix}/{docs_token}"

    async def search(
        self,
        query: str,
        max_results: int = 10,
        docs_types: list[str] | None = None,
    ) -> WebSearchResponse:
        """搜索飞书云文档

        调用飞书「搜索云文档」API，检索当前应用可见的文档。

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（不超过 API 上限 50）
            docs_types: 文件类型过滤列表，可选值：doc、sheet、slides、
                        bitable、mindnote、file；传 None 或空列表不过滤

        Returns:
            WebSearchResponse，results 为 WebSearchResult 列表
        """
        count = max(1, min(int(max_results), _MAX_COUNT))
        if count != max_results:
            logger.debug(
                "max_results=%d 已调整为 count=%d（飞书 API 上限 %d）",
                max_results,
                count,
                _MAX_COUNT,
            )

        body: dict[str, Any] = {
            "search_key": query,
            "count": count,
            "offset": 0,
        }
        if docs_types:
            body["docs_types"] = docs_types

        token = await self._ensure_token()
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        results: list[WebSearchResult] = []

        try:
            resp = await self.post(self.SEARCH_URL, json=body, headers=auth_headers)
        except Exception as e:
            logger.warning("飞书云文档搜索请求失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source="feishu_drive",
                results=results,
                total_results=0,
            )

        try:
            payload = resp.json()
        except Exception as e:
            logger.warning("飞书云文档搜索响应解析失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source="feishu_drive",
                results=results,
                total_results=0,
            )

        code = payload.get("code")
        if code != 0:
            logger.warning(
                "飞书云文档搜索 API 返回错误 code=%s, msg=%s (query=%s)",
                code,
                payload.get("msg", ""),
                query,
            )
            return WebSearchResponse(
                query=query,
                source="feishu_drive",
                results=results,
                total_results=0,
            )

        data = payload.get("data") or {}
        entities = data.get("docs_entities") or []
        total = data.get("total", len(entities))

        for item in entities:
            if not isinstance(item, dict):
                continue
            try:
                docs_token = (item.get("docs_token") or "").strip()
                docs_type = (item.get("docs_type") or "").strip()
                title = (item.get("title") or "").strip()

                if not docs_token or not title:
                    continue

                url = self._build_doc_url(docs_type, docs_token)

                results.append(
                    WebSearchResult(
                        source="feishu_drive",
                        title=title,
                        url=url,
                        snippet="",
                        engine=self.ENGINE_NAME,
                        raw={
                            "docs_token": docs_token,
                            "docs_type": docs_type,
                            "owner_id": item.get("owner_id"),
                        },
                    )
                )

                if len(results) >= max_results:
                    break
            except Exception as e:
                logger.debug("飞书云文档单条结果解析失败: %s", e)
                continue

        try:
            total_int = int(total)
        except (TypeError, ValueError):
            total_int = len(results)

        logger.info(
            "飞书云文档搜索返回 %d 条结果 (query=%s, total=%s)",
            len(results),
            query,
            total_int,
        )

        return WebSearchResponse(
            query=query,
            source="feishu_drive",
            results=results,
            total_results=total_int,
        )
