"""SouWen 基础设施层测试"""

import pytest
from souwen.models import (
    PaperResult,
    PatentResult,
    SearchResponse,
    Author,
    Applicant,
    SourceType,
)
from souwen.exceptions import (
    SouWenError,
    ConfigError,
    AuthError,
    RateLimitError,
    SourceUnavailableError,
    ParseError,
    NotFoundError,
)
from souwen.config import SouWenConfig, get_config
from souwen.rate_limiter import TokenBucketLimiter, SlidingWindowLimiter


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

    def test_source_type_enum(self):
        """数据源枚举完整性"""
        assert SourceType.OPENALEX.value == "openalex"
        assert SourceType.GOOGLE_PATENTS.value == "google_patents"
        # 确保论文和专利源都存在
        paper_sources = [
            SourceType.OPENALEX, SourceType.SEMANTIC_SCHOLAR,
            SourceType.CROSSREF, SourceType.ARXIV, SourceType.DBLP,
            SourceType.CORE, SourceType.PUBMED, SourceType.UNPAYWALL,
        ]
        patent_sources = [
            SourceType.PATENTSVIEW, SourceType.USPTO_ODP,
            SourceType.EPO_OPS, SourceType.CNIPA, SourceType.THE_LENS,
            SourceType.PQAI, SourceType.PATSNAP, SourceType.GOOGLE_PATENTS,
        ]
        assert len(paper_sources) == 8
        assert len(patent_sources) == 8


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
