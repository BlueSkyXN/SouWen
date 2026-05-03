from scripts import hf_space_smoke as smoke
from souwen.registry import all_adapters, fetch_providers


def test_normalize_base_url_adds_scheme_and_trims_slash():
    assert smoke.normalize_base_url("blueskyxn-souwen.hf.space/") == (
        "https://blueskyxn-souwen.hf.space"
    )


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
    assert "`basic/health`" in report
    assert "`curl_cffi+warp-on`" in report


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

    adapters = all_adapters().values()
    search_sources = [adapter for adapter in adapters if "search" in adapter.capabilities]
    zero_key_search = {adapter.name for adapter in search_sources if not adapter.resolved_needs_config}
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

    providers = fetch_providers()
    zero_key_fetch = {provider.name for provider in providers if not provider.resolved_needs_config}
    required_fetch = {provider.name for provider in providers if provider.resolved_needs_config}

    assert zero_key_fetch <= tested | skipped
    assert required_fetch == required_key


def test_non_search_zero_key_capabilities_are_tested_or_explicitly_excluded():
    covered_routes = {"duckduckgo_images", "duckduckgo_videos", "wayback"}
    covered_fetch = {item["provider"] for item in smoke.ZERO_KEY_FETCH_PROVIDER_TESTS}
    skipped_fetch = {item["provider"] for item in smoke.ZERO_KEY_FETCH_SKIPPED}
    no_public_endpoint = set(smoke.EXCLUDED_NO_PUBLIC_ENDPOINT_SOURCES)

    non_search = {
        adapter.name
        for adapter in all_adapters().values()
        if "search" not in adapter.capabilities and not adapter.resolved_needs_config
    }

    assert non_search <= covered_routes | covered_fetch | skipped_fetch | no_public_endpoint


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
