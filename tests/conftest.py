"""Pytest 全局 fixtures。

`_auto_clear_config_cache`：每个测试前后清除 `get_config` 的 lru_cache，
避免 env 变量 / monkeypatch 状态在用例间泄漏。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _auto_clear_config_cache():
    from souwen.config import get_config

    try:
        get_config.cache_clear()
    except AttributeError:
        pass
    yield
    try:
        get_config.cache_clear()
    except AttributeError:
        pass
