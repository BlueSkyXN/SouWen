"""registry/capabilities.py — capability 与 domain 常量再导出

从 adapter.py 再导出便于 `from souwen.registry.capabilities import CAPABILITIES` 这种
直觉的 import。adapter.py 是真实定义处。
"""

from __future__ import annotations

from souwen.registry.adapter import (
    CAPABILITIES,
    DOMAINS,
    FETCH_DOMAIN,
    INTEGRATIONS,
)

__all__ = ["CAPABILITIES", "DOMAINS", "FETCH_DOMAIN", "INTEGRATIONS"]
