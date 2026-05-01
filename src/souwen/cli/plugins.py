"""plugins 命令组：插件管理"""

from __future__ import annotations

import re
from pathlib import Path

import typer
from rich.table import Table

from souwen.cli._common import _run_async, console
from souwen.plugin_manager import (
    DEFAULT_PLUGIN_HEALTH_TIMEOUT_SECONDS,
    collect_plugin_health,
    run_plugin_health,
)

_PLUGIN_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

plugins_app = typer.Typer(
    name="plugins",
    help="插件管理 — 列表、启用/禁用、安装/卸载、重载、健康检查",
    no_args_is_help=True,
)


def _render_health_cell(
    name: str,
    status: str,
    health_map: dict[str, dict[str, object]],
) -> str:
    """Render the health cell for the list table."""
    if status != "loaded":
        return "[dim]—[/dim]"
    info = health_map.get(name)
    if info is None:
        return "[dim]?[/dim]"
    state = str(info.get("status", "")).lower()
    if state in {"ok", "healthy"}:
        return "[green]✅ ok[/green]"
    if state in {"degraded", "warn", "warning"}:
        return f"[yellow]⚠ {state}[/yellow]"
    if state in {"not_loaded"}:
        return "[dim]未加载[/dim]"
    return f"[red]❌ {state or 'error'}[/red]"


def _plugin_scaffold_files(name: str) -> dict[Path, str]:
    """Return the files for a new plugin scaffold."""
    project_name = name.replace("_", "-")
    return {
        Path("pyproject.toml"): f"""[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "souwen-plugin-{project_name}"
version = "0.1.0"
description = "SouWen plugin: {name}"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.entry-points."souwen.plugins"]
{name} = "{name}:plugin"

[tool.setuptools.packages.find]
include = ["{name}*"]
""",
        Path(name) / "__init__.py": f'''"""SouWen plugin scaffold for {name}."""

from __future__ import annotations

import logging

from souwen.plugin import Plugin
from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.loader import lazy

logger = logging.getLogger(__name__)

adapter = SourceAdapter(
    name="{name}",
    domain="fetch",
    integration="self_hosted",
    description="TODO: describe the {name} fetch provider",
    config_field=None,
    client_loader=lazy("{name}.client:{name.title().replace("_", "")}Client"),
    methods={{"fetch": MethodSpec("fetch")}},
    needs_config=False,
    default_enabled=False,
    tags=frozenset({{"external_plugin"}}),
)


def health_check() -> dict[str, str]:
    """Return a lightweight plugin health status."""
    return {{"status": "ok"}}


plugin = Plugin(
    name="{name}",
    version="0.1.0",
    adapters=[adapter],
    health_check=health_check,
)


try:
    from .handler import register

    register()
except ImportError as exc:
    logger.warning("可选 fetch handler 注册不可用: %s", exc, exc_info=True)
except Exception as exc:
    logger.warning("可选 fetch handler 注册失败: %s", exc, exc_info=True)
''',
        Path(name) / "client.py": f'''"""Client implementation for the {name} plugin."""

from __future__ import annotations


class {name.title().replace("_", "")}Client:
    """TODO: implement provider-specific API calls."""

    async def fetch(self, url: str, *, timeout: float = 30.0) -> str:
        """Fetch one URL and return markdown content."""
        return f"# TODO\\n\\nFetched {{url}} with timeout={{timeout}}."
''',
        Path(name) / "handler.py": f'''"""Fetch handler registration for the {name} plugin."""

from __future__ import annotations

from typing import Any

from souwen.models import FetchResponse, FetchResult


async def {name}_handler(
    urls: list[str],
    timeout: float = 30.0,
    **kwargs: Any,
) -> FetchResponse:
    """Fetch URLs through the {name} provider."""
    del kwargs
    results = [
        FetchResult(
            url=url,
            final_url=url,
            source="{name}",
            title=f"TODO: {{url}}",
            content=f"# TODO\\n\\nImplement {name} fetching for {{url}} (timeout={{timeout}}).",
            content_format="markdown",
            snippet="TODO",
        )
        for url in urls
    ]
    return FetchResponse(
        urls=urls,
        results=results,
        total=len(results),
        total_ok=len(results),
        total_failed=0,
        provider="{name}",
    )


def register() -> None:
    """Register the fetch handler when SouWen loads this plugin."""
    from souwen.web.fetch import register_fetch_handler

    register_fetch_handler("{name}", {name}_handler)
''',
        Path("tests") / f"test_{name}.py": f'''"""Tests for the {name} SouWen plugin."""

from __future__ import annotations

from souwen.testing import assert_valid_plugin

from {name} import plugin


def test_plugin_contract() -> None:
    assert_valid_plugin(plugin)
''',
        Path("README.md"): f"""# {name}

SouWen plugin scaffold for `{name}`.

## Develop

```bash
python -m pip install -e ".[dev]"
pytest
```

## Register with SouWen

This package exposes the `{name}` entry point in the `souwen.plugins` group:

```toml
[project.entry-points."souwen.plugins"]
{name} = "{name}:plugin"
```

Edit `{name}/client.py` and `{name}/handler.py` to integrate your provider, then
run the contract test to verify the plugin envelope.
""",
    }


@plugins_app.command("new")
def new_cmd(
    name: str = typer.Argument(..., help="新插件名称（小写字母开头，可含数字和下划线）"),
) -> None:
    """创建一个新的 SouWen 插件项目骨架。"""
    if _PLUGIN_NAME_RE.fullmatch(name) is None:
        console.print("[red]插件名称必须以小写字母开头，且只能包含小写字母、数字和下划线。[/red]")
        raise typer.Exit(code=1)

    target_dir = Path(name)
    if target_dir.exists():
        console.print(f"[red]目标目录 {name!r} 已存在。[/red]")
        raise typer.Exit(code=1)

    for rel_path, content in _plugin_scaffold_files(name).items():
        path = target_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    console.print(f"[green]✅ 已创建插件项目: {target_dir}[/green]")
    console.print(f"[dim]下一步: cd {target_dir} && python -m pip install -e '.[dev]'[/dim]")


@plugins_app.command("list")
def list_cmd(
    show_health: bool = typer.Option(
        False,
        "--health",
        help="并发执行已加载插件的 health_check 并附加状态列。",
    ),
    health_timeout: float = typer.Option(
        DEFAULT_PLUGIN_HEALTH_TIMEOUT_SECONDS,
        "--health-timeout",
        help="单个 health_check 的超时秒数。",
    ),
) -> None:
    """列出所有插件"""
    from souwen.plugin_manager import is_restart_required, list_plugins

    plugins = list_plugins()

    if is_restart_required():
        console.print("[bold yellow]⚠ 插件状态已变更，重启后完全生效。[/bold yellow]")
        console.print()

    if not plugins:
        console.print("[dim]未发现任何插件。[/dim]")
        return

    health_map: dict[str, dict[str, object]] = {}
    if show_health:
        loaded_names = [p.name for p in plugins if p.status == "loaded"]
        if loaded_names:
            health_map = _run_async(collect_plugin_health(loaded_names, timeout=health_timeout))

    table = Table(title="🔌 SouWen 插件", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Source", style="magenta")
    table.add_column("Version", style="dim")
    if show_health:
        table.add_column("Health", justify="center")
    table.add_column("Description", style="dim")

    status_icons = {
        "loaded": "[green]✅ 已加载[/green]",
        "available": "[yellow]📦 可用[/yellow]",
        "disabled": "[red]⛔ 禁用[/red]",
        "error": "[red]❌ 错误[/red]",
    }

    for p in plugins:
        row = [
            p.name,
            status_icons.get(p.status, p.status),
            p.source,
            p.version or "-",
        ]
        if show_health:
            row.append(_render_health_cell(p.name, p.status, health_map))
        row.append(p.description or "-")
        table.add_row(*row)

    console.print(table)


@plugins_app.command("info")
def info_cmd(
    name: str = typer.Argument(..., help="插件名称"),
) -> None:
    """查看插件详情"""
    from souwen.plugin_manager import get_plugin_info

    info = get_plugin_info(name)
    if info is None:
        console.print(f"[red]插件 {name!r} 未找到。[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]🔌 {info.name}[/bold cyan]")
    console.print(f"  状态:    {info.status}")
    console.print(f"  来源:    {info.source}")
    console.print(f"  包名:    {info.package or '-'}")
    console.print(f"  版本:    {info.version or '-'}")
    console.print(f"  官方:    {'是' if info.first_party else '否'}")
    console.print(f"  描述:    {info.description or '-'}")
    if info.source_adapters:
        console.print(f"  数据源:  {', '.join(info.source_adapters)}")
    if info.fetch_handlers:
        console.print(f"  处理器:  {', '.join(info.fetch_handlers)}")
    if info.error:
        console.print(f"  [red]错误:    {info.error}[/red]")
    if info.restart_required:
        console.print("  [yellow]⚠ 需要重启[/yellow]")


@plugins_app.command("enable")
def enable_cmd(
    name: str = typer.Argument(..., help="插件名称"),
) -> None:
    """启用插件（重启后生效）"""
    from souwen.plugin_manager import enable_plugin

    result = enable_plugin(name)
    if result["success"]:
        console.print(f"[green]✅ {result['message']}[/green]")
    else:
        console.print(f"[red]❌ {result['message']}[/red]")
        raise typer.Exit(code=1)


@plugins_app.command("disable")
def disable_cmd(
    name: str = typer.Argument(..., help="插件名称"),
) -> None:
    """禁用插件（重启后生效）"""
    from souwen.plugin_manager import disable_plugin_async

    result = _run_async(disable_plugin_async(name))
    if result["success"]:
        console.print(f"[green]✅ {result['message']}[/green]")
    else:
        console.print(f"[red]❌ {result['message']}[/red]")
        raise typer.Exit(code=1)


@plugins_app.command("install")
def install_cmd(
    package: str = typer.Argument(..., help="插件包名（如 superweb2pdf）"),
) -> None:
    """安装插件（需 SOUWEN_ENABLE_PLUGIN_INSTALL=1）"""
    from souwen.plugin_manager import install_plugin

    console.print(f"[dim]正在安装 {package}...[/dim]")
    result = _run_async(install_plugin(package))
    if result["success"]:
        console.print("[green]✅ 安装成功。重启后生效。[/green]")
    else:
        console.print(f"[red]❌ 安装失败: {result['output']}[/red]")
        raise typer.Exit(code=1)


@plugins_app.command("uninstall")
def uninstall_cmd(
    package: str = typer.Argument(..., help="插件包名（如 superweb2pdf）"),
) -> None:
    """卸载插件（需 SOUWEN_ENABLE_PLUGIN_INSTALL=1）"""
    from souwen.plugin_manager import uninstall_plugin

    console.print(f"[dim]正在卸载 {package}...[/dim]")
    result = _run_async(uninstall_plugin(package))
    if result["success"]:
        console.print("[green]✅ 卸载成功。重启后生效。[/green]")
    else:
        console.print(f"[red]❌ 卸载失败: {result['output']}[/red]")
        raise typer.Exit(code=1)


@plugins_app.command("reload")
def reload_cmd() -> None:
    """重新扫描插件（追加模式）"""
    from souwen.plugin_manager import reload_plugins

    result = reload_plugins()
    console.print(f"[green]{result['message']}[/green]")
    if result["loaded"]:
        console.print(f"  新增: {', '.join(result['loaded'])}")
    if result["errors"]:
        for err in result["errors"]:
            console.print(f"  [red]错误: {err.get('name', '?')} — {err.get('error', '?')}[/red]")


@plugins_app.command("health")
def health_cmd(
    name: str = typer.Argument(..., help="插件名称（必须已加载）"),
    timeout: float = typer.Option(
        DEFAULT_PLUGIN_HEALTH_TIMEOUT_SECONDS,
        "--timeout",
        "-t",
        help="health_check 超时秒数。",
    ),
) -> None:
    """运行单个插件的 health_check（对应 GET /admin/plugins/{name}/health）。"""
    result = _run_async(run_plugin_health(name, timeout=timeout))
    state = str(result.get("status", "")).lower()
    if state == "not_loaded":
        console.print(f"[red]❌ {result.get('message', '插件未加载')}[/red]")
        raise typer.Exit(code=1)
    if state in {"ok", "healthy"}:
        console.print(f"[green]✅ {name} 健康[/green]")
    elif state in {"degraded", "warn", "warning"}:
        console.print(f"[yellow]⚠ {name}: {state}[/yellow]")
    else:
        console.print(f"[red]❌ {name}: {state or 'error'}[/red]")
    for key, value in result.items():
        if key == "status":
            continue
        console.print(f"  {key}: {value}")
    if state not in {"ok", "healthy", "degraded", "warn", "warning"}:
        raise typer.Exit(code=1)
