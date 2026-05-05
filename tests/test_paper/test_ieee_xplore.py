"""IEEE Xplore source tests."""

from __future__ import annotations

from datetime import date
import pytest

from souwen.core.exceptions import ConfigError
from souwen.models import SourceType
from souwen.paper.ieee_xplore import IeeeXploreClient


class TestIeeeXplore:
    SAMPLE = {
        "doi": "10.1109/TPAMI.2024.1234567",
        "title": "Paper Title",
        "authors": {
            "authors": [
                {"full_name": "John Smith", "affiliation": "MIT"},
                {"full_name": "Jane Doe", "affiliation": "Stanford"},
            ]
        },
        "abstract": "This paper studies machine learning.",
        "publication_title": "IEEE Transactions on PAMI",
        "publication_year": "2024",
        "publication_date": "15 March 2024",
        "article_number": "1234567",
        "start_page": "1",
        "end_page": "15",
        "citing_paper_count": 12345,
        "pdf_url": "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=1234567",
        "html_url": "https://ieeexplore.ieee.org/document/1234567",
        "content_type": "Journals",
        "publisher": "IEEE",
        "access_type": "Open Access",
        "index_terms": {
            "ieee_terms": {"terms": ["machine learning", "deep learning"]},
            "author_terms": {"terms": ["neural networks"]},
        },
    }

    def test_parse_article_basic(self):
        paper = IeeeXploreClient._parse_article(self.SAMPLE)

        assert paper.title == "Paper Title"
        assert [a.name for a in paper.authors] == ["John Smith", "Jane Doe"]
        assert paper.authors[0].affiliation == "MIT"
        assert paper.abstract == "This paper studies machine learning."
        assert paper.doi == "10.1109/TPAMI.2024.1234567"
        assert paper.year == 2024
        assert paper.publication_date == date(2024, 3, 15)
        assert paper.journal == "IEEE Transactions on PAMI"
        assert paper.venue == "IEEE Transactions on PAMI"
        assert paper.citation_count == 12345
        assert paper.pdf_url == "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=1234567"
        assert paper.source_url == "https://doi.org/10.1109/TPAMI.2024.1234567"
        assert paper.open_access_url == "https://ieeexplore.ieee.org/document/1234567"
        assert paper.source == SourceType.IEEE_XPLORE
        assert paper.raw["article_number"] == "1234567"
        assert paper.raw["is_open_access"] is True
        assert paper.raw["start_page"] == 1
        assert paper.raw["end_page"] == 15
        assert "machine learning" in paper.raw["ieee_terms"]
        assert "neural networks" in paper.raw["author_terms"]

    def test_parse_article_missing_fields(self):
        paper = IeeeXploreClient._parse_article({"title": "Minimal IEEE Paper"})

        assert paper.title == "Minimal IEEE Paper"
        assert paper.authors == []
        assert paper.abstract is None
        assert paper.doi is None
        assert paper.year is None
        assert paper.publication_date is None
        assert paper.citation_count == 0
        assert paper.pdf_url is None
        assert paper.journal is None
        assert paper.source_url == "https://ieeexplore.ieee.org/"
        assert paper.raw["is_open_access"] is False
        assert paper.raw["ieee_terms"] == []

    def test_parse_article_access_type_camel_case(self):
        paper = IeeeXploreClient._parse_article(
            {
                "title": "Open IEEE Paper",
                "html_url": "https://ieeexplore.ieee.org/document/7654321",
                "accessType": "OPEN_ACCESS",
            }
        )

        assert paper.open_access_url == "https://ieeexplore.ieee.org/document/7654321"
        assert paper.raw["is_open_access"] is True

    def test_parse_article_year_rejects_invalid_values(self):
        paper = IeeeXploreClient._parse_article(
            {"title": "IEEE Paper", "publication_year": "99999", "citing_paper_count": 12345}
        )

        assert paper.year is None
        assert paper.citation_count == 12345

    @pytest.mark.asyncio
    async def test_search_uses_default_sorting_and_preserves_large_total(self):
        captured_params = {}

        class DummyLimiter:
            async def acquire(self):
                return None

        class DummyResponse:
            def json(self):
                return {"total_records": "12345", "articles": []}

        class DummyClient:
            async def get(self, path, params):
                captured_params.update(params)
                assert path == "/search/articles"
                return DummyResponse()

        client = IeeeXploreClient(api_key="test-key")
        client._limiter = DummyLimiter()
        client._client = DummyClient()

        response = await client.search("machine learning", max_results=10)

        assert "sort_field" not in captured_params
        assert "sort_order" not in captured_params
        assert response.total_results == 12345

    def test_article_number_source_url_fallback(self):
        paper = IeeeXploreClient._parse_article(
            {"title": "IEEE Paper", "article_number": "9876543"}
        )

        assert paper.source_url == "https://ieeexplore.ieee.org/document/9876543"

    def test_client_without_api_key_raises_config_error(self, monkeypatch):
        monkeypatch.delenv("SOUWEN_IEEE_API_KEY", raising=False)
        monkeypatch.delenv("IEEE_API_KEY", raising=False)
        from souwen.config import reload_config

        reload_config()
        try:
            with pytest.raises(ConfigError) as exc_info:
                IeeeXploreClient()

            assert exc_info.value.key == "ieee_api_key"
            assert exc_info.value.service == "IEEE Xplore"
        finally:
            reload_config()
