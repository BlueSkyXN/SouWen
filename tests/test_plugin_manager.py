"""tests/test_plugin_manager.py — 插件管理器测试"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from souwen.plugin_manager import (
    ALLOWED_PACKAGES,
    PLUGIN_CATALOG,
    PluginInfo,
    _PACKAGE_NAME_RE,
    _catalog_by_name,
    _catalog_packages,
    _discover_catalog_entries,
    _load_state,
    _save_state,
    disable_plugin,
    disable_plugin_async,
    enable_plugin,
    get_plugin_info,
    install_plugin,
    is_plugin_install_enabled,
    is_restart_required,
    list_plugins,
    reload_plugins,
    uninstall_plugin,
)


@pytest.fixture()
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect plugin state file to a temp directory."""
    state_path = tmp_path / "plugins.state.json"
    monkeypatch.setattr("souwen.plugin_manager._get_state_path", lambda: state_path)
    monkeypatch.setattr("souwen.plugin_manager._restart_required", False)
    return state_path


class _DummyAdapter:
    def __init__(self, description: str = "Dummy plugin") -> None:
        self.description = description


class _FakeCatalogEntryPoint:
    def __init__(self, name: str, loader: Any) -> None:
        self.name = name
        self._loader = loader

    def load(self) -> Any:
        return self._loader()


class _FakeCatalogEntryPoints:
    def __init__(self, eps: list[_FakeCatalogEntryPoint]) -> None:
        self._eps = eps

    def select(self, *, group: str) -> list[_FakeCatalogEntryPoint]:
        if group == "souwen.plugin_catalog":
            return list(self._eps)
        return []


class TestPluginInfo:
    def test_model_creation_with_all_fields(self) -> None:
        info = PluginInfo(
            name="superweb2pdf",
            package="superweb2pdf",
            version="1.2.3",
            status="loaded",
            source="entry_point",
            first_party=True,
            description="PDF plugin",
            error=None,
            source_adapters=["superweb2pdf"],
            fetch_handlers=["superweb2pdf"],
            restart_required=True,
        )

        assert info.name == "superweb2pdf"
        assert info.package == "superweb2pdf"
        assert info.version == "1.2.3"
        assert info.status == "loaded"
        assert info.source == "entry_point"
        assert info.first_party is True
        assert info.description == "PDF plugin"
        assert info.error is None
        assert info.source_adapters == ["superweb2pdf"]
        assert info.fetch_handlers == ["superweb2pdf"]
        assert info.restart_required is True

    def test_model_defaults(self) -> None:
        info = PluginInfo(name="example", status="available", source="catalog")

        assert info.package is None
        assert info.version is None
        assert info.first_party is False
        assert info.description == ""
        assert info.error is None
        assert info.source_adapters == []
        assert info.fetch_handlers == []
        assert info.restart_required is False

    def test_mutable_defaults_are_isolated(self) -> None:
        first = PluginInfo(name="first", status="loaded", source="config_path")
        second = PluginInfo(name="second", status="loaded", source="config_path")

        first.source_adapters.append("first")
        first.fetch_handlers.append("first")

        assert second.source_adapters == []
        assert second.fetch_handlers == []


class TestCatalogDiscovery:
    def test_dynamic_catalog_entries_are_discovered(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entry = {
            "name": "dynamic_demo",
            "package": "dynamic-demo",
            "description": "Dynamic demo",
            "entry_point": "dynamic_demo",
            "first_party": "false",
        }
        monkeypatch.setattr(
            "souwen.plugin_manager.metadata.entry_points",
            lambda: _FakeCatalogEntryPoints(
                [_FakeCatalogEntryPoint("dynamic_demo", lambda: entry)]
            ),
        )

        assert _discover_catalog_entries() == [entry]
        assert _catalog_by_name()["dynamic_demo"] == entry
        assert "dynamic-demo" in _catalog_packages()

    def test_static_catalog_overrides_dynamic_entries(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        static = PLUGIN_CATALOG[0]
        dynamic_override = {
            "name": static["name"],
            "package": "different-package",
            "description": "Dynamic should not win",
            "entry_point": "different_entry_point",
            "first_party": "false",
        }
        monkeypatch.setattr(
            "souwen.plugin_manager.metadata.entry_points",
            lambda: _FakeCatalogEntryPoints(
                [_FakeCatalogEntryPoint(static["name"], lambda: dynamic_override)]
            ),
        )

        assert _catalog_by_name()[static["name"]] == static

    def test_malformed_catalog_entries_are_warned_and_skipped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def boom() -> dict[str, str]:
            raise RuntimeError("broken catalog")

        monkeypatch.setattr(
            "souwen.plugin_manager.metadata.entry_points",
            lambda: _FakeCatalogEntryPoints(
                [
                    _FakeCatalogEntryPoint("bad_type", lambda: ["not", "a", "dict"]),
                    _FakeCatalogEntryPoint("missing", lambda: {"name": "missing"}),
                    _FakeCatalogEntryPoint(
                        "bad_value",
                        lambda: {
                            "name": "bad_value",
                            "package": 123,
                            "description": "Bad value",
                            "entry_point": "bad_value",
                        },
                    ),
                    _FakeCatalogEntryPoint("boom", boom),
                ]
            ),
        )

        with caplog.at_level(logging.WARNING, logger="souwen.plugin_manager"):
            assert _discover_catalog_entries() == []

        messages = "\n".join(record.getMessage() for record in caplog.records)
        assert "bad_type" in messages
        assert "missing" in messages
        assert "bad_value" in messages
        assert "boom" in messages


class TestExamplePluginLogging:
    def _load_example_plugin(
        self,
        *,
        package_name: str,
        handler_module: types.ModuleType | None = None,
        hide_handler: bool = False,
    ) -> None:
        init_path = (
            Path(__file__).resolve().parents[1]
            / "examples/minimal-plugin/souwen_example_plugin/__init__.py"
        )
        search_path = init_path.parent / "__missing_handler__" if hide_handler else init_path.parent
        spec = importlib.util.spec_from_file_location(
            package_name,
            init_path,
            submodule_search_locations=[str(search_path)],
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = module
        if handler_module is not None:
            sys.modules[f"{package_name}.handler"] = handler_module
        try:
            spec.loader.exec_module(module)
        finally:
            for key in list(sys.modules):
                if key == package_name or key.startswith(f"{package_name}."):
                    sys.modules.pop(key, None)

    def test_optional_handler_import_error_is_logged(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.WARNING):
            self._load_example_plugin(
                package_name="_souwen_example_plugin_missing_handler",
                hide_handler=True,
            )

        assert "可选 fetch handler 注册不可用" in caplog.text

    def test_optional_handler_runtime_error_is_logged(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        handler = types.ModuleType("_souwen_example_plugin_broken_handler.handler")

        def register() -> None:
            raise RuntimeError("handler boom")

        handler.register = register  # type: ignore[attr-defined]

        with caplog.at_level(logging.WARNING):
            self._load_example_plugin(
                package_name="_souwen_example_plugin_broken_handler",
                handler_module=handler,
            )

        assert "可选 fetch handler 注册失败" in caplog.text
        assert "handler boom" in caplog.text


class TestStateFile:
    def test_load_state_with_missing_file_creates_default(self, state_dir: Path) -> None:
        assert not state_dir.exists()

        state = _load_state()

        assert state == {"disabled_plugins": [], "installed_via_api": []}
        assert json.loads(state_dir.read_text(encoding="utf-8")) == state

    def test_save_and_load_state_roundtrip(self, state_dir: Path) -> None:
        expected = {
            "disabled_plugins": ["beta", "alpha", "alpha"],
            "installed_via_api": ["superweb2pdf"],
        }

        _save_state(expected)

        assert _load_state() == {
            "disabled_plugins": ["alpha", "beta"],
            "installed_via_api": ["superweb2pdf"],
        }

    def test_state_normalization_with_dirty_data(self, state_dir: Path) -> None:
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        state_dir.write_text(
            json.dumps(
                {
                    "disabled_plugins": ["beta", "", "alpha", "alpha", 7],
                    "installed_via_api": "not-a-list",
                    "unknown": ["ignored"],
                }
            ),
            encoding="utf-8",
        )

        assert _load_state() == {
            "disabled_plugins": ["7", "alpha", "beta"],
            "installed_via_api": [],
        }

    def test_load_state_with_invalid_json_returns_default(self, state_dir: Path) -> None:
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        state_dir.write_text("{broken json", encoding="utf-8")

        assert _load_state() == {"disabled_plugins": [], "installed_via_api": []}

    def test_atomic_write_does_not_corrupt_existing_file(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original = {"disabled_plugins": ["original"], "installed_via_api": []}
        _save_state(original)

        def broken_dump(obj: Any, fp: Any, *args: Any, **kwargs: Any) -> None:
            fp.write('{"disabled_plugins": ["partial"]')
            raise OSError("simulated partial write")

        monkeypatch.setattr("souwen.plugin_manager.json.dump", broken_dump)

        _save_state({"disabled_plugins": ["new"], "installed_via_api": ["superweb2pdf"]})

        assert json.loads(state_dir.read_text(encoding="utf-8")) == original
        assert not list(state_dir.parent.glob(f".{state_dir.name}.*.tmp"))


class TestListPlugins:
    def test_no_external_plugins_returns_catalog_entries_as_available(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [])
        monkeypatch.setattr("souwen.plugin_manager.all_adapters", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handler_owners", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_loaded_plugins", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)
        monkeypatch.setattr("souwen.plugin_manager._package_version", lambda package: None)

        plugins = list_plugins()

        catalog_names = {item["name"] for item in PLUGIN_CATALOG}
        assert catalog_names <= {plugin.name for plugin in plugins}
        assert all(plugin.status == "available" for plugin in plugins)
        assert all(plugin.source == "catalog" for plugin in plugins)

    def test_external_plugins_are_reported_as_loaded(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        clean_registry: None,
    ) -> None:
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: ["external_demo"])
        monkeypatch.setattr(
            "souwen.plugin_manager.all_adapters",
            lambda: {"external_demo": _DummyAdapter("External demo")},
        )
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handler_owners", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_loaded_plugins", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        plugin = next(item for item in list_plugins() if item.name == "external_demo")

        assert plugin.status == "loaded"
        assert plugin.source == "config_path"
        assert plugin.description == "External demo"
        assert plugin.source_adapters == ["external_demo"]

    def test_external_catalog_plugin_uses_entry_point_source(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        catalog_name = PLUGIN_CATALOG[0]["name"]
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [catalog_name])
        monkeypatch.setattr(
            "souwen.plugin_manager.all_adapters",
            lambda: {catalog_name: _DummyAdapter("Loaded catalog plugin")},
        )
        monkeypatch.setattr(
            "souwen.plugin_manager.get_fetch_handlers", lambda: {catalog_name: object()}
        )
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handler_owners", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_loaded_plugins", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._package_version", lambda package: "9.9.9")

        plugin = next(item for item in list_plugins() if item.name == catalog_name)

        assert plugin.status == "loaded"
        assert plugin.source == "entry_point"
        assert plugin.package == PLUGIN_CATALOG[0]["package"]
        assert plugin.version == "9.9.9"
        assert plugin.first_party is True
        assert plugin.fetch_handlers == [catalog_name]

    def test_disabled_plugins_appear_with_disabled_status(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _save_state({"disabled_plugins": ["ghost", "superweb2pdf"], "installed_via_api": []})
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [])
        monkeypatch.setattr("souwen.plugin_manager.all_adapters", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handler_owners", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_loaded_plugins", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        plugins_by_name = {plugin.name: plugin for plugin in list_plugins()}

        assert plugins_by_name["ghost"].status == "disabled"
        assert plugins_by_name["ghost"].source == "config_path"
        assert plugins_by_name["superweb2pdf"].status == "disabled"


class TestGetPluginInfo:
    def test_found_plugin_returns_plugin_info(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [])
        monkeypatch.setattr("souwen.plugin_manager.all_adapters", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handler_owners", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_loaded_plugins", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        info = get_plugin_info("superweb2pdf")

        assert isinstance(info, PluginInfo)
        assert info.name == "superweb2pdf"

    def test_not_found_returns_none(self, state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [])
        monkeypatch.setattr("souwen.plugin_manager.all_adapters", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handler_owners", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_loaded_plugins", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        assert get_plugin_info("missing-plugin") is None


class TestEnableDisable:
    def test_enable_plugin_removes_from_disabled_list_and_sets_restart_flag(
        self,
        state_dir: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _save_state({"disabled_plugins": ["alpha", "beta"], "installed_via_api": []})

        with caplog.at_level(logging.INFO, logger="souwen.plugin_manager"):
            result = enable_plugin("alpha")

        assert result["success"] is True
        assert result["restart_required"] is True
        assert _load_state()["disabled_plugins"] == ["beta"]
        assert is_restart_required() is True
        record = next(
            record
            for record in caplog.records
            if getattr(record, "event", None) == "plugin_enabled"
        )
        assert record.plugin == "alpha"

    def test_disable_plugin_adds_to_disabled_list_and_sets_restart_flag(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _save_state({"disabled_plugins": ["alpha"], "installed_via_api": []})
        monkeypatch.setattr(
            "souwen.plugin_manager._resolve_disable_target", lambda name: (name, None)
        )
        monkeypatch.setattr("souwen.registry.views._unreg_external", lambda name: False)

        with caplog.at_level(logging.INFO, logger="souwen.plugin_manager"):
            result = disable_plugin("beta")

        assert result["success"] is True
        assert result["restart_required"] is True
        assert _load_state()["disabled_plugins"] == ["alpha", "beta"]
        assert is_restart_required() is True
        record = next(
            record
            for record in caplog.records
            if getattr(record, "event", None) == "plugin_disabled"
        )
        assert record.plugin == "beta"

    def test_disable_plugin_deduplicates_disabled_list(
        self, state_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _save_state({"disabled_plugins": ["alpha"], "installed_via_api": []})
        monkeypatch.setattr(
            "souwen.plugin_manager._resolve_disable_target", lambda name: (name, None)
        )
        monkeypatch.setattr("souwen.registry.views._unreg_external", lambda name: False)

        disable_plugin("alpha")

        assert _load_state()["disabled_plugins"] == ["alpha"]

    def test_disable_plugin_rejects_unknown_target(self, state_dir: Path) -> None:
        result = disable_plugin("nonexistent_xyz")

        assert result["success"] is False
        assert "不是可禁用" in result["message"]


class TestInstallUninstall:
    def test_install_enabled_helper_reflects_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SOUWEN_ENABLE_PLUGIN_INSTALL", raising=False)
        assert is_plugin_install_enabled() is False

        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")
        assert is_plugin_install_enabled() is True

    @pytest.mark.asyncio
    async def test_install_plugin_when_env_not_set_returns_error(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SOUWEN_ENABLE_PLUGIN_INSTALL", raising=False)

        result = await install_plugin("superweb2pdf")

        assert result["success"] is False
        assert result["restart_required"] is False
        assert "未启用" in result["output"]

    @pytest.mark.asyncio
    async def test_install_plugin_with_invalid_package_name_returns_error(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")

        result = await install_plugin("bad package")

        assert result == {"success": False, "output": "非法插件包名。", "restart_required": False}

    @pytest.mark.asyncio
    async def test_install_plugin_with_package_not_in_allow_list_returns_error(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")

        result = await install_plugin("unknown-plugin")

        assert result == {
            "success": False,
            "output": "插件包不在允许列表中。",
            "restart_required": False,
        }

    @pytest.mark.asyncio
    async def test_uninstall_plugin_when_env_not_set_returns_error(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SOUWEN_ENABLE_PLUGIN_INSTALL", raising=False)

        result = await uninstall_plugin("superweb2pdf")

        assert result["success"] is False
        assert result["restart_required"] is False
        assert "未启用" in result["output"]

    @pytest.mark.asyncio
    async def test_install_plugin_success_updates_state_and_restart_required(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        async def fake_run_pip(args: list[str], timeout: float) -> tuple[bool, str]:
            assert args == ["install", "superweb2pdf"]
            assert timeout == 120
            return True, "installed"

        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")
        monkeypatch.setattr("souwen.plugin_manager._run_pip", fake_run_pip)

        with caplog.at_level(logging.INFO, logger="souwen.plugin_manager"):
            result = await install_plugin("superweb2pdf")

        assert result == {"success": True, "output": "installed", "restart_required": True}
        assert _load_state()["installed_via_api"] == ["superweb2pdf"]
        assert is_restart_required() is True
        record = next(
            record
            for record in caplog.records
            if getattr(record, "event", None) == "plugin_installed"
        )
        assert record.plugin == "superweb2pdf"
        assert record.package == "superweb2pdf"

    @pytest.mark.asyncio
    async def test_uninstall_plugin_success_updates_state_and_restart_required(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        async def fake_run_pip(args: list[str], timeout: float) -> tuple[bool, str]:
            assert args == ["uninstall", "-y", "superweb2pdf"]
            assert timeout == 60
            return True, "uninstalled"

        _save_state({"disabled_plugins": [], "installed_via_api": ["superweb2pdf"]})
        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")
        monkeypatch.setattr("souwen.plugin_manager._run_pip", fake_run_pip)

        with caplog.at_level(logging.INFO, logger="souwen.plugin_manager"):
            result = await uninstall_plugin("superweb2pdf")

        assert result == {"success": True, "output": "uninstalled", "restart_required": True}
        assert _load_state()["installed_via_api"] == []
        assert is_restart_required() is True
        record = next(
            record
            for record in caplog.records
            if getattr(record, "event", None) == "plugin_uninstalled"
        )
        assert record.plugin == "superweb2pdf"
        assert record.package == "superweb2pdf"


class TestReloadPlugins:
    def test_reload_plugins_calls_discover_entrypoint_plugins(
        self,
        monkeypatch: pytest.MonkeyPatch,
        state_dir: Path,
    ) -> None:
        called = False

        def fake_discover(
            *, skip_names: set[str] | None = None
        ) -> tuple[list[str], list[dict[str, str]]]:
            nonlocal called
            called = True
            return ["alpha"], [{"source": "entry_points", "name": "broken", "error": "boom"}]

        monkeypatch.setattr("souwen.plugin_manager.discover_entrypoint_plugins", fake_discover)

        result = reload_plugins()

        assert called is True
        assert result["loaded"] == ["alpha"]
        assert result["errors"] == [{"source": "entry_points", "name": "broken", "error": "boom"}]
        assert "新增加载 1 个" in result["message"]
        assert "错误 1 个" in result["message"]

    def test_reload_respects_disabled_list(
        self,
        monkeypatch: pytest.MonkeyPatch,
        state_dir: Path,
    ) -> None:
        _save_state({"disabled_plugins": ["beta"], "installed_via_api": []})
        captured_skip: set[str] | None = None

        def fake_discover(
            *, skip_names: set[str] | None = None
        ) -> tuple[list[str], list[dict[str, str]]]:
            nonlocal captured_skip
            captured_skip = skip_names
            return [], []

        monkeypatch.setattr("souwen.plugin_manager.discover_entrypoint_plugins", fake_discover)

        reload_plugins()

        assert captured_skip == {"beta"}


class TestRuntimeDisable:
    def test_disable_runtime_unreg_called(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        unload_called_with: list[str] = []
        monkeypatch.setattr(
            "souwen.plugin_manager._resolve_disable_target", lambda name: (name, name)
        )
        monkeypatch.setattr(
            "souwen.plugin_manager.unload_plugin",
            lambda name: (
                unload_called_with.append(name),
                {
                    "name": name,
                    "status": "unloaded",
                    "removed_adapters": [name],
                    "removed_handlers": [],
                    "errors": [],
                },
            )[-1],
        )

        result = disable_plugin("test_plugin")

        assert result["success"] is True
        assert "test_plugin" in unload_called_with

    def test_enable_already_enabled_noop(self, state_dir: Path) -> None:
        _save_state({"disabled_plugins": [], "installed_via_api": []})

        result = enable_plugin("something")

        assert result["success"] is True
        assert result["restart_required"] is False
        assert "已处于启用状态" in result["message"]

    def test_disable_already_disabled_noop(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _save_state({"disabled_plugins": ["alpha"], "installed_via_api": []})
        monkeypatch.setattr(
            "souwen.plugin_manager._resolve_disable_target", lambda name: (name, None)
        )

        result = disable_plugin("alpha")

        assert result["success"] is True
        assert result["restart_required"] is False
        assert "已处于禁用状态" in result["message"]

    def test_disable_by_adapter_name_unloads_owning_plugin(
        self,
        state_dir: Path,
        clean_registry: None,
    ) -> None:
        from souwen.plugin import Plugin, _PLUGINS, _register_plugin
        from souwen.registry.adapter import MethodSpec, SourceAdapter
        from souwen.registry.loader import lazy
        from souwen.registry.views import all_adapters

        adapter = SourceAdapter(
            name="adapter_demo",
            domain="fetch",
            integration="self_hosted",
            description="adapter demo",
            config_field=None,
            client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
            methods={"fetch": MethodSpec("fetch")},
            tags=frozenset({"external_plugin"}),
        )
        saved = dict(_PLUGINS)
        _PLUGINS.clear()
        try:
            _register_plugin(
                Plugin(name="plugin_demo", adapters=[adapter]),
                source_label="t",
                loaded=[],
                errors=[],
            )

            result = disable_plugin("adapter_demo")

            assert result["success"] is True
            assert _load_state()["disabled_plugins"] == ["plugin_demo"]
            assert "plugin_demo" not in _PLUGINS
            assert "adapter_demo" not in all_adapters()
            assert "解析为插件 'plugin_demo'" in result["message"]
        finally:
            _PLUGINS.clear()
            _PLUGINS.update(saved)

    @pytest.mark.asyncio
    async def test_disable_async_awaits_shutdown(
        self,
        state_dir: Path,
        clean_registry: None,
    ) -> None:
        from souwen.plugin import Plugin, _PLUGINS, _register_plugin

        calls: list[str] = []

        async def shutdown(plugin):
            calls.append(plugin.name)

        saved = dict(_PLUGINS)
        _PLUGINS.clear()
        try:
            _register_plugin(
                Plugin(name="async_disable", on_shutdown=shutdown),
                source_label="t",
                loaded=[],
                errors=[],
            )

            result = await disable_plugin_async("async_disable")

            assert result["success"] is True
            assert calls == ["async_disable"]
            assert _load_state()["disabled_plugins"] == ["async_disable"]
            assert "async_disable" not in _PLUGINS
        finally:
            _PLUGINS.clear()
            _PLUGINS.update(saved)


class TestValidDisableTarget:
    def test_catalog_plugin_is_valid_target(self) -> None:
        from souwen.plugin_manager import _valid_disable_target

        assert _valid_disable_target("superweb2pdf") is True

    def test_unknown_name_is_invalid_target(self) -> None:
        from souwen.plugin_manager import _valid_disable_target

        assert _valid_disable_target("totally_fake_plugin_xyz") is False


class TestUnregExternal:
    def test_unreg_external_removes_plugin(self) -> None:
        from souwen.registry.views import _EXTERNAL_PLUGINS, _REGISTRY, _unreg_external

        # 临时插入一个假的外部插件
        _REGISTRY["_test_fake"] = object()  # type: ignore[assignment]
        _EXTERNAL_PLUGINS.add("_test_fake")
        try:
            assert _unreg_external("_test_fake") is True
            assert "_test_fake" not in _REGISTRY
            assert "_test_fake" not in _EXTERNAL_PLUGINS
        finally:
            _REGISTRY.pop("_test_fake", None)
            _EXTERNAL_PLUGINS.discard("_test_fake")

    def test_unreg_external_rejects_builtin(self) -> None:
        from souwen.registry.views import _unreg_external

        assert _unreg_external("arxiv") is False


class TestPackageNameValidation:
    @pytest.mark.parametrize(
        "package",
        sorted(
            ALLOWED_PACKAGES | {item["package"] for item in PLUGIN_CATALOG if item.get("package")}
        ),
    )
    def test_allowed_package_names_pass_regex(self, package: str) -> None:
        assert _PACKAGE_NAME_RE.fullmatch(package)

    @pytest.mark.parametrize(
        "package",
        [
            "bad package",
            "http://example.com/pkg",
            "https://example.com/pkg",
            "pkg/name",
            "pkg$name",
            "pkg@1.0",
            "-starts-with-dash",
            ".starts-with-dot",
            "",
            "a" * 102,
        ],
    )
    def test_invalid_package_names_fail_regex(self, package: str) -> None:
        assert _PACKAGE_NAME_RE.fullmatch(package) is None


class TestAPIEndpoints:
    @pytest.fixture()
    def client(self):
        fastapi = pytest.importorskip("fastapi")
        testclient = pytest.importorskip("fastapi.testclient")
        from souwen.server.routes.admin.plugins import router

        app = fastapi.FastAPI()
        app.include_router(router)
        return testclient.TestClient(app)

    def test_get_plugins_returns_list(
        self,
        client: Any,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [])
        monkeypatch.setattr("souwen.plugin_manager.all_adapters", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handler_owners", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_loaded_plugins", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        response = client.get("/plugins")

        assert response.status_code == 200
        payload = response.json()
        assert "plugins" in payload
        assert isinstance(payload["plugins"], list)
        assert payload["restart_required"] is False
        # install_enabled 字段供前端决定是否展示安装/卸载入口
        assert "install_enabled" in payload
        assert isinstance(payload["install_enabled"], bool)

    def test_get_plugin_unknown_returns_404(
        self,
        client: Any,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [])
        monkeypatch.setattr("souwen.plugin_manager.all_adapters", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handler_owners", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_loaded_plugins", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        response = client.get("/plugins/unknown")

        assert response.status_code == 404

    def test_plugin_health_with_callable(
        self,
        client: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from souwen.plugin import Plugin

        async def health_check() -> dict[str, Any]:
            return {"status": "ok", "latency_ms": 1}

        monkeypatch.setattr(
            "souwen.plugin.get_loaded_plugins",
            lambda: {"healthy": Plugin(name="healthy", health_check=health_check)},
        )

        response = client.get("/plugins/healthy/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "latency_ms": 1}

    def test_plugin_health_without_callable(
        self,
        client: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from souwen.plugin import Plugin

        monkeypatch.setattr(
            "souwen.plugin.get_loaded_plugins",
            lambda: {"plain": Plugin(name="plain")},
        )

        response = client.get("/plugins/plain/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "message": "no health check defined"}

    def test_plugin_health_unknown_returns_404(
        self,
        client: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {})

        response = client.get("/plugins/missing/health")

        assert response.status_code == 404

    def test_post_enable_plugin(
        self,
        client: Any,
        state_dir: Path,
    ) -> None:
        _save_state({"disabled_plugins": ["alpha"], "installed_via_api": []})

        response = client.post("/plugins/alpha/enable")

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert _load_state()["disabled_plugins"] == []

    def test_post_disable_plugin(
        self,
        client: Any,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "souwen.plugin_manager._resolve_disable_target", lambda name: (name, None)
        )
        monkeypatch.setattr("souwen.registry.views._unreg_external", lambda name: False)

        response = client.post("/plugins/alpha/disable")

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert _load_state()["disabled_plugins"] == ["alpha"]

    def test_post_install_without_env_var(
        self,
        client: Any,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SOUWEN_ENABLE_PLUGIN_INSTALL", raising=False)

        response = client.post("/plugins/install", json={"package": "superweb2pdf"})

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "未启用" in response.json()["message"]

    def test_post_install_with_invalid_package_returns_actionable_message(
        self,
        client: Any,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")

        response = client.post("/plugins/install", json={"package": "bad package"})

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert response.json()["message"] == "非法插件包名。"

    def test_post_install_sanitizes_raw_pip_failure_output(
        self,
        client: Any,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        async def fake_run_pip(args: list[str], timeout: float) -> tuple[bool, str]:
            return False, "Collecting superweb2pdf\nERROR: private index token leaked"

        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")
        monkeypatch.setattr("souwen.plugin_manager._run_pip", fake_run_pip)

        caplog.set_level(logging.WARNING, logger="souwen.server")
        response = client.post("/plugins/install", json={"package": "superweb2pdf"})

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert response.json()["message"] == "操作失败，详见服务端日志"
        assert "private index token leaked" not in caplog.text
        assert "Collecting superweb2pdf" not in caplog.text

    def test_post_reload(
        self,
        client: Any,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "souwen.plugin_manager.discover_entrypoint_plugins",
            lambda *, skip_names=None: (["alpha"], []),
        )

        response = client.post("/plugins/reload")

        assert response.status_code == 200
        assert response.json()["loaded"] == ["alpha"]
        assert response.json()["errors"] == []


# ── Fix verification: disable by plugin name (not just adapter name) ──


class TestDisableByPluginName:
    """Fix #1: _valid_disable_target accepts loaded Plugin names."""

    def test_disable_accepts_loaded_plugin_name(
        self, state_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plugin named 'plugin_x' with adapter 'adapter_x' should be disableable."""
        from souwen.plugin import Plugin, _PLUGINS

        saved = dict(_PLUGINS)
        try:
            _PLUGINS["plugin_x"] = Plugin(name="plugin_x")
            monkeypatch.setattr(
                "souwen.plugin_manager.unload_plugin",
                lambda name: {
                    "name": name,
                    "status": "unloaded",
                    "removed_adapters": [],
                    "removed_handlers": [],
                    "errors": [],
                },
            )
            result = disable_plugin("plugin_x")
            assert result["success"] is True
        finally:
            _PLUGINS.clear()
            _PLUGINS.update(saved)
