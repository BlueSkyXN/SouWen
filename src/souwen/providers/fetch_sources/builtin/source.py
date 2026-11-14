"""builtin 通用抓取源（SPEC 7 单模块形态：声明 + Provider + 注册）。

通用抓取的"请求构造与解析"是共享底座（egress 阶梯、IP-pin、提取器链、
robots、大小限制都在其中），位于 runtime_clients/web/builtin.py 并同
时服务 fetch 编排层；本模块声明源身份并注册它。
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from souwen.common_runtime.errors import SouWenError
from souwen.common_runtime.transport.errors import RateLimitError, SourceUnavailableError
from souwen.config import SouWenConfig
from souwen.platform.manifest_registry import ProviderManifest
from souwen.platform.provider_spi import (
    ContentMetadata,
    ExecutionContext,
    FetchResult,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    ProviderProbe,
    Provenance,
    RequestContext,
)
from souwen.providers.runtime_clients.web._extractor_chain import content_quality
from souwen.providers.runtime_clients.web.builtin import BuiltinFetcherClient

BUILTIN_FETCH_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "builtin-fetch",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "builtin-fetch",
                "capability": "fetch",
                "export": "BuiltinFetchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "builtin-fetch-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        # Targets are request-specific and validated before every connection.
        "network": {"egress_hosts": [], "proxy_supported": True, "browser_required": False},
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["builtin-fetch-provider-config-v1"],
        },
    }
)


_PROVIDER_ID = "builtin-fetch"
_DEFAULT_MAX_CODE_POINTS = 200_000


class BuiltinFetchClientProtocol(Protocol):
    async def fetch(
        self,
        url: str,
        timeout: float = 30.0,
        start_index: int = 0,
        max_length: int | None = None,
        respect_robots_txt: bool | None = None,
        selector: str | None = None,
        enforce_target_contract: bool = False,
    ) -> Any:
        """Return a existing FetchResult produced by the safe redirect pipeline."""


class BuiltinFetchProvider:
    """Fetch one target with mandatory target media, size, and URL policy."""

    capability = "fetch"

    def __init__(
        self,
        client: BuiltinFetchClientProtocol,
        *,
        enabled: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._closed = False

    async def fetch(
        self,
        request: FetchTargetRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchResult:
        execution.raise_if_cancelled_or_expired()
        if self._closed or not self._enabled:
            raise ProviderError(ProviderErrorCode.INVALID_CONFIG, provider_id=_PROVIDER_ID)
        max_code_points = (
            request.content.max_code_points
            if request.content is not None and request.content.max_code_points is not None
            else _DEFAULT_MAX_CODE_POINTS
        )
        try:
            receipt = await asyncio.wait_for(
                self._client.fetch(
                    str(request.target),
                    timeout=min(30.0, execution.remaining_seconds),
                    max_length=max_code_points,
                    respect_robots_txt=(
                        request.policy.respect_robots if request.policy is not None else None
                    ),
                    enforce_target_contract=True,
                ),
                timeout=execution.remaining_seconds,
            )
            execution.raise_if_cancelled_or_expired()
            return _canonical_result(
                receipt,
                request=request,
                context=context,
                retrieved_at=self._clock(),
            )
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except (asyncio.TimeoutError, TimeoutError):
            raise ProviderError(
                ProviderErrorCode.DEADLINE_EXCEEDED,
                provider_id=_PROVIDER_ID,
            ) from None
        except RateLimitError as exc:
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id=_PROVIDER_ID,
                retry_after_seconds=getattr(exc, "retry_after", None),
            ) from None
        except SourceUnavailableError:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_id=_PROVIDER_ID,
            ) from None
        except (AttributeError, TypeError, ValueError):
            raise ProviderError(
                ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
                provider_id=_PROVIDER_ID,
            ) from None
        except SouWenError:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_id=_PROVIDER_ID,
            ) from None
        except Exception:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_id=_PROVIDER_ID,
            ) from None

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        execution.raise_if_cancelled_or_expired()
        return ProviderProbe(
            provider=_PROVIDER_ID,
            capability="fetch",
            status="unavailable" if self._closed or not self._enabled else "available",
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        closer = getattr(self._client, "close", None) or getattr(self._client, "aclose", None)
        if closer is None:
            return
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            self._closed = False
            raise


def _canonical_result(
    receipt: Any,
    *,
    request: FetchTargetRequest,
    context: RequestContext,
    retrieved_at: datetime,
) -> FetchResult:
    del context
    raw = getattr(receipt, "raw", None)
    if not isinstance(raw, dict):
        raise ValueError("missing target receipt metadata")
    error_code = raw.get("target_error_code")
    if getattr(receipt, "error", None):
        code = {
            "policy_blocked": ProviderErrorCode.POLICY_BLOCKED,
            "response_too_large": ProviderErrorCode.PAYLOAD_TOO_LARGE,
            "unsupported_media_type": ProviderErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "empty_content": ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
        }.get(error_code, ProviderErrorCode.PROVIDER_UNAVAILABLE)
        raise ProviderError(code, provider_id=_PROVIDER_ID)

    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ProviderError(
            ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
            provider_id=_PROVIDER_ID,
        )
    media_type = raw.get("media_type")
    if not isinstance(media_type, str) or not media_type:
        raise ValueError("missing media type")
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at must be timezone-aware")
    final_url = getattr(receipt, "final_url", None)
    return FetchResult(
        target=request.target,
        final_url=final_url,
        status="success",
        title=getattr(receipt, "title", None) or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type=media_type,
            charset=raw.get("charset") if isinstance(raw.get("charset"), str) else None,
            retrieved_at=retrieved_at,
            truncated=bool(getattr(receipt, "content_truncated", False)),
            content_length=(
                raw.get("content_length_bytes")
                if isinstance(raw.get("content_length_bytes"), int)
                else None
            ),
            quality=content_quality(content),
        ),
        provenance=(
            Provenance(
                provider=_PROVIDER_ID,
                attempt=1,
                outcome="success",
                retrieved_at=retrieved_at,
            ),
        ),
    )


__all__ = ["BuiltinFetchProvider", "BuiltinFetchClientProtocol"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, reviewed_proxy
    return BuiltinFetchProvider(
        BuiltinFetcherClient(respect_robots_txt=config.respect_robots_txt),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = BUILTIN_FETCH_MANIFEST
SPEC = None
PROVIDER_TYPE = BuiltinFetchProvider

# 抓取主干：不可用时 readiness 必须报 not_ready（SPEC 7 声明驱动）。
READINESS_REQUIRED = True

__all__ = ["MANIFEST", "PROVIDER_TYPE", "READINESS_REQUIRED", "SPEC", "build_provider"]
