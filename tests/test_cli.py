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
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from souwen.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_config_files(monkeypatch, tmp_path):
    """CLI 用例固定在空配置环境运行，不读取用户目录里的真实配置。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
    for key in (
        "SOUWEN_API_PASSWORD",
        "SOUWEN_VISITOR_PASSWORD",
        "SOUWEN_USER_PASSWORD",
        "SOUWEN_ADMIN_PASSWORD",
        "SOUWEN_EDITION",
    ):
        monkeypatch.delenv(key, raising=False)
    from souwen.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


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


def test_redact_cli_text_uses_fallback_for_empty_values():
    from souwen.cli._common import redact_cli_text

    assert redact_cli_text(None, "未知错误") == "未知错误"
    assert redact_cli_text("", "未知错误") == "未知错误"


def test_fetch_rejects_unknown_provider():
    """fetch 命令应在参数校验阶段拒绝未知 provider。"""
    result = runner.invoke(app, ["fetch", "https://example.com", "-p", "nope"])
    assert result.exit_code != 0
    assert "无效提供者" in result.output


def test_fetch_rejects_basic_disallowed_provider(monkeypatch):
    """fetch 命令应在参数校验阶段拒绝当前 edition 不允许的已知 provider。"""
    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(
        app,
        ["fetch", "https://example.com", "-p", "jina_reader"],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code != 0
    assert "fetch provider 'jina_reader' requires" in result.output
    assert "edition=pro, current edition=basic" in result.output


def test_fetch_accepts_runtime_plugin_provider(monkeypatch, clean_registry):
    """CLI import 后注册的 fetch provider 也应能通过参数校验。"""
    from souwen.cli import fetch as cli_fetch
    from souwen.models import FetchResponse
    from souwen.registry import fetch_providers
    from souwen.registry.adapter import MethodSpec, SourceAdapter
    from souwen.registry.views import _reg_external
    from souwen.web import fetch as web_fetch

    provider = "runtime_fetch_probe"
    assert provider not in cli_fetch._FETCH_PROVIDER_NAMES
    monkeypatch.setenv("SOUWEN_EDITION", "full")
    from souwen.config import get_config

    get_config.cache_clear()

    assert _reg_external(
        SourceAdapter(
            name=provider,
            domain="fetch",
            integration="scraper",
            description="runtime fetch provider probe",
            config_field=None,
            client_loader=lambda: object,
            methods={"fetch": MethodSpec("fetch")},
            category="fetch",
        )
    )
    assert provider in {adapter.name for adapter in fetch_providers()}

    captured: dict[str, list[str] | None] = {}

    async def fake_fetch_content(
        urls,
        providers=None,
        strategy="fallback",
        timeout=30.0,
        **_kwargs,
    ):
        captured["providers"] = providers
        return FetchResponse(
            urls=urls,
            results=[],
            total=len(urls),
            total_ok=0,
            total_failed=0,
            providers=providers or [],
            strategy=strategy,
        )

    monkeypatch.setattr(web_fetch, "fetch_content", fake_fetch_content)

    result = runner.invoke(app, ["fetch", "https://example.com", "-p", provider])

    assert result.exit_code == 0, result.output
    assert captured["providers"] == [provider]


def test_warp_modes_marks_basic_disallowed_modes(monkeypatch):
    """warp modes 应展示当前 edition 下不可用的模式及升级原因。"""
    from souwen.cli import warp as cli_warp
    from souwen.config import get_config

    class FakeWarpManager:
        def _has_wireproxy(self):
            return True

        def _has_kernel_wg(self):
            return True

        def _has_usque(self):
            return True

        def _has_warp_cli(self):
            return True

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    get_config.cache_clear()
    monkeypatch.setattr(cli_warp, "_get_warp_manager", lambda: FakeWarpManager())

    result = runner.invoke(app, ["warp", "modes"], env={"COLUMNS": "220"})

    assert result.exit_code == 0
    assert "edition=basic" in result.output
    assert "需升级" in result.output
    assert "WARP mode 'usque' requires edition=pro" in result.output
    assert "WARP mode 'warp-cli' requires edition=pro" in result.output


def test_warp_enable_rejects_basic_disallowed_mode_before_manager(monkeypatch):
    """warp enable 对当前 edition 不支持的已知模式应直接返回清晰错误。"""
    from souwen.cli import warp as cli_warp
    from souwen.config import get_config

    def fail_if_called():
        raise AssertionError("manager should not be constructed for edition-denied mode")

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    get_config.cache_clear()
    monkeypatch.setattr(cli_warp, "_get_warp_manager", fail_if_called)

    result = runner.invoke(app, ["warp", "enable", "--mode", "usque"])

    assert result.exit_code == 1
    assert "WARP mode 'usque' requires edition=pro" in result.output
    assert "current edition=basic" in result.output


def test_fetch_cli_redacts_result_errors(monkeypatch):
    """``fetch`` 文本输出不应泄漏 FetchResult.error 或 URL query 中的 secret。"""
    from souwen.models import FetchResponse, FetchResult
    from souwen.web import fetch as web_fetch

    async def fake_fetch_content(urls, providers=None, strategy="fallback", timeout=30.0, **kwargs):
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url="https://example.com/cb?apiKey=url-secret&safe=1",
                    final_url="https://example.com/cb?apiKey=url-secret&safe=1",
                    source="builtin",
                    error="provider failed token=fetch-secret Cookie: sid=session-secret",
                )
            ],
            total=1,
            total_ok=0,
            total_failed=1,
            providers=providers or ["builtin"],
            strategy=strategy,
        )

    monkeypatch.setattr(web_fetch, "fetch_content", fake_fetch_content)

    result = runner.invoke(app, ["fetch", "https://example.com/cb?apiKey=input-secret&safe=1"])

    assert result.exit_code == 0, result.output
    assert "url-secret" not in result.output
    assert "fetch-secret" not in result.output
    assert "session-secret" not in result.output
    assert "apiKey=***" in result.output
    assert "token:***" in result.output
    assert "Cookie:***" in result.output


def test_bilibili_cli_error_redacts_secret_detail(monkeypatch):
    """Bilibili CLI 错误输出不应泄漏上游异常中的 Cookie/token。"""
    from souwen.web.bilibili._errors import BilibiliAuthRequired

    class FakeBilibiliClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get_video_details(self, bvid):
            raise BilibiliAuthRequired(
                -101,
                "need login Cookie: SESSDATA=sess-secret; token=api-secret "
                "callback https://bili.example/cb?apiKey=url-secret&safe=1",
            )

    monkeypatch.setattr("souwen.web.bilibili.BilibiliClient", FakeBilibiliClient)

    result = runner.invoke(app, ["bilibili", "video", "BV1xx411c7mD"])

    assert result.exit_code == 1
    assert "sess-secret" not in result.output
    assert "api-secret" not in result.output
    assert "url-secret" not in result.output
    assert "Cookie:***" in result.output
    assert "token:***" in result.output
    assert "apiKey=***" in result.output


def test_bilibili_video_cli_renders_detail_model(monkeypatch):
    """``bilibili video`` 应按当前 BilibiliVideoDetail 模型字段渲染。"""
    from souwen.web.bilibili.models import BilibiliVideoDetail, VideoOwner

    class FakeBilibiliClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get_video_details(self, bvid):
            return BilibiliVideoDetail(
                bvid=bvid,
                title="Example Bili Video",
                description="Example description",
                owner=VideoOwner(mid=123, name="Example UP"),
            )

    monkeypatch.setattr("souwen.web.bilibili.BilibiliClient", FakeBilibiliClient)

    result = runner.invoke(app, ["bilibili", "video", "BV1xx411c7mD"])

    assert result.exit_code == 0, result.output
    assert "Example Bili Video" in result.output
    assert "Example UP" in result.output
    assert "https://space.bilibili.com/123" in result.output
    assert "Example description" in result.output


def test_youtube_cli_config_error_redacts_secret_detail(monkeypatch):
    """YouTube CLI ConfigError 输出不应泄漏异常文本中的 secret。"""
    from souwen.core.exceptions import ConfigError

    class FakeYouTubeClient:
        def __init__(self):
            raise ConfigError(
                "youtube_api_key token=yt-secret",
                "YouTube Cookie: sid=session-secret",
                "https://yt.example/cb?apiKey=url-secret&safe=1",
            )

    monkeypatch.setattr("souwen.web.youtube.YouTubeClient", FakeYouTubeClient)

    result = runner.invoke(app, ["youtube", "trending"])

    assert result.exit_code == 1
    assert "yt-secret" not in result.output
    assert "session-secret" not in result.output
    assert "url-secret" not in result.output
    assert "token:***" in result.output
    assert "Cookie:***" in result.output
    assert "apiKey=***" in result.output


def test_youtube_trending_cli_handles_web_search_response(monkeypatch):
    """``youtube trending`` 应正确处理 YouTubeClient 返回的 WebSearchResponse。"""
    from souwen.models import WebSearchResponse, WebSearchResult

    class FakeYouTubeClient:
        async def get_trending(
            self,
            region_code="US",
            video_category_id=None,
            max_results=20,
        ):
            return WebSearchResponse(
                query="trending",
                source="youtube",
                results=[
                    WebSearchResult(
                        source="youtube",
                        title="Example Video",
                        url="https://www.youtube.com/watch?v=abc123",
                        snippet="Example Channel",
                        engine="youtube",
                    )
                ],
                total_results=1,
            )

    monkeypatch.setattr("souwen.web.youtube.YouTubeClient", FakeYouTubeClient)

    result = runner.invoke(app, ["youtube", "trending"])

    assert result.exit_code == 0, result.output
    assert "Example Video" in result.output
    assert "YouTube 热门" in result.output


def test_wayback_cli_exception_redacts_secret_detail(monkeypatch):
    """Wayback CLI 异常输出不应泄漏 token/cookie/URL secret。"""

    class FakeWaybackClient:
        async def query_snapshots(self, **kwargs):
            raise RuntimeError(
                "cdx failed token=wayback-secret Cookie: sid=session-secret "
                "callback https://archive.example/cb?apiKey=url-secret&safe=1"
            )

    monkeypatch.setattr("souwen.web.wayback.WaybackClient", FakeWaybackClient)

    result = runner.invoke(app, ["wayback", "cdx", "https://example.com"])

    assert result.exit_code == 1
    assert "wayback-secret" not in result.output
    assert "session-secret" not in result.output
    assert "url-secret" not in result.output
    assert "token:***" in result.output
    assert "Cookie:***" in result.output
    assert "apiKey=***" in result.output


def test_config_show_indicates_unconfigured(monkeypatch, tmp_path):
    """无密码、无配置文件环境下，``config show`` 必须明确提示"未配置"。

    通过 ``chdir(tmp_path)`` 隔离仓库里的 ``souwen.yaml``，并 delenv
    清掉可能存在的认证环境变量，以覆盖全新用户首次运行场景。
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOUWEN_API_PASSWORD", raising=False)
    monkeypatch.delenv("SOUWEN_VISITOR_PASSWORD", raising=False)
    monkeypatch.delenv("SOUWEN_USER_PASSWORD", raising=False)
    monkeypatch.delenv("SOUWEN_ADMIN_PASSWORD", raising=False)
    from souwen.config import reload_config

    reload_config()
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "未配置" in result.output


def test_config_show_redacts_nested_source_secrets(monkeypatch):
    """``config show`` 不应泄漏 sources 中的嵌套凭据。"""
    monkeypatch.setenv(
        "SOUWEN_SOURCES",
        (
            '{"openalex": {'
            '"api_key": "source-secret", '
            '"headers": {"Authorization": "Bearer header-secret", "X-Trace-Id": "trace-1"}, '
            '"params": {"apiKey": "param-secret", "page": 1}'
            "}}"
        ),
    )
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0, result.output
    assert "source-secret" not in result.output
    assert "header-secret" not in result.output
    assert "param-secret" not in result.output
    assert "trace-1" in result.output
    assert "***" in result.output


def test_config_init_includes_openalex_key_and_legacy_email(monkeypatch, tmp_path):
    """CLI 生成模板应同时提供当前 API Key 和兼容联系邮箱字段。"""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["config", "init"])

    assert result.exit_code == 0
    content = (tmp_path / "souwen.yaml").read_text(encoding="utf-8")
    assert "openalex_api_key: ~" in content
    assert "openalex_email: ~" in content


def test_config_backend_lists_current_backends(monkeypatch, tmp_path):
    """``config backend`` 应能读取 HTTP backend 快照，不依赖 re-export 私有变量。"""
    monkeypatch.chdir(tmp_path)
    from souwen.config import reload_config

    reload_config()
    result = runner.invoke(app, ["config", "backend"])
    assert result.exit_code == 0
    assert "curl_cffi" in result.output
    assert "duckduckgo" in result.output


def test_config_backend_trims_default(monkeypatch, tmp_path):
    """``config backend --default`` 应先 trim，再校验和保存。"""
    monkeypatch.chdir(tmp_path)
    from souwen.config import get_config, reload_config

    reload_config()
    result = runner.invoke(app, ["config", "backend", "--default", " httpx "])

    assert result.exit_code == 0, result.output
    assert get_config().default_http_backend == "httpx"
    assert "全局默认已设为: httpx" in result.output


def test_config_backend_set_trims_source_and_backend(monkeypatch, tmp_path):
    """``config backend --set`` 应先 trim source/backend，再校验和保存。"""
    monkeypatch.chdir(tmp_path)
    from souwen.config import get_config, reload_config

    reload_config()
    result = runner.invoke(app, ["config", "backend", "--set", " duckduckgo = httpx "])

    assert result.exit_code == 0, result.output
    assert get_config().http_backend["duckduckgo"] == "httpx"
    assert "duckduckgo 已设为: httpx" in result.output


@pytest.mark.parametrize(
    ("set_value", "message"),
    [
        (" =httpx", "source 不能是空字符串"),
        ("duckduckgo= ", "backend 不能是空字符串"),
    ],
)
def test_config_backend_set_rejects_blank_parts(monkeypatch, tmp_path, set_value, message):
    """``config backend --set`` 应在校验前拒绝 strip 后为空的两侧参数。"""
    monkeypatch.chdir(tmp_path)
    from souwen.config import get_config, reload_config

    reload_config()
    result = runner.invoke(app, ["config", "backend", "--set", set_value])

    assert result.exit_code == 1
    assert message in result.output
    assert get_config().http_backend == {}


def test_sources_list():
    """``sources`` Rich 表应把静态 gate 和 runtime 分列展示。"""
    result = runner.invoke(app, ["sources"], env={"COLUMNS": "240"})
    assert result.exit_code == 0
    assert "Static Gate" in result.output
    assert "Runtime" in result.output


def test_sources_available_only_help_describes_static_and_runtime_axes():
    result = runner.invoke(app, ["sources", "--help"], env={"COLUMNS": "240"})

    assert result.exit_code == 0
    assert "仅列出静态 gate 与当前 runtime 均可用的源" in result.output


def test_sources_json_outputs_formal_catalog_contract():
    """``sources --json`` 输出与 ``/api/v1/sources`` 一致的正式 catalog shape。"""
    result = runner.invoke(app, ["sources", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data) == {"sources", "categories", "defaults"}
    openalex = next(item for item in data["sources"] if item["name"] == "openalex")
    assert openalex["domain"] == "paper"
    assert openalex["category"] == "paper"
    assert openalex["capabilities"] == ["search"]
    assert openalex["auth_requirement"] == "optional"
    assert openalex["credential_fields"] == ["openalex_api_key"]
    assert openalex["credentials_satisfied"] is True
    assert openalex["configured_credentials"] is False
    assert openalex["min_edition"] == "pro"
    assert openalex["edition_available"] is True
    assert openalex["edition_reason"] == ""
    assert openalex["available"] is True


def test_sources_json_marks_edition_unavailable(monkeypatch):
    """``sources --json`` 应返回 edition metadata，并让 unavailable 源不可调度。"""
    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["sources", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    openalex = next(item for item in data["sources"] if item["name"] == "openalex")
    assert openalex["min_edition"] == "pro"
    assert openalex["edition_available"] is False
    assert "source 'openalex' requires edition=pro" in openalex["edition_reason"]
    assert openalex["available"] is False


def test_doctor_report_includes_edition(monkeypatch):
    """``doctor`` 报告应显示当前 edition 和需升级原因。"""
    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "edition=basic" in result.output
    assert "source 'openalex' requires" in result.output
    assert "edition=pro" in result.output
    assert "current edition=basic" in result.output


def test_doctor_live_invokes_explicit_probe(monkeypatch):
    """``doctor --live`` 应调用显式 live probe，并支持 source/timeout 参数。"""
    import souwen.doctor as doctor_mod

    captured: dict[str, object] = {}

    async def fake_check_all_live(sources=None, timeout=5.0, **kwargs):
        captured["sources"] = sources
        captured["timeout"] = timeout
        captured["kwargs"] = kwargs
        return [
            {
                "name": "openalex",
                "category": "paper",
                "status": "ok",
                "integration_type": "open_api",
                "required_key": None,
                "key_requirement": "none",
                "auth_requirement": "none",
                "credential_fields": [],
                "optional_credential_effect": None,
                "risk_level": "low",
                "risk_reasons": [],
                "distribution": "core",
                "package_extra": None,
                "stability": "stable",
                "usage_note": None,
                "min_edition": "basic",
                "edition": "pro",
                "edition_available": True,
                "edition_reason": "",
                "available": True,
                "message": "免配置",
                "enabled": True,
                "description": "OpenAlex",
                "channel": None,
                "live_probe": {
                    "status": "ok",
                    "message": "live search returned 1 result(s)",
                    "elapsed_ms": 1,
                },
            }
        ]

    monkeypatch.setattr(doctor_mod, "check_all_live", fake_check_all_live)

    result = runner.invoke(
        app,
        ["doctor", "--live", "--source", "openalex", "--timeout", "1"],
        env={"COLUMNS": "240"},
    )

    assert result.exit_code == 0, result.output
    assert captured["sources"] == ["openalex"]
    assert captured["timeout"] == 1.0
    assert "live probe: 1/1 ok" in result.output
    assert "live=ok: live search returned 1 result(s)" in result.output


def test_doctor_edition_outputs_report_and_json(monkeypatch):
    """``doctor edition`` 应输出当前 edition 能力报告，并支持 JSON。"""
    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["doctor", "edition"], env={"COLUMNS": "240"})
    assert result.exit_code == 0, result.output
    assert "Edition 自检 (edition=basic)" in result.output
    assert "需升级 source" in result.output
    assert "openalex" in result.output
    assert "WARP 可用模式: auto, wireproxy, external" in result.output
    assert "LLM requires edition=pro" in result.output

    json_result = runner.invoke(app, ["doctor", "edition", "--json"])
    assert json_result.exit_code == 0, json_result.output
    data = json.loads(json_result.output)
    assert data["edition"] == "basic"
    assert any(item["name"] == "openalex" for item in data["sources"]["upgrade_required"])
    assert any(
        item["name"] == "jina_reader" for item in data["fetch_providers"]["upgrade_required"]
    )
    assert data["warp"]["available_modes"] == ["auto", "wireproxy", "external"]
    assert data["llm"]["edition_available"] is False
    assert set(data["probe"]["mcp"]) == {"declared", "available", "reason"}
    package_extras = data["probe"]["package_extras"]
    assert set(package_extras) == {"declared", "available", "reason"}
    assert package_extras["declared"]["mcp"] == ["mcp"]
    assert package_extras["declared"]["scraper"] == ["curl_cffi"]
    assert package_extras["declared"]["web"] == ["trafilatura"]
    assert isinstance(package_extras["available"], list)
    assert isinstance(package_extras["reason"], str)


def test_sources_json_supports_filters(monkeypatch):
    """``sources`` 支持 effective available/category/capability 三类过滤。"""
    monkeypatch.setenv("SOUWEN_SOURCES", '{"duckduckgo": {"enabled": false}}')
    from souwen.config import get_config
    from souwen.feature_matrix import RuntimeProbe

    get_config.cache_clear()
    monkeypatch.setattr(
        "souwen.feature_matrix.public_adapter_runtime_probe",
        lambda _adapter: RuntimeProbe(True, ""),
    )
    result = runner.invoke(
        app,
        [
            "sources",
            "--json",
            "--available-only",
            "--category",
            "web_general",
            "--capability",
            "search",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sources"]
    assert all(item["available"] and item["runtime_available"] for item in data["sources"])
    assert all(item["category"] == "web_general" for item in data["sources"])
    assert all("search" in item["capabilities"] for item in data["sources"])
    assert "duckduckgo" not in {item["name"] for item in data["sources"]}


def test_sources_json_available_only_excludes_runtime_unavailable(monkeypatch):
    """Static availability alone must not pass ``--available-only``."""
    payload = {
        "sources": [
            {
                "name": "static_only",
                "available": True,
                "runtime_available": False,
            },
            {
                "name": "effective",
                "available": True,
                "runtime_available": True,
            },
            {
                "name": "runtime_only",
                "available": False,
                "runtime_available": True,
            },
        ],
        "categories": [],
        "defaults": {},
    }
    monkeypatch.setattr(
        "souwen.registry.catalog.public_source_catalog_payload",
        lambda _config: payload,
    )

    result = runner.invoke(app, ["sources", "--json", "--available-only"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data) == {"sources", "categories", "defaults"}
    assert [item["name"] for item in data["sources"]] == ["effective"]


def test_sources_rejects_unknown_category():
    """未知正式 category 需要明确失败，避免误以为空结果。"""
    result = runner.invoke(app, ["sources", "--category", "general"])
    assert result.exit_code == 1
    assert "未知 category" in result.output


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


def test_config_source_update_trims_runtime_fields(monkeypatch):
    """``config source`` 应在写入前规范化 source/proxy/backend/base_url。"""
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(
        app,
        [
            "config",
            "source",
            " openalex ",
            "--proxy",
            " WARP ",
            "--backend",
            " httpx ",
            "--base-url",
            " https://api.example.com/v1 ",
        ],
    )

    assert result.exit_code == 0, result.output
    cfg = get_config()
    sc = cfg.sources["openalex"]
    assert sc.proxy == "warp"
    assert sc.http_backend == "httpx"
    assert sc.base_url == "https://api.example.com/v1"


def test_config_source_rejects_invalid_proxy_before_save(monkeypatch):
    """``config source --proxy`` 应拒绝非法代理值，不写入频道配置。"""
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["config", "source", "openalex", "--proxy", "ftp://proxy"])

    assert result.exit_code == 1
    assert "代理 URL 无效" in result.output
    assert "openalex" not in get_config().sources


def test_config_source_rejects_invalid_base_url_before_save(monkeypatch):
    """``config source --base-url`` 应只接受 http/https URL。"""
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["config", "source", "openalex", "--base-url", "ftp://example"])

    assert result.exit_code == 1
    assert "base_url 必须为 http/https URL" in result.output
    assert "openalex" not in get_config().sources


def test_config_source_redacts_headers_and_params(monkeypatch):
    """``config source`` 详情页不应泄漏 headers/params 中的 secret。"""
    monkeypatch.setenv(
        "SOUWEN_SOURCES",
        (
            '{"openalex": {'
            '"headers": {"Authorization": "Bearer header-secret", "X-Trace-Id": "trace-1"}, '
            '"params": {"api_key": "param-secret", "page": 1}'
            "}}"
        ),
    )
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["config", "source", "openalex"])

    assert result.exit_code == 0, result.output
    assert "header-secret" not in result.output
    assert "param-secret" not in result.output
    assert "trace-1" in result.output
    assert "***" in result.output


def test_config_proxy_redacts_displayed_urls(monkeypatch):
    """``config proxy`` 展示代理 URL 时应隐藏 userinfo 与敏感 query。"""
    from souwen.config import get_config

    cfg = get_config()
    cfg.proxy = "socks5://user:pass@proxy.example:1080?token=proxy-secret&safe=1"
    cfg.proxy_pool.append("http://user:pass@pool.example:8080?apiKey=pool-secret&safe=1")

    result = runner.invoke(app, ["config", "proxy"])

    assert result.exit_code == 0, result.output
    assert "user:pass" not in result.output
    assert "proxy-secret" not in result.output
    assert "pool-secret" not in result.output
    assert "socks5://***@proxy.example:1080?token=***&safe=1" in result.output
    assert "http://***@pool.example:8080?apiKey=***&safe=1" in result.output


def test_config_proxy_remove_pool_trims_url(monkeypatch, tmp_path):
    """``config proxy --remove-pool`` 应先 trim URL，再从代理池移除。"""
    monkeypatch.chdir(tmp_path)
    from souwen.config import get_config, reload_config

    reload_config()
    cfg = get_config()
    cfg.proxy_pool.append("http://pool.example:8080")

    result = runner.invoke(
        app,
        ["config", "proxy", "--remove-pool", " http://pool.example:8080 "],
    )

    assert result.exit_code == 0, result.output
    assert cfg.proxy_pool == []
    assert "代理池: 空" in result.output


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--add-pool", "   "], "add_pool 不能是空字符串"),
        (["--remove-pool", "   "], "remove_pool 不能是空字符串"),
    ],
)
def test_config_proxy_rejects_blank_pool_args(monkeypatch, tmp_path, args, message):
    """``config proxy`` 的代理池 URL 参数 strip 后为空时应失败。"""
    monkeypatch.chdir(tmp_path)
    from souwen.config import get_config, reload_config

    reload_config()
    result = runner.invoke(app, ["config", "proxy", *args])

    assert result.exit_code == 1
    assert message in result.output
    assert get_config().proxy_pool == []


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


def test_search_patent_uses_registry_defaults_when_sources_omitted(monkeypatch):
    """专利搜索省略 ``--sources`` 时，也应透传 ``None`` 给 registry 默认源。"""
    import sys

    search_module = sys.modules["souwen.search"]
    captured = {}

    async def fake_search(query, sources=None, per_page=10, **kwargs):
        captured["query"] = query
        captured["sources"] = sources
        captured["per_page"] = per_page
        return []

    monkeypatch.setattr(search_module, "search_patents", fake_search)
    result = runner.invoke(app, ["search", "patent", "test", "--json"])
    assert result.exit_code == 0
    assert captured == {"query": "test", "sources": None, "per_page": 5}


def test_search_web_uses_registry_defaults_when_engines_omitted(monkeypatch):
    """网页搜索省略 ``--engines`` 时，应透传 ``None`` 给 registry 默认源。"""
    from souwen.web import search as web_search_mod

    captured = {}

    async def fake_web_search(query, engines=None, max_results_per_engine=10, **kwargs):
        captured["query"] = query
        captured["engines"] = engines
        captured["max_results_per_engine"] = max_results_per_engine
        return web_search_mod.WebSearchResponse(query=query, source="duckduckgo", results=[])

    monkeypatch.setattr(web_search_mod, "web_search", fake_web_search)
    result = runner.invoke(app, ["search", "web", "test", "--json"])
    assert result.exit_code == 0
    assert captured == {"query": "test", "engines": None, "max_results_per_engine": 10}


def test_search_web_preserves_explicit_empty_engines(monkeypatch):
    """网页搜索显式传空 ``--engines`` 时，应透传空列表而不是回退默认源。"""
    from souwen.web import search as web_search_mod

    captured = {}

    async def fake_web_search(query, engines=None, max_results_per_engine=10, **kwargs):
        captured["query"] = query
        captured["engines"] = engines
        captured["max_results_per_engine"] = max_results_per_engine
        return web_search_mod.WebSearchResponse(query=query, source="duckduckgo", results=[])

    monkeypatch.setattr(web_search_mod, "web_search", fake_web_search)
    result = runner.invoke(app, ["search", "web", "test", "--engines", "", "--json"])
    assert result.exit_code == 0
    assert captured == {"query": "test", "engines": [], "max_results_per_engine": 10}


def test_search_paper_reports_basic_disallowed_source(monkeypatch):
    """CLI 搜索显式请求当前 edition 不允许的 source 时应清晰失败。"""
    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["search", "paper", "test", "--sources", "openalex"])

    assert result.exit_code == 1
    assert "source 'openalex' requires edition=pro" in result.output


def test_search_web_reports_basic_disallowed_engine(monkeypatch):
    """CLI web 搜索显式请求当前 edition 不允许的 engine 时应清晰失败。"""
    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["search", "web", "test", "--engines", "tavily"])

    assert result.exit_code == 1
    assert "source 'tavily' requires edition=pro" in result.output


def test_plugins_new_scaffolds_project(monkeypatch, tmp_path: Path):
    """``plugins new`` creates a complete plugin project skeleton."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["plugins", "new", "demo_plugin"])

    assert result.exit_code == 0
    assert "python -m pip install -e '.[dev]'" in result.output
    root = tmp_path / "demo_plugin"
    expected_files = [
        "pyproject.toml",
        "souwen-plugin.json",
        "demo_plugin/__init__.py",
        "demo_plugin/client.py",
        "demo_plugin/handler.py",
        "tests/test_demo_plugin.py",
        "README.md",
    ]
    for rel_path in expected_files:
        assert (root / rel_path).is_file()

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    manifest = (root / "souwen-plugin.json").read_text(encoding="utf-8")
    init_py = (root / "demo_plugin/__init__.py").read_text(encoding="utf-8")
    client_py = (root / "demo_plugin/client.py").read_text(encoding="utf-8")
    handler_py = (root / "demo_plugin/handler.py").read_text(encoding="utf-8")
    test_py = (root / "tests/test_demo_plugin.py").read_text(encoding="utf-8")
    assert '[project.entry-points."souwen.plugins"]' in pyproject
    assert 'demo_plugin = "demo_plugin:plugin"' in pyproject
    assert '"entry_point": "demo_plugin:plugin"' in manifest
    assert '"methods": ["fetch"]' in manifest
    assert "Plugin(" in init_py
    assert "SourceAdapter(" in init_py
    assert "TODO" not in "\n".join([manifest, init_py, client_py, handler_py, test_py])
    assert "__aenter__" in client_py
    assert "scaffold handler executed successfully" in client_py
    assert "async with DemoPluginClient() as client" in handler_py
    assert 'raw={"provider": "demo_plugin", "scaffold": True}' in handler_py
    assert "asyncio.run" in test_py
    assert "test_fetch_handler_smoke" in test_py


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


def test_plugins_new_rejects_trailing_underscore(monkeypatch, tmp_path: Path):
    """Plugin scaffold names must generate valid distribution names."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["plugins", "new", "demo_"])

    assert result.exit_code == 1
    assert "字母或数字结尾" in result.output
    assert not (tmp_path / "demo_").exists()


def test_plugins_new_rejects_python_keyword(monkeypatch, tmp_path: Path):
    """Plugin scaffold names must not be Python keywords."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["plugins", "new", "class"])

    assert result.exit_code == 1
    assert "Python 关键字" in result.output
    assert not (tmp_path / "class").exists()


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


def test_plugins_info_trims_name_before_lookup(monkeypatch):
    """``plugins info`` 应先 strip name，再调用插件管理器。"""
    from souwen.plugin_manager import PluginInfo

    seen: dict[str, str] = {}

    def fake_get_plugin_info(name: str) -> PluginInfo:
        seen["name"] = name
        return PluginInfo(name=name, status="loaded", source="entry_point")

    monkeypatch.setattr("souwen.plugin_manager.get_plugin_info", fake_get_plugin_info)

    result = runner.invoke(app, ["plugins", "info", " demo "])

    assert result.exit_code == 0
    assert seen["name"] == "demo"
    assert "demo" in result.output


def test_plugins_enable_disable_trim_name_before_manager(monkeypatch):
    """``plugins enable/disable`` 应先 strip name，再调用插件管理器。"""
    seen: dict[str, str] = {}

    def fake_enable_plugin(name: str) -> dict[str, object]:
        seen["enable"] = name
        return {"success": True, "message": "enabled", "restart_required": False}

    async def fake_disable_plugin_async(name: str) -> dict[str, object]:
        seen["disable"] = name
        return {"success": True, "message": "disabled", "restart_required": False}

    monkeypatch.setattr("souwen.plugin_manager.enable_plugin", fake_enable_plugin)
    monkeypatch.setattr("souwen.plugin_manager.disable_plugin_async", fake_disable_plugin_async)

    enable_result = runner.invoke(app, ["plugins", "enable", " demo "])
    disable_result = runner.invoke(app, ["plugins", "disable", " demo "])

    assert enable_result.exit_code == 0
    assert disable_result.exit_code == 0
    assert seen == {"enable": "demo", "disable": "demo"}


def test_plugins_health_trims_name_before_lookup(monkeypatch):
    """``plugins health`` 应先 strip name，再调用 health helper。"""
    from souwen.cli import plugins as cli_plugins

    seen: dict[str, object] = {}

    async def fake_run_plugin_health(
        name: str,
        *,
        timeout: float | None = None,
        include_error_detail: bool = True,
    ) -> dict[str, str]:
        seen["name"] = name
        seen["timeout"] = timeout
        seen["include_error_detail"] = include_error_detail
        return {"status": "ok"}

    monkeypatch.setattr(cli_plugins, "run_plugin_health", fake_run_plugin_health)

    result = runner.invoke(app, ["plugins", "health", " demo "])

    assert result.exit_code == 0
    assert seen["name"] == "demo"
    assert seen["include_error_detail"] is False
    assert "demo 健康" in result.output


def test_plugins_health_redacts_secret_payload(monkeypatch):
    """``plugins health`` 输出插件 payload 时也应按字段名和文本内容脱敏。"""
    from souwen.cli import plugins as cli_plugins

    async def fake_run_plugin_health(
        name: str,
        *,
        timeout: float | None = None,
        include_error_detail: bool = True,
    ) -> dict[str, object]:
        del name, timeout, include_error_detail
        return {
            "status": "error",
            "api_key": "health-secret",
            "message": (
                "failed token=message-secret Cookie: sid=session-secret "
                "callback https://health.example/cb?apiKey=url-secret&safe=1"
            ),
        }

    monkeypatch.setattr(cli_plugins, "run_plugin_health", fake_run_plugin_health)

    result = runner.invoke(app, ["plugins", "health", "demo"])

    assert result.exit_code == 1
    assert "health-secret" not in result.output
    assert "message-secret" not in result.output
    assert "session-secret" not in result.output
    assert "url-secret" not in result.output
    assert "api_key: ***" in result.output
    assert "token:***" in result.output
    assert "Cookie:***" in result.output
    assert "apiKey=***" in result.output
    assert "safe=1" in result.output


def test_plugins_rejects_blank_name_before_manager(monkeypatch):
    """strip 后为空的插件名应在 CLI 边界失败，不调用管理器。"""
    called = False

    def fake_get_plugin_info(name: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("souwen.plugin_manager.get_plugin_info", fake_get_plugin_info)

    result = runner.invoke(app, ["plugins", "info", "   "])

    assert result.exit_code == 1
    assert called is False
    assert "name 不能是空字符串" in result.output


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


def test_plugins_install_trims_package_and_sanitizes_failure_output(monkeypatch):
    """``plugins install`` 不应打印 raw pip 失败输出里的私密内容。"""
    seen: dict[str, str] = {}

    async def fake_install_plugin(package: str) -> dict[str, object]:
        seen["package"] = package
        return {
            "success": False,
            "output": "Collecting superweb2pdf\nERROR: private index token leaked",
            "restart_required": False,
        }

    monkeypatch.setattr("souwen.plugin_manager.install_plugin", fake_install_plugin)

    result = runner.invoke(app, ["plugins", "install", " superweb2pdf "])

    assert result.exit_code == 1
    assert seen["package"] == "superweb2pdf"
    assert "操作失败，详见服务端日志" in result.output
    assert "private index token leaked" not in result.output
    assert "Collecting superweb2pdf" not in result.output


def test_plugins_uninstall_trims_package_and_sanitizes_failure_output(monkeypatch):
    """``plugins uninstall`` 不应打印 raw pip 失败输出里的私密内容。"""
    seen: dict[str, str] = {}

    async def fake_uninstall_plugin(package: str) -> dict[str, object]:
        seen["package"] = package
        return {
            "success": False,
            "output": "Found existing installation\nERROR: private index token leaked",
            "restart_required": False,
        }

    monkeypatch.setattr("souwen.plugin_manager.uninstall_plugin", fake_uninstall_plugin)

    result = runner.invoke(app, ["plugins", "uninstall", " superweb2pdf "])

    assert result.exit_code == 1
    assert seen["package"] == "superweb2pdf"
    assert "操作失败，详见服务端日志" in result.output
    assert "private index token leaked" not in result.output
    assert "Found existing installation" not in result.output


def test_plugins_install_rejects_blank_package_before_manager(monkeypatch):
    """strip 后为空的 package 应在 CLI 边界失败，不调用安装管理器。"""
    called = False

    async def fake_install_plugin(package: str) -> dict[str, object]:
        nonlocal called
        called = True
        return {"success": True, "output": "", "restart_required": True}

    monkeypatch.setattr("souwen.plugin_manager.install_plugin", fake_install_plugin)

    result = runner.invoke(app, ["plugins", "install", "   "])

    assert result.exit_code == 1
    assert called is False
    assert "package 不能是空字符串" in result.output


def test_plugins_reload_sanitizes_error_output(monkeypatch):
    """``plugins reload`` 不应把插件加载异常原文打印到终端。"""

    def fake_reload_plugins() -> dict[str, object]:
        return {
            "loaded": [],
            "errors": [
                {
                    "source": "entry_points",
                    "name": "broken",
                    "error": "Import failed with private token leaked",
                }
            ],
            "message": "插件重新扫描完成，新增加载 0 个，错误 1 个。",
        }

    monkeypatch.setattr("souwen.plugin_manager.reload_plugins", fake_reload_plugins)

    result = runner.invoke(app, ["plugins", "reload"])

    assert result.exit_code == 1
    assert "broken" in result.output
    assert "插件加载失败，请查看日志" in result.output
    assert "private token leaked" not in result.output
    assert "Import failed" not in result.output
