"""SouWen 最小插件示例。

演示如何创建一个 SouWen 外部插件，注册数据源和 fetch handler。
此插件仅返回 echo 结果，不依赖任何第三方服务。
"""

from __future__ import annotations

import logging

from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.loader import lazy

logger = logging.getLogger(__name__)

plugin = SourceAdapter(
    name="example_echo",
    domain="fetch",
    integration="scraper",
    description="示例插件：echo 返回原始 URL（仅用于演示插件对接规范）",
    config_field=None,
    client_loader=lazy("souwen_example_plugin.client:EchoClient"),
    methods={"fetch": MethodSpec("fetch")},
    needs_config=False,
    default_enabled=False,  # 示例插件默认不启用
    tags=frozenset({"external_plugin", "example"}),
)

# Auto-register fetch handler when loaded by SouWen's plugin discovery
try:
    from .handler import register

    register()
except ImportError as exc:
    logger.warning("可选 fetch handler 注册不可用: %s", exc, exc_info=True)
except Exception as exc:
    logger.warning("可选 fetch handler 注册失败: %s", exc, exc_info=True)
