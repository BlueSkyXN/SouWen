"""Volcengine Ark Responses annotation parsing for model-bound web search sources."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

from souwen.models import SearchCandidate, SearchSnippet, SearchSourceProvenance


def build_ark_request(query: str, model_id: str, *, max_keyword: int = 10) -> dict:
    """Build the fixed Ark Responses payload; callers cannot supply a dynamic model."""
    if not query.strip() or not model_id.strip() or not 1 <= max_keyword <= 50:
        raise ValueError("invalid Ark search request")
    return {
        "model": model_id,
        "input": query.strip(),
        "tools": [{"type": "web_search", "max_keyword": max_keyword}],
    }


def parse_ark_annotations(
    payload: Mapping, provenance: SearchSourceProvenance
) -> list[SearchCandidate]:
    """Parse only completed search annotations; never infer sources from final answer text."""
    candidates: list[SearchCandidate] = []
    saw_completed_search = False
    for output in payload.get("output", []):
        if not isinstance(output, Mapping) or output.get("status") != "completed":
            continue
        content = output.get("content") or output.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            annotations = part.get("annotations", [])
            if annotations:
                saw_completed_search = True
            for annotation in annotations:
                if not isinstance(annotation, Mapping):
                    continue
                url = annotation.get("url") or annotation.get("source_url")
                title = annotation.get("title")
                if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
                    continue
                parsed = urlsplit(url)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    continue
                summary = annotation.get("summary") or annotation.get("snippet")
                candidates.append(
                    SearchCandidate(
                        title=title.strip(),
                        url=url,
                        provider_snippet=(
                            SearchSnippet(
                                text=summary, type="provider_summary", provider="volcengine_ark"
                            )
                            if isinstance(summary, str) and summary.strip()
                            else None
                        ),
                        published_at=annotation.get("publish_time")
                        if isinstance(annotation.get("publish_time"), str)
                        else None,
                        site_name=annotation.get("site_name")
                        if isinstance(annotation.get("site_name"), str)
                        else None,
                        favicon_url=annotation.get("logo")
                        if isinstance(annotation.get("logo"), str)
                        else None,
                        provenance=provenance,
                    )
                )
    if not saw_completed_search:
        raise ValueError("Ark response has no completed search annotations")
    return candidates
