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

import json

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


def test_catalog_commands_are_registered_and_status_is_machine_readable(monkeypatch, tmp_path):
    db_path = tmp_path / "catalog.sqlite3"
    monkeypatch.setenv("SOUWEN_LOCAL_CATALOG_PATH", str(db_path))
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["catalog", "status", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["initialized"] is False
    assert payload["path"] == str(db_path)
    assert payload["latest_imports"] == {}


def test_catalog_import_accepts_local_rdf_and_rejects_invalid_source(monkeypatch, tmp_path):
    db_path = tmp_path / "catalog.sqlite3"
    rdf_path = tmp_path / "pg11.rdf"
    rdf_path.write_text(
        """<?xml version=\"1.0\"?>
<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:pgterms=\"http://www.gutenberg.org/2009/pgterms/\">
  <pgterms:ebook rdf:about=\"ebooks/11\"><dcterms:title>Alice</dcterms:title></pgterms:ebook>
</rdf:RDF>""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SOUWEN_LOCAL_CATALOG_PATH", str(db_path))
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["catalog", "import", "gutenberg", str(rdf_path), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["inserted"] == 1
    invalid = runner.invoke(app, ["catalog", "import", "unknown", str(rdf_path)])
    assert invalid.exit_code != 0
    assert "仅支持 gutenberg" in invalid.output


def test_catalog_import_accepts_taiwan_new_books_csv(monkeypatch, tmp_path):
    db_path = tmp_path / "catalog.sqlite3"
    csv_path = tmp_path / "new-books.csv"
    csv_path.write_text(
        "申請書名,作者,出版機構,ISBN\n測試新書,王小明,測試出版社,978-986-12345-6-7\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SOUWEN_LOCAL_CATALOG_PATH", str(db_path))
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["catalog", "import", "taiwan_new_books", str(csv_path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source"] == "taiwan_new_books"
    assert payload["inserted"] == 1


def test_explicit_gutenberg_search_reports_recovery_without_path(monkeypatch, tmp_path):
    import sys

    from souwen.core.exceptions import LocalCatalogUnavailableError

    async def unavailable(*_args, **_kwargs):
        raise LocalCatalogUnavailableError(f"local catalog is not initialized: {tmp_path}")

    monkeypatch.setattr(sys.modules["souwen.search"], "search_books", unavailable)
    result = runner.invoke(app, ["search", "book", "Alice", "--sources", "gutenberg"])
    assert result.exit_code == 1
    assert "souwen catalog import gutenberg <rdf-input>" in result.output
    assert str(tmp_path) not in result.output


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


def test_citation_cli_commands_are_registered_and_json_uses_public_facade(monkeypatch):
    from souwen.models import CitationCountResponse

    async def fake_count(identifier):
        assert identifier == "doi:10.1/x"
        return CitationCountResponse(
            identifier={"scheme": "doi", "value": "10.1/x"},
            count=3,
            source_url="https://example.test",
        )

    monkeypatch.setattr("souwen.citations.get_citation_count", fake_count)
    help_result = runner.invoke(app, ["citation", "--help"])
    result = runner.invoke(app, ["citation", "count", "doi:10.1/x", "--json"])
    assert help_result.exit_code == 0, help_result.output
    for command in ("count", "incoming", "references"):
        command_help = runner.invoke(app, ["citation", command, "--help"])
        assert command_help.exit_code == 0, command_help.output
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["count"] == 3


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


def test_config_show_redacts_llm_search_gateway_base_url_but_keeps_source_base_url(monkeypatch):
    """gateway endpoint 仅在 config view 隐藏，普通 source URL 继续显示。"""
    private_gateway_url = "https://private-gateway.example.com/v1"
    source_base_url = "https://source.example.com/v1"
    monkeypatch.setenv("SOUWEN_SOURCES", json.dumps({"openalex": {"base_url": source_base_url}}))
    monkeypatch.setenv(
        "SOUWEN_LLM_SEARCH_GATEWAYS",
        json.dumps({"uniapi": {"api_key": "gateway-secret", "base_url": private_gateway_url}}),
    )
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0, result.output
    assert "gateway-secret" not in result.output
    assert private_gateway_url not in result.output
    assert "private-gateway.example.com" not in result.output
    assert source_base_url in result.output
    assert "llm_search_gateways" in result.output
    # Rich table wrapping and quote rendering differs on Windows; the security
    # contract is the absence of the private URL while the redaction marker
    # remains visible.
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


def test_invalid_llm_search_gateway_does_not_leak_private_url(monkeypatch):
    private_url = "file:///private/internal/gateway?token=url-secret"
    monkeypatch.setenv(
        "SOUWEN_LLM_SEARCH_GATEWAYS",
        json.dumps({"uniapi": {"api_key": "secret", "base_url": private_url}}),
    )
    from souwen.config import get_config

    get_config.cache_clear()
    result = runner.invoke(app, ["sources", "--json"])

    rendered = f"{result.output}\n{result.exception}"
    assert result.exit_code != 0
    assert private_url not in rendered
    assert "url-secret" not in rendered
    assert "input_value" not in rendered


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
    """``config source`` 应规范化 source/proxy/backend/base_url/timeout。"""
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
            "--timeout",
            "45",
        ],
    )

    assert result.exit_code == 0, result.output
    cfg = get_config()
    sc = cfg.sources["openalex"]
    assert sc.proxy == "warp"
    assert sc.http_backend == "httpx"
    assert sc.base_url == "https://api.example.com/v1"
    assert sc.timeout == 45
    assert "Timeout: 45s" in result.output


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


def test_search_book_uses_registry_defaults_when_sources_omitted(monkeypatch):
    """图书搜索省略 ``--sources`` 时，也应透传 ``None`` 给 registry 默认源。"""
    import sys

    search_module = sys.modules["souwen.search"]
    captured = {}

    async def fake_search(query, sources=None, per_page=10, **kwargs):
        captured["query"] = query
        captured["sources"] = sources
        captured["per_page"] = per_page
        return []

    monkeypatch.setattr(search_module, "search_books", fake_search)
    result = runner.invoke(app, ["search", "book", "test", "--json"])
    assert result.exit_code == 0
    assert captured == {"query": "test", "sources": None, "per_page": 5}


def test_search_research_output_uses_registry_defaults_when_sources_omitted(monkeypatch):
    """科研产出搜索省略 ``--sources`` 时，应透传 ``None`` 给 registry 默认源。"""
    import sys

    search_module = sys.modules["souwen.search"]
    captured = {}

    async def fake_search(query, sources=None, per_page=10, **kwargs):
        captured["query"] = query
        captured["sources"] = sources
        captured["per_page"] = per_page
        return []

    monkeypatch.setattr(search_module, "search_research_outputs", fake_search)
    result = runner.invoke(app, ["search", "research-output", "test", "--json"])
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
