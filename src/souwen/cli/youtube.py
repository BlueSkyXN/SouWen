"""youtube 子命令组：trending / video / transcript"""

from __future__ import annotations

import asyncio
import json

import typer
from rich.table import Table

from souwen.cli._common import _run_async, console

youtube_app = typer.Typer(help="YouTube 视频工具")


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
    from souwen.core.exceptions import ConfigError, RateLimitError
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

    from souwen.core.exceptions import ConfigError, RateLimitError
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
    from souwen.core.exceptions import ConfigError
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
