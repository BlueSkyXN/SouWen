"""bioRxiv / medRxiv 预印本源解析测试。"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.models import SourceType
from souwen.paper.biorxiv import BioRxivClient


class TestBioRxiv:
    SAMPLE = {
        "doi": "10.1101/2024.01.01.123456",
        "title": "Neural mechanisms of memory consolidation",
        "authors": "Author One; Author Two; Author Three",
        "author_corresponding": "Author One",
        "author_corresponding_institution": "MIT",
        "date": "2024-01-15",
        "version": "1",
        "type": "new results",
        "license": "cc_by",
        "category": "neuroscience",
        "jatsxml": "https://www.biorxiv.org/content/10.1101/2024.01.01.123456v1.source.xml",
        "abstract": "Memory consolidation depends on coordinated neural activity.",
        "published": "NA",
        "server": "biorxiv",
    }

    def test_parse_result_basic(self):
        paper = BioRxivClient._parse_result(self.SAMPLE)

        assert paper.title == "Neural mechanisms of memory consolidation"
        assert [a.name for a in paper.authors] == [
            "Author One",
            "Author Two",
            "Author Three",
        ]
        assert paper.abstract == "Memory consolidation depends on coordinated neural activity."
        assert paper.doi == "10.1101/2024.01.01.123456"
        assert paper.year == 2024
        assert paper.publication_date == date(2024, 1, 15)
        assert paper.source == SourceType.BIORXIV
        assert paper.source_url == "https://doi.org/10.1101/2024.01.01.123456"
        assert paper.journal == "bioRxiv"
        assert paper.venue == "neuroscience"
        assert paper.citation_count is None
        assert paper.raw["server"] == "biorxiv"
        assert paper.raw["category"] == "neuroscience"
        assert paper.raw["version"] == "1"
        assert paper.raw["license"] == "cc_by"
        assert paper.raw["author_corresponding"] == "Author One"

    def test_parse_result_medrxiv(self):
        sample = {
            **self.SAMPLE,
            "server": "medrxiv",
            "category": "epidemiology",
            "doi": "10.1101/2024.02.03.987654",
        }
        paper = BioRxivClient._parse_result(sample)

        assert paper.source == SourceType.BIORXIV
        assert paper.journal == "medRxiv"
        assert paper.venue == "epidemiology"
        assert paper.source_url == "https://doi.org/10.1101/2024.02.03.987654"
        assert paper.raw["server"] == "medrxiv"

    def test_parse_result_missing_fields(self):
        minimal = {"title": "Minimal preprint"}
        paper = BioRxivClient._parse_result(minimal)

        assert paper.title == "Minimal preprint"
        assert paper.authors == []
        assert paper.abstract == ""
        assert paper.doi is None
        assert paper.year is None
        assert paper.publication_date is None
        assert paper.source == SourceType.BIORXIV
        assert paper.source_url == "https://www.biorxiv.org/"
        assert paper.journal == "bioRxiv"
        assert paper.venue is None
        assert paper.raw["server"] == "biorxiv"

    def test_matches_query_title_or_abstract(self):
        assert BioRxivClient._matches_query(self.SAMPLE, "memory") is True
        assert BioRxivClient._matches_query(self.SAMPLE, "coordinated neural") is True
        assert BioRxivClient._matches_query(self.SAMPLE, "not-present") is False
        assert BioRxivClient._matches_query(self.SAMPLE, "") is True

    @pytest.mark.asyncio
    async def test_search_uses_api_metadata_for_pagination(self):
        """API 每页 30 条时，按 total/cursor/count 继续请求下一页。"""

        def item(index: int) -> dict[str, str]:
            return {
                **self.SAMPLE,
                "doi": f"10.1101/2024.01.01.{index:06d}",
                "title": f"Memory pagination result {index}",
            }

        page1 = {
            "messages": [{"total": "40", "count": "30", "cursor": "0"}],
            "collection": [item(i) for i in range(30)],
        }
        page2 = {
            "messages": [{"total": "40", "count": "10", "cursor": "30"}],
            "collection": [item(i) for i in range(30, 40)],
        }
        page1_resp = MagicMock()
        page1_resp.json.return_value = page1
        page2_resp = MagicMock()
        page2_resp.json.return_value = page2

        client = BioRxivClient()
        mock_get = AsyncMock(side_effect=[page1_resp, page2_resp])
        with (
            patch.object(client._limiter, "acquire", new=AsyncMock()),
            patch.object(client._client, "get", new=mock_get),
        ):
            resp = await client.search("memory", per_page=35)

        assert len(resp.results) == 35
        assert mock_get.await_count == 2
        requested_paths = [call.args[0] for call in mock_get.await_args_list]
        assert requested_paths[0].endswith("/0/json")
        assert requested_paths[1].endswith("/30/json")
