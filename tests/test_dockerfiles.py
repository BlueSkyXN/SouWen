from __future__ import annotations

from pathlib import Path

import pytest

SUPERWEB2PDF_ARCHIVE = (
    "https://github.com/BlueSkyXN/SuperWeb2PDF/archive/d1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip"
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
    assert 'pip install ".[server,tls]" "playwright>=1.40" "${WEB2PDF_PACKAGE}"' in text
