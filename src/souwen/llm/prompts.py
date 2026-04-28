"""SouWen LLM 提示词模板 + 搜索结果格式化

提供三种摘要模式的系统 prompt 和搜索结果到 LLM 输入的格式化函数。
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.llm.models import SummaryCitation
from souwen.models import (
    PaperResult,
    PatentResult,
    SearchResponse,
    WebSearchResult,
)

logger = logging.getLogger("souwen.llm")


# ── 系统 Prompt ────────────────────────────────────────────

SYSTEM_PROMPT_BASE = """\
You are a research assistant that synthesizes search results into clear, well-organized summaries.

Rules:
- Cite sources using [N] notation (e.g., [1], [2]) based on the reference IDs provided.
- Every factual claim must include at least one citation.
- Use the language matching the user's query (Chinese query → Chinese response, English query → English response).
- Do NOT fabricate information not present in the provided sources.
- Do NOT include URLs in the text body; they are already linked via citation IDs.
"""

SYSTEM_PROMPT_BRIEF = (
    SYSTEM_PROMPT_BASE
    + """
Mode: Brief summary.
- Provide a concise overview in 3-5 paragraphs.
- Focus on the most important findings and key takeaways.
- Keep the total length under 500 words.
"""
)

SYSTEM_PROMPT_DETAILED = (
    SYSTEM_PROMPT_BASE
    + """
Mode: Detailed summary.
- Provide a comprehensive summary organized by themes or subtopics.
- Use headings (##) to structure the response.
- Include methodology details, key findings, and implications.
- Compare different perspectives from the sources when available.
- Aim for 800-1500 words.
"""
)

SYSTEM_PROMPT_ACADEMIC = (
    SYSTEM_PROMPT_BASE
    + """
Mode: Academic summary.
- Write in formal academic tone suitable for a literature review.
- Structure: Background → Key Findings → Methodology Patterns → Gaps & Future Directions.
- Use precise terminology and nuanced analysis.
- Cross-reference sources to identify consensus and disagreements.
- Aim for 1000-2000 words.
"""
)

SYSTEM_PROMPTS: dict[str, str] = {
    "brief": SYSTEM_PROMPT_BRIEF,
    "detailed": SYSTEM_PROMPT_DETAILED,
    "academic": SYSTEM_PROMPT_ACADEMIC,
}


def get_system_prompt(mode: str, override: str | None = None) -> str:
    """获取系统 prompt

    Args:
        mode: 摘要模式 (brief/detailed/academic)
        override: 用户自定义 prompt（覆盖内置）

    Returns:
        系统 prompt 文本
    """
    if override:
        logger.info("使用自定义系统 prompt（覆盖 %s 模式）", mode)
        return override
    return SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPT_BRIEF)


# ── 搜索结果格式化 ──────────────────────────────────────────


def _format_paper(idx: int, paper: PaperResult) -> str:
    """格式化单篇论文为 LLM 输入"""
    parts = [f"[{idx}]"]
    parts.append(f"Title: {paper.title}")
    if paper.authors:
        author_names = [author.name for author in paper.authors[:3]]
        if len(paper.authors) > 3:
            author_names.append("et al.")
        parts.append(f"Authors: {', '.join(author_names)}")
    if paper.venue:
        parts.append(f"Venue: {paper.venue}")
    if paper.year:
        parts.append(f"Year: {paper.year}")
    if paper.tldr:
        parts.append(f"TLDR: {paper.tldr}")
    elif paper.abstract:
        abstract = paper.abstract[:800]
        if len(paper.abstract) > 800:
            abstract += "..."
        parts.append(f"Abstract: {abstract}")
    if paper.source_url:
        parts.append(f"URL: {paper.source_url}")
    return " | ".join(parts)


def _format_patent(idx: int, patent: PatentResult) -> str:
    """格式化单件专利为 LLM 输入"""
    parts = [f"[{idx}]"]
    parts.append(f"Title: {patent.title}")
    parts.append(f"ID: {patent.patent_id}")
    if patent.applicants:
        names = [applicant.name for applicant in patent.applicants[:3]]
        parts.append(f"Applicants: {', '.join(names)}")
    if patent.publication_date:
        parts.append(f"Date: {patent.publication_date}")
    if patent.abstract:
        abstract = patent.abstract[:800]
        if len(patent.abstract) > 800:
            abstract += "..."
        parts.append(f"Abstract: {abstract}")
    if patent.source_url:
        parts.append(f"URL: {patent.source_url}")
    return " | ".join(parts)


def _format_web(idx: int, web: WebSearchResult) -> str:
    """格式化单条网页结果为 LLM 输入"""
    parts = [f"[{idx}]"]
    parts.append(f"Title: {web.title}")
    if web.snippet:
        snippet = web.snippet[:500]
        if len(web.snippet) > 500:
            snippet += "..."
        parts.append(f"Snippet: {snippet}")
    parts.append(f"URL: {web.url}")
    return " | ".join(parts)


def format_results_for_llm(
    responses: list[SearchResponse],
    *,
    max_results: int = 20,
) -> tuple[str, list[SummaryCitation]]:
    """将搜索结果格式化为 LLM 输入文本 + 引用列表

    Args:
        responses: 搜索响应列表（多个数据源）
        max_results: 最大结果条数（超出则截断低优先级结果）

    Returns:
        (formatted_text, citations) — LLM 输入文本和对应的引用列表
    """
    seen_keys: set[str] = set()
    items: list[tuple[str, Any]] = []

    for response in responses:
        for result in response.results:
            key = _dedup_key(result)
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)
            items.append((response.source.value, result))

    items = items[:max_results]

    lines: list[str] = []
    citations: list[SummaryCitation] = []

    for idx_0, (source_name, result) in enumerate(items):
        idx = idx_0 + 1

        if isinstance(result, PaperResult):
            lines.append(_format_paper(idx, result))
            citations.append(
                SummaryCitation(
                    id=idx,
                    title=result.title,
                    url=result.source_url,
                    source=source_name,
                )
            )
        elif isinstance(result, PatentResult):
            lines.append(_format_patent(idx, result))
            citations.append(
                SummaryCitation(
                    id=idx,
                    title=result.title,
                    url=result.source_url,
                    source=source_name,
                )
            )
        elif isinstance(result, WebSearchResult):
            lines.append(_format_web(idx, result))
            citations.append(
                SummaryCitation(
                    id=idx,
                    title=result.title,
                    url=result.url,
                    source=source_name,
                )
            )

    text = "\n\n".join(lines)
    return text, citations


def _dedup_key(result: Any) -> str:
    """生成去重 key — 按 DOI/URL/patent_id 去重"""
    if isinstance(result, PaperResult):
        if result.doi:
            return f"doi:{result.doi.lower()}"
        return f"paper:{result.source_url}"
    if isinstance(result, PatentResult):
        return f"patent:{result.patent_id}"
    if isinstance(result, WebSearchResult):
        return f"web:{result.url}"
    return ""

# ── Fetch 页面摘要 prompt ─────────────────────────────────

_PAGE_SUMMARY_PROMPTS: dict[str, str] = {
    "brief": (
        "You are a web content summarizer. Given the full text of a web page, "
        "produce a concise summary capturing the main points. "
        "Write 2-4 sentences. Use clear, objective language. "
        "If the content is a research paper, highlight the key findings. "
        "If it's a news article, capture the essential facts."
    ),
    "detailed": (
        "You are a web content analyst. Given the full text of a web page, "
        "produce a detailed summary covering all significant points. "
        "Structure with key sections if the content is long. "
        "Include important data, conclusions, and context. "
        "Aim for 1-3 paragraphs depending on content length."
    ),
    "academic": (
        "You are an academic content analyst. Given the full text of a web page, "
        "produce a scholarly summary following academic conventions. "
        "If the content is a research paper, cover: objective, methodology, "
        "key results, and conclusions. Use precise, formal language. "
        "Note limitations or caveats mentioned in the text."
    ),
}


def get_page_summary_prompt(mode: str = "brief", override: str | None = None) -> str:
    """Return system prompt for page content summarization."""
    if override:
        return override
    return _PAGE_SUMMARY_PROMPTS.get(mode, _PAGE_SUMMARY_PROMPTS["brief"])


# ── Deep Search prompt（两轮流水线）──────────────────────────

# Pass 1: Extract key information from each fetched page
DEEP_EXTRACT_PROMPT = (
    "You are an information extraction assistant. Given the full text content "
    "of a web page and a user query, extract the most relevant information "
    "that helps answer the query. Focus on:\n"
    "- Key facts, data points, and findings relevant to the query\n"
    "- Important conclusions or claims with supporting evidence\n"
    "- Definitions, explanations, or context that aids understanding\n\n"
    "Be concise but thorough. Preserve specific numbers, dates, and proper nouns. "
    "Output a structured extraction, not a full summary. "
    "If the page content is not relevant to the query, say so briefly."
)

# Pass 2: Synthesize extractions from multiple pages
_DEEP_SYNTHESIS_PROMPTS: dict[str, str] = {
    "brief": (
        "You are a research synthesis assistant. You have extracted information "
        "from multiple web pages related to a user query. Synthesize these extractions "
        "into a concise, well-organized answer.\n\n"
        "Rules:\n"
        "- Cite sources using [1], [2], etc. notation\n"
        "- Prioritize accuracy — only state what the sources support\n"
        "- Resolve contradictions between sources by noting the disagreement\n"
        "- Write 3-5 sentences for a brief overview\n"
        "- Use clear, objective language"
    ),
    "detailed": (
        "You are a research synthesis assistant. You have extracted information "
        "from multiple web pages related to a user query. Synthesize these extractions "
        "into a comprehensive, well-structured answer.\n\n"
        "Rules:\n"
        "- Cite sources using [1], [2], etc. notation\n"
        "- Organize information thematically, not by source\n"
        "- Include supporting evidence, data, and examples from sources\n"
        "- Resolve contradictions between sources by noting the disagreement\n"
        "- Write 2-5 paragraphs with clear structure\n"
        "- Identify gaps where sources don't provide enough information"
    ),
    "academic": (
        "You are an academic research synthesis assistant. You have extracted information "
        "from multiple sources related to a research query. Synthesize these into a "
        "scholarly analysis suitable for academic use.\n\n"
        "Rules:\n"
        "- Cite all sources using [1], [2], etc. notation\n"
        "- Follow academic writing conventions with formal language\n"
        "- Organize by themes/aspects, comparing and contrasting sources\n"
        "- Assess the strength of evidence and note methodological considerations\n"
        "- Identify consensus, disagreements, and research gaps\n"
        "- Write 3-6 paragraphs with a clear analytical structure"
    ),
}


def get_deep_extract_prompt() -> str:
    """Return the extraction prompt for deep search pass 1."""
    return DEEP_EXTRACT_PROMPT


def get_deep_synthesis_prompt(mode: str = "brief", override: str | None = None) -> str:
    """Return synthesis prompt for deep search pass 2."""
    if override:
        return override
    return _DEEP_SYNTHESIS_PROMPTS.get(mode, _DEEP_SYNTHESIS_PROMPTS["brief"])


def format_extractions_for_synthesis(
    extractions: list[tuple[int, str, str, str]],
) -> str:
    """Format page extractions for the synthesis pass.

    Args:
        extractions: list of (citation_id, title, url, extracted_text) tuples.

    Returns:
        Formatted string for the synthesis LLM prompt.
    """
    if not extractions:
        return ""
    parts: list[str] = []
    for cid, title, url, text in extractions:
        header = f"[{cid}] {title}" if title else f"[{cid}] {url}"
        parts.append(f"{header}\n{text}")
    return "\n\n---\n\n".join(parts)

