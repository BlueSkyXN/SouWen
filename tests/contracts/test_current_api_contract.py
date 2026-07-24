"""Current-only, language-neutral HTTP fixture checks.

These tests intentionally lock the present API shape.  They are not a target
API contract and must not be used to introduce future `/api/v1` operations.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "current_api_golden.json"


@pytest.fixture()
def golden() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolate_current_contract(monkeypatch, tmp_path):
    """Keep contract checks deterministic and independent of local configuration/plugins."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
    for key in (
        "SOUWEN_USER_PASSWORD",
        "SOUWEN_ADMIN_PASSWORD",
        "SOUWEN_ADMIN_OPEN",
        "SOUWEN_GUEST_ENABLED",
        "SOUWEN_EDITION",
    ):
        monkeypatch.delenv(key, raising=False)

    from souwen.config import get_config
    from souwen.server import limiter as limiter_mod

    get_config.cache_clear()
    monkeypatch.setattr(
        limiter_mod,
        "_search_limiter",
        limiter_mod.InMemoryRateLimiter(max_requests=60, window_seconds=60),
    )
    yield
    get_config.cache_clear()


def _schema_name(schema: dict) -> str:
    return schema["$ref"].rsplit("/", maxsplit=1)[-1]


def test_fixture_is_current_only_parseable_json(golden: dict) -> None:
    assert golden["fixture_version"] == 1
    assert golden["scope"] == "current_api_only"
    assert golden["not_target_contract"] is True
    assert set(golden["operations"]) == {
        "health",
        "readiness",
        "search_paper",
        "enriched_web_search",
        "fetch",
    }
    assert golden["errors"]["shape"] == ["error", "detail", "request_id"]


def test_golden_examples_parse_against_current_pydantic_models(golden: dict) -> None:
    from souwen.models import FetchResponse
    from souwen.server.schemas.common import ErrorResponse, HealthResponse, ReadinessResponse
    from souwen.server.schemas.fetch import FetchRequest
    from souwen.server.schemas.search import (
        EnrichedWebSearchRequest,
        EnrichedWebSearchResponse,
        SearchPaperResponse,
    )

    operations = golden["operations"]
    HealthResponse.model_validate(operations["health"]["response"])
    ReadinessResponse.model_validate(operations["readiness"]["response"])
    SearchPaperResponse.model_validate(operations["search_paper"]["response"])
    EnrichedWebSearchRequest.model_validate(operations["enriched_web_search"]["request"]["json"])
    EnrichedWebSearchResponse.model_validate(operations["enriched_web_search"]["response"])
    FetchRequest.model_validate(operations["fetch"]["request"]["json"])
    response = FetchResponse.model_validate(operations["fetch"]["response"])
    assert response.provider == "builtin"
    for error in ("not_found", "validation_error", "unauthorized"):
        ErrorResponse.model_validate(golden["errors"][error]["response"])


def test_openapi_matches_current_fixture_operation_refs(golden: dict) -> None:
    from souwen.server.app import app

    schema = app.openapi()
    for operation in golden["operations"].values():
        request = operation["request"]
        expected = operation["openapi"]
        actual = schema["paths"][request["path"]][expected["method"]]
        assert (
            _schema_name(actual["responses"]["200"]["content"]["application/json"]["schema"])
            == (expected["response_schema"])
        )
        if "request_schema" in expected:
            assert (
                _schema_name(actual["requestBody"]["content"]["application/json"]["schema"])
                == (expected["request_schema"])
            )
        if "required_query_parameter" in expected:
            parameters = {parameter["name"]: parameter for parameter in actual["parameters"]}
            required = parameters[expected["required_query_parameter"]]
            assert required["in"] == "query"
            assert required["required"] is True

    # Current global exception handlers supply the flat body at runtime; they are not OpenAPI components.
    assert "ErrorResponse" not in schema["components"]["schemas"]


def test_current_health_readiness_and_error_routes_follow_fixture(
    golden: dict, monkeypatch
) -> None:
    from souwen.server.app import app

    client = TestClient(app, raise_server_exceptions=False)
    operations = golden["operations"]

    health = client.get(operations["health"]["request"]["path"])
    assert health.status_code == 200
    assert health.json()["status"] == operations["health"]["response"]["status"]
    assert {"version", "source_sha"} <= health.json().keys()

    readiness = client.get(operations["readiness"]["request"]["path"])
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is operations["readiness"]["response"]["ready"]

    missing = client.get(golden["errors"]["not_found"]["request"]["path"])
    assert missing.status_code == 404
    assert missing.json()["error"] == golden["errors"]["not_found"]["response"]["error"]
    assert set(golden["errors"]["shape"]) <= missing.json().keys()
    assert missing.headers["x-request-id"] == missing.json()["request_id"]

    monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
    from souwen.config import get_config

    get_config.cache_clear()
    invalid_fetch = client.post(
        golden["errors"]["validation_error"]["request"]["path"],
        json=golden["errors"]["validation_error"]["request"]["json"],
    )
    assert invalid_fetch.status_code == 422
    assert (
        invalid_fetch.json()["error"] == golden["errors"]["validation_error"]["response"]["error"]
    )
    assert set(golden["errors"]["shape"]) <= invalid_fetch.json().keys()


def test_current_auth_and_fetch_route_behavior_follow_fixture(golden: dict, monkeypatch) -> None:
    from souwen.models import FetchResponse, FetchResult
    from souwen.server.app import app

    client = TestClient(app, raise_server_exceptions=False)
    unauthorized = golden["errors"]["unauthorized"]

    monkeypatch.setenv("SOUWEN_USER_PASSWORD", "fixture-user-password")
    from souwen.config import get_config

    get_config.cache_clear()
    auth_response = client.get(
        unauthorized["request"]["path"], params=unauthorized["request"]["query"]
    )
    assert auth_response.status_code == 401
    assert auth_response.json()["error"] == unauthorized["response"]["error"]
    assert auth_response.headers["www-authenticate"] == unauthorized["headers"]["WWW-Authenticate"]

    monkeypatch.delenv("SOUWEN_USER_PASSWORD", raising=False)
    monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
    get_config.cache_clear()

    async def fake_fetch(**kwargs):
        response = golden["operations"]["fetch"]["response"]
        assert kwargs["urls"] == response["urls"]
        return FetchResponse.model_validate(response)

    import souwen.web.fetch as web_fetch

    monkeypatch.setattr(web_fetch, "fetch_content", fake_fetch)
    fetch_operation = golden["operations"]["fetch"]
    fetch_response = client.post(
        fetch_operation["request"]["path"], json=fetch_operation["request"]["json"]
    )
    assert fetch_response.status_code == 200
    assert fetch_response.json() == fetch_operation["response"]
    assert FetchResult.model_validate(fetch_response.json()["results"][0]).source == "builtin"
