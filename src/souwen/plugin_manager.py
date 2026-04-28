"""SouWen 插件管理器 — 插件生命周期管理

提供插件的列表查询、启用/禁用、安装/卸载、重新扫描功能。
面向 API 端点、CLI 命令和 Web 面板。
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from souwen.plugin import discover_entrypoint_plugins
from souwen.registry.views import all_adapters, external_plugins
from souwen.web.fetch import get_fetch_handlers

logger = logging.getLogger("souwen.plugin_manager")

PLUGIN_CATALOG: list[dict[str, str]] = [
    {
        "name": "superweb2pdf",
        "package": "superweb2pdf",
        "description": "SuperWeb2PDF — 网页截图转 PDF（基于 Playwright Chromium）",
        "entry_point": "superweb2pdf",
        "first_party": "true",
    },
]

ALLOWED_PACKAGES: frozenset[str] = frozenset(
    {
        "superweb2pdf",
        "souwen-example-plugin",
    }
)
_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")

_restart_required: bool = False


class PluginInfo(BaseModel):
    """插件状态视图。"""

    name: str
    package: str | None = None
    version: str | None = None
    status: str
    source: str
    first_party: bool = False
    description: str = ""
    error: str | None = None
    source_adapters: list[str] = Field(default_factory=list)
    fetch_handlers: list[str] = Field(default_factory=list)
    restart_required: bool = False


def _default_state() -> dict[str, list[str]]:
    """返回状态文件默认结构。"""
    return {"disabled_plugins": [], "installed_via_api": []}


def _get_state_path() -> Path:
    """获取插件状态文件路径，配置不可用时回退到默认数据目录。"""
    try:
        from souwen.config import get_config

        data_path = getattr(get_config(), "data_path", None)
        if isinstance(data_path, Path):
            base_dir = data_path
        elif data_path is not None:
            base_dir = Path(data_path).expanduser()
        else:
            data_dir = getattr(get_config(), "data_dir", "~/.local/share/souwen")
            base_dir = Path(data_dir).expanduser()
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取配置目录失败，使用默认插件状态目录: %s", exc)
        base_dir = Path("~/.local/share/souwen").expanduser()
    return base_dir / "plugins.state.json"


def _normalize_state(raw: Any) -> dict[str, list[str]]:
    """把磁盘状态清洗为稳定结构。"""
    state = _default_state()
    if not isinstance(raw, dict):
        return state
    for key in state:
        values = raw.get(key, [])
        if isinstance(values, list):
            state[key] = sorted({str(item) for item in values if str(item).strip()})
    return state


def _load_state() -> dict[str, list[str]]:
    """读取插件状态文件；不存在时创建。"""
    path = _get_state_path()
    try:
        if not path.exists():
            state = _default_state()
            _save_state(state)
            return state
        with path.open("r", encoding="utf-8") as f:
            return _normalize_state(json.load(f))
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取插件状态文件失败: %s", exc)
        return _default_state()


def _save_state(state: dict[str, Any]) -> None:
    """原子写入插件状态文件。"""
    path = _get_state_path()
    clean_state = _normalize_state(state)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(clean_state, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("保存插件状态文件失败: %s", exc)
        try:
            if "tmp_path" in locals() and tmp_path.exists():
                tmp_path.unlink()
        except Exception:  # noqa: BLE001
            pass


def _catalog_by_name() -> dict[str, dict[str, str]]:
    """按名称索引插件目录。"""
    return {item["name"]: item for item in PLUGIN_CATALOG if item.get("name")}


def _catalog_packages() -> set[str]:
    """返回目录中声明的包名集合。"""
    return {item["package"] for item in PLUGIN_CATALOG if item.get("package")}


def _is_truthy(value: str | None) -> bool:
    """解析目录中的布尔字符串。"""
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _import_name_for_catalog(item: dict[str, str]) -> str:
    """推断目录插件用于 import 检测的模块名。"""
    fallback = item.get("package") or item.get("name", "")
    return item.get("entry_point") or fallback.replace("-", "_")


def _package_version(package: str | None) -> str | None:
    """安全读取已安装包版本。"""
    if not package:
        return None
    try:
        from importlib import metadata

        return metadata.version(package)
    except Exception:  # noqa: BLE001
        return None


def _is_package_importable(item: dict[str, str]) -> bool:
    """判断目录插件是否能被当前 Python 环境导入。"""
    import_name = _import_name_for_catalog(item)
    if not import_name:
        return False
    try:
        return importlib.util.find_spec(import_name) is not None
    except Exception as exc:  # noqa: BLE001
        logger.warning("检测插件 %r 可导入性失败: %s", import_name, exc)
        return False


def _source_for_plugin(name: str, catalog: dict[str, dict[str, str]]) -> str:
    """推断插件来源。"""
    if name in catalog:
        return "entry_point"
    return "config_path"


def _mark_restart_required() -> None:
    """标记有变更需要重启后完全生效。"""
    global _restart_required
    _restart_required = True


def list_plugins() -> list[PluginInfo]:
    """列出当前加载、禁用和目录可用插件。"""
    try:
        state = _load_state()
        disabled = set(state.get("disabled_plugins", []))
        adapters = all_adapters()
        external = set(external_plugins())
        fetch_handlers = get_fetch_handlers()
        catalog = _catalog_by_name()
        result: dict[str, PluginInfo] = {}

        for name in sorted(external):
            adapter = adapters.get(name)
            catalog_item = catalog.get(name, {})
            package = catalog_item.get("package") or None
            status = "disabled" if name in disabled else "loaded"
            result[name] = PluginInfo(
                name=name,
                package=package,
                version=_package_version(package),
                status=status,
                source=_source_for_plugin(name, catalog),
                first_party=_is_truthy(catalog_item.get("first_party")),
                description=(
                    getattr(adapter, "description", "") or catalog_item.get("description", "")
                ),
                source_adapters=[name] if adapter is not None else [],
                fetch_handlers=[name] if name in fetch_handlers else [],
                restart_required=_restart_required,
            )

        for item in PLUGIN_CATALOG:
            name = item.get("name", "").strip()
            if not name or name in result:
                continue
            package = item.get("package") or None
            importable = _is_package_importable(item)
            status = "disabled" if name in disabled else ("loaded" if importable else "available")
            result[name] = PluginInfo(
                name=name,
                package=package,
                version=_package_version(package),
                status=status,
                source="catalog",
                first_party=_is_truthy(item.get("first_party")),
                description=item.get("description", ""),
                source_adapters=[name] if name in adapters else [],
                fetch_handlers=[name] if name in fetch_handlers else [],
                restart_required=_restart_required,
            )

        for name in sorted(disabled):
            if name in result:
                result[name].status = "disabled"
                result[name].restart_required = _restart_required
                continue
            result[name] = PluginInfo(
                name=name,
                status="disabled",
                source="config_path",
                restart_required=_restart_required,
            )

        return sorted(result.values(), key=lambda p: (p.name.lower(), p.name))
    except Exception as exc:  # noqa: BLE001
        logger.warning("列出插件失败: %s", exc)
        return []


def get_plugin_info(name: str) -> PluginInfo | None:
    """按名称查询插件信息。"""
    try:
        for plugin in list_plugins():
            if plugin.name == name:
                return plugin
    except Exception as exc:  # noqa: BLE001
        logger.warning("查询插件 %r 失败: %s", name, exc)
    return None


def _valid_disable_target(name: str) -> bool:
    """检查插件名是否为可禁用目标（外部插件或目录中的插件）。"""
    catalog_names = {item.get("name") for item in PLUGIN_CATALOG if item.get("name")}
    try:
        ext = set(external_plugins())
    except Exception:  # noqa: BLE001
        ext = set()
    return name in ext or name in catalog_names


def enable_plugin(name: str) -> dict[str, Any]:
    """启用插件（从禁用列表移除，重启后生效）。"""
    try:
        state = _load_state()
        disabled = set(state.get("disabled_plugins", []))
        if name not in disabled:
            return {
                "success": True,
                "restart_required": False,
                "message": f"插件 {name!r} 已处于启用状态。",
            }
        disabled.discard(name)
        state["disabled_plugins"] = sorted(disabled)
        _save_state(state)
        _mark_restart_required()
        return {
            "success": True,
            "restart_required": True,
            "message": f"插件 {name!r} 已启用，重启后完全生效。",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("启用插件 %r 失败: %s", name, exc)
        return {"success": False, "restart_required": False, "message": str(exc)}


def disable_plugin(name: str) -> dict[str, Any]:
    """禁用插件（写入禁用列表 + 运行时从注册表移除）。

    运行时立即从 _REGISTRY 移除（新请求不再使用该插件），
    完全生效（含 fetch handler 清理）需重启。
    """
    try:
        if not _valid_disable_target(name):
            return {
                "success": False,
                "restart_required": False,
                "message": f"插件 {name!r} 不是可禁用的外部插件。",
            }
        state = _load_state()
        disabled = set(state.get("disabled_plugins", []))
        if name in disabled:
            return {
                "success": True,
                "restart_required": False,
                "message": f"插件 {name!r} 已处于禁用状态。",
            }
        disabled.add(name)
        state["disabled_plugins"] = sorted(disabled)
        _save_state(state)

        # 运行时从注册表移除（B2: 仅移除 _REGISTRY，不动 _FETCH_HANDLERS 避免误删内置处理器）
        try:
            from souwen.registry.views import _unreg_external

            removed = _unreg_external(name)
            if removed:
                logger.info("已从注册表运行时移除插件 %r", name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("运行时移除插件 %r 失败: %s", name, exc)

        _mark_restart_required()
        return {
            "success": True,
            "restart_required": True,
            "message": f"插件 {name!r} 已禁用，搜索源已立即停用，完全清理需重启。",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("禁用插件 %r 失败: %s", name, exc)
        return {"success": False, "restart_required": False, "message": str(exc)}


def _plugin_install_enabled() -> bool:
    """安装/卸载开关，默认关闭。"""
    return os.environ.get("SOUWEN_ENABLE_PLUGIN_INSTALL") == "1"


def _validate_package(package: str) -> str | None:
    """校验包名和允许列表，返回错误信息或 None。"""
    if not _PACKAGE_NAME_RE.fullmatch(package or ""):
        return "非法插件包名。"
    allowed = set(ALLOWED_PACKAGES) | _catalog_packages()
    if package not in allowed:
        return "插件包不在允许列表中。"
    return None


async def _run_pip(args: list[str], timeout: float) -> tuple[bool, str]:
    """异步运行 pip 命令并返回合并输出。"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pip",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        stdout, _ = await process.communicate()
        output = (stdout or b"").decode("utf-8", errors="replace")
        return False, f"pip 命令超时。\n{output}".strip()
    output = (stdout or b"").decode("utf-8", errors="replace")
    return process.returncode == 0, output


async def install_plugin(package: str) -> dict[str, Any]:
    """安装允许列表中的插件包。"""
    if not _plugin_install_enabled():
        return {
            "success": False,
            "output": "插件安装功能未启用，请设置 SOUWEN_ENABLE_PLUGIN_INSTALL=1。",
            "restart_required": False,
        }
    error = _validate_package(package)
    if error:
        return {"success": False, "output": error, "restart_required": False}

    try:
        success, output = await _run_pip(["install", package], timeout=120)
        if success:
            state = _load_state()
            installed = set(state.get("installed_via_api", []))
            installed.add(package)
            state["installed_via_api"] = sorted(installed)
            _save_state(state)
            _mark_restart_required()
        return {"success": success, "output": output, "restart_required": success}
    except Exception as exc:  # noqa: BLE001
        logger.warning("安装插件包 %r 失败: %s", package, exc)
        return {"success": False, "output": str(exc), "restart_required": False}


async def uninstall_plugin(package: str) -> dict[str, Any]:
    """卸载允许列表中的插件包。"""
    if not _plugin_install_enabled():
        return {
            "success": False,
            "output": "插件卸载功能未启用，请设置 SOUWEN_ENABLE_PLUGIN_INSTALL=1。",
            "restart_required": False,
        }
    error = _validate_package(package)
    if error:
        return {"success": False, "output": error, "restart_required": False}

    try:
        success, output = await _run_pip(["uninstall", "-y", package], timeout=60)
        if success:
            state = _load_state()
            installed = set(state.get("installed_via_api", []))
            installed.discard(package)
            state["installed_via_api"] = sorted(installed)
            _save_state(state)
            _mark_restart_required()
        return {"success": success, "output": output, "restart_required": success}
    except Exception as exc:  # noqa: BLE001
        logger.warning("卸载插件包 %r 失败: %s", package, exc)
        return {"success": False, "output": str(exc), "restart_required": False}


def reload_plugins() -> dict[str, Any]:
    """重新扫描 entry point 插件并追加注册新插件（尊重禁用列表）。"""
    try:
        importlib.invalidate_caches()
        state = _load_state()
        skip_names = set(state.get("disabled_plugins", []))
        loaded, errors = discover_entrypoint_plugins(skip_names=skip_names)
        message = f"插件重新扫描完成，新增加载 {len(loaded)} 个，错误 {len(errors)} 个。"
        if skip_names:
            message += f" 已跳过禁用插件: {', '.join(sorted(skip_names))}。"
        return {"loaded": loaded, "errors": errors, "message": message}
    except Exception as exc:  # noqa: BLE001
        logger.warning("重新扫描插件失败: %s", exc)
        return {
            "loaded": [],
            "errors": [{"source": "entry_points", "name": "<reload>", "error": str(exc)}],
            "message": "插件重新扫描失败。",
        }


def is_restart_required() -> bool:
    """返回当前进程内是否已有插件状态变更需要重启。"""
    return _restart_required


__all__ = [
    "ALLOWED_PACKAGES",
    "PLUGIN_CATALOG",
    "PluginInfo",
    "disable_plugin",
    "enable_plugin",
    "get_plugin_info",
    "install_plugin",
    "is_restart_required",
    "list_plugins",
    "reload_plugins",
    "uninstall_plugin",
]
