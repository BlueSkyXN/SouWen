"""CLI 公共工具：console、版本回调、异步运行助手"""

from __future__ import annotations

import asyncio
import sys

import typer
from rich.console import Console

from souwen import __version__

console = Console()


def _deprecation_notice(old_cmd: str) -> None:
    """Print a one-line deprecation notice to stderr (non-blocking)."""
    print(
        f"⚠ '{old_cmd}' will be reorganized in v2.0. See `souwen --help` for details.",
        file=sys.stderr,
    )


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
