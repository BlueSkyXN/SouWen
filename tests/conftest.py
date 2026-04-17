"""Pytest 全局 fixtures。

提供 autouse fixture，保证用例之间状态隔离。

Fixtures:
- ``_auto_clear_config_cache``：autouse，在每个测试前后清空 ``get_config``
  的 lru_cache，避免 ``monkeypatch.setenv`` / ``reload_config`` 在一个用例
  里写入的配置污染后续用例（最典型的场景是前一个 case 设置了
  ``SOUWEN_TAVILY_API_KEY``，后一个 case 期望它未设置）。
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
