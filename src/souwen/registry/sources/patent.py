"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
    _P_PER_PAGE,
    _P_SIZE,
    _P_NUM_RESULTS,
    _P_N_RESULTS,
    _P_RANGE_END,
    _patentsview_pre_call,
)

# ═════════════════════════════════════════════════════════════
#  2. patent（8 源）
# ═════════════════════════════════════════════════════════════


_reg(
    SourceAdapter(
        name="patentsview",
        domain="patent",
        integration="open_api",
        description="PatentsView 美国专利 (待修复)",
        config_field=None,
        client_loader=lazy("souwen.patent.patentsview:PatentsViewClient"),
        methods={
            "search": MethodSpec(
                "search",
                _P_PER_PAGE,
                pre_call=_patentsview_pre_call,
            ),
        },
        # "待修复"状态，默认 public catalog 不展示
        catalog_visibility="hidden",
        stability="deprecated",
        usage_note="公开搜索端点已变更，当前接入待修复",
    )
)

_reg(
    SourceAdapter(
        name="pqai",
        domain="patent",
        integration="open_api",
        description="PQAI 专利语义搜索 (待修复)",
        config_field=None,
        client_loader=lazy("souwen.patent.pqai:PqaiClient"),
        methods={"search": MethodSpec("search", _P_N_RESULTS)},
        catalog_visibility="hidden",
        stability="deprecated",
        usage_note="匿名 API 当前返回 401，暂不建议默认使用",
    )
)

_reg(
    SourceAdapter(
        name="epo_ops",
        domain="patent",
        integration="official_api",
        description="EPO OPS 欧洲专利局",
        config_field="epo_consumer_key",
        credential_fields=("epo_consumer_key", "epo_consumer_secret"),
        client_loader=lazy("souwen.patent.epo_ops:EpoOpsClient"),
        # epo_ops 的方法是 search(cql_query, range_end)
        methods={"search": MethodSpec("search", _P_RANGE_END)},
    )
)

_reg(
    SourceAdapter(
        name="uspto_odp",
        domain="patent",
        integration="official_api",
        description="USPTO ODP 美国专利局",
        config_field="uspto_api_key",
        client_loader=lazy("souwen.patent.uspto_odp:UsptoOdpClient"),
        # 方法名是 search_applications，统一到 'search' capability
        methods={"search": MethodSpec("search_applications", _P_PER_PAGE)},
    )
)

_reg(
    SourceAdapter(
        name="the_lens",
        domain="patent",
        integration="official_api",
        description="The Lens 专利+学术",
        config_field="lens_api_token",
        client_loader=lazy("souwen.patent.the_lens:TheLensClient"),
        methods={"search": MethodSpec("search_patents", _P_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="cnipa",
        domain="patent",
        integration="official_api",
        description="CNIPA 中国国知局",
        config_field="cnipa_client_id",
        credential_fields=("cnipa_client_id", "cnipa_client_secret"),
        client_loader=lazy("souwen.patent.cnipa:CnipaClient"),
        methods={"search": MethodSpec("search", _P_PER_PAGE)},
    )
)

_reg(
    SourceAdapter(
        name="patsnap",
        domain="patent",
        integration="official_api",
        description="PatSnap 智慧芽",
        config_field="patsnap_api_key",
        client_loader=lazy("souwen.patent.patsnap:PatSnapClient"),
        methods={"search": MethodSpec("search")},  # limit → limit
    )
)

_reg(
    SourceAdapter(
        name="google_patents",
        domain="patent",
        integration="scraper",
        description="Google Patents 爬虫",
        config_field=None,
        # v1 统一：由 GooglePatentsScraper 承担（P1 阶段会合并到 patent/google_patents.py）
        client_loader=lazy("souwen.patent.google_patents_scraper:GooglePatentsScraper"),
        methods={"search": MethodSpec("search", _P_NUM_RESULTS)},
        default_for=frozenset({"patent:search"}),
        risk_level="medium",
        risk_reasons=frozenset({"anti_scraping", "captcha", "requires_browser"}),
        stability="experimental",
        usage_note="实验性爬虫，易受反爬影响",
    )
)
