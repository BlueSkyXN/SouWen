"""OpenAPI contract tests for public server endpoints."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")


def _component_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def test_sources_endpoint_exposes_source_catalog_contract() -> None:
    """``/api/v1/sources`` must expose the formal Source Catalog response shape."""
    from souwen.server.app import app

    schema = app.openapi()
    operation = schema["paths"]["/api/v1/sources"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert response_schema["$ref"].endswith("/SourceCatalogResponse")

    components = schema["components"]["schemas"]
    response_component = components[_component_name(response_schema["$ref"])]
    response_props = response_component["properties"]
    assert set(response_props) == {"sources", "categories", "defaults"}
    assert not {"paper", "general", "wiki"} & set(response_props)

    source_ref = response_props["sources"]["items"]["$ref"]
    source_component = components[_component_name(source_ref)]
    source_props = source_component["properties"]
    assert {
        "name",
        "domain",
        "category",
        "capabilities",
        "description",
        "auth_requirement",
        "credential_fields",
        "missing_credential_fields",
        "credentials_satisfied",
        "configured_credentials",
        "config_valid",
        "config_reason",
        "risk_level",
        "stability",
        "distribution",
        "default_for",
        "min_edition",
        "edition_available",
        "edition_reason",
        "runtime_available",
        "runtime_reason",
        "available",
    } <= set(source_props)

    assert "SourcesResponse" not in components


def test_doctor_endpoint_exposes_edition_contract() -> None:
    """``/api/v1/doctor`` response must include the current edition."""
    from souwen.server.app import app

    schema = app.openapi()
    operation = schema["paths"]["/api/v1/doctor"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert response_schema["$ref"].endswith("/DoctorResponse")

    components = schema["components"]["schemas"]
    response_component = components[_component_name(response_schema["$ref"])]
    response_props = response_component["properties"]
    assert "edition" in response_props
    assert set(response_props["edition"]["enum"]) == {"basic", "pro", "full"}
    assert "probe_mode" in response_props
    assert set(response_props["probe_mode"]["enum"]) == {"static", "live"}
    assert "live_probe" in response_props

    source_ref = response_props["sources"]["items"]["$ref"]
    source_component = components[_component_name(source_ref)]
    source_props = source_component["properties"]
    assert {
        "name",
        "category",
        "status",
        "integration_type",
        "required_key",
        "key_requirement",
        "auth_requirement",
        "credential_fields",
        "missing_credential_fields",
        "config_valid",
        "optional_credential_effect",
        "risk_level",
        "risk_reasons",
        "distribution",
        "package_extra",
        "stability",
        "usage_note",
        "min_edition",
        "edition",
        "edition_available",
        "edition_reason",
        "available",
        "message",
        "enabled",
        "description",
        "channel",
        "live_probe",
    } <= set(source_props)
    assert set(source_props["min_edition"]["enum"]) == {"basic", "pro", "full"}
    assert set(source_props["edition"]["enum"]) == {"basic", "pro", "full"}


def test_admin_sources_config_exposes_channel_config_contract() -> None:
    """Admin source config endpoints must expose the Panel channel-config contract."""
    from souwen.server.app import app

    schema = app.openapi()
    components = schema["components"]["schemas"]

    list_operation = schema["paths"]["/api/v1/admin/sources/config"]["get"]
    list_response = list_operation["responses"]["200"]["content"]["application/json"]["schema"]
    source_ref = list_response["additionalProperties"]["$ref"]
    assert source_ref.endswith("/SourceChannelConfigResponse")

    single_operation = schema["paths"]["/api/v1/admin/sources/config/{source_name}"]["get"]
    single_response = single_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert single_response["$ref"].endswith("/SourceChannelConfigResponse")

    component = components[_component_name(source_ref)]
    props = component["properties"]
    assert {
        "enabled",
        "proxy",
        "http_backend",
        "base_url",
        "timeout",
        "has_api_key",
        "configured_credentials",
        "credentials_satisfied",
        "missing_credential_fields",
        "config_valid",
        "config_reason",
        "available",
        "headers",
        "params",
        "category",
        "domain",
        "capabilities",
        "integration_type",
        "min_edition",
        "edition_available",
        "edition_reason",
        "key_requirement",
        "auth_requirement",
        "credential_fields",
        "optional_credential_effect",
        "risk_level",
        "risk_reasons",
        "distribution",
        "package_extra",
        "stability",
        "usage_note",
        "default_enabled",
        "default_for",
        "description",
        "name",
    } <= set(props)
    assert set(props["min_edition"]["enum"]) == {"basic", "pro", "full"}
    assert set(props["integration_type"]["enum"]) == {
        "open_api",
        "scraper",
        "official_api",
        "self_hosted",
    }


def test_whoami_endpoint_exposes_role_and_edition_contract() -> None:
    """``/api/v1/whoami`` must expose the Panel auth/edition contract."""
    from souwen.server.app import app

    schema = app.openapi()
    operation = schema["paths"]["/api/v1/whoami"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/WhoamiResponse")

    components = schema["components"]["schemas"]
    component = components[_component_name(response_schema["$ref"])]
    props = component["properties"]
    assert {
        "role",
        "features",
        "edition",
        "edition_capabilities",
        "guest_enabled",
        "user_password_set",
        "admin_password_set",
        "admin_open",
    } <= set(props)
    assert set(props["role"]["enum"]) == {"guest", "user", "admin"}
    assert set(props["edition"]["enum"]) == {"basic", "pro", "full"}

    capabilities_ref = props["edition_capabilities"]["$ref"]
    capabilities = components[_component_name(capabilities_ref)]["properties"]
    assert {
        "llm",
        "warp_modes",
        "fetch_providers",
        "plugin_preinstalled",
    } <= set(capabilities)


def test_fetch_utility_endpoints_expose_response_contracts() -> None:
    """Fetch utility routes must not publish empty OpenAPI response schemas."""
    from souwen.server.app import app

    schema = app.openapi()
    components = schema["components"]["schemas"]

    fetch_operation = schema["paths"]["/api/v1/fetch"]["post"]
    fetch_response = fetch_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert fetch_response["$ref"].endswith("/FetchResponse")

    links_operation = schema["paths"]["/api/v1/links"]["get"]
    links_response = links_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert links_response["$ref"].endswith("/LinkExtractionResponse")
    links_component = components[_component_name(links_response["$ref"])]
    links_props = links_component["properties"]
    assert {
        "source_url",
        "final_url",
        "links",
        "total",
        "filtered_count",
        "error",
    } <= set(links_props)
    link_item_ref = links_props["links"]["items"]["$ref"]
    link_item_props = components[_component_name(link_item_ref)]["properties"]
    assert {"url", "text"} <= set(link_item_props)

    sitemap_operation = schema["paths"]["/api/v1/sitemap"]["get"]
    sitemap_response = sitemap_operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert sitemap_response["$ref"].endswith("/SitemapResponse")
    sitemap_component = components[_component_name(sitemap_response["$ref"])]
    sitemap_props = sitemap_component["properties"]
    assert {
        "root_url",
        "entries",
        "total",
        "sitemaps_parsed",
        "errors",
    } <= set(sitemap_props)
    sitemap_entry_ref = sitemap_props["entries"]["items"]["$ref"]
    sitemap_entry_props = components[_component_name(sitemap_entry_ref)]["properties"]
    assert {"loc", "lastmod", "changefreq", "priority"} <= set(sitemap_entry_props)


def test_enriched_web_search_exposes_typed_additive_contract() -> None:
    """The enriched endpoint must stay model-bound and never accept provider credentials."""
    from souwen.server.app import app

    schema = app.openapi()
    components = schema["components"]["schemas"]
    operation = schema["paths"]["/api/v1/search/web/enriched"]["post"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]

    request = components[_component_name(request_ref)]
    response = components[_component_name(response_ref)]
    assert request_ref.endswith("/EnrichedWebSearchRequest")
    assert response_ref.endswith("/EnrichedWebSearchResponse")
    assert {
        "query",
        "sources",
        "source_strategy",
        "max_results_per_source",
        "fetch",
        "budget",
    } <= set(request["properties"])
    assert {"model", "model_id", "scheme_id", "api_key", "base_url"}.isdisjoint(
        request["properties"]
    )
    assert request["additionalProperties"] is False
    assert {"query", "results", "answer", "meta", "usage"} <= set(response["properties"])


def test_bilibili_endpoints_expose_response_contracts() -> None:
    """Bilibili direct routes must expose Panel-compatible response schemas."""
    from souwen.server.app import app

    schema = app.openapi()
    components = schema["components"]["schemas"]

    search_response = schema["paths"]["/api/v1/bilibili/search"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert search_response["$ref"].endswith("/BilibiliSearchResponse")
    search_props = components[_component_name(search_response["$ref"])]["properties"]
    assert {"keyword", "results", "total", "page", "page_size", "order"} <= set(search_props)
    item_ref = search_props["results"]["items"]["$ref"]
    item_props = components[_component_name(item_ref)]["properties"]
    assert {"bvid", "title", "author", "play", "danmaku", "duration", "pic"} <= set(item_props)

    video_response = schema["paths"]["/api/v1/bilibili/video/{bvid}"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert video_response["$ref"].endswith("/BilibiliVideoDetailResponse")
    video_props = components[_component_name(video_response["$ref"])]["properties"]
    assert {"bvid", "data"} <= set(video_props)

    users_response = schema["paths"]["/api/v1/bilibili/search/users"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert users_response["$ref"].endswith("/BilibiliUserSearchResponse")
    users_props = components[_component_name(users_response["$ref"])]["properties"]
    assert {"keyword", "results", "total", "page"} <= set(users_props)

    articles_response = schema["paths"]["/api/v1/bilibili/search/articles"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert articles_response["$ref"].endswith("/BilibiliArticleSearchResponse")
    articles_props = components[_component_name(articles_response["$ref"])]["properties"]
    assert {"keyword", "results", "total", "page"} <= set(articles_props)


def test_admin_warp_endpoints_expose_response_contracts() -> None:
    """Admin WARP routes must publish typed JSON schemas, and events must be SSE."""
    from souwen.server.app import app

    schema = app.openapi()
    components = schema["components"]["schemas"]

    expected_refs = {
        ("get", "/api/v1/admin/warp"): "WarpStatusResponse",
        ("get", "/api/v1/admin/warp/modes"): "WarpModesResponse",
        ("post", "/api/v1/admin/warp/enable"): "WarpActionResponse",
        ("post", "/api/v1/admin/warp/register"): "WarpActionResponse",
        ("post", "/api/v1/admin/warp/test"): "WarpTestResponse",
        ("get", "/api/v1/admin/warp/config"): "WarpConfigResponse",
        ("post", "/api/v1/admin/warp/disable"): "WarpActionResponse",
        ("get", "/api/v1/admin/warp/components"): "WarpComponentsResponse",
        ("post", "/api/v1/admin/warp/components/install"): "WarpComponentInstallResponse",
        ("post", "/api/v1/admin/warp/components/uninstall"): "WarpActionResponse",
        ("post", "/api/v1/admin/warp/switch"): "WarpActionResponse",
    }
    for (method, path), component_name in expected_refs.items():
        response_schema = schema["paths"][path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"].endswith(f"/{component_name}")

    status_props = components["WarpStatusResponse"]["properties"]
    assert {
        "status",
        "mode",
        "owner",
        "socks_port",
        "http_port",
        "ip",
        "pid",
        "interface",
        "last_error",
        "protocol",
        "proxy_type",
        "available_modes",
    } <= set(status_props)
    assert set(status_props["status"]["enum"]) == {
        "disabled",
        "starting",
        "enabled",
        "stopping",
        "error",
    }

    mode_ref = components["WarpModesResponse"]["properties"]["modes"]["items"]["$ref"]
    mode_props = components[_component_name(mode_ref)]["properties"]
    assert {
        "id",
        "name",
        "protocol",
        "installed",
        "requires_privilege",
        "docker_only",
        "proxy_types",
        "description",
        "min_edition",
        "edition_available",
        "edition_reason",
    } <= set(mode_props)

    config_props = components["WarpConfigResponse"]["properties"]
    assert {
        "warp_enabled",
        "warp_mode",
        "warp_socks_port",
        "warp_http_port",
        "warp_external_proxy",
        "has_license_key",
        "has_team_token",
        "has_proxy_auth",
    } <= set(config_props)

    events_content = schema["paths"]["/api/v1/admin/warp/events"]["get"]["responses"]["200"][
        "content"
    ]
    assert "text/event-stream" in events_content
    assert "application/json" not in events_content


def test_admin_plugin_endpoints_expose_response_contracts() -> None:
    """Admin plugin routes must expose typed schemas without raw pip/error details."""
    from souwen.server.app import app

    schema = app.openapi()
    components = schema["components"]["schemas"]

    expected_refs = {
        ("get", "/api/v1/admin/plugins"): "PluginListResponse",
        ("get", "/api/v1/admin/plugins/{name}"): "PluginInfoResponse",
        ("get", "/api/v1/admin/plugins/{name}/health"): "PluginHealthResponse",
        ("post", "/api/v1/admin/plugins/{name}/enable"): "PluginActionResponse",
        ("post", "/api/v1/admin/plugins/{name}/disable"): "PluginActionResponse",
        ("post", "/api/v1/admin/plugins/install"): "PluginPackageActionResponse",
        ("post", "/api/v1/admin/plugins/uninstall"): "PluginPackageActionResponse",
        ("post", "/api/v1/admin/plugins/reload"): "PluginReloadResponse",
    }
    for (method, path), component_name in expected_refs.items():
        response_schema = schema["paths"][path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"].endswith(f"/{component_name}")

    info_props = components["PluginInfoResponse"]["properties"]
    assert {
        "name",
        "package",
        "version",
        "status",
        "source",
        "first_party",
        "description",
        "error",
        "source_adapters",
        "fetch_handlers",
        "restart_required",
    } <= set(info_props)

    list_props = components["PluginListResponse"]["properties"]
    assert {"plugins", "restart_required", "install_enabled"} <= set(list_props)
    assert list_props["plugins"]["items"]["$ref"].endswith("/PluginInfoResponse")

    action_props = components["PluginActionResponse"]["properties"]
    assert {"success", "restart_required", "message"} <= set(action_props)

    package_action_props = components["PluginPackageActionResponse"]["properties"]
    assert {"success", "package", "restart_required", "message"} <= set(package_action_props)

    reload_props = components["PluginReloadResponse"]["properties"]
    assert {"loaded", "errors", "message"} <= set(reload_props)
    error_ref = reload_props["errors"]["items"]["$ref"]
    assert {"source", "name"} <= set(components[_component_name(error_ref)]["properties"])


def test_admin_config_and_network_update_endpoints_expose_response_contracts() -> None:
    """Remaining admin config/network updates must not publish empty response schemas."""
    from souwen.server.app import app

    schema = app.openapi()
    components = schema["components"]["schemas"]

    expected_refs = {
        ("get", "/api/v1/admin/config"): "AdminConfigResponse",
        ("get", "/api/v1/admin/ping"): "AdminPingResponse",
        ("put", "/api/v1/admin/sources/config/{source_name}"): "UpdateSourceConfigResponse",
        ("put", "/api/v1/admin/proxy"): "ProxyConfigUpdateResponse",
        ("put", "/api/v1/admin/http-backend"): "HttpBackendUpdateResponse",
    }
    for (method, path), component_name in expected_refs.items():
        response_schema = schema["paths"][path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"].endswith(f"/{component_name}")

    config_schema = components["AdminConfigResponse"]
    assert config_schema["type"] == "object"
    assert config_schema["additionalProperties"] is True

    ping_props = components["AdminPingResponse"]["properties"]
    assert ping_props["status"]["const"] == "ok"

    source_update_props = components["UpdateSourceConfigResponse"]["properties"]
    assert {"status", "source"} <= set(source_update_props)
    assert source_update_props["status"]["const"] == "ok"

    proxy_update_props = components["ProxyConfigUpdateResponse"]["properties"]
    assert {"status", "proxy", "proxy_pool"} <= set(proxy_update_props)
    assert proxy_update_props["status"]["const"] == "ok"

    http_backend_update_props = components["HttpBackendUpdateResponse"]["properties"]
    assert {"status", "default", "overrides"} <= set(http_backend_update_props)
    assert http_backend_update_props["status"]["const"] == "ok"


def test_success_json_responses_do_not_publish_empty_schemas() -> None:
    """Typed JSON success responses should not degrade to ambiguous ``{}`` schemas."""
    from souwen.server.app import app

    schema = app.openapi()
    empty: list[tuple[str, str]] = []
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            responses = operation.get("responses", {})
            ok = (
                responses.get("200")
                or responses.get("201")
                or responses.get("202")
                or responses.get("204")
            )
            if not ok:
                continue
            content = ok.get("content", {}).get("application/json", {})
            if content.get("schema") == {}:
                empty.append((method.upper(), path))

    assert empty == []
