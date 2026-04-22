"""wayback 子命令组：cdx / check / save"""

from __future__ import annotations

import asyncio
import json

import typer
from rich.table import Table

from souwen.cli._common import _deprecation_notice, _run_async, console

wayback_app = typer.Typer(help="Wayback Machine 归档工具")


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
    _deprecation_notice("souwen wayback cdx", "souwen archive cdx")
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
    _deprecation_notice("souwen wayback check", "souwen archive check")
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
    _deprecation_notice("souwen wayback save", "souwen archive save")
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
