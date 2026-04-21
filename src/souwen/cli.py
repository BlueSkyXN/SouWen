"""SouWen CLI — typer + rich 命令行工具

文件用途：
    提供命令行接口，让用户快速搜索论文、专利、网页。基于 typer（FastAPI 作者的 CLI 库）
    和 rich（彩色终端输出）。支持全局选项（--version、--verbose、--quiet）以及
    多个子命令组。

子命令清单（[已修正] 与实际注册的 typer 命令对齐）：
    search paper <query>
        - 选项：--sources/-s（默认 "openalex,arxiv"）、--limit/-n（默认 5）、
                --json/-j、--timeout/-t
        - 调用 souwen.search.search_papers，按表格或 JSON 输出
    search patent <query>
        - 选项：--sources/-s（默认 "google_patents"）、--limit/-n、--json、--timeout
    search web <query>
        - 选项：--engines/-e（默认 "duckduckgo,bing"）、--limit/-n、--json、--timeout
        - 调用 souwen.web.search.web_search

    sources
        - 单一命令（无子命令），列出所有可用数据源（来自 souwen.models.ALL_SOURCES）

    config show
        - 显示当前 SouWenConfig 字段，敏感字段（含 key/secret/token/password 关键字）做掩码
    config init
        - 在当前目录生成 souwen.yaml 配置模板（已存在则跳过）
    config backend [--default …] [--set source=backend]
        - 查看/修改 HTTP 后端配置（仅影响爬虫源），运行时生效
    config source [<name>] [--enable/--disable] [--proxy …] [--backend …]
                  [--base-url …] [--api-key …]
        - 列出或修改单个数据源的频道配置（运行时生效）

    serve [--host 0.0.0.0] [--port 8000] [--reload]
        - 启动 uvicorn 运行 souwen.server.app:app（需安装 server extra）
        - 启动前打印访客/管理密码状态、Docs 开放情况、可信代理、CORS 等

    doctor
        - 数据源健康检查（调用 souwen.doctor.check_all + format_report）

    mcp
        - 打印 MCP Server 配置 JSON，供 Claude Code / Cursor 等 AI Agent 集成使用

全局选项（main 回调）：
    --version / -V：显示版本并退出
    --verbose / -v：日志级别（默认 WARNING；-v → INFO；-vv → DEBUG）
    --quiet / -q：强制 WARNING 级别

输出格式：
    使用 rich.Console 和 rich.Table 实现彩色、对齐的输出
    搜索子命令支持 --json 输出 SearchResponse 的 JSON 序列化

异常处理：
    - KeyboardInterrupt (Ctrl+C)：优雅退出，返回码 130
    - asyncio.CancelledError：记录取消消息，返回码 1
    - 子命令超时：返回码 124

模块依赖：
    - typer: CLI 框架
    - rich: 彩色终端输出
    - souwen.search: 统一搜索接口
    - souwen.web.search: Web 搜索实现
    - souwen.config: 配置管理
    - souwen.source_registry: 数据源元数据
    - souwen.doctor: 健康检查
    - souwen.logging_config: 日志设置
"""

from __future__ import annotations

import asyncio
import json
import logging

import typer
from rich.console import Console
from rich.table import Table

from souwen import __version__

app = typer.Typer(
    name="souwen",
    help="SouWen — 面向 AI Agent 的学术论文 + 专利 + 网页统一搜索工具",
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    """版本回调函数

    Args:
        value: 布尔值（typer 自动传入 --version 标志的状态）

    Raises:
        typer.Exit: 版本输出后退出程序
    """
    if value:
        typer.echo(f"souwen {__version__}")
        raise typer.Exit(0)


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="显示版本并退出",
    ),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="-v info / -vv debug"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="只输出警告和错误"),
) -> None:
    """SouWen 全局选项

    配置日志级别和其他全局设置。此回调在所有子命令前执行。

    Args:
        version: --version 标志（触发版本输出）
        verbose: -v 计数（决定日志级别：0 = WARNING, 1+ = INFO, 2+ = DEBUG）
        quiet: -q 标志（强制 WARNING 级别）
    """
    if quiet:
        level = logging.WARNING
    elif verbose >= 2:
        level = logging.DEBUG
    elif verbose >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    try:
        from souwen.logging_config import setup_logging

        setup_logging(level=logging.getLevelName(level))
    except Exception:
        logging.getLogger("souwen").setLevel(level)


def _run_async(coro):
    """运行异步任务，优雅处理 KeyboardInterrupt 和 CancelledError

    Args:
        coro: 异步协程对象

    Returns:
        协程的返回值

    Raises:
        typer.Exit: 键盘中断时退出码 130，取消时退出码 1
    """
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ 已取消[/yellow]")
        raise typer.Exit(130)
    except asyncio.CancelledError:
        console.print("\n[yellow]⚠ 任务被取消[/yellow]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# search 子命令组
# ---------------------------------------------------------------------------
search_app = typer.Typer(help="搜索论文/专利/网页")
app.add_typer(search_app, name="search")


@search_app.command("paper")
def search_paper(
    query: str = typer.Argument(..., help="搜索关键词"),
    sources: str = typer.Option("openalex,arxiv", "--sources", "-s", help="数据源，逗号分隔"),
    limit: int = typer.Option(5, "--limit", "-n", help="每个源返回数量"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="总超时（秒），默认不限制"),
) -> None:
    """搜索学术论文"""
    from souwen.search import search_papers

    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    async def _do():
        coro = search_papers(query, sources=source_list, per_page=limit)
        if timeout is not None:
            return await asyncio.wait_for(coro, timeout=timeout)
        return await coro

    with console.status(f"[bold green]搜索论文: {query} ..."):
        try:
            results = _run_async(_do())
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 搜索超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if json_output:
        from rich import print_json

        data = [r.model_dump(mode="json") for r in results]
        print_json(json.dumps(data, ensure_ascii=False))
        return

    # 显示失败源的警告
    returned_sources = {r.source.value for r in results}
    failed = [s for s in source_list if s not in returned_sources]
    if failed:
        console.print(f"[yellow]⚠ 以下数据源未返回结果: {', '.join(failed)}[/yellow]")

    if not results:
        console.print("[dim]未找到任何结果。[/dim]")
        return

    for resp in results:
        table = Table(
            title=f"📄 {resp.source.value} ({len(resp.results)} 条)",
            show_lines=True,
        )
        table.add_column("Title", style="cyan", max_width=60)
        table.add_column("Year", justify="center")
        table.add_column("Citations", justify="right")
        table.add_column("DOI", style="dim")
        table.add_column("Source", style="green")
        for paper in resp.results:
            table.add_row(
                paper.title,
                str(paper.year or ""),
                str(paper.citation_count or ""),
                paper.doi or "",
                paper.source.value,
            )
        console.print(table)


@search_app.command("patent")
def search_patent(
    query: str = typer.Argument(..., help="搜索关键词"),
    sources: str = typer.Option("google_patents", "--sources", "-s", help="数据源，逗号分隔"),
    limit: int = typer.Option(5, "--limit", "-n", help="每个源返回数量"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="总超时（秒），默认不限制"),
) -> None:
    """搜索专利"""
    from souwen.search import search_patents

    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    async def _do():
        coro = search_patents(query, sources=source_list, per_page=limit)
        if timeout is not None:
            return await asyncio.wait_for(coro, timeout=timeout)
        return await coro

    with console.status(f"[bold green]搜索专利: {query} ..."):
        try:
            results = _run_async(_do())
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 搜索超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if json_output:
        from rich import print_json

        data = [r.model_dump(mode="json") for r in results]
        print_json(json.dumps(data, ensure_ascii=False))
        return

    returned_sources = {r.source.value for r in results}
    failed = [s for s in source_list if s not in returned_sources]
    if failed:
        console.print(f"[yellow]⚠ 以下数据源未返回结果: {', '.join(failed)}[/yellow]")

    if not results:
        console.print("[dim]未找到任何结果。[/dim]")
        return

    for resp in results:
        table = Table(
            title=f"📋 {resp.source.value} ({len(resp.results)} 条)",
            show_lines=True,
        )
        table.add_column("Title", style="cyan", max_width=50)
        table.add_column("Patent ID", style="yellow")
        table.add_column("Filing Date", justify="center")
        table.add_column("Applicants", style="dim", max_width=30)
        table.add_column("Source", style="green")
        for patent in resp.results:
            applicant_names = (
                ", ".join(a.name for a in patent.applicants) if patent.applicants else ""
            )
            table.add_row(
                patent.title,
                patent.patent_id,
                str(patent.filing_date or ""),
                applicant_names,
                patent.source.value,
            )
        console.print(table)


@search_app.command("web")
def search_web_cmd(
    query: str = typer.Argument(..., help="搜索关键词"),
    engines: str = typer.Option("duckduckgo,bing", "--engines", "-e", help="搜索引擎，逗号分隔"),
    limit: int = typer.Option(10, "--limit", "-n", help="每引擎最大结果数"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="总超时（秒），默认不限制"),
) -> None:
    """搜索网页"""
    from souwen.web.search import web_search

    engine_list = [e.strip() for e in engines.split(",") if e.strip()]

    async def _do():
        coro = web_search(query, engines=engine_list, max_results_per_engine=limit)
        if timeout is not None:
            return await asyncio.wait_for(coro, timeout=timeout)
        return await coro

    with console.status(f"[bold green]搜索网页: {query} ..."):
        try:
            resp = _run_async(_do())
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 搜索超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if json_output:
        from rich import print_json

        print_json(json.dumps(resp.model_dump(mode="json"), ensure_ascii=False))
        return

    table = Table(
        title=f"🌐 网页搜索 ({len(resp.results)} 条)",
        show_lines=True,
    )
    table.add_column("Title", style="cyan", max_width=50)
    table.add_column("URL", style="blue", max_width=40)
    table.add_column("Snippet", style="dim", max_width=50)
    table.add_column("Engine", style="green")
    for item in resp.results:
        table.add_row(
            item.title,
            item.url,
            item.snippet[:100] + ("..." if len(item.snippet) > 100 else ""),
            item.engine,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# fetch 子命令
# ---------------------------------------------------------------------------


@app.command("fetch")
def fetch_cmd(
    urls: list[str] = typer.Argument(..., help="目标 URL（支持多个）"),
    provider: str = typer.Option(
        "builtin",
        "--provider",
        "-p",
        help=(
            "内容提供者: builtin/jina_reader/tavily/firecrawl/exa/"
            "crawl4ai/scrapfly/diffbot/scrapingbee/zenrows/scraperapi/"
            "apify/cloudflare/wayback/newspaper/readability/"
            "mcp/site_crawler/deepwiki"
        ),
    ),
    selector: str = typer.Option(None, "--selector", "-s", help="CSS 选择器（仅 builtin 支持）"),
    start_index: int = typer.Option(0, "--start-index", help="内容起始切片位置"),
    max_length: int = typer.Option(None, "--max-length", help="内容最大长度"),
    respect_robots: bool = typer.Option(False, "--respect-robots", help="遵守 robots.txt"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="每 URL 超时（秒）"),
) -> None:
    """抓取网页内容 — 默认使用内置抓取（零配置）"""
    from souwen.web.fetch import fetch_content

    async def _do():
        return await fetch_content(
            urls=urls,
            providers=[provider],
            timeout=float(timeout),
            selector=selector,
            start_index=start_index,
            max_length=max_length,
            respect_robots_txt=respect_robots,
        )

    with console.status(f"[bold green]抓取 {len(urls)} 个 URL ..."):
        try:
            resp = _run_async(_do())
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 抓取超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if json_output:
        from rich import print_json

        print_json(json.dumps(resp.model_dump(mode="json"), ensure_ascii=False))
        return

    console.print(f"[bold]📄 抓取完成: {resp.total_ok}/{resp.total} 成功[/bold]")
    for r in resp.results:
        if r.error:
            console.print(f"  [red]✗ {r.url}: {r.error}[/red]")
        else:
            console.print(f"  [green]✓ {r.url}[/green] — {r.title}")
            if r.snippet:
                console.print(
                    f"    [dim]{r.snippet[:200]}{'...' if len(r.snippet) > 200 else ''}[/dim]"
                )


@app.command("links")
def links_cmd(
    url: str = typer.Argument(..., help="目标页面 URL"),
    base_url: str = typer.Option(None, "--base-url", "-b", help="URL 前缀过滤"),
    limit: int = typer.Option(100, "--limit", "-n", help="最大链接数"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """提取页面链接 — 去重 + SSRF 过滤"""
    from souwen.web.links import extract_links

    async def _do():
        return await extract_links(url=url, base_url_filter=base_url, limit=limit)

    with console.status("[bold green]提取链接 ..."):
        result = _run_async(_do())

    if result.error:
        console.print(f"[red]✗ {result.error}[/red]")
        raise typer.Exit(1)

    if json_output:
        from rich import print_json

        print_json(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
        return

    console.print(
        f"[bold]🔗 提取完成: {result.total} 个链接 (过滤 {result.filtered_count} 个)[/bold]"
    )
    for link in result.links:
        text_part = f" — {link.text}" if link.text else ""
        console.print(f"  [cyan]{link.url}[/cyan]{text_part}")


# ---------------------------------------------------------------------------
# sitemap 子命令
# ---------------------------------------------------------------------------


@app.command("sitemap")
def sitemap_cmd(
    url: str = typer.Argument(..., help="Sitemap URL 或站点根 URL"),
    discover: bool = typer.Option(False, "--discover", "-d", help="自动从 robots.txt 发现 sitemap"),
    limit: int = typer.Option(1000, "--limit", "-n", help="最大条目数"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """解析 sitemap.xml — 提取站点 URL 列表"""
    from souwen.web.sitemap import discover_sitemap, parse_sitemap

    async def _do():
        if discover:
            return await discover_sitemap(url, max_entries=limit)
        return await parse_sitemap(url, max_entries=limit)

    with console.status("[bold green]解析 sitemap ..."):
        result = _run_async(_do())

    if json_output:
        from rich import print_json

        print_json(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
        return

    if result.errors:
        for err in result.errors:
            console.print(f"  [yellow]⚠ {err}[/yellow]")

    console.print(
        f"[bold]🗺️ Sitemap 解析完成: {result.total} 个 URL "
        f"({result.sitemaps_parsed} 个 sitemap 文件)[/bold]"
    )
    for entry in result.entries[:50]:
        parts = [f"  [cyan]{entry.loc}[/cyan]"]
        if entry.lastmod:
            parts.append(f"[dim]{entry.lastmod}[/dim]")
        if entry.priority is not None:
            parts.append(f"[dim]p={entry.priority}[/dim]")
        console.print(" ".join(parts))
    if result.total > 50:
        console.print(f"  [dim]... 还有 {result.total - 50} 个 URL（使用 --json 查看全部）[/dim]")


# ---------------------------------------------------------------------------
# search images / videos 子命令
# ---------------------------------------------------------------------------


@search_app.command("images")
def search_images_cmd(
    query: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-n", help="最大结果数"),
    region: str = typer.Option("wt-wt", "--region", "-r", help="区域 (wt-wt=全球, cn-zh=中国)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """搜索图片 — DuckDuckGo Images"""
    from souwen.web.ddg_images import DuckDuckGoImagesClient

    async def _do():
        client = DuckDuckGoImagesClient()
        return await client.search(query=query, max_results=limit, region=region)

    with console.status(f"[bold green]搜索图片: {query} ..."):
        try:
            coro = _do()
            if timeout is not None:
                resp = _run_async(asyncio.wait_for(coro, timeout=timeout))
            else:
                resp = _run_async(coro)
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 搜索超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if json_output:
        from rich import print_json

        print_json(json.dumps(resp.model_dump(mode="json"), ensure_ascii=False))
        return

    table = Table(title=f"🖼️ 图片搜索 ({len(resp.results)} 条)", show_lines=True)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Source", style="dim", max_width=20)
    table.add_column("Size", style="green")
    table.add_column("URL", style="blue", max_width=50)
    for item in resp.results:
        table.add_row(
            item.title,
            item.image_source,
            f"{item.width}×{item.height}" if item.width else "",
            item.image_url[:50],
        )
    console.print(table)


@search_app.command("videos")
def search_videos_cmd(
    query: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-n", help="最大结果数"),
    region: str = typer.Option("wt-wt", "--region", "-r", help="区域"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """搜索视频 — DuckDuckGo Videos"""
    from souwen.web.ddg_videos import DuckDuckGoVideosClient

    async def _do():
        client = DuckDuckGoVideosClient()
        return await client.search(query=query, max_results=limit, region=region)

    with console.status(f"[bold green]搜索视频: {query} ..."):
        try:
            coro = _do()
            if timeout is not None:
                resp = _run_async(asyncio.wait_for(coro, timeout=timeout))
            else:
                resp = _run_async(coro)
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 搜索超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if json_output:
        from rich import print_json

        print_json(json.dumps(resp.model_dump(mode="json"), ensure_ascii=False))
        return

    table = Table(title=f"🎬 视频搜索 ({len(resp.results)} 条)", show_lines=True)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Publisher", style="yellow")
    table.add_column("Duration", style="green")
    table.add_column("Views", style="magenta", justify="right")
    table.add_column("URL", style="blue", max_width=40)
    for item in resp.results:
        views = f"{item.view_count:,}" if item.view_count else ""
        table.add_row(item.title, item.publisher, item.duration, views, item.url[:40])
    console.print(table)


# ---------------------------------------------------------------------------
# youtube 子命令组
# ---------------------------------------------------------------------------
youtube_app = typer.Typer(help="YouTube 视频工具")
app.add_typer(youtube_app, name="youtube")


@youtube_app.command("trending")
def youtube_trending(
    region: str = typer.Option("US", "--region", "-r", help="地区代码 (US/CN/JP/KR 等)"),
    category: str = typer.Option(
        "", "--category", "-c", help="分类 ID (10=音乐, 20=游戏, 25=新闻)"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="最大结果数"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """获取 YouTube 热门视频"""
    from souwen.exceptions import ConfigError, RateLimitError
    from souwen.web.youtube import YouTubeClient

    async def _do():
        client = YouTubeClient()
        return await client.get_trending(
            region_code=region, video_category_id=category or None, max_results=limit
        )

    with console.status(f"[bold green]获取 YouTube 热门 ({region}) ..."):
        try:
            coro = _do()
            if timeout is not None:
                results = _run_async(asyncio.wait_for(coro, timeout=timeout))
            else:
                results = _run_async(coro)
        except ConfigError as e:
            console.print(f"[red]❌ YouTube API 未配置: {e}[/red]")
            raise typer.Exit(1)
        except RateLimitError:
            console.print("[red]❌ YouTube API 配额已用尽[/red]")
            raise typer.Exit(1)
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 请求超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if json_output:
        from rich import print_json

        print_json(json.dumps([r.model_dump(mode="json") for r in results], ensure_ascii=False))
        return

    table = Table(title=f"🔥 YouTube 热门 ({region}, {len(results)} 条)", show_lines=True)
    table.add_column("Title", style="cyan", max_width=45)
    table.add_column("Channel", style="yellow", max_width=20)
    table.add_column("URL", style="blue", max_width=40)
    for item in results:
        table.add_row(item.title, item.snippet[:20] if item.snippet else "", item.url)
    console.print(table)


@youtube_app.command("video")
def youtube_video(
    video_id: str = typer.Argument(..., help="YouTube 视频 ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """获取 YouTube 视频详情"""
    from dataclasses import asdict

    from souwen.exceptions import ConfigError, RateLimitError
    from souwen.web.youtube import YouTubeClient

    async def _do():
        client = YouTubeClient()
        return await client.get_video_details([video_id])

    with console.status(f"[bold green]获取视频详情: {video_id} ..."):
        try:
            coro = _do()
            if timeout is not None:
                results = _run_async(asyncio.wait_for(coro, timeout=timeout))
            else:
                results = _run_async(coro)
        except ConfigError as e:
            console.print(f"[red]❌ YouTube API 未配置: {e}[/red]")
            raise typer.Exit(1)
        except RateLimitError:
            console.print("[red]❌ YouTube API 配额已用尽[/red]")
            raise typer.Exit(1)
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 请求超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if not results:
        console.print(f"[yellow]⚠ 视频 {video_id} 不存在或不可用[/yellow]")
        raise typer.Exit(1)

    if json_output:
        from rich import print_json

        print_json(json.dumps([asdict(r) for r in results], ensure_ascii=False))
        return

    detail = results[0]
    console.print(f"[bold cyan]📹 {detail.title}[/bold cyan]")
    console.print(f"  频道: [yellow]{detail.channel_title}[/yellow]")
    console.print(f"  发布: {detail.published_at}")
    console.print(f"  时长: {detail.duration_seconds // 60}:{detail.duration_seconds % 60:02d}")
    console.print(
        f"  播放: {detail.view_count:,}  点赞: {detail.like_count:,}  评论: {detail.comment_count:,}"
    )
    if detail.tags:
        console.print(f"  标签: {', '.join(detail.tags[:10])}")
    if detail.description:
        console.print(f"\n[dim]{detail.description[:300]}[/dim]")


@youtube_app.command("transcript")
def youtube_transcript(
    video_id: str = typer.Argument(..., help="YouTube 视频 ID"),
    lang: str = typer.Option("en", "--lang", "-l", help="字幕语言 (en/zh/ja/ko)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """提取 YouTube 视频字幕"""
    from souwen.exceptions import ConfigError
    from souwen.web.youtube import YouTubeClient

    async def _do():
        client = YouTubeClient()
        return await client.get_transcript(video_id, lang=lang)

    with console.status(f"[bold green]提取字幕: {video_id} ({lang}) ..."):
        try:
            coro = _do()
            if timeout is not None:
                segments = _run_async(asyncio.wait_for(coro, timeout=timeout))
            else:
                segments = _run_async(coro)
        except ConfigError as e:
            console.print(f"[red]❌ YouTube API 未配置: {e}[/red]")
            raise typer.Exit(1)
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 请求超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)

    if segments is None:
        console.print("[yellow]⚠ 该视频暂无字幕[/yellow]")
        raise typer.Exit(1)

    if json_output:
        from rich import print_json

        print_json(json.dumps(segments, ensure_ascii=False))
        return

    console.print(f"[bold]📝 字幕 ({len(segments)} 段)[/bold]\n")
    for seg in segments:
        start = seg.get("start", 0)
        minutes = int(start) // 60
        seconds = int(start) % 60
        console.print(f"[dim][{minutes:02d}:{seconds:02d}][/dim] {seg.get('text', '')}")


# ---------------------------------------------------------------------------
# bilibili 子命令组
# ---------------------------------------------------------------------------
bilibili_app = typer.Typer(help="Bilibili 视频工具")
app.add_typer(bilibili_app, name="bilibili")


def _bilibili_run(coro, timeout: int | None):
    """运行 bilibili 协程并统一处理超时与异常映射"""
    from souwen.web.bilibili._errors import (
        BilibiliAuthRequired,
        BilibiliError,
        BilibiliNotFound,
        BilibiliRateLimited,
        BilibiliRiskControl,
    )

    try:
        if timeout is not None:
            return _run_async(asyncio.wait_for(coro, timeout=timeout))
        return _run_async(coro)
    except BilibiliNotFound as e:
        console.print(f"[yellow]⚠ 未找到: {e}[/yellow]")
        raise typer.Exit(1)
    except BilibiliAuthRequired as e:
        console.print(f"[red]❌ 需要登录: {e}[/red]")
        raise typer.Exit(1)
    except BilibiliRateLimited:
        console.print("[red]❌ 请求被限流[/red]")
        raise typer.Exit(1)
    except BilibiliRiskControl as e:
        console.print(f"[red]❌ 触发风控: {e}[/red]")
        raise typer.Exit(1)
    except BilibiliError as e:
        console.print(f"[red]❌ Bilibili 错误: {e}[/red]")
        raise typer.Exit(1)
    except asyncio.TimeoutError:
        console.print(f"[red]⏱ 请求超时 (>{timeout}s)[/red]")
        raise typer.Exit(124)


def _bili_print_json(obj) -> None:
    from rich import print_json

    if isinstance(obj, list):
        data = [r.model_dump(mode="json") if hasattr(r, "model_dump") else r for r in obj]
    elif hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json")
    else:
        data = obj
    print_json(json.dumps(data, ensure_ascii=False))


@bilibili_app.command("search")
def bilibili_search(
    keyword: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-n", help="最大结果数"),
    _page: int = typer.Option(1, "--page", "-p", hidden=True, help="页码（保留兼容）"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """搜索 Bilibili 视频"""
    from souwen.web.bilibili import BilibiliClient

    _ = _page  # hidden option kept for CLI symmetry

    async def _do():
        async with BilibiliClient() as client:
            return await client.search(keyword, max_results=limit)

    with console.status(f"[bold green]搜索 Bilibili: {keyword} ..."):
        response = _bilibili_run(_do(), timeout)

    results = response.results
    if json_output:
        from rich import print_json

        print_json(json.dumps(response.model_dump(mode="json"), ensure_ascii=False))
        return

    table = Table(title=f"🔍 Bilibili 搜索: {keyword} ({len(results)} 条)", show_lines=True)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("UP主", style="yellow", max_width=15)
    table.add_column("播放", style="green", justify="right")
    table.add_column("URL", style="blue", max_width=35)
    for item in results:
        raw = item.raw or {}
        play = raw.get("play") or 0
        try:
            play_str = f"{int(play):,}"
        except (TypeError, ValueError):
            play_str = str(play)
        table.add_row(item.title, str(raw.get("author") or ""), play_str, item.url)
    console.print(table)


@bilibili_app.command("search-users")
def bilibili_search_users(
    keyword: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-n", help="最大结果数"),
    page: int = typer.Option(1, "--page", "-p", help="页码"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """搜索 Bilibili 用户"""
    from souwen.web.bilibili import BilibiliClient

    async def _do():
        async with BilibiliClient() as client:
            return await client.search_users(keyword, page=page, max_results=limit)

    with console.status(f"[bold green]搜索 Bilibili 用户: {keyword} ..."):
        results = _bilibili_run(_do(), timeout)

    if json_output:
        _bili_print_json(results)
        return

    table = Table(title=f"👤 用户搜索: {keyword} ({len(results)} 条)", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("MID", style="yellow")
    table.add_column("Fans", style="green", justify="right")
    table.add_column("Sign", style="dim", max_width=30)
    for u in results:
        table.add_row(u.uname, str(u.mid), f"{u.fans:,}", u.usign or "")
    console.print(table)


@bilibili_app.command("video")
def bilibili_video(
    bvid: str = typer.Argument(..., help="BV 号（如 BV1xx411c7mD）"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """获取 Bilibili 视频详情（标题、UP 主、播放量等元数据）"""
    from souwen.web.bilibili import BilibiliClient

    async def _do():
        async with BilibiliClient() as client:
            return await client.get_video_details(bvid)

    with console.status(f"[bold green]获取视频详情: {bvid} ..."):
        detail = _bilibili_run(_do(), timeout)

    if json_output:
        _bili_print_json(detail)
        return

    console.print(f"[bold cyan]📹 {detail.title}[/bold cyan]")
    console.print(f"  BV号: [dim]{detail.bvid}[/dim]")
    console.print(f"  UP主: [yellow]{detail.owner.name}[/yellow]  ({detail.space_url})")
    console.print(f"  时长: {detail.duration_str}")
    console.print(
        f"  播放: {detail.stat.view:,}  弹幕: {detail.stat.danmaku:,}"
        f"  点赞: {detail.stat.like:,}  投币: {detail.stat.coin:,}"
        f"  收藏: {detail.stat.favorite:,}"
    )
    if detail.tags:
        console.print(f"  标签: {', '.join(detail.tags[:10])}")
    if detail.desc:
        console.print(f"\n[dim]{detail.desc[:300]}[/dim]")
    console.print(f"\n  🔗 {detail.url}")


@bilibili_app.command("search-articles")
def bilibili_search_articles(
    keyword: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-n", help="最大结果数"),
    page: int = typer.Option(1, "--page", "-p", help="页码"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """搜索 Bilibili 专栏文章"""
    from souwen.web.bilibili import BilibiliClient

    async def _do():
        async with BilibiliClient() as client:
            return await client.search_articles(keyword, page=page, max_results=limit)

    with console.status(f"[bold green]搜索 Bilibili 专栏: {keyword} ..."):
        results = _bilibili_run(_do(), timeout)

    if json_output:
        _bili_print_json(results)
        return

    table = Table(title=f"📰 专栏搜索: {keyword} ({len(results)} 条)", show_lines=True)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Author", style="yellow", max_width=15)
    table.add_column("分类", style="magenta", max_width=12)
    table.add_column("阅读", style="green", justify="right")
    table.add_column("URL", style="blue", max_width=40)
    for a in results:
        table.add_row(
            a.title,
            a.author,
            a.category_name,
            f"{a.view:,}",
            a.url,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# wayback 子命令组
# ---------------------------------------------------------------------------
wayback_app = typer.Typer(help="Wayback Machine 归档工具")
app.add_typer(wayback_app, name="wayback")


@wayback_app.command("cdx")
def wayback_cdx(
    url: str = typer.Argument(..., help="目标 URL（支持通配符 *）"),
    from_date: str | None = typer.Option(None, "--from", help="起始日期 (YYYYMMDD)"),
    to_date: str | None = typer.Option(None, "--to", help="结束日期 (YYYYMMDD)"),
    limit: int = typer.Option(20, "--limit", "-n", help="最大快照数"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int = typer.Option(60, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """查询 URL 的历史快照列表"""
    from souwen.web.wayback import WaybackClient

    async def _do():
        client = WaybackClient()
        return await client.query_snapshots(
            url=url, from_date=from_date, to_date=to_date, limit=limit, timeout=float(timeout)
        )

    with console.status(f"[bold green]查询快照: {url} ..."):
        try:
            resp = _run_async(asyncio.wait_for(_do(), timeout=timeout + 10))
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 查询超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)
        except Exception as e:
            console.print(f"[red]❌ 查询失败: {e}[/red]")
            raise typer.Exit(1)

    if json_output:
        from rich import print_json

        print_json(json.dumps(resp.model_dump(mode="json"), ensure_ascii=False))
        return

    console.print(f"[bold]📦 Wayback CDX: {resp.total} 条快照[/bold]")
    if not resp.snapshots:
        console.print("[dim]暂无快照记录[/dim]")
        return

    table = Table(show_lines=True)
    table.add_column("Timestamp", style="cyan")
    table.add_column("Status", style="green", justify="center")
    table.add_column("MIME", style="yellow")
    table.add_column("URL", style="blue", max_width=50)
    for s in resp.snapshots[:limit]:
        table.add_row(s.timestamp, str(s.status_code), s.mime_type, s.url[:50])
    console.print(table)


@wayback_app.command("check")
def wayback_check(
    url: str = typer.Argument(..., help="目标 URL"),
    timestamp: str | None = typer.Option(None, "--timestamp", help="目标时间戳 (YYYYMMDD)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="超时（秒）"),
) -> None:
    """检查 URL 是否有 Wayback 存档"""
    from souwen.web.wayback import WaybackClient

    async def _do():
        client = WaybackClient()
        return await client.check_availability(url=url, timestamp=timestamp, timeout=float(timeout))

    with console.status(f"[bold green]检查存档: {url} ..."):
        try:
            resp = _run_async(asyncio.wait_for(_do(), timeout=timeout + 5))
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 检查超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)
        except Exception as e:
            console.print(f"[red]❌ 检查失败: {e}[/red]")
            raise typer.Exit(1)

    if json_output:
        from rich import print_json

        print_json(json.dumps(resp.model_dump(mode="json"), ensure_ascii=False))
        return

    if resp.available:
        console.print("[green]✓ 有存档[/green]")
        console.print(f"  快照 URL: [blue]{resp.snapshot_url}[/blue]")
        console.print(f"  时间戳:   {resp.timestamp}")
        console.print(f"  状态码:   {resp.status}")
    else:
        console.print("[yellow]✗ 暂无存档[/yellow]")
        if resp.error:
            console.print(f"  [dim]{resp.error}[/dim]")


@wayback_app.command("save")
def wayback_save(
    url: str = typer.Argument(..., help="待存档 URL"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int = typer.Option(90, "--timeout", "-t", help="超时（秒，存档较慢）"),
) -> None:
    """提交 URL 到 Internet Archive 即时存档"""
    from souwen.web.wayback import WaybackClient

    async def _do():
        client = WaybackClient()
        return await client.save_page(url=url, timeout=float(timeout))

    with console.status(f"[bold green]存档中: {url} (可能需要 30-120 秒) ..."):
        try:
            resp = _run_async(asyncio.wait_for(_do(), timeout=timeout + 15))
        except asyncio.TimeoutError:
            console.print(f"[red]⏱ 存档超时 (>{timeout}s)[/red]")
            raise typer.Exit(124)
        except Exception as e:
            console.print(f"[red]❌ 存档失败: {e}[/red]")
            raise typer.Exit(1)

    if json_output:
        from rich import print_json

        print_json(json.dumps(resp.model_dump(mode="json"), ensure_ascii=False))
        return

    if resp.success:
        console.print("[green]✓ 存档成功[/green]")
        console.print(f"  快照 URL: [blue]{resp.snapshot_url}[/blue]")
        console.print(f"  时间戳:   {resp.timestamp}")
    else:
        console.print("[red]✗ 存档失败[/red]")
        if resp.error:
            console.print(f"  [dim]{resp.error}[/dim]")


# ---------------------------------------------------------------------------
# config 子命令组
# ---------------------------------------------------------------------------
config_app = typer.Typer(help="配置管理")
app.add_typer(config_app, name="config")


def _mask_value(value: str | None) -> str:
    """显示敏感字段的状态（不泄漏实际值）"""
    if value is None or value == "":
        return "[dim]未配置[/dim]"
    return f"[green]已配置[/green] [dim](长度 {len(value)})[/dim]"


@config_app.command("show")
def config_show() -> None:
    """显示当前配置（隐藏 Key 值）"""
    from souwen.config import get_config

    cfg = get_config()
    table = Table(title="⚙️  SouWen 配置", show_lines=True)
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")

    for field_name, field_info in cfg.model_fields.items():
        raw_val = getattr(cfg, field_name)
        is_secret = (
            "key" in field_name
            or "secret" in field_name
            or "token" in field_name
            or "password" in field_name
            or "sessdata" in field_name
        )
        if is_secret:
            display = _mask_value(str(raw_val) if raw_val is not None else None)
        else:
            display = str(raw_val) if raw_val is not None else "[dim]未配置[/dim]"
        table.add_row(field_name, display)

    console.print(table)


@config_app.command("init")
def config_init() -> None:
    """生成 souwen.yaml 配置模板"""
    from pathlib import Path

    template = """\
# SouWen 配置文件
# 复制为 souwen.yaml 并填入实际值即可使用
# 也可放置于 ~/.config/souwen/config.yaml 作为全局配置
#
# 优先级：环境变量 > ./souwen.yaml > ~/.config/souwen/config.yaml > .env > 默认值

# ===== 论文数据源 =====
paper:
  openalex_email: ~
  semantic_scholar_api_key: ~
  core_api_key: ~
  pubmed_api_key: ~
  unpaywall_email: ~
  ieee_api_key: ~

# ===== 专利数据源 =====
patent:
  uspto_api_key: ~
  epo_consumer_key: ~
  epo_consumer_secret: ~
  cnipa_client_id: ~
  cnipa_client_secret: ~
  lens_api_token: ~
  patsnap_api_key: ~

# ===== 常规搜索 =====
web:
  # 爬虫引擎 (DuckDuckGo/Yahoo/Brave/Google/Bing/Startpage/Baidu/Mojeek/Yandex) 无需 Key
  searxng_url: ~
  tavily_api_key: ~
  exa_api_key: ~
  serper_api_key: ~
  brave_api_key: ~
  serpapi_api_key: ~
  firecrawl_api_key: ~
  perplexity_api_key: ~
  linkup_api_key: ~
  scrapingdog_api_key: ~
  metaso_api_key: ~
  whoogle_url: ~
  websurfx_url: ~

# ===== 通用设置 =====
general:
  proxy: ~
  # 代理池：多个代理地址，每次请求随机选取（优先于 proxy）
  # proxy_pool:
  #   - http://proxy1:7890
  #   - http://proxy2:7890
  #   - socks5://proxy3:1080
  proxy_pool: []
  timeout: 30
  max_retries: 3
  data_dir: ~/.local/share/souwen
  # HTTP 后端: auto | curl_cffi | httpx
  default_http_backend: auto
  # http_backend:
  #   duckduckgo: curl_cffi
  #   google_patents: httpx
  http_backend: {}

# ===== 服务 =====
server:
  # 旧版统一密码（同时作用于访客和管理端点，向后兼容）
  api_password: ~
  # 访客密码（仅保护搜索端点，优先于 api_password）
  visitor_password: ~
  # 管理密码（仅保护管理端点，优先于 api_password）
  admin_password: ~
"""

    dest = Path("souwen.yaml")
    if dest.exists():
        console.print("[yellow]⚠️  souwen.yaml 已存在，跳过生成[/yellow]")
        return

    try:
        dest.write_text(template, encoding="utf-8")
    except OSError as e:
        console.print(f"[red]❌ 写入 souwen.yaml 失败: {e}[/red]")
        raise typer.Exit(1) from e
    console.print("[green]✅ 已生成 souwen.yaml 配置模板[/green]")


@config_app.command("backend")
def config_backend(
    default: str | None = typer.Option(
        None, help="设置全局默认 HTTP 后端: auto | curl_cffi | httpx"
    ),
    set_source: str | None = typer.Option(
        None, "--set", help="设置指定源的 HTTP 后端，格式: source=backend (如 duckduckgo=httpx)"
    ),
) -> None:
    """查看/修改 HTTP 后端配置（仅影响爬虫源）"""
    from souwen.config import get_config
    from souwen.scraper.base import _HAS_CURL_CFFI

    _VALID = {"auto", "curl_cffi", "httpx"}
    _SCRAPER_ENGINES = [
        "duckduckgo",
        "yahoo",
        "brave",
        "google",
        "bing",
        "startpage",
        "baidu",
        "mojeek",
        "yandex",
        "google_patents",
    ]

    cfg = get_config()
    modified = False

    if default is not None:
        if default not in _VALID:
            console.print(f"[red]无效的后端: {default}，可选: {', '.join(_VALID)}[/red]")
            raise typer.Exit(1)
        cfg.default_http_backend = default
        modified = True
        console.print(f"[green]全局默认已设为: {default}[/green]")

    if set_source is not None:
        parts = set_source.split("=", 1)
        if len(parts) != 2:
            console.print("[red]格式错误，应为: source=backend (如 duckduckgo=httpx)[/red]")
            raise typer.Exit(1)
        source, backend = parts[0].strip(), parts[1].strip()
        if source not in _SCRAPER_ENGINES:
            console.print(f"[red]未知的爬虫源: {source}，可选: {', '.join(_SCRAPER_ENGINES)}[/red]")
            raise typer.Exit(1)
        if backend not in _VALID:
            console.print(f"[red]无效的后端: {backend}，可选: {', '.join(_VALID)}[/red]")
            raise typer.Exit(1)
        if backend == "auto":
            cfg.http_backend.pop(source, None)
        else:
            cfg.http_backend[source] = backend
        modified = True
        console.print(f"[green]{source} 已设为: {backend}[/green]")

    # 显示当前配置
    table = Table(title="🔌 HTTP 后端配置", show_lines=True)
    table.add_column("源", style="cyan")
    table.add_column("后端", style="green")
    table.add_column("状态", style="dim")

    table.add_row(
        "[bold]全局默认[/bold]",
        cfg.default_http_backend,
        f"curl_cffi {'✅ 可用' if _HAS_CURL_CFFI else '❌ 未安装'}",
    )
    for engine in _SCRAPER_ENGINES:
        override = cfg.http_backend.get(engine)
        effective = override or cfg.default_http_backend
        display = f"{override} [dim](覆盖)[/dim]" if override else f"{effective} [dim](默认)[/dim]"
        table.add_row(engine, display, "")

    console.print(table)

    if modified:
        console.print("[yellow]⚠ 运行时修改仅当前进程有效。如需持久化请修改 souwen.yaml[/yellow]")


@config_app.command("source")
def config_source(
    name: str | None = typer.Argument(None, help="数据源名称（留空列出全部）"),
    enable: bool | None = typer.Option(None, "--enable/--disable", help="启用/禁用数据源"),
    proxy: str | None = typer.Option(None, help="代理: inherit | none | warp | URL"),
    backend: str | None = typer.Option(
        None, "--backend", help="HTTP 后端: auto | curl_cffi | httpx"
    ),
    base_url: str | None = typer.Option(None, "--base-url", help="覆盖基础 URL"),
    api_key: str | None = typer.Option(None, "--api-key", help="覆盖 API Key"),
) -> None:
    """查看/修改数据源频道配置"""
    from souwen.config import SourceChannelConfig, get_config
    from souwen.source_registry import get_all_sources, is_known_source

    cfg = get_config()

    # integration_type → 表格短标签
    _INTEGRATION_SHORT = {
        "open_api": "公开",
        "scraper": "爬虫",
        "official_api": "授权",
        "self_hosted": "自建",
    }

    if name is None:
        # 列出全部数据源配置
        all_sources = get_all_sources()
        table = Table(title="📡 数据源频道配置", show_lines=True)
        table.add_column("源", style="cyan")
        table.add_column("类别", style="yellow")
        table.add_column("集成", style="magenta")
        table.add_column("启用", justify="center")
        table.add_column("代理", style="dim")
        table.add_column("后端", style="dim")
        table.add_column("自定义", style="dim")

        for src_name, meta in all_sources.items():
            sc = cfg.get_source_config(src_name)
            enabled_icon = "✅" if sc.enabled else "🚫"
            customs = []
            if sc.base_url:
                customs.append("base_url")
            if sc.api_key:
                customs.append("api_key")
            if sc.headers:
                customs.append("headers")
            if sc.params:
                customs.append("params")
            table.add_row(
                src_name,
                meta.category,
                _INTEGRATION_SHORT.get(meta.integration_type, meta.integration_type),
                enabled_icon,
                sc.proxy,
                sc.http_backend,
                ", ".join(customs) if customs else "-",
            )

        console.print(table)
        return

    if not is_known_source(name):
        console.print(f"[red]未知数据源: {name}[/red]")
        raise typer.Exit(1)

    modified = False
    sc = cfg.sources.get(name, SourceChannelConfig())

    if enable is not None:
        sc.enabled = enable
        modified = True
    if proxy is not None:
        sc.proxy = proxy
        modified = True
    if backend is not None:
        _VALID = {"auto", "curl_cffi", "httpx"}
        if backend not in _VALID:
            console.print(f"[red]无效的后端: {backend}，可选: {', '.join(_VALID)}[/red]")
            raise typer.Exit(1)
        sc.http_backend = backend
        modified = True
    if base_url is not None:
        sc.base_url = base_url if base_url else None
        modified = True
    if api_key is not None:
        sc.api_key = api_key if api_key else None
        modified = True

    if modified:
        cfg.sources[name] = sc
        console.print(f"[green]✅ {name} 配置已更新[/green]")
        console.print("[yellow]⚠ 运行时修改仅当前进程有效。如需持久化请修改 souwen.yaml[/yellow]")

    # 显示当前配置
    from souwen.source_registry import get_source

    meta = get_source(name)
    console.print(f"\n[bold]{name}[/bold] ({meta.description})")
    console.print(f"  类别: {meta.category}  集成: {meta.integration_type}")
    console.print(f"  启用: {'✅' if sc.enabled else '🚫'}")
    console.print(f"  代理: {sc.proxy}")
    console.print(f"  后端: {sc.http_backend}")
    if sc.base_url:
        console.print(f"  Base URL: {sc.base_url}")
    has_key = bool(cfg.resolve_api_key(name, meta.config_field))
    console.print(f"  API Key: {'✅ 已配置' if has_key else '⬜ 未配置'}")
    if sc.headers:
        console.print(f"  Headers: {json.dumps(sc.headers)}")
    if sc.params:
        console.print(f"  Params: {json.dumps(sc.params)}")


@config_app.command("proxy")
def config_proxy(
    proxy: str | None = typer.Option(
        None, "--proxy", help="全局代理 URL（如 socks5://127.0.0.1:1080）"
    ),
    add_pool: str | None = typer.Option(None, "--add-pool", help="向代理池添加一个 URL"),
    remove_pool: str | None = typer.Option(None, "--remove-pool", help="从代理池移除一个 URL"),
    clear_pool: bool = typer.Option(False, "--clear-pool", help="清空代理池"),
    clear_proxy: bool = typer.Option(False, "--clear-proxy", help="清除全局代理"),
) -> None:
    """查看/修改全局代理配置"""
    from souwen.config import _validate_proxy_url, get_config

    cfg = get_config()
    modified = False

    if proxy is not None:
        try:
            validated = _validate_proxy_url(proxy)
            cfg.proxy = validated
            modified = True
        except ValueError as e:
            console.print(f"[red]代理 URL 无效: {e}[/red]")
            raise typer.Exit(1)

    if clear_proxy:
        cfg.proxy = None
        modified = True

    if add_pool is not None:
        try:
            validated = _validate_proxy_url(add_pool)
            if validated and validated not in cfg.proxy_pool:
                cfg.proxy_pool.append(validated)
                modified = True
        except ValueError as e:
            console.print(f"[red]代理池 URL 无效: {e}[/red]")
            raise typer.Exit(1)

    if remove_pool is not None:
        if remove_pool in cfg.proxy_pool:
            cfg.proxy_pool.remove(remove_pool)
            modified = True
        else:
            console.print(f"[yellow]代理池中未找到: {remove_pool}[/yellow]")

    if clear_pool:
        cfg.proxy_pool = []
        modified = True

    if modified:
        console.print("[green]✅ 代理配置已更新[/green]")
        console.print("[yellow]⚠ 运行时修改仅当前进程有效。如需持久化请修改 souwen.yaml[/yellow]")

    console.print("\n[bold]📡 全局代理配置[/bold]")
    console.print(f"  代理: {cfg.proxy or '[dim]未设置[/dim]'}")
    if cfg.proxy_pool:
        console.print(f"  代理池 ({len(cfg.proxy_pool)} 个):")
        for i, p in enumerate(cfg.proxy_pool, 1):
            console.print(f"    {i}. {p}")
    else:
        console.print("  代理池: [dim]空[/dim]")

    try:
        import socksio  # noqa: F401

        console.print("  SOCKS 支持: [green]✅ 已安装 socksio[/green]")
    except ImportError:
        console.print("  SOCKS 支持: [yellow]⚠ 未安装 socksio (pip install httpx[socks])[/yellow]")


# ---------------------------------------------------------------------------
# sources 命令
# ---------------------------------------------------------------------------
@app.command("sources")
def list_sources() -> None:
    """列出所有可用数据源"""
    from souwen.source_registry import get_all_sources

    _INTEGRATION_SHORT = {
        "open_api": "公开",
        "scraper": "爬虫",
        "official_api": "授权",
        "self_hosted": "自建",
    }

    table = Table(title="📚 SouWen 数据源", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="yellow")
    table.add_column("Integration", style="magenta")
    table.add_column("Needs Key", justify="center")
    table.add_column("Description", style="dim")

    for name, meta in get_all_sources().items():
        needs_key = meta.config_field is not None
        key_indicator = "🔑" if needs_key else "✅"
        integration = _INTEGRATION_SHORT.get(meta.integration_type, meta.integration_type)
        table.add_row(name, meta.category, integration, key_indicator, meta.description)

    console.print(table)


# ---------------------------------------------------------------------------
# serve 命令
# ---------------------------------------------------------------------------
@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="监听地址"),
    port: int = typer.Option(8000, help="监听端口"),
    reload: bool = typer.Option(False, help="开发模式自动重载"),
) -> None:
    """启动 API 服务"""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]❌ 需要安装 server 依赖: pip install souwen\\[server][/red]")
        raise typer.Exit(1)

    from souwen.logging_config import setup_logging

    setup_logging()

    from souwen.config import get_config

    cfg = get_config()
    console.print("[bold]━━━ SouWen 启动配置 ━━━[/bold]")
    # 访客密码状态
    v_pw = cfg.effective_visitor_password
    v_color = "green" if v_pw else "red"
    v_text = "已启用" if v_pw else "未启用（开放访问）"
    console.print(f"  访客密码:        [{v_color}]{v_text}[/]")
    # 管理密码状态
    a_pw = cfg.effective_admin_password
    a_color = "green" if a_pw else "yellow"
    a_text = "已启用" if a_pw else "未启用（管理端开放）"
    console.print(f"  管理密码:        [{a_color}]{a_text}[/]")
    console.print(f"  Docs:            {'已开放' if cfg.expose_docs else '已隐藏'}")
    console.print(
        f"  Trusted proxies: {', '.join(cfg.trusted_proxies) if cfg.trusted_proxies else '(未配置)'}"
    )
    console.print(
        f"  CORS origins:    {', '.join(cfg.cors_origins) if cfg.cors_origins else '(未配置)'}"
    )
    console.print(f"  监听:            http://{host}:{port}")
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

    uvicorn.run("souwen.server.app:app", host=host, port=port, reload=reload)


# ---------------------------------------------------------------------------
# doctor 命令
# ---------------------------------------------------------------------------
@app.command("doctor")
def doctor_cmd() -> None:
    """检查所有数据源可用性"""
    from souwen.doctor import check_all, format_report

    results = check_all()
    console.print(format_report(results))


# ---------------------------------------------------------------------------
# mcp 命令
# ---------------------------------------------------------------------------
@app.command("mcp")
def mcp_info() -> None:
    """显示 MCP Server 配置信息（用于 Claude Code / Cursor 集成）"""
    import sys

    config = {
        "mcpServers": {
            "souwen": {
                "command": sys.executable,
                "args": ["-m", "souwen.integrations.mcp_server"],
            }
        }
    }
    console.print("[bold]📡 SouWen MCP Server 配置[/bold]\n")
    console.print("将以下配置添加到你的 AI Agent 的 MCP 配置文件中：\n")
    from rich import print_json

    print_json(json.dumps(config, indent=2))
    console.print("\n[dim]Claude Code: ~/.claude/claude_code_config.json[/dim]")
    console.print("[dim]Cursor: .cursor/mcp.json[/dim]")


if __name__ == "__main__":
    app()
