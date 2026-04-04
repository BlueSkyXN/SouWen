"""SouWen FastAPI 应用入口"""

from __future__ import annotations

from fastapi import FastAPI

from souwen import __version__
from souwen.server.routes import router

app = FastAPI(
    title="SouWen API",
    description="面向 AI Agent 的学术论文 + 专利 + 网页统一搜索 API",
    version=__version__,
)
app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__}
