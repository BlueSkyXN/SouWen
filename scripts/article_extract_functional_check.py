"""Cloud-only article extraction functional check.

This script validates optional article extraction runtimes outside ordinary
pytest. It exercises SouWen's ``newspaper`` and ``readability`` fetch providers
against a local HTML fixture when their optional dependencies are installed.
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
from urllib.parse import urlparse

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


ARTICLE_TITLE = "Article Extraction Functional Fixture"
ARTICLE_MARKER = "SouWen article extraction provider reached the fixture"
ARTICLE_HTML = f"""<!doctype html>
<html>
  <head>
    <title>{ARTICLE_TITLE}</title>
    <meta property="og:title" content="{ARTICLE_TITLE}">
    <meta name="description" content="Local fixture for optional article extraction runtimes.">
  </head>
  <body>
    <article>
      <h1>{ARTICLE_TITLE}</h1>
      <p>{ARTICLE_MARKER} with a stable local document.</p>
      <p>
        This fixture contains enough plain language for article extractors to
        produce meaningful body text without using the public internet, browser
        downloads, credentials, or any production account state.
      </p>
      <p>
        It checks the provider integration path rather than only importing the
        optional package, so full runtime gates can detect parser and fetch
        regressions before release.
      </p>
    </article>
  </body>
</html>
"""


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        body = ARTICLE_HTML.encode("utf-8")
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
        yield f"http://{host}:{port}/article"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def allow_local_fixture_url(url: str) -> Iterator[None]:
    """Temporarily allow this script's local fixture origin through URL safety checks."""
    from souwen.web import fetch as fetch_module

    fixture = urlparse(url)
    original_validate = fetch_module.validate_fetch_url

    def _validate(candidate: str) -> tuple[bool, str]:
        parsed = urlparse(candidate)
        same_fixture_origin = (
            parsed.scheme == fixture.scheme
            and parsed.hostname == fixture.hostname
            and parsed.port == fixture.port
        )
        if same_fixture_origin:
            return True, ""
        return original_validate(candidate)

    fetch_module.validate_fetch_url = _validate
    try:
        yield
    finally:
        fetch_module.validate_fetch_url = original_validate


def configure_fixture_runtime() -> None:
    """Keep local fixture checks independent from user proxy/backend settings."""
    os.environ["SOUWEN_EDITION"] = "full"
    raw_sources = os.environ.get("SOUWEN_SOURCES")
    try:
        sources = json.loads(raw_sources) if raw_sources else {}
    except json.JSONDecodeError:
        sources = {}
    if not isinstance(sources, dict):
        sources = {}

    for provider in ("newspaper", "readability"):
        current = sources.get(provider)
        if not isinstance(current, dict):
            current = {}
        sources[provider] = {
            **current,
            "proxy": "none",
            "http_backend": "httpx",
        }
    os.environ["SOUWEN_SOURCES"] = json.dumps(sources)

    from souwen.config import reload_config

    reload_config()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_newspaper_import(*, require_runtime: bool) -> tuple[str, dict[str, object]]:
    try:
        import newspaper
    except ImportError:
        if not require_runtime:
            raise CheckSkipped(
                'newspaper4k runtime is not installed; run pip install -e ".[newspaper]" in CI'
            )
        raise

    require(callable(getattr(newspaper, "article", None)), "newspaper.article missing")
    return (
        "newspaper4k import check passed",
        {"module": "newspaper", "article_callable": True},
    )


def verify_readability_import(*, require_runtime: bool) -> tuple[str, dict[str, object]]:
    try:
        from readability import Document
    except ImportError:
        if not require_runtime:
            raise CheckSkipped(
                'readability-lxml runtime is not installed; run pip install -e ".[readability]" in CI'
            )
        raise

    require(callable(Document), "readability.Document missing")
    return (
        "readability-lxml import check passed",
        {"module": "readability", "document_callable": True},
    )


async def run_provider_check(
    provider: str,
    url: str,
    *,
    timeout: float,
) -> tuple[str, dict[str, object]]:
    from souwen.web.fetch import fetch_content

    response = await fetch_content(
        urls=[url],
        providers=[provider],
        timeout=timeout,
        skip_ssrf_check=True,
    )
    require(response.provider == provider, f"unexpected provider: {response.provider}")
    require(response.total == 1, f"unexpected total: {response.total}")
    require(response.total_ok == 1, f"unexpected total_ok: {response.total_ok}")
    result = response.results[0]
    require(result.error is None, f"unexpected error: {result.error}")
    require(result.source == provider, f"unexpected source: {result.source}")
    require(ARTICLE_MARKER in result.content, "expected fixture marker not found in content")
    return (
        f"{provider} fixture extraction passed: {result.final_url}",
        {
            "provider": provider,
            "url": url,
            "final_url": result.final_url,
            "title": result.title,
            "content_format": result.content_format,
        },
    )


async def _run_optional_provider(
    recorder: ResultRecorder,
    *,
    provider: str,
    import_name: str,
    import_check,
    require_runtime: bool,
    fixture_url: str,
    timeout: float,
) -> None:
    import_result = await run_check(
        recorder,
        import_name,
        lambda: import_check(require_runtime=require_runtime),
        required=require_runtime,
        timeout=timeout,
    )
    if import_result.outcome != Outcome.PASS:
        recorder.record(
            f"{provider}_fixture",
            outcome=Outcome.SKIP,
            required=False,
            message=f"{provider} runtime import did not pass; fixture check skipped",
        )
        return

    await run_check(
        recorder,
        f"{provider}_fixture",
        lambda: run_provider_check(provider, fixture_url, timeout=timeout),
        required=True,
        timeout=timeout,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run article extraction functional checks.")
    add_common_args(parser, default_mode="fixture")
    parser.add_argument(
        "--require-runtime",
        action="store_true",
        help="Treat missing newspaper/readability runtimes as FAIL.",
    )
    parser.add_argument(
        "--require-newspaper",
        action="store_true",
        help="Treat missing newspaper4k runtime as FAIL.",
    )
    parser.add_argument(
        "--require-readability",
        action="store_true",
        help="Treat missing readability-lxml runtime as FAIL.",
    )
    args = parser.parse_args()
    recorder = ResultRecorder(script="article_extract_functional_check", mode=args.mode)

    try:
        if args.mode == "offline":
            recorder.record(
                "offline_mode",
                outcome=Outcome.SKIP,
                required=False,
                message="offline mode requested; article extraction checks skipped",
            )
        else:
            configure_fixture_runtime()
            with local_fixture_server() as url, allow_local_fixture_url(url):
                await _run_optional_provider(
                    recorder,
                    provider="newspaper",
                    import_name="import_newspaper4k",
                    import_check=verify_newspaper_import,
                    require_runtime=args.require_runtime or args.require_newspaper,
                    fixture_url=url,
                    timeout=args.timeout,
                )
                await _run_optional_provider(
                    recorder,
                    provider="readability",
                    import_name="import_readability_lxml",
                    import_check=verify_readability_import,
                    require_runtime=args.require_runtime or args.require_readability,
                    fixture_url=url,
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
