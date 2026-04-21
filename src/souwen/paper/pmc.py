"""PubMed Central (PMC) E-utilities 客户端

官方文档: https://www.ncbi.nlm.nih.gov/books/NBK25501/
鉴权: 可选 API Key，无 Key 限流 3 req/s，有 Key 10 req/s
搜索模式: 两步式 esearch → efetch（与 PubMed 相同，db=pmc）
返回: XML (pmc_article_set)

文件用途：PubMed Central 全文开放获取数据库搜索客户端，
与 pubmed.py 使用相同的 NCBI E-utilities 接口，但检索 db=pmc 数据库。

函数/类清单：
    PmcClient（类）
        - 功能：PubMed Central 两步搜索客户端（esearch 获取 PMC ID，efetch 获取详情）
        - 关键属性：api_key (str|None) NCBI API Key, _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（无 Key: 3 req/s, 有 Key: 10 req/s）

    _common_params() -> dict
        - 功能：构建公共请求参数（含 API Key 若已配置）

    _parse_article(article_el: ET.Element) -> PaperResult
        - 功能：将 PMC XML <article> 元素转换为 PaperResult
        - 输入：article_el <article> XML 元素（JATS 格式）
        - 输出：统一的 PaperResult 模型，包含 PMCID、DOI 等字段

    search(query: str, retmax: int, retstart: int) -> SearchResponse
        - 功能：搜索 PMC 文献（两步：esearch → efetch）
        - 输入：query PMC/PubMed 检索式，retmax 返回条数，retstart 起始偏移
        - 输出：SearchResponse 包含搜索结果及分页信息

    fetch(pmc_ids: list[str]) -> list[PaperResult]
        - 功能：根据 PMC ID 列表批量获取文章详情（efetch 阶段）
        - 输入：pmc_ids PMC ID 列表（格式如 "PMC1234567" 或纯数字）
        - 输出：PaperResult 列表

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - defusedxml.ElementTree: 安全 XML 解析
"""

from __future__ import annotations

import logging
import defusedxml.ElementTree as ET
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# 无 Key: 3 req/s, 有 Key: 10 req/s（与 PubMed 相同策略）
_NO_KEY_RPS = 3.0
_KEYED_RPS = 10.0


class PmcClient:
    """PubMed Central (PMC) 全文数据库搜索客户端。

    采用两步搜索模式:
    1. esearch.fcgi (db=pmc) — 获取 PMC ID 列表
    2. efetch.fcgi (db=pmc) — 根据 PMC ID 批量获取 JATS XML 详情
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 PMC 客户端。

        Args:
            api_key: NCBI API Key。未提供时从全局配置读取（复用 pubmed_api_key）。
        """
        cfg = get_config()
        # PMC 与 PubMed 共用同一个 NCBI API Key
        self.api_key: str | None = api_key or cfg.resolve_api_key("pubmed", "pubmed_api_key")

        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="pmc")
        rps = _KEYED_RPS if self.api_key else _NO_KEY_RPS
        self._limiter = TokenBucketLimiter(rate=rps, burst=rps)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> PmcClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _common_params(self) -> dict[str, str]:
        """构建公共请求参数。

        若配置了 API Key，将其加入参数以提升限流阈值。
        """
        params: dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    @staticmethod
    def _text(el: ET.Element | None) -> str:
        """安全提取 XML 元素文本（含子元素文本拼接）。"""
        if el is None:
            return ""
        return "".join(el.itertext()).strip()

    @classmethod
    def _parse_article(cls, article_el: ET.Element) -> PaperResult:
        """将 PMC efetch XML <article> 元素转换为 PaperResult。

        PMC efetch 返回 JATS 格式的 XML（pmc-articleset 根元素，
        每篇文章对应一个 <article> 元素）。

        Args:
            article_el: ``<article>`` XML 元素。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            front = article_el.find("front")
            if front is None:
                raise ParseError("PMC article 缺少 <front> 元素")

            article_meta = front.find("article-meta")
            if article_meta is None:
                raise ParseError("PMC article 缺少 <article-meta> 元素")

            # 提取 PMCID 和 DOI
            pmcid: str = ""
            doi: str | None = None
            pmid: str | None = None
            for id_el in article_meta.findall("article-id"):
                id_type = id_el.get("pub-id-type", "")
                text = (id_el.text or "").strip()
                if id_type == "pmc":
                    pmcid = text
                elif id_type == "doi":
                    doi = text
                elif id_type == "pmid":
                    pmid = text

            # 提取标题（title-group/article-title）
            title_group = article_meta.find("title-group")
            title = ""
            if title_group is not None:
                title = cls._text(title_group.find("article-title"))

            # 提取摘要（abstract/p）
            abstract_parts: list[str] = []
            for abstract_el in article_meta.findall("abstract"):
                for p in abstract_el.iter("p"):
                    text = cls._text(p)
                    if text:
                        abstract_parts.append(text)
            abstract = " ".join(abstract_parts) or None

            # 提取作者列表（contrib-group/contrib[@contrib-type='author']）
            authors: list[Author] = []
            contrib_group = article_meta.find("contrib-group")
            if contrib_group is not None:
                for contrib in contrib_group.findall("contrib"):
                    if contrib.get("contrib-type") != "author":
                        continue
                    name_el = contrib.find("name")
                    if name_el is None:
                        continue
                    surname = cls._text(name_el.find("surname"))
                    given = cls._text(name_el.find("given-names"))
                    full_name = f"{given} {surname}".strip()
                    if full_name:
                        authors.append(Author(name=full_name))

            # 提取发表日期（pub-date[@pub-type='epub'] 或第一个 pub-date）
            year: int | None = None
            pub_date: str | None = None
            for pub_date_el in article_meta.findall("pub-date"):
                y_el = pub_date_el.find("year")
                m_el = pub_date_el.find("month")
                d_el = pub_date_el.find("day")
                if y_el is not None and y_el.text:
                    try:
                        year = int(y_el.text.strip())
                        m_str = (m_el.text or "01").strip().zfill(2) if m_el is not None else "01"
                        d_str = (d_el.text or "01").strip().zfill(2) if d_el is not None else "01"
                        pub_date = f"{year}-{m_str}-{d_str}"
                    except ValueError:
                        pass
                    break  # 取第一个有效的日期即可

            # 提取期刊名（journal-meta/journal-title）
            journal_meta = front.find("journal-meta")
            journal_title: str | None = None
            if journal_meta is not None:
                jtg = journal_meta.find("journal-title-group")
                if jtg is not None:
                    journal_title = cls._text(jtg.find("journal-title")) or None
                else:
                    journal_title = cls._text(journal_meta.find("journal-title")) or None

            # 构建 PMC 文章 URL
            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/" if pmcid else ""
            pdf_url = (
                f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/" if pmcid else None
            )

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.PMC,
                source_url=pmc_url,
                pdf_url=pdf_url,
                citation_count=None,
                journal=journal_title,
                raw={
                    "pmcid": pmcid,
                    "pmid": pmid,
                    "journal": journal_title,
                },
            )
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(f"解析 PMC article 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        retmax: int = 10,
        retstart: int = 0,
    ) -> SearchResponse:
        """搜索 PubMed Central 文献（两步: esearch → efetch）。

        Args:
            query: PMC 检索式，支持 PubMed 高级语法。
            retmax: 返回条数，上限 10000。
            retstart: 起始偏移量。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        # ---- Step 1: esearch 获取 PMC ID 列表 ----
        await self._limiter.acquire()

        search_params = self._common_params()
        search_params.update(
            {
                "db": "pmc",
                "term": query,
                "retmax": str(min(retmax, 10000)),
                "retstart": str(retstart),
                "retmode": "json",
            }
        )

        search_resp = await self._client.get("/esearch.fcgi", params=search_params)
        try:
            search_data: dict[str, Any] = search_resp.json()
        except Exception as exc:
            raise ParseError(f"PMC esearch JSON 解析失败: {exc}") from exc

        result_set = search_data.get("esearchresult", {})
        try:
            total = int(result_set.get("count", 0))
        except (ValueError, TypeError):
            total = 0

        id_list: list[str] = result_set.get("idlist", [])
        page = (retstart // retmax) + 1 if retmax > 0 else 1

        if not id_list:
            return SearchResponse(
                query=query,
                total_results=total,
                page=page,
                per_page=retmax,
                results=[],
                source=SourceType.PMC,
            )

        # ---- Step 2: efetch 获取详情 ----
        results = await self.fetch(id_list)

        return SearchResponse(
            query=query,
            total_results=total,
            page=page,
            per_page=retmax,
            results=results,
            source=SourceType.PMC,
        )

    async def fetch(self, pmc_ids: list[str]) -> list[PaperResult]:
        """根据 PMC ID 列表批量获取文章详情。

        Args:
            pmc_ids: PMC ID 列表（纯数字或带 "PMC" 前缀均可）。

        Returns:
            PaperResult 列表。
        """
        if not pmc_ids:
            return []

        await self._limiter.acquire()

        fetch_params = self._common_params()
        fetch_params.update(
            {
                "db": "pmc",
                "id": ",".join(pmc_ids),
                "retmode": "xml",
            }
        )

        fetch_resp = await self._client.get("/efetch.fcgi", params=fetch_params)
        try:
            root = ET.fromstring(fetch_resp.text)
        except ET.ParseError as exc:
            raise ParseError(f"PMC efetch XML 解析失败: {exc}") from exc

        results: list[PaperResult] = []
        # efetch 根元素可能是 <pmc-articleset> 或 <PubmedArticleSet>
        for article_el in root.findall("article"):
            try:
                results.append(self._parse_article(article_el))
            except ParseError as exc:
                logger.warning("跳过解析失败的 PMC 文章: %s", exc)

        return results
