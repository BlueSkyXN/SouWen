"""registry/adapter.py — SourceAdapter + MethodSpec + 常量

SourceAdapter 是 v1 架构的最小数据源单元，替代 v0 的：
  - source_registry.SourceMeta（元数据）
  - search.py 的 _PAPER_SOURCES / _PATENT_SOURCES 大 dict（执行适配 lambda）
  - web/search.py 的 engine_map / source_map（同上）

设计见 `local/v1-初步定义.md §5`。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

# ── 常量 ────────────────────────────────────────────────────

#: v1 的 10 个业务领域
DOMAINS: frozenset[str] = frozenset({
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
})

#: 横切能力（不是独立领域）
FETCH_DOMAIN: str = "fetch"

#: v1 的 11 个标准 capability。超出的（如 Exa 的 find_similar）采用命名空间前缀（D8）。
CAPABILITIES: frozenset[str] = frozenset({
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
})

#: 集成类型（沿用 v0 定义）
INTEGRATIONS: frozenset[str] = frozenset({
    "open_api",
    "scraper",
    "official_api",
    "self_hosted",
})


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
        """确定性的 needs_config：显式值优先，否则从 integration 推断。

        推断规则（保持与 v0 ALL_SOURCES 一致）：
          - official_api / self_hosted 且 config_field 非 None → True
          - 其他 → False
          - 注意：`openalex` / `github` / `doaj` / `zenodo` / `openaire` 等
            integration=official_api 但 Key 是"可选"的源，声明时需显式传 `needs_config=False`。
        """
        if self.needs_config is not None:
            return self.needs_config
        if self.integration in {"official_api", "self_hosted"} and self.config_field is not None:
            return True
        return False

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
                    f"SourceAdapter({self.name!r}) extra_domains 仅允许 {{'fetch'}}，"
                    f"得到 {extra!r}"
                )
        for key in self.default_for:
            if ":" not in key:
                raise ValueError(
                    f"SourceAdapter({self.name!r}) default_for 条目 {key!r} 必须是 'domain:capability' 形式"
                )
