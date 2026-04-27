"""warp 子命令组：status / enable / disable / modes / register / test"""

from __future__ import annotations

import shutil

import typer
from rich.panel import Panel
from rich.table import Table

from souwen.cli._common import _run_async, console

warp_app = typer.Typer(help="WARP 代理管理")


def _get_warp_manager():
    """延迟导入并返回 WARP 管理器单例。"""
    from souwen.server.warp import WarpManager

    return WarpManager.get_instance()


@warp_app.command("status")
def warp_status() -> None:
    """显示 WARP 代理状态"""
    mgr = _get_warp_manager()
    _run_async(mgr.reconcile())

    s = mgr.get_status()
    status_color = {
        "enabled": "green",
        "disabled": "dim",
        "starting": "yellow",
        "stopping": "yellow",
        "error": "red",
    }.get(s["status"], "white")

    table = Table(title="🛡️  WARP 代理状态", show_lines=True)
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")

    table.add_row("状态", f"[{status_color}]{s['status']}[/{status_color}]")
    table.add_row("模式", s["mode"])
    table.add_row("管理者", s["owner"])
    table.add_row("SOCKS5 端口", str(s["socks_port"]))
    if s.get("http_port", 0) > 0:
        table.add_row("HTTP 端口", str(s["http_port"]))
    table.add_row("出口 IP", s.get("ip") or "—")
    if s.get("pid", 0) > 0:
        table.add_row("进程 PID", str(s["pid"]))
    if s.get("protocol"):
        table.add_row("协议", s["protocol"])
    if s.get("proxy_type"):
        table.add_row("代理类型", s["proxy_type"])
    if s.get("interface"):
        table.add_row("网卡", s["interface"])
    if s.get("last_error"):
        table.add_row("错误", f"[red]{s['last_error']}[/red]")

    console.print(table)

    modes = s.get("available_modes", {})
    mode_text = "  ".join(
        f"[green]✓[/green] {m}" if avail else f"[dim]✗ {m}[/dim]" for m, avail in modes.items()
    )
    console.print(f"\n可用模式: {mode_text}")


@warp_app.command("enable")
def warp_enable(
    mode: str = typer.Option(
        "auto", help="模式: auto | wireproxy | kernel | usque | warp-cli | external"
    ),
    socks_port: int = typer.Option(1080, help="SOCKS5 端口"),
    endpoint: str = typer.Option("", help="自定义 WARP Endpoint"),
) -> None:
    """启用 WARP 代理"""
    mgr = _get_warp_manager()
    ep = endpoint if endpoint else None

    with console.status("[bold cyan]正在启动 WARP 代理...[/bold cyan]"):
        result = _run_async(mgr.enable(mode=mode, socks_port=socks_port, endpoint=ep))

    if result.get("ok"):
        console.print(
            Panel(
                f"[green]✅ WARP 已启用[/green]\n"
                f"模式: {result.get('mode', '—')}\n"
                f"出口 IP: {result.get('ip', '—')}",
                title="WARP 代理",
                border_style="green",
            )
        )
    else:
        console.print(f"[red]❌ 启动失败: {result.get('error', '未知错误')}[/red]")
        raise typer.Exit(1)


@warp_app.command("disable")
def warp_disable() -> None:
    """禁用 WARP 代理"""
    mgr = _get_warp_manager()

    with console.status("[bold cyan]正在关闭 WARP 代理...[/bold cyan]"):
        result = _run_async(mgr.disable())

    if result.get("ok"):
        console.print("[green]✅ WARP 已关闭[/green]")
    else:
        console.print(f"[red]❌ 关闭失败: {result.get('error', '未知错误')}[/red]")
        raise typer.Exit(1)


@warp_app.command("modes")
def warp_modes() -> None:
    """列出所有 WARP 模式及其可用性"""
    from souwen.config import get_config

    mgr = _get_warp_manager()
    cfg = get_config()

    table = Table(title="🛡️  WARP 可用模式", show_lines=True)
    table.add_column("模式", style="cyan", width=12)
    table.add_column("状态", width=8)
    table.add_column("协议", width=12)
    table.add_column("权限", width=8)
    table.add_column("代理类型", width=14)
    table.add_column("说明")

    modes_info = [
        ("wireproxy", mgr._has_wireproxy(), "WireGuard", False, "SOCKS5", "用户态 WireGuard"),
        (
            "kernel",
            mgr._has_kernel_wg(),
            "WireGuard",
            True,
            "SOCKS5",
            "内核 WireGuard + microsocks",
        ),
        ("usque", mgr._has_usque(), "MASQUE/QUIC", False, "SOCKS5+HTTP", "MASQUE 协议"),
        (
            "warp-cli",
            mgr._has_warp_cli(),
            "官方客户端",
            True,
            "SOCKS5+HTTP",
            "Cloudflare 官方 + GOST",
        ),
        ("external", bool(cfg.warp_external_proxy), "任意", False, "SOCKS5/HTTP", "外部代理容器"),
    ]

    for name, available, protocol, needs_priv, proxy_type, desc in modes_info:
        status = "[green]✓ 可用[/green]" if available else "[dim]✗ 不可用[/dim]"
        priv = "[yellow]需要[/yellow]" if needs_priv else "[green]无需[/green]"
        table.add_row(name, status, protocol, priv, proxy_type, desc)

    console.print(table)


@warp_app.command("register")
def warp_register(
    backend: str = typer.Option("wgcf", help="注册后端: wgcf | usque"),
) -> None:
    """注册新的 Cloudflare WARP 账号"""
    mgr = _get_warp_manager()

    with console.status(f"[bold cyan]正在注册 WARP 账号 (后端: {backend})...[/bold cyan]"):
        if backend == "usque":
            usque_bin = shutil.which("usque")
            if not usque_bin:
                console.print("[red]❌ usque 未安装[/red]")
                raise typer.Exit(1)

            config_path = "/app/data/usque-config.json"
            success = _run_async(mgr._usque_register(usque_bin, config_path))
            if success:
                console.print(f"[green]✅ usque 注册成功[/green]\n配置: {config_path}")
            else:
                console.print("[red]❌ 注册失败（可能触发速率限制）[/red]")
                raise typer.Exit(1)

        elif backend == "wgcf":
            result = mgr._wgcf_register()
            if result:
                console.print(f"[green]✅ wgcf 注册成功[/green]\n配置: {result}")
            else:
                console.print("[red]❌ 注册失败（可能触发速率限制或 wgcf 未安装）[/red]")
                raise typer.Exit(1)
        else:
            console.print(f"[red]❌ 未知后端: {backend}[/red]")
            raise typer.Exit(1)


@warp_app.command("test")
def warp_test() -> None:
    """测试 WARP 代理连接"""
    mgr = _get_warp_manager()
    s = mgr.get_status()

    if s["status"] != "enabled":
        console.print("[yellow]⚠️ WARP 未启用[/yellow]")
        raise typer.Exit(1)

    port = s["socks_port"]
    with console.status("[bold cyan]正在测试连接...[/bold cyan]"):
        alive = mgr._check_socks_alive(port)
        ip = mgr._get_warp_ip(port) if alive else "unknown"

    if alive:
        console.print(
            Panel(
                f"[green]✅ 连接正常[/green]\n出口 IP: {ip}\n端口: {port}\n模式: {s['mode']}",
                title="WARP 连接测试",
                border_style="green",
            )
        )
    else:
        console.print("[red]❌ 连接失败 — SOCKS5 代理无响应[/red]")
        raise typer.Exit(1)
