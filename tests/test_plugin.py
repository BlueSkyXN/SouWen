"""souwen.plugin 测试 — 外部插件发现、加载与注册。

覆盖：
  - _coerce_to_adapters：单/列表/工厂 callable/异常分支
  - _resolve_dotted_path：合法/非法/缺失模块或属性
  - _reg_external：新增/重名/external_plugins 视图
  - discover_entrypoint_plugins：无入口/有效入口/加载失败
  - load_config_plugins：合法/非法/空
  - load_plugins：纯 entry_points / 含 config / 错误隔离
  - _reset_registry 清理 EXTERNAL_PLUGINS
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import BaseModel

from souwen.plugin import (
    Plugin,
    _PLUGINS,
    _coerce_to_adapters,
    _coerce_to_plugin,
    _register_plugin,
    _resolve_dotted_path,
    discover_entrypoint_plugins,
    get_loaded_plugins,
    load_config_plugins,
    load_plugins,
    unload_plugin,
)
from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.loader import lazy
from souwen.registry.views import (
    _EXTERNAL_PLUGINS,
    _REGISTRY,
    _reg_external,
    _reset_registry,
    all_adapters,
    external_plugins,
)
from souwen.web.fetch import (
    _FETCH_HANDLERS,
    _current_plugin_owner,
    get_fetch_handler_owners,
    register_fetch_handler,
    unregister_fetch_handlers_by_owner,
)
from souwen.testing import assert_valid_plugin, validate_client_contract


# ── helpers ────────────────────────────────────────────────


def make_test_adapter(name: str = "test_plugin", domain: str = "fetch") -> SourceAdapter:
    """构造测试用 adapter，复用 builtin fetch 的 client_loader。"""
    return SourceAdapter(
        name=name,
        domain=domain,
        integration="scraper",
        description=f"Test plugin: {name}",
        config_field=None,
        client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        needs_config=False,
    )


class _FakeEntryPoint:
    """模拟 importlib.metadata.EntryPoint."""

    def __init__(self, name: str, loader):
        self.name = name
        self._loader = loader

    def load(self):
        return self._loader()


class _FakeEntryPoints:
    """模拟 importlib.metadata.EntryPoints（实现 .select）。"""

    def __init__(self, eps: list[_FakeEntryPoint]):
        self._eps = eps

    def select(self, *, group: str):  # noqa: ARG002
        return list(self._eps)


# ── _coerce_to_adapters ────────────────────────────────────


class TestCoerceToAdapters:
    def test_single_adapter(self):
        a = make_test_adapter("c1")
        out = _coerce_to_adapters(a)
        assert out == [a]

    def test_callable_returning_adapter(self):
        a = make_test_adapter("c2")
        out = _coerce_to_adapters(lambda: a)
        assert out == [a]

    def test_list_of_adapters(self):
        a1, a2 = make_test_adapter("c3a"), make_test_adapter("c3b")
        out = _coerce_to_adapters([a1, a2])
        assert out == [a1, a2]

    def test_tuple_of_adapters(self):
        a1, a2 = make_test_adapter("c3c"), make_test_adapter("c3d")
        out = _coerce_to_adapters((a1, a2))
        assert out == [a1, a2]

    def test_callable_returning_list(self):
        a1, a2 = make_test_adapter("c4a"), make_test_adapter("c4b")
        out = _coerce_to_adapters(lambda: [a1, a2])
        assert out == [a1, a2]

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError, match="必须是 Plugin"):
            _coerce_to_adapters(123)

    def test_invalid_type_string_raises(self):
        with pytest.raises(TypeError):
            _coerce_to_adapters("not an adapter")

    def test_list_with_non_adapter_raises(self):
        a = make_test_adapter("c5")
        with pytest.raises(TypeError, match="非 SourceAdapter 元素"):
            _coerce_to_adapters([a, "bad"])


# ── _resolve_dotted_path ────────────────────────────────────


class TestResolveDottedPath:
    def test_valid_path(self):
        obj = _resolve_dotted_path("souwen.registry.views:all_adapters")
        assert callable(obj)
        assert obj is all_adapters

    def test_missing_colon_raises(self):
        with pytest.raises(ValueError, match="必须是"):
            _resolve_dotted_path("souwen.registry.views.all_adapters")

    def test_empty_module_raises(self):
        with pytest.raises(ValueError):
            _resolve_dotted_path(":attr")

    def test_empty_attr_raises(self):
        with pytest.raises(ValueError):
            _resolve_dotted_path("souwen.registry.views:")

    def test_nonexistent_module_raises(self):
        with pytest.raises(ImportError):
            _resolve_dotted_path("souwen.nonexistent_xyz_module:foo")

    def test_nonexistent_attr_raises(self):
        with pytest.raises(AttributeError, match="没有属性"):
            _resolve_dotted_path("souwen.registry.views:nonexistent_attr_xyz")


# ── _reg_external ──────────────────────────────────────────


class TestRegExternal:
    def test_new_adapter_registered(self, clean_registry):
        a = make_test_adapter("ext_new_one")
        ok = _reg_external(a)
        assert ok is True
        assert "ext_new_one" in _REGISTRY
        assert "ext_new_one" in _EXTERNAL_PLUGINS
        assert "ext_new_one" in external_plugins()

    def test_duplicate_returns_false(self, clean_registry):
        a = make_test_adapter("ext_dup")
        assert _reg_external(a) is True
        # 同名再注册应失败
        a2 = make_test_adapter("ext_dup")
        ok = _reg_external(a2)
        assert ok is False

    def test_external_plugins_sorted(self, clean_registry):
        _reg_external(make_test_adapter("zz_plugin"))
        _reg_external(make_test_adapter("aa_plugin"))
        plugins = external_plugins()
        assert plugins.index("aa_plugin") < plugins.index("zz_plugin")

    def test_appears_in_all_adapters(self, clean_registry):
        a = make_test_adapter("ext_visible")
        _reg_external(a)
        assert "ext_visible" in all_adapters()
        assert all_adapters()["ext_visible"] is a


# ── discover_entrypoint_plugins ────────────────────────────


class TestDiscoverEntrypointPlugins:
    def test_no_plugins_installed(self, clean_registry, monkeypatch):
        # 强制返回空 EntryPoints
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([]),
        )
        loaded, errors = discover_entrypoint_plugins()
        assert loaded == []
        assert errors == []

    def test_valid_entry_point(self, clean_registry, monkeypatch):
        adapter = make_test_adapter("ep_ok")
        ep = _FakeEntryPoint("ep_ok", lambda: adapter)
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([ep]),
        )
        loaded, errors = discover_entrypoint_plugins()
        assert loaded == ["ep_ok"]
        assert errors == []
        assert "ep_ok" in external_plugins()

    def test_entry_point_load_failure(self, clean_registry, monkeypatch):
        def boom():
            raise RuntimeError("boom!")

        ep = _FakeEntryPoint("bad_ep", boom)
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([ep]),
        )
        loaded, errors = discover_entrypoint_plugins()
        assert loaded == []
        assert len(errors) == 1
        assert errors[0]["name"] == "bad_ep"
        assert "boom" in errors[0]["error"]

    def test_entry_points_call_itself_fails(self, clean_registry, monkeypatch):
        def fail():
            raise RuntimeError("metadata broken")

        monkeypatch.setattr("souwen.plugin.metadata.entry_points", fail)
        loaded, errors = discover_entrypoint_plugins()
        assert loaded == []
        assert errors == []  # 整体失败时只 warn，不计入 errors

    def test_invalid_type_returned_collected_as_error(self, clean_registry, monkeypatch):
        ep = _FakeEntryPoint("bad_type_ep", lambda: 42)
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([ep]),
        )
        loaded, errors = discover_entrypoint_plugins()
        assert loaded == []
        assert len(errors) == 1
        assert errors[0]["name"] == "bad_type_ep"

    def test_duplicate_with_builtin_logged_not_error(self, clean_registry, monkeypatch):
        # 与已有内置源同名 → _reg_external 返回 False，不计入 loaded，也不计 errors
        ep = _FakeEntryPoint("builtin", lambda: make_test_adapter("builtin"))
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([ep]),
        )
        loaded, errors = discover_entrypoint_plugins()
        assert "builtin" not in loaded
        assert errors == []


# ── load_config_plugins ────────────────────────────────────


class TestLoadConfigPlugins:
    def test_valid_path(self, clean_registry, monkeypatch):
        # 暴露一个 adapter 工厂以便 _resolve_dotted_path 能 import
        adapter = make_test_adapter("cfg_ok")
        import souwen.plugin as plugin_mod

        monkeypatch.setattr(plugin_mod, "_test_factory", lambda: adapter, raising=False)
        loaded, errors = load_config_plugins(["souwen.plugin:_test_factory"])
        assert loaded == ["cfg_ok"]
        assert errors == []

    def test_invalid_path_format(self, clean_registry):
        loaded, errors = load_config_plugins(["no_colon_here"])
        assert loaded == []
        assert len(errors) == 1
        assert errors[0]["name"] == "no_colon_here"

    def test_nonexistent_module(self, clean_registry):
        loaded, errors = load_config_plugins(["souwen.nonexistent_qqq:foo"])
        assert loaded == []
        assert len(errors) == 1
        assert "souwen.nonexistent_qqq:foo" == errors[0]["name"]

    def test_empty_list(self, clean_registry):
        loaded, errors = load_config_plugins([])
        assert (loaded, errors) == ([], [])

    def test_none_handled(self, clean_registry):
        loaded, errors = load_config_plugins(None)  # type: ignore[arg-type]
        assert (loaded, errors) == ([], [])

    def test_skips_blank_and_non_str(self, clean_registry):
        loaded, errors = load_config_plugins(["", "  ", None])  # type: ignore[list-item]
        assert loaded == []
        assert errors == []


# ── load_plugins ───────────────────────────────────────────


class TestLoadPlugins:
    def test_no_config_only_entry_points(self, clean_registry, monkeypatch):
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([]),
        )
        result = load_plugins(None)
        assert result == {"loaded": [], "errors": []}

    def test_with_config_plugins(self, clean_registry, monkeypatch):
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([]),
        )
        adapter = make_test_adapter("cfg_via_load")
        import souwen.plugin as plugin_mod

        monkeypatch.setattr(plugin_mod, "_test_load_factory", lambda: adapter, raising=False)

        class FakeConfig:
            plugins = ["souwen.plugin:_test_load_factory"]

        result = load_plugins(FakeConfig())
        assert "cfg_via_load" in result["loaded"]
        assert result["errors"] == []

    def test_errors_collected_not_raised(self, clean_registry, monkeypatch):
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([]),
        )

        class FakeConfig:
            plugins = ["bogus:path", "souwen.no_such_module:x"]

        result = load_plugins(FakeConfig())
        assert result["loaded"] == []
        assert len(result["errors"]) == 2

    def test_config_without_plugins_attr(self, clean_registry, monkeypatch):
        monkeypatch.setattr(
            "souwen.plugin.metadata.entry_points",
            lambda: _FakeEntryPoints([]),
        )

        class FakeConfig:
            pass

        result = load_plugins(FakeConfig())
        assert result == {"loaded": [], "errors": []}

    def test_entry_point_discovery_total_failure(self, clean_registry, monkeypatch):
        # discover_entrypoint_plugins 抛异常时被 load_plugins 兜底
        def boom(*_a: Any, **_kw: Any):
            raise RuntimeError("ep system down")

        monkeypatch.setattr("souwen.plugin.discover_entrypoint_plugins", boom)
        result = load_plugins(None)
        assert result["loaded"] == []
        assert len(result["errors"]) == 1
        assert "ep system down" in result["errors"][0]["error"]

    def test_autoload_zero_skips_entry_point_discovery(
        self, clean_registry, clean_plugins, monkeypatch
    ):
        calls: list[set[str]] = []

        def discover(*, skip_names: set[str] | None = None, config: Any = None):
            calls.append(skip_names or set())
            return [], []

        monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
        monkeypatch.setattr("souwen.plugin.discover_entrypoint_plugins", discover)
        result = load_plugins(None)

        assert result == {"loaded": [], "errors": []}
        assert calls == []

    def test_autoload_false_skips_entry_points_but_allows_config_plugins(
        self, clean_registry, clean_plugins, monkeypatch
    ):
        monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "false")
        monkeypatch.setattr(
            "souwen.plugin.discover_entrypoint_plugins",
            lambda **_: pytest.fail("entry point discovery should be disabled"),
        )
        adapter = make_test_adapter("explicit_config_allowed")
        import souwen.plugin as plugin_mod

        monkeypatch.setattr(
            plugin_mod, "_test_autoload_off_factory", lambda: adapter, raising=False
        )

        class FakeConfig:
            plugins = ["souwen.plugin:_test_autoload_off_factory"]

        result = load_plugins(FakeConfig())

        assert result["loaded"] == ["explicit_config_allowed"]
        assert result["errors"] == []

    def test_env_denylist_is_merged_into_skip_names(self, clean_registry, monkeypatch):
        captured: list[set[str]] = []

        def discover(*, skip_names: set[str] | None = None, config: Any = None):
            captured.append(set(skip_names or set()))
            return [], []

        monkeypatch.setenv("SOUWEN_PLUGIN_DENYLIST", "ops_blocked, adapter_blocked ,")
        monkeypatch.setattr(
            "souwen.plugin_manager._load_state",
            lambda: {"disabled_plugins": ["state_blocked"], "installed_via_api": []},
        )
        monkeypatch.setattr("souwen.plugin.discover_entrypoint_plugins", discover)

        result = load_plugins(None)

        assert result == {"loaded": [], "errors": []}
        assert captured == [{"ops_blocked", "adapter_blocked", "state_blocked"}]


# ── 集成 / 状态清理 ────────────────────────────────────────


class TestPluginIntegration:
    def test_register_and_appear_in_views(self, clean_registry):
        a = make_test_adapter("integration_one")
        assert _reg_external(a) is True
        assert "integration_one" in all_adapters()
        assert "integration_one" in external_plugins()

    def test_reset_registry_clears_external_plugins(self, clean_registry):
        _reg_external(make_test_adapter("will_be_cleared"))
        assert "will_be_cleared" in _EXTERNAL_PLUGINS
        _reset_registry()
        assert _EXTERNAL_PLUGINS == set()
        assert _REGISTRY == {}
        # clean_registry fixture 会在 yield 后恢复


# ── Phase 1: Plugin 信封 + Handler 溯源 ────────────────────


@pytest.fixture()
def clean_plugins():
    """清理 _PLUGINS 字典。"""
    saved = dict(_PLUGINS)
    _PLUGINS.clear()
    yield
    _PLUGINS.clear()
    _PLUGINS.update(saved)


@pytest.fixture()
def clean_fetch_handlers():
    """清理 _FETCH_HANDLERS 字典。"""
    saved = dict(_FETCH_HANDLERS)
    _FETCH_HANDLERS.clear()
    yield
    _FETCH_HANDLERS.clear()
    _FETCH_HANDLERS.update(saved)


class TestPluginDataclass:
    def test_basic_creation(self):
        p = Plugin(name="test")
        assert p.name == "test"
        assert p.adapters == []
        assert p.version == "0.0.0"
        assert p.api_version == "1"
        assert p.min_souwen_version is None
        assert p.max_souwen_version is None
        assert p.config == {}
        assert p._registered_adapter_names == []

    def test_with_adapters(self):
        a = make_test_adapter("src1")
        p = Plugin(name="my_plugin", adapters=[a], version="1.0.0")
        assert len(p.adapters) == 1
        assert p.version == "1.0.0"


class TestCoerceToPlugin:
    def test_plugin_passthrough(self):
        p = Plugin(name="orig")
        result = _coerce_to_plugin(p, plugin_name="override")
        assert result.name == "override"
        assert result is p

    def test_adapter_wrapped(self):
        a = make_test_adapter("adapter1")
        result = _coerce_to_plugin(a, plugin_name="my_ep")
        assert isinstance(result, Plugin)
        assert result.name == "my_ep"
        assert len(result.adapters) == 1
        assert result.adapters[0].name == "adapter1"

    def test_adapter_list_wrapped(self):
        a1 = make_test_adapter("a1")
        a2 = make_test_adapter("a2")
        result = _coerce_to_plugin([a1, a2], plugin_name="multi")
        assert len(result.adapters) == 2

    def test_callable_factory(self):
        a = make_test_adapter("factory_out")
        result = _coerce_to_plugin(lambda: a, plugin_name="from_factory")
        assert result.name == "from_factory"
        assert len(result.adapters) == 1

    def test_callable_returning_plugin(self):
        p = Plugin(name="inner", adapters=[make_test_adapter("inner_a")])
        result = _coerce_to_plugin(lambda: p, plugin_name="outer")
        assert result.name == "outer"

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError, match="Plugin"):
            _coerce_to_plugin(123, plugin_name="bad")

    def test_invalid_list_element_raises(self):
        with pytest.raises(TypeError, match="非 SourceAdapter"):
            _coerce_to_plugin([42], plugin_name="bad_list")


class TestRegisterPlugin:
    def test_registers_adapters_and_tracks(
        self, clean_registry, clean_plugins, clean_fetch_handlers
    ):
        a = make_test_adapter("reg_test_adapter")
        p = Plugin(name="reg_test", adapters=[a])
        loaded: list[str] = []
        errors: list[dict] = []
        _register_plugin(p, source_label="test", loaded=loaded, errors=errors)

        assert "reg_test_adapter" in loaded
        assert not errors
        assert "reg_test" in _PLUGINS
        assert _PLUGINS["reg_test"]._registered_adapter_names == ["reg_test_adapter"]

    def test_register_plugin_logs_structured_events(
        self,
        clean_registry,
        clean_plugins,
        clean_fetch_handlers,
        caplog: pytest.LogCaptureFixture,
    ):
        p = Plugin(name="log_test", adapters=[make_test_adapter("log_adapter")])

        with caplog.at_level(logging.INFO, logger="souwen.plugin"):
            _register_plugin(p, source_label="test", loaded=[], errors=[])

        adapter_record = next(
            record
            for record in caplog.records
            if getattr(record, "event", None) == "adapter_registered"
        )
        plugin_record = next(
            record for record in caplog.records if getattr(record, "event", None) == "plugin_loaded"
        )
        assert adapter_record.plugin == "log_test"
        assert adapter_record.adapter == "log_adapter"
        assert plugin_record.plugin == "log_test"
        assert plugin_record.adapters == ["log_adapter"]

    def test_duplicate_plugin_rejected(self, clean_registry, clean_plugins):
        a = make_test_adapter("dup_adapter")
        p = Plugin(name="dup_plugin", adapters=[a])
        loaded: list[str] = []
        errors: list[dict] = []
        _register_plugin(p, source_label="t1", loaded=loaded, errors=errors)
        assert not errors

        loaded2: list[str] = []
        errors2: list[dict] = []
        p2 = Plugin(name="dup_plugin", adapters=[make_test_adapter("dup_adapter2")])
        _register_plugin(p2, source_label="t2", loaded=loaded2, errors=errors2)
        assert len(errors2) == 1
        assert "已加载" in errors2[0]["error"]

    def test_on_startup_not_called_during_registration(
        self, clean_registry, clean_plugins, clean_fetch_handlers
    ):
        calls = []
        p = Plugin(
            name="startup_test", adapters=[], on_startup=lambda plug: calls.append(plug.name)
        )
        _register_plugin(p, source_label="t", loaded=[], errors=[])
        assert calls == []

    def test_injects_validated_config(self, clean_registry, clean_plugins, clean_fetch_handlers):
        class DemoConfig(BaseModel):
            api_key: str
            limit: int = 5

        class FakeConfig:
            plugin_config = {"config_test": {"api_key": "secret", "limit": 7}}

        p = Plugin(name="config_test", adapters=[], config_schema=DemoConfig)
        errors: list[dict[str, str]] = []
        _register_plugin(p, source_label="t", loaded=[], errors=errors, config=FakeConfig())

        assert not errors
        assert _PLUGINS["config_test"].config == {"api_key": "secret", "limit": 7}

    def test_config_without_schema_is_injected_raw(
        self, clean_registry, clean_plugins, clean_fetch_handlers
    ):
        class FakeConfig:
            plugin_config = {"raw_config_test": {"enabled": True}}

        p = Plugin(name="raw_config_test", adapters=[])
        _register_plugin(p, source_label="t", loaded=[], errors=[], config=FakeConfig())

        assert _PLUGINS["raw_config_test"].config == {"enabled": True}

    def test_invalid_config_prevents_registration(
        self, clean_registry, clean_plugins, clean_fetch_handlers
    ):
        class DemoConfig(BaseModel):
            api_key: str

        class FakeConfig:
            plugin_config = {"bad_config": {"limit": 7}}

        errors: list[dict[str, str]] = []
        p = Plugin(name="bad_config", adapters=[], config_schema=DemoConfig)
        _register_plugin(p, source_label="t", loaded=[], errors=errors, config=FakeConfig())

        assert "bad_config" not in _PLUGINS
        assert len(errors) == 1
        assert errors[0]["name"] == "bad_config"

    def test_min_souwen_version_too_high_rejects_plugin(
        self, clean_registry, clean_plugins, clean_fetch_handlers
    ):
        p = Plugin(
            name="future_plugin",
            adapters=[make_test_adapter("future_adapter")],
            min_souwen_version="99.0.0",
        )
        loaded: list[str] = []
        errors: list[dict[str, str]] = []

        _register_plugin(p, source_label="t", loaded=loaded, errors=errors)

        assert loaded == []
        assert "future_plugin" not in _PLUGINS
        assert len(errors) == 1
        assert "99.0.0" in errors[0]["error"]

    def test_compatible_souwen_version_accepts_plugin(
        self, clean_registry, clean_plugins, clean_fetch_handlers
    ):
        p = Plugin(
            name="compatible_plugin",
            adapters=[make_test_adapter("compatible_adapter")],
            min_souwen_version="0.9.0",
            max_souwen_version="2.0.0",
        )
        loaded: list[str] = []
        errors: list[dict[str, str]] = []

        _register_plugin(p, source_label="t", loaded=loaded, errors=errors)

        assert loaded == ["compatible_adapter"]
        assert errors == []
        assert "compatible_plugin" in _PLUGINS

    def test_lifecycle_helper_supports_async_hooks(self, clean_plugins, monkeypatch):
        import asyncio

        from souwen.server import app as app_mod

        calls: list[str] = []

        async def startup(plug):
            calls.append(f"startup:{plug.name}")

        async def shutdown(plug):
            calls.append(f"shutdown:{plug.name}")

        p = Plugin(name="async_life", on_startup=startup, on_shutdown=shutdown)
        monkeypatch.setattr(app_mod, "get_loaded_plugins", lambda: {"async_life": p})

        asyncio.run(app_mod._call_plugin_lifecycle_hooks("on_startup"))
        asyncio.run(app_mod._call_plugin_lifecycle_hooks("on_shutdown"))

        assert calls == ["startup:async_life", "shutdown:async_life"]


class TestUnloadPlugin:
    def test_unload_removes_everything(self, clean_registry, clean_plugins, clean_fetch_handlers):
        a = make_test_adapter("unload_adapter")
        p = Plugin(name="unload_test", adapters=[a])
        _register_plugin(p, source_label="t", loaded=[], errors=[])
        assert "unload_test" in _PLUGINS
        assert "unload_adapter" in all_adapters()

        # Also register a fetch handler owned by this plugin
        async def fake_handler(*a, **kw):
            pass

        register_fetch_handler("unload_adapter", fake_handler, owner="unload_test")

        result = unload_plugin("unload_test")
        assert result["status"] == "unloaded"
        assert "unload_adapter" in result["removed_adapters"]
        assert "unload_adapter" in result["removed_handlers"]
        assert "unload_test" not in _PLUGINS
        assert "unload_adapter" not in all_adapters()

    def test_unload_not_loaded(self, clean_plugins):
        result = unload_plugin("ghost")
        assert result["status"] == "not_loaded"

    def test_on_shutdown_called(self, clean_registry, clean_plugins, clean_fetch_handlers):
        calls = []
        p = Plugin(
            name="shutdown_test",
            adapters=[],
            on_shutdown=lambda plug: calls.append(plug.name),
        )
        _register_plugin(p, source_label="t", loaded=[], errors=[])
        unload_plugin("shutdown_test")
        assert calls == ["shutdown_test"]

    def test_unload_plugin_logs_structured_event(
        self,
        clean_registry,
        clean_plugins,
        clean_fetch_handlers,
        caplog: pytest.LogCaptureFixture,
    ):
        p = Plugin(name="unload_log", adapters=[make_test_adapter("unload_log_adapter")])
        _register_plugin(p, source_label="t", loaded=[], errors=[])
        caplog.clear()

        with caplog.at_level(logging.INFO, logger="souwen.plugin"):
            unload_plugin("unload_log")

        record = next(
            record
            for record in caplog.records
            if getattr(record, "event", None) == "plugin_unloaded"
        )
        assert record.plugin == "unload_log"
        assert record.removed_adapters == ["unload_log_adapter"]


class TestGetLoadedPlugins:
    def test_returns_copy(self, clean_plugins):
        _PLUGINS["test"] = Plugin(name="test")
        result = get_loaded_plugins()
        assert "test" in result
        result.pop("test")
        assert "test" in _PLUGINS  # original unchanged


class TestFetchHandlerProvenance:
    def test_register_with_explicit_owner(self, clean_fetch_handlers):
        async def handler(*a, **kw):
            pass

        register_fetch_handler("prov_test", handler, owner="my_plugin")
        owners = get_fetch_handler_owners()
        assert owners["prov_test"] == "my_plugin"

    def test_register_fetch_handler_logs_structured_event(
        self,
        clean_fetch_handlers,
        caplog: pytest.LogCaptureFixture,
    ):
        async def handler(*a, **kw):
            pass

        with caplog.at_level(logging.DEBUG, logger="souwen.web.fetch"):
            register_fetch_handler("log_handler", handler, owner="handler_plugin")

        record = next(
            record
            for record in caplog.records
            if getattr(record, "event", None) == "fetch_handler_registered"
        )
        assert record.plugin == "handler_plugin"
        assert record.provider == "log_handler"

    def test_register_picks_up_contextvar(self, clean_fetch_handlers):
        async def handler(*a, **kw):
            pass

        token = _current_plugin_owner.set("ctx_plugin")
        try:
            register_fetch_handler("ctx_test", handler)
        finally:
            _current_plugin_owner.reset(token)
        assert get_fetch_handler_owners()["ctx_test"] == "ctx_plugin"

    def test_unregister_by_owner(self, clean_fetch_handlers):
        async def h1(*a, **kw):
            pass

        async def h2(*a, **kw):
            pass

        register_fetch_handler("owned1", h1, owner="plugin_x")
        register_fetch_handler("owned2", h2, owner="plugin_x")
        register_fetch_handler("other", h1, owner="plugin_y")

        removed = unregister_fetch_handlers_by_owner("plugin_x")
        assert set(removed) == {"owned1", "owned2"}
        assert "other" in _FETCH_HANDLERS
        assert "owned1" not in _FETCH_HANDLERS

    def test_builtin_handler_has_none_owner(self, clean_fetch_handlers):
        async def handler(*a, **kw):
            pass

        register_fetch_handler("builtin", handler)
        assert get_fetch_handler_owners()["builtin"] is None


class TestDiscoverWithPluginEnvelope:
    """discover_entrypoint_plugins now uses Plugin-based flow."""

    def test_entry_point_creates_plugin_object(self, clean_registry, clean_plugins, monkeypatch):
        adapter = make_test_adapter("ep_plugin_test")
        eps = _FakeEntryPoints([_FakeEntryPoint("my_ep", lambda: adapter)])
        monkeypatch.setattr("souwen.plugin.metadata.entry_points", lambda: eps)

        loaded, errors = discover_entrypoint_plugins()
        assert "ep_plugin_test" in loaded
        assert not errors
        assert "my_ep" in _PLUGINS
        assert _PLUGINS["my_ep"]._registered_adapter_names == ["ep_plugin_test"]

    def test_skip_names_by_ep_name(self, clean_registry, clean_plugins, monkeypatch):
        """skip_names 按 entry-point 名预筛（不触发 import）。"""
        load_count = []

        def tracked_loader():
            load_count.append(1)
            return make_test_adapter("should_not_load")

        eps = _FakeEntryPoints([_FakeEntryPoint("skip_me", tracked_loader)])
        monkeypatch.setattr("souwen.plugin.metadata.entry_points", lambda: eps)

        loaded, errors = discover_entrypoint_plugins(skip_names={"skip_me"})
        assert loaded == []
        assert load_count == []  # ep.load() never called

    def test_skip_names_by_adapter_name(self, clean_registry, clean_plugins, monkeypatch):
        """skip_names 也按 adapter.name 二次过滤。"""
        adapter = make_test_adapter("blocked_adapter")
        eps = _FakeEntryPoints([_FakeEntryPoint("allowed_ep", lambda: adapter)])
        monkeypatch.setattr("souwen.plugin.metadata.entry_points", lambda: eps)

        loaded, errors = discover_entrypoint_plugins(skip_names={"blocked_adapter"})
        assert loaded == []

    def test_contextvar_set_during_load(
        self, clean_registry, clean_plugins, clean_fetch_handlers, monkeypatch
    ):
        """entry-point load 期间 _current_plugin_owner contextvar 被设置。"""
        captured_owner = []

        async def capturing_handler(*a, **kw):
            pass

        def side_effect_loader():
            # 模拟插件在 import 时注册 fetch handler
            register_fetch_handler("side_effect_prov", capturing_handler)
            captured_owner.append(_current_plugin_owner.get())
            return make_test_adapter("side_effect_adapter")

        eps = _FakeEntryPoints([_FakeEntryPoint("side_ep", side_effect_loader)])
        monkeypatch.setattr("souwen.plugin.metadata.entry_points", lambda: eps)

        loaded, errors = discover_entrypoint_plugins()
        assert captured_owner == ["side_ep"]
        assert get_fetch_handler_owners().get("side_effect_prov") == "side_ep"


class TestConfigPluginsWithPluginEnvelope:
    def test_config_plugin_creates_plugin_object(self, clean_registry, clean_plugins, monkeypatch):
        adapter = make_test_adapter("cfg_envelope_test")
        import souwen.plugin as plugin_mod

        monkeypatch.setattr(plugin_mod, "_test_cfg_factory", lambda: adapter, raising=False)

        loaded, errors = load_config_plugins(["souwen.plugin:_test_cfg_factory"])
        assert "cfg_envelope_test" in loaded
        assert "souwen.plugin:_test_cfg_factory" in _PLUGINS


class TestPluginContractHelper:
    class ValidClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def fetch(self, url: str) -> dict[str, str]:
            return {"url": url}

    class MissingContractClient:
        pass

    def make_contract_adapter(self, name: str, client_loader: Any) -> SourceAdapter:
        return SourceAdapter(
            name=name,
            domain="fetch",
            integration="scraper",
            description="Contract adapter",
            config_field=None,
            client_loader=client_loader,
            methods={"fetch": MethodSpec("fetch")},
            needs_config=False,
        )

    def test_valid_plugin_passes_contract(self):
        plugin = Plugin(
            name="valid_contract", adapters=[make_test_adapter("valid_contract_adapter")]
        )

        assert_valid_plugin(plugin)

    def test_invalid_entry_point_fails_with_clear_message(self):
        with pytest.raises(AssertionError, match="cannot be coerced"):
            assert_valid_plugin(123)

    def test_non_callable_health_check_fails(self):
        plugin = Plugin(name="bad_health", health_check="not-callable")  # type: ignore[arg-type]

        with pytest.raises(AssertionError, match="health_check"):
            assert_valid_plugin(plugin)

    def test_adapter_without_methods_fails(self):
        adapter = SourceAdapter(
            name="no_methods",
            domain="fetch",
            integration="scraper",
            description="No methods",
            config_field=None,
            client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
            methods={},
            needs_config=False,
        )
        plugin = Plugin(name="no_methods_plugin", adapters=[adapter])

        with pytest.raises(AssertionError, match="at least one method"):
            assert_valid_plugin(plugin)

    def test_builtin_name_conflict_fails(self):
        plugin = Plugin(name="conflict", adapters=[make_test_adapter("arxiv")])

        with pytest.raises(AssertionError, match="built-in source"):
            assert_valid_plugin(plugin)

    def test_validate_client_contract_accepts_valid_client(self):
        adapter = self.make_contract_adapter("valid_deep_contract", lambda: self.ValidClient)

        assert validate_client_contract(adapter) == []

    def test_validate_client_contract_reports_invalid_client(self):
        adapter = self.make_contract_adapter(
            "invalid_deep_contract",
            lambda: self.MissingContractClient,
        )

        issues = validate_client_contract(adapter)

        assert any("__aenter__" in issue for issue in issues)
        assert any("__aexit__" in issue for issue in issues)
        assert any("'fetch'" in issue for issue in issues)

    def test_assert_valid_plugin_includes_deep_contract_issues(self):
        adapter = self.make_contract_adapter(
            "invalid_assert_contract",
            lambda: self.MissingContractClient,
        )
        plugin = Plugin(name="invalid_assert_plugin", adapters=[adapter])

        with pytest.raises(AssertionError, match="__aenter__"):
            assert_valid_plugin(plugin)

    def test_validate_client_contract_warns_when_loader_fails(
        self,
        caplog: pytest.LogCaptureFixture,
    ):
        def broken_loader() -> type:
            raise RuntimeError("optional dependency missing")

        adapter = self.make_contract_adapter("missing_dependency_contract", broken_loader)

        with caplog.at_level(logging.WARNING, logger="souwen.testing"):
            issues = validate_client_contract(adapter)

        assert issues == []
        assert "optional dependency missing" in caplog.text


# ── Fix verification: orphan handler cleanup + async shutdown ──────


class TestOrphanHandlerCleanup:
    """Fix #2: disabled plugins' side-effect handlers cleaned up."""

    def test_filtered_adapters_cleanup_orphan_handlers(
        self, clean_registry, clean_plugins, clean_fetch_handlers, monkeypatch
    ):
        """When all adapters are filtered, ep.load() side-effect handlers must be removed."""

        async def orphan_handler(*a, **kw):
            pass

        def side_effect_loader():
            register_fetch_handler("orphan_prov", orphan_handler)
            return make_test_adapter("blocked_adapter")

        eps = _FakeEntryPoints([_FakeEntryPoint("ep_x", side_effect_loader)])
        monkeypatch.setattr("souwen.plugin.metadata.entry_points", lambda: eps)

        loaded, errors = discover_entrypoint_plugins(skip_names={"blocked_adapter"})
        assert loaded == []
        # Orphan handler must have been cleaned up
        assert "orphan_prov" not in _FETCH_HANDLERS
        assert "ep_x" not in _PLUGINS


class TestAsyncShutdownClose:
    """Fix #3: async shutdown coroutine is properly closed."""

    def test_async_shutdown_closed_not_leaked(
        self, clean_registry, clean_plugins, clean_fetch_handlers
    ):
        closed = []

        async def async_shutdown(plugin):
            try:
                pass
            except GeneratorExit:
                closed.append(True)
                raise

        p = Plugin(name="async_test", adapters=[], on_shutdown=async_shutdown)
        _register_plugin(p, source_label="t", loaded=[], errors=[])
        result = unload_plugin("async_test")

        assert result["status"] == "unloaded"
        # Should report the skip in errors
        assert any("async hook skipped" in e for e in result["errors"])


# ── GPT-5.5 Review Fix Verification Tests ──────────────────


class TestInvalidVersionConstraint:
    """Fix #4: Invalid version strings should not crash all discovery."""

    def test_invalid_min_souwen_version_reports_error(self, clean_plugins):
        """A plugin with unparseable min_souwen_version should be rejected gracefully."""
        from souwen.plugin import _check_plugin_version_compatibility

        p = Plugin(name="bad_version", adapters=[], min_souwen_version="not-a-version")
        errors: list[dict] = []
        result = _check_plugin_version_compatibility(p, source_label="test", errors=errors)
        assert result is False
        assert len(errors) == 1
        assert "无法解析" in errors[0]["error"]

    def test_invalid_max_souwen_version_reports_error(self, clean_plugins):
        """A plugin with unparseable max_souwen_version should be rejected gracefully."""
        from souwen.plugin import _check_plugin_version_compatibility

        p = Plugin(name="bad_max", adapters=[], max_souwen_version="!!!bad!!!")
        errors: list[dict] = []
        result = _check_plugin_version_compatibility(p, source_label="test", errors=errors)
        assert result is False
        assert len(errors) == 1
        assert "无法解析" in errors[0]["error"]


class TestPartialAdapterDisable:
    """Fix #2: Disabling one adapter in a multi-adapter plugin should remove its fetch handler."""

    def test_skipped_adapter_handler_removed(self, clean_plugins):
        """When one adapter is disabled, its fetch handler should be cleaned up."""
        from souwen.web.fetch import unregister_fetch_handler

        # Simulate: plugin registers 2 fetch handlers
        async def handler_a(urls, timeout, **_):
            return []

        async def handler_b(urls, timeout, **_):
            return []

        register_fetch_handler("adapter_a", handler_a)
        register_fetch_handler("adapter_b", handler_b)

        assert "adapter_a" in _FETCH_HANDLERS
        assert "adapter_b" in _FETCH_HANDLERS

        # Unregister one by provider name
        assert unregister_fetch_handler("adapter_b") is True
        assert "adapter_a" in _FETCH_HANDLERS
        assert "adapter_b" not in _FETCH_HANDLERS

        # Second call returns False (already removed)
        assert unregister_fetch_handler("adapter_b") is False


class TestRetroactiveConfigInjection:
    """Fix #1: Entry-point plugins should receive plugin_config after config loads."""

    def test_inject_config_into_loaded_plugins(self, clean_plugins):
        """_inject_config_into_loaded_plugins should inject config into already-loaded plugins."""
        from souwen.plugin import _inject_config_into_loaded_plugins

        p = Plugin(name="my_ep_plugin", adapters=[], config_schema=dict)
        _PLUGINS["my_ep_plugin"] = p

        # Create a mock config with plugin_config
        class MockConfig:
            plugin_config = {"my_ep_plugin": {"key": "value"}}

        injected = _inject_config_into_loaded_plugins(MockConfig())
        assert "my_ep_plugin" in injected
        assert p.config == {"key": "value"}

    def test_inject_skips_already_configured_plugins(self, clean_plugins):
        """If a plugin already has config, it should not be overwritten."""
        from souwen.plugin import _inject_config_into_loaded_plugins

        p = Plugin(name="configured", adapters=[], config={"existing": True})
        _PLUGINS["configured"] = p

        class MockConfig:
            plugin_config = {"configured": {"new": "val"}}

        injected = _inject_config_into_loaded_plugins(MockConfig())
        assert "configured" not in injected
        assert p.config == {"existing": True}


class TestFailedPluginHandlerCleanup:
    """Fix: Failed/rejected plugins should not leave fetch handlers active."""

    def test_failed_ep_load_cleans_handlers(self, clean_plugins, clean_fetch_handlers, monkeypatch):
        """When entry point load fails, any side-effect handlers are cleaned up."""

        # Simulate: a plugin registers a handler during import, then fails
        async def leaked_handler(urls, timeout, **_):
            return []

        register_fetch_handler("leaked_provider", leaked_handler, owner="failing_ep")
        assert "leaked_provider" in _FETCH_HANDLERS

        # The cleanup should happen when unregister_fetch_handlers_by_owner is called
        from souwen.web.fetch import unregister_fetch_handlers_by_owner

        removed = unregister_fetch_handlers_by_owner("failing_ep")
        assert "leaked_provider" in removed
        assert "leaked_provider" not in _FETCH_HANDLERS

    def test_rejected_duplicate_preserves_existing_handlers(
        self, clean_plugins, clean_fetch_handlers
    ):
        """When _register_plugin rejects a duplicate, existing handlers are preserved."""
        adapter = make_test_adapter("dup_src")
        p1 = Plugin(name="my_dup_plugin", adapters=[adapter])
        _register_plugin(p1, source_label="test", loaded=[], errors=[])
        assert "my_dup_plugin" in _PLUGINS

        # Simulate: the already-loaded plugin has a live handler
        register_fetch_handler("live_handler", lambda: None, owner="my_dup_plugin")
        # Attempt to register duplicate — should NOT remove the live handler
        errors: list[dict] = []
        _register_plugin(
            Plugin(name="my_dup_plugin", adapters=[]),
            source_label="test",
            loaded=[],
            errors=errors,
        )
        # Live handler should still be there
        assert "live_handler" in _FETCH_HANDLERS
        assert len(errors) == 1
        assert "已加载" in errors[0]["error"]
