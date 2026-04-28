"""tests/test_plugin_manager.py — 插件管理器测试"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from souwen.plugin_manager import (
    ALLOWED_PACKAGES,
    PLUGIN_CATALOG,
    PluginInfo,
    _PACKAGE_NAME_RE,
    _load_state,
    _save_state,
    disable_plugin,
    enable_plugin,
    get_plugin_info,
    install_plugin,
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
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {catalog_name: object()})
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
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        info = get_plugin_info("superweb2pdf")

        assert isinstance(info, PluginInfo)
        assert info.name == "superweb2pdf"

    def test_not_found_returns_none(self, state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [])
        monkeypatch.setattr("souwen.plugin_manager.all_adapters", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        assert get_plugin_info("missing-plugin") is None


class TestEnableDisable:
    def test_enable_plugin_removes_from_disabled_list_and_sets_restart_flag(
        self,
        state_dir: Path,
    ) -> None:
        _save_state({"disabled_plugins": ["alpha", "beta"], "installed_via_api": []})

        result = enable_plugin("alpha")

        assert result["success"] is True
        assert result["restart_required"] is True
        assert _load_state()["disabled_plugins"] == ["beta"]
        assert is_restart_required() is True

    def test_disable_plugin_adds_to_disabled_list_and_sets_restart_flag(
        self,
        state_dir: Path,
    ) -> None:
        _save_state({"disabled_plugins": ["alpha"], "installed_via_api": []})

        result = disable_plugin("beta")

        assert result["success"] is True
        assert result["restart_required"] is True
        assert _load_state()["disabled_plugins"] == ["alpha", "beta"]
        assert is_restart_required() is True

    def test_disable_plugin_deduplicates_disabled_list(self, state_dir: Path) -> None:
        _save_state({"disabled_plugins": ["alpha"], "installed_via_api": []})

        disable_plugin("alpha")

        assert _load_state()["disabled_plugins"] == ["alpha"]


class TestInstallUninstall:
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

        assert result == {"success": False, "output": "插件包不在允许列表中。", "restart_required": False}

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
    ) -> None:
        async def fake_run_pip(args: list[str], timeout: float) -> tuple[bool, str]:
            assert args == ["install", "superweb2pdf"]
            assert timeout == 120
            return True, "installed"

        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")
        monkeypatch.setattr("souwen.plugin_manager._run_pip", fake_run_pip)

        result = await install_plugin("superweb2pdf")

        assert result == {"success": True, "output": "installed", "restart_required": True}
        assert _load_state()["installed_via_api"] == ["superweb2pdf"]
        assert is_restart_required() is True

    @pytest.mark.asyncio
    async def test_uninstall_plugin_success_updates_state_and_restart_required(
        self,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_run_pip(args: list[str], timeout: float) -> tuple[bool, str]:
            assert args == ["uninstall", "-y", "superweb2pdf"]
            assert timeout == 60
            return True, "uninstalled"

        _save_state({"disabled_plugins": [], "installed_via_api": ["superweb2pdf"]})
        monkeypatch.setenv("SOUWEN_ENABLE_PLUGIN_INSTALL", "1")
        monkeypatch.setattr("souwen.plugin_manager._run_pip", fake_run_pip)

        result = await uninstall_plugin("superweb2pdf")

        assert result == {"success": True, "output": "uninstalled", "restart_required": True}
        assert _load_state()["installed_via_api"] == []
        assert is_restart_required() is True


class TestReloadPlugins:
    def test_reload_plugins_calls_discover_entrypoint_plugins(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        called = False

        def fake_discover() -> tuple[list[str], list[dict[str, str]]]:
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


class TestPackageNameValidation:
    @pytest.mark.parametrize(
        "package",
        sorted(ALLOWED_PACKAGES | {item["package"] for item in PLUGIN_CATALOG if item.get("package")}),
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
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        response = client.get("/plugins")

        assert response.status_code == 200
        payload = response.json()
        assert "plugins" in payload
        assert isinstance(payload["plugins"], list)
        assert payload["restart_required"] is False

    def test_get_plugin_unknown_returns_404(
        self,
        client: Any,
        state_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("souwen.plugin_manager.external_plugins", lambda: [])
        monkeypatch.setattr("souwen.plugin_manager.all_adapters", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager.get_fetch_handlers", lambda: {})
        monkeypatch.setattr("souwen.plugin_manager._is_package_importable", lambda item: False)

        response = client.get("/plugins/unknown")

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
    ) -> None:
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
        assert "未启用" in response.json()["output"]

    def test_post_reload(
        self,
        client: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "souwen.plugin_manager.discover_entrypoint_plugins",
            lambda: (["alpha"], []),
        )

        response = client.post("/plugins/reload")

        assert response.status_code == 200
        assert response.json()["loaded"] == ["alpha"]
        assert response.json()["errors"] == []
