"""Deterministic normalized legacy responses shared by batch-one integration tests."""

from __future__ import annotations

from datetime import date

from souwen.models import Author, PaperResult, PatentResult, SearchResponse


def response(source: str, *results: object) -> SearchResponse:
    return SearchResponse(
        query="conformance",
        source=source,
        total_results=len(results),
        page=1,
        per_page=10,
        results=list(results),
    )


def batch_one_paper(provider_id: str) -> PaperResult:
    values = {
        "arxiv": {"source_url": "https://arxiv.org/abs/2601.00001"},
        "biorxiv": {
            "doi": "10.1101/2026.01.01.000001",
            "source_url": "https://doi.org/10.1101/2026.01.01.000001",
            "raw": {"type": "new result"},
        },
        "crossref": {
            "doi": "10.1000/crossref-v2",
            "source_url": "https://doi.org/10.1000/crossref-v2",
            "raw": {"type": "journal-article"},
            "citation_count": 2,
        },
        "dblp": {
            "doi": "10.1000/dblp-v2",
            "source_url": "https://doi.org/10.1000/dblp-v2",
            "raw": {"type": "Conference and Workshop Papers"},
        },
        "europepmc": {
            "source_url": "https://europepmc.org/article/MED/123456",
            "raw": {"id": "123456", "is_open_access": True},
            "citation_count": 3,
        },
        "hal": {
            "source_url": "https://hal.science/hal-123456",
            "raw": {"hal_id": "hal-123456", "doc_type": "ART"},
        },
        "huggingface": {
            "source_url": "https://huggingface.co/papers/2601.00001",
            "raw": {"arxiv_id": "2601.00001"},
        },
        "iacr": {
            "source_url": "https://eprint.iacr.org/2026/1",
            "raw": {"paper_id": "2026/1"},
        },
        "osti": {
            "source_url": "https://www.osti.gov/biblio/3012392",
            "raw": {"osti_id": "3012392", "product_type": "Report"},
        },
        "pmc": {
            "source_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123456/",
            "raw": {"pmcid": "PMC123456"},
        },
        "pubmed": {
            "doi": "10.1000/pubmed-v2",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/123456/",
            "raw": {"pmid": "123456"},
        },
    }[provider_id]
    return PaperResult(
        source=provider_id,
        title=f"{provider_id} conformance record",
        authors=[Author(name="Batch One Researcher")],
        abstract="Deterministic provider fixture",
        year=2026,
        **values,
    )


def google_patent() -> PatentResult:
    return PatentResult(
        source="google_patents",
        patent_id="US1234567A",
        title="Google Patents conformance record",
        publication_date=date(2026, 1, 2),
        source_url="https://patents.google.com/patent/US1234567A/en",
    )


__all__ = ["batch_one_paper", "google_patent", "response"]
