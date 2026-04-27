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

from typing import Any

import pytest

from souwen.plugin import (
    _coerce_to_adapters,
    _resolve_dotted_path,
    discover_entrypoint_plugins,
    load_config_plugins,
    load_plugins,
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
        with pytest.raises(TypeError, match="必须是 SourceAdapter"):
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
