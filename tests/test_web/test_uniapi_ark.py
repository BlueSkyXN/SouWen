from __future__ import annotations

import pytest

from souwen.models import SearchSourceProvenance
from souwen.web.llm_search.schemes.ark_annotations import build_ark_request, parse_ark_annotations


def _provenance():
    return SearchSourceProvenance(
        source_id="ark_fixture", scheme_id="uniapi_ark_annotations_v1", requested_model_id="fixture"
    )


def test_ark_parser_uses_only_completed_structured_annotations():
    payload = {
        "output": [
            {
                "status": "completed",
                "content": [
                    {
                        "annotations": [
                            {"title": "Real", "url": "https://example.com/a", "summary": "S"}
                        ]
                    }
                ],
            }
        ]
    }
    candidates = parse_ark_annotations(payload, _provenance())
    assert candidates[0].title == "Real"
    assert candidates[0].provider_snippet.type == "provider_summary"


def test_ark_parser_fails_closed_without_completed_annotations():
    with pytest.raises(ValueError, match="no completed"):
        parse_ark_annotations({"output": [{"status": "in_progress", "content": []}]}, _provenance())


def test_ark_request_binds_model_and_tool_shape():
    assert build_ark_request("q", "model") == {
        "model": "model",
        "input": "q",
        "tools": [{"type": "web_search", "max_keyword": 10}],
    }
