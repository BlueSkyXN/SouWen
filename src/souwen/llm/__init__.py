"""SouWen LLM 集成 — 搜索结果智能摘要

为搜索结果提供 LLM 驱动的智能总结能力，支持 OpenAI-compatible API。

公开 API::

    from souwen.llm import summarize          # 核心摘要函数
    from souwen.llm.client import llm_complete # 底层 LLM 调用
    from souwen.llm.models import SummaryResult, LLMResponse
"""

from souwen.llm.summarize import summarize

__all__ = ["summarize"]
