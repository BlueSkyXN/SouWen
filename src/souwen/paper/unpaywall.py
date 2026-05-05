"""Unpaywall API 客户端

官方文档: https://unpaywall.org/products/api
鉴权: 需邮箱参数 (email)
注册: https://unpaywall.org/products/api
用途: 通过 DOI 查找开放获取 PDF 链接

文件用途：Unpaywall 开放获取 PDF 查找客户端，查询论文的合法 OA 版本。

函数/类清单：
    UnpaywallClient（类）
        - 功能：Unpaywall OA PDF 查找客户端，通过 DOI 查询论文的开放获取版本
        - 关键属性：email (str) 注册邮箱（API 鉴权用），_client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（~1 req/s，100K req/day）

    find_oa(doi: str) -> PaperResult
        - 功能：通过 DOI 查找论文的开放获取 PDF 链接
        - 输入：doi 论文 DOI（如 "10.1038/s41586-021-03819-2"）
        - 输出：PaperResult 模型，其中 pdf_url 为 OA PDF 链接（若可用）
        - 异常：NotFoundError DOI 不存在或 ParseError 响应解析失败时抛出
        - 说明：返回的 PaperResult.raw 包含 is_oa/oa_status/all_pdf_urls 等元数据

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - ConfigError, NotFoundError, ParseError: 异常类
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import PaperResult, SourceType
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.unpaywall.org/v2"
_REGISTER_URL = "https://unpaywall.org/products/api"

# Unpaywall 限流: 100,000 req/day ≈ ~1.15 req/s，保守设为 1
_DEFAULT_RPS = 1.0


class UnpaywallClient:
    """Unpaywall 开放获取 PDF 查找客户端。

    通过 DOI 查询论文是否有免费合法的 OA 版本，返回 PDF 下载链接。

    Raises:
        ConfigError: 未配置 unpaywall_email 时抛出。
    """

    def __init__(self, email: str | None = None) -> None:
        """初始化 Unpaywall 客户端。

        Args:
            email: 注册邮箱，用于 API 鉴权。未提供时从全局配置读取。

        Raises:
            ConfigError: 邮箱未配置。
        """
        cfg = get_config()
        self.email: str = email or cfg.resolve_api_key("unpaywall", "unpaywall_email") or ""

        if not self.email:
            raise ConfigError(
                key="unpaywall_email",
                service="Unpaywall",
                register_url=_REGISTER_URL,
            )

        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="unpaywall")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> UnpaywallClient:
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
    # 公开方法
    # ------------------------------------------------------------------

    async def find_oa(self, doi: str) -> PaperResult:
        """通过 DOI 查找开放获取 PDF。

        Args:
            doi: 论文 DOI，例如 ``"10.1038/s41586-021-03819-2"``。

        Returns:
            PaperResult 模型，其中 ``pdf_url`` 为 OA PDF 链接（若可用）。

        Raises:
            NotFoundError: DOI 不存在或未找到 OA 版本。
            ParseError: 响应解析失败。
        """
        await self._limiter.acquire()

        params = {"email": self.email}
        resp = await self._client.get(f"/{doi}", params=params)

        if resp.status_code == 404:
            raise NotFoundError(f"Unpaywall 未找到 DOI: {doi}")

        try:
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            raise ParseError(f"Unpaywall 响应解析失败: {exc}") from exc

        # 提取最佳 OA 位置（Unpaywall 已预处理选择最佳来源）
        best_oa = data.get("best_oa_location") or {}
        # 优先使用 url_for_pdf，其次使用 url
        pdf_url: str | None = best_oa.get("url_for_pdf") or best_oa.get("url")

        # 收集所有可用的 OA PDF 链接（用于备选）
        all_pdf_urls: list[str] = []
        for loc in data.get("oa_locations", []):
            url = loc.get("url_for_pdf") or loc.get("url")
            if url:
                all_pdf_urls.append(url)

        # 检查是否标记为 OA
        is_oa: bool = data.get("is_oa", False)

        if not is_oa:
            logger.info("DOI %s 在 Unpaywall 中标记为非 OA", doi)

        return PaperResult(
            title=data.get("title", ""),
            authors=[],  # Unpaywall 返回的作者信息有限
            abstract="",
            doi=doi,
            year=data.get("year"),
            publication_date=data.get("published_date"),
            source=SourceType.UNPAYWALL,
            source_url=data.get("doi_url", ""),
            pdf_url=pdf_url,
            citation_count=None,
            journal=data.get("journal_name") or None,
            raw={
                "is_oa": is_oa,
                "oa_status": data.get("oa_status"),
                "journal_name": data.get("journal_name"),
                "publisher": data.get("publisher"),
                "all_pdf_urls": all_pdf_urls,
                "best_oa_host_type": best_oa.get("host_type"),
                "best_oa_version": best_oa.get("version"),
            },
        )
