"""doctor 命令组：检查数据源与 edition 能力。"""

from __future__ import annotations

import json as json_module

import typer

from souwen.cli._common import _run_async, console

doctor_app = typer.Typer(
    help="检查数据源健康状态与当前 edition 能力",
    invoke_without_command=True,
    no_args_is_help=False,
)


@doctor_app.callback(invoke_without_command=True)
def doctor_cmd(
    ctx: typer.Context,
    live: bool = typer.Option(False, "--live", help="执行真实联网探测（默认只做静态检查）"),
    source: list[str] | None = typer.Option(
        None,
        "--source",
        "-s",
        help="只对指定 source 执行 live probe，可重复",
    ),
    timeout: float = typer.Option(5.0, "--timeout", help="单源 live probe 超时秒数"),
) -> None:
    """检查所有数据源可用性"""
    if ctx.invoked_subcommand is not None:
        return
    from souwen.doctor import check_all, check_all_live, format_report

    results = _run_async(check_all_live(sources=source, timeout=timeout)) if live else check_all()
    console.print(format_report(results))


@doctor_app.command("edition")
def doctor_edition_cmd(
    json_output: bool = typer.Option(False, "--json", "-j", help="输出 JSON"),
) -> None:
    """检查当前 edition 声明能力与可用能力"""
    from souwen.doctor import check_edition, format_edition_report

    report = check_edition()
    if json_output:
        typer.echo(json_module.dumps(report, ensure_ascii=False, indent=2))
        return
    console.print(format_edition_report(report))
