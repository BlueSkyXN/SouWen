"""arxiv_fulltext（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
import re
from bs4 import BeautifulSoup
from collections.abc import Mapping
from datetime import datetime, timezone
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.provider_support.rate_limiter import TokenBucketLimiter
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import (
    ClientFetchProviderSpec,
    ClientTransportDeclaration,
    ClientFetchProvider,
    ClientFetchSpec,
)
from souwen.platform.provider_spec.models import HttpOperation
from souwen.platform.provider_spi import (
    ContentMetadata,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
)
from souwen.providers.runtime_clients.models import FetchResult
from souwen.providers.runtime_clients.web._extractor_chain import content_quality
from typing import Any, Protocol
from urllib.parse import urlsplit
from souwen.platform.provider_spi import FetchResult as ProviderFetchResult


from souwen.platform.manifest_registry import ProviderManifest


ARXIV_FULLTEXT_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "arxiv_fulltext",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "arxiv_fulltext-fetch",
                "capability": "fetch",
                "export": "ArxivFulltextFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "arxiv-fulltext-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["arxiv.org"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["arxiv-fulltext-provider-config-v1"],
        },
    }
)

__all__ = ["ARXIV_FULLTEXT_PROVIDER_MANIFEST"]


ARXIV_FULLTEXT_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="arxiv_fulltext",
    adapter_id="arxiv_fulltext-fetch",
    adapter_reason="arXiv identifier extraction and HTML text parsing remain in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="arxiv.org",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/html/"),),
    ),
    target_contract="arxiv_publication_url",
    configuration_keys=("enabled",),
)

__all__ = ["ARXIV_FULLTEXT_FETCH_PROFILE"]


logger = logging.getLogger(__name__)

_HTML_BASE = "https://arxiv.org/html"

_ABS_BASE = "https://arxiv.org/abs"

_RATE_LIMIT_RPS = 1.0 / 3.0

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


_PAPER_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z0-9.-]*/\d{7})(?:v\d+)?$")

_ACCEPTED_PATHS = ("/abs/", "/html/")


class ArxivFulltextClientProtocol(Protocol):
    async def get_fulltext(self, paper_id: str) -> Any: ...
    async def close(self) -> None: ...


class ArxivFulltextFetchProvider(ClientFetchProvider):
    """Fetch one reviewed arXiv target without broadening the source scope."""

    capability = "fetch"

    def __init__(self, client: ArxivFulltextClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _FETCH_SPEC, enabled=enabled)


async def _invoke(client: Any, request: FetchTargetRequest) -> Any:
    return await client.get_fulltext(_paper_id(request))


def _project(
    receipt: Any, request: FetchTargetRequest, context: RequestContext
) -> ProviderFetchResult:
    del context
    provider_id = ARXIV_FULLTEXT_FETCH_PROFILE.provider_id
    if getattr(receipt, "source", None) != provider_id:
        raise ValueError("unexpected existing arXiv source")
    if getattr(receipt, "error", None):
        raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE, provider_id=provider_id)
    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("invalid arXiv full-text receipt")
    final_url = _final_url(receipt, _paper_id(request))
    retrieved_at = datetime.now(timezone.utc)
    return ProviderFetchResult(
        target=request.target,
        final_url=final_url,
        status="success",
        title=getattr(receipt, "title", None) or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type="text/plain",
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


def _paper_id(request: FetchTargetRequest) -> str:
    target = urlsplit(str(request.target))
    prefix = next((item for item in _ACCEPTED_PATHS if target.path.startswith(item)), None)
    paper_id = target.path[len(prefix) :] if prefix is not None else ""
    if (
        target.scheme != "https"
        or target.hostname != ARXIV_FULLTEXT_FETCH_PROFILE.transport.host
        or target.username is not None
        or target.password is not None
        or target.port is not None
        or target.query
        or target.fragment
        or _PAPER_ID.fullmatch(paper_id) is None
    ):
        raise ProviderError(
            ProviderErrorCode.POLICY_BLOCKED,
            provider_id=ARXIV_FULLTEXT_FETCH_PROFILE.provider_id,
        )
    return paper_id


def _final_url(receipt: Any, paper_id: str) -> str:
    final_url = urlsplit(str(getattr(receipt, "final_url", "")))
    if (
        final_url.scheme != "https"
        or final_url.hostname != ARXIV_FULLTEXT_FETCH_PROFILE.transport.host
        or final_url.username is not None
        or final_url.password is not None
        or final_url.port is not None
        or final_url.path != f"/html/{paper_id}"
        or final_url.query
        or final_url.fragment
    ):
        raise ValueError("invalid arXiv final URL")
    return f"https://arxiv.org/html/{paper_id}"


_FETCH_SPEC = ClientFetchSpec(ARXIV_FULLTEXT_FETCH_PROFILE.provider_id, _invoke, _project)

__all__ = ["ArxivFulltextClientProtocol", "ArxivFulltextFetchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, reviewed_proxy
    return ArxivFulltextFetchProvider(
        ArxivFulltextClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = ARXIV_FULLTEXT_PROVIDER_MANIFEST
SPEC = ARXIV_FULLTEXT_FETCH_PROFILE
PROVIDER_TYPE = ArxivFulltextFetchProvider


def site_handler_matches(target: str) -> bool:
    """站点处理器谓词：arxiv.org 论文页先走本源的全文解析（SPEC 4.1）。

    由 ``server.v2_runtime`` 按目录发现时探测；源目录之外不再写 arxiv 分支。
    """
    parsed = urlsplit(target)
    return parsed.hostname == ARXIV_FULLTEXT_FETCH_PROFILE.transport.host and any(
        parsed.path.startswith(prefix) for prefix in ("/abs/", "/pdf/", "/html/")
    )


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider", "site_handler_matches"]
