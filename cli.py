#!/usr/bin/env python3
"""SouWen CLI 入口脚本 — 用于源码运行和打包构建

文件用途：
    根级脚本入口，支持源码直接运行和打包为单文件可执行程序。
    动态配置 Python 路径以支持源码运行模式，最后代理调用 souwen.cli 主应用。

支持的运行模式：

    源码运行（开发调试）:
        python cli.py --help
        python cli.py search paper "transformer attention"
        python cli.py serve --port 8080

    打包构建（生产部署）:
        nuitka --onefile --standalone cli.py
        pyinstaller --onefile --clean cli.py

核心函数/类：
    无 — 本文件仅充当入口代理，所有功能实现于 souwen.cli 模块

模块依赖：
    - souwen.cli: 实际 CLI 应用程序入口
    - sys, pathlib: 标准库，用于路径操作和 sys.path 管理
"""

from __future__ import annotations

import sys
from pathlib import Path

# 源码运行时将 src/ 加入 Python 路径
# 这使得开发者可以直接运行 python cli.py，而无需事先安装包
_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# 延迟导入 app，确保 sys.path 已正确配置
from souwen.cli import app  # noqa: E402

if __name__ == "__main__":
    # 执行 CLI 应用程序
    app()
