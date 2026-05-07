"""Built-in source declarations.

Source adapters live in category/domain modules so each catalog segment stays
small enough to review. Import order is behavioral: it preserves registry
insertion order, which also drives default source ordering in runtime views.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType


def _import_segment(name: str) -> ModuleType:
    return import_module(f"{__name__}.{name}")


_import_segment("paper")
_import_segment("patent")
_web_general = _import_segment("web_general")
_import_segment("web_professional")
_web_general.register_self_hosted()
_import_segment("social")
_import_segment("video")
_import_segment("knowledge")
_import_segment("developer")
_import_segment("cn_tech")
_import_segment("office")
_import_segment("archive")
_import_segment("fetch")

__all__ = ()
