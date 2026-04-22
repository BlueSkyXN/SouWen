"""doctor 命令：检查所有数据源可用性"""

from __future__ import annotations

from souwen.cli import app
from souwen.cli._common import console


@app.command("doctor")
def doctor_cmd() -> None:
    """检查所有数据源可用性"""
    from souwen.doctor import check_all, format_report

    results = check_all()
    console.print(format_report(results))
