"""Wayback public route request-boundary tests."""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from souwen.models import WaybackAvailability, WaybackCDXResponse


@pytest.fixture(autouse=True)
def isolated_search_limiter(monkeypatch):
    from souwen.server import limiter as limiter_mod

    monkeypatch.setattr(
        limiter_mod,
        "_search_limiter",
        limiter_mod.InMemoryRateLimiter(max_requests=60, window_seconds=60),
    )


@pytest.fixture()
def client():
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def stub_wayback_client(monkeypatch):
    """Replace WaybackClient with an in-memory fake and record route inputs."""
    calls: list[dict] = []

    class FakeWaybackClient:
        async def query_snapshots(
            self,
            url,
            from_date=None,
            to_date=None,
            filter_status=None,
            limit=100,
            collapse=None,
            timeout=60.0,
        ):
            calls.append(
                {
                    "method": "cdx",
                    "url": url,
                    "from_date": from_date,
                    "to_date": to_date,
                    "filter_status": filter_status,
                    "limit": limit,
                    "collapse": collapse,
                    "timeout": timeout,
                }
            )
            return WaybackCDXResponse(url=url, snapshots=[], total=0)

        async def check_availability(self, url, timestamp=None, timeout=30.0):
            calls.append(
                {
                    "method": "check",
                    "url": url,
                    "timestamp": timestamp,
                    "timeout": timeout,
                }
            )
            return WaybackAvailability(
                url=url,
                available=True,
                snapshot_url="https://web.archive.org/web/20240101000000/https://example.com/",
                timestamp="20240101000000",
                status_code=200,
            )

    monkeypatch.setattr("souwen.web.wayback.WaybackClient", FakeWaybackClient)
    return calls


@pytest.mark.parametrize("path", ["/api/v1/wayback/cdx", "/api/v1/wayback/check"])
def test_wayback_blank_url_returns_422(client, stub_wayback_client, path):
    """Blank URL query values should be rejected before calling WaybackClient."""
    resp = client.get(path, params={"url": "   "})

    assert resp.status_code == 422
    assert stub_wayback_client == []


def test_wayback_cdx_url_is_normalized(client, stub_wayback_client):
    """CDX route should trim URL before querying the Wayback client."""
    resp = client.get(
        "/api/v1/wayback/cdx",
        params={
            "url": " https://example.com/* ",
            "from": "20240101",
            "to": "20240131",
            "filter_status": 200,
            "collapse": "timestamp:8",
            "limit": 5,
            "timeout": 9,
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["url"] == "https://example.com/*"
    assert stub_wayback_client == [
        {
            "method": "cdx",
            "url": "https://example.com/*",
            "from_date": "20240101",
            "to_date": "20240131",
            "filter_status": [200],
            "limit": 5,
            "collapse": "timestamp:8",
            "timeout": 9.0,
        }
    ]


def test_wayback_check_url_is_normalized(client, stub_wayback_client):
    """Availability route should trim URL before querying the Wayback client."""
    resp = client.get(
        "/api/v1/wayback/check",
        params={
            "url": " https://example.com/ ",
            "timestamp": "20240101",
            "timeout": 7,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["url"] == "https://example.com/"
    assert body["available"] is True
    assert stub_wayback_client == [
        {
            "method": "check",
            "url": "https://example.com/",
            "timestamp": "20240101",
            "timeout": 7.0,
        }
    ]
