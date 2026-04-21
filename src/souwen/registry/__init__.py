"""SouWen 数据源注册表 — 单一事实源

v1 架构的核心：所有数据源的元数据 + 执行适配都在这里声明。

新增一个源的代价从 v0 的"改 7 处"降到"改 1-2 处"：
  1. 实现 Client 类
  2. 在 sources.py 里 _reg(SourceAdapter(...))
  3. （若需 API Key）在 config.py 的 SouWenConfig 加字段

所有其他消费者（门面 / CLI / 服务端 / 前端 / 文档）都从注册表派生。

公开 API：
    - SourceAdapter / MethodSpec / DOMAINS / FETCH_DOMAIN / CAPABILITIES / INTEGRATIONS
      —— 核心数据类与常量（adapter.py）
    - lazy —— 客户端类的字符串懒加载（loader.py）
    - get / all_adapters / by_domain / by_capability / by_domain_and_capability /
      defaults_for / all_domains / all_capabilities / fetch_providers / high_risk_sources /
      enum_values / as_all_sources_dict
      —— 查询视图（views.py）

设计参见 `local/v1-初步定义.md §5` 与 `local/重构计划.md §1.3`。
"""

from __future__ import annotations

from souwen.registry.adapter import (
    CAPABILITIES,
    DOMAINS,
    FETCH_DOMAIN,
    INTEGRATIONS,
    MethodSpec,
    SourceAdapter,
)
from souwen.registry.loader import lazy
from souwen.registry.views import (
    all_adapters,
    all_capabilities,
    all_domains,
    as_all_sources_dict,
    by_capability,
    by_domain,
    by_domain_and_capability,
    defaults_for,
    enum_values,
    fetch_providers,
    get,
    high_risk_sources,
)

# 触发 sources.py 的 import，填充 _REGISTRY。
# 这一步**必须**在所有视图符号 import 之后，因为 sources.py 里会调用 views._reg。
from souwen.registry import sources as _sources  # noqa: F401,E402

__all__ = [
    # 常量与数据类
    "SourceAdapter",
    "MethodSpec",
    "DOMAINS",
    "FETCH_DOMAIN",
    "CAPABILITIES",
    "INTEGRATIONS",
    # 懒加载
    "lazy",
    # 视图
    "get",
    "all_adapters",
    "by_domain",
    "by_capability",
    "by_domain_and_capability",
    "defaults_for",
    "all_domains",
    "all_capabilities",
    "fetch_providers",
    "high_risk_sources",
    "enum_values",
    "as_all_sources_dict",
]
