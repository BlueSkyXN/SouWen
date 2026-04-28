"""SouWen 插件系统 — 外部数据源发现与加载

提供两条加载路径：

1. **Entry Points 自动发现**：第三方包在 `pyproject.toml` 里声明
   ```toml
   [project.entry-points."souwen.plugins"]
   my_source = "my_pkg.plugin:adapter"
   ```
   即可被自动发现并注册。

2. **配置文件手动指定**：在 `souwen.yaml` 或 `SOUWEN_PLUGINS` 环境变量里
   列出 `"module.path:attribute"` 形式的字符串。

每个入口可以解析为：
  - `Plugin` 实例（推荐，支持生命周期钩子 / 配置 / 健康检查）
  - 单个 `SourceAdapter` 实例（自动包装为 Plugin）
  - 返回上述任一形态的零参 callable（工厂函数）
  - `SourceAdapter` 列表/元组（一次注册多个源）

加载失败（导入异常、类型不符、与内置源重名等）只记录警告，
**绝不**让宿主程序崩溃。
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from importlib import metadata
from typing import TYPE_CHECKING, Any

from souwen.registry.adapter import SourceAdapter
from souwen.registry.views import _reg_external, _unreg_external
from souwen.web.fetch import _current_plugin_owner, unregister_fetch_handlers_by_owner

if TYPE_CHECKING:
    from souwen.config.models import SouWenConfig

logger = logging.getLogger("souwen.plugin")

ENTRY_POINT_GROUP = "souwen.plugins"

# ── Plugin 信封类 ────────────────────────────────────────────

LifecycleHook = Callable[["Plugin"], None | Awaitable[None]]
HealthCheck = Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass
class Plugin:
    """插件信封 — 包装 SourceAdapter(s) + 生命周期钩子 + 配置。

    插件通过 ``name`` 唯一标识。name 由加载器从 entry-point 名 /
    配置路径自动设置，不等于 adapter.name（一个插件可包含多个 adapter）。
    """

    name: str
    adapters: list[SourceAdapter] = field(default_factory=list)
    version: str = "0.0.0"
    config_schema: type | None = None
    on_startup: LifecycleHook | None = None
    on_shutdown: LifecycleHook | None = None
    health_check: HealthCheck | None = None
    # 由加载器填充，不要手动设置
    _registered_adapter_names: list[str] = field(default_factory=list, repr=False)


#: 已加载的 Plugin 对象存储（plugin.name → Plugin）
_PLUGINS: dict[str, Plugin] = {}


def _coerce_to_adapters(obj: Any) -> list[SourceAdapter]:
    """把入口对象统一转成 `list[SourceAdapter]`。

    支持的形态：
      - SourceAdapter 实例
      - 零参 callable，调用后返回上述任一形态
      - list/tuple，元素为 SourceAdapter

    类型不符时抛 TypeError，由调用方捕获。
    """
    if callable(obj) and not isinstance(obj, (SourceAdapter, Plugin)):
        obj = obj()

    if isinstance(obj, SourceAdapter):
        return [obj]

    if isinstance(obj, (list, tuple)):
        adapters: list[SourceAdapter] = []
        for item in obj:
            if not isinstance(item, SourceAdapter):
                raise TypeError(f"插件返回的列表包含非 SourceAdapter 元素: {type(item).__name__}")
            adapters.append(item)
        return adapters

    raise TypeError(
        f"插件入口必须是 Plugin / SourceAdapter / 返回它的 callable / 其列表，得到 {type(obj).__name__}"
    )


def _coerce_to_plugin(obj: Any, *, plugin_name: str) -> Plugin:
    """把入口对象统一转成 `Plugin` 实例（向后兼容所有旧形态）。

    接受（按优先级）：
      - Plugin 实例 → 直接返回（name 强制覆盖为 plugin_name）
      - SourceAdapter / list[SourceAdapter] / 零参 callable → 包装为合成 Plugin
    """
    if callable(obj) and not isinstance(obj, (SourceAdapter, Plugin)):
        obj = obj()

    if isinstance(obj, Plugin):
        if obj.name != plugin_name:
            logger.debug("插件 self-name %r 被覆盖为 %r", obj.name, plugin_name)
            obj.name = plugin_name
        return obj

    if isinstance(obj, SourceAdapter):
        return Plugin(name=plugin_name, adapters=[obj])

    if isinstance(obj, (list, tuple)):
        adapters: list[SourceAdapter] = []
        for item in obj:
            if not isinstance(item, SourceAdapter):
                raise TypeError(
                    f"插件 {plugin_name!r}: 列表包含非 SourceAdapter 元素: {type(item).__name__}"
                )
            adapters.append(item)
        return Plugin(name=plugin_name, adapters=adapters)

    raise TypeError(
        f"插件 {plugin_name!r}: 入口必须是 Plugin/SourceAdapter/list/callable，得到 {type(obj).__name__}"
    )


def _register_adapters(
    adapters: Iterable[SourceAdapter],
    *,
    source_label: str,
    loaded: list[str],
    errors: list[dict[str, str]],
) -> None:
    """逐个注册 adapter，捕获每个的异常单独处理。"""
    for adapter in adapters:
        try:
            ok = _reg_external(adapter)
        except Exception as exc:  # noqa: BLE001 — 第三方代码未知异常
            logger.warning("注册插件源 %r (来自 %s) 失败: %s", adapter.name, source_label, exc)
            errors.append({"source": source_label, "name": adapter.name, "error": str(exc)})
            continue
        if ok:
            loaded.append(adapter.name)
            logger.info("已加载插件源 %r (来自 %s)", adapter.name, source_label)


def _register_plugin(
    plugin: Plugin,
    *,
    source_label: str,
    loaded: list[str],
    errors: list[dict[str, str]],
) -> None:
    """注册 Plugin：adapter 注册 + on_startup 调用，全程在 owner contextvar 下。"""
    if plugin.name in _PLUGINS:
        errors.append({
            "source": source_label,
            "name": plugin.name,
            "error": f"插件 {plugin.name!r} 已加载，跳过重复注册",
        })
        return

    token = _current_plugin_owner.set(plugin.name)
    try:
        for adapter in plugin.adapters:
            try:
                ok = _reg_external(adapter)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "注册插件源 %r (插件 %r, %s) 失败: %s",
                    adapter.name, plugin.name, source_label, exc,
                )
                errors.append({"source": source_label, "name": adapter.name, "error": str(exc)})
                continue
            if ok:
                plugin._registered_adapter_names.append(adapter.name)
                loaded.append(adapter.name)
                logger.info(
                    "已加载插件源 %r (插件 %r, %s)", adapter.name, plugin.name, source_label
                )

        # 同步路径调用 on_startup；异步钩子由 app 启动时单独调用
        if plugin.on_startup is not None:
            try:
                result = plugin.on_startup(plugin)
                if hasattr(result, "__await__"):
                    logger.warning(
                        "插件 %r on_startup 返回了协程，同步加载路径不支持异步钩子 — 已跳过",
                        plugin.name,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("插件 %r on_startup 失败: %s", plugin.name, exc)
                errors.append({
                    "source": source_label,
                    "name": plugin.name,
                    "error": f"on_startup: {exc}",
                })
    finally:
        _current_plugin_owner.reset(token)

    _PLUGINS[plugin.name] = plugin


def unload_plugin(name: str) -> dict[str, Any]:
    """卸载插件：on_shutdown → 移除 fetch handler → 移除 adapter。"""
    plugin = _PLUGINS.pop(name, None)
    if plugin is None:
        return {"name": name, "status": "not_loaded"}

    errs: list[str] = []

    if plugin.on_shutdown is not None:
        try:
            result = plugin.on_shutdown(plugin)
            if hasattr(result, "__await__"):
                logger.warning("插件 %r on_shutdown 返回了协程，同步路径不支持 — 已跳过", name)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"on_shutdown: {exc}")

    removed_handlers = unregister_fetch_handlers_by_owner(name)
    removed_adapters: list[str] = []
    for adapter_name in plugin._registered_adapter_names:
        if _unreg_external(adapter_name):
            removed_adapters.append(adapter_name)

    return {
        "name": name,
        "status": "unloaded",
        "removed_handlers": removed_handlers,
        "removed_adapters": removed_adapters,
        "errors": errs,
    }


def get_loaded_plugins() -> dict[str, Plugin]:
    """返回已加载的 Plugin 对象映射（只读副本）。"""
    return dict(_PLUGINS)


def _resolve_dotted_path(path: str) -> Any:
    """解析 `"module.path:attribute"` 字符串为 Python 对象。"""
    if ":" not in path:
        raise ValueError(f"插件路径必须是 'module.path:attribute' 形式，得到 {path!r}")
    module_path, _, attr = path.partition(":")
    if not module_path or not attr:
        raise ValueError(f"插件路径格式非法: {path!r}")
    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise AttributeError(f"模块 {module_path!r} 没有属性 {attr!r}") from exc


def discover_entrypoint_plugins(
    group: str = ENTRY_POINT_GROUP,
    *,
    skip_names: set[str] | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    """通过 entry points 发现并注册插件。

    Args:
        group: entry point 分组名，默认 `"souwen.plugins"`。
        skip_names: 要跳过的插件名集合（按 entry-point 名或 adapter 名匹配）。

    Returns:
        `(loaded_names, errors)` 二元组。
    """
    loaded: list[str] = []
    errors: list[dict[str, str]] = []
    _skip = skip_names or set()

    try:
        eps = metadata.entry_points()
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 entry points 失败: %s", exc)
        return loaded, errors

    if hasattr(eps, "select"):
        candidates = list(eps.select(group=group))
    else:  # pragma: no cover — 兼容老接口
        candidates = list(eps.get(group, []))  # type: ignore[union-attr]

    for ep in candidates:
        ep_name = getattr(ep, "name", "<unknown>")
        label = f"entry_point:{ep_name}"

        # 按 entry-point 名预筛（快速跳过，不触发 import）
        if ep_name in _skip:
            logger.info("跳过已禁用的插件 %r (来自 %s)", ep_name, label)
            continue

        # 设置 contextvar 覆盖模块级 import 时的 fetch handler 注册
        token = _current_plugin_owner.set(ep_name)
        try:
            try:
                obj = ep.load()
                plugin = _coerce_to_plugin(obj, plugin_name=ep_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("加载插件 entry point %r 失败: %s", ep_name, exc)
                errors.append({"source": label, "name": ep_name, "error": str(exc)})
                continue
        finally:
            _current_plugin_owner.reset(token)

        # 按 adapter.name 二次过滤（adapter 名可能与 ep 名不同）
        if _skip:
            plugin.adapters = [a for a in plugin.adapters if a.name not in _skip]

        if plugin.adapters:
            _register_plugin(plugin, source_label=label, loaded=loaded, errors=errors)

    return loaded, errors


def load_config_plugins(
    plugin_paths: list[str],
    *,
    skip_names: set[str] | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    """从 `"module.path:attribute"` 字符串列表加载插件。

    Args:
        plugin_paths: 插件路径列表。
        skip_names: 要跳过的插件名集合。
    """
    loaded: list[str] = []
    errors: list[dict[str, str]] = []
    _skip = skip_names or set()

    for path in plugin_paths or []:
        if not isinstance(path, str) or not path.strip():
            logger.warning("跳过非法的插件路径: %r", path)
            continue
        path = path.strip()
        label = f"config:{path}"

        token = _current_plugin_owner.set(path)
        try:
            try:
                obj = _resolve_dotted_path(path)
                plugin = _coerce_to_plugin(obj, plugin_name=path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("加载配置插件 %r 失败: %s", path, exc)
                errors.append({"source": label, "name": path, "error": str(exc)})
                continue
        finally:
            _current_plugin_owner.reset(token)

        if _skip:
            plugin.adapters = [a for a in plugin.adapters if a.name not in _skip]

        if plugin.adapters:
            _register_plugin(plugin, source_label=label, loaded=loaded, errors=errors)

    return loaded, errors


def load_plugins(config: SouWenConfig | None = None) -> dict[str, Any]:
    """加载所有插件（entry points + 配置文件指定）。

    这是面向 `souwen.registry` 的统一入口，应该在内置源注册完成后调用。
    自动读取插件禁用列表，跳过已禁用的插件。

    Args:
        config: 可选的 `SouWenConfig`。提供则会读取其 `plugins` 字段。
            为 None 时只做 entry points 发现，避免在 registry 初始化期间
            循环导入 config 模块。

    Returns:
        ``{"loaded": [...名称], "errors": [...]}``。即使全部失败也不抛异常。
    """
    all_loaded: list[str] = []
    all_errors: list[dict[str, str]] = []

    # 读取插件禁用列表（函数级 import 避免循环依赖）
    skip_names: set[str] = set()
    try:
        from souwen.plugin_manager import _load_state

        skip_names = set(_load_state().get("disabled_plugins", []))
        if skip_names:
            logger.info("插件禁用列表: %s", ", ".join(sorted(skip_names)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取插件禁用列表失败，将加载所有插件: %s", exc)

    try:
        loaded, errors = discover_entrypoint_plugins(skip_names=skip_names)
        all_loaded.extend(loaded)
        all_errors.extend(errors)
    except Exception as exc:  # noqa: BLE001 — 兜底，绝不让插件系统拖垮宿主
        logger.warning("entry points 插件发现整体失败: %s", exc)
        all_errors.append({"source": "entry_points", "name": "<discover>", "error": str(exc)})

    if config is not None:
        try:
            paths = list(getattr(config, "plugins", []) or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取 config.plugins 失败: %s", exc)
            paths = []
        if paths:
            try:
                loaded, errors = load_config_plugins(paths, skip_names=skip_names)
                all_loaded.extend(loaded)
                all_errors.extend(errors)
            except Exception as exc:  # noqa: BLE001
                logger.warning("配置插件加载整体失败: %s", exc)
                all_errors.append({"source": "config", "name": "<load>", "error": str(exc)})

    return {"loaded": all_loaded, "errors": all_errors}


__all__ = [
    "ENTRY_POINT_GROUP",
    "HealthCheck",
    "LifecycleHook",
    "Plugin",
    "discover_entrypoint_plugins",
    "get_loaded_plugins",
    "load_config_plugins",
    "load_plugins",
    "unload_plugin",
]
