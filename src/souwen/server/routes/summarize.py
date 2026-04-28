"""LLM 摘要端点 — 搜索 + 摘要一站式接口"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from souwen.server.auth import check_search_auth
from souwen.server.limiter import InMemoryRateLimiter, get_client_ip
from souwen.server.routes._common import logger
from souwen.server.schemas.common import SearchMeta


class SummarizeRequest(BaseModel):
    """POST /api/v1/summarize 请求体"""

    query: str = Field(..., min_length=1, max_length=500, description="搜索查询")
    domain: str = Field("paper", description="搜索域: paper/patent/web")
    sources: list[str] | None = Field(None, description="指定数据源列表")
    per_page: int = Field(10, ge=1, le=50, description="每源结果数")
    mode: Literal["brief", "detailed", "academic"] = Field("brief", description="摘要模式")
    model: str | None = Field(None, description="可选 LLM 模型覆盖")
    max_tokens: int | None = Field(None, ge=100, le=8192, description="可选最大 token 数")
    temperature: float | None = Field(None, ge=0.0, le=2.0, description="可选温度覆盖")
    system_prompt: str | None = Field(None, max_length=2000, description="自定义系统 prompt")


class SummarizeResponse(BaseModel):
    """POST /api/v1/summarize 响应"""

    query: str
    summary: str
    mode: str
    citations: list[dict]
    model: str
    usage: dict
    sources_used: int
    results_used: int
    search_meta: SearchMeta


router = APIRouter()


def _get_summarize_limiter() -> InMemoryRateLimiter:
    from souwen.config import get_config
    cfg = get_config()
    return InMemoryRateLimiter(max_requests=cfg.llm.rate_limit_summarize, window_seconds=60)


_summarize_limiter: InMemoryRateLimiter | None = None


def rate_limit_summarize(request: Request) -> None:
    """Limit summarize calls based on llm.rate_limit_summarize config."""
    global _summarize_limiter  # noqa: PLW0603
    if _summarize_limiter is None:
        _summarize_limiter = _get_summarize_limiter()
    _summarize_limiter.check(get_client_ip(request))


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    dependencies=[Depends(rate_limit_summarize), Depends(check_search_auth)],
)
async def api_summarize(body: SummarizeRequest):
    """搜索 + LLM 摘要 — 一站式智能搜索总结"""

    from souwen.exceptions import ConfigError, SouWenError
    from souwen.facade.search import search
    from souwen.llm.client import LLMError
    from souwen.llm.summarize import summarize

    try:
        responses = await search(
            body.query,
            domain=body.domain,
            sources=body.sources,
            limit=body.per_page,
        )

        if not responses or not any(response.results for response in responses):
            raise HTTPException(status_code=404, detail="No search results found")

        succeeded = [response.source.value for response in responses]
        requested = body.sources or [response.source.value for response in responses]
        meta = SearchMeta(
            requested=requested,
            succeeded=succeeded,
            failed=[source for source in requested if source not in succeeded],
        )

        result = await summarize(
            query=body.query,
            responses=responses,
            mode=body.mode,
            model=body.model,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            system_prompt_override=body.system_prompt,
        )

        return SummarizeResponse(
            query=result.query,
            summary=result.summary,
            mode=result.mode,
            citations=[citation.model_dump() for citation in result.citations],
            model=result.model,
            usage=result.usage.model_dump(),
            sources_used=result.sources_used,
            results_used=result.results_used,
            search_meta=meta,
        )
    except HTTPException:
        raise
    except ConfigError as exc:
        logger.warning("LLM 服务未配置: query=%s error=%s", body.query, exc)
        raise HTTPException(status_code=503, detail="LLM service not configured") from exc
    except LLMError as exc:
        logger.exception("LLM 摘要服务错误: query=%s", body.query)
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}") from exc
    except ValueError as exc:
        logger.warning("LLM 摘要请求无效: query=%s error=%s", body.query, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SouWenError as exc:
        logger.exception("摘要上游失败: query=%s", body.query)
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}") from exc
    except Exception:
        logger.warning("摘要内部错误: query=%s", body.query, exc_info=True)
        raise
