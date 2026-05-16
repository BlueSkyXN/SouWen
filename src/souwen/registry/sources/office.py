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
# 11. office（1 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="feishu_drive",
        domain="office",
        integration="official_api",
        description="飞书云文档搜索 (需 App ID + App Secret)",
        config_field="feishu_app_id",
        credential_fields=("feishu_app_id", "feishu_app_secret"),
        client_loader=lazy("souwen.web.feishu_drive:FeishuDriveClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)
