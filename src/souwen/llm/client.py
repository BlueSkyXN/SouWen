"""SouWen LLM 客户端 — OpenAI-compatible API

基于 httpx 的轻量级 LLM 客户端，支持所有 OpenAI-compatible 服务。
不依赖 openai SDK，复用 SouWen 已有的 httpx 基础设施。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, RateLimitError, SouWenError
from souwen.core.retry import make_retry
from souwen.llm.models import LLMMessage, LLMResponse, LLMUsage

logger = logging.getLogger("souwen.llm")


class LLMError(SouWenError):
    """LLM 调用失败

    Attributes:
        status_code: HTTP 状态码（如有）
        body: 错误响应体（截断）
    """

    def __init__(self, message: str, *, status_code: int | None = None, body: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class _LLMRetriableError(LLMError):
    """LLM 可重试错误（内部使用，不暴露给外部）"""

    pass


# LLM-specific retry: retry on 429 and 5xx, NOT on other 4xx
_LLM_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    RateLimitError,
    _LLMRetriableError,
)

_llm_retry = make_retry(
    attempts=3,
    min_wait=2.0,
    max_wait=15.0,
    multiplier=1.5,
    retry_on=_LLM_RETRY_EXCEPTIONS,
)


def _ensure_llm_enabled() -> None:
    """检查 LLM 是否已启用且配置有效"""
    cfg = get_config().llm
    if not cfg.enabled:
        raise ConfigError("llm.enabled", "LLM")
    if not cfg.get_api_key():
        raise ConfigError("llm.api_key", "LLM")


@_llm_retry
async def llm_complete(
    messages: list[LLMMessage],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> LLMResponse:
    """调用 LLM 生成完成。

    参数从 config.llm 读取默认值，可通过参数覆盖。

    Raises:
        LLMError: LLM 调用失败
        ConfigError: LLM 未启用或缺少 API Key
    """
    _ensure_llm_enabled()
    cfg = get_config()
    llm_cfg = cfg.llm

    api_key = llm_cfg.get_api_key()
    base_url = llm_cfg.base_url.rstrip("/")
    url = f"{base_url}/chat/completions"

    payload: dict[str, Any] = {
        "model": model or llm_cfg.model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens if max_tokens is not None else llm_cfg.max_tokens,
        "temperature": temperature if temperature is not None else llm_cfg.temperature,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    proxy = cfg.get_proxy()
    client_kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(llm_cfg.timeout, connect=10.0),
        "follow_redirects": True,
    }
    if proxy:
        client_kwargs["proxy"] = proxy

    async with httpx.AsyncClient(**client_kwargs) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise
        except httpx.ConnectError:
            raise
        except httpx.HTTPError as exc:
            raise LLMError(f"HTTP 请求失败: {exc}", status_code=None) from exc

    if resp.status_code == 429:
        retry_after = None
        retry_after_header = resp.headers.get("retry-after")
        if retry_after_header:
            try:
                retry_after = float(retry_after_header)
            except ValueError:
                pass
        raise RateLimitError("LLM API 限流 (429)", retry_after=retry_after)

    if resp.status_code >= 500:
        body = resp.text[:500]
        raise _LLMRetriableError(
            f"LLM 上游错误: HTTP {resp.status_code}",
            status_code=resp.status_code,
            body=body,
        )

    if resp.status_code != 200:
        body = resp.text[:500]
        raise LLMError(
            f"LLM API 错误: HTTP {resp.status_code} - {body}",
            status_code=resp.status_code,
            body=body,
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise LLMError(f"LLM 响应解析失败: {exc}") from exc

    choices = data.get("choices", [])
    if not choices:
        raise LLMError("LLM 返回空 choices")

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "")
    finish_reason = choice.get("finish_reason", "")

    usage_data = data.get("usage", {})
    usage = LLMUsage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
    )

    return LLMResponse(
        content=content,
        model=data.get("model", payload["model"]),
        usage=usage,
        finish_reason=finish_reason,
    )
