"""jina_reader（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.security import validate_fetch_url
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import (
    ClientFetchProviderSpec,
    ClientTransportDeclaration,
    ClientFetchProvider,
    ClientFetchSpec,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation
from souwen.platform.provider_spi import (
    ContentMetadata,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
)
from souwen.providers.runtime_clients.models import FetchResponse, FetchResult
from souwen.providers.runtime_clients.web._extractor_chain import content_quality
from typing import TYPE_CHECKING, Any, Protocol
from souwen.platform.provider_spi import FetchResult as ProviderFetchResult


from souwen.platform.manifest_registry import ProviderManifest

JINA_READER_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "jina_reader",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "jina-reader-fetch",
                "capability": "fetch",
                "export": "JinaReaderFetchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "jina-reader-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["JINA_API_KEY"]},
        "network": {
            "egress_hosts": ["r.jina.ai"],
            "min_egress": "impersonate",
            "max_egress": "proxy",
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["jina-reader-provider-config-v1"],
        },
    }
)

__all__ = ["JINA_READER_PROVIDER_MANIFEST"]


JINA_READER_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="jina_reader",
    adapter_id="jina-reader-fetch",
    adapter_reason="Jina Reader path encoding and response variants remain in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        host="r.jina.ai", protocol="json", operations=(HttpOperation(method="GET", endpoint="/"),)
    ),
    auth=AuthDeclaration(
        placement="bearer", reference="JINA_API_KEY", field_name="Authorization", required=False
    ),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["JINA_READER_FETCH_PROFILE"]


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class JinaReaderClient(SouWenHttpClient):
    """Jina Reader 内容抓取客户端

    通过 r.jina.ai 代理服务将网页转换为干净的 Markdown 文本。
    免费可用，设置 API Key 可提升限额。
    """

    ENGINE_NAME = "jina_reader"
    BASE_URL = "https://r.jina.ai"
    PROVIDER_NAME = "jina_reader"

    def __init__(self, api_key: str | None = None) -> None:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "X-Return-Format": "markdown",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        super().__init__(
            base_url=self.BASE_URL,
            source_name="jina_reader",
            headers=headers,
        )
        self._api_key = api_key

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL 的内容

        Args:
            url: 目标网页 URL
            timeout: 超时秒数

        Returns:
            FetchResult 包含提取的 Markdown 内容
        """
        from souwen.providers.runtime_clients.web.fetch import ssrf_blocked_fetch_result

        blocked = ssrf_blocked_fetch_result(url, self.PROVIDER_NAME)
        if blocked is not None:
            return blocked

        try:
            resp = await self.get(f"/{url}")
            # Jina Reader JSON 响应格式:
            # { "code": 200, "status": ..., "data": { "title": ..., "content": ..., "url": ... } }
            data = resp.json()
            if isinstance(data, dict):
                inner = data.get("data", data)
                content = inner.get("content", "")
                title = inner.get("title", "")
                final_url = inner.get("url", url)
                snippet = content[:500] if content else ""
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    title=title,
                    content=content,
                    content_format="markdown",
                    source=self.PROVIDER_NAME,
                    snippet=snippet,
                    published_date=inner.get("publishedTime"),
                    author=inner.get("author"),
                    raw={"provider": "jina_reader", "has_key": bool(self._api_key)},
                )
            # 纯文本响应回退
            text = resp.text
            return FetchResult(
                url=url,
                final_url=url,
                content=text,
                content_format="markdown",
                source=self.PROVIDER_NAME,
                snippet=text[:500],
                raw={"provider": "jina_reader", "format": "plain"},
            )
        except Exception as exc:
            logger.warning("Jina Reader fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 5,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数（Jina 免费 ~20 RPM）
            timeout: 每个 URL 超时

        Returns:
            FetchResponse 聚合结果
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.fetch(u, timeout=timeout)

        results = await asyncio.gather(*[_fetch_one(u) for u in urls])
        result_list = list(results)
        ok = sum(1 for r in result_list if r.error is None)
        return FetchResponse(
            urls=urls,
            results=result_list,
            total=len(result_list),
            total_ok=ok,
            total_failed=len(result_list) - ok,
            provider=self.PROVIDER_NAME,
        )


class JinaReaderClientProtocol(Protocol):
    async def fetch(self, url: str, timeout: float = 30.0) -> Any: ...
    async def close(self) -> None: ...


class JinaReaderFetchProvider(ClientFetchProvider):
    capability = "fetch"

    def __init__(self, client: JinaReaderClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _FETCH_SPEC, enabled=enabled)


async def _invoke(client: Any, request: FetchTargetRequest) -> Any:
    return await client.fetch(_target(request), timeout=30.0)


def _project(
    receipt: Any, request: FetchTargetRequest, context: RequestContext
) -> ProviderFetchResult:
    del context
    return _result(receipt, request, JINA_READER_FETCH_PROFILE.provider_id)


def _target(request: FetchTargetRequest) -> str:
    target = str(request.target)
    if not validate_fetch_url(target)[0]:
        raise ProviderError(
            ProviderErrorCode.POLICY_BLOCKED, provider_id=JINA_READER_FETCH_PROFILE.provider_id
        )
    return target


def _result(receipt: Any, request: FetchTargetRequest, provider_id: str) -> ProviderFetchResult:
    if getattr(receipt, "source", None) != provider_id:
        raise ValueError("unexpected existing source")
    if getattr(receipt, "error", None):
        raw = getattr(receipt, "raw", None)
        code = (
            ProviderErrorCode.POLICY_BLOCKED
            if isinstance(raw, dict) and raw.get("blocked_by_ssrf")
            else ProviderErrorCode.PROVIDER_UNAVAILABLE
        )
        raise ProviderError(code, provider_id=provider_id)
    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("invalid existing receipt content")
    final_url = getattr(receipt, "final_url", None)
    if not isinstance(final_url, str) or not validate_fetch_url(final_url)[0]:
        raise ValueError("invalid existing final URL")
    content_format = getattr(receipt, "content_format", None)
    media_type = {"text": "text/plain", "markdown": "text/markdown"}.get(content_format)
    if media_type is None:
        raise ValueError("invalid existing content format")
    retrieved_at = datetime.now(timezone.utc)
    title = getattr(receipt, "title", None)
    if title is not None and not isinstance(title, str):
        raise ValueError("invalid existing title")
    return ProviderFetchResult(
        target=request.target,
        final_url=final_url,
        status="success",
        title=title or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type=media_type,
            retrieved_at=retrieved_at,
            truncated=False,
            content_length=len(content.encode()),
            quality=content_quality(content),
        ),
        provenance=(
            Provenance(
                provider=provider_id, attempt=1, outcome="success", retrieved_at=retrieved_at
            ),
        ),
    )


_FETCH_SPEC = ClientFetchSpec(JINA_READER_FETCH_PROFILE.provider_id, _invoke, _project)

__all__ = ["JinaReaderClientProtocol", "JinaReaderFetchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config
    from souwen.common_runtime.channel_overrides import without_source_channel_overrides

    with without_source_channel_overrides(proxy=reviewed_proxy):
        client = JinaReaderClient(api_key=secrets.get("JINA_API_KEY"))
    return JinaReaderFetchProvider(client, enabled=bool(configuration["enabled"]))


MANIFEST = JINA_READER_PROVIDER_MANIFEST
SPEC = JINA_READER_FETCH_PROFILE
PROVIDER_TYPE = JinaReaderFetchProvider

# 兜底顺序：0 = wayback，1 = jina_reader（仅当 jina_fallback_enabled 时使用）。
FALLBACK_ORDER = 1
# 该兜底需要部署方显式开启（SPEC 4.4：默认关闭）。
FALLBACK_REQUIRES_OPT_IN = True


__all__ = [
    "FALLBACK_ORDER",
    "FALLBACK_REQUIRES_OPT_IN",
    "MANIFEST",
    "PROVIDER_TYPE",
    "SPEC",
    "build_provider",
]
