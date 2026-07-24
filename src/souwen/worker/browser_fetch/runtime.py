"""Fail-closed runtime settings and Uvicorn entry point for the Browser Worker."""

from __future__ import annotations

import os
from dataclasses import dataclass

from souwen import __version__

from .app import create_browser_worker_app
from .executor import PlaywrightBrowserExecutor
from .protocol import (
    BROWSER_WORKER_DEFAULT_PORT,
    BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST,
    WorkerRuntimeEvidence,
)


@dataclass(frozen=True)
class BrowserWorkerSettings:
    host: str
    port: int
    token: str
    evidence: WorkerRuntimeEvidence

    @classmethod
    def from_env(cls) -> BrowserWorkerSettings:
        host = os.environ.get("SOUWEN_BROWSER_WORKER_HOST", "127.0.0.1").strip()
        if host != "127.0.0.1":
            raise ValueError("Browser Worker must bind exactly 127.0.0.1")
        try:
            port = int(
                os.environ.get("SOUWEN_BROWSER_WORKER_PORT", str(BROWSER_WORKER_DEFAULT_PORT))
            )
        except ValueError:
            raise ValueError("Browser Worker port must be an integer") from None
        if not 1 <= port <= 65535:
            raise ValueError("Browser Worker port is out of range")

        token = os.environ.get("SOUWEN_BROWSER_WORKER_TOKEN", "")
        if len(token) < 32:
            raise ValueError("SOUWEN_BROWSER_WORKER_TOKEN must contain at least 32 characters")
        source_sha = os.environ.get("SOUWEN_SOURCE_SHA", "").strip().lower()
        config_revision = os.environ.get("SOUWEN_CONFIG_REVISION", "").strip()
        evidence = WorkerRuntimeEvidence(
            source_sha=source_sha,
            runtime_version=__version__,
            config_revision=config_revision,
            provider_inventory_digest=BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST,
        )
        return cls(host=host, port=port, token=token, evidence=evidence)


def run() -> None:
    """Run the internal Worker; the Deployment supervisor owns process lifecycle."""
    import uvicorn

    settings = BrowserWorkerSettings.from_env()
    app = create_browser_worker_app(
        token=settings.token,
        evidence=settings.evidence,
        executor=PlaywrightBrowserExecutor(),
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
        server_header=False,
    )


if __name__ == "__main__":
    run()


__all__ = ["BrowserWorkerSettings", "run"]
