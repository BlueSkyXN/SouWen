"""Fail-closed live gate for the explicitly selected HFS LLM Search Provider."""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.parse import urlsplit

import yaml

from souwen.config import SouWenConfig, get_config, reload_config
from souwen.platform.provider_spi import (
    ExecutionContext,
    LLMSearchRequest,
    ProviderError,
    ProviderRef,
    RequestContext,
)
from souwen.server.v2_runtime import build_target_runtime


DEFAULT_TIMEOUT_SECONDS = 60.0
_QUERY = "What is retrieval augmented generation?"
_EXACT_ENV_REFERENCE = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)\}$")
_MANAGED_ENV_REFERENCE = ("uniapi", "api_key", "UNIAPI_API_KEY")


class PreflightFailure(RuntimeError):
    """A bounded failure that contains no gateway, credential, or raw upstream detail."""


@dataclass(frozen=True, slots=True)
class PreflightReceipt:
    provider_id: str
    evidence_count: int


@contextmanager
def _isolated_environment(values: Mapping[str, str]):
    previous = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(values)
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def _decode_and_validate_config(encoded: str) -> str:
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        raw = yaml.safe_load(decoded)
    except (binascii.Error, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise PreflightFailure("invalid HFS LLM Search configuration") from exc
    if not isinstance(raw, dict):
        raise PreflightFailure("invalid HFS LLM Search configuration")

    gateways = raw.get("llm_search_gateways")
    uniapi = gateways.get("uniapi") if isinstance(gateways, dict) else None
    if not isinstance(uniapi, dict):
        raise PreflightFailure("invalid HFS LLM Search configuration")

    for gateway_name, gateway in gateways.items():
        if not isinstance(gateway, dict):
            continue
        for field_name in ("api_key", "base_url"):
            value = gateway.get(field_name)
            match = _EXACT_ENV_REFERENCE.fullmatch(value) if isinstance(value, str) else None
            if match is None:
                continue
            reference = (gateway_name, field_name, match.group(1))
            if reference != _MANAGED_ENV_REFERENCE:
                raise PreflightFailure(
                    "HFS LLM Search configuration contains an unmanaged environment reference"
                )

    base_url = uniapi.get("base_url")
    parsed = urlsplit(base_url.strip()) if isinstance(base_url, str) else None
    if (
        parsed is None
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or _EXACT_ENV_REFERENCE.fullmatch(base_url.strip()) is not None
    ):
        raise PreflightFailure("HFS LLM Search configuration requires a literal HTTP(S) base URL")
    return decoded


def load_preflight_config(encoded: str, api_key: str) -> SouWenConfig:
    """Load the exact deployment YAML through the production config loader."""
    decoded = _decode_and_validate_config(encoded)
    if not api_key:
        raise PreflightFailure("invalid HFS LLM Search configuration")

    original_cwd = Path.cwd()
    try:
        with tempfile.TemporaryDirectory(prefix="souwen-hfs-llm-preflight-") as tmpdir:
            config_path = Path(tmpdir) / "souwen.yaml"
            config_path.write_text(decoded, encoding="utf-8")
            config_path.chmod(0o600)
            os.chdir(tmpdir)
            try:
                with _isolated_environment(
                    {
                        "HOME": tmpdir,
                        "USERPROFILE": tmpdir,
                        "UNIAPI_API_KEY": api_key,
                    }
                ):
                    get_config.cache_clear()
                    config = reload_config()
            finally:
                os.chdir(original_cwd)
                get_config.cache_clear()
            return config
    except PreflightFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - raw config errors must not escape to CI logs.
        raise PreflightFailure("invalid HFS LLM Search configuration") from exc
    finally:
        get_config.cache_clear()


async def run_preflight(
    config: SouWenConfig,
    *,
    runtime_factory: Callable[[SouWenConfig], Any] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> PreflightReceipt:
    """Execute one exact-provider production request without retry or model fallback."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise PreflightFailure("HFS LLM Search preflight timeout must be positive")
    selected = config.enabled_uniapi_ark_source_ids()
    if len(selected) != 1:
        raise PreflightFailure(
            "HFS LLM Search preflight requires exactly one explicitly selected Provider"
        )
    provider_id = selected[0]
    factory = runtime_factory or build_target_runtime
    runtime = None
    result = None
    failure: BaseException | None = None
    try:
        runtime = factory(config)
        result = await runtime.services.llm_search.search(
            LLMSearchRequest(
                query=_QUERY,
                providers=(ProviderRef(id=provider_id, kind="llm_search"),),
                strategy="single",
                max_results_per_provider=1,
            ),
            RequestContext(request_id="hfs-llm-provider-preflight"),
            ExecutionContext.with_timeout(timeout_seconds),
        )
    except asyncio.CancelledError:
        failure = PreflightFailure(
            f"selected LLM Search Provider {provider_id} failed: provider_unavailable"
        )
    except ProviderError as exc:
        retry_after = ""
        if exc.retry_after_seconds is not None:
            retry_after = f", retry_after={exc.retry_after_seconds:g}"
        failure = PreflightFailure(
            f"selected LLM Search Provider {provider_id} failed: {exc.code.value}{retry_after}"
        )
    except Exception:  # noqa: BLE001 - never expose transport/config exception text.
        failure = PreflightFailure(
            f"selected LLM Search Provider {provider_id} failed: provider_unavailable"
        )

    if runtime is not None:
        try:
            await runtime.close()
        except asyncio.CancelledError:
            if failure is None:
                failure = PreflightFailure("HFS LLM Search preflight runtime cleanup failed")
        except Exception:  # noqa: BLE001 - cleanup errors must remain credential-safe.
            if failure is None:
                failure = PreflightFailure("HFS LLM Search preflight runtime cleanup failed")

    if failure is not None:
        raise failure
    evidence = getattr(result, "evidence", ())
    if not isinstance(evidence, (tuple, list)) or not evidence:
        raise PreflightFailure(
            f"selected LLM Search Provider {provider_id} failed: invalid_upstream_response"
        )
    return PreflightReceipt(provider_id=provider_id, evidence_count=len(evidence))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe the one HFS-configured LLM Search Provider before any Space mutation."
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Single provider-call timeout in seconds (default: 60).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    encoded = os.environ.get("SOUWEN_CONFIG_B64", "")
    api_key = os.environ.get("UNIAPI_API_KEY", "")
    if not encoded or not api_key:
        print("ERROR: HFS LLM Search preflight requires configured secrets", file=sys.stderr)
        return 1
    try:
        config = load_preflight_config(encoded, api_key)
        receipt = asyncio.run(
            run_preflight(
                config,
                timeout_seconds=args.request_timeout,
            )
        )
    except PreflightFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 - never expose unexpected runtime/config exception text.
        print("ERROR: HFS LLM Search preflight failed safely", file=sys.stderr)
        return 1
    print(
        "HFS LLM Search preflight passed: "
        f"provider={receipt.provider_id}, evidence={receipt.evidence_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
