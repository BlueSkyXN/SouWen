"""archive/ — 档案/历史域（v1）

Wayback 在 v1 独立为 archive domain（主 domain），同时保留在 fetch 提供者清单里
（extra_domains={"fetch"}）。
"""

from souwen.web.wayback import WaybackClient

__all__ = ["WaybackClient"]
