"""Wayback Machine（Internet Archive）抓取客户端

文件用途：
    通过 Internet Archive 的 Wayback Machine 公开服务，抓取目标 URL 的
    最新存档快照。无需 API Key，零成本可用，适合作为活页失效或被墙站点
    的兜底抓取方案。返回经 _html_extract 转换的 Markdown/Text 内容。

函数/类清单：
    WaybackClient（类）
        - 功能：Wayback Machine 抓取客户端，先查可用性再拉取原始 HTML
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "wayback", BASE_URL = "https://web.archive.org",
                  PROVIDER_NAME = "wayback"
        - 主要方法：fetch(url, timeout) -> FetchResult,
                  fetch_batch(urls, max_concurrency, timeout) -> FetchResponse

    WaybackClient.__init__()
        - 功能：初始化 Wayback 客户端（无需 API Key），设置自定义 User-Agent
        - 输入：无
        - 输出：实例

    WaybackClient.fetch(url, timeout=30.0) -> FetchResult
        - 功能：查询最新存档快照并抓取其原始 HTML（避免 Wayback 工具栏注入）
        - 步骤：① archive.org/wayback/available 查可用性；
               ② 在快照 URL 中插入 id_ 修饰符获取原始 HTML；
               ③ 调 extract_from_html 提取正文
        - 输入：url 目标网页 URL，timeout 超时秒数
        - 输出：FetchResult，附带快照 URL 与时间戳
        - 异常：所有异常封装到 FetchResult.error，避免中断批量任务

    WaybackClient.fetch_batch(urls, max_concurrency=2, timeout=30.0) -> FetchResponse
        - 功能：批量抓取多个 URL，限制低并发并加 0.5 秒间隔以遵守限流
        - 输入：urls URL 列表，max_concurrency 最大并发数，timeout 单 URL 超时
        - 输出：FetchResponse 聚合结果

模块依赖：
    - asyncio: 异步并发控制（Semaphore + gather + sleep 限流）
    - logging: 日志记录
    - re: 正则表达式（向快照 URL 插入 id_ 修饰符）
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: FetchResponse, FetchResult 数据模型
    - souwen.web._html_extract: 共享 HTML → Markdown/Text 提取工具

技术要点：
    - 可用性 API：GET https://archive.org/wayback/available?url={url}
      响应字段：archived_snapshots.closest.{available, url, timestamp, status}
    - 快照原始 HTML 端点形如：http://web.archive.org/web/<ts>id_/<original_url>
      `id_` 修饰符告诉 Wayback 返回原始字节（不注入工具栏 JS/CSS），
      该修饰符是内容提取干净度的关键
    - 插入 id_ 的正则：re.sub(r"(/web/\\d+)(/)", r"\\1id_\\2", snapshot_url)
    - 限流：Internet Archive 约 1 req/s，故 max_concurrency=2 + 0.5s sleep
    - User-Agent：Internet Archive 要求设置可识别 UA，便于联系与封禁分级
    - published_date：从快照时间戳 YYYYMMDDHHMMSS 截取前 8 位作为 YYYY-MM-DD
"""

from __future__ import annotations

import asyncio
import logging
import re

from souwen.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult
from souwen.web._html_extract import extract_from_html

logger = logging.getLogger("souwen.web.wayback")


class WaybackClient(SouWenHttpClient):
    """Wayback Machine 抓取客户端（无需 API Key）"""

    ENGINE_NAME = "wayback"
    BASE_URL = "https://web.archive.org"
    PROVIDER_NAME = "wayback"

    def __init__(self) -> None:
        # Internet Archive 要求设置可识别 UA，便于联系与封禁分级
        super().__init__(
            base_url=self.BASE_URL,
            headers={
                "User-Agent": (
                    "SouWen/0.7 (Academic Search Tool; +https://github.com/BlueSkyXN/SouWen)"
                ),
            },
            source_name="wayback",
        )

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

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """查询最新存档快照并抓取原始 HTML

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（应用于 HTTP 层）

        Returns:
            FetchResult 包含提取的内容与快照元数据
        """
        try:
            # Step 1: 查询最新可用快照（注意：可用性 API 在 archive.org 域名下）
            avail_resp = await self.get(
                "https://archive.org/wayback/available",
                params={"url": url},
            )
            avail_data = avail_resp.json() or {}
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

            # Step 3: 拉取原始存档 HTML（follow_redirects 已默认开启）
            snap_resp = await self.get(raw_snapshot_url)
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
