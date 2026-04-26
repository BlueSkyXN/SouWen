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
  - 单个 `SourceAdapter` 实例
  - 返回 `SourceAdapter` 的零参 callable（工厂函数）
  - `SourceAdapter` 列表/元组（一次注册多个源）

加载失败（导入异常、类型不符、与内置源重名等）只记录警告，
**绝不**让宿主程序崩溃。
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable
from importlib import metadata
from typing import TYPE_CHECKING, Any

from souwen.registry.adapter import SourceAdapter
from souwen.registry.views import _reg_external

if TYPE_CHECKING:
    from souwen.config.models import SouWenConfig

logger = logging.getLogger("souwen.plugin")

ENTRY_POINT_GROUP = "souwen.plugins"


def _coerce_to_adapters(obj: Any) -> list[SourceAdapter]:
    """把入口对象统一转成 `list[SourceAdapter]`。

    支持的形态：
      - SourceAdapter 实例
      - 零参 callable，调用后返回上述任一形态
      - list/tuple，元素为 SourceAdapter

    类型不符时抛 TypeError，由调用方捕获。
    """
    if callable(obj) and not isinstance(obj, SourceAdapter):
        obj = obj()

    if isinstance(obj, SourceAdapter):
        return [obj]

    if isinstance(obj, (list, tuple)):
        adapters: list[SourceAdapter] = []
        for item in obj:
            if not isinstance(item, SourceAdapter):
                raise TypeError(
                    f"插件返回的列表包含非 SourceAdapter 元素: {type(item).__name__}"
                )
            adapters.append(item)
        return adapters

    raise TypeError(
        f"插件入口必须是 SourceAdapter / 返回它的 callable / 其列表，得到 {type(obj).__name__}"
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
            logger.warning(
                "注册插件源 %r (来自 %s) 失败: %s", adapter.name, source_label, exc
            )
            errors.append({"source": source_label, "name": adapter.name, "error": str(exc)})
            continue
        if ok:
            loaded.append(adapter.name)
            logger.info("已加载插件源 %r (来自 %s)", adapter.name, source_label)


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
) -> tuple[list[str], list[dict[str, str]]]:
    """通过 entry points 发现并注册插件。

    Args:
        group: entry point 分组名，默认 `"souwen.plugins"`。

    Returns:
        `(loaded_names, errors)` 二元组。
    """
    loaded: list[str] = []
    errors: list[dict[str, str]] = []

    try:
        eps = metadata.entry_points()
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 entry points 失败: %s", exc)
        return loaded, errors

    # Python 3.10+: EntryPoints 对象有 .select()；旧版本是 dict
    if hasattr(eps, "select"):
        candidates = list(eps.select(group=group))
    else:  # pragma: no cover — 兼容老接口
        candidates = list(eps.get(group, []))  # type: ignore[union-attr]

    for ep in candidates:
        ep_name = getattr(ep, "name", "<unknown>")
        label = f"entry_point:{ep_name}"
        try:
            obj = ep.load()
            adapters = _coerce_to_adapters(obj)
        except Exception as exc:  # noqa: BLE001
            logger.warning("加载插件 entry point %r 失败: %s", ep_name, exc)
            errors.append({"source": label, "name": ep_name, "error": str(exc)})
            continue
        _register_adapters(adapters, source_label=label, loaded=loaded, errors=errors)

    return loaded, errors


def load_config_plugins(
    plugin_paths: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    """从 `"module.path:attribute"` 字符串列表加载插件。

    用于处理 YAML 配置 / 环境变量里手动声明的插件。
    """
    loaded: list[str] = []
    errors: list[dict[str, str]] = []

    for path in plugin_paths or []:
        if not isinstance(path, str) or not path.strip():
            logger.warning("跳过非法的插件路径: %r", path)
            continue
        path = path.strip()
        label = f"config:{path}"
        try:
            obj = _resolve_dotted_path(path)
            adapters = _coerce_to_adapters(obj)
        except Exception as exc:  # noqa: BLE001
            logger.warning("加载配置插件 %r 失败: %s", path, exc)
            errors.append({"source": label, "name": path, "error": str(exc)})
            continue
        _register_adapters(adapters, source_label=label, loaded=loaded, errors=errors)

    return loaded, errors


def load_plugins(config: SouWenConfig | None = None) -> dict[str, Any]:
    """加载所有插件（entry points + 配置文件指定）。

    这是面向 `souwen.registry` 的统一入口，应该在内置源注册完成后调用。

    Args:
        config: 可选的 `SouWenConfig`。提供则会读取其 `plugins` 字段。
            为 None 时只做 entry points 发现，避免在 registry 初始化期间
            循环导入 config 模块。

    Returns:
        ``{"loaded": [...名称], "errors": [...]}``。即使全部失败也不抛异常。
    """
    all_loaded: list[str] = []
    all_errors: list[dict[str, str]] = []

    try:
        loaded, errors = discover_entrypoint_plugins()
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
                loaded, errors = load_config_plugins(paths)
                all_loaded.extend(loaded)
                all_errors.extend(errors)
            except Exception as exc:  # noqa: BLE001
                logger.warning("配置插件加载整体失败: %s", exc)
                all_errors.append(
                    {"source": "config", "name": "<load>", "error": str(exc)}
                )

    return {"loaded": all_loaded, "errors": all_errors}


__all__ = [
    "ENTRY_POINT_GROUP",
    "discover_entrypoint_plugins",
    "load_config_plugins",
    "load_plugins",
]
