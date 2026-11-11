from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "dockerfile",
    [
        Path("Dockerfile"),
        Path("cloud/hfs/Dockerfile"),
    ],
)
def test_dockerfiles_exclude_removed_pdf_capture_stack(dockerfile: Path):
    text = dockerfile.read_text(encoding="utf-8")

    for removed in ("WITH_WEB2PDF", "WEB2PDF_PACKAGE", "superweb2pdf", "pymupdf4llm"):
        assert removed not in text


@pytest.mark.parametrize(
    "dockerfile",
    [Path("Dockerfile"), Path("cloud/hfs/Dockerfile")],
)
def test_runtime_base_images_are_pinned_by_digest(dockerfile: Path):
    from_lines = [
        line
        for line in dockerfile.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ")
    ]

    assert from_lines
    assert all(re.search(r"@sha256:[0-9a-f]{64}(?:\s|$)", line) for line in from_lines)


@pytest.mark.parametrize(
    "dockerfile",
    [Path("cloud/hfs/Dockerfile")],
)
def test_remote_source_images_require_immutable_commit_sha(dockerfile: Path):
    text = dockerfile.read_text(encoding="utf-8")

    assert "ARG SOUWEN_REF=0000000000000000000000000000000000000000" in text
    assert "ARG SOUWEN_REF=main" not in text
    assert 'git fetch --depth 1 origin "${SOUWEN_REF}"' in text
    assert 'test "$(git rev-parse HEAD)" = "${SOUWEN_REF}"' in text
    assert "runtime.source.sha" in text


def test_root_image_accepts_explicit_source_sha():
    text = Path("Dockerfile").read_text(encoding="utf-8")

    assert 'ARG SOUWEN_SOURCE_SHA=""' in text
    assert "SOUWEN_SOURCE_SHA_FILE=/app/runtime.source.sha" in text
    assert "'^[0-9a-fA-F]{40}$'" in text
