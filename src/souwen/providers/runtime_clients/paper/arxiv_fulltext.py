"""arXiv 论文全文获取模块

从 ``https://arxiv.org/html/{paper_id}`` 获取 HTML 版本，并用 BeautifulSoup
提取纯文本（剥离 nav/header/footer/script/style）。不解析或下载 PDF。

文件用途：为 SouWen 提供论文全文获取能力，支持后续的全文分析和知识提取。

函数/类清单：
    ArxivFulltextClient（类，async context manager）
        - 功能：arXiv HTML 全文抓取
        - 关键属性：_client (SouWenHttpClient), _limiter (TokenBucketLimiter,
                   1 req / 3 sec，与 ArxivClient 同步)

    get_fulltext(paper_id: str) -> FetchResult
        - 功能：按 paper_id 获取论文全文
        - 输入：paper_id 形如 ``2301.00001`` 或带版本号 ``2301.00001v2``
        - 输出：FetchResult，content 字段为 Markdown 或纯文本

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器（与 arxiv.py 共享 3s 间隔）
    - BeautifulSoup4: HTML 解析（核心依赖）
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.providers.runtime_clients.models import FetchResult
from souwen.common_runtime.provider_support.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_HTML_BASE = "https://arxiv.org/html"
_ABS_BASE = "https://arxiv.org/abs"

# arXiv 要求至少 3 秒间隔（与 ArxivClient 一致）
_RATE_LIMIT_RPS = 1.0 / 3.0

# HTML 中需要剥离的标签（噪音 / 非正文）
_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "noscript", "form")


class ArxivFulltextClient:
    """arXiv HTML 全文抓取客户端。"""

    def __init__(self) -> None:
        """初始化客户端，使用与 arXiv API 相同的 3 秒限流。"""
        # 不绑定 base_url，便于访问完整 arXiv HTML URL。
        self._client = SouWenHttpClient(source_name="arxiv_fulltext")
        self._limiter = TokenBucketLimiter(rate=_RATE_LIMIT_RPS, burst=1.0)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ArxivFulltextClient:
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
    def _extract_html_text(html: str) -> tuple[str, str]:
        """从 arXiv HTML 渲染页提取标题和正文纯文本。

        Returns:
            (title, text) 元组。
        """
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.find("title")
        title = title_el.get_text(strip=True) if title_el else ""

        for tag in soup(list(_STRIP_TAGS)):
            tag.decompose()

        body = soup.find("body") or soup
        # 用换行分隔块级元素，避免段落首尾粘连
        text = body.get_text(separator="\n", strip=True)
        # 合并多余空行
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return title, "\n".join(lines)

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def get_fulltext(self, paper_id: str) -> FetchResult:
        """按 arXiv ID 获取论文全文。

        Args:
            paper_id: arXiv ID（如 ``2301.00001`` 或 ``2301.00001v2``）。

        Returns:
            FetchResult。失败时 ``error`` 字段被填充，``content`` 为空。
        """
        abs_url = f"{_ABS_BASE}/{paper_id}"
        html_url = f"{_HTML_BASE}/{paper_id}"
        error = "arXiv HTML 请求失败"
        # ── HTML ────────────────────────────────────────────────────
        await self._limiter.acquire()
        try:
            html_resp = await self._client.get(html_url)
        except Exception as exc:
            logger.warning("arXiv HTML 请求失败: %s", exc)
            html_resp = None

        if html_resp is not None and html_resp.status_code == 200:
            try:
                title, text = self._extract_html_text(html_resp.text)
                return FetchResult(
                    url=abs_url,
                    final_url=str(html_resp.url),
                    title=title,
                    content=text,
                    content_format="text",
                    source="arxiv_fulltext",
                    snippet=text[:500],
                    raw={"variant": "html", "paper_id": paper_id},
                )
            except Exception as exc:
                logger.warning("arXiv HTML 解析失败: %s", exc)
                error = "arXiv HTML 解析失败"
        elif html_resp is not None:
            error = f"arXiv HTML 抓取返回 HTTP {html_resp.status_code}"

        return FetchResult(
            url=abs_url,
            final_url=str(html_resp.url) if html_resp is not None else html_url,
            source="arxiv_fulltext",
            error=error,
            raw={"variant": "html", "paper_id": paper_id},
        )
