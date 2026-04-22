"""search 子命令组：paper / patent / web / images / videos"""

from __future__ import annotations

import asyncio
import json

import typer
from rich.table import Table

from souwen.cli._common import _run_async, console
from souwen.registry import defaults_for

search_app = typer.Typer(help="搜索论文/专利/网页")
_DEFAULT_PAPER_SOURCES = defaults_for("paper", "search")
_DEFAULT_PAPER_SOURCES_LABEL = ",".join(_DEFAULT_PAPER_SOURCES)


@search_app.command("paper")
def search_paper(
    query: str = typer.Argument(..., help="搜索关键词"),
    sources: str | None = typer.Option(
        None,
        "--sources",
        "-s",
        help=f"数据源，逗号分隔；默认 {_DEFAULT_PAPER_SOURCES_LABEL}",
    ),
    limit: int = typer.Option(5, "--limit", "-n", help="每个源返回数量"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    timeout: int | None = typer.Option(None, "--timeout", "-t", help="总超时（秒），默认不限制"),
) -> None:
    """搜索学术论文"""
    from souwen.search import search_papers

    requested_sources = None
    if sources is None:
        source_list = list(_DEFAULT_PAPER_SOURCES)
    else:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]
        requested_sources = source_list

    async def _do():
        coro = search_papers(query, sources=requested_sources, per_page=limit)
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
