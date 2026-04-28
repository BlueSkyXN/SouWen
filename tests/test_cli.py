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

from pathlib import Path

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


def test_fetch_help_lists_arxiv_fulltext_provider():
    """fetch --help 应暴露 arxiv_fulltext provider。"""
    result = runner.invoke(app, ["fetch", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "arxiv_fulltext" in result.output


def test_fetch_rejects_unknown_provider():
    """fetch 命令应在参数校验阶段拒绝未知 provider。"""
    result = runner.invoke(app, ["fetch", "https://example.com", "-p", "nope"])
    assert result.exit_code != 0
    assert "无效提供者" in result.output


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


def test_search_paper_uses_registry_defaults_when_sources_omitted(monkeypatch):
    """未显式传 ``--sources`` 时，应透传 ``None`` 让 registry 默认源生效。"""
    import sys

    search_module = sys.modules["souwen.search"]
    captured = {}

    async def fake_search(query, sources=None, per_page=10, **kwargs):
        captured["query"] = query
        captured["sources"] = sources
        captured["per_page"] = per_page
        return []

    monkeypatch.setattr(search_module, "search_papers", fake_search)
    result = runner.invoke(app, ["search", "paper", "test", "--json"])
    assert result.exit_code == 0
    assert captured == {"query": "test", "sources": None, "per_page": 5}


def test_plugins_new_scaffolds_project(monkeypatch, tmp_path: Path):
    """``plugins new`` creates a complete plugin project skeleton."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["plugins", "new", "demo_plugin"])

    assert result.exit_code == 0
    root = tmp_path / "demo_plugin"
    expected_files = [
        "pyproject.toml",
        "demo_plugin/__init__.py",
        "demo_plugin/client.py",
        "demo_plugin/handler.py",
        "tests/test_demo_plugin.py",
        "README.md",
    ]
    for rel_path in expected_files:
        assert (root / rel_path).is_file()

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    init_py = (root / "demo_plugin/__init__.py").read_text(encoding="utf-8")
    assert '[project.entry-points."souwen.plugins"]' in pyproject
    assert 'demo_plugin = "demo_plugin:plugin"' in pyproject
    assert "Plugin(" in init_py
    assert "SourceAdapter(" in init_py


def test_plugins_new_rejects_invalid_name(monkeypatch, tmp_path: Path):
    """Plugin scaffold names must be lowercase alphanumeric plus underscores."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["plugins", "new", "Bad-Plugin"])

    assert result.exit_code == 1
    assert "必须以小写字母开头" in result.output
    assert not (tmp_path / "Bad-Plugin").exists()


def test_plugins_new_rejects_digit_prefix(monkeypatch, tmp_path: Path):
    """Plugin scaffold names must also be valid Python package identifiers."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["plugins", "new", "1plugin"])

    assert result.exit_code == 1
    assert not (tmp_path / "1plugin").exists()
