"""可选：注册 fetch handler 以支持 `souwen fetch -p example_echo`。"""

from __future__ import annotations

from typing import Any

from souwen.models import FetchResponse, FetchResult


async def example_echo_handler(
    urls: list[str],
    timeout: float = 30.0,
    **kwargs: Any,
) -> FetchResponse:
    results = [
        FetchResult(
            url=u,
            final_url=u,
            source="example_echo",
            title=f"Echo: {u}",
            content=f"# Echo\n\nURL: {u}",
            content_format="markdown",
            snippet=f"Echo response for {u}",
        )
        for u in urls
    ]
    return FetchResponse(
        urls=urls,
        results=results,
        total=len(results),
        total_ok=len(results),
        total_failed=0,
        provider="example_echo",
    )


def register() -> None:
    """注册 fetch handler — 插件 __init__.py 或 conftest 中调用。"""
    from souwen.web.fetch import register_fetch_handler
    register_fetch_handler("example_echo", example_echo_handler)
