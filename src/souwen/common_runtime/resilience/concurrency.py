"""Event-loop-local concurrency primitives without product policy."""

from __future__ import annotations

import asyncio
import weakref


class LoopLocalSemaphorePool:
    """Return one semaphore per running event loop for this pool."""

    def __init__(self) -> None:
        self._semaphores: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, asyncio.Semaphore
        ] = weakref.WeakKeyDictionary()

    def get(self, size: int) -> asyncio.Semaphore:
        """Return the current loop's semaphore, creating it with ``size`` once."""
        loop = asyncio.get_running_loop()
        semaphore = self._semaphores.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(size)
            self._semaphores[loop] = semaphore
        return semaphore

    def clear(self) -> None:
        """Discard all loop-local semaphores owned by this pool."""
        self._semaphores = weakref.WeakKeyDictionary()
