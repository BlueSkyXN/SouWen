"""registry 结构一致性测试（D11 的 8 项硬断言 + 补充）

防止未来漂移：只要 `registry/sources/` 声明了某个东西，
以下测试就保证它真的能用。

断言（D11）：
  1. capabilities 全部属于 CAPABILITIES 或是 'xxx:yyy' 命名空间
  2. extra_domains 只允许 "fetch"（v1 初期）
  3. MethodSpec.method_name 在 client_loader() 返回的类上实际存在
  4. MethodSpec.param_map 的目标参数名是方法签名里真实的参数
  5. adapter.config_field 在 SouWenConfig.model_fields 里存在
  6. default_for 的每个 key 能解析为 (domain, capability) 且都合法
  7. 注册表没有重名
  8. SourceMeta 与正式 catalog 投影对齐

补充断言（门面与数据流健壮性）：
  9. 默认源名在 registry 的同 domain 下可查
 10. high_risk 源 default_for 为空（不进默认集）
 11. resolve_params 能完整覆盖所有 adapter/method（不抛异常）
"""

from __future__ import annotations

import inspect

import pytest

from souwen.config import SouWenConfig
from souwen.registry import (
    all_adapters,
    all_capabilities,
    all_domains,
    by_domain_and_capability,
    defaults_for,
    enum_values,
    fetch_providers,
    high_risk_sources,
    source_catalog,
)
from souwen.registry import external_plugins
from souwen.registry.adapter import (
    AUTH_REQUIREMENTS,
    CATALOG_VISIBILITIES,
    CAPABILITIES,
    DISTRIBUTIONS,
    DOMAINS,
    FETCH_DOMAIN,
    INTEGRATIONS,
    MethodSpec,
    OPTIONAL_CREDENTIAL_EFFECTS,
    RISK_LEVELS,
    RISK_REASONS,
    SOURCE_CATEGORIES,
    SourceAdapter,
    STABILITIES,
)
from souwen.registry.loader import lazy
from souwen.registry.views import _reg_external, _unreg_external


# ── 基础不变量 ──────────────────────────────────────────────


class TestRegistryInvariants:
    """注册表自身的基础不变量。"""

    def test_registry_non_empty(self):
        """至少注册了一些源（防止 sources package 导入失败被吃掉）。"""
        assert len(all_adapters()) >= 70, "注册表应有 70+ 个源"

    def test_all_source_names_unique(self):
        """D11-7：名字全局唯一（_reg 已做运行时检查，这里静态再做一次）。"""
        names = [a.name for a in all_adapters().values()]
        assert len(names) == len(set(names)), (
            f"重复源名: {set([n for n in names if names.count(n) > 1])}"
        )

    def test_domain_set_consistent(self):
        """所有 adapter 的 domain 都在 DOMAINS ∪ {fetch} 里。"""
        for adapter in all_adapters().values():
            assert adapter.domain in DOMAINS or adapter.domain == FETCH_DOMAIN, (
                f"{adapter.name}: domain={adapter.domain!r} 非法"
            )

    def test_integration_set_consistent(self):
        """所有 integration 值合法。"""
        for adapter in all_adapters().values():
            assert adapter.integration in INTEGRATIONS, (
                f"{adapter.name}: integration={adapter.integration!r} 非法"
            )

    def test_catalog_metadata_sets_consistent(self):
        """source catalog 新增元数据字段均在枚举常量内。"""
        for adapter in all_adapters().values():
            assert adapter.resolved_auth_requirement in AUTH_REQUIREMENTS, (
                f"{adapter.name}: auth_requirement={adapter.resolved_auth_requirement!r} 非法"
            )
            if adapter.optional_credential_effect is not None:
                assert adapter.optional_credential_effect in OPTIONAL_CREDENTIAL_EFFECTS, (
                    f"{adapter.name}: optional_credential_effect="
                    f"{adapter.optional_credential_effect!r} 非法"
                )
            assert adapter.resolved_risk_level in RISK_LEVELS, (
                f"{adapter.name}: risk_level={adapter.resolved_risk_level!r} 非法"
            )
            assert adapter.resolved_risk_reasons <= RISK_REASONS, (
                f"{adapter.name}: risk_reasons={sorted(adapter.resolved_risk_reasons)} 非法"
            )
            assert adapter.resolved_distribution in DISTRIBUTIONS, (
                f"{adapter.name}: distribution={adapter.resolved_distribution!r} 非法"
            )
            assert adapter.resolved_stability in STABILITIES, (
                f"{adapter.name}: stability={adapter.resolved_stability!r} 非法"
            )
            if adapter.category is not None:
                assert adapter.category in SOURCE_CATEGORIES, (
                    f"{adapter.name}: category={adapter.category!r} 非法"
                )
            assert adapter.catalog_visibility in CATALOG_VISIBILITIES, (
                f"{adapter.name}: catalog_visibility={adapter.catalog_visibility!r} 非法"
            )


class TestSourceAdapterCatalogValidation:
    """SourceAdapter catalog 字段的注册期防呆。"""

    @staticmethod
    def _adapter(**overrides) -> SourceAdapter:
        base = {
            "name": "catalog_validation_probe",
            "domain": "fetch",
            "integration": "scraper",
            "description": "probe",
            "config_field": None,
            "client_loader": lazy("souwen.web.builtin:BuiltinFetcherClient"),
            "methods": {"fetch": MethodSpec("fetch")},
        }
        base.update(overrides)
        return SourceAdapter(**base)

    def test_required_auth_must_have_credential_fields(self):
        with pytest.raises(ValueError, match="必须声明 config_field 或 credential_fields"):
            self._adapter(auth_requirement="required")

    def test_none_auth_cannot_declare_credentials(self):
        with pytest.raises(ValueError, match="不能声明 credential_fields"):
            self._adapter(
                auth_requirement="none",
                credential_fields=("tavily_api_key",),
            )

    def test_implicit_auth_with_credentials_needs_primary_or_explicit_auth(self):
        with pytest.raises(ValueError, match="不能声明 credential_fields"):
            self._adapter(credential_fields=("tavily_api_key", "serper_api_key"))

    def test_optional_credential_effect_only_allowed_for_optional_auth(self):
        with pytest.raises(ValueError, match="仅适用于 auth_requirement='optional'"):
            self._adapter(
                config_field="tavily_api_key",
                auth_requirement="required",
                optional_credential_effect="rate_limit",
            )

    def test_implicit_optional_credentials_remain_supported(self):
        adapter = self._adapter(
            config_field="openalex_email",
            integration="official_api",
            needs_config=False,
            optional_credential_effect="politeness",
        )
        assert adapter.resolved_auth_requirement == "optional"
        assert adapter.resolved_credential_fields == ("openalex_email",)
        assert adapter.resolved_needs_config is False

    def test_self_hosted_can_explicitly_skip_config_requirement(self):
        adapter = self._adapter(
            integration="self_hosted",
            config_field="searxng_url",
            needs_config=False,
        )
        assert adapter.resolved_auth_requirement == "optional"
        assert adapter.resolved_credential_fields == ("searxng_url",)
        assert adapter.resolved_needs_config is False

    def test_none_field_can_explicitly_require_config(self):
        adapter = self._adapter(
            config_field=None,
            credential_fields=("tavily_api_key",),
            needs_config=True,
        )
        assert adapter.resolved_auth_requirement == "required"
        assert adapter.resolved_credential_fields == ("tavily_api_key",)
        assert adapter.resolved_needs_config is True

    def test_self_hosted_without_declared_fields_is_rejected(self):
        with pytest.raises(
            ValueError, match="self_hosted 源必须声明 config_field 或 credential_fields"
        ):
            self._adapter(auth_requirement="self_hosted")

    def test_self_hosted_integration_without_declared_fields_is_rejected(self):
        with pytest.raises(
            ValueError, match="self_hosted 源必须声明 config_field 或 credential_fields"
        ):
            self._adapter(integration="self_hosted", needs_config=False)

    def test_has_required_credentials_rejects_required_meta_without_fields(self):
        from types import SimpleNamespace

        from souwen.registry.meta import has_required_credentials

        meta = SimpleNamespace(
            auth_requirement="required",
            credential_fields=(),
            config_field=None,
        )

        assert has_required_credentials(SouWenConfig(), "catalog_validation_probe", meta) is False

    def test_invalid_catalog_category_is_rejected(self):
        with pytest.raises(ValueError, match="category=.*SOURCE_CATEGORIES"):
            self._adapter(category="wiki")

    def test_invalid_catalog_visibility_is_rejected(self):
        with pytest.raises(ValueError, match="catalog_visibility=.*CATALOG_VISIBILITIES"):
            self._adapter(catalog_visibility="private")


# ── D11 硬断言 ──────────────────────────────────────────────


class TestD11HardAsserts:
    """D11 要求的 8 项断言。"""

    def test_capabilities_in_standard_set(self):
        """D11-1：capabilities 要么在 CAPABILITIES，要么是 'xxx:yyy' 命名空间。"""
        for adapter in all_adapters().values():
            for cap in adapter.capabilities:
                if cap in CAPABILITIES:
                    continue
                assert ":" in cap, f"{adapter.name}: capability={cap!r} 既不在标准集也不是命名空间"

    def test_extra_domains_only_fetch(self):
        """D11-2：extra_domains 目前只允许 {"fetch"}。"""
        for adapter in all_adapters().values():
            for extra in adapter.extra_domains:
                assert extra == FETCH_DOMAIN, (
                    f"{adapter.name}: extra_domains={extra!r}，v1 初期只允许 'fetch'"
                )

    def test_method_specs_point_to_real_methods(self):
        """D11-3：每个 MethodSpec.method_name 在 Client 上实际存在。

        这一步会真正触发 Client 的 import——也是 loader 工作正确的验证。
        """
        for adapter in all_adapters().values():
            client_cls = adapter.client_loader()
            for cap, spec in adapter.methods.items():
                method = getattr(client_cls, spec.method_name, None)
                assert method is not None, (
                    f"{adapter.name}.{spec.method_name} (capability={cap!r}) "
                    f"不在 {client_cls.__name__} 上"
                )
                assert callable(method), f"{adapter.name}.{spec.method_name} 不可调用"

    def test_param_map_targets_exist_in_signature(self):
        """D11-4：param_map 的 native 参数名是方法签名的真实参数。"""
        for adapter in all_adapters().values():
            client_cls = adapter.client_loader()
            for cap, spec in adapter.methods.items():
                if not spec.param_map:
                    continue
                method = getattr(client_cls, spec.method_name)
                sig = inspect.signature(method)
                has_var_keyword = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                )
                for unified_name, native_name in spec.param_map.items():
                    # 如果方法接受 **kwargs，不强制检查（逃生舱）
                    if has_var_keyword:
                        continue
                    assert native_name in sig.parameters, (
                        f"{adapter.name}.{spec.method_name} (capability={cap!r}) "
                        f"param_map[{unified_name!r}]={native_name!r} 不是方法参数。"
                        f"签名参数: {list(sig.parameters)}"
                    )

    def test_config_field_references_valid(self):
        """D11-5：每个 adapter.config_field 在 SouWenConfig 里存在。"""
        from souwen.config import SouWenConfig

        config_fields = set(SouWenConfig.model_fields.keys())
        for adapter in all_adapters().values():
            if adapter.config_field is None:
                continue
            assert adapter.config_field in config_fields, (
                f"{adapter.name}.config_field={adapter.config_field!r} 不在 SouWenConfig"
            )

    def test_credential_fields_reference_valid(self):
        """每个 credential_fields 字段也必须能被 SouWenConfig 解析。"""
        from souwen.config import SouWenConfig

        config_fields = set(SouWenConfig.model_fields.keys())
        for adapter in all_adapters().values():
            for field in adapter.resolved_credential_fields:
                assert field in config_fields, (
                    f"{adapter.name}.credential_fields 包含 {field!r}，但它不在 SouWenConfig"
                )

    def test_default_for_references_valid(self):
        """D11-6：default_for 的每个 key 能解析为 (domain, capability) 且都合法。"""
        for adapter in all_adapters().values():
            for key in adapter.default_for:
                assert ":" in key, f"{adapter.name}: default_for 条目 {key!r} 缺冒号"
                domain, cap = key.split(":", 1)
                assert domain in DOMAINS or domain == FETCH_DOMAIN, (
                    f"{adapter.name}: default_for domain={domain!r} 非法"
                )
                assert cap in CAPABILITIES, (
                    f"{adapter.name}: default_for capability={cap!r} 不是标准 capability"
                )
                # 对应 capability 必须在 methods 里
                assert cap in adapter.capabilities, (
                    f"{adapter.name}: default_for 声明 {key!r}，但 methods 里没有 {cap!r}"
                )
                # 对应 domain 必须在 adapter.domains 里
                assert domain in adapter.domains, (
                    f"{adapter.name}: default_for 声明 {key!r}，但 {domain!r} 不在 "
                    f"adapter.domains={adapter.domains}"
                )

    def test_source_meta_matches_catalog_projection(self):
        """D11-8：SourceMeta 与正式 catalog 投影一致。"""
        from souwen.registry import meta as source_meta

        catalog = source_catalog()
        metadata = source_meta.get_all_sources()
        assert set(metadata.keys()) == set(catalog.keys())
        for name, entry in catalog.items():
            meta = metadata[name]
            assert meta.category == entry.category
            assert meta.auth_requirement == entry.auth_requirement
            assert meta.credential_fields == entry.credential_fields
            assert meta.risk_level == entry.risk_level
            assert meta.distribution == entry.distribution
            assert meta.stability == entry.stability


# ── 补充一致性检查 ─────────────────────────────────────────


class TestExtraConsistency:
    """门面 / 默认源等补充检查。"""

    def test_defaults_reference_valid_sources(self):
        """补充-9：default_for 的每个默认名都指向注册表里存在的源。"""
        for adapter in all_adapters().values():
            for key in adapter.default_for:
                domain, cap = key.split(":", 1)
                defaults = defaults_for(domain, cap)
                assert adapter.name in defaults, (
                    f"{adapter.name} 声明 default_for={key!r}，"
                    f"但 defaults_for({domain!r}, {cap!r})={defaults} 没包含它"
                )

    def test_high_risk_sources_not_in_defaults(self):
        """补充-10：high_risk 源不应该在任何 default_for 集合里（D10）。"""
        high_risk = set(high_risk_sources())
        for adapter in all_adapters().values():
            if adapter.name in high_risk:
                assert not adapter.default_for, (
                    f"{adapter.name} 是 high_risk 但声明了 default_for={adapter.default_for}，"
                    f"这会让高风险源默认启用"
                )

    def test_resolve_params_never_raises(self):
        """补充-11：resolve_params 对所有 adapter/method 不抛异常（基本 sanity）。"""
        for adapter in all_adapters().values():
            for cap, spec in adapter.methods.items():
                try:
                    native = adapter.resolve_params(spec, query="test", limit=5)
                    assert isinstance(native, dict)
                except Exception as e:
                    pytest.fail(
                        f"{adapter.name}.resolve_params(cap={cap}) 抛异常: {type(e).__name__}: {e}"
                    )


# ── Source id 与 registry 对齐 ──────────────────────────────


class TestSourceIdDerivation:
    """source id 直接从 registry adapter name 派生。"""

    def test_enum_values_are_adapter_names(self):
        """registry enum_values 只返回 adapter.name，不再经过旧前缀枚举层。"""
        registry_names = set(all_adapters())
        ids = set(enum_values())
        assert ids == registry_names
        assert "web_" + "duckduckgo" not in ids
        assert "web_" + "bing" not in ids
        assert "fetch_" + "builtin" not in ids
        assert {"duckduckgo", "bing", "builtin", "jina_reader"} <= ids

    def test_catalog_keys_are_adapter_names(self):
        """正式 catalog 的 key 与 registry adapter.name 保持一致。"""
        assert set(source_catalog()) == set(enum_values())


# ── Fetch 提供者覆盖 ───────────────────────────────────────


class TestFetchProviders:
    """fetch 能力的派发面不能掉链子。"""

    def test_fetch_providers_non_empty(self):
        """至少有 builtin 一个。"""
        providers = fetch_providers()
        assert len(providers) >= 10, "fetch 提供者至少 10 个"
        names = [p.name for p in providers]
        assert "builtin" in names
        assert "arxiv_fulltext" in names
        # 跨域源应该在这里
        assert "tavily" in names
        assert "firecrawl" in names
        assert "exa" in names
        assert "wayback" in names

    def test_fetch_default(self):
        """fetch:fetch 默认提供者是 builtin。"""
        defaults = defaults_for("fetch", "fetch")
        assert defaults == ["builtin"], f"fetch:fetch 默认应该只有 builtin，实际 {defaults}"


# ── Domain 完整性 ──────────────────────────────────────────


class TestDomainCoverage:
    """v1 的 10 个 domain 都应该至少有一个源。"""

    def test_all_domains_populated(self):
        """10 个 domain 都有源。"""
        doms = set(all_domains())
        for dom in DOMAINS:
            assert dom in doms, f"domain={dom!r} 在注册表中没有任何源"
        assert FETCH_DOMAIN in doms

    def test_each_domain_has_search_capability(self):
        """每个非 fetch domain 至少有一个源支持 'search'（web 的 search_* 变种不计）。"""
        for dom in DOMAINS:
            adapters = by_domain_and_capability(dom, "search")
            if dom == "archive":
                # archive 用 archive_lookup 作主能力
                adapters = by_domain_and_capability(dom, "archive_lookup")
            assert len(adapters) >= 1, f"domain={dom!r} 没有源支持 search/archive_lookup"


# ── Capability 枚举稳定性 ──────────────────────────────────


class TestCapabilityStability:
    """capability 常量集稳定。"""

    def test_standard_capability_set(self):
        """标准 capability 12 个（v1-初步定义 §1.2 列了 11 项，但 archive_lookup/save 算 2 个）。"""
        assert len(CAPABILITIES) == 12
        expected = {
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
        assert CAPABILITIES == expected

    def test_all_standard_capabilities_used(self):
        """每个标准 capability 至少有一个源实现（除非是预留的）。"""
        allowed_unused: set[str] = set()  # 没有预留能力
        used = set(all_capabilities())
        for cap in CAPABILITIES - allowed_unused:
            assert cap in used, (
                f"标准 capability {cap!r} 没有源实现；如果预留未用，请加入 allowed_unused 集合"
            )


# ── 外部插件支持 ───────────────────────────────────────────


class TestExternalPlugins:
    """`external_plugins()` 视图与 `_reg_external` 的集成行为。"""

    def test_external_plugins_returns_list(self):
        out = external_plugins()
        assert isinstance(out, list)
        # 列表内容必定是 _REGISTRY 子集
        names = set(all_adapters().keys())
        for n in out:
            assert n in names, f"external_plugins() 返回的 {n!r} 不在 registry"

    def test_reg_external_does_not_corrupt_registry(self, clean_registry):
        """注册并恢复后，所有 D11 不变量仍然成立。"""
        adapter = SourceAdapter(
            name="ext_consistency_probe",
            domain="fetch",
            integration="scraper",
            description="probe",
            config_field=None,
            client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
            methods={"fetch": MethodSpec("fetch")},
            needs_config=False,
        )
        ok = _reg_external(adapter)
        assert ok is True
        # 注册后，注册表里能找到；并且 capability/domain 都合法
        adapters = all_adapters()
        assert "ext_consistency_probe" in adapters
        a = adapters["ext_consistency_probe"]
        assert a.domain in DOMAINS or a.domain == FETCH_DOMAIN
        assert a.integration in INTEGRATIONS
        for cap in a.capabilities:
            assert cap in CAPABILITIES or ":" in cap

    def test_external_adapter_passes_d11_validation(self, clean_registry):
        """外部 adapter 也要满足：methods 指向真实存在的 client 方法。"""
        adapter = SourceAdapter(
            name="ext_d11_probe",
            domain="fetch",
            integration="scraper",
            description="probe",
            config_field=None,
            client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
            methods={"fetch": MethodSpec("fetch")},
            needs_config=False,
        )
        _reg_external(adapter)
        a = all_adapters()["ext_d11_probe"]
        client_cls = a.client_loader()
        for cap, spec in a.methods.items():
            assert callable(getattr(client_cls, spec.method_name, None)), (
                f"external adapter {a.name} method {spec.method_name} 不可调用"
            )

    def test_reg_external_refreshes_source_meta_cache(self, clean_registry):
        """运行时注册/注销插件源后，SourceMeta 视图必须同步刷新。"""
        from souwen.registry import meta as source_meta

        # 先构建一次缓存，复现旧问题：之后注册插件若不失效会读不到新源。
        assert "ext_cache_probe" not in source_meta.get_all_sources()
        assert source_meta.get_source("ext_cache_probe") is None

        adapter = SourceAdapter(
            name="ext_cache_probe",
            domain="fetch",
            integration="scraper",
            description="probe",
            config_field=None,
            client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
            methods={"fetch": MethodSpec("fetch")},
            needs_config=False,
        )
        assert _reg_external(adapter) is True
        assert source_meta.get_source("ext_cache_probe") is not None
        assert source_meta.is_known_source("ext_cache_probe") is True
        assert "ext_cache_probe" in source_meta.ALL_SOURCE_NAMES

        assert _unreg_external("ext_cache_probe") is True
        assert source_meta.get_source("ext_cache_probe") is None
        assert source_meta.is_known_source("ext_cache_probe") is False
        assert "ext_cache_probe" not in source_meta.ALL_SOURCE_NAMES

    def test_external_web_plugin_without_explicit_category_is_visible(self, clean_registry):
        """外部 web 插件不声明 category 时仍进入 catalog。"""
        from souwen.registry import meta as source_meta

        adapter = SourceAdapter(
            name="ext_web_probe",
            domain="web",
            integration="scraper",
            description="web probe",
            config_field=None,
            client_loader=lazy("souwen.web.duckduckgo:DuckDuckGoClient"),
            methods={"search": MethodSpec("search")},
            needs_config=False,
        )

        assert _reg_external(adapter) is True
        meta = source_meta.get_source("ext_web_probe")
        assert meta is not None
        assert meta.category == "web_general"
        assert meta.distribution == "plugin"
        assert source_meta.is_known_source("ext_web_probe") is True
        assert "ext_web_probe" in source_meta.ALL_SOURCE_NAMES

    def test_external_web_plugin_can_use_public_professional_category_tag(self, clean_registry):
        """外部 web 插件可用公开 category:* tag 选择专业网页分类。"""
        from souwen.registry import meta as source_meta

        adapter = SourceAdapter(
            name="ext_professional_web_probe",
            domain="web",
            integration="official_api",
            description="professional web probe",
            config_field="tavily_api_key",
            client_loader=lazy("souwen.web.tavily:TavilyClient"),
            methods={"search": MethodSpec("search")},
            auth_requirement="required",
            credential_fields=("tavily_api_key",),
            tags=frozenset({"category:professional"}),
        )

        assert _reg_external(adapter) is True
        meta = source_meta.get_source("ext_professional_web_probe")
        assert meta is not None
        assert meta.category == "web_professional"
