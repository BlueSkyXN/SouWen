"""CLI 命令测试"""
from __future__ import annotations

from typer.testing import CliRunner

from souwen.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    from souwen import __version__

    assert __version__ in result.output


def test_help_lists_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "serve" in result.output


def test_config_show_indicates_unconfigured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOUWEN_API_PASSWORD", raising=False)
    from souwen.config import reload_config

    reload_config()
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "未配置" in result.output


def test_sources_list():
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0


def test_keyboard_interrupt_exits_130(monkeypatch):
    import sys

    search_module = sys.modules["souwen.search"]

    async def fake_search(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(search_module, "search_papers", fake_search)
    result = runner.invoke(app, ["search", "paper", "test"])
    assert result.exit_code == 130
