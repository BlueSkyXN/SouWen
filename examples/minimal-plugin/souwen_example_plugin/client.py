"""Echo 客户端 — 仅回显 URL，演示 Client 合约。"""

from __future__ import annotations

from souwen.models import FetchResponse, FetchResult


class EchoClient:
    """最小 fetch 客户端实现。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def fetch(
        self,
        urls: list[str],
        timeout: float = 30.0,
        **kwargs,
    ) -> FetchResponse:
        results = [
            FetchResult(
                url=u,
                final_url=u,
                source="example_echo",
                title=f"Echo: {u}",
                content=f"# Echo\n\nURL: {u}\n\n此内容由示例插件生成。",
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
