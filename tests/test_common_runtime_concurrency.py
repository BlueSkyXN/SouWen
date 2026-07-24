"""Canonical loop-local semaphore and legacy concurrency-policy conformance."""

from __future__ import annotations

import ast
import asyncio
import gc
import importlib
import weakref
from pathlib import Path

import pytest

import souwen.common_runtime.resilience.concurrency as canonical_module
from souwen.common_runtime.resilience import LoopLocalSemaphorePool
from souwen.core import concurrency as legacy_module


def _run_in_new_loop(factory):
    loop = asyncio.new_event_loop()
    try:
        return loop, loop.run_until_complete(factory())
    except BaseException:
        loop.close()
        raise


def test_canonical_pool_is_stdlib_only_and_product_neutral() -> None:
    path = Path(canonical_module.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert imported == {"__future__", "asyncio", "weakref"}
    assert '"search"' not in source
    assert '"web"' not in source
    assert "SOUWEN_MAX_CONCURRENCY" not in source


def test_same_loop_identity_and_first_size_wins() -> None:
    pool = LoopLocalSemaphorePool()

    async def exercise() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
        return pool.get(2), pool.get(7)

    semaphore, same_semaphore = asyncio.run(exercise())

    assert semaphore is same_semaphore
    assert semaphore._value == 2


def test_different_loops_and_pools_are_isolated() -> None:
    first_pool = LoopLocalSemaphorePool()
    second_pool = LoopLocalSemaphorePool()

    async def get_from_first() -> asyncio.Semaphore:
        return first_pool.get(2)

    async def get_from_both() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
        return first_pool.get(3), second_pool.get(4)

    loop_one, semaphore_one = _run_in_new_loop(get_from_first)
    loop_one.close()
    loop_two, (semaphore_two, other_pool_semaphore) = _run_in_new_loop(get_from_both)
    loop_two.close()

    assert semaphore_one is not semaphore_two
    assert semaphore_two is not other_pool_semaphore
    assert semaphore_one._value == 2
    assert semaphore_two._value == 3
    assert other_pool_semaphore._value == 4


def test_clear_replaces_current_loop_semaphore() -> None:
    pool = LoopLocalSemaphorePool()

    async def exercise() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
        before = pool.get(2)
        pool.clear()
        after = pool.get(5)
        return before, after

    before, after = asyncio.run(exercise())

    assert before is not after
    assert before._value == 2
    assert after._value == 5


def test_clear_discards_entries_for_all_live_loops() -> None:
    pool = LoopLocalSemaphorePool()

    async def get(size: int) -> asyncio.Semaphore:
        return pool.get(size)

    loop_one, semaphore_one = _run_in_new_loop(lambda: get(2))
    loop_two, semaphore_two = _run_in_new_loop(lambda: get(3))
    try:
        pool.clear()
        next_one = loop_one.run_until_complete(get(5))
        next_two = loop_two.run_until_complete(get(7))
    finally:
        loop_one.close()
        loop_two.close()

    assert next_one is not semaphore_one
    assert next_two is not semaphore_two
    assert next_one._value == 5
    assert next_two._value == 7


def test_size_semantics_and_running_loop_error_match_asyncio() -> None:
    pool = LoopLocalSemaphorePool()

    with pytest.raises(RuntimeError, match="no running event loop"):
        pool.get(1)

    async def zero_size() -> asyncio.Semaphore:
        return pool.get(0)

    assert asyncio.run(zero_size())._value == 0

    pool.clear()

    async def negative_size() -> None:
        pool.get(-1)

    with pytest.raises(ValueError, match="Semaphore initial value must be >= 0"):
        asyncio.run(negative_size())


def test_closed_loop_entry_is_removed_after_garbage_collection() -> None:
    pool = LoopLocalSemaphorePool()

    async def get_semaphore() -> asyncio.Semaphore:
        return pool.get(1)

    loop, semaphore = _run_in_new_loop(get_semaphore)
    loop_ref = weakref.ref(loop)
    assert len(pool._semaphores) == 1

    loop.close()
    del loop
    del semaphore
    gc.collect()

    assert loop_ref() is None
    assert len(pool._semaphores) == 0


@pytest.fixture(autouse=True)
def _clear_legacy_pools() -> None:
    legacy_module.clear_semaphore()
    yield
    legacy_module.clear_semaphore()


def test_legacy_channels_use_independent_canonical_pools() -> None:
    assert set(legacy_module._sem_pools) == {"search", "web"}
    assert all(
        isinstance(pool, LoopLocalSemaphorePool) for pool in legacy_module._sem_pools.values()
    )

    async def exercise() -> tuple[asyncio.Semaphore, asyncio.Semaphore, asyncio.Semaphore]:
        search = legacy_module.get_semaphore("search", 2)
        search_again = legacy_module.get_semaphore("search", 9)
        web = legacy_module.get_semaphore("web", 3)
        return search, search_again, web

    search, search_again, web = asyncio.run(exercise())

    assert search is search_again
    assert search is not web
    assert search._value == 2
    assert web._value == 3


def test_legacy_environment_policy_and_exact_unknown_channel_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOUWEN_MAX_CONCURRENCY", "6")

    async def get_default() -> asyncio.Semaphore:
        return legacy_module.get_semaphore("search")

    assert asyncio.run(get_default())._value == 6

    with pytest.raises(ValueError) as exc_info:
        legacy_module.get_semaphore("provider")
    assert str(exc_info.value) == "unknown channel 'provider'; expected 'search' or 'web'"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 10),
        ("", 10),
        ("0", 10),
        ("-3", 10),
        ("invalid", 10),
        ("6", 6),
    ],
)
def test_legacy_max_concurrency_environment_matrix(
    monkeypatch: pytest.MonkeyPatch,
    raw: str | None,
    expected: int,
) -> None:
    if raw is None:
        monkeypatch.delenv("SOUWEN_MAX_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("SOUWEN_MAX_CONCURRENCY", raw)

    assert legacy_module.get_max_concurrency() == expected


def test_legacy_valid_channel_requires_running_loop_and_unknown_clear_is_noop() -> None:
    with pytest.raises(RuntimeError, match="no running event loop"):
        legacy_module.get_semaphore("search", 1)

    legacy_module.clear_semaphore("unknown")
    assert set(legacy_module._sem_pools) == {"search", "web"}


def test_search_and_web_helpers_use_isolated_canonical_pools() -> None:
    search_module = importlib.import_module("souwen.search")
    web_search_module = importlib.import_module("souwen.web.search")

    async def exercise() -> tuple[asyncio.Semaphore, asyncio.Semaphore, asyncio.AbstractEventLoop]:
        return (
            search_module._get_semaphore(),
            web_search_module._get_web_semaphore(),
            asyncio.get_running_loop(),
        )

    search, web, loop = asyncio.run(exercise())

    assert search is not web
    assert search is legacy_module._sem_pools["search"]._semaphores.get(loop)
    assert web is legacy_module._sem_pools["web"]._semaphores.get(loop)


def test_legacy_clear_one_channel_or_all() -> None:
    async def populate() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
        return (
            legacy_module.get_semaphore("search", 1),
            legacy_module.get_semaphore("web", 2),
        )

    async def read_again() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
        return (
            legacy_module.get_semaphore("search", 3),
            legacy_module.get_semaphore("web", 4),
        )

    async def exercise() -> tuple[
        asyncio.Semaphore,
        asyncio.Semaphore,
        asyncio.Semaphore,
        asyncio.Semaphore,
        asyncio.Semaphore,
        asyncio.Semaphore,
    ]:
        original_search, original_web = await populate()
        legacy_module.clear_semaphore("search")
        next_search, same_web = await read_again()
        legacy_module.clear_semaphore()
        final_search, final_web = await read_again()
        return original_search, original_web, next_search, same_web, final_search, final_web

    original_search, original_web, next_search, same_web, final_search, final_web = asyncio.run(
        exercise()
    )

    assert next_search is not original_search
    assert same_web is original_web
    assert final_search is not next_search
    assert final_web is not same_web
    assert next_search._value == 3
    assert same_web._value == 2
    assert final_search._value == 3
    assert final_web._value == 4


def test_legacy_channel_clear_discards_entries_for_all_live_loops() -> None:
    async def get_search(size: int) -> asyncio.Semaphore:
        return legacy_module.get_semaphore("search", size)

    loop_one, semaphore_one = _run_in_new_loop(lambda: get_search(2))
    loop_two, semaphore_two = _run_in_new_loop(lambda: get_search(3))
    try:
        legacy_module.clear_semaphore("search")
        next_one = loop_one.run_until_complete(get_search(5))
        next_two = loop_two.run_until_complete(get_search(7))
    finally:
        loop_one.close()
        loop_two.close()

    assert next_one is not semaphore_one
    assert next_two is not semaphore_two
    assert next_one._value == 5
    assert next_two._value == 7
