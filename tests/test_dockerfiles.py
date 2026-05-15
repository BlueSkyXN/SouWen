from __future__ import annotations

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
def test_web2pdf_package_build_arg_requires_explicit_install_source(dockerfile: Path):
    text = dockerfile.read_text(encoding="utf-8")

    assert "ARG WEB2PDF_PACKAGE=" in text
    assert "ARG WEB2PDF_PACKAGE=superweb2pdf" not in text
    assert (
        "WITH_WEB2PDF=1 requires --build-arg WEB2PDF_PACKAGE=<installable package/url/path>"
        in text
    )
    assert 'pip install "${WEB2PDF_PACKAGE}"' in text
