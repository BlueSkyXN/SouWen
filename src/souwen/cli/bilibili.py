"""bilibili 子命令组：search / search-users / video / search-articles"""

from __future__ import annotations

import asyncio
import json

import typer
from rich.table import Table

from souwen.cli._common import _run_async, console

bilibili_app = typer.Typer(help="Bilibili 视频工具")


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
