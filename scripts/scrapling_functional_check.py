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
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/...` execution.
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check


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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def run_provider_check(
    url: str,
    mode: str,
    *,
    selector: str,
    expected_title: str,
    expected_marker: str,
    timeout: float,
) -> tuple[str, dict[str, object]]:
    configure_scrapling(mode)

    from souwen.web.fetch import fetch_content

    response = await fetch_content(
        urls=[url],
        providers=["scrapling"],
        timeout=timeout,
        skip_ssrf_check=True,
        selector=selector,
        respect_robots_txt=True,
    )
    require(response.provider == "scrapling", f"unexpected provider: {response.provider}")
    require(response.total == 1, f"unexpected total: {response.total}")
    require(response.total_ok == 1, f"unexpected total_ok: {response.total_ok}")
    result = response.results[0]
    require(result.error is None, f"unexpected error: {result.error}")
    require(result.source == "scrapling", f"unexpected source: {result.source}")
    require(result.title == expected_title, f"unexpected title: {result.title}")
    require(expected_marker in result.content, "expected marker not found in content")
    require(result.raw["mode"] == mode, f"unexpected raw mode: {result.raw}")
    return (
        f"scrapling {mode} check passed: {result.final_url}",
        {
            "url": url,
            "final_url": result.final_url,
            "mode": mode,
            "title": result.title,
        },
    )


def verify_real_scrapling_import() -> tuple[str, dict[str, object]]:
    from scrapling.fetchers import AsyncFetcher, DynamicFetcher, StealthyFetcher

    require(hasattr(AsyncFetcher, "get"), "AsyncFetcher.get missing")
    require(hasattr(DynamicFetcher, "async_fetch"), "DynamicFetcher.async_fetch missing")
    require(hasattr(StealthyFetcher, "async_fetch"), "StealthyFetcher.async_fetch missing")
    return (
        "real scrapling.fetchers import check passed",
        {
            "async_fetcher": AsyncFetcher.__name__,
            "dynamic_fetcher": DynamicFetcher.__name__,
            "stealthy_fetcher": StealthyFetcher.__name__,
        },
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run cloud-only Scrapling functional checks.")
    add_common_args(parser, default_mode="fixture")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Also exercise Scrapling DynamicFetcher. Requires `scrapling install` first.",
    )
    args = parser.parse_args()
    recorder = ResultRecorder(script="scrapling_functional_check", mode=args.mode)

    try:
        if args.mode == "offline":
            recorder.record(
                "offline_mode",
                outcome=Outcome.SKIP,
                required=False,
                message="offline mode requested; live Scrapling checks skipped",
            )
        else:
            await run_check(
                recorder,
                "import_scrapling_fetchers",
                verify_real_scrapling_import,
                required=True,
                timeout=args.timeout,
            )
            with local_fixture_server() as url:
                await run_check(
                    recorder,
                    "fetcher_fixture",
                    lambda: run_provider_check(
                        url,
                        "fetcher",
                        selector="main",
                        expected_title="Scrapling Functional Fixture",
                        expected_marker="SouWen Scrapling provider reached the fixture",
                        timeout=args.timeout,
                    ),
                    required=True,
                    timeout=args.timeout,
                )
            if args.browser and args.mode == "live":
                await run_check(
                    recorder,
                    "dynamic_browser_live",
                    lambda: run_provider_check(
                        os.environ.get("SCRAPLING_BROWSER_CHECK_URL", "https://example.com/"),
                        "dynamic",
                        selector="body",
                        expected_title=os.environ.get(
                            "SCRAPLING_BROWSER_CHECK_TITLE", "Example Domain"
                        ),
                        expected_marker=os.environ.get(
                            "SCRAPLING_BROWSER_CHECK_MARKER", "Example Domain"
                        ),
                        timeout=args.timeout,
                    ),
                    required=True,
                    timeout=args.timeout,
                )
            elif args.browser:
                recorder.record(
                    "dynamic_browser_live",
                    outcome=Outcome.SKIP,
                    required=False,
                    message="browser live check requires --mode live",
                )
    finally:
        try:
            recorder.write_reports(
                json_report=args.json_report,
                markdown_report=args.markdown_report,
            )
        except Exception as exc:  # noqa: BLE001 - report write failures have a fixed exit code.
            print(f"failed to write functional check reports: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc

    for check in recorder.checks:
        print(
            "{outcome} {name}: {message}".format(
                outcome=check.outcome.value,
                name=check.name,
                message=check.message,
            )
        )
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
