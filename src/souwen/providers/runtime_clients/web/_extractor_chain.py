"""Main-content extractor chain: trafilatura → readability → newspaper.

SPEC 4.2: extraction is an internal chain; the first extractor producing
enough body wins, otherwise the longest result is kept. The helpers also
detect verification interstitials and JS shells so the fetch ladder can
escalate the egress level instead of returning junk.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("souwen.providers.runtime_clients.web.extractor_chain")

# SPEC 4.3：提取正文短于该阈值视为失败，触发升级
MIN_BODY_CHARS = 200

_VERIFICATION_MARKERS = (
    "just a moment",
    "attention required",
    "verify you are a human",
    "access denied",
    "captcha",
    "unusual traffic",
    "enable javascript and cookies",
    "checking your browser",
    "robot policy",
)


def _count_words(text: str) -> int:
    return len([word for word in text.split() if word])


def _sufficient(content: str | None) -> bool:
    return bool(content) and len(content.strip()) >= MIN_BODY_CHARS


def _trafilatura(html: str, url: str) -> dict[str, Any]:
    from souwen.providers.runtime_clients.web.builtin import _extract_with_trafilatura

    return _extract_with_trafilatura(html, url)


def _readability(html: str, url: str) -> dict[str, Any] | None:
    try:
        from souwen.providers.runtime_clients.web.readability_fetcher import (
            _extract_with_readability_sync,
        )
    except Exception:
        return None
    try:
        return asyncio.get_running_loop().run_in_executor(
            None, _extract_with_readability_sync, html, url
        )
    except RuntimeError:
        return None


def _newspaper(html: str, url: str) -> dict[str, Any] | None:
    try:
        import newspaper
    except Exception:
        return None

    def _run() -> dict[str, Any]:
        try:
            article = newspaper.article(url, input_html=html)
        except Exception:
            return {}
        text = getattr(article, "text", "") or ""
        if not text.strip():
            return {}
        return {
            "content": text,
            "title": getattr(article, "title", "") or "",
            "content_format": "text",
        }

    try:
        return asyncio.get_running_loop().run_in_executor(None, _run)
    except RuntimeError:
        return None


def _normalize(extracted: dict[str, Any] | None) -> dict[str, Any]:
    base = {
        "content": "",
        "title": "",
        "author": None,
        "date": None,
        "description": "",
        "content_format": "text",
    }
    if extracted:
        for key in base:
            if extracted.get(key):
                base[key] = extracted[key]
    return base


async def extract_body(html: str, url: str) -> dict[str, Any]:
    """Run the extractor chain and return the first sufficient result.

    Falls back to the longest insufficient result so short-but-real pages
    (config pages, plain text) still surface instead of erroring.
    """

    candidates: list[dict[str, Any]] = []

    first = _normalize(_trafilatura(html, url))
    candidates.append(first)
    if _sufficient(first.get("content")):
        return first

    readability_future = _readability(html, url)
    if readability_future is not None:
        try:
            second = _normalize(await readability_future)
        except Exception:
            second = None
        if second is not None:
            candidates.append(second)
            if _sufficient(second.get("content")):
                return second

    newspaper_future = _newspaper(html, url)
    if newspaper_future is not None:
        try:
            third = _normalize(await newspaper_future)
        except Exception:
            third = None
        if third is not None:
            candidates.append(third)
            if _sufficient(third.get("content")):
                return third

    best = max(candidates, key=lambda item: len(item.get("content") or ""))
    return best


def looks_like_blocked_content(html: str, content: str | None) -> bool:
    """Detect verification interstitials and JS shells (SPEC 4.3).

    - The extracted body is short while the page itself is large (JS shell).
    - Title or body carries a known anti-bot interstitial marker.
    """

    body = (content or "").strip()
    if body and len(body) >= MIN_BODY_CHARS:
        return False
    haystack = f"{body}\n{html[:4000]}".lower()
    if any(marker in haystack for marker in _VERIFICATION_MARKERS):
        return True
    # 正文很短而原始 HTML 很大：大概率是 JS 空壳
    return len(html) > 20_000 and len(body) < MIN_BODY_CHARS


__all__ = ["MIN_BODY_CHARS", "extract_body", "looks_like_blocked_content"]
