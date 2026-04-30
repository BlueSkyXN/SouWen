"""SouWen CLI — typer + rich 命令行工具

文件用途：
    提供命令行接口，让用户快速搜索论文、专利、网页。基于 typer（FastAPI 作者的 CLI 库）
    和 rich（彩色终端输出）。支持全局选项（--version、--verbose、--quiet）以及
    多个子命令组。

模块结构（V1 重构后）：
    cli/__init__.py      - 主 app 与全局回调
    cli/_common.py       - 共享工具（console / _run_async / _version_callback）
    cli/search.py        - search paper/patent/web/images/videos
    cli/fetch.py         - fetch / links / sitemap
    cli/youtube.py       - youtube trending/video/transcript
    cli/bilibili.py      - bilibili search/video/...
    cli/wayback.py       - wayback cdx/check/save
    cli/config_cmds.py   - config show/init/backend/source/proxy
    cli/sources.py       - sources
    cli/serve.py         - serve
    cli/doctor.py        - doctor
    cli/mcp.py           - mcp
    cli/warp.py          - warp status/enable/disable/modes/register/test

全局选项（main 回调）：
    --version / -V：显示版本并退出
    --verbose / -v：日志级别（默认 WARNING；-v → INFO；-vv → DEBUG）
    --quiet / -q：强制 WARNING 级别
"""

from __future__ import annotations

import logging

import typer

from souwen.cli._common import _run_async, _version_callback, console

app = typer.Typer(
    name="souwen",
    help="SouWen — 面向 AI Agent 的学术论文 + 专利 + 网页统一搜索工具",
    no_args_is_help=True,
)


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


# ---------------------------------------------------------------------------
# 子命令注册：导入各子模块（它们通过 `from souwen.cli import app` 使用主 app）
# 注意：必须在 `app` 定义之后导入，否则会循环导入失败
# ---------------------------------------------------------------------------
from souwen.cli import (  # noqa: E402, F401
    bilibili,
    config_cmds,
    doctor,
    fetch,
    mcp,
    plugins,
    search,
    serve,
    sources,
    warp,
    wayback,
    youtube,
)

# 子 app 注册到主 app
app.add_typer(search.search_app, name="search")
app.add_typer(youtube.youtube_app, name="youtube")
app.add_typer(bilibili.bilibili_app, name="bilibili")
app.add_typer(wayback.wayback_app, name="wayback")
app.add_typer(config_cmds.config_app, name="config")
app.add_typer(warp.warp_app, name="warp")
app.add_typer(plugins.plugins_app, name="plugins")

# 兼容性导出：tests/test_infra.py 直接 `from souwen.cli import _mask_value`
from souwen.cli.config_cmds import _mask_value  # noqa: E402, F401

__all__ = ["app", "main", "console", "_run_async", "_version_callback", "_mask_value"]


if __name__ == "__main__":
    app()
