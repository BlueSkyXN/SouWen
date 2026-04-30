"""SouWen LLM 客户端 — 多协议 LLM API 调度器

支持 OpenAI Chat Completions、OpenAI Responses、Anthropic Claude Messages 三种协议。
通过 config.llm.protocol 配置切换，每种协议由 providers/ 下独立模块实现。
"""

from __future__ import annotations

import logging
from typing import Callable, Coroutine

import httpx

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, RateLimitError, SouWenError
from souwen.core.retry import make_retry
from souwen.llm.models import LLMMessage, LLMResponse

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


# ── 重试策略 ─────────────────────────────────────────────────

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


# ── 协议注册表 ───────────────────────────────────────────────

_ProviderFn = Callable[..., Coroutine[None, None, LLMResponse]]

_PROVIDERS: dict[str, tuple[str, str]] = {
    "openai_chat": ("souwen.llm.providers.openai_chat", "complete"),
    "openai_responses": ("souwen.llm.providers.openai_responses", "complete"),
    "anthropic_messages": ("souwen.llm.providers.anthropic_messages", "complete"),
}


def _get_provider(protocol: str) -> _ProviderFn:
    """按 protocol 名称加载对应的 provider 函数"""
    spec = _PROVIDERS.get(protocol)
    if spec is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise ConfigError(
            f"llm.protocol={protocol!r}",
            f"LLM (supported: {supported})",
        )
    module_path, fn_name = spec
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, fn_name)


# ── 公开 API ─────────────────────────────────────────────────


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
    """调用 LLM 生成完成 — 自动按 protocol 配置分发到对应 provider。

    参数从 config.llm 读取默认值，可通过参数覆盖。

    Raises:
        LLMError: LLM 调用失败
        ConfigError: LLM 未启用、缺少 API Key 或 protocol 不支持
    """
    _ensure_llm_enabled()
    cfg = get_config()
    llm_cfg = cfg.llm

    # 分离系统 prompt：第一条 role=system 的消息提取出来
    system: str | None = None
    user_messages: list[LLMMessage] = []
    for msg in messages:
        if msg.role == "system" and system is None:
            system = msg.content
        else:
            user_messages.append(msg)

    provider_fn = _get_provider(llm_cfg.protocol)

    # 为 Anthropic 构建 extra_headers（使用配置的 version 而非硬编码）
    extra_headers: dict[str, str] | None = None
    if llm_cfg.protocol == "anthropic_messages":
        extra_headers = {"anthropic-version": llm_cfg.anthropic_version}

    logger.info(
        "LLM dispatch: protocol=%s model=%s",
        llm_cfg.protocol,
        model or llm_cfg.model,
    )

    return await provider_fn(
        system,
        user_messages,
        api_key=llm_cfg.get_api_key(),
        base_url=llm_cfg.base_url.rstrip("/"),
        model=model or llm_cfg.model,
        max_tokens=max_tokens if max_tokens is not None else llm_cfg.max_tokens,
        temperature=temperature if temperature is not None else llm_cfg.temperature,
        timeout=llm_cfg.timeout,
        proxy=cfg.get_proxy(),
        extra_headers=extra_headers,
    )
