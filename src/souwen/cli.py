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
