"""fetch / links / sitemap 直接命令"""

from __future__ import annotations

import asyncio
import json

import typer

from souwen.cli import app
from souwen.cli._common import _run_async, console
from souwen.registry import fetch_providers

_FETCH_PROVIDER_NAMES = tuple(adapter.name for adapter in fetch_providers())
_FETCH_PROVIDER_HELP = "内容提供者: " + "/".join(_FETCH_PROVIDER_NAMES)


def _validate_fetch_provider(value: str) -> str:
    """校验 CLI fetch provider 选项。"""
    if value not in _FETCH_PROVIDER_NAMES:
        raise typer.BadParameter(f"无效提供者: {value}，可选: {', '.join(_FETCH_PROVIDER_NAMES)}")
    return value


@app.command("fetch")
def fetch_cmd(
    urls: list[str] = typer.Argument(..., help="目标 URL（支持多个）"),
    provider: str = typer.Option(
        "builtin",
        "--provider",
        "-p",
        callback=_validate_fetch_provider,
        help=_FETCH_PROVIDER_HELP,
    ),
    selector: str = typer.Option(
        None, "--selector", "-s", help="CSS 选择器（builtin / scrapling 支持）"
    ),
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
