"""Current-only security behavior fixtures with deterministic local fakes."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
import socket
from typing import Any

import httpx
import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "current_security_behavior_v1.json"


@pytest.fixture()
def current_security() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolate_current_security(monkeypatch, tmp_path):
    """Do not read local HOME/config or initialize external plugins in contract tests."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
    for key in (
        "SOUWEN_USER_PASSWORD",
        "SOUWEN_ADMIN_PASSWORD",
        "SOUWEN_ADMIN_OPEN",
        "SOUWEN_GUEST_ENABLED",
        "SOUWEN_PROXY",
        "SOUWEN_PROXY_POOL",
    ):
        monkeypatch.delenv(key, raising=False)

    from souwen.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _addrinfo(address: str, port: int = 443) -> tuple[Any, ...]:
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))


def test_fixture_is_parseable_current_only_json(current_security: dict[str, Any]) -> None:
    assert current_security["fixture_version"] == 1
    assert current_security["scope"] == "current_security_behavior_only"
    assert current_security["not_target_contract"] is True
    assert current_security["open_decisions"] == [
        "Q-006",
        "Q-007",
        "API-Q-001",
        "Q-008",
        "REL-Q-001",
    ]


def test_current_ssrf_scheme_literal_dns_and_binding_contract(
    current_security: dict[str, Any], monkeypatch
) -> None:
    from souwen.server.schemas.fetch import FetchRequest
    from souwen.web.fetch import fetch_content, resolve_fetch_target, validate_fetch_url

    ssrf = current_security["ssrf"]
    assert ssrf["allowed_schemes"] == ["http", "https"]
    for url in ssrf["blocked_direct_examples"]:
        ok, _reason = validate_fetch_url(url)
        assert ok is False

    bypass = ssrf["internal_bypass_surface"]
    assert bypass["fetch_content_parameter"] in inspect.signature(fetch_content).parameters
    assert (bypass["fetch_content_parameter"] in FetchRequest.model_fields) is bypass[
        "rest_request_field_exposed"
    ]

    public = ssrf["public_dns_example"]
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [_addrinfo(public["resolved_ip"])],
    )
    target, reason = resolve_fetch_target(public["original_url"])
    assert reason == ""
    assert target is not None
    assert target.connect_url == public["connect_url"]
    assert target.host_header == public["host_header"]
    assert target.sni_hostname == public["sni_hostname"]

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [_addrinfo(public["resolved_ip"]), _addrinfo("127.0.0.1")],
    )
    blocked_target, blocked_reason = resolve_fetch_target(public["original_url"])
    assert blocked_target is None
    assert "内部/私有" in blocked_reason


@pytest.mark.asyncio
async def test_current_redirect_and_proxy_paths_keep_bound_ssrf_transport(
    current_security: dict[str, Any], monkeypatch
) -> None:
    from souwen.core.exceptions import SourceUnavailableError
    from souwen.core.scraper import base as base_module
    from souwen.core.scraper.base import BaseScraper
    from souwen.web.fetch import ResolvedFetchTarget

    public = current_security["ssrf"]["public_dns_example"]
    proxy_contract = current_security["ssrf"]["proxy_bound_request"]
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [_addrinfo(public["resolved_ip"])],
    )

    scraper = BaseScraper(min_delay=0, max_delay=0, max_retries=1, use_curl_cffi=False)
    sent: list[str] = []

    async def redirect_once(_url: str, **kwargs: Any) -> httpx.Response:
        target = kwargs["_resolved_target"]
        sent.append(target.connect_url)
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/internal"},
            request=httpx.Request("GET", target.connect_url),
        )

    monkeypatch.setattr(scraper, "_fetch", redirect_once)
    try:
        with pytest.raises(SourceUnavailableError, match="重定向目标被拦截"):
            await scraper._fetch_with_safe_redirects(public["original_url"])
    finally:
        await scraper.close()
    assert sent == [public["connect_url"]]

    captured: dict[str, Any] = {}

    class CapturingAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            captured["request"] = (method, url, kwargs)
            return httpx.Response(200, request=httpx.Request(method, url))

        async def aclose(self) -> None:
            return None

    proxy_scraper = BaseScraper(min_delay=0, max_delay=0, max_retries=1, use_curl_cffi=False)
    proxy_scraper._proxy = proxy_contract["proxy"]
    monkeypatch.setattr(base_module.httpx, "AsyncClient", CapturingAsyncClient)
    target = ResolvedFetchTarget(
        original_url=public["original_url"],
        connect_url=public["connect_url"],
        host_header=public["host_header"],
        sni_hostname=public["sni_hostname"],
    )
    try:
        await proxy_scraper._do_resolved_request("GET", target, None, {"Host": target.host_header})
    finally:
        await proxy_scraper.close()

    assert captured["init"]["proxy"] == proxy_contract["proxy"]
    assert captured["init"]["trust_env"] is proxy_contract["trust_env"]
    assert captured["init"]["follow_redirects"] is proxy_contract["follow_redirects"]
    _method, connect_url, request_kwargs = captured["request"]
    assert connect_url == proxy_contract["connect_url"]
    assert request_kwargs["headers"]["Host"] == proxy_contract["host_header"]
    assert request_kwargs["extensions"] == {"sni_hostname": proxy_contract["sni_hostname"]}


@pytest.mark.asyncio
async def test_current_browser_guard_reuses_ssrf_validation(
    current_security: dict[str, Any],
) -> None:
    from souwen.web.scrapling_fetcher import ScraplingFetcherClient

    browser = current_security["ssrf"]["browser_policy"]

    class FakePage:
        def __init__(self) -> None:
            self.routes: list[tuple[str, Any]] = []

        async def route(self, pattern: str, handler: Any) -> None:
            self.routes.append((pattern, handler))

    class FakeRoute:
        def __init__(self, url: str) -> None:
            self.request = type("Request", (), {"url": url})()
            self.actions: list[str] = []

        async def abort(self) -> None:
            self.actions.append("abort")

        async def fallback(self) -> None:
            self.actions.append("fallback")

    page = FakePage()
    await ScraplingFetcherClient._browser_page_setup()(page)
    assert page.routes and page.routes[0][0] == browser["route_pattern"]
    handler = page.routes[0][1]

    blocked = FakeRoute(browser["blocked_url"])
    await handler(blocked)
    assert blocked.actions == [browser["blocked_action"]]

    allowed = FakeRoute(browser["allowed_url"])
    await handler(allowed)
    assert allowed.actions == [browser["allowed_action"]]


def test_current_request_error_auth_and_config_redaction_contract(
    current_security: dict[str, Any], monkeypatch
) -> None:
    from souwen.config import get_config
    from souwen.core.redaction import redact_llm_search_gateway_config_view, redact_secret_payload
    from souwen.server.app import app

    redaction = current_security["redaction"]
    assert redact_secret_payload(redaction["input"]) == redaction["expected"]
    assert (
        redact_llm_search_gateway_config_view(redaction["gateway_input"])
        == redaction["gateway_expected"]
    )

    client = TestClient(app, raise_server_exceptions=False)
    request_error = current_security["request_error"]
    supplied_id = "fixture-request-id"
    error_response = client.get("/api/v1/fixture-missing", headers={"X-Request-ID": supplied_id})
    assert error_response.status_code == 404
    assert error_response.headers["x-request-id"] == supplied_id
    assert error_response.json()["request_id"] == supplied_id
    assert set(request_error["error_shape"]) <= error_response.json().keys()
    assert error_response.json()["error"] == request_error["not_found_code"]
    assert error_response.headers["x-response-time"].endswith("s")

    monkeypatch.setenv("SOUWEN_USER_PASSWORD", "fixture-user-value")
    monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "fixture-admin-value")
    get_config.cache_clear()
    auth = current_security["auth"]
    preferred = client.get(
        "/api/v1/whoami",
        headers={
            "Authorization": "Bearer outer-proxy-value",
            "X-SouWen-Token": "fixture-admin-value",
        },
    )
    assert preferred.status_code == 200
    assert preferred.json()["role"] == "admin"
    assert auth["precedence"] == "X-SouWen-Token"

    no_fallback = client.get(
        "/api/v1/whoami",
        headers={
            "Authorization": "Bearer fixture-admin-value",
            "X-SouWen-Token": "invalid-fixture-value",
        },
    )
    assert no_fallback.status_code == 401
    assert auth["invalid_explicit_custom_token_fallback"] is False
