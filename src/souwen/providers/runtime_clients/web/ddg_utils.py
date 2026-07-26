"""DuckDuckGo 搜索共享工具

VQD token 提取、HTML 表单解析、URL/文本规范化等
供 DuckDuckGo 系列搜索客户端共用。
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote


# VQD 提取正则 — 多模式覆盖 DDG 轮换格式
_VQD_PATTERNS = [
    re.compile(rb'vqd="([^"]+)"'),
    re.compile(rb"vqd='([^']+)'"),
    re.compile(rb"vqd=([^&]+)&"),
    re.compile(rb'"vqd":"([^"]+)"'),
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")


def extract_vqd(html_bytes: bytes, keywords: str) -> str | None:
    """从 DuckDuckGo 首页 HTML 中提取 VQD token

    VQD 是 DuckDuckGo JSON 搜索接口（images/news/videos）的认证令牌。
    DDG 轮换嵌入格式，因此尝试多种正则模式。

    Args:
        html_bytes: 首页响应的原始字节
        keywords: 搜索关键词（用于调试日志）

    Returns:
        VQD token 字符串，未找到则返回 None
    """
    for pattern in _VQD_PATTERNS:
        m = pattern.search(html_bytes)
        if m:
            return m.group(1).decode()
    return None


def normalize_url(url: str) -> str:
    """规范化 URL — 解码 + 去除多余空格"""
    if not url:
        return ""
    url = unquote(url)
    url = url.replace(" ", "+")
    return url.strip()


def normalize_text(html_text: str) -> str:
    """规范化文本 — 去 HTML 标签 + 反转义 + 压缩空白"""
    if not html_text:
        return ""
    text = _HTML_TAG_RE.sub("", html_text)
    text = unescape(text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def parse_next_form_data(html_bytes: bytes) -> dict[str, str] | None:
    """从 DuckDuckGo HTML 响应中提取分页表单的隐藏字段

    DDG HTML 版本的「下一页」是一个含有多个 hidden input 的 form。
    我们需要原样回传所有 hidden 字段作为下一次 POST 的表单数据。

    Args:
        html_bytes: 响应的原始 HTML 字节

    Returns:
        隐藏字段字典 {name: value}，未找到分页表单则返回 None
    """
    # 快速查找：包含 "next" 相关表单
    from lxml import html as lxml_html

    try:
        tree = lxml_html.fromstring(html_bytes)
    except Exception:
        return None

    # html 后端: div.nav-link 里的 form
    nav_forms = tree.xpath('//div[@class="nav-link"]//form')
    if not nav_forms:
        # lite 后端: form 包含 value 含 "ext" 或 "Next" 的 input
        nav_forms = tree.xpath("//form[.//input[contains(@value, 'ext')]]")
    if not nav_forms:
        return None

    form = nav_forms[-1]  # 取最后一个（"Next" 而非 "Previous"）
    inputs = form.xpath(".//input[@type='hidden']")
    if not inputs:
        return None

    data: dict[str, str] = {}
    for inp in inputs:
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            data[name] = value
    return data if data else None


def build_filter_string(*tokens: str | None) -> str:
    """构建 DDG JSON 接口的过滤字符串

    Args:
        *tokens: 各过滤维度的值（None 或空字符串表示不过滤该维度）

    Returns:
        逗号分隔的过滤字符串，例如 "time:Day,,size:Large,,,,"
    """
    parts = []
    for t in tokens:
        parts.append(t if t else "")
    return ",".join(parts)


def parse_next_offset(next_url: str | None) -> str | None:
    """从 JSON 接口的 next URL 中解析分页偏移量

    Args:
        next_url: 响应中的 next 字段（如 "i.js?s=100&..."）

    Returns:
        偏移量字符串，无法解析则返回 None
    """
    if not next_url:
        return None
    # 查找 s=NNN
    m = re.search(r"[?&]s=(\d+)", next_url)
    return m.group(1) if m else None
