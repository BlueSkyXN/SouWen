"""SouWen 基础设施层测试。

覆盖 ``souwen.models``（数据模型）、``souwen.core.exceptions``（异常体系）、
``souwen.config``（配置管理）、``souwen.core.rate_limiter``（限流）、
``souwen.web``（网页搜索）、``souwen.search``（统一搜索）、
``souwen.server``（FastAPI 服务）等核心基础设施。

验证数据模型的字段完整性、异常继承关系、配置默认值、限流器行为、
网页搜索去重、统一搜索门面、OAuth 并发安全等不变量。

测试清单：
- ``TestModels``：数据模型创建与字段验证
- ``TestExceptions``：异常体系继承关系
- ``TestConfig``：配置值与路径展开
- ``TestRateLimiter``：限流器异步操作
- ``TestWebSearch``：网页搜索引擎、URL 解码、去重、API Key 必需性
- ``TestUnifiedSearch``：统一搜索门面与数据源映射
- ``TestYAMLConfig``：YAML 配置加载与示例文件
- ``TestCLI``：CLI 工具与脱敏
- ``TestServer``：FastAPI 服务导入与路由
- ``TestOAuthTokenConcurrency``：OAuth Token 并发刷新安全性
"""

import pytest
from souwen.models import (
    PaperResult,
    PatentResult,
    SearchResponse,
    Author,
    Applicant,
    SourceType,
    WebSearchResult,
    WebSearchResponse,
)
from souwen.core.exceptions import (
    SouWenError,
    ConfigError,
    AuthError,
    RateLimitError,
    SourceUnavailableError,
    ParseError,
    NotFoundError,
)
from souwen.config import SouWenConfig
from souwen.core.rate_limiter import TokenBucketLimiter, SlidingWindowLimiter
from souwen.registry.meta import (
    AUTH_REQUIREMENT_TYPES,
    DISTRIBUTION_TYPES,
    INTEGRATION_TYPES,
    get_all_sources,
    get_sources_by_auth_requirement,
    get_sources_by_distribution,
    get_sources_by_integration_type,
)


class TestModels:
    """数据模型测试"""

    def test_paper_result_minimal(self):
        """最小字段创建论文结果"""
        paper = PaperResult(
            source=SourceType.OPENALEX,
            title="Test Paper",
            source_url="https://example.com",
        )
        assert paper.title == "Test Paper"
        assert paper.source == SourceType.OPENALEX
        assert paper.authors == []
        assert paper.doi is None

    def test_paper_result_full(self):
        """完整字段创建论文结果"""
        paper = PaperResult(
            source=SourceType.SEMANTIC_SCHOLAR,
            title="Deep Learning for NLP",
            authors=[Author(name="Alice", affiliation="MIT", orcid="0000-0001-0000-0001")],
            abstract="This paper presents...",
            doi="10.1234/test",
            year=2024,
            citation_count=100,
            source_url="https://example.com/paper",
            tldr="DL beats traditional NLP",
        )
        assert len(paper.authors) == 1
        assert paper.authors[0].orcid == "0000-0001-0000-0001"
        assert paper.tldr is not None

    def test_patent_result(self):
        """专利结果模型"""
        patent = PatentResult(
            source=SourceType.PATENTSVIEW,
            title="Network Authentication Method",
            patent_id="US10123456B2",
            applicants=[Applicant(name="TechCorp", country="US")],
            inventors=["John Doe", "Jane Smith"],
            ipc_codes=["H04W12/06"],
            source_url="https://example.com/patent",
        )
        assert patent.patent_id == "US10123456B2"
        assert len(patent.applicants) == 1
        assert len(patent.inventors) == 2

    def test_search_response_paper(self):
        """搜索响应（论文）"""
        resp = SearchResponse(
            query="test",
            source=SourceType.OPENALEX,
            total_results=100,
            results=[
                PaperResult(
                    source=SourceType.OPENALEX,
                    title="Paper 1",
                    source_url="https://example.com/1",
                ),
            ],
            page=1,
            per_page=10,
        )
        assert resp.total_results == 100
        assert len(resp.results) == 1

    def test_web_search_result(self):
        """网页搜索结果模型"""
        result = WebSearchResult(
            source=SourceType.WEB_DUCKDUCKGO,
            title="Python Tutorial",
            url="https://docs.python.org/3/tutorial/",
            snippet="The Python Tutorial — Python 3 documentation",
            engine="duckduckgo",
        )
        assert result.title == "Python Tutorial"
        assert result.engine == "duckduckgo"
        assert result.source == SourceType.WEB_DUCKDUCKGO

    def test_web_search_response(self):
        """网页搜索响应"""
        resp = WebSearchResponse(
            query="python",
            source=SourceType.WEB_DUCKDUCKGO,
            total_results=1,
            results=[
                WebSearchResult(
                    source=SourceType.WEB_DUCKDUCKGO,
                    title="Python.org",
                    url="https://www.python.org",
                    snippet="The official home of Python",
                    engine="duckduckgo",
                ),
            ],
        )
        assert resp.total_results == 1
        assert len(resp.results) == 1

    def test_source_type_enum(self):
        """数据源枚举完整性"""
        assert SourceType.OPENALEX.value == "openalex"
        assert SourceType.GOOGLE_PATENTS.value == "google_patents"
        assert SourceType.WEB_DUCKDUCKGO.value == "web_duckduckgo"
        assert SourceType.WEB_YAHOO.value == "web_yahoo"
        assert SourceType.WEB_BRAVE.value == "web_brave"
        assert SourceType.WEB_GOOGLE.value == "web_google"
        assert SourceType.WEB_BING.value == "web_bing"
        assert SourceType.WEB_SEARXNG.value == "web_searxng"
        assert SourceType.WEB_TAVILY.value == "web_tavily"
        assert SourceType.WEB_EXA.value == "web_exa"
        assert SourceType.WEB_SERPER.value == "web_serper"
        assert SourceType.WEB_BRAVE_API.value == "web_brave_api"
        # 确保论文、专利、搜索源都存在
        paper_sources = [
            SourceType.OPENALEX,
            SourceType.SEMANTIC_SCHOLAR,
            SourceType.CROSSREF,
            SourceType.ARXIV,
            SourceType.DBLP,
            SourceType.CORE,
            SourceType.PUBMED,
            SourceType.UNPAYWALL,
            SourceType.HUGGINGFACE,
            SourceType.EUROPEPMC,
            SourceType.PMC,
            SourceType.DOAJ,
            SourceType.ZENODO,
            SourceType.HAL,
            SourceType.OPENAIRE,
            SourceType.IACR,
            SourceType.BIORXIV,
            SourceType.ZOTERO,
            SourceType.IEEE_XPLORE,
        ]
        patent_sources = [
            SourceType.PATENTSVIEW,
            SourceType.USPTO_ODP,
            SourceType.EPO_OPS,
            SourceType.CNIPA,
            SourceType.THE_LENS,
            SourceType.PQAI,
            SourceType.PATSNAP,
            SourceType.GOOGLE_PATENTS,
        ]
        web_sources = [
            SourceType.WEB_DUCKDUCKGO,
            SourceType.WEB_YAHOO,
            SourceType.WEB_BRAVE,
            SourceType.WEB_GOOGLE,
            SourceType.WEB_BING,
            SourceType.WEB_SEARXNG,
            SourceType.WEB_TAVILY,
            SourceType.WEB_EXA,
            SourceType.WEB_SERPER,
            SourceType.WEB_BRAVE_API,
            SourceType.WEB_GITHUB,
            SourceType.WEB_STACKOVERFLOW,
            SourceType.WEB_REDDIT,
            SourceType.WEB_BILIBILI,
            SourceType.WEB_WIKIPEDIA,
            SourceType.WEB_YOUTUBE,
            SourceType.WEB_ZHIHU,
            SourceType.WEB_WEIBO,
            SourceType.WEB_NODESEEK,
            SourceType.WEB_HOSTLOC,
            SourceType.WEB_V2EX,
            SourceType.WEB_COOLAPK,
            SourceType.WEB_XIAOHONGSHU,
            SourceType.WEB_FEISHU_DRIVE,
            SourceType.WEB_ZHIPUAI,
            SourceType.WEB_ALIYUN_IQS,
            SourceType.WEB_XCRAWL,
        ]
        assert len(paper_sources) == 19
        assert len(patent_sources) == 8
        assert len(web_sources) == 27


class TestExceptions:
    """异常体系测试"""

    def test_config_error_with_url(self):
        """配置错误带注册链接"""
        err = ConfigError("core_api_key", "CORE", "https://core.ac.uk/services/api")
        assert "core_api_key" in str(err)
        assert "https://core.ac.uk" in str(err)

    def test_config_error_without_url(self):
        """配置错误不带注册链接"""
        err = ConfigError("api_key", "TestService")
        assert "api_key" in str(err)
        assert err.register_url is None

    def test_rate_limit_error(self):
        """限流错误带重试时间"""
        err = RateLimitError("太快了", retry_after=30.0)
        assert err.retry_after == 30.0

    def test_exception_hierarchy(self):
        """异常继承关系"""
        assert issubclass(ConfigError, SouWenError)
        assert issubclass(AuthError, SouWenError)
        assert issubclass(RateLimitError, SouWenError)
        assert issubclass(SourceUnavailableError, SouWenError)
        assert issubclass(ParseError, SouWenError)
        assert issubclass(NotFoundError, SouWenError)


class TestConfig:
    """配置管理测试"""

    def test_default_config(self):
        """默认配置值"""
        config = SouWenConfig()
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.openalex_email is None
        assert config.proxy is None

    def test_custom_config(self):
        """自定义配置值"""
        config = SouWenConfig(
            openalex_email="test@example.com",
            timeout=60,
        )
        assert config.openalex_email == "test@example.com"
        assert config.timeout == 60

    def test_data_path(self):
        """数据路径展开"""
        config = SouWenConfig(data_dir="~/.local/share/souwen")
        path = config.data_path
        assert "~" not in str(path)


class TestRateLimiter:
    """限流器测试"""

    @pytest.mark.asyncio
    async def test_token_bucket_acquire(self):
        """令牌桶获取令牌"""
        limiter = TokenBucketLimiter(rate=10.0, burst=10)
        # 应该能立即获取
        await limiter.acquire()

    @pytest.mark.asyncio
    async def test_sliding_window_acquire(self):
        """滑动窗口获取许可"""
        limiter = SlidingWindowLimiter(max_requests=100, window_seconds=60.0)
        await limiter.acquire()

    def test_sliding_window_update_headers(self):
        """滑动窗口从响应头更新"""
        limiter = SlidingWindowLimiter(max_requests=100, window_seconds=60.0)
        limiter.update_from_headers(remaining=50)


class TestWebSearch:
    """网页搜索模块测试"""

    def test_web_module_imports(self):
        """网页搜索模块导入（全部 10 个引擎）"""
        from souwen.web import (
            DuckDuckGoClient,
            YahooClient,
            BraveClient,
            GoogleClient,
            BingClient,
            SearXNGClient,
            TavilyClient,
            ExaClient,
            SerperClient,
            BraveApiClient,
            web_search,
        )

        # 爬虫引擎
        assert DuckDuckGoClient.ENGINE_NAME == "duckduckgo"
        assert YahooClient.ENGINE_NAME == "yahoo"
        assert BraveClient.ENGINE_NAME == "brave"
        assert GoogleClient.ENGINE_NAME == "google"
        assert BingClient.ENGINE_NAME == "bing"
        # API 引擎
        assert SearXNGClient.ENGINE_NAME == "searxng"
        assert TavilyClient.ENGINE_NAME == "tavily"
        assert ExaClient.ENGINE_NAME == "exa"
        assert SerperClient.ENGINE_NAME == "serper"
        assert BraveApiClient.ENGINE_NAME == "brave_api"
        assert callable(web_search)

    def test_ddg_url_decode(self):
        """DuckDuckGo URL 重定向解码"""
        from souwen.web.duckduckgo import DuckDuckGoClient

        # 正常重定向 URL
        encoded = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org&rut=abc"
        assert DuckDuckGoClient._decode_ddg_url(encoded) == "https://www.python.org"
        # 无重定向，原样返回
        assert DuckDuckGoClient._decode_ddg_url("https://example.com") == "https://example.com"

    def test_yahoo_url_decode(self):
        """Yahoo URL 重定向解码"""
        from souwen.web.yahoo import YahooClient

        # 正常重定向 URL
        encoded = "https://r.search.yahoo.com/RU=https%3A%2F%2Fwww.python.org/RK=2/RS=abc"
        assert YahooClient._decode_yahoo_url(encoded) == "https://www.python.org"
        # 无重定向，原样返回
        assert YahooClient._decode_yahoo_url("https://example.com") == "https://example.com"

    def test_deduplicate(self):
        """URL 去重"""
        from souwen.web.search import _deduplicate

        results = [
            WebSearchResult(
                source=SourceType.WEB_DUCKDUCKGO,
                title="A",
                url="https://example.com/",
                snippet="",
                engine="ddg",
            ),
            WebSearchResult(
                source=SourceType.WEB_YAHOO,
                title="B",
                url="https://example.com",
                snippet="",
                engine="yahoo",
            ),
            WebSearchResult(
                source=SourceType.WEB_BRAVE,
                title="C",
                url="https://other.com",
                snippet="",
                engine="brave",
            ),
        ]
        deduped = _deduplicate(results)
        assert len(deduped) == 2
        assert deduped[0].title == "A"
        assert deduped[1].title == "C"

    def test_google_url_decode(self):
        """Google URL 重定向解码"""
        from souwen.web.google import GoogleClient

        # /url?q= 重定向
        encoded = "/url?q=https%3A%2F%2Fwww.python.org&sa=U&ved=..."
        assert GoogleClient._decode_google_url(encoded) == "https://www.python.org"
        # 直接 URL
        assert GoogleClient._decode_google_url("https://example.com") == "https://example.com"
        # 内部链接过滤
        assert GoogleClient._decode_google_url("/search?q=test") == ""

    def test_api_engines_require_config(self):
        """API 引擎缺少 Key 时报 ConfigError"""
        from souwen.core.exceptions import ConfigError
        from souwen.web.tavily import TavilyClient
        from souwen.web.exa import ExaClient
        from souwen.web.serper import SerperClient
        from souwen.web.brave_api import BraveApiClient
        import pytest

        for cls in [TavilyClient, ExaClient, SerperClient, BraveApiClient]:
            with pytest.raises(ConfigError):
                cls()


class TestUnifiedSearch:
    """统一搜索门面测试"""

    def test_search_facade_imports(self):
        """统一搜索模块导入"""
        from souwen.search import search, search_papers, search_patents, web_search

        assert callable(search)
        assert callable(search_papers)
        assert callable(search_patents)
        assert callable(web_search)

    def test_search_paper_sources_mapping(self):
        """论文数据源映射完整性（v1 从 registry 派生）

        v0 有 `_PAPER_SOURCES` 和 `_DEFAULT_PAPER_SOURCES`。
        v1 改为 `registry.by_domain_and_capability('paper', 'search')` 和
        `search._default_paper_sources()`。
        """
        from souwen.registry import by_domain_and_capability
        from souwen.search import _default_paper_sources

        paper_adapters = by_domain_and_capability("paper", "search")
        assert len(paper_adapters) == 18  # 19 paper 源中 unpaywall 只有 find_oa，不含 search
        defaults = _default_paper_sources()
        assert defaults  # 必须非空
        names = {a.name for a in paper_adapters}
        for s in defaults:
            assert s in names, f"默认源 {s} 不在 paper adapters 中"

    def test_search_patent_sources_mapping(self):
        """专利数据源映射完整性（v1 从 registry 派生）"""
        from souwen.registry import by_domain_and_capability
        from souwen.search import _default_patent_sources

        patent_adapters = by_domain_and_capability("patent", "search")
        assert len(patent_adapters) == 8  # 8 个专利源全部支持 search
        defaults = _default_patent_sources()
        assert defaults
        names = {a.name for a in patent_adapters}
        for s in defaults:
            assert s in names, f"默认源 {s} 不在 patent adapters 中"

    @pytest.mark.asyncio
    async def test_search_invalid_domain(self):
        """搜索无效领域抛出 ValueError"""
        from souwen.search import search

        with pytest.raises(ValueError, match="未知搜索领域"):
            await search("test", domain="invalid")


class TestYAMLConfig:
    """YAML 配置测试"""

    def test_yaml_load_empty(self):
        """无 YAML 文件时返回空字典"""
        from souwen.config import _load_yaml_config

        # In test env, no souwen.yaml exists in CWD
        result = _load_yaml_config()
        assert isinstance(result, dict)

    def test_reload_config(self):
        """reload_config 返回新配置"""
        from souwen.config import reload_config, get_config

        cfg1 = get_config()
        cfg2 = reload_config()
        assert cfg1.timeout == cfg2.timeout

    def test_config_yaml_example_exists(self):
        """souwen.example.yaml 存在"""
        from pathlib import Path

        # 相对于项目根目录查找（支持 CI 环境）
        repo_root = Path(__file__).resolve().parent.parent
        example = repo_root / "souwen.example.yaml"
        assert example.exists(), f"souwen.example.yaml not found at {example}"


class TestCLI:
    """CLI 工具测试"""

    def test_cli_app_exists(self):
        """CLI app 可导入"""
        from souwen.cli import app

        assert app is not None

    def test_cli_mask_value(self):
        """Key 脱敏：不泄漏实际值，区分已配置/未配置"""
        from souwen.cli import _mask_value

        assert "未配置" in _mask_value(None)
        assert "未配置" in _mask_value("")
        # 已配置：仅显示长度，不泄漏任何前缀
        long_masked = _mask_value("abcdef123")
        assert "已配置" in long_masked
        assert "abcd" not in long_masked  # 不再泄漏前缀
        assert "9" in long_masked  # 包含长度信息
        # 已配置：短值同样不泄漏
        short_masked = _mask_value("ab")
        assert "已配置" in short_masked
        assert "ab" not in short_masked

    def test_cli_all_sources_data(self):
        """数据源清单完整性（v1 从 registry 派生）

        注意：v0 的 `ALL_SOURCES` 与 `source_meta` 之间存在漂移
        （bing_cn / ddg_news / ddg_images / ddg_videos / metaso / twitter / facebook
        在 source_meta 登记但 ALL_SOURCES 漏列）。
        v1 统一由 registry 派生，修复漂移；因此 general/social 数字比 v0 更高。
        """
        from souwen.models import ALL_SOURCES

        assert len(ALL_SOURCES["paper"]) == 18
        assert len(ALL_SOURCES["patent"]) == 6
        total_web = sum(
            len(ALL_SOURCES[c])
            for c in ("general", "professional", "social", "developer", "wiki", "video")
        )
        # v0 期望 31；v1 修复漂移后为 39
        assert total_web == 39
        assert len(ALL_SOURCES["fetch"]) >= 21  # 21 内置 + 可能有外部插件
        # cn_tech 拆分后独立源
        assert len(ALL_SOURCES["cn_tech"]) == 9


class TestServer:
    """FastAPI 服务测试"""

    def test_server_imports(self):
        """服务模块可导入"""
        try:
            from souwen.server.app import app

            assert app is not None
            assert app.title == "SouWen API"
        except ImportError:
            pytest.skip("fastapi not installed")

    def test_server_routes_exist(self):
        """路由端点存在"""
        try:
            from souwen.server.app import app

            routes = [r.path for r in app.routes]
            assert "/health" in routes
        except ImportError:
            pytest.skip("fastapi not installed")


class TestSourceRegistryIntegrationType:
    """数据源注册表 — get_sources_by_integration_type() 测试"""

    def test_each_integration_type_non_empty(self):
        """4 种集成类型均应返回非空列表"""
        for itype in INTEGRATION_TYPES:
            sources = get_sources_by_integration_type(itype)
            assert len(sources) > 0, f"集成类型 {itype} 不应为空"

    def test_returned_sources_have_correct_type(self):
        """返回的 SourceMeta 的 integration_type 必须与查询一致"""
        for itype in INTEGRATION_TYPES:
            sources = get_sources_by_integration_type(itype)
            for meta in sources:
                assert meta.integration_type == itype, (
                    f"源 {meta.name} 的 integration_type={meta.integration_type} "
                    f"与查询 {itype} 不一致"
                )

    def test_union_covers_all_sources(self):
        """4 种集成类型的并集应覆盖所有已注册数据源"""
        all_sources = get_all_sources()
        union: set[str] = set()
        for itype in INTEGRATION_TYPES:
            union.update(meta.name for meta in get_sources_by_integration_type(itype))
        assert union == set(all_sources.keys()), (
            f"集成类型并集与全集不一致，缺失: {set(all_sources.keys()) - union}，"
            f"多余: {union - set(all_sources.keys())}"
        )

    def test_unknown_type_returns_empty(self):
        """未知集成类型应返回空列表"""
        assert get_sources_by_integration_type("nonexistent_type") == []
        assert get_sources_by_integration_type("") == []


class TestSourceRegistryCatalogViews:
    """数据源注册表 — source catalog 维度查询测试"""

    def test_auth_requirement_views_cover_all_sources(self):
        """鉴权分层并集应覆盖所有已注册数据源。"""
        all_sources = get_all_sources()
        union: set[str] = set()
        for requirement in AUTH_REQUIREMENT_TYPES:
            sources = get_sources_by_auth_requirement(requirement)
            for meta in sources:
                assert meta.auth_requirement == requirement
            union.update(meta.name for meta in sources)
        assert union == set(all_sources.keys())

    def test_distribution_views_cover_all_sources(self):
        """分发范围并集应覆盖所有已注册数据源。"""
        all_sources = get_all_sources()
        union: set[str] = set()
        for distribution in DISTRIBUTION_TYPES:
            sources = get_sources_by_distribution(distribution)
            for meta in sources:
                assert meta.distribution == distribution
            union.update(meta.name for meta in sources)
        assert union == set(all_sources.keys())

    def test_known_optional_and_multifield_sources(self):
        """可选凭据与多字段凭据的代表源元数据应稳定。"""
        sources = get_all_sources()
        openalex = sources["openalex"]
        assert openalex.auth_requirement == "optional"
        assert openalex.needs_config is False
        assert openalex.optional_credential_effect == "politeness"
        assert openalex.credential_fields == ("openalex_email",)

        epo_ops = sources["epo_ops"]
        assert epo_ops.auth_requirement == "required"
        assert epo_ops.credential_fields == ("epo_consumer_key", "epo_consumer_secret")

    def test_unknown_catalog_views_return_empty(self):
        """未知 catalog 维度值应返回空列表。"""
        assert get_sources_by_auth_requirement("unknown") == []
        assert get_sources_by_distribution("unknown") == []


class TestOAuthTokenConcurrency:
    """OAuth token 并发刷新测试"""

    @pytest.mark.asyncio
    async def test_ensure_token_is_serialized(self):
        """10 个并发 _ensure_token 只会打一次 token 端点"""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from souwen.core.http_client import OAuthClient

        client = OAuthClient(
            base_url="https://example.com",
            token_url="https://example.com/oauth/token",
            client_id="cid",
            client_secret="sec",
        )
        try:

            async def fake_post(*args, **kwargs):
                await asyncio.sleep(0.01)
                resp = MagicMock()
                resp.status_code = 200
                resp.json = MagicMock(return_value={"access_token": "tok_xyz", "expires_in": 1200})
                return resp

            client._client.post = AsyncMock(side_effect=fake_post)

            tokens = await asyncio.gather(*[client._ensure_token() for _ in range(10)])

            assert all(t == "tok_xyz" for t in tokens)
            assert client._client.post.await_count == 1
        finally:
            await client.close()
