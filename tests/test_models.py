"""SouWen 数据模型边界测试。

覆盖 ``souwen.models`` 中数据模型的完整性、字段约束和 source id 边界。
验证 source catalog 元数据、结果 source 使用 registry adapter name、extra='forbid' 验证、
WebSearchResult 必要字段等不变量。

测试清单：
- ``TestSourceCatalog``：catalog 字典结构、计数、论文/专利/Web 源统计
- ``TestResultSourceIds``：结果 source 字段使用 adapter name，且允许插件运行时 source
- ``TestExtraForbid``：拒绝未知字段
- ``TestWebSearchResult``：必要字段校验、snippet 默认值
"""

import pytest
from pydantic import ValidationError

from souwen.models import (
    EnrichedWebSearchResult,
    FetchResponse,
    PaperResult,
    PatentResult,
    SearchCandidate,
    SearchSnippet,
    SearchSourceProvenance,
    SearchResponse,
    WebSearchResult,
)
from souwen.registry.catalog import public_source_catalog, source_catalog


class TestSourceCatalog:
    """source catalog 元信息测试"""

    def test_paper_count(self):
        """paper catalog 暴露 21 个数据源（含 citation enrichment）"""
        catalog = public_source_catalog()
        assert sum(1 for entry in catalog.values() if entry.category == "paper") == 21

    def test_patent_count(self):
        """patent 暴露 8 个搜索数据源。"""
        catalog = public_source_catalog()
        assert sum(1 for entry in catalog.values() if entry.category == "patent") == 8

    def test_web_count(self):
        """web-derived categories have correct source counts."""
        catalog = public_source_catalog()
        counts: dict[str, int] = {}
        for entry in catalog.values():
            counts[entry.category] = counts.get(entry.category, 0) + 1
        assert counts["web_general"] == 21
        assert counts["web_professional"] == 11
        assert counts["social"] == 5
        assert counts["developer"] == 2
        assert counts["knowledge"] == 1
        assert counts["video"] == 2
        # cn_tech 拆分后独立源
        assert counts["cn_tech"] == 9

    def test_total_count(self):
        """总计暴露的数据源数量（含可能的外部插件）。"""
        assert len(public_source_catalog()) >= 91

    def test_each_entry_has_display_fields(self):
        """每条目包含展示所需字段。"""
        for name, entry in public_source_catalog().items():
            assert entry.name == name
            assert isinstance(entry.needs_config, bool)
            assert entry.description

    def test_search_only_exposes_supported_paper_sources(self):
        """paper 搜索列表不再暴露 unpaywall。"""
        names = {
            name for name, entry in public_source_catalog().items() if entry.category == "paper"
        }
        assert "unpaywall" not in names

    def test_patent_search_exposes_repaired_credential_sources_without_defaults(self):
        """PatentsView/PQAI 可见但需要凭据，且不进入默认专利源。"""
        from souwen.registry import defaults_for

        names = {
            name: entry
            for name, entry in public_source_catalog().items()
            if entry.category == "patent"
        }
        assert names["patentsview"].auth_requirement == "required"
        assert names["patentsview"].available_by_default is False
        assert names["pqai"].auth_requirement == "required"
        assert names["pqai"].available_by_default is False
        assert "patentsview" not in defaults_for("patent", "search")
        assert "pqai" not in defaults_for("patent", "search")

    def test_self_hosted_web_sources_require_setup(self):
        """自建 Web 引擎在清单中标记为需要配置。"""
        needs_key = {
            name: entry.needs_config
            for name, entry in public_source_catalog().items()
            if entry.category == "web_general"
        }
        assert needs_key["searxng"] is True
        assert needs_key["whoogle"] is True
        assert needs_key["websurfx"] is True


class TestResultSourceIds:
    """结果模型 source 字段使用 registry adapter name。"""

    def test_result_source_uses_registry_adapter_name(self):
        """内置结果模型样例的 source 都应直接等于 adapter.name。"""
        registry_names = set(source_catalog())
        samples = [
            PaperResult(source="openalex", title="T", source_url="https://example.com/paper"),
            PatentResult(
                source="google_patents",
                title="P",
                patent_id="US123",
                source_url="https://example.com/patent",
            ),
            WebSearchResult(
                source="duckduckgo",
                title="W",
                url="https://example.com",
                engine="duckduckgo",
            ),
            SearchResponse(query="q", source="duckduckgo", results=[]),
        ]

        for sample in samples:
            assert sample.source in registry_names
            assert not sample.source.startswith(("web_", "fetch_"))

    def test_result_source_allows_runtime_plugin_name(self):
        """模型层只承载字符串，不把插件 source 限死在内置 registry 中。"""
        paper = PaperResult(
            source="external_plugin_source",
            title="Plugin Paper",
            source_url="https://example.com/plugin",
        )
        assert paper.source == "external_plugin_source"


class TestExtraForbid:
    """extra='forbid' 拒绝未知字段"""

    def test_paper_rejects_unknown(self):
        """PaperResult 拒绝未知字段"""
        with pytest.raises(ValidationError):
            PaperResult(
                source="openalex",
                title="T",
                source_url="https://x.com",
                unknown_field="bad",
            )

    def test_patent_rejects_unknown(self):
        """PatentResult 拒绝未知字段"""
        with pytest.raises(ValidationError):
            PatentResult(
                source="patentsview",
                title="P",
                patent_id="US123",
                source_url="https://x.com",
                unknown_field="bad",
            )

    def test_search_response_rejects_unknown(self):
        """SearchResponse 拒绝未知字段"""
        with pytest.raises(ValidationError):
            SearchResponse(
                query="q",
                source="openalex",
                results=[],
                unknown_field="bad",
            )


class TestFetchResponse:
    """FetchResponse schema contract tests."""

    def test_provider_field_is_marked_deprecated(self):
        schema = FetchResponse.model_json_schema()
        provider_schema = schema["properties"]["provider"]

        assert provider_schema["deprecated"] is True
        assert provider_schema["x-souwen-sunset"] == "2.1.0 GA"

    def test_provider_populates_providers_for_legacy_responses(self):
        """旧 provider 字段仍应补齐 canonical providers 列表。"""
        response = FetchResponse(urls=[], results=[], provider="builtin")

        assert response.provider == "builtin"
        assert response.providers == ["builtin"]

    def test_single_provider_list_populates_compat_provider(self):
        """单 provider 列表应补齐 deprecated provider 兼容字段。"""
        response = FetchResponse(urls=[], results=[], providers=["jina_reader"])

        assert response.provider == "jina_reader"
        assert response.providers == ["jina_reader"]

    def test_multi_provider_list_keeps_compat_provider_null(self):
        """多 provider 响应不应伪装成单一 provider。"""
        response = FetchResponse(urls=[], results=[], providers=["builtin", "jina_reader"])

        assert response.provider is None
        assert response.providers == ["builtin", "jina_reader"]


class TestWebSearchResult:
    """WebSearchResult 必要字段测试"""

    def test_requires_source(self):
        """source 是必需字段"""
        with pytest.raises(ValidationError):
            WebSearchResult(title="T", url="https://x.com", engine="duckduckgo")

    def test_requires_title(self):
        """title 是必需字段"""
        with pytest.raises(ValidationError):
            WebSearchResult(source="duckduckgo", url="https://x.com", engine="ddg")

    def test_requires_url(self):
        """url 是必需字段"""
        with pytest.raises(ValidationError):
            WebSearchResult(source="duckduckgo", title="T", engine="ddg")

    def test_requires_engine(self):
        """engine 是必需字段"""
        with pytest.raises(ValidationError):
            WebSearchResult(source="duckduckgo", title="T", url="https://x.com")

    def test_valid_creation(self):
        """完整字段创建成功"""
        r = WebSearchResult(
            source="duckduckgo",
            title="Example",
            url="https://example.com",
            engine="duckduckgo",
            snippet="A snippet",
        )
        assert r.title == "Example"
        assert r.snippet == "A snippet"

    def test_snippet_defaults_empty(self):
        """snippet 默认空字符串"""
        r = WebSearchResult(
            source="duckduckgo",
            title="T",
            url="https://x.com",
            engine="ddg",
        )
        assert r.snippet == ""


class TestEnrichedSearchContracts:
    @staticmethod
    def _provenance(source_id: str = "fixture_source") -> SearchSourceProvenance:
        return SearchSourceProvenance(
            source_id=source_id,
            scheme_id="fixture_scheme_v1",
            requested_model_id="fixture-model",
        )

    def test_candidate_allows_url_only_discovery_but_validates_http_url(self):
        candidate = SearchCandidate(
            url="https://example.com/article",
            provenance=self._provenance(),
        )

        assert candidate.title is None
        with pytest.raises(ValidationError, match="http/https"):
            SearchCandidate(url="file:///private/article", provenance=self._provenance())

    def test_final_result_requires_real_title_url_and_discovery_provenance(self):
        result = EnrichedWebSearchResult(
            result_id="R1",
            rank=1,
            title="Real page title",
            url="https://example.com/article",
            canonical_url="https://example.com/article",
            site_domain="example.com",
            discoveries=[self._provenance(), self._provenance("second_source")],
            fetch_status="success",
            provider_snippet=SearchSnippet(text="Provider text", type="provider_summary"),
            content_excerpt=SearchSnippet(text="Extracted text", type="extractive"),
            summary=SearchSnippet(text="Generated text", type="generated", model="configured"),
        )

        assert [item.source_id for item in result.discoveries] == [
            "fixture_source",
            "second_source",
        ]
        with pytest.raises(ValidationError):
            EnrichedWebSearchResult(
                result_id="R2",
                rank=2,
                title=" ",
                url="https://example.com/empty-title",
                canonical_url="https://example.com/empty-title",
                site_domain="example.com",
                discoveries=[],
                fetch_status="not_requested",
            )

    def test_final_result_rejects_ambiguous_snippet_slots(self):
        with pytest.raises(ValidationError, match="content_excerpt"):
            EnrichedWebSearchResult(
                result_id="R1",
                rank=1,
                title="Title",
                url="https://example.com/article",
                canonical_url="https://example.com/article",
                site_domain="example.com",
                discoveries=[self._provenance()],
                fetch_status="success",
                content_excerpt=SearchSnippet(text="wrong", type="provider_snippet"),
            )
