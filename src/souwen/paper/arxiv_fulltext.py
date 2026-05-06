"""arXiv 论文全文获取模块

支持两种获取方式：
1. HTML 版本（优先）：从 ``https://arxiv.org/html/{paper_id}`` 获取，
   用 BeautifulSoup 提取纯文本（剥离 nav/header/footer/script/style）。
2. PDF 回退：从 ``https://arxiv.org/pdf/{paper_id}`` 下载 PDF，
   用 ``pymupdf4llm`` 转换为 Markdown（可选依赖，未安装则只返回原始字节大小提示）。

文件用途：为 SouWen 提供论文全文获取能力，支持后续的全文分析和知识提取。

函数/类清单：
    ArxivFulltextClient（类，async context manager）
        - 功能：HTML 优先 + PDF 回退的 arXiv 全文抓取
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
    - pymupdf4llm: PDF→Markdown 转换（可选依赖，[pdf] extra）
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResult
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_HTML_BASE = "https://arxiv.org/html"
_PDF_BASE = "https://arxiv.org/pdf"
_ABS_BASE = "https://arxiv.org/abs"

# arXiv 要求至少 3 秒间隔（与 ArxivClient 一致）
_RATE_LIMIT_RPS = 1.0 / 3.0

# HTML 中需要剥离的标签（噪音 / 非正文）
_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "noscript", "form")


class ArxivFulltextClient:
    """arXiv 全文抓取客户端（HTML 优先，PDF 回退）。"""

    def __init__(self) -> None:
        """初始化客户端，使用与 arXiv API 相同的 3 秒限流。"""
        # 不绑定 base_url，便于 HTML/PDF 分别访问完整地址
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

    @staticmethod
    def _pdf_to_markdown(pdf_bytes: bytes) -> str | None:
        """用 pymupdf4llm 将 PDF 字节流转为 Markdown。

        可选依赖：未安装时返回 None，由调用方决定回退方案。
        """
        try:
            import pymupdf4llm  # type: ignore
            import pymupdf  # type: ignore
        except ImportError:
            logger.warning('pymupdf4llm 未安装，无法转换 PDF；可执行 `pip install -e ".[pdf]"`')
            return None

        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            md = pymupdf4llm.to_markdown(doc)
            doc.close()
            return md
        except Exception as exc:
            logger.warning("pymupdf4llm 转换失败: %s", exc)
            return None

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
        pdf_url = f"{_PDF_BASE}/{paper_id}"

        # ── 1. HTML 优先 ────────────────────────────────────────────
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

        # ── 2. PDF 回退 ─────────────────────────────────────────────
        await self._limiter.acquire()
        try:
            pdf_resp = await self._client.get(pdf_url)
        except Exception as exc:
            return FetchResult(
                url=abs_url,
                final_url=pdf_url,
                source="arxiv_fulltext",
                error=f"PDF 请求失败: {exc}",
            )

        if pdf_resp.status_code != 200:
            return FetchResult(
                url=abs_url,
                final_url=str(pdf_resp.url),
                source="arxiv_fulltext",
                error=f"PDF 抓取返回 HTTP {pdf_resp.status_code}",
            )

        markdown = self._pdf_to_markdown(pdf_resp.content)
        if markdown is None:
            return FetchResult(
                url=abs_url,
                final_url=str(pdf_resp.url),
                source="arxiv_fulltext",
                error='pymupdf4llm 不可用或转换失败；请执行 `pip install -e ".[pdf]"`',
                raw={"variant": "pdf", "paper_id": paper_id, "pdf_size": len(pdf_resp.content)},
            )

        return FetchResult(
            url=abs_url,
            final_url=str(pdf_resp.url),
            title="",  # PDF 无独立标题元数据，留空
            content=markdown,
            content_format="markdown",
            source="arxiv_fulltext",
            snippet=markdown[:500],
            raw={"variant": "pdf", "paper_id": paper_id, "pdf_size": len(pdf_resp.content)},
        )
