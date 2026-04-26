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


@pytest.fixture
def clean_registry():
    """保存并恢复 registry 状态，给插件相关测试用。

    适用于会向 _REGISTRY / _EXTERNAL_PLUGINS 写入条目的测试，
    避免污染其他用例（特别是 test_consistency.py 的全量遍历）。
    """
    from souwen.registry.views import _EXTERNAL_PLUGINS, _REGISTRY

    saved_registry = dict(_REGISTRY)
    saved_plugins = set(_EXTERNAL_PLUGINS)
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(saved_registry)
        _EXTERNAL_PLUGINS.clear()
        _EXTERNAL_PLUGINS.update(saved_plugins)


@pytest.fixture
def clean_fetch_handlers():
    """保存并恢复 fetch handler 注册表，给插件相关测试用。"""
    from souwen.web.fetch import _FETCH_HANDLERS

    saved = dict(_FETCH_HANDLERS)
    try:
        yield
    finally:
        _FETCH_HANDLERS.clear()
        _FETCH_HANDLERS.update(saved)


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
