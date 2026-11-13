"""Fetch-ladder browser executor backed by the in-process Playwright pool."""

from __future__ import annotations

from datetime import datetime, timezone

from souwen.common_runtime.provider_support.browser_fetch import (
    BrowserAcquisitionError,
    fetch_page_content,
)


class InProcessBrowserFetchExecutor:
    """``BrowserFetchExecutor`` port backed by the in-process pool."""

    def __init__(self, *, proxy_provider=None) -> None:
        self._proxy_provider = proxy_provider

    def _proxy(self) -> str | None:
        if self._proxy_provider is not None:
            return self._proxy_provider()
        from souwen.config import get_config

        return get_config().get_proxy()

    async def fetch(
        self,
        request,
        request_context,
        execution,
    ):
        from souwen.platform.provider_spi import (
            ContentMetadata,
            FetchResult,
            ProviderError,
            ProviderErrorCode,
            Provenance,
        )

        if request.policy is not None and request.policy.respect_robots is True:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)
        max_code_points = (
            request.content.max_code_points
            if request.content is not None and request.content.max_code_points is not None
            else 200_000
        )
        try:
            outcome = await fetch_page_content(
                str(request.target),
                max_code_points=max_code_points,
                timeout_seconds=30.0,
                proxy=self._proxy(),
            )
        except BrowserAcquisitionError as exc:
            code = {
                "policy_blocked": ProviderErrorCode.POLICY_BLOCKED,
                "browser_timeout": ProviderErrorCode.DEADLINE_EXCEEDED,
            }.get(exc.code, ProviderErrorCode.PROVIDER_UNAVAILABLE)
            raise ProviderError(code, provider_id="builtin-fetch") from None
        retrieved_at = datetime.now(timezone.utc)
        return FetchResult(
            target=request.target,
            final_url=outcome.final_url,
            status="success",
            title=outcome.title,
            content=outcome.content,
            content_metadata=ContentMetadata(
                media_type=outcome.media_type,
                charset=outcome.charset,
                retrieved_at=retrieved_at,
                truncated=outcome.truncated,
                content_length=len(outcome.content.encode()),
                quality="low" if len(outcome.content.strip()) <= 63 else "high",
            ),
            provenance=(
                Provenance(
                    provider="builtin-fetch",
                    attempt=2,
                    outcome="success",
                    retrieved_at=retrieved_at,
                ),
            ),
        )

    async def readiness(self, request_context, execution):  # pragma: no cover - trivial
        from souwen.platform.provider_spi import ProviderProbe

        return ProviderProbe(provider="builtin-fetch", capability="fetch", status="available")


__all__ = ["InProcessBrowserFetchExecutor"]
