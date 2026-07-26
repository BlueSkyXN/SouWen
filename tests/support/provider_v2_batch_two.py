"""Deterministic normalized legacy results for Batch 2 conformance/runtime tests."""

from __future__ import annotations

from datetime import date

from souwen.providers.runtime_clients.models import Author, PaperResult, PatentResult


def batch_two_paper(provider_id: str) -> PaperResult:
    common = {
        "source": provider_id,
        "title": f"{provider_id} conformance record",
        "authors": [Author(name="Batch Two Author")],
        "abstract": "Deterministic provider response.",
        "year": 2026,
    }
    if provider_id == "core":
        return PaperResult(
            **common,
            doi="10.1000/core-b2",
            source_url="https://core.ac.uk/works/CORE-B2",
            raw={"core_id": "CORE-B2", "language": "en"},
        )
    if provider_id == "doaj":
        return PaperResult(
            **common,
            source_url="https://doaj.org/article/DOAJ-B2",
            raw={"doaj_id": "DOAJ-B2"},
        )
    if provider_id == "ieee_xplore":
        return PaperResult(
            **common,
            source_url="https://ieeexplore.ieee.org/document/123456",
            citation_count=2,
            raw={"article_number": "123456", "is_open_access": True},
        )
    if provider_id == "openaire":
        return PaperResult(
            **common,
            doi="10.1000/openaire-b2",
            source_url="https://explore.openaire.eu/search/publication?pid=OPENAIRE-B2",
            raw={
                "openaire_id": "OPENAIRE-B2",
                "result_type": "publication",
                "language": "en",
            },
        )
    if provider_id == "semantic_scholar":
        return PaperResult(
            **common,
            source_url="https://www.semanticscholar.org/paper/S2-B2",
            citation_count=3,
            raw={"is_open_access": True},
        )
    if provider_id == "zenodo":
        return PaperResult(
            **common,
            source_url="https://zenodo.org/records/123456",
            raw={"zenodo_id": 123456, "resource_subtype": "article"},
        )
    if provider_id == "zotero":
        return PaperResult(
            **common,
            source_url="https://api.zotero.org/users/12345/items/ABCD1234",
            raw={
                "item_key": "ABCD1234",
                "item_type": "journalArticle",
                "library_id": "12345",
                "library_type": "user",
            },
        )
    raise ValueError("unsupported Batch 2 paper provider")


def batch_two_patent(provider_id: str) -> PatentResult:
    identifiers = {
        "cnipa": ("CN123A", "https://open.cnipr.com/patent/CN123A", {}),
        "epo_ops": (
            "EP123",
            "https://worldwide.espacenet.com/patent/search?q=EP123",
            {},
        ),
        "patsnap": ("US123", "https://connect.patsnap.com/patent/US123", {}),
        "pqai": ("US123", "https://patents.google.com/patent/US123", {}),
        "the_lens": (
            "US123",
            "https://www.lens.org/lens/patent/LENS-B2",
            {"lens_id": "LENS-B2"},
        ),
        "uspto_odp": ("US123", "https://data.uspto.gov/patent/US123", {}),
    }
    try:
        patent_id, source_url, raw = identifiers[provider_id]
    except KeyError as exc:
        raise ValueError("unsupported Batch 2 patent provider") from exc
    return PatentResult(
        source=provider_id,
        patent_id=patent_id,
        title=f"{provider_id} conformance record",
        publication_date=date(2026, 1, 2),
        source_url=source_url,
        raw=raw,
    )


__all__ = ["batch_two_paper", "batch_two_patent"]
