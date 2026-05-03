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

import asyncio
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


def test_config_source_self_hosted_legacy_channel_api_key(monkeypatch):
    """``config source`` 详情页应识别旧版 self-hosted URL 通道。"""
    monkeypatch.setenv("SOUWEN_SEARXNG_URL", "")
    monkeypatch.setenv("SOUWEN_SOURCES", '{"searxng":{"api_key":"https://legacy-searxng.example"}}')
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["config", "source", "searxng"])
    assert result.exit_code == 0
    assert "API Key" in result.output
    assert "已配置" in result.output


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


def test_plugins_health_with_loaded_plugin(monkeypatch):
    """``plugins health <name>`` 调用本进程的 health_check（与 API 同源）。"""
    from souwen.plugin import Plugin

    async def healthy() -> dict[str, str]:
        return {"status": "ok", "latency_ms": "1"}

    plugin = Plugin(name="demo", health_check=healthy)
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {"demo": plugin})

    result = runner.invoke(app, ["plugins", "health", "demo"])

    assert result.exit_code == 0
    assert "demo 健康" in result.output
    assert "latency_ms" in result.output


def test_plugins_health_returns_error_when_not_loaded(monkeypatch):
    """未加载的插件应当退出码 1，并提示未加载。"""
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {})

    result = runner.invoke(app, ["plugins", "health", "missing"])

    assert result.exit_code == 1
    assert "未加载" in result.output


def test_plugins_health_handles_health_exception(monkeypatch):
    """health_check 抛异常时应捕获并以 error 状态退出码 1。"""
    from souwen.plugin import Plugin

    def boom() -> dict[str, str]:
        raise RuntimeError("upstream timeout")

    plugin = Plugin(name="boom", health_check=boom)
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {"boom": plugin})

    result = runner.invoke(app, ["plugins", "health", "boom"])

    assert result.exit_code == 1


def test_plugins_health_rejects_sync_wrapper_returning_coroutine(monkeypatch):
    """异步 health_check 必须声明为 async def，避免同步入口返回 coroutine。"""
    from souwen.plugin import Plugin

    async def inner() -> dict[str, str]:
        return {"status": "ok"}

    def wrapper():
        return inner()

    plugin = Plugin(name="wrapped", health_check=wrapper)
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {"wrapped": plugin})

    result = runner.invoke(app, ["plugins", "health", "wrapped"])

    assert result.exit_code == 1
    assert "async def" in result.output


def test_plugins_health_times_out(monkeypatch):
    """单个插件 health_check 超时应返回错误，而不是无限等待。"""
    from souwen.plugin import Plugin

    async def slow() -> dict[str, str]:
        await asyncio.sleep(1)
        return {"status": "ok"}

    plugin = Plugin(name="slow", health_check=slow)
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {"slow": plugin})

    result = runner.invoke(app, ["plugins", "health", "slow", "--timeout", "0.01"])

    assert result.exit_code == 1
    assert "超时" in result.output


def test_plugins_list_with_health_flag(monkeypatch):
    """``plugins list --health`` 给已加载插件附加 Health 列。"""
    from souwen.plugin import Plugin
    from souwen.plugin_manager import PluginInfo

    async def healthy() -> dict[str, str]:
        return {"status": "ok"}

    plugin = Plugin(name="demo", health_check=healthy)
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {"demo": plugin})
    monkeypatch.setattr(
        "souwen.plugin_manager.list_plugins",
        lambda: [
            PluginInfo(
                name="demo",
                status="loaded",
                source="entry_point",
                version="1.0.0",
                description="demo plugin",
            ),
        ],
    )
    monkeypatch.setattr("souwen.plugin_manager.is_restart_required", lambda: False)

    result = runner.invoke(app, ["plugins", "list", "--health"], env={"COLUMNS": "200"})

    assert result.exit_code == 0
    assert "Health" in result.output
    assert "demo" in result.output


def test_plugins_list_health_marks_timeout(monkeypatch):
    """批量 health check 中单个插件超时应落到 error 状态，不拖住列表命令。"""
    from souwen.plugin import Plugin
    from souwen.plugin_manager import PluginInfo

    async def slow() -> dict[str, str]:
        await asyncio.sleep(1)
        return {"status": "ok"}

    plugin = Plugin(name="slow", health_check=slow)
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {"slow": plugin})
    monkeypatch.setattr(
        "souwen.plugin_manager.list_plugins",
        lambda: [
            PluginInfo(
                name="slow",
                status="loaded",
                source="entry_point",
                version="1.0.0",
                description="slow plugin",
            ),
        ],
    )
    monkeypatch.setattr("souwen.plugin_manager.is_restart_required", lambda: False)

    result = runner.invoke(
        app,
        ["plugins", "list", "--health", "--health-timeout", "0.01"],
        env={"COLUMNS": "200"},
    )

    assert result.exit_code == 0
    assert "Health" in result.output
    assert "error" in result.output
