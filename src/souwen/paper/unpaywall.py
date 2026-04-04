"""Unpaywall API 客户端

官方文档: https://unpaywall.org/products/api
鉴权: 需邮箱参数 (email)
注册: https://unpaywall.org/products/api
用途: 通过 DOI 查找开放获取 PDF 链接
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError, NotFoundError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import PaperResult, SourceType
from souwen.rate_limiter import TokenBucketLimiter

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
        self.email: str = email or getattr(cfg, "unpaywall_email", "") or ""

        if not self.email:
            raise ConfigError(
                "Unpaywall 邮箱未配置。请前往 "
                f"{_REGISTER_URL} 了解详情，"
                "并设置 unpaywall_email 配置项。"
            )

        self._client = SouWenHttpClient(base_url=_BASE_URL)
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, capacity=_DEFAULT_RPS)

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

        # 最佳 OA 位置
        best_oa = data.get("best_oa_location") or {}
        pdf_url: str | None = (
            best_oa.get("url_for_pdf")
            or best_oa.get("url")
        )

        # 收集所有 OA 位置的 PDF
        all_pdf_urls: list[str] = []
        for loc in data.get("oa_locations", []):
            url = loc.get("url_for_pdf") or loc.get("url")
            if url:
                all_pdf_urls.append(url)

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
            source_id=doi,
            url=data.get("doi_url"),
            pdf_url=pdf_url,
            citation_count=None,
            extra={
                "is_oa": is_oa,
                "oa_status": data.get("oa_status"),
                "journal_name": data.get("journal_name"),
                "publisher": data.get("publisher"),
                "all_pdf_urls": all_pdf_urls,
                "best_oa_host_type": best_oa.get("host_type"),
                "best_oa_version": best_oa.get("version"),
            },
        )
