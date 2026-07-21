import json
from types import SimpleNamespace

import pytest

from scripts import hf_space_smoke as smoke
from souwen.editions import fetch_provider_min_edition as registry_fetch_provider_min_edition
from souwen.registry import all_adapters, fetch_providers


class FakeSmokeClient:
    def __init__(self):
        self.json_routes = {
            "/health": smoke.ResponseData(
                200,
                {"status": "ok", "version": "1.2.3"},
                0.1,
            ),
            "/readiness": smoke.ResponseData(
                200,
                {"ready": True, "version": "1.2.3", "error": None},
                0.1,
            ),
            "/openapi.json": smoke.ResponseData(
                200,
                {"info": {"title": "SouWen API", "version": "1.2.3"}},
                0.1,
            ),
            "/api/v1/whoami": smoke.ResponseData(200, {"role": "admin"}, 0.1),
        }
        self.text_routes = {
            "/docs": smoke.TextResponseData(
                200,
                "<html><title>Swagger UI</title></html>",
                {"content-type": "text/html; charset=utf-8"},
                0.1,
            ),
            "/panel": smoke.TextResponseData(
                200,
                '<html><body><div id="root"></div></body></html>',
                {"content-type": "text/html; charset=utf-8"},
                0.1,
            ),
        }

    def get(self, path, **_kwargs):
        return self.json_routes[path]

    def get_text(self, path, **_kwargs):
        return self.text_routes[path]


def test_normalize_base_url_adds_scheme_and_trims_slash():
    assert smoke.normalize_base_url("blueskyxn-souwen.hf.space/") == (
        "https://blueskyxn-souwen.hf.space"
    )


def test_normalize_expected_source_sha_requires_full_hex_sha():
    assert smoke.normalize_expected_source_sha("A" * 40) == "a" * 40
    assert smoke.normalize_expected_source_sha(None) is None

    with pytest.raises(ValueError, match="40 hexadecimal"):
        smoke.normalize_expected_source_sha("main")


def test_private_space_uses_separate_outer_and_application_auth_headers(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200
        headers = SimpleNamespace(items=lambda: [])

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, *, timeout):
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)
    client = smoke.ApiClient(
        smoke.SmokeConfig(
            base_url="https://private-space.example",
            expected_version="2.0.0rc1",
            request_timeout=3,
            bearer_token="souwen-admin-token",
            hf_space_token="hf-read-token",
        )
    )

    status, _raw, _headers, _elapsed = client._request_raw("GET", "/api/v1/whoami", auth=True)

    assert status == 200
    assert captured["headers"]["authorization"] == "Bearer hf-read-token"
    assert captured["headers"]["x-souwen-token"] == "souwen-admin-token"
    assert captured["timeout"] == 3


def test_required_failures_only_counts_required_failed_rows():
    results = [
        smoke.ProbeResult("basic", "health", "pass", "ok", required=True),
        smoke.ProbeResult("web", "bing", "warn", "flaky", required=False),
        smoke.ProbeResult("paper", "default", "fail", "too few", required=True),
        smoke.ProbeResult("media", "images", "fail", "upstream", required=False),
    ]

    failures = smoke.required_failures(results)

    assert [item.name for item in failures] == ["default"]


def test_build_markdown_report_includes_gate_summary():
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
    )
    results = [
        smoke.ProbeResult("basic", "health", "pass", "ok", required=True),
        smoke.ProbeResult("zero-key-web", "curl_cffi+warp-on", "warn", "0/10"),
    ]

    report = smoke.build_markdown_report(config, results)

    assert "# SouWen HF Space CD Test Report" in report
    assert "Result: **passed**" in report
    assert "Overall outcome: **WARN**" in report
    assert "`basic/health`" in report
    assert "`curl_cffi+warp-on`" in report


def test_build_json_payload_uses_functional_schema():
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
        mode="capability",
    )
    results = [
        smoke.ProbeResult("basic", "health", "pass", "ok", required=True, elapsed=0.1),
        smoke.ProbeResult("web", "bing", "warn", "flaky"),
        smoke.ProbeResult("media", "images", "fail", "upstream", required=False),
        smoke.ProbeResult("fetch", "mcp", "skip", "missing runtime"),
    ]

    payload = smoke.build_json_payload(config, results)

    assert payload["schema_version"] == 1
    assert payload["script"] == "hf_space_smoke"
    assert payload["mode"] == "capability"
    assert payload["overall"] == "WARN"
    by_name = {item["name"]: item for item in payload["checks"]}
    assert by_name["basic/health"]["outcome"] == "PASS"
    assert by_name["web/bing"]["outcome"] == "WARN"
    assert by_name["media/images"]["outcome"] == "WARN"
    assert by_name["media/images"]["details"]["legacy_outcome"] == "fail"
    assert by_name["fetch/mcp"]["outcome"] == "SKIP"


def test_offline_mode_writes_skip_reports_without_live_calls(monkeypatch, tmp_path):
    def fail_if_called(_config):
        raise AssertionError("offline mode must not run live probes")

    json_report = tmp_path / "hf-space.json"
    markdown_report = tmp_path / "hf-space.md"
    monkeypatch.setattr(smoke, "run_report", fail_if_called)

    code = smoke.main(
        [
            "--mode",
            "offline",
            "--base-url",
            "https://example.test",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
            "--summary-file",
            "",
        ]
    )

    assert code == 0
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["mode"] == "offline"
    assert payload["overall"] == "SKIP"
    assert payload["checks"][0]["name"] == "mode/offline"
    assert payload["checks"][0]["outcome"] == "SKIP"
    assert "Overall outcome: **SKIP**" in markdown_report.read_text(encoding="utf-8")


def test_offline_mode_default_does_not_write_repo_root_reports(monkeypatch, tmp_path):
    """本地直接运行 smoke 不应默认在当前目录生成 report 文件。"""

    def fail_if_called(_config):
        raise AssertionError("offline mode must not run live probes")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("SOUWEN_SMOKE_REPORT_FILE", raising=False)
    monkeypatch.delenv("SOUWEN_SMOKE_JSON_FILE", raising=False)
    monkeypatch.setattr(smoke, "run_report", fail_if_called)

    code = smoke.main(["--mode", "offline", "--base-url", "https://example.test"])

    assert code == 0
    assert not (tmp_path / "hf-space-cd-report.md").exists()
    assert not (tmp_path / "hf-space-cd-report.json").exists()


def test_report_write_failure_returns_argument_error_code(monkeypatch, tmp_path, capsys):
    def fail_if_called(_config):
        raise AssertionError("offline mode must not run live probes")

    def fail_write_text(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(smoke, "run_report", fail_if_called)
    monkeypatch.setattr(smoke, "write_text", fail_write_text)

    code = smoke.main(
        [
            "--mode",
            "offline",
            "--base-url",
            "https://example.test",
            "--json-report",
            str(tmp_path / "hf-space.json"),
            "--markdown-report",
            str(tmp_path / "hf-space.md"),
            "--summary-file",
            "",
        ]
    )

    assert code == 2
    assert "failed to write HF Space smoke reports: disk full" in capsys.readouterr().err


def test_fail_admin_open_can_be_enabled_by_env(monkeypatch):
    monkeypatch.setenv("SOUWEN_SMOKE_FAIL_ADMIN_OPEN", "1")
    monkeypatch.delenv("SOUWEN_SMOKE_WARN_ADMIN_OPEN", raising=False)

    args = smoke.parse_args([])

    assert args.fail_admin_open is True


def test_public_base_url_defaults_admin_open_gate_to_fail(monkeypatch):
    monkeypatch.delenv("SOUWEN_SMOKE_FAIL_ADMIN_OPEN", raising=False)
    monkeypatch.delenv("SOUWEN_SMOKE_WARN_ADMIN_OPEN", raising=False)

    args = smoke.parse_args(["--base-url", "https://example.test"])
    base_url = smoke.normalize_base_url(args.base_url)

    assert args.fail_admin_open is None
    assert smoke.resolve_fail_admin_open(base_url, args.fail_admin_open) is True


def test_local_base_url_defaults_admin_open_gate_to_warn(monkeypatch):
    monkeypatch.delenv("SOUWEN_SMOKE_FAIL_ADMIN_OPEN", raising=False)
    monkeypatch.delenv("SOUWEN_SMOKE_WARN_ADMIN_OPEN", raising=False)

    args = smoke.parse_args(["--base-url", "http://127.0.0.1:8000"])
    base_url = smoke.normalize_base_url(args.base_url)

    assert args.fail_admin_open is None
    assert smoke.resolve_fail_admin_open(base_url, args.fail_admin_open) is False


def test_warn_admin_open_can_be_enabled_by_env(monkeypatch):
    monkeypatch.delenv("SOUWEN_SMOKE_FAIL_ADMIN_OPEN", raising=False)
    monkeypatch.setenv("SOUWEN_SMOKE_WARN_ADMIN_OPEN", "1")

    args = smoke.parse_args([])

    assert args.fail_admin_open is False


def test_warn_admin_open_cli_overrides_fail_env(monkeypatch):
    monkeypatch.setenv("SOUWEN_SMOKE_FAIL_ADMIN_OPEN", "1")

    args = smoke.parse_args(["--warn-admin-open"])

    assert args.fail_admin_open is False


def test_basic_checks_cover_docs_and_panel_routes():
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
    )
    state = smoke.RunState()

    results = smoke.run_basic_checks(FakeSmokeClient(), config, state)  # type: ignore[arg-type]

    by_name = {item.name: item for item in results}
    assert by_name["openapi"].outcome == "pass"
    assert by_name["docs"].outcome == "pass"
    assert by_name["panel"].outcome == "pass"
    assert by_name["whoami"].outcome == "pass"
    assert state.admin_available is True


def test_basic_checks_require_exact_source_sha_when_pinned():
    client = FakeSmokeClient()
    client.json_routes["/health"] = smoke.ResponseData(
        200,
        {"status": "ok", "version": "1.2.3", "source_sha": "a" * 40},
        0.1,
    )
    client.json_routes["/readiness"] = smoke.ResponseData(
        200,
        {"ready": True, "version": "1.2.3", "source_sha": "b" * 40, "error": None},
        0.1,
    )
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        expected_source_sha="a" * 40,
        request_timeout=1,
    )

    results = smoke.run_basic_checks(client, config, smoke.RunState())  # type: ignore[arg-type]
    by_name = {item.name: item for item in results}

    assert by_name["health"].outcome == "pass"
    assert by_name["readiness"].outcome == "fail"
    assert "expected=" in by_name["readiness"].detail


def test_basic_checks_warn_when_public_admin_open_without_password():
    client = FakeSmokeClient()
    client.json_routes["/api/v1/whoami"] = smoke.ResponseData(
        200,
        {"role": "admin", "admin_open": True, "admin_password_set": False},
        0.1,
    )
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
    )
    state = smoke.RunState()

    results = smoke.run_basic_checks(client, config, state)  # type: ignore[arg-type]
    by_check = {(item.section, item.name): item for item in results}
    payload = smoke.build_json_payload(config, results)
    report = smoke.build_markdown_report(config, results)

    whoami = by_check[("basic", "whoami")]
    security = by_check[("security", "admin-open")]
    assert whoami.meta["admin_access_mode"] == "open"
    assert security.outcome == "warn"
    assert security.required is False
    assert "remote admin endpoints are open" in security.detail
    assert payload["overall"] == "WARN"
    assert payload["checks"][-1]["name"] == "security/admin-open"
    assert payload["checks"][-1]["details"]["meta"]["admin_open"] is True
    assert "- Admin access: `open`" in report
    assert "## security" in report
    assert "`admin-open`" in report
    assert state.admin_open is True
    assert state.admin_password_set is False


def test_basic_checks_fail_when_public_admin_open_gate_is_required():
    client = FakeSmokeClient()
    client.json_routes["/api/v1/whoami"] = smoke.ResponseData(
        200,
        {"role": "admin", "admin_open": True, "admin_password_set": False},
        0.1,
    )
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
        fail_admin_open=True,
    )
    state = smoke.RunState()

    results = smoke.run_basic_checks(client, config, state)  # type: ignore[arg-type]
    by_check = {(item.section, item.name): item for item in results}
    payload = smoke.build_json_payload(config, results)
    report = smoke.build_markdown_report(config, results)

    security = by_check[("security", "admin-open")]
    assert security.outcome == "fail"
    assert security.required is True
    assert smoke.required_failures(results) == [security]
    assert payload["overall"] == "FAIL"
    assert payload["checks"][-1]["outcome"] == "FAIL"
    assert payload["environment"]["fail_admin_open"] is True
    assert "- Public admin-open gate: `fail`" in report


def test_basic_checks_allow_local_admin_open_without_warning():
    client = FakeSmokeClient()
    client.json_routes["/api/v1/whoami"] = smoke.ResponseData(
        200,
        {"role": "admin", "admin_open": True, "admin_password_set": False},
        0.1,
    )
    config = smoke.SmokeConfig(
        base_url="http://127.0.0.1:49265",
        expected_version="1.2.3",
        request_timeout=1,
    )
    state = smoke.RunState()

    results = smoke.run_basic_checks(client, config, state)  # type: ignore[arg-type]
    by_check = {(item.section, item.name): item for item in results}

    assert by_check[("security", "admin-open")].outcome == "pass"
    assert "local/CI base URL" in by_check[("security", "admin-open")].detail
    assert smoke.overall_outcome(results) == smoke.Outcome.PASS


def test_surface_only_report_skips_mutating_matrix_and_restore(monkeypatch):
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
        surface_only=True,
    )
    monkeypatch.setattr(smoke, "ApiClient", lambda _config: FakeSmokeClient())
    monkeypatch.setattr(
        smoke,
        "run_admin_checks",
        lambda _client, _config, state: [
            smoke.ProbeResult("admin", "ping", "pass", "ok", required=True)
        ],
    )

    results = smoke.run_report(config)
    report = smoke.build_markdown_report(config, results)

    assert all(item.section != "matrix" for item in results)
    assert all(item.section != "restore" for item in results)
    assert "- HTTP backend mutation matrix: `skipped (surface-only)`" in report
    assert "- Direct zero-key routes: `skipped (surface-only)`" in report
    assert "- HTTP backend matrix: `auto,httpx,curl_cffi`" not in report


def test_build_markdown_report_includes_source_matrix():
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
    )
    results = [
        smoke.ProbeResult(
            "zero-key-web-source",
            "duckduckgo+curl_cffi+warp-auto",
            "pass",
            "status=200, total=3, count=3",
            meta={
                "matrix_kind": "web-source",
                "source": "duckduckgo",
                "backend": "curl_cffi",
                "warp": "auto",
                "count": 3,
            },
        )
    ]

    report = smoke.build_markdown_report(config, results)

    assert "## Zero-Key Matrix" in report
    assert "### Web Scraper Sources" in report
    assert "`duckduckgo`" in report
    assert "`curl_cffi`" in report


def test_build_markdown_report_includes_fetch_matrix_and_exclusions():
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
    )
    results = [
        smoke.ProbeResult(
            "zero-key-fetch-source",
            "builtin+curl_cffi+warp-off",
            "pass",
            "status=200, total_ok=1, total_failed=0",
            meta={
                "matrix_kind": "fetch-source",
                "provider": "builtin",
                "backend": "curl_cffi",
                "warp": "off",
                "total": 1,
                "total_ok": 1,
                "total_failed": 0,
            },
        )
    ]

    report = smoke.build_markdown_report(config, results)

    assert "### Fetch Providers" in report
    assert "`builtin`" in report
    assert "Required-key direct APIs" in report
    assert "### Excluded By Design" in report
    assert "Required-key fetch" in report


def test_fetch_provider_smoke_min_editions_match_registry():
    providers = {provider.name: provider for provider in fetch_providers()}

    for item in smoke.ZERO_KEY_FETCH_PROVIDER_TESTS:
        provider = providers[item["provider"]]
        assert smoke.fetch_provider_min_edition(item) == registry_fetch_provider_min_edition(
            provider
        )


def test_eligible_fetch_provider_tests_respects_edition():
    pro_providers = {item["provider"] for item in smoke.eligible_fetch_provider_tests("pro")}
    full_providers = {item["provider"] for item in smoke.eligible_fetch_provider_tests("full")}
    gated_providers = {item["provider"] for item in smoke.edition_gated_fetch_provider_tests("pro")}

    assert "builtin" in pro_providers
    assert "jina_reader" in pro_providers
    assert "arxiv_fulltext" not in pro_providers
    assert "crawl4ai" not in pro_providers
    assert "arxiv_fulltext" in full_providers
    assert "crawl4ai" in full_providers
    assert gated_providers == {
        "arxiv_fulltext",
        "crawl4ai",
        "newspaper",
        "readability",
    }


def test_build_markdown_report_counts_edition_gated_fetch_skips():
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
        edition="pro",
    )
    results = [
        smoke.ProbeResult(
            "admin",
            "config",
            "pass",
            "status=200, edition='pro'",
            meta={"edition": "pro"},
        ),
        smoke.ProbeResult(
            "zero-key-fetch-source",
            "builtin+curl_cffi+warp-off",
            "pass",
            "status=200, total_ok=1, total_failed=0",
            meta={
                "matrix_kind": "fetch-source",
                "provider": "builtin",
                "backend": "curl_cffi",
                "warp": "off",
                "total": 1,
                "total_ok": 1,
                "total_failed": 0,
            },
        ),
        smoke.edition_skipped_fetch_provider(
            {
                "provider": "crawl4ai",
                "min_edition": "full",
            },
            "pro",
        ),
    ]

    report = smoke.build_markdown_report(config, results)

    assert "- Edition: `pro`" in report
    assert "1 tested, 1 skipped by edition" in report
    assert "requires edition=full; current edition=pro" in report


def test_build_markdown_report_expands_open_sources_and_direct_routes():
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version="1.2.3",
        request_timeout=1,
    )
    results = [
        smoke.ProbeResult(
            "zero-key-open-search",
            "optional-key-and-open-sources",
            "pass",
            "status=200, total=2",
            meta={
                "matrix_kind": "open-search",
                "requested": ["github", "stackoverflow"],
                "counts": {"github": 2, "stackoverflow": 0},
            },
        ),
        smoke.ProbeResult(
            "zero-key-route",
            "sources",
            "pass",
            "status=200, entries=20",
            meta={
                "matrix_kind": "direct-route",
                "route": "/api/v1/sources",
                "count": 20,
            },
        ),
    ]

    report = smoke.build_markdown_report(config, results)

    assert "### Open / Optional-Key Platform Sources" in report
    assert "`github`" in report
    assert "`stackoverflow`" in report
    assert "### Direct API Routes" in report
    assert "`/api/v1/sources`" in report


def test_zero_key_search_sources_are_covered_or_explicitly_excluded():
    covered = {
        *smoke.DEFAULT_PAPER_SOURCES,
        *smoke.EXTRA_ZERO_KEY_PAPER_SOURCES,
        *smoke.ZERO_KEY_PATENT_SOURCES,
        *smoke.ZERO_KEY_WEB_SCRAPERS,
        *smoke.ZERO_KEY_OPEN_SEARCH_SOURCES,
    }
    no_public_endpoint = set(smoke.EXCLUDED_NO_PUBLIC_ENDPOINT_SOURCES)
    required_key = set(smoke.EXCLUDED_REQUIRED_KEY_SEARCH_SOURCES)
    self_hosted = set(smoke.EXCLUDED_SELF_HOSTED_SEARCH_SOURCES)

    adapters = [
        adapter for adapter in all_adapters().values() if "external_plugin" not in adapter.tags
    ]
    search_sources = [adapter for adapter in adapters if "search" in adapter.capabilities]
    zero_key_search = {
        adapter.name for adapter in search_sources if not adapter.resolved_needs_config
    }
    required_search = {
        adapter.name
        for adapter in search_sources
        if adapter.resolved_needs_config and adapter.integration != "self_hosted"
    }
    self_hosted_search = {
        adapter.name
        for adapter in search_sources
        if adapter.resolved_needs_config and adapter.integration == "self_hosted"
    }

    assert zero_key_search <= covered | no_public_endpoint
    assert required_search <= required_key
    assert self_hosted_search == self_hosted


def test_zero_key_fetch_providers_are_covered_or_explicitly_excluded():
    tested = {item["provider"] for item in smoke.ZERO_KEY_FETCH_PROVIDER_TESTS}
    skipped = {item["provider"] for item in smoke.ZERO_KEY_FETCH_SKIPPED}
    required_key = set(smoke.EXCLUDED_REQUIRED_KEY_FETCH_PROVIDERS)

    providers = [
        provider for provider in fetch_providers() if "external_plugin" not in provider.tags
    ]
    zero_key_fetch = {provider.name for provider in providers if not provider.resolved_needs_config}
    required_fetch = {provider.name for provider in providers if provider.resolved_needs_config}

    assert zero_key_fetch <= tested | skipped
    assert required_fetch == required_key | {"mcp"}
    assert "mcp" in skipped


def test_non_search_zero_key_capabilities_are_tested_or_explicitly_excluded():
    covered_routes = {"duckduckgo_images", "duckduckgo_videos", "wayback", "opencitations"}
    covered_fetch = {item["provider"] for item in smoke.ZERO_KEY_FETCH_PROVIDER_TESTS}
    skipped_fetch = {item["provider"] for item in smoke.ZERO_KEY_FETCH_SKIPPED}
    no_public_endpoint = set(smoke.EXCLUDED_NO_PUBLIC_ENDPOINT_SOURCES)

    non_search = {
        adapter.name
        for adapter in all_adapters().values()
        if "external_plugin" not in adapter.tags
        and "search" not in adapter.capabilities
        and not adapter.resolved_needs_config
    }

    assert non_search <= covered_routes | covered_fetch | skipped_fetch | no_public_endpoint


def test_zero_key_checks_refuse_mutation_without_safe_snapshots():
    config = smoke.SmokeConfig(
        base_url="https://example.test",
        expected_version=None,
        request_timeout=1,
    )
    state = smoke.RunState(admin_available=True, backend_snapshot_ok=True, warp_snapshot_ok=False)

    results = smoke.run_zero_key_checks(object(), config, state)  # type: ignore[arg-type]

    assert len(results) == 1
    assert results[0].name == "mutation-snapshot"
    assert results[0].outcome == "fail"
    assert results[0].required is True
    assert "mutation matrix skipped" in results[0].detail


def test_restore_state_does_not_mutate_when_snapshots_are_unknown():
    state = smoke.RunState(admin_available=True)

    results = smoke.restore_state(object(), state)  # type: ignore[arg-type]

    assert [(item.name, item.outcome) for item in results] == [
        ("http-backend", "skip"),
        ("warp", "skip"),
    ]


def test_summarize_search_response_handles_missing_meta():
    total, succeeded, failed = smoke.summarize_search_response({"total": 3})

    assert total == 3
    assert succeeded == []
    assert failed == []


def test_grouped_result_counts_counts_per_source():
    counts = smoke.grouped_result_counts(
        {
            "results": [
                {"source": "openalex", "results": [{"title": "a"}, {"title": "b"}]},
                {"source": "dblp", "results": []},
            ]
        }
    )

    assert counts == {"openalex": 2, "dblp": 0}


def test_web_result_counts_counts_per_engine():
    counts = smoke.web_result_counts(
        {
            "results": [
                {"engine": "duckduckgo", "title": "a"},
                {"engine": "duckduckgo", "title": "b"},
                {"engine": "bing", "title": "c"},
            ]
        }
    )

    assert counts == {"duckduckgo": 2, "bing": 1}
