"""SouWen 数据模型边界测试。

覆盖 ``souwen.models`` 中数据模型的完整性、字段约束、枚举值。
验证 ALL_SOURCES 元数据、SourceType 枚举完整性、extra='forbid' 验证、
WebSearchResult 必要字段等不变量。

测试清单：
- ``TestAllSources``：ALL_SOURCES 字典结构、计数、论文/专利/Web 源统计
- ``TestSourceTypeEnum``：SourceType 枚举值完整性、各源名称
- ``TestExtraForbid``：拒绝未知字段
- ``TestWebSearchResult``：必要字段校验、snippet 默认值
"""

import pytest
from pydantic import ValidationError

from souwen.models import (
    ALL_SOURCES,
    PaperResult,
    PatentResult,
    SearchResponse,
    SourceType,
    WebSearchResult,
)


class TestAllSources:
    """ALL_SOURCES 元信息测试"""

    def test_paper_count(self):
        """paper 暴露 17 个搜索数据源"""
        assert len(ALL_SOURCES["paper"]) == 17

    def test_patent_count(self):
        """patent 暴露 6 个搜索数据源"""
        assert len(ALL_SOURCES["patent"]) == 6

    def test_web_count(self):
        """web-derived categories have correct source counts（v1 从 registry 派生）

        v0 的 ALL_SOURCES 漏列了 source_registry 已登记的 bing_cn / ddg_news /
        ddg_images / ddg_videos / metaso / twitter / facebook。v1 统一从 registry
        派生，修复漂移；因此 general/social 数字比 v0 更高。
        """
        assert len(ALL_SOURCES["general"]) == 21  # v0: 16
        assert len(ALL_SOURCES["professional"]) == 7
        assert len(ALL_SOURCES["social"]) == 5  # v0: 3
        assert len(ALL_SOURCES["developer"]) == 2
        assert len(ALL_SOURCES["wiki"]) == 1
        assert len(ALL_SOURCES["video"]) == 2
        # cn_tech 拆分后独立源
        assert len(ALL_SOURCES["cn_tech"]) == 9

    def test_total_count(self):
        """总计暴露的数据源数量（含可能的外部插件）。"""
        total = sum(len(v) for v in ALL_SOURCES.values())
        assert total >= 90  # v0: 73, v1 内置: 90, 外部插件可增加

    def test_each_entry_is_tuple_of_three(self):
        """每条目是 (name, requires_key, desc) 三元组"""
        for category, sources in ALL_SOURCES.items():
            for entry in sources:
                assert len(entry) == 3, f"{category}: {entry}"
                assert isinstance(entry[0], str)
                assert isinstance(entry[1], bool)
                assert isinstance(entry[2], str)

    def test_search_only_exposes_supported_paper_sources(self):
        """paper 搜索列表不再暴露 unpaywall。"""
        names = {name for name, _, _ in ALL_SOURCES["paper"]}
        assert "unpaywall" not in names

    def test_patent_search_hides_known_broken_free_defaults(self):
        """patent 搜索列表不再默认暴露已失效免费源。"""
        names = {name for name, _, _ in ALL_SOURCES["patent"]}
        assert "patentsview" not in names
        assert "pqai" not in names

    def test_self_hosted_web_sources_require_setup(self):
        """自建 Web 引擎在清单中标记为需要配置。"""
        needs_key = {name: required for name, required, _ in ALL_SOURCES["general"]}
        assert needs_key["searxng"] is True
        assert needs_key["whoogle"] is True
        assert needs_key["websurfx"] is True


class TestSourceTypeEnum:
    """SourceType 枚举测试"""

    def test_has_59_values(self):
        """枚举有 76 个值"""
        assert len(SourceType) == 76

    def test_paper_sources_exist(self):
        """论文数据源枚举存在"""
        assert SourceType.OPENALEX.value == "openalex"
        assert SourceType.ARXIV.value == "arxiv"
        assert SourceType.CROSSREF.value == "crossref"
        assert SourceType.BIORXIV.value == "biorxiv"
        assert SourceType.IEEE_XPLORE.value == "ieee_xplore"

    def test_patent_sources_exist(self):
        """专利数据源枚举存在"""
        assert SourceType.PATENTSVIEW.value == "patentsview"
        assert SourceType.EPO_OPS.value == "epo_ops"

    def test_web_sources_exist(self):
        """Web 数据源枚举存在"""
        assert SourceType.WEB_DUCKDUCKGO.value == "web_duckduckgo"
        assert SourceType.WEB_TAVILY.value == "web_tavily"

    def test_is_string_enum(self):
        """SourceType 是 str 枚举"""
        assert isinstance(SourceType.OPENALEX, str)
        assert SourceType.OPENALEX == "openalex"


class TestExtraForbid:
    """extra='forbid' 拒绝未知字段"""

    def test_paper_rejects_unknown(self):
        """PaperResult 拒绝未知字段"""
        with pytest.raises(ValidationError):
            PaperResult(
                source=SourceType.OPENALEX,
                title="T",
                source_url="https://x.com",
                unknown_field="bad",
            )

    def test_patent_rejects_unknown(self):
        """PatentResult 拒绝未知字段"""
        with pytest.raises(ValidationError):
            PatentResult(
                source=SourceType.PATENTSVIEW,
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
                source=SourceType.OPENALEX,
                results=[],
                unknown_field="bad",
            )


class TestWebSearchResult:
    """WebSearchResult 必要字段测试"""

    def test_requires_source(self):
        """source 是必需字段"""
        with pytest.raises(ValidationError):
            WebSearchResult(title="T", url="https://x.com", engine="duckduckgo")

    def test_requires_title(self):
        """title 是必需字段"""
        with pytest.raises(ValidationError):
            WebSearchResult(source=SourceType.WEB_DUCKDUCKGO, url="https://x.com", engine="ddg")

    def test_requires_url(self):
        """url 是必需字段"""
        with pytest.raises(ValidationError):
            WebSearchResult(source=SourceType.WEB_DUCKDUCKGO, title="T", engine="ddg")

    def test_requires_engine(self):
        """engine 是必需字段"""
        with pytest.raises(ValidationError):
            WebSearchResult(source=SourceType.WEB_DUCKDUCKGO, title="T", url="https://x.com")

    def test_valid_creation(self):
        """完整字段创建成功"""
        r = WebSearchResult(
            source=SourceType.WEB_DUCKDUCKGO,
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
            source=SourceType.WEB_DUCKDUCKGO,
            title="T",
            url="https://x.com",
            engine="ddg",
        )
        assert r.snippet == ""
