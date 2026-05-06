"""Cloud-only Crawl4AI functional check.

This script intentionally lives outside pytest. It exercises the real
``crawl4ai`` package and SouWen's Crawl4AI provider integration in a CI job
where browser runtime installation is explicit in the workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

try:
    from scripts._functional_common import (
        CheckSkipped,
        Outcome,
        ResultRecorder,
        add_common_args,
        run_check,
    )
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/...` execution.
    from _functional_common import (
        CheckSkipped,
        Outcome,
        ResultRecorder,
        add_common_args,
        run_check,
    )


HTML = """<!doctype html>
<html>
  <head><title>Crawl4AI Functional Fixture</title></head>
  <body>
    <main id="content">
      <h1>Crawl4AI Cloud Functional Check</h1>
      <p data-testid="marker">SouWen Crawl4AI provider reached the fixture.</p>
    </main>
  </body>
</html>
"""


RUNTIME_MISSING_MARKERS = (
    "Executable doesn't exist",
    "BrowserType.launch",
    "playwright install",
    "Please run",
    "Host system is missing dependencies",
    "No such file or directory",
)


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def looks_like_runtime_missing(message: str | None) -> bool:
    if not message:
        return False
    return any(marker in message for marker in RUNTIME_MISSING_MARKERS)


def verify_real_crawl4ai_import(*, require_runtime: bool) -> tuple[str, dict[str, object]]:
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError as exc:
        if not require_runtime:
            raise CheckSkipped(
                'crawl4ai package is not installed; run pip install -e ".[crawl4ai]" in CI runtime',
                details={"exception_type": exc.__class__.__name__, "message": str(exc)},
            ) from exc
        raise

    require(hasattr(AsyncWebCrawler, "arun"), "AsyncWebCrawler.arun missing")
    return (
        "real crawl4ai AsyncWebCrawler import check passed",
        {"async_web_crawler": AsyncWebCrawler.__name__},
    )


async def run_provider_check(
    url: str,
    *,
    expected_title: str,
    expected_marker: str,
    timeout: float,
    require_runtime: bool,
) -> tuple[str, dict[str, object]]:
    from souwen.web.fetch import fetch_content

    response = await fetch_content(
        urls=[url],
        providers=["crawl4ai"],
        timeout=timeout,
        skip_ssrf_check=True,
    )
    require(response.provider == "crawl4ai", f"unexpected provider: {response.provider}")
    require(response.total == 1, f"unexpected total: {response.total}")
    result = response.results[0]
    if result.error and looks_like_runtime_missing(result.error) and not require_runtime:
        raise CheckSkipped(
            "crawl4ai browser runtime is not installed; CI should install it explicitly",
            details={"url": url, "error": result.error},
        )
    require(response.total_ok == 1, f"unexpected total_ok: {response.total_ok}")
    require(result.error is None, f"unexpected error: {result.error}")
    require(result.source == "crawl4ai", f"unexpected source: {result.source}")
    require(result.title == expected_title, f"unexpected title: {result.title}")
    require(expected_marker in result.content, "expected marker not found in content")
    require(result.raw["provider"] == "crawl4ai", f"unexpected raw provider: {result.raw}")
    return (
        f"crawl4ai fixture check passed: {result.final_url}",
        {
            "url": url,
            "final_url": result.final_url,
            "provider": result.source,
            "title": result.title,
        },
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run cloud-only Crawl4AI functional checks.")
    add_common_args(parser, default_mode="fixture")
    parser.add_argument(
        "--require-runtime",
        action="store_true",
        help="Treat missing crawl4ai/browser runtime as FAIL instead of SKIP.",
    )
    args = parser.parse_args()
    recorder = ResultRecorder(script="crawl4ai_functional_check", mode=args.mode)

    try:
        if args.mode == "offline":
            recorder.record(
                "offline_mode",
                outcome=Outcome.SKIP,
                required=False,
                message="offline mode requested; Crawl4AI checks skipped",
            )
        else:
            import_result = await run_check(
                recorder,
                "import_crawl4ai",
                lambda: verify_real_crawl4ai_import(require_runtime=args.require_runtime),
                required=args.require_runtime,
                timeout=args.timeout,
            )
            if import_result.outcome != Outcome.PASS:
                recorder.record(
                    "browser_fixture",
                    outcome=Outcome.SKIP,
                    required=False,
                    message="crawl4ai import did not pass; browser fixture check skipped",
                )
            else:
                with local_fixture_server() as url:
                    await run_check(
                        recorder,
                        "browser_fixture",
                        lambda: run_provider_check(
                            url,
                            expected_title="Crawl4AI Functional Fixture",
                            expected_marker="SouWen Crawl4AI provider reached the fixture",
                            timeout=args.timeout,
                            require_runtime=args.require_runtime,
                        ),
                        required=args.require_runtime,
                        timeout=args.timeout,
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
