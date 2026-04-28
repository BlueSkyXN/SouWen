"""plugins 命令组：插件管理"""

from __future__ import annotations

import typer
from rich.table import Table

from souwen.cli._common import _run_async, console

plugins_app = typer.Typer(
    name="plugins",
    help="插件管理 — 列表、启用/禁用、安装/卸载、重载",
    no_args_is_help=True,
)


@plugins_app.command("list")
def list_cmd() -> None:
    """列出所有插件"""
    from souwen.plugin_manager import is_restart_required, list_plugins

    plugins = list_plugins()

    if is_restart_required():
        console.print("[bold yellow]⚠ 插件状态已变更，重启后完全生效。[/bold yellow]")
        console.print()

    if not plugins:
        console.print("[dim]未发现任何插件。[/dim]")
        return

    table = Table(title="🔌 SouWen 插件", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Source", style="magenta")
    table.add_column("Version", style="dim")
    table.add_column("Description", style="dim")

    status_icons = {
        "loaded": "[green]✅ 已加载[/green]",
        "available": "[yellow]📦 可用[/yellow]",
        "disabled": "[red]⛔ 禁用[/red]",
        "error": "[red]❌ 错误[/red]",
    }

    for p in plugins:
        table.add_row(
            p.name,
            status_icons.get(p.status, p.status),
            p.source,
            p.version or "-",
            p.description or "-",
        )

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
    from souwen.plugin_manager import disable_plugin

    result = disable_plugin(name)
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
