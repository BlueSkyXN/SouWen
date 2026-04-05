#!/usr/bin/env python3
"""SouWen CLI 入口脚本 — 用于源码运行和打包构建

源码运行:
    python cli.py --help
    python cli.py search paper "transformer attention"
    python cli.py serve --port 8080

打包构建:
    nuitka --onefile --standalone cli.py
    pyinstaller --onefile --clean cli.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# 源码运行时将 src/ 加入 Python 路径
_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from souwen.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
