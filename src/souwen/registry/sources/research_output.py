"""Built-in research-output source declarations."""

from __future__ import annotations

from souwen.registry.sources._helpers import MethodSpec, SourceAdapter, _P_PER_PAGE, _reg, lazy


_reg(
    SourceAdapter(
        name="datacite",
        domain="research_output",
        category="research_output",
        integration="official_api",
        description="DataCite DOI 元数据：数据集、软件、文本、活动等科研产出（官方匿名 REST API）",
        config_field=None,
        auth_requirement="none",
        risk_level="low",
        distribution="core",
        stability="stable",
        usage_note=(
            "仅返回 DataCite 元数据、landing page 与声明 content URL；不验证链接可访问性，"
            "不下载文件，也不由 rights metadata 推断再分发权。"
        ),
        client_loader=lazy("souwen.research_output.datacite:DataCiteClient"),
        methods={"search": MethodSpec("search", _P_PER_PAGE)},
        default_for=frozenset({"research_output:search"}),
    )
)
