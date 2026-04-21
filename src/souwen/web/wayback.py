"""Wayback Machine（Internet Archive）抓取客户端

文件用途：
    通过 Internet Archive 的 Wayback Machine 公开服务，抓取目标 URL 的
    最新存档快照。无需 API Key，零成本可用，适合作为活页失效或被墙站点
    的兜底抓取方案。返回经 _html_extract 转换的 Markdown/Text 内容。
    支持 CDX Server API 查询历史快照列表。

函数/类清单：
    WaybackClient（类）
        - 功能：Wayback Machine 抓取客户端，先查可用性再拉取原始 HTML，
                支持 CDX API 查询历史快照列表
        - 继承：BaseScraper（爬虫基类，提供 TLS 指纹 / WARP / 退避）
        - 关键属性：ENGINE_NAME = "wayback", BASE_URL = "https://web.archive.org",
                  PROVIDER_NAME = "wayback"
        - 主要方法：fetch(url, timeout) -> FetchResult,
                  fetch_batch(urls, max_concurrency, timeout) -> FetchResponse,
                  query_snapshots(url, from_date, to_date, ...) -> WaybackCDXResponse

    WaybackClient.__init__()
        - 功能：初始化 Wayback 客户端（无需 API Key），设置较低的礼貌延迟
                以匹配 archive.org ~1 req/s 的限流
        - 输入：无
        - 输出：实例

    WaybackClient.fetch(url, timeout=30.0) -> FetchResult
        - 功能：查询最新存档快照并抓取其原始 HTML（避免 Wayback 工具栏注入）
        - 步骤：① archive.org/wayback/available 查可用性（普通 httpx，纯 API 调用）；
               ② 在快照 URL 中插入 id_ 修饰符获取原始 HTML（走 BaseScraper._fetch）；
               ③ 调 extract_from_html 提取正文
        - 输入：url 目标网页 URL，timeout 超时秒数
        - 输出：FetchResult，附带快照 URL 与时间戳
        - 异常：所有异常封装到 FetchResult.error，避免中断批量任务

    WaybackClient.fetch_batch(urls, max_concurrency=2, timeout=30.0) -> FetchResponse
        - 功能：批量抓取多个 URL，限制低并发并加 0.5 秒间隔以遵守限流
        - 输入：urls URL 列表，max_concurrency 最大并发数，timeout 单 URL 超时
        - 输出：FetchResponse 聚合结果

    WaybackClient.query_snapshots(url, from_date, to_date, ...) -> WaybackCDXResponse
        - 功能：使用 CDX Server API 查询 URL 的所有历史快照列表
        - 输入：url 目标 URL（支持通配符 *），from_date/to_date 日期范围（YYYYMMDD），
                filter_status 状态码过滤，filter_mime MIME 类型过滤，
                limit 最大快照数，collapse 去重规则，timeout 超时
        - 输出：WaybackCDXResponse 包含快照列表和查询元数据
        - 示例用途：查看网页历史版本、分析内容演变、批量获取域名下所有存档

模块依赖：
    - asyncio: 异步并发控制（Semaphore + gather + sleep 限流）
    - logging: 日志记录
    - re: 正则表达式（向快照 URL 插入 id_ 修饰符）
    - httpx: 直接调用 archive.org 可用性 API（非网页抓取，不需要指纹）
    - souwen.scraper.base: BaseScraper 基类（TLS 指纹 / WARP / 自适应退避）
    - souwen.models: FetchResponse, FetchResult 数据模型
    - souwen.web._html_extract: 共享 HTML → Markdown/Text 提取工具

技术要点：
    - 可用性 API：GET https://archive.org/wayback/available?url={url}
      响应字段：archived_snapshots.closest.{available, url, timestamp, status}
      —— 这是 JSON API，使用 httpx 直连即可，无需 TLS 指纹
    - CDX Server API：GET https://web.archive.org/cdx/search/cdx?url={url}&output=json
      支持参数：from/to（日期范围 YYYYMMDD）、filter（statuscode/mimetype）、
               limit（数量限制）、collapse（去重：timestamp:8 按天，digest 按内容）
      响应格式：JSON 数组，第一行是字段名，后续行是数据值
      常用字段：timestamp（YYYYMMDDHHMMSS）、original（原始 URL）、
               statuscode、mimetype、digest（SHA-1）、length（字节数）
    - 快照原始 HTML 端点形如：http://web.archive.org/web/<ts>id_/<original_url>
      `id_` 修饰符告诉 Wayback 返回原始字节（不注入工具栏 JS/CSS），
      该修饰符是内容提取干净度的关键
    - 插入 id_ 的正则：re.sub(r"(/web/\\d+)(/)", r"\\1id_\\2", snapshot_url)
    - 限流：Internet Archive 约 1 req/s，故 min_delay=0.5/max_delay=1.0
      + max_concurrency=2 + 0.5s sleep
    - User-Agent：由 BaseScraper 浏览器指纹自动提供，可被频道配置覆盖
    - published_date：从快照时间戳 YYYYMMDDHHMMSS 截取前 8 位作为 YYYY-MM-DD
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from souwen.models import FetchResponse, FetchResult, WaybackCDXResponse, WaybackSnapshot
from souwen.scraper.base import BaseScraper
from souwen.web._html_extract import extract_from_html

logger = logging.getLogger("souwen.web.wayback")


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

    async def _check_availability(self, url: str, timeout: float) -> dict[str, Any]:
        """查询 archive.org 可用性 API（纯 JSON 接口，使用 httpx 直连）

        Args:
            url: 待查询的目标 URL
            timeout: 单次请求超时

        Returns:
            archive.org/wayback/available 的 JSON 响应（解析后的 dict）
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://archive.org/wayback/available",
                params={"url": url},
            )
            return resp.json() or {}

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """查询最新存档快照并抓取原始 HTML

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（应用于可用性 API 调用层）

        Returns:
            FetchResult 包含提取的内容与快照元数据
        """
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
