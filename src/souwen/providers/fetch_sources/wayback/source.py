"""wayback（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import asyncio
import logging
import re
import httpx
from collections.abc import Mapping
from datetime import datetime, timezone
from souwen.common_runtime.provider_support.scraper.base import BaseScraper
from souwen.common_runtime.security import validate_fetch_url
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
from souwen.providers.runtime_clients.models import (
    FetchResponse,
    FetchResult,
    WaybackAvailability,
    WaybackCDXResponse,
    WaybackSaveResult,
    WaybackSnapshot,
)
from souwen.providers.runtime_clients.web._extractor_chain import content_quality
from souwen.providers.runtime_clients.web._html_extract import extract_from_html
from typing import Any, Protocol
from urllib.parse import urlsplit
from souwen.platform.provider_spi import FetchResult as ProviderFetchResult


from souwen.platform.manifest_registry import ProviderManifest

WAYBACK_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "wayback",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "wayback-fetch",
                "capability": "fetch",
                "export": "WaybackFetchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "wayback-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["archive.org", "web.archive.org"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["wayback-provider-config-v1"],
        },
    }
)


WAYBACK_FETCH_PROVIDER_SPEC = ClientFetchProviderSpec(
    provider_id="wayback",
    adapter_id="wayback-fetch",
    adapter_reason="existing Wayback client owns availability lookup, SSRF policy, and archived-content parsing",
    transport=ClientTransportDeclaration(
        host="archive.org",
        protocol="multi_transport",
        operations=(HttpOperation(method="GET", endpoint="/wayback/available"),),
    ),
    additional_transports=(
        ClientTransportDeclaration(
            host="web.archive.org",
            protocol="multi_transport",
            operations=(HttpOperation(method="GET", endpoint="/web/:snapshot/:target"),),
        ),
    ),
    target_contract="public_url",
    configuration_keys=("enabled",),
)


logger = logging.getLogger("souwen.providers.runtime_clients.web.wayback")


class WaybackClient(BaseScraper):
    """Wayback Machine 抓取客户端（无需 API Key）

    继承 BaseScraper 获得 TLS 指纹伪装、WARP 代理、自适应退避等反反爬能力。
    archive.org 限流 ~1 req/s，故采用较低的礼貌延迟与并发。
    """

    ENGINE_NAME = "wayback"
    BASE_URL = "https://web.archive.org"
    PROVIDER_NAME = "wayback"

    def __init__(self) -> None:
        # archive.org 限流约 1 req/s，使用 0.5~1.0s 的礼貌延迟
        super().__init__(
            min_delay=0.5,
            max_delay=1.0,
            max_retries=3,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "WaybackClient":
        await super().__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await super().__aexit__(*args)

    @staticmethod
    def _to_raw_snapshot_url(snapshot_url: str) -> str:
        """在 Wayback 快照 URL 中插入 id_ 修饰符以获取原始 HTML

        例：http://web.archive.org/web/20240101000000/http://example.com/
            → http://web.archive.org/web/20240101000000id_/http://example.com/
        """
        return re.sub(r"(/web/\d+)(/)", r"\1id_\2", snapshot_url, count=1)

    @staticmethod
    def _format_published_date(timestamp: str) -> str | None:
        """将 Wayback 时间戳 YYYYMMDDHHMMSS 截取前 8 位转 YYYY-MM-DD"""
        if not timestamp or len(timestamp) < 8 or not timestamp[:8].isdigit():
            return None
        return f"{timestamp[0:4]}-{timestamp[4:6]}-{timestamp[6:8]}"

    async def _check_availability(
        self, url: str, timeout: float, timestamp: str | None = None
    ) -> dict[str, Any]:
        """查询 archive.org 可用性 API（纯 JSON 接口，使用 httpx 直连）

        Args:
            url: 待查询的目标 URL
            timeout: 单次请求超时
            timestamp: 可选，指定查询最接近该时间的快照（YYYYMMDD 或 YYYYMMDDHHMMSS）

        Returns:
            archive.org/wayback/available 的 JSON 响应（解析后的 dict）
        """
        params: dict[str, Any] = {"url": url}
        if timestamp:
            params["timestamp"] = timestamp
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://archive.org/wayback/available",
                params=params,
            )
            return resp.json() or {}

    async def check_availability(
        self,
        url: str,
        timestamp: str | None = None,
        timeout: float = 30.0,
    ) -> WaybackAvailability:
        """检查 URL 是否有 Wayback Machine 存档（公开 Availability API）

        Args:
            url: 目标 URL
            timestamp: 可选，指定查询最接近该时间的快照（YYYYMMDD 或 YYYYMMDDHHMMSS）
            timeout: 超时秒数

        Returns:
            WaybackAvailability 结构化可用性信息；任何异常都会被封装到 error 字段
        """
        try:
            avail_data = await self._check_availability(url, timeout=timeout, timestamp=timestamp)
            closest = (avail_data.get("archived_snapshots") or {}).get("closest") or {}
            snapshot_url = closest.get("url") or None
            ts = closest.get("timestamp") or None
            available = bool(closest.get("available", False)) and bool(snapshot_url)

            # status 字段在响应里通常是字符串，统一转 int；非数字时回退 None
            status_raw = closest.get("status")
            status_code: int | None
            if isinstance(status_raw, int):
                status_code = status_raw
            elif isinstance(status_raw, str) and status_raw.isdigit():
                status_code = int(status_raw)
            else:
                status_code = None

            return WaybackAvailability(
                url=url,
                available=available,
                snapshot_url=snapshot_url,
                timestamp=ts,
                published_date=self._format_published_date(ts) if ts else None,
                status_code=status_code,
            )
        except Exception as exc:
            logger.warning("Wayback availability check failed: url=%s err=%s", url, exc)
            return WaybackAvailability(
                url=url,
                available=False,
                error=str(exc),
            )

    async def save_page(self, url: str, timeout: float = 60.0) -> WaybackSaveResult:
        """触发 Wayback Machine 立即存档指定 URL（Save Page Now 基础版）

        通过 Save Page Now 服务请求 Internet Archive 立即抓取并存档网页当前状态。
        无需 API Key，但受 archive.org 全局限流约束。

        Args:
            url: 要存档的网页 URL
            timeout: 超时秒数（存档可能需要较长时间，默认 60s）

        Returns:
            WaybackSaveResult 包含存档结果；任何异常都会被封装到 error 字段
        """
        from souwen.providers.runtime_clients.web.fetch import validate_fetch_url

        valid, reason = validate_fetch_url(url)
        if not valid:
            return WaybackSaveResult(
                url=url,
                success=False,
                error=f"SSRF 校验失败: {reason}",
            )

        try:
            save_endpoint = f"https://web.archive.org/save/{url}"
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                # SPN 基础版：POST 即可触发存档；失败的状态码会在下方判定为 success=False
                resp = await client.post(save_endpoint)

            # IA 在不同情况下会返回：3xx 重定向（Location 指向 /web/<ts>/<url>）、
            # 200 + Content-Location header、或 200 + HTML 内嵌快照路径。
            snapshot_url: str | None = None

            location = resp.headers.get("location") or resp.headers.get("content-location")
            if location:
                snapshot_url = (
                    location
                    if location.startswith("http")
                    else (
                        f"https://web.archive.org{location}" if location.startswith("/") else None
                    )
                )

            # 回退：在响应体中提取形如 /web/YYYYMMDDHHMMSS/<url> 的路径
            if not snapshot_url:
                body = resp.text or ""
                match = re.search(r"(/web/\d{14}/\S+?)(?=[\s\"'<>])", body)
                if match:
                    snapshot_url = f"https://web.archive.org{match.group(1)}"

            # 从快照 URL 中抽取时间戳
            timestamp: str | None = None
            if snapshot_url:
                ts_match = re.search(r"/web/(\d{14})", snapshot_url)
                if ts_match:
                    timestamp = ts_match.group(1)

            # 判定成功：状态码 2xx/3xx + 拿到了快照 URL 即视为成功触发
            success = 200 <= resp.status_code < 400 and bool(snapshot_url)

            if success:
                return WaybackSaveResult(
                    url=url,
                    success=True,
                    snapshot_url=snapshot_url,
                    timestamp=timestamp,
                )

            return WaybackSaveResult(
                url=url,
                success=False,
                snapshot_url=snapshot_url,
                timestamp=timestamp,
                error=f"Save Page Now 未返回有效快照（HTTP {resp.status_code}）",
            )
        except Exception as exc:
            logger.warning("Wayback save failed: url=%s err=%s", url, exc)
            return WaybackSaveResult(
                url=url,
                success=False,
                error=str(exc),
            )

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """查询最新存档快照并抓取原始 HTML

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（应用于可用性 API 调用层）

        Returns:
            FetchResult 包含提取的内容与快照元数据
        """
        from souwen.providers.runtime_clients.web.fetch import validate_fetch_url

        valid, reason = validate_fetch_url(url)
        if not valid:
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=f"SSRF 校验失败: {reason}",
                raw={"provider": "wayback", "blocked_by_ssrf": True},
            )

        try:
            # Step 1: 查询最新可用快照（archive.org 域名下的 JSON API）
            avail_data = await self._check_availability(url, timeout=timeout)
            closest = (avail_data.get("archived_snapshots") or {}).get("closest") or {}
            snapshot_url = closest.get("url") or ""
            timestamp = closest.get("timestamp") or ""

            # 无可用快照（无 closest 或 available=False）
            if not snapshot_url or not closest.get("available", False):
                return FetchResult(
                    url=url,
                    final_url=url,
                    source=self.PROVIDER_NAME,
                    error="该 URL 无存档快照",
                    raw={"provider": "wayback"},
                )

            # Step 2: 注入 id_ 修饰符获取无注入的原始 HTML
            raw_snapshot_url = self._to_raw_snapshot_url(snapshot_url)

            # Step 3: 拉取原始存档 HTML（走 BaseScraper，享 TLS 指纹 + WARP + 退避）
            snap_resp = await self._fetch(raw_snapshot_url)
            html = snap_resp.text or ""

            # Step 4: 委托共享工具提取正文
            extracted = extract_from_html(html, url)
            content = extracted.get("content", "") or ""
            title = extracted.get("title", "") or ""
            content_format = extracted.get("content_format", "markdown") or "markdown"
            author = extracted.get("author")

            snippet = content[:500] if content else ""
            # 优先使用提取器解析的日期，回退到 Wayback 快照时间戳
            published_date = extracted.get("date") or self._format_published_date(timestamp)

            return FetchResult(
                url=url,
                final_url=url,
                title=title,
                content=content,
                content_format=content_format,
                source=self.PROVIDER_NAME,
                snippet=snippet,
                published_date=published_date,
                author=author,
                raw={
                    "provider": "wayback",
                    "archive_url": snapshot_url,
                    "timestamp": timestamp,
                },
            )
        except Exception as exc:
            # 异常封装到 FetchResult.error，避免中断批量任务
            logger.warning("Wayback fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "wayback"},
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 2,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL（低并发 + 间隔以尊重 IA 限流 ~1 req/s）

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数（默认 2）
            timeout: 每个 URL 超时

        Returns:
            FetchResponse 聚合结果
        """
        # Semaphore 控制并发；每次请求后 sleep 0.5s 以避免触发 Internet Archive 限流
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                result = await self.fetch(u, timeout=timeout)
                await asyncio.sleep(0.5)
                return result

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

    async def query_snapshots(
        self,
        url: str,
        from_date: str | None = None,
        to_date: str | None = None,
        filter_status: list[int] | None = None,
        filter_mime: str | None = None,
        limit: int | None = None,
        collapse: str | None = None,
        timeout: float = 30.0,
    ) -> WaybackCDXResponse:
        """查询 URL 的所有历史快照（CDX Server API）

        Args:
            url: 目标 URL（支持通配符 * 查询整个域名）
            from_date: 起始日期（YYYYMMDD 或 YYYY-MM-DD 格式）
            to_date: 结束日期（YYYYMMDD 或 YYYY-MM-DD 格式）
            filter_status: 过滤状态码列表（如 [200, 301]）
            filter_mime: 过滤 MIME 类型（如 "text/html"）
            limit: 最大返回快照数量（默认无限制）
            collapse: 去重字段（如 "timestamp:8" 按天去重，"digest" 按内容去重）
            timeout: 请求超时秒数

        Returns:
            WaybackCDXResponse 包含快照列表和元数据

        示例:
            # 查询某个 URL 的所有快照
            resp = await client.query_snapshots("example.com")

            # 查询 2023 年的快照
            resp = await client.query_snapshots("example.com", from_date="20230101", to_date="20231231")

            # 只查询成功的 HTML 页面
            resp = await client.query_snapshots("example.com", filter_status=[200], filter_mime="text/html")

            # 按天去重，只返回每天第一个快照
            resp = await client.query_snapshots("example.com", collapse="timestamp:8")
        """
        try:
            # 构建 CDX API 请求参数
            params: dict[str, Any] = {
                "url": url,
                "output": "json",  # JSON 格式输出
            }

            # 添加日期范围过滤
            if from_date:
                # 支持 YYYY-MM-DD 格式，转换为 YYYYMMDD
                params["from"] = from_date.replace("-", "")
            if to_date:
                params["to"] = to_date.replace("-", "")

            # 添加状态码过滤
            if filter_status:
                params["filter"] = [f"statuscode:{code}" for code in filter_status]

            # 添加 MIME 类型过滤
            if filter_mime:
                if "filter" not in params:
                    params["filter"] = []
                params["filter"].append(f"mimetype:{filter_mime}")

            # 添加限制和去重
            if limit:
                params["limit"] = limit
            if collapse:
                params["collapse"] = collapse

            # 调用 CDX API
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    "https://web.archive.org/cdx/search/cdx",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            # 解析 CDX 响应
            # CDX JSON 格式：第一行是字段名数组，后续每行是值数组
            # 示例：[["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            #       ["com,example)/", "20230101000000", "http://example.com/", "text/html", "200", "ABC123", "1234"], ...]

            snapshots: list[WaybackSnapshot] = []

            if isinstance(data, list) and len(data) > 1:
                # 第一行是字段名
                fields = data[0] if data else []

                # 后续行是数据
                for row in data[1:]:
                    if not isinstance(row, list) or len(row) < 3:
                        continue

                    # 构建字段映射
                    snapshot_data: dict[str, Any] = {}
                    for i, field in enumerate(fields):
                        if i < len(row):
                            snapshot_data[field] = row[i]

                    # 提取关键字段
                    timestamp = str(snapshot_data.get("timestamp") or "")
                    original_url = snapshot_data.get("original", url)
                    # CDX 字段类型不稳定（偶尔返回 int 或 None），统一转 str 后再判断，避免 AttributeError
                    status_raw = snapshot_data.get("statuscode")
                    if isinstance(status_raw, int):
                        status_code = status_raw
                    else:
                        status_str = str(status_raw or "")
                        status_code = int(status_str) if status_str.isdigit() else 200
                    mime = str(snapshot_data.get("mimetype") or "")
                    digest = str(snapshot_data.get("digest") or "")
                    length_raw = snapshot_data.get("length")
                    if isinstance(length_raw, int):
                        length_val = length_raw
                    else:
                        length_str = str(length_raw or "")
                        length_val = int(length_str) if length_str.isdigit() else 0

                    # 构建快照 URL
                    archive_url = f"https://web.archive.org/web/{timestamp}/{original_url}"

                    # 格式化日期
                    published_date = self._format_published_date(timestamp)

                    # 创建快照对象
                    snapshot = WaybackSnapshot(
                        timestamp=timestamp,
                        url=original_url,
                        archive_url=archive_url,
                        status_code=status_code,
                        mime_type=mime,
                        digest=digest,
                        length=length_val,
                        published_date=published_date,
                    )
                    snapshots.append(snapshot)

            return WaybackCDXResponse(
                url=url,
                snapshots=snapshots,
                total=len(snapshots),
                from_date=params.get("from"),
                to_date=params.get("to"),
                filter_status=filter_status,
                filter_mime=filter_mime,
            )

        except Exception as exc:
            logger.warning("CDX query failed: url=%s err=%s", url, exc)
            return WaybackCDXResponse(
                url=url,
                snapshots=[],
                total=0,
                error=str(exc),
            )


class WaybackClientProtocol(Protocol):
    async def fetch(self, url: str, timeout: float = 30.0) -> Any: ...
    async def close(self) -> None: ...


class WaybackFetchProvider(ClientFetchProvider):
    def __init__(self, client: WaybackClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: FetchTargetRequest) -> Any:
    return await client.fetch(_target(request), timeout=30.0)


def _project(
    receipt: Any, request: FetchTargetRequest, context: RequestContext
) -> ProviderFetchResult:
    del context
    if getattr(receipt, "source", None) != "wayback":
        raise ValueError("invalid Wayback receipt")
    if getattr(receipt, "error", None):
        raw = getattr(receipt, "raw", None)
        code = (
            ProviderErrorCode.POLICY_BLOCKED
            if isinstance(raw, dict) and raw.get("blocked_by_ssrf")
            else ProviderErrorCode.PROVIDER_UNAVAILABLE
        )
        raise ProviderError(code, provider_id="wayback")
    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("invalid Wayback content")
    final = _url(str(getattr(receipt, "final_url", None) or request.target))
    if final != _url(str(request.target)) or not validate_fetch_url(final)[0]:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id="wayback")
    title = getattr(receipt, "title", None)
    if title is not None and not isinstance(title, str):
        raise ValueError("invalid Wayback title")
    now = datetime.now(timezone.utc)
    return ProviderFetchResult(
        target=request.target,
        final_url=final,
        status="success",
        title=title or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type="text/html",
            retrieved_at=now,
            truncated=False,
            content_length=len(content.encode()),
            quality=content_quality(content),
        ),
        provenance=(
            Provenance(provider="wayback", attempt=1, outcome="success", retrieved_at=now),
        ),
    )


def _url(value: str) -> str:
    p = urlsplit(value)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("invalid target URL")
    return value


def _target(request: FetchTargetRequest) -> str:
    try:
        target = _url(str(request.target))
    except ValueError as exc:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id="wayback") from exc
    if not validate_fetch_url(target)[0]:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id="wayback")
    return target


_SPEC = ClientFetchSpec("wayback", _invoke, _project)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config
    from souwen.common_runtime.channel_overrides import without_source_channel_overrides

    # 未声明的频道覆盖不生效：wayback 不支持代理/自定义 base_url，构造期
    # 以受审空覆盖运行（与旧 _build_reviewed_client_provider 语义一致）。
    with without_source_channel_overrides(proxy=None):
        client = WaybackClient()
    return WaybackFetchProvider(client, enabled=bool(configuration["enabled"]))


MANIFEST = WAYBACK_PROVIDER_MANIFEST
SPEC = WAYBACK_FETCH_PROVIDER_SPEC
PROVIDER_TYPE = WaybackFetchProvider

# 页面本身不可达时的最后兜底顺序（SPEC 4.4）。runtime 按此声明组装，
# 源目录之外不再写 wayback 分支。
FALLBACK_ORDER = 0


__all__ = ["FALLBACK_ORDER", "MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
