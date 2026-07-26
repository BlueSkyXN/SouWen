from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "dockerfile",
    [
        Path("Dockerfile"),
        Path("cloud/hfs/Dockerfile"),
        Path("cloud/modelscope/Dockerfile"),
    ],
)
def test_dockerfiles_exclude_removed_pdf_capture_stack(dockerfile: Path):
    text = dockerfile.read_text(encoding="utf-8")

    for removed in ("WITH_WEB2PDF", "WEB2PDF_PACKAGE", "superweb2pdf", "pymupdf4llm"):
        assert removed not in text


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
    install_index = dockerfile.index('pip install ".[server,tls,web,robots,scraper]"')
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


def test_hfs_target_image_runs_supervisor_with_internal_browser_worker():
    dockerfile = Path("cloud/hfs/Dockerfile").read_text(encoding="utf-8")
    entrypoint = Path("cloud/hfs/entrypoint.sh").read_text(encoding="utf-8")

    assert 'pip install ".[server,tls,web,robots,scraper]" "playwright>=1.40"' in dockerfile
    assert "RUN playwright install chromium" in dockerfile
    assert dockerfile.count("EXPOSE 49265") == 1
    assert "EXPOSE 49266" not in dockerfile
    assert "exec python /app/deploy/process/supervisor.py" in entrypoint
    assert "exec uvicorn" not in entrypoint


def test_container_healthchecks_use_canonical_healthz_probe():
    for dockerfile in ("Dockerfile", "cloud/hfs/Dockerfile", "cloud/modelscope/Dockerfile"):
        assert "/healthz" in Path(dockerfile).read_text(encoding="utf-8")
