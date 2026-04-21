"""registry/loader.py — Client 类的字符串懒加载

为什么需要懒加载：
  registry 模块如果在 import 时直接加载所有 80+ 个 Client，会显著拖慢启动时间
  （每个 Client 都可能带一堆 httpx / curl_cffi / playwright 依赖）。

  改用字符串懒加载后：
  - registry 自身只依赖 dataclasses + typing
  - Client 的 import 推迟到门面真正要调用它时
  - 支持循环模块结构（registry ↔ domain）
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from functools import lru_cache


@lru_cache(maxsize=None)
def _import_by_path(import_path: str) -> type:
    """按 'module.path:ClassName' 字符串导入类（带 LRU 缓存）。

    缓存语义：每个 import_path 只解析一次；后续调用直接拿缓存结果。
    这对于一个 Client 被多次搜索调用的场景很有价值。
    """
    module_path, _, class_name = import_path.partition(":")
    if not module_path or not class_name:
        raise ValueError(
            f"lazy() 参数必须是 'module.path:ClassName' 形式，得到 {import_path!r}"
        )
    module = importlib.import_module(module_path)
    try:
        obj = getattr(module, class_name)
    except AttributeError as exc:
        raise ImportError(
            f"无法从模块 {module_path!r} 获取 {class_name!r}：{exc}"
        ) from exc
    if not isinstance(obj, type):
        raise TypeError(
            f"lazy({import_path!r}) 期望得到类，实际得到 {type(obj).__name__}"
        )
    return obj


def lazy(import_path: str) -> Callable[[], type]:
    """形如 'souwen.paper.openalex:OpenAlexClient' 的字符串 → 零参函数。

    调用返回的函数会真正触发 import，并返回 Client 类本身。

    Example:
        >>> loader = lazy("souwen.paper.openalex:OpenAlexClient")
        >>> OpenAlexClient = loader()   # 此刻才 import
        >>> async with OpenAlexClient() as client: ...

    Args:
        import_path: 'module.path:ClassName' 字符串。

    Returns:
        zero-arg 函数，调用返回类对象。
    """

    def _load() -> type:
        return _import_by_path(import_path)

    _load.__name__ = f"lazy[{import_path}]"
    _load.__qualname__ = _load.__name__
    return _load
