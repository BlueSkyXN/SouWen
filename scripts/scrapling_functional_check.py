"""Cloud-only Scrapling functional check.

This script intentionally lives outside pytest. It exercises the real
``D4Vinci/Scrapling`` package and SouWen's Scrapling provider integration in a
GitHub Actions job with optional browser runtime installed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator


HTML = """<!doctype html>
<html>
  <head><title>Scrapling Functional Fixture</title></head>
  <body>
    <main id="content">
      <h1>Scrapling Cloud Functional Check</h1>
      <p data-testid="marker">SouWen Scrapling provider reached the fixture.</p>
    </main>
  </body>
</html>
"""


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
            self.send_response(200)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def local_fixture_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/fixture"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def configure_scrapling(mode: str) -> None:
    os.environ["SOUWEN_SOURCES"] = json.dumps(
        {
            "scrapling": {
                "params": {
                    "mode": mode,
                    "content_format": "text",
                    "headless": True,
                    "disable_resources": True,
                    "network_idle": True,
                }
            }
        }
    )
    from souwen.config import reload_config

    reload_config()


async def run_provider_check(url: str, mode: str) -> None:
    configure_scrapling(mode)

    from souwen.web.fetch import fetch_content

    response = await fetch_content(
        urls=[url],
        providers=["scrapling"],
        timeout=30,
        skip_ssrf_check=True,
        selector="main",
        respect_robots_txt=True,
    )
    assert response.provider == "scrapling", response
    assert response.total == 1, response
    assert response.total_ok == 1, response
    result = response.results[0]
    assert result.error is None, result.error
    assert result.source == "scrapling", result
    assert result.title == "Scrapling Functional Fixture", result.title
    assert "SouWen Scrapling provider reached the fixture" in result.content, result.content
    assert result.raw["mode"] == mode, result.raw
    print(f"scrapling {mode} check passed: {result.final_url}")


def verify_real_scrapling_import() -> None:
    from scrapling.fetchers import AsyncFetcher, DynamicFetcher, StealthyFetcher

    assert hasattr(AsyncFetcher, "get")
    assert hasattr(DynamicFetcher, "async_fetch")
    assert hasattr(StealthyFetcher, "async_fetch")
    print("real scrapling.fetchers import check passed")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run cloud-only Scrapling functional checks.")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Also exercise Scrapling DynamicFetcher. Requires `scrapling install` first.",
    )
    args = parser.parse_args()

    verify_real_scrapling_import()
    with local_fixture_server() as url:
        await run_provider_check(url, "fetcher")
        if args.browser:
            await run_provider_check(url, "dynamic")


if __name__ == "__main__":
    asyncio.run(main())
