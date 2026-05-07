"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
)

# ═════════════════════════════════════════════════════════════
# 12. archive（Wayback，主 domain=archive，extra_domains={"fetch"}）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="wayback",
        domain="archive",
        integration="open_api",
        description="Internet Archive Wayback (免费)",
        config_field=None,
        client_loader=lazy("souwen.web.wayback:WaybackClient"),
        extra_domains=frozenset({"fetch"}),
        methods={
            "archive_lookup": MethodSpec("query_snapshots"),
            "archive_save": MethodSpec("save_page"),
            "fetch": MethodSpec("fetch"),
        },
        default_for=frozenset({"archive:archive_lookup"}),
    )
)
