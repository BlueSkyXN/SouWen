"""tests/test_paper/test_new_sources package — 新增论文源解析测试

覆盖 7 个新增论文搜索客户端的静态解析方法（不发起真实 HTTP）：
EuropePMC / PMC / DOAJ / Zenodo / HAL / OpenAIRE / IACR。

测试聚焦在各 ``_parse_*`` 静态/类方法上，使用代表性 fixture 数据校验
字段映射不变量与缺失字段的容错行为。
"""

from __future__ import annotations

from datetime import date

import defusedxml.ElementTree as ET
import pytest
from bs4 import BeautifulSoup

from souwen.models import SourceType
from souwen.paper.doaj import DoajClient
from souwen.paper.europepmc import EuropePmcClient
from souwen.paper.hal import HalClient
from souwen.paper.iacr import IacrClient
from souwen.paper.openaire import OpenAireClient
from souwen.paper.pmc import PmcClient
from souwen.paper.zenodo import ZenodoClient


# =============================================================================
# 1. EuropePMC
# =============================================================================


class TestEuropePmc:
    SAMPLE = {
        "id": "12345678",
        "pmid": "12345678",
        "source": "MED",
        "title": "A study on machine learning in healthcare",
        "authorList": {
            "author": [{"fullName": "Smith J"}, {"fullName": "Doe A"}],
        },
        "abstractText": "Background: Machine learning has shown promise...",
        "doi": "10.1234/test.2024.001",
        "pubYear": "2024",
        "firstPublicationDate": "2024-03-15",
        "journalTitle": "Nature Medicine",
        "citedByCount": 42,
        "isOpenAccess": "Y",
        "fullTextUrlList": {
            "fullTextUrl": [
                {"documentStyle": "pdf", "url": "https://europepmc.org/pdf/12345678"},
                {"documentStyle": "html", "url": "https://europepmc.org/article/12345678"},
            ]
        },
        "keywordList": {"keyword": ["machine learning", "healthcare"]},
    }

    def test_parse_result_basic(self):
        paper = EuropePmcClient._parse_result(self.SAMPLE)

        assert paper.title == "A study on machine learning in healthcare"
        assert [a.name for a in paper.authors] == ["Smith J", "Doe A"]
        assert paper.abstract.startswith("Background: Machine learning")
        assert paper.doi == "10.1234/test.2024.001"
        assert paper.year == 2024
        assert paper.journal == "Nature Medicine"
        assert paper.citation_count == 42
        assert paper.pdf_url == "https://europepmc.org/pdf/12345678"
        assert paper.source == SourceType.EUROPEPMC
        # PMID 优先级用于 source_url
        assert "12345678" in paper.source_url
        assert paper.raw["is_open_access"] is True
        assert "machine learning" in paper.raw["keywords"]

    def test_parse_result_missing_fields(self):
        minimal = {"id": "999", "title": "Minimal Paper"}
        paper = EuropePmcClient._parse_result(minimal)

        assert paper.title == "Minimal Paper"
        assert paper.authors == []
        assert paper.doi is None
        assert paper.year is None
        assert paper.citation_count is None
        assert paper.pdf_url is None
        assert paper.journal is None
        assert paper.raw["is_open_access"] is False
        # source_url 总有 fallback
        assert paper.source_url.startswith("https://europepmc.org/")


# =============================================================================
# 2. PMC (JATS XML)
# =============================================================================


_PMC_XML = """<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmc">PMC1234567</article-id>
      <article-id pub-id-type="doi">10.1234/test.001</article-id>
      <title-group><article-title>Test Paper Title</article-title></title-group>
      <contrib-group>
        <contrib contrib-type="author"><name><surname>Smith</surname><given-names>John</given-names></name></contrib>
        <contrib contrib-type="author"><name><surname>Doe</surname><given-names>Jane</given-names></name></contrib>
      </contrib-group>
      <abstract><p>This is the abstract text.</p></abstract>
      <pub-date pub-type="epub"><year>2024</year><month>03</month><day>15</day></pub-date>
      <journal-title-group><journal-title>BMC Medicine</journal-title></journal-title-group>
    </article-meta>
  </front>
</article>"""


_PMC_XML_NO_ABSTRACT = """<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmc">7654321</article-id>
      <title-group><article-title>No Abstract Paper</article-title></title-group>
      <contrib-group>
        <contrib contrib-type="author"><name><surname>Lee</surname><given-names>Min</given-names></name></contrib>
      </contrib-group>
      <pub-date pub-type="epub"><year>2023</year></pub-date>
    </article-meta>
  </front>
</article>"""


class TestPmc:
    def test_parse_article_basic(self):
        root = ET.fromstring(_PMC_XML)
        paper = PmcClient._parse_article(root)

        assert paper.title == "Test Paper Title"
        assert paper.doi == "10.1234/test.001"
        assert paper.year == 2024
        assert paper.publication_date == date(2024, 3, 15)
        assert paper.journal == "BMC Medicine"
        assert paper.abstract == "This is the abstract text."
        assert len(paper.authors) == 2
        assert paper.authors[0].name == "John Smith"
        assert paper.authors[1].name == "Jane Doe"
        assert paper.source == SourceType.PMC
        assert "PMC1234567" in paper.source_url
        assert paper.pdf_url and "PMC1234567" in paper.pdf_url
        assert paper.raw["pmcid"] == "PMC1234567"

    def test_parse_article_missing_abstract(self):
        root = ET.fromstring(_PMC_XML_NO_ABSTRACT)
        paper = PmcClient._parse_article(root)

        assert paper.title == "No Abstract Paper"
        assert paper.abstract == ""
        assert paper.doi is None
        assert paper.year == 2023
        assert paper.journal is None
        assert len(paper.authors) == 1
        # PMCID 自动归一化加 PMC 前缀
        assert paper.raw["pmcid"] == "PMC7654321"


# =============================================================================
# 3. DOAJ
# =============================================================================


class TestDoaj:
    SAMPLE = {
        "id": "abcdef1234567890",
        "bibjson": {
            "title": "Open Access Publishing Trends",
            "author": [{"name": "Author One"}, {"name": "Author Two"}],
            "abstract": "This paper examines trends in OA publishing...",
            "identifier": [{"type": "doi", "id": "10.5678/doaj.test"}],
            "year": "2024",
            "month": "6",
            "journal": {"title": "Journal of OA", "publisher": "OA Press"},
            "keywords": ["open access", "publishing"],
            "link": [{"type": "fulltext", "url": "https://example.com/paper.pdf"}],
        },
    }

    def test_parse_result_basic(self):
        paper = DoajClient._parse_result(self.SAMPLE)

        assert paper.title == "Open Access Publishing Trends"
        assert [a.name for a in paper.authors] == ["Author One", "Author Two"]
        assert paper.abstract == "This paper examines trends in OA publishing..."
        assert paper.doi == "10.5678/doaj.test"
        assert paper.year == 2024
        assert paper.publication_date == date(2024, 6, 1)
        assert paper.journal == "Journal of OA"
        assert paper.pdf_url == "https://example.com/paper.pdf"
        assert paper.citation_count is None
        assert paper.raw["doaj_id"] == "abcdef1234567890"
        assert paper.raw["publisher"] == "OA Press"
        assert paper.raw["keywords"] == ["open access", "publishing"]

    def test_parse_abstract_dict_format(self):
        sample = {
            "id": "x1",
            "bibjson": {
                "title": "Dict abstract paper",
                "abstract": {"text": "Abstract from dict"},
            },
        }
        paper = DoajClient._parse_result(sample)
        assert paper.abstract == "Abstract from dict"
        assert paper.doi is None
        assert paper.year is None
        assert paper.publication_date is None


# =============================================================================
# 4. Zenodo
# =============================================================================


class TestZenodo:
    SAMPLE = {
        "id": 12345,
        "metadata": {
            "title": "Dataset and Analysis Tools",
            "creators": [{"name": "Doe, John"}, {"name": "Smith, Jane"}],
            "description": "<p>This is an <b>HTML</b> abstract.</p>",
            "publication_date": "2024-01-15",
            "doi": "10.5281/zenodo.12345",
            "keywords": ["analysis", "tools"],
            "resource_type": {"type": "publication", "subtype": "article"},
        },
        "files": [
            {
                "key": "paper.pdf",
                "links": {"self": "https://zenodo.org/api/files/abc/paper.pdf"},
            }
        ],
        "links": {"html": "https://zenodo.org/records/12345"},
    }

    def test_parse_record_basic(self):
        paper = ZenodoClient._parse_record(self.SAMPLE)

        assert paper.title == "Dataset and Analysis Tools"
        assert [a.name for a in paper.authors] == ["Doe, John", "Smith, Jane"]
        assert paper.doi == "10.5281/zenodo.12345"
        assert paper.year == 2024
        assert paper.publication_date == date(2024, 1, 15)
        assert paper.pdf_url == "https://zenodo.org/api/files/abc/paper.pdf"
        assert paper.source_url == "https://zenodo.org/records/12345"
        assert paper.raw["zenodo_id"] == 12345
        assert paper.raw["keywords"] == ["analysis", "tools"]
        assert paper.raw["resource_subtype"] == "article"

    def test_strip_html(self):
        paper = ZenodoClient._parse_record(self.SAMPLE)
        assert paper.abstract is not None
        assert "<" not in paper.abstract
        assert ">" not in paper.abstract
        assert "HTML" in paper.abstract

    def test_no_pdf_files(self):
        sample = {
            "id": 999,
            "metadata": {
                "title": "No PDF Record",
                "publication_date": "2023-05-01",
            },
            "files": [{"key": "data.csv", "links": {"self": "https://zenodo.org/data.csv"}}],
            "links": {"html": "https://zenodo.org/records/999"},
        }
        paper = ZenodoClient._parse_record(sample)
        assert paper.pdf_url is None
        assert paper.year == 2023
        assert paper.source_url == "https://zenodo.org/records/999"


# =============================================================================
# 5. HAL
# =============================================================================


class TestHal:
    SAMPLE = {
        "halId_s": "hal-03123456",
        "title_s": ["A Study on French Archives"],
        "authFullName_s": ["Jean Dupont", "Marie Martin"],
        "abstract_s": ["This paper studies..."],
        "doiId_s": "10.1234/hal.test",
        "producedDateY_i": 2024,
        "submittedDate_s": "2024-02-20 10:00:00",
        "fileMain_s": "https://hal.archives-ouvertes.fr/hal-03123456/file/paper.pdf",
        "uri_s": "https://hal.archives-ouvertes.fr/hal-03123456",
        "docType_s": "ART",
        "journalTitle_s": "Archives Journal",
    }

    def test_parse_doc_basic(self):
        paper = HalClient._parse_doc(self.SAMPLE)

        # 数组字段被解包为首元素
        assert paper.title == "A Study on French Archives"
        assert paper.abstract == "This paper studies..."
        assert [a.name for a in paper.authors] == ["Jean Dupont", "Marie Martin"]
        assert paper.doi == "10.1234/hal.test"
        assert paper.year == 2024
        assert paper.publication_date == date(2024, 2, 20)
        assert paper.pdf_url == "https://hal.archives-ouvertes.fr/hal-03123456/file/paper.pdf"
        assert paper.source_url == "https://hal.archives-ouvertes.fr/hal-03123456"
        assert paper.journal == "Archives Journal"
        assert paper.source == SourceType.HAL
        assert paper.raw["hal_id"] == "hal-03123456"
        assert paper.raw["doc_type"] == "ART"

    def test_parse_doc_missing_arrays(self):
        sample = {
            "halId_s": "hal-99999",
            "title_s": ["Minimal HAL Doc"],
        }
        paper = HalClient._parse_doc(sample)
        assert paper.title == "Minimal HAL Doc"
        assert paper.authors == []
        assert paper.doi is None
        assert paper.year is None
        assert paper.publication_date is None
        assert paper.pdf_url is None
        assert paper.journal is None
        # 没有 uri_s 时基于 hal_id 构造
        assert paper.source_url == "https://hal.science/hal-99999"


# =============================================================================
# 6. OpenAIRE
# =============================================================================


class TestOpenAire:
    SAMPLE = {
        "metadata": {
            "oaf:entity": {
                "oaf:result": {
                    "title": {"$": "EU Research Product Title", "@classid": "main title"},
                    "creator": [
                        {"$": "Author Alpha", "@rank": "1"},
                        {"$": "Author Beta", "@rank": "2"},
                    ],
                    "description": {"$": "This is the abstract of the research product."},
                    "pid": [{"$": "10.9999/openaire.test", "@classid": "doi"}],
                    "dateofacceptance": {"$": "2024-06-01"},
                    "journal": {"$": "EU Science Journal", "@issn": "1234-5678"},
                    "children": {
                        "instance": [
                            {"webresource": [{"url": {"$": "https://example.com/paper.pdf"}}]}
                        ]
                    },
                }
            }
        }
    }

    def test_extract_text_dict(self):
        assert OpenAireClient._extract_text({"$": "hello"}) == "hello"
        assert OpenAireClient._extract_text({"$": None}) == ""
        assert OpenAireClient._extract_text({}) == ""

    def test_extract_text_string(self):
        assert OpenAireClient._extract_text("plain") == "plain"
        assert OpenAireClient._extract_text(None) == ""
        assert OpenAireClient._extract_text(123) == "123"

    def test_parse_result_basic(self):
        paper = OpenAireClient._parse_result(self.SAMPLE)

        assert paper.title == "EU Research Product Title"
        assert [a.name for a in paper.authors] == ["Author Alpha", "Author Beta"]
        assert paper.abstract == "This is the abstract of the research product."
        assert paper.doi == "10.9999/openaire.test"
        assert paper.year == 2024
        assert paper.publication_date == date(2024, 6, 1)
        assert paper.journal == "EU Science Journal"
        assert paper.pdf_url == "https://example.com/paper.pdf"
        assert paper.source_url == "https://example.com/paper.pdf"
        assert paper.source == SourceType.OPENAIRE


# =============================================================================
# 7. IACR
# =============================================================================


_IACR_HTML = """<div class="mb-4">
  <a class="paperlink" href="/2025/1014">2025/1014</a>
  <strong>A New Cryptographic Protocol</strong>
  <span class="fst-italic">Alice Crypto, Bob Security</span>
  <p class="search-abstract">We present a novel approach to...</p>
  <small class="badge">cryptographic protocols</small>
</div>"""


_IACR_HTML_MINIMAL = """<div class="mb-4">
  <a class="paperlink" href="/2024/0001">2024/0001</a>
  <strong>Bare Title Only</strong>
</div>"""


class TestIacr:
    def test_parse_result_block_basic(self):
        soup = BeautifulSoup(_IACR_HTML, "lxml")
        block = soup.select_one("div.mb-4")
        paper = IacrClient._parse_result_block(block)

        assert paper is not None
        assert paper.title == "A New Cryptographic Protocol"
        assert paper.year == 2025
        assert paper.source == SourceType.IACR
        assert paper.source_url == "https://eprint.iacr.org/2025/1014"
        assert paper.pdf_url == "https://eprint.iacr.org/2025/1014.pdf"
        assert paper.abstract == "We present a novel approach to..."
        assert [a.name for a in paper.authors] == ["Alice Crypto", "Bob Security"]
        assert paper.venue == "cryptographic protocols"
        assert paper.raw["paper_id"] == "2025/1014"
        assert paper.raw["categories"] == ["cryptographic protocols"]

    def test_parse_result_block_missing_fields(self):
        soup = BeautifulSoup(_IACR_HTML_MINIMAL, "lxml")
        block = soup.select_one("div.mb-4")
        paper = IacrClient._parse_result_block(block)

        assert paper is not None
        assert paper.title == "Bare Title Only"
        assert paper.year == 2024
        assert paper.authors == []
        assert paper.abstract is None
        assert paper.venue is None
        assert paper.raw["paper_id"] == "2024/0001"
        assert paper.raw["categories"] == []


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
