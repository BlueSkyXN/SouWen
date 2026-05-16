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
#  9. developer（2 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="github",
        domain="developer",
        integration="open_api",
        description="GitHub 仓库搜索 (可选 Token)",
        config_field="github_token",
        needs_config=False,  # Token 可选
        optional_credential_effect="rate_limit",
        client_loader=lazy("souwen.web.github:GitHubClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"developer:search"}),
    )
)

_reg(
    SourceAdapter(
        name="stackoverflow",
        domain="developer",
        integration="open_api",
        description="StackOverflow 问答搜索",
        config_field="stackoverflow_api_key",
        needs_config=False,  # Key 可选
        optional_credential_effect="quota",
        client_loader=lazy("souwen.web.stackoverflow:StackOverflowClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"developer:search"}),
    )
)
