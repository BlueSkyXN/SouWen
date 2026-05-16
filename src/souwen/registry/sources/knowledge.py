"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
    _P_MAX_RESULTS,
)

# ═════════════════════════════════════════════════════════════
#  8. knowledge（1 源：Wikipedia；DeepWiki 归 fetch）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="wikipedia",
        domain="knowledge",
        integration="open_api",
        description="Wikipedia 百科搜索",
        config_field=None,
        client_loader=lazy("souwen.web.wikipedia:WikipediaClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"knowledge:search"}),
    )
)
