"""SouWen CLI — typer + rich 命令行工具

用法:
    souwen search paper "transformer attention"
    souwen search patent "lithium battery"
    souwen search web "Python asyncio"
    souwen sources
    souwen config show
    souwen serve --port 8080
"""

from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="souwen",
    help="SouWen — 面向 AI Agent 的学术论文 + 专利 + 网页统一搜索工具",
    no_args_is_help=True,
)
console = Console()

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
) -> None:
    """搜索学术论文"""
    from souwen.search import search_papers

    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    with console.status(f"[bold green]搜索论文: {query} ..."):
        results = asyncio.run(search_papers(query, sources=source_list, per_page=limit))

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
    sources: str = typer.Option("patentsview,pqai", "--sources", "-s", help="数据源，逗号分隔"),
    limit: int = typer.Option(5, "--limit", "-n", help="每个源返回数量"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """搜索专利"""
    from souwen.search import search_patents

    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    with console.status(f"[bold green]搜索专利: {query} ..."):
        results = asyncio.run(search_patents(query, sources=source_list, per_page=limit))

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
    engines: str = typer.Option(
        "duckduckgo,yahoo,brave", "--engines", "-e", help="搜索引擎，逗号分隔"
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="每引擎最大结果数"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """搜索网页"""
    from souwen.web.search import web_search

    engine_list = [e.strip() for e in engines.split(",") if e.strip()]

    with console.status(f"[bold green]搜索网页: {query} ..."):
        resp = asyncio.run(web_search(query, engines=engine_list, max_results_per_engine=limit))

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
# config 子命令组
# ---------------------------------------------------------------------------
config_app = typer.Typer(help="配置管理")
app.add_typer(config_app, name="config")


def _mask_value(value: str | None) -> str:
    """隐藏 Key 值，仅显示前 4 位"""
    if value is None:
        return "[dim]未设置[/dim]"
    if len(value) <= 4:
        return value[:1] + "***"
    return value[:4] + "***"


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
        is_secret = "key" in field_name or "secret" in field_name or "token" in field_name
        if is_secret and raw_val is not None:
            display = _mask_value(str(raw_val))
        else:
            display = str(raw_val) if raw_val is not None else "[dim]未设置[/dim]"
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
"""

    dest = Path("souwen.yaml")
    if dest.exists():
        console.print("[yellow]⚠️  souwen.yaml 已存在，跳过生成[/yellow]")
        return

    dest.write_text(template, encoding="utf-8")
    console.print("[green]✅ 已生成 souwen.yaml 配置模板[/green]")


# ---------------------------------------------------------------------------
# sources 命令
# ---------------------------------------------------------------------------
@app.command("sources")
def list_sources() -> None:
    """列出所有可用数据源"""
    from souwen.models import ALL_SOURCES

    table = Table(title="📚 SouWen 数据源", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Needs Key", justify="center")
    table.add_column("Description", style="dim")

    for source_type, entries in ALL_SOURCES.items():
        for name, needs_key, description in entries:
            key_indicator = "🔑" if needs_key else "✅"
            table.add_row(name, source_type, key_indicator, description)

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

    console.print(f"[bold green]🚀 启动 SouWen API 服务 → http://{host}:{port}[/bold green]")
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
