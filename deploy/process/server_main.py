"""Frozen-aware entry point for the target SouWen server bundle."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__:
    from .supervisor import INTERNAL_ROLE_ENV, DeploymentSettings, main as supervisor_main
else:
    from supervisor import INTERNAL_ROLE_ENV, DeploymentSettings, main as supervisor_main


logger = logging.getLogger("souwen.deployment.server_main")
_ROLLOUT_ENV = "SOUWEN_V2_ROLLOUT"
_BROWSER_DIRNAME = "ms-playwright"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="souwen-server",
        description="Start the target SouWen API runtime and its internal Browser Worker.",
    )
    parser.add_argument("--host", choices=("0.0.0.0", "127.0.0.1"))
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--internal-role",
        choices=("worker", "api"),
        help=argparse.SUPPRESS,
    )
    return parser


def _force_target_rollout() -> None:
    configured = os.environ.get(_ROLLOUT_ENV, "").strip().lower()
    if configured and configured != "target":
        raise ValueError("souwen-server only supports SOUWEN_V2_ROLLOUT=target")
    os.environ[_ROLLOUT_ENV] = "target"


def _configure_frozen_browser_runtime() -> None:
    if not getattr(sys, "frozen", False):
        return
    browser_root = Path(sys.executable).resolve().parent / _BROWSER_DIRNAME
    if not browser_root.is_dir():
        raise RuntimeError("souwen-server bundle is missing its Playwright Chromium runtime")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_root)


def _run_worker() -> None:
    from souwen.worker.browser_fetch.runtime import run

    run()


def _run_api() -> None:
    import uvicorn

    settings = DeploymentSettings.from_env()
    uvicorn.run(
        "souwen.server.app:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=1,
        log_level="info",
        access_log=True,
        timeout_keep_alive=120,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.internal_role is not None and os.environ.get(INTERNAL_ROLE_ENV) != "1":
        parser.error("internal server roles are reserved for the SouWen supervisor")

    try:
        _force_target_rollout()
        _configure_frozen_browser_runtime()
        if args.host is not None:
            os.environ["HOST"] = args.host
        if args.port is not None:
            os.environ["PORT"] = str(args.port)

        if args.internal_role == "worker":
            _run_worker()
            return 0
        if args.internal_role == "api":
            _run_api()
            return 0
        return supervisor_main()
    except (RuntimeError, ValueError) as exc:
        logger.error("server bundle entry point failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
