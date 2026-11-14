"""共享 HTML → Markdown/Text 提取工具"""

from __future__ import annotations

import re
from typing import Any

# 可选依赖探测
_HAS_TRAFILATURA = False
_HAS_HTML2TEXT = False

_SCRIPT_BLOCK_RE = re.compile(
    r"<script\b[^>]*>.*?</script\b[^>]*>",
    flags=re.DOTALL | re.IGNORECASE,
)
_STYLE_BLOCK_RE = re.compile(
    r"<style\b[^>]*>.*?</style\b[^>]*>",
    flags=re.DOTALL | re.IGNORECASE,
)

try:
    import trafilatura  # noqa: F401

    _HAS_TRAFILATURA = True
except ImportError:
    pass

try:
    import html2text as _html2text_mod  # noqa: F401

    _HAS_HTML2TEXT = True
except ImportError:
    pass


def _strip_html(html: str) -> str:
    """正则剥离 HTML 标签（零依赖回退）"""
    text = _SCRIPT_BLOCK_RE.sub("", html)
    text = _STYLE_BLOCK_RE.sub("", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_title_from_html(html: str) -> str:
    """从 HTML 的 <title> 标签中提取页面标题"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_from_html(html: str, url: str) -> dict[str, Any]:
    """将原始 HTML 提取为结构化内容

    提取优先级：trafilatura（最佳质量） > html2text > 正则剥离。

    Args:
        html: 原始 HTML 字符串
        url: 源页面 URL（用于 trafilatura 元数据推断）

    Returns:
        字典包含: content, title, author, date, description,
                  content_format ("markdown" | "text")
    """
    # 优先使用 trafilatura（最佳质量）
    if _HAS_TRAFILATURA:
        import trafilatura

        content = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=True,
            include_tables=True,
            include_formatting=True,
            favor_precision=True,
            deduplicate=True,
            with_metadata=False,
        )
        metadata = trafilatura.extract_metadata(html, default_url=url)

        if content:
            return {
                "content": content,
                "title": (metadata.title if metadata else "") or "",
                "author": metadata.author if metadata else None,
                "date": metadata.date if metadata else None,
                "description": (metadata.description if metadata else "") or "",
                "content_format": "markdown",
            }

        # extract 失败时尝试 bare_extraction
        result = trafilatura.bare_extraction(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=True,
            include_tables=True,
            favor_precision=True,
        )
        if result and getattr(result, "text", None):
            return {
                "content": result.text,
                "title": getattr(result, "title", "") or "",
                "author": getattr(result, "author", None),
                "date": getattr(result, "date", None),
                "description": getattr(result, "description", "") or "",
                "content_format": "markdown",
            }

    # 回退到 html2text
    if _HAS_HTML2TEXT:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        md = h.handle(html)
        if md.strip():
            return {
                "content": md.strip(),
                "title": _extract_title_from_html(html),
                "author": None,
                "date": None,
                "description": "",
                "content_format": "markdown",
            }

    # 最终回退：纯正则剥离
    text = _strip_html(html)
    return {
        "content": text,
        "title": _extract_title_from_html(html),
        "author": None,
        "date": None,
        "description": "",
        "content_format": "text",
    }
