"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
    _P_PER_PAGE,
    _P_ROWS,
    _P_RETMAX,
    _P_SIZE,
    _P_HITS,
    _P_TOP_N,
    _P_MAX_RESULTS,
    _P_PAGE_SIZE,
)

# ═════════════════════════════════════════════════════════════
#  1. paper（19 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="openalex",
        domain="paper",
        integration="open_api",
        description="OpenAlex 开放学术数据",
        config_field="openalex_email",  # 可选 email（提升速率限制）
        needs_config=False,  # 零配置可用
        optional_credential_effect="politeness",
        client_loader=lazy("souwen.paper.openalex:OpenAlexClient"),
        methods={"search": MethodSpec("search", _P_PER_PAGE)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="semantic_scholar",
        domain="paper",
        integration="official_api",
        description="Semantic Scholar API",
        config_field="semantic_scholar_api_key",
        needs_config=False,  # 免 Key 可试用
        optional_credential_effect="rate_limit",
        client_loader=lazy("souwen.paper.semantic_scholar:SemanticScholarClient"),
        methods={"search": MethodSpec("search")},  # limit → limit 同名
    )
)

_reg(
    SourceAdapter(
        name="crossref",
        domain="paper",
        integration="open_api",
        description="CrossRef 跨库检索",
        config_field=None,
        client_loader=lazy("souwen.paper.crossref:CrossrefClient"),
        methods={"search": MethodSpec("search", _P_ROWS)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="arxiv",
        domain="paper",
        integration="open_api",
        description="arXiv 预印本",
        config_field=None,
        client_loader=lazy("souwen.paper.arxiv:ArxivClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="dblp",
        domain="paper",
        integration="open_api",
        description="DBLP 计算机科学文献",
        config_field=None,
        client_loader=lazy("souwen.paper.dblp:DblpClient"),
        methods={"search": MethodSpec("search", _P_HITS)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="core",
        domain="paper",
        integration="official_api",
        description="CORE 开放获取聚合",
        config_field="core_api_key",
        client_loader=lazy("souwen.paper.core:CoreClient"),
        methods={"search": MethodSpec("search")},  # limit → limit
    )
)

_reg(
    SourceAdapter(
        name="pubmed",
        domain="paper",
        integration="open_api",
        description="PubMed 生物医学",
        config_field=None,
        client_loader=lazy("souwen.paper.pubmed:PubMedClient"),
        methods={"search": MethodSpec("search", _P_RETMAX)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="biorxiv",
        domain="paper",
        integration="open_api",
        description="bioRxiv/medRxiv 生物医学预印本",
        config_field=None,
        client_loader=lazy("souwen.paper.biorxiv:BioRxivClient"),
        methods={"search": MethodSpec("search", _P_PER_PAGE)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="zotero",
        domain="paper",
        integration="official_api",
        description="Zotero 个人文献库搜索 (需 API Key + Library ID)",
        config_field="zotero_api_key",
        credential_fields=("zotero_api_key", "zotero_library_id"),
        client_loader=lazy("souwen.paper.zotero:ZoteroClient"),
        methods={"search": MethodSpec("search")},  # limit → limit
    )
)

_reg(
    SourceAdapter(
        name="huggingface",
        domain="paper",
        integration="open_api",
        description="HuggingFace Papers 社区精选（语义搜索 + 热度排行，无需 Key）",
        config_field=None,
        client_loader=lazy("souwen.paper.huggingface:HuggingFaceClient"),
        methods={"search": MethodSpec("search", _P_TOP_N)},
    )
)

_reg(
    SourceAdapter(
        name="europepmc",
        domain="paper",
        integration="open_api",
        description="Europe PMC 欧洲生物医学文献",
        config_field=None,
        client_loader=lazy("souwen.paper.europepmc:EuropePmcClient"),
        methods={"search": MethodSpec("search", _P_PAGE_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="pmc",
        domain="paper",
        integration="open_api",
        description="PubMed Central 生物医学全文",
        config_field=None,
        client_loader=lazy("souwen.paper.pmc:PmcClient"),
        methods={"search": MethodSpec("search", _P_RETMAX)},
    )
)

_reg(
    SourceAdapter(
        name="doaj",
        domain="paper",
        integration="official_api",
        description="DOAJ 开放获取期刊目录（可选 Key）",
        config_field="doaj_api_key",
        needs_config=False,  # 可选 Key
        optional_credential_effect="rate_limit",
        client_loader=lazy("souwen.paper.doaj:DoajClient"),
        methods={"search": MethodSpec("search", _P_PAGE_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="zenodo",
        domain="paper",
        integration="official_api",
        description="Zenodo CERN 开放科学仓库（可选 Token）",
        config_field="zenodo_access_token",
        needs_config=False,  # 可选 Token
        optional_credential_effect="quota",
        client_loader=lazy("souwen.paper.zenodo:ZenodoClient"),
        methods={"search": MethodSpec("search", _P_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="hal",
        domain="paper",
        integration="open_api",
        description="HAL 法国开放档案（Solr API）",
        config_field=None,
        client_loader=lazy("souwen.paper.hal:HalClient"),
        methods={"search": MethodSpec("search", _P_ROWS)},
    )
)

_reg(
    SourceAdapter(
        name="openaire",
        domain="paper",
        integration="official_api",
        description="OpenAIRE 欧盟研究基础设施（可选 Key）",
        config_field="openaire_api_key",
        needs_config=False,  # 可选 Key
        optional_credential_effect="quota",
        client_loader=lazy("souwen.paper.openaire:OpenAireClient"),
        methods={"search": MethodSpec("search", _P_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="iacr",
        domain="paper",
        integration="scraper",
        description="IACR ePrint 密码学预印本（实验性 HTML 爬虫）",
        config_field=None,
        client_loader=lazy("souwen.paper.iacr:IacrClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        risk_level="medium",
        risk_reasons=frozenset({"unstable_html"}),
        stability="experimental",
    )
)

_reg(
    SourceAdapter(
        name="ieee_xplore",
        domain="paper",
        integration="official_api",
        description="IEEE Xplore 电气电子工程文献",
        config_field="ieee_api_key",
        client_loader=lazy("souwen.paper.ieee_xplore:IeeeXploreClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="unpaywall",
        domain="paper",
        integration="official_api",
        description="Unpaywall OA 查找",
        config_field="unpaywall_email",
        needs_config=True,  # 客户端初始化会要求 email
        client_loader=lazy("souwen.paper.unpaywall:UnpaywallClient"),
        # unpaywall 没有 search 方法，只有 find_oa(doi)；用命名空间声明（D8）
        methods={"unpaywall:find_oa": MethodSpec("find_oa")},
        # 不参与 search 调度，默认 public catalog 不展示
        catalog_visibility="hidden",
        usage_note="仅支持 DOI OA 查找",
    )
)
