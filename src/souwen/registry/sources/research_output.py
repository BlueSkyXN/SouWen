"""Built-in research-output source declarations."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    _P_PAGE_SIZE,
    _P_PER_PAGE,
    _reg,
    lazy,
)


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


_reg(
    SourceAdapter(
        name="figshare",
        domain="research_output",
        category="research_output",
        integration="official_api",
        description="Figshare public article 元数据、license 与声明 file links（官方匿名 API v2）",
        config_field=None,
        auth_requirement="none",
        risk_level="low",
        distribution="core",
        stability="stable",
        usage_note=(
            "仅查询公开 article metadata；search 不逐条请求 detail。file download URL、license 和 "
            "link-only 标记均为上游声明，SouWen 不跟随、下载或验证访问/再分发权限。"
        ),
        client_loader=lazy("souwen.research_output.figshare:FigshareClient"),
        methods={
            "search": MethodSpec("search", _P_PAGE_SIZE),
            "get_detail": MethodSpec("get_by_id", {"id": "article_id"}),
        },
        default_for=frozenset(),
    )
)
