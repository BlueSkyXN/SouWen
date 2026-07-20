from __future__ import annotations

import re
from pathlib import Path

import pytest

SUPERWEB2PDF_ARCHIVE = (
    "https://github.com/BlueSkyXN/SuperWeb2PDF/archive/d1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip"
    "#sha256=f56a380aa3f06d169d3fcc723d5525779519afaff159b37e8a789e50b797c76b"
)


@pytest.mark.parametrize(
    "dockerfile",
    [
        Path("Dockerfile"),
        Path("cloud/hfs/Dockerfile"),
        Path("cloud/modelscope/Dockerfile"),
    ],
)
def test_web2pdf_package_build_arg_uses_resolvable_install_source(dockerfile: Path):
    text = dockerfile.read_text(encoding="utf-8")

    assert f"ARG WEB2PDF_PACKAGE={SUPERWEB2PDF_ARCHIVE}" in text
    assert "ARG WEB2PDF_PACKAGE=superweb2pdf" not in text
    assert ".[server,tls," + "web2pdf]" not in text
    assert 'pip install ".[edition-pro]" "playwright>=1.40" "${WEB2PDF_PACKAGE}"' in text
    assert 'pip install ".[server,tls]"' not in text


@pytest.mark.parametrize(
    "dockerfile",
    [Path("Dockerfile"), Path("cloud/hfs/Dockerfile"), Path("cloud/modelscope/Dockerfile")],
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
    [Path("cloud/hfs/Dockerfile"), Path("cloud/modelscope/Dockerfile")],
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


def test_root_image_copies_custom_build_hook_before_dependency_install():
    """Hatchling must be able to load the custom hook during the first PEP 517 build."""
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '[tool.hatch.build.hooks.custom]\npath = "hatch_build.py"' in pyproject
    copy_index = dockerfile.index("COPY pyproject.toml README.md LICENSE hatch_build.py ./")
    install_index = dockerfile.index('pip install ".[edition-pro]"')
    assert copy_index < install_index


def test_warp_release_assets_are_verified_against_maintained_table():
    checksums = Path("scripts/warp-checksums.txt").read_text(encoding="utf-8")
    rows = [line for line in checksums.splitlines() if line and not line.startswith("#")]

    assert len(rows) == 6
    assert {tuple(line.split()[:4]) for line in rows} == {
        (tool, version, "linux", arch)
        for tool, version in (
            ("wgcf", "2.2.30"),
            ("wireproxy", "1.1.2"),
            ("usque", "3.0.0"),
        )
        for arch in ("amd64", "arm64")
    }
    for dockerfile in ("Dockerfile", "cloud/hfs/Dockerfile", "cloud/modelscope/Dockerfile"):
        text = Path(dockerfile).read_text(encoding="utf-8")
        assert "warp-checksums.txt" in text
        assert "sha256sum -c -" in text


def test_modelscope_runtime_bin_defaults_to_persistent_data_path():
    text = Path("cloud/modelscope/entrypoint.sh").read_text(encoding="utf-8")
    dockerfile = Path("cloud/modelscope/Dockerfile").read_text(encoding="utf-8")
    runtime = Path("src/souwen/server/warp.py").read_text(encoding="utf-8")

    assert "${WARP_RUNTIME_BIN_DIR:-/home/user/app/data/bin}" in text
    assert "${WARP_RUNTIME_BIN_DIR:-/app/data/bin}" not in text
    assert "WARP_DATA_DIR=/home/user/app/data" in dockerfile
    assert "WARP_RUNTIME_BIN_DIR=/home/user/app/data/bin" in dockerfile
    assert 'os.environ.get("WARP_RUNTIME_BIN_DIR"' in runtime
