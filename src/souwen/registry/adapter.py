"""registry/adapter.py — SourceAdapter + MethodSpec + 常量

SourceAdapter 是架构的最小数据源单元，统一承载：
  - 元数据（name / domain / integration / config_field / description）
  - 执行适配（method_specs / param_map / client_loader）
  - 默认源声明（default_for）

设计见 `local/v1-初步定义.md §5`。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

# ── 常量 ────────────────────────────────────────────────────

#: 业务领域（10 个）
DOMAINS: frozenset[str] = frozenset(
    {
        "paper",
        "patent",
        "web",
        "social",
        "video",
        "knowledge",
        "developer",
        "cn_tech",
        "office",
        "archive",
    }
)

#: 横切能力（不是独立领域）
FETCH_DOMAIN: str = "fetch"

#: 11 个标准 capability。超出的（如 Exa 的 find_similar）采用命名空间前缀（D8）。
CAPABILITIES: frozenset[str] = frozenset(
    {
        "search",
        "search_news",
        "search_images",
        "search_videos",
        "search_articles",
        "search_users",
        "get_detail",
        "get_trending",
        "get_transcript",
        "fetch",
        "archive_lookup",
        "archive_save",
    }
)

#: 集成类型：描述"怎么接入"，不描述鉴权强度。
INTEGRATIONS: frozenset[str] = frozenset(
    {
        "open_api",
        "scraper",
        "official_api",
        "self_hosted",
    }
)

#: 鉴权/配置要求：描述"运行前需要什么凭据或实例"。
AUTH_REQUIREMENTS: frozenset[str] = frozenset(
    {
        "none",
        "optional",
        "required",
        "self_hosted",
    }
)

#: 可选凭据带来的主要收益。
OPTIONAL_CREDENTIAL_EFFECTS: frozenset[str] = frozenset(
    {
        "rate_limit",
        "quota",
        "quality",
        "personalization",
        "private_access",
        "write_access",
        "politeness",
        "unknown",
    }
)

#: 风险等级：影响默认启用、默认搜索、文档提示，不等同于 integration。
RISK_LEVELS: frozenset[str] = frozenset({"low", "medium", "high"})

#: 风险原因标签。用于解释为什么一个源不适合默认调度。
RISK_REASONS: frozenset[str] = frozenset(
    {
        "anti_scraping",
        "account_ban",
        "ip_block",
        "captcha",
        "quota_cost",
        "legal_tos",
        "unstable_html",
        "requires_browser",
        "geo_sensitive",
        "rate_limit",
        "unknown",
    }
)

#: 分发范围：描述推荐安装/治理边界，不代表源码一定物理拆包。
DISTRIBUTIONS: frozenset[str] = frozenset({"core", "extra", "plugin"})

#: 接入成熟度。
STABILITIES: frozenset[str] = frozenset({"stable", "beta", "experimental", "deprecated"})


# ── 数据类 ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MethodSpec:
    """一个 capability 在具体 Client 上的调用适配。

    绝大多数源用声明式 param_map（{"limit": "per_page"} 这种）。
    极少数需要复杂变换（如 PatentsView 的 query = {"_contains": {"patent_title": q}}）
    使用 pre_call 回调逃生舱。

    Attributes:
        method_name: Client 实例上的方法名（如 'search' / 'search_articles' / 'get_transcript'）。
        param_map: 统一入参名 → 源原生参数名的映射。未映射的按原名传。
            常用映射：limit → per_page/rows/retmax/size/hits/top_n/max_results/num_results/n_results/
                     page_size/range_end
        pre_call: 对 resolve_params 结果做最终变换的函数（如重命名 query → cql_query，或把
            query 包装为 {"_contains": {...}} 结构）。返回最终传给方法的 kwargs。
    """

    method_name: str
    param_map: Mapping[str, str] = field(default_factory=dict)
    pre_call: Callable[[dict[str, Any]], dict[str, Any]] | None = None


@dataclass(frozen=True, slots=True)
class SourceAdapter:
    """数据源的完整声明——v1 单一事实源的核心单元。

    设计原则：
      - **不可变**（frozen=True, slots=True）：保证注册后不被意外篡改。
      - **懒加载 Client**：`client_loader` 是 `lazy("path:Class")` 返回的函数，
        注册表模块导入时不触发业务层 import，避免启动变慢。
      - **声明优先**：`methods` 是 `capability → MethodSpec` 的映射，门面直接查表派发。

    Attributes:
        name: 源的唯一标识（如 'openalex' / 'tavily'）。
        domain: 主领域（属于 DOMAINS 或等于 FETCH_DOMAIN）。
        integration: 集成类型（属于 INTEGRATIONS）。
        description: UI / 文档用的描述文案。
        config_field: 对应 `SouWenConfig` 的字段名；None 表示零配置。
        client_loader: 返回 Client 类的 zero-arg 函数（通常由 `lazy()` 产出）。
        methods: capability → MethodSpec 的映射。门面通过 `adapter.methods["search"]` 派发。
        extra_domains: 跨域能力。如 Tavily 主 domain=web，extra_domains={"fetch"}。
            v1 初期仅允许目标为 "fetch"。
        default_enabled: UI / CLI 默认是否勾选。高风险源（如 google / twitter / baidu）设 False。
        default_for: 形如 {"paper:search"}，声明在哪些 (domain, capability) 下作为默认源（D9）。
        tags: 预留标签集合，如 {"high_risk"}（D10）/ {"ai_summarize"} / {"chinese_friendly"}。
        needs_config: 是否"**必须**配置才能工作"（API Key 类；注意不等同于 `config_field is not None`，
            因为 openalex / github / doaj 等有**可选**配置字段）。默认按 integration 推断但可覆盖。
        auth_requirement: 鉴权/配置要求；None 表示从旧字段派生，便于渐进迁移。
        credential_fields: 完整凭据字段。多字段 OAuth 源应列全，如 ("client_id", "client_secret")。
        optional_credential_effect: 可选凭据的收益，如提高 rate limit 或解锁个性化能力。
        risk_level / risk_reasons: 风险等级与原因，兼容旧 tag high_risk。
        distribution / package_extra: 推荐分发范围与 optional dependency 组。
        stability: 源的成熟度。v0_all_sources:exclude 会被视为 experimental。
    """

    name: str
    domain: str
    integration: str
    description: str
    config_field: str | None
    client_loader: Callable[[], type]
    methods: Mapping[str, MethodSpec]
    extra_domains: frozenset[str] = field(default_factory=frozenset)
    default_enabled: bool = True
    default_for: frozenset[str] = field(default_factory=frozenset)
    tags: frozenset[str] = field(default_factory=frozenset)
    needs_config: bool | None = None
    # None 表示从 (integration, config_field) 推断；测试里可用 `resolved_needs_config` 取确定值
    auth_requirement: str | None = None
    credential_fields: tuple[str, ...] = ()
    optional_credential_effect: str | None = None
    risk_level: str = "low"
    risk_reasons: frozenset[str] = field(default_factory=frozenset)
    distribution: str = "core"
    package_extra: str | None = None
    stability: str = "stable"

    @property
    def capabilities(self) -> frozenset[str]:
        """该源支持的 capability 集合。"""
        return frozenset(self.methods.keys())

    @property
    def domains(self) -> frozenset[str]:
        """该源涉及的 domain 集合（主 + extra）。"""
        return frozenset({self.domain}) | self.extra_domains

    @property
    def is_scraper(self) -> bool:
        """是否爬虫类源（需要 curl_cffi TLS 指纹支持）。"""
        return self.integration == "scraper"

    @property
    def resolved_needs_config(self) -> bool:
        """确定性的 needs_config：显式值优先，否则从鉴权口径推断。

        推断规则：
          - explicit needs_config → 原样采用
          - required → True
          - self_hosted 且存在配置字段 → True
          - none / optional → False
          - 注意：`openalex` / `github` / `doaj` / `zenodo` / `openaire` 等
            integration=official_api 但 Key 是"可选"的源，声明时需显式传 `needs_config=False`。
        """
        if self.needs_config is not None:
            return self.needs_config
        requirement = self.resolved_auth_requirement
        if requirement == "required":
            return True
        if requirement == "self_hosted":
            return bool(self.resolved_credential_fields)
        return False

    @property
    def resolved_auth_requirement(self) -> str:
        """确定性的鉴权/配置要求。

        新字段 `auth_requirement` 显式声明时优先；未声明时从旧的
        integration/config_field/needs_config 组合派生，保证外部插件兼容。
        """
        if self.auth_requirement is not None:
            return self.auth_requirement
        if self.needs_config is not None:
            if self.needs_config:
                return "self_hosted" if self.integration == "self_hosted" else "required"
            return "optional" if self.config_field or self.credential_fields else "none"
        if self.integration == "self_hosted":
            return "self_hosted"
        if self.config_field is None:
            return "none"
        if self.integration == "official_api":
            return "required"
        return "optional"

    @property
    def resolved_credential_fields(self) -> tuple[str, ...]:
        """返回完整凭据字段列表；未显式列出时回退到 config_field。"""
        if self.credential_fields:
            return self.credential_fields
        if self.config_field:
            return (self.config_field,)
        return ()

    @property
    def resolved_risk_level(self) -> str:
        """兼容旧 high_risk tag 的风险等级。"""
        if "high_risk" in self.tags:
            return "high"
        return self.risk_level

    @property
    def resolved_risk_reasons(self) -> frozenset[str]:
        """返回风险原因；旧 high_risk tag 只提升风险等级，不臆造原因。"""
        return frozenset(self.risk_reasons)

    @property
    def resolved_package_extra(self) -> str | None:
        """推荐 optional dependency 组。"""
        if self.package_extra:
            return self.package_extra
        if self.integration == "scraper":
            return "scraper"
        return None

    @property
    def resolved_distribution(self) -> str:
        """推荐分发范围。

        显式字段优先；否则把依赖 optional extra 的内置源归到 extra。
        外部插件会由 SourceMeta 视图按 external_plugins() 进一步标记为 plugin。
        """
        if self.distribution != "core":
            return self.distribution
        if self.resolved_package_extra:
            return "extra"
        return "core"

    @property
    def resolved_stability(self) -> str:
        """兼容 v0 排除标签的成熟度。"""
        if "v0_all_sources:exclude" in self.tags and self.stability == "stable":
            return "experimental"
        return self.stability

    def resolve_params(
        self,
        method_spec: MethodSpec,
        /,
        **unified_kwargs: Any,
    ) -> dict[str, Any]:
        """把统一入参翻译为源原生参数。

        执行流程：
          1. `param_map` 重命名：如 `limit → per_page`。
          2. `pre_call`（若有）做最终变换。

        Args:
            method_spec: 要调用的 MethodSpec（从 self.methods 查）。
            **unified_kwargs: 统一入参，如 query="foo", limit=10, page=1。

        Returns:
            直接可 `**kwargs` 传给 Client 方法的 dict。
        """
        native: dict[str, Any] = {}
        for key, val in unified_kwargs.items():
            native_key = method_spec.param_map.get(key, key)
            native[native_key] = val
        if method_spec.pre_call is not None:
            native = method_spec.pre_call(native)
        return native

    def __post_init__(self) -> None:
        """注册时期校验：防止明显错误。"""
        if self.domain != FETCH_DOMAIN and self.domain not in DOMAINS:
            raise ValueError(
                f"SourceAdapter({self.name!r}) domain={self.domain!r} 不在 DOMAINS ∪ {{fetch}} 中"
            )
        if self.integration not in INTEGRATIONS:
            raise ValueError(
                f"SourceAdapter({self.name!r}) integration={self.integration!r} 不在 INTEGRATIONS 中"
            )
        if self.auth_requirement is not None and self.auth_requirement not in AUTH_REQUIREMENTS:
            raise ValueError(
                f"SourceAdapter({self.name!r}) auth_requirement={self.auth_requirement!r} "
                f"不在 AUTH_REQUIREMENTS 中"
            )
        if (
            self.optional_credential_effect is not None
            and self.optional_credential_effect not in OPTIONAL_CREDENTIAL_EFFECTS
        ):
            raise ValueError(
                f"SourceAdapter({self.name!r}) optional_credential_effect="
                f"{self.optional_credential_effect!r} 不在 OPTIONAL_CREDENTIAL_EFFECTS 中"
            )
        if self.risk_level not in RISK_LEVELS:
            raise ValueError(
                f"SourceAdapter({self.name!r}) risk_level={self.risk_level!r} 不在 RISK_LEVELS 中"
            )
        invalid_reasons = self.risk_reasons - RISK_REASONS
        if invalid_reasons:
            raise ValueError(
                f"SourceAdapter({self.name!r}) risk_reasons 包含非法值: {sorted(invalid_reasons)}"
            )
        if self.distribution not in DISTRIBUTIONS:
            raise ValueError(
                f"SourceAdapter({self.name!r}) distribution={self.distribution!r} 不在 DISTRIBUTIONS 中"
            )
        if self.stability not in STABILITIES:
            raise ValueError(
                f"SourceAdapter({self.name!r}) stability={self.stability!r} 不在 STABILITIES 中"
            )
        effective_auth = self.resolved_auth_requirement
        resolved_fields = self.resolved_credential_fields
        if effective_auth == "none" and resolved_fields:
            raise ValueError(
                f"SourceAdapter({self.name!r}) auth_requirement='none' 不能声明 credential_fields"
            )
        if (
            self.integration == "self_hosted" or effective_auth == "self_hosted"
        ) and not resolved_fields:
            raise ValueError(
                f"SourceAdapter({self.name!r}) self_hosted 源必须声明 config_field 或 credential_fields"
            )
        if effective_auth == "required" and not resolved_fields:
            raise ValueError(
                f"SourceAdapter({self.name!r}) auth_requirement={effective_auth!r} "
                "必须声明 config_field 或 credential_fields"
            )
        if self.optional_credential_effect is not None and effective_auth != "optional":
            raise ValueError(
                f"SourceAdapter({self.name!r}) optional_credential_effect 仅适用于 "
                "auth_requirement='optional'"
            )
        for cap in self.methods.keys():
            if cap in CAPABILITIES:
                continue
            if ":" in cap:  # 命名空间形式，如 "exa:find_similar"（D8）
                continue
            raise ValueError(
                f"SourceAdapter({self.name!r}) capability={cap!r} 既不在标准集也不是 'xxx:yyy' 命名空间"
            )
        for extra in self.extra_domains:
            if extra != FETCH_DOMAIN:
                raise ValueError(
                    f"SourceAdapter({self.name!r}) extra_domains 仅允许 {{'fetch'}}，得到 {extra!r}"
                )
        for key in self.default_for:
            if ":" not in key:
                raise ValueError(
                    f"SourceAdapter({self.name!r}) default_for 条目 {key!r} 必须是 'domain:capability' 形式"
                )
