"""config 子命令组：show / init / backend / source / proxy"""

from __future__ import annotations

import json

import typer
from rich.table import Table

from souwen.cli._common import console

config_app = typer.Typer(help="配置管理")


def _mask_value(value: str | None) -> str:
    """显示敏感字段的状态（不泄漏实际值）"""
    if value is None or value == "":
        return "[dim]未配置[/dim]"
    return f"[green]已配置[/green] [dim](长度 {len(value)})[/dim]"


@config_app.command("show")
def config_show() -> None:
    """显示当前配置（隐藏 Key 值）"""
    from souwen.config import SouWenConfig, get_config

    cfg = get_config()
    table = Table(title="⚙️  SouWen 配置", show_lines=True)
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")

    for field_name, field_info in SouWenConfig.model_fields.items():
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
    from souwen.source_registry import (
        AUTH_REQUIREMENT_LABELS,
        DISTRIBUTION_LABELS,
        RISK_LEVEL_LABELS,
        get_all_sources,
        has_configured_credentials,
        is_known_source,
    )

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
        table.add_column("鉴权", style="blue")
        table.add_column("风险", style="red")
        table.add_column("分发", style="green")
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
                AUTH_REQUIREMENT_LABELS.get(meta.key_requirement, meta.key_requirement),
                RISK_LEVEL_LABELS.get(meta.risk_level, meta.risk_level),
                DISTRIBUTION_LABELS.get(meta.distribution, meta.distribution),
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
    console.print(
        "  鉴权: "
        f"{AUTH_REQUIREMENT_LABELS.get(meta.key_requirement, meta.key_requirement)}"
        f"  风险: {RISK_LEVEL_LABELS.get(meta.risk_level, meta.risk_level)}"
        f"  分发: {DISTRIBUTION_LABELS.get(meta.distribution, meta.distribution)}"
    )
    if meta.credential_fields:
        console.print(f"  凭据字段: {', '.join(meta.credential_fields)}")
    if meta.package_extra:
        console.print(f"  Extra: {meta.package_extra}")
    console.print(f"  启用: {'✅' if sc.enabled else '🚫'}")
    console.print(f"  代理: {sc.proxy}")
    console.print(f"  后端: {sc.http_backend}")
    if sc.base_url:
        console.print(f"  Base URL: {sc.base_url}")
    has_key = has_configured_credentials(cfg, name, meta)
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
