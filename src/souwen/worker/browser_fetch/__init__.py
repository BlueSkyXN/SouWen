"""Lightweight public internal contract for the Browser Fetch Worker."""

from .protocol import (
    BROWSER_WORKER_CONTRACT_MAJOR,
    BROWSER_WORKER_DEFAULT_PORT,
    BROWSER_WORKER_PAGE_SLOTS,
    WorkerErrorResponse,
    WorkerFetchRequest,
    WorkerFetchResponse,
    WorkerProbeResponse,
    WorkerRuntimeEvidence,
)

__all__ = [
    "BROWSER_WORKER_CONTRACT_MAJOR",
    "BROWSER_WORKER_DEFAULT_PORT",
    "BROWSER_WORKER_PAGE_SLOTS",
    "WorkerErrorResponse",
    "WorkerFetchRequest",
    "WorkerFetchResponse",
    "WorkerProbeResponse",
    "WorkerRuntimeEvidence",
]
