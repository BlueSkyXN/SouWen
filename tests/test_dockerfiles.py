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


@pytest.mark.parametrize(
    ("tool", "version_arg"),
    [("wgcf", "WGCF_VERSION"), ("wireproxy", "WIREPROXY_VERSION"), ("usque", "USQUE_VERSION")],
)
def test_both_images_install_the_same_warp_components(tool: str, version_arg: str):
    """WarpManager's auto chain is usque > wireproxy > none.

    The Space image installed only wireproxy and wgcf, so it fell back to
    wireproxy and never came up (WARP 代理验证超时), while the root image
    worked through usque. A deploy-time check caught it; this test keeps the
    two images from drifting again.
    """

    for dockerfile in (Path("Dockerfile"), Path("cloud/hfs/Dockerfile")):
        text = dockerfile.read_text(encoding="utf-8")
        assert f"ARG {version_arg}=" in text, f"{dockerfile} has no {version_arg}"
        assert f"verify {tool} " in text, f"{dockerfile} does not checksum {tool}"
        assert f"/usr/local/bin/{tool}" in text, f"{dockerfile} does not install {tool}"


@pytest.mark.parametrize(
    "dockerfile",
    [Path("Dockerfile"), Path("cloud/hfs/Dockerfile")],
)
def test_warp_checksums_cover_every_installed_component(dockerfile: Path):
    """A component installed without a checksum line would fail the build."""

    text = dockerfile.read_text(encoding="utf-8")
    checksums = Path("scripts/warp-checksums.txt").read_text(encoding="utf-8")

    for tool in ("wgcf", "wireproxy", "usque"):
        if f"verify {tool} " not in text:
            continue
        assert f"\n{tool} " in f"\n{checksums}"


@pytest.mark.parametrize(
    "dockerfile",
    [Path("Dockerfile"), Path("cloud/hfs/Dockerfile")],
)
def test_playwright_browsers_are_installed_after_libatomic1(dockerfile: Path):
    """The bundled node driver needs libatomic.so.1 before --with-deps can run."""

    text = dockerfile.read_text(encoding="utf-8")

    assert "playwright install" in text
    assert "libatomic1" in text
    assert text.index("libatomic1") < text.index("playwright install")
