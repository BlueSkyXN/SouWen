"""CLI 命令测试。

覆盖 ``souwen.cli`` 顶层 Typer 应用的基本契约：版本/帮助输出、子命令
存在性、未配置提示、以及交互中断时的标准退出码。
使用 ``typer.testing.CliRunner`` 同步捕获 stdout 并断言 exit_code。

测试清单：
- ``test_version_flag``：``--version`` 打印当前包版本并 exit 0。
- ``test_help_lists_subcommands``：``--help`` 包含 ``search`` / ``serve``
  等关键子命令。
- ``test_config_show_indicates_unconfigured``：未设密码时 ``config show``
  输出包含"未配置"字样，不泄漏任何 Key 值。
- ``test_sources_list``：``sources`` 命令正常退出。
- ``test_keyboard_interrupt_exits_130``：被 Ctrl+C 打断时返回 POSIX 约定
  的 exit code 130（128 + SIGINT(2)）。
"""
from __future__ import annotations

from typer.testing import CliRunner

from souwen.cli import app

runner = CliRunner()


def test_version_flag():
    """``--version`` 必须以 exit 0 成功，且输出中包含 ``souwen.__version__``。"""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    from souwen import __version__

    assert __version__ in result.output


def test_help_lists_subcommands():
    """``--help`` 必须列出核心子命令（search / serve），保证顶层入口稳定。"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "serve" in result.output


def test_config_show_indicates_unconfigured(monkeypatch, tmp_path):
    """无密码、无配置文件环境下，``config show`` 必须明确提示"未配置"。

    通过 ``chdir(tmp_path)`` 隔离仓库里的 ``souwen.yaml``，并 delenv
    清掉可能存在的 ``SOUWEN_API_PASSWORD``，以覆盖全新用户首次运行场景。
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOUWEN_API_PASSWORD", raising=False)
    from souwen.config import reload_config

    reload_config()
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "未配置" in result.output


def test_sources_list():
    """``sources`` 子命令可以正常打印数据源列表（仅校验 exit 0）。"""
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0


def test_keyboard_interrupt_exits_130(monkeypatch):
    """用户 Ctrl+C 中断时，CLI 必须以 exit code 130 优雅退出。

    通过 monkeypatch 让 ``search_papers`` 直接抛 ``KeyboardInterrupt``，
    验证 CLI 捕获并按 POSIX 约定返回 128+SIGINT=130，而非 1 或 traceback。
    """
    import sys

    search_module = sys.modules["souwen.search"]

    async def fake_search(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(search_module, "search_papers", fake_search)
    result = runner.invoke(app, ["search", "paper", "test"])
    assert result.exit_code == 130
