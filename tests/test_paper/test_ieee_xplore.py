"""IEEE Xplore source tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

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
        "citing_paper_count": 42,
        "pdf_url": "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=1234567",
        "html_url": "https://ieeexplore.ieee.org/document/1234567",
        "content_type": "Journals",
        "publisher": "IEEE",
        "is_open_access": True,
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
        assert paper.citation_count == 42
        assert paper.pdf_url == "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=1234567"
        assert paper.source_url == "https://doi.org/10.1109/TPAMI.2024.1234567"
        assert paper.open_access_url == "https://ieeexplore.ieee.org/document/1234567"
        assert paper.source == SourceType.IEEE_XPLORE
        assert paper.raw["article_number"] == "1234567"
        assert paper.raw["is_open_access"] is True
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
        assert paper.citation_count is None
        assert paper.pdf_url is None
        assert paper.journal is None
        assert paper.source_url == "https://ieeexplore.ieee.org/"
        assert paper.raw["is_open_access"] is False
        assert paper.raw["ieee_terms"] == []

    def test_article_number_source_url_fallback(self):
        paper = IeeeXploreClient._parse_article(
            {"title": "IEEE Paper", "article_number": "9876543"}
        )

        assert paper.source_url == "https://ieeexplore.ieee.org/document/9876543"

    @pytest.mark.asyncio
    async def test_search_without_api_key_returns_empty_response(self):
        client = IeeeXploreClient(api_key="")

        with patch("souwen.paper.ieee_xplore.logger.warning") as warn:
            response = await client.search("machine learning", max_results=5)

        assert response.query == "machine learning"
        assert response.total_results == 0
        assert response.per_page == 5
        assert response.results == []
        assert response.source == SourceType.IEEE_XPLORE
        warn.assert_called_once()
        assert "ieee_api_key" in warn.call_args.args[0]
