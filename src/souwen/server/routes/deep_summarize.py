"""Deep Search 端点 — 搜索 + 抓取 + 两轮 LLM 综合"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from souwen.server.auth import check_search_auth
from souwen.server.limiter import InMemoryRateLimiter, get_client_ip
from souwen.server.routes._common import logger, require_llm_enabled


class DeepSummarizeRequest(BaseModel):
    """POST /api/v1/deep-summarize 请求体"""

    query: str = Field(..., min_length=1, max_length=500, description="搜索查询")
    domain: str = Field("paper", description="搜索域: paper/patent/web")
    sources: list[str] | None = Field(None, description="指定数据源列表")
    per_page: int = Field(10, ge=1, le=50, description="每源搜索结果数")
    max_fetch: int = Field(5, ge=1, le=10, description="最多抓取页面数")
    fetch_provider: str = Field("builtin", description="内容抓取提供者")
    fetch_timeout: float = Field(30.0, ge=5.0, le=120.0, description="每页抓取超时")
    mode: Literal["brief", "detailed", "academic"] | None = Field(
        None, description="摘要模式（默认使用配置 llm.default_mode）"
    )
    model: str | None = Field(None, description="可选 LLM 模型覆盖")
    max_tokens: int | None = Field(None, ge=100, le=8192, description="可选最大 token 数")
    temperature: float | None = Field(None, ge=0.0, le=2.0, description="可选温度覆盖")
    system_prompt: str | None = Field(None, max_length=2000, description="自定义综合 prompt")


class DeepFetchStatsResponse(BaseModel):
    """Deep Search 抓取统计"""

    fetched_urls: list[str] = Field(default_factory=list)
    failed_urls: list[str] = Field(default_factory=list)
    used_urls: list[str] = Field(default_factory=list)
    skipped_urls: list[str] = Field(default_factory=list)


class DeepSummarizeResponse(BaseModel):
    """POST /api/v1/deep-summarize 响应"""

    query: str
    summary: str
    mode: str
    citations: list[dict]
    model: str
    usage: dict
    fetch_stats: DeepFetchStatsResponse
    sources_used: int
    results_used: int
    pages_synthesized: int


router = APIRouter()

# Deep search rate limit — configurable via llm.rate_limit_deep
_deep_limiter: InMemoryRateLimiter | None = None


def _get_deep_limiter() -> InMemoryRateLimiter:
    from souwen.config import get_config

    cfg = get_config()
    return InMemoryRateLimiter(max_requests=cfg.llm.rate_limit_deep, window_seconds=60)


def rate_limit_deep_summarize(request: Request) -> None:
    """Rate limit for deep search based on llm.rate_limit_deep config."""
    global _deep_limiter  # noqa: PLW0603
    if _deep_limiter is None:
        _deep_limiter = _get_deep_limiter()
    _deep_limiter.check(get_client_ip(request))


@router.post(
    "/deep-summarize",
    response_model=DeepSummarizeResponse,
    dependencies=[
        Depends(rate_limit_deep_summarize),
        Depends(require_llm_enabled),
        Depends(check_search_auth),
    ],
)
async def api_deep_summarize(body: DeepSummarizeRequest):
    """Deep Search — 搜索 + 抓取 + 两轮 LLM 深度综合"""

    from souwen.config import get_config
    from souwen.exceptions import ConfigError, SouWenError
    from souwen.llm.client import LLMError
    from souwen.llm.deep_search import deep_summarize

    cfg = get_config()
    effective_mode = body.mode or cfg.llm.default_mode
    effective_system_prompt = body.system_prompt or cfg.llm.system_prompt

    try:
        result = await deep_summarize(
            query=body.query,
            domain=body.domain,
            sources=body.sources,
            per_page=body.per_page,
            max_fetch=body.max_fetch,
            fetch_provider=body.fetch_provider,
            fetch_timeout=body.fetch_timeout,
            mode=effective_mode,
            model=body.model,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            system_prompt_override=effective_system_prompt,
        )

        return DeepSummarizeResponse(
            query=result.query,
            summary=result.summary,
            mode=result.mode,
            citations=[c.model_dump() for c in result.citations],
            model=result.model,
            usage=result.usage.model_dump(),
            fetch_stats=DeepFetchStatsResponse(
                fetched_urls=result.fetch_stats.fetched_urls,
                failed_urls=result.fetch_stats.failed_urls,
                used_urls=result.fetch_stats.used_urls,
                skipped_urls=result.fetch_stats.skipped_urls,
            ),
            sources_used=result.sources_used,
            results_used=result.results_used,
            pages_synthesized=result.pages_synthesized,
        )
    except ConfigError as exc:
        logger.warning("LLM 服务未配置: query=%s error=%s", body.query, exc)
        raise HTTPException(status_code=503, detail="LLM service not configured") from exc
    except LLMError as exc:
        logger.exception("Deep Search LLM 错误: query=%s", body.query)
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}") from exc
    except ValueError as exc:
        logger.warning("Deep Search 请求无效: query=%s error=%s", body.query, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SouWenError as exc:
        logger.exception("Deep Search 上游失败: query=%s", body.query)
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc
    except Exception:
        logger.warning("Deep Search 内部错误: query=%s", body.query, exc_info=True)
        raise
