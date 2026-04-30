"""Fetch + LLM 摘要端点 — URL 页面内容摘要"""

from __future__ import annotations

import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from souwen.server.auth import check_search_auth
from souwen.server.limiter import InMemoryRateLimiter, get_client_ip
from souwen.server.routes._common import logger, require_llm_enabled


class FetchSummarizeRequest(BaseModel):
    """POST /api/v1/fetch/summarize 请求体"""

    urls: list[str] = Field(..., min_length=1, max_length=10, description="待抓取并摘要的 URL 列表")
    provider: str = Field("builtin", description="Fetch 提供者")
    timeout: float = Field(30.0, ge=5.0, le=120.0, description="每 URL 超时秒数")
    mode: Literal["brief", "detailed", "academic"] | None = Field(
        None, description="摘要模式（默认使用配置 llm.default_mode）"
    )
    model: str | None = Field(None, description="可选 LLM 模型覆盖")
    max_tokens: int | None = Field(None, ge=100, le=8192, description="可选最大 token 数")
    temperature: float | None = Field(None, ge=0.0, le=2.0, description="可选温度覆盖")
    system_prompt: str | None = Field(None, max_length=2000, description="自定义系统 prompt")


class FetchSummarizeItemResponse(BaseModel):
    """单个 URL 的摘要结果"""

    url: str
    final_url: str = ""
    title: str = ""
    summary: str = ""
    word_count: int = 0
    content_truncated: bool = False
    error: str | None = None
    provider: str = ""


class FetchSummarizeResponse(BaseModel):
    """POST /api/v1/fetch/summarize 响应"""

    items: list[FetchSummarizeItemResponse]
    mode: str
    model: str
    usage: dict
    total_urls: int
    total_ok: int
    total_failed: int


router = APIRouter()

_fetch_summarize_limiter: InMemoryRateLimiter | None = None
_fetch_summarize_lock = threading.Lock()


def _get_fetch_summarize_limiter() -> InMemoryRateLimiter:
    from souwen.config import get_config

    cfg = get_config()
    return InMemoryRateLimiter(max_requests=cfg.llm.rate_limit_fetch, window_seconds=60)


def rate_limit_fetch_summarize(request: Request) -> None:
    """Rate limit for fetch+summarize based on llm.rate_limit_fetch config."""
    from souwen.config import get_config

    global _fetch_summarize_limiter  # noqa: PLW0603
    max_requests = get_config().llm.rate_limit_fetch
    if (
        _fetch_summarize_limiter is None
        or _fetch_summarize_limiter.max_requests != max_requests
        or _fetch_summarize_limiter.window_seconds != 60
    ):
        with _fetch_summarize_lock:
            if (
                _fetch_summarize_limiter is None
                or _fetch_summarize_limiter.max_requests != max_requests
                or _fetch_summarize_limiter.window_seconds != 60
            ):
                _fetch_summarize_limiter = InMemoryRateLimiter(
                    max_requests=max_requests,
                    window_seconds=60,
                )
    _fetch_summarize_limiter.check(get_client_ip(request))


@router.post(
    "/fetch/summarize",
    response_model=FetchSummarizeResponse,
    dependencies=[
        Depends(require_llm_enabled),
        Depends(rate_limit_fetch_summarize),
        Depends(check_search_auth),
    ],
)
async def api_fetch_summarize(body: FetchSummarizeRequest):
    """抓取 URL 页面内容并用 LLM 逐页生成摘要"""

    from souwen.config import get_config
    from souwen.exceptions import ConfigError, SouWenError
    from souwen.llm.client import LLMError
    from souwen.llm.fetch_summarize import summarize_pages

    cfg = get_config()
    effective_mode = body.mode or cfg.llm.default_mode
    effective_system_prompt = body.system_prompt or cfg.llm.system_prompt

    try:
        result = await summarize_pages(
            urls=body.urls,
            provider=body.provider,
            timeout=body.timeout,
            mode=effective_mode,
            model=body.model,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            system_prompt_override=effective_system_prompt,
        )

        return FetchSummarizeResponse(
            items=[
                FetchSummarizeItemResponse(
                    url=item.url,
                    final_url=item.final_url,
                    title=item.title,
                    summary=item.summary,
                    word_count=item.word_count,
                    content_truncated=item.content_truncated,
                    error=item.error,
                    provider=item.provider,
                )
                for item in result.items
            ],
            mode=result.mode,
            model=result.model,
            usage=result.usage.model_dump(),
            total_urls=result.total_urls,
            total_ok=result.total_ok,
            total_failed=result.total_failed,
        )
    except ConfigError as exc:
        logger.warning("LLM 服务未配置: %s", exc)
        raise HTTPException(status_code=503, detail="LLM service not configured") from exc
    except LLMError as exc:
        logger.exception("Fetch+Summarize LLM 错误")
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}") from exc
    except ValueError as exc:
        logger.warning("Fetch+Summarize 请求无效: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SouWenError as exc:
        logger.exception("Fetch+Summarize 上游失败")
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc
    except Exception:
        logger.warning("Fetch+Summarize 内部错误", exc_info=True)
        raise
