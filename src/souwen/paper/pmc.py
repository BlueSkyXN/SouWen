"""PubMed Central (PMC) / NCBI E-utilities 客户端

官方文档: https://www.ncbi.nlm.nih.gov/books/NBK25501/
鉴权: 可选 API Key（复用 NCBI/PubMed Key），无 Key 限流 3 req/s，有 Key 10 req/s
搜索模式: 两步式 esearch → efetch（efetch 必须，esummary 缺失摘要）
返回: JATS XML

文件用途：PubMed Central 全文开放获取文献搜索客户端，针对 NCBI E-utilities
``db=pmc`` 子集，使用 efetch 解析 JATS XML 提取标题、作者、摘要、DOI、期刊
等完整字段，并提供 PMC 全文页/PDF 链接。

函数/类清单：
    PmcClient（类）
        - 功能：PMC 两步搜索客户端（esearch 获取 PMCID，efetch 解析 JATS XML）
        - 关键属性：api_key (str|None) NCBI API Key（与 PubMed 共享）,
                   _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（无 Key 3 req/s，有 Key 10 req/s）

    _common_params() -> dict
        - 功能：构建公共请求参数（包含 api_key 若已配置）

    _parse_article(article_el: ET.Element) -> PaperResult
        - 功能：将 JATS ``<article>`` XML 元素转换为 PaperResult
        - 输入：article_el JATS ``<article>`` 元素
        - 输出：统一的 PaperResult 模型，包含 PMCID、期刊、PDF 链接等

    search(query: str, retmax: int = 10, retstart: int = 0) -> SearchResponse
        - 功能：搜索 PMC 文献（两步：esearch → efetch）
        - 输入：query 检索式, retmax 返回条数（上限 10000）, retstart 起始偏移
        - 输出：SearchResponse 包含搜索结果及分页信息

    fetch(pmcids: list[str]) -> list[PaperResult]
        - 功能：根据 PMCID 列表批量获取论文 JATS XML 详情
        - 输入：pmcids PMC ID 列表（不带 PMC 前缀的纯数字）
        - 输出：PaperResult 列表，解析失败的条目跳过并记录日志

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - defusedxml.ElementTree: 安全 XML 解析（防止 XXE 攻击）
"""

from __future__ import annotations

import logging
from typing import Any

import defusedxml.ElementTree as ET

from souwen.config import get_config
from souwen.core.exceptions import ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# 无 Key: 3 req/s, 有 Key: 10 req/s
_NO_KEY_RPS = 3.0
_KEYED_RPS = 10.0

# PMC 数据源类型，待补充至 SourceType 枚举后即可替换为 SourceType.PMC
# SourceType.PMC 已在 models.py 中注册


class PmcClient:
    """PubMed Central (PMC) 全文开放获取文献搜索客户端。

    采用两步搜索模式:
    1. esearch.fcgi (db=pmc) — 获取 PMCID 列表
    2. efetch.fcgi  (db=pmc) — 根据 PMCID 批量获取 JATS XML 详情

    与 PubMed 区别:
        - PubMed (db=pubmed) 仅返回引文+摘要，PMC (db=pmc) 提供 JATS 全文 XML
        - PMC 文献必然有开放获取的全文链接
        - efetch 必须用于 PMC（esummary 经常缺失摘要等关键字段）
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 PMC 客户端。

        Args:
            api_key: NCBI API Key（与 PubMed 共享）。未提供时从全局配置读取
                     （pubmed_api_key 字段）。
        """
        cfg = get_config()
        # PMC 与 PubMed 同属 NCBI E-utilities，共用同一把 API Key
        self.api_key: str | None = api_key or cfg.resolve_api_key("pmc", "pubmed_api_key")

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

        若配置了 API Key，将其加入参数以提升限流阈值至 10 req/s。
        """
        params: dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    @staticmethod
    def _normalize_pmcid(pmcid: str) -> str:
        """将 PMCID 归一化为 ``PMC<digits>`` 形式。"""
        s = (pmcid or "").strip()
        if not s:
            return ""
        if s.upper().startswith("PMC"):
            return "PMC" + s[3:]
        return f"PMC{s}"

    @classmethod
    def _parse_article(cls, article_el: ET.Element) -> PaperResult:
        """将 JATS ``<article>`` XML 元素转换为 PaperResult。

        Args:
            article_el: JATS ``<article>`` 元素。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败。
        """
        try:
            # ----- 提取 article-id：PMCID / DOI / PMID -----
            pmcid_raw: str = ""
            doi: str | None = None
            pmid: str = ""
            for aid in article_el.iter("article-id"):
                id_type = (aid.get("pub-id-type") or "").lower()
                text = (aid.text or "").strip()
                if not text:
                    continue
                if id_type == "pmc" and not pmcid_raw:
                    pmcid_raw = text
                elif id_type == "doi" and not doi:
                    doi = text
                elif id_type == "pmid" and not pmid:
                    pmid = text

            pmcid = cls._normalize_pmcid(pmcid_raw)
            paper_id = pmcid  # PMC 唯一标识

            # ----- 标题（article-title 可能含子元素，需拼接所有文本）-----
            title_el = article_el.find(".//title-group/article-title")
            if title_el is None:
                title_el = article_el.find(".//article-title")
            title = "".join(title_el.itertext()).strip() if title_el is not None else ""

            # ----- 作者列表（contrib[@contrib-type="author"]）-----
            authors: list[Author] = []
            for contrib in article_el.iter("contrib"):
                if (contrib.get("contrib-type") or "").lower() != "author":
                    continue
                name_el = contrib.find("name")
                if name_el is not None:
                    surname = name_el.findtext("surname", "") or ""
                    given = name_el.findtext("given-names", "") or ""
                    full = f"{given} {surname}".strip()
                else:
                    # 团体作者
                    coll = contrib.find("collab")
                    full = "".join(coll.itertext()).strip() if coll is not None else ""

                # 机构信息（在 contrib 内的 aff，或通过 xref 引用，简化处理只取直接子 aff）
                affiliations: list[str] = []
                for aff in contrib.findall("aff"):
                    aff_text = "".join(aff.itertext()).strip()
                    if aff_text:
                        affiliations.append(aff_text)

                if full:
                    authors.append(
                        Author(
                            name=full,
                            affiliation="; ".join(affiliations) if affiliations else None,
                        )
                    )

            # ----- 摘要（abstract/p，可能多段）-----
            abstract_parts: list[str] = []
            for abs_el in article_el.findall(".//abstract"):
                # 跳过 abstract-type="graphical" 等非主摘要
                abs_type = (abs_el.get("abstract-type") or "").lower()
                if abs_type and abs_type not in ("", "summary", "toc"):
                    continue
                # 优先按段落收集
                paras = abs_el.findall(".//p")
                if paras:
                    for p in paras:
                        text = "".join(p.itertext()).strip()
                        if text:
                            abstract_parts.append(text)
                else:
                    text = "".join(abs_el.itertext()).strip()
                    if text:
                        abstract_parts.append(text)
            abstract = " ".join(abstract_parts)

            # ----- 期刊名（journal-title 优先，fallback abbrev-journal-title）-----
            journal: str | None = None
            jt_el = article_el.find(".//journal-title")
            if jt_el is not None:
                journal = "".join(jt_el.itertext()).strip() or None
            if not journal:
                ajt_el = article_el.find(".//abbrev-journal-title")
                if ajt_el is not None:
                    journal = "".join(ajt_el.itertext()).strip() or None

            # ----- 发表日期（优先 epub，其次 ppub，最后任意 pub-date）-----
            year: int | None = None
            pub_date: str | None = None
            chosen_date_el: ET.Element | None = None
            for pub_type in ("epub", "ppub", "pub", "collection"):
                for d in article_el.iter("pub-date"):
                    dtype = (d.get("pub-type") or d.get("date-type") or "").lower()
                    if dtype == pub_type:
                        chosen_date_el = d
                        break
                if chosen_date_el is not None:
                    break
            if chosen_date_el is None:
                chosen_date_el = article_el.find(".//pub-date")

            if chosen_date_el is not None:
                y = chosen_date_el.findtext("year", "") or ""
                m = chosen_date_el.findtext("month", "01") or "01"
                d = chosen_date_el.findtext("day", "01") or "01"
                if y and y.isdigit():
                    try:
                        year = int(y)
                    except ValueError:
                        year = None
                    m_num = m.zfill(2) if m.isdigit() else "01"
                    d_num = d.zfill(2) if d.isdigit() else "01"
                    pub_date = f"{y}-{m_num}-{d_num}"

            # ----- URL 构建 -----
            if pmcid:
                source_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
                pdf_url: str | None = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
            else:
                source_url = "https://www.ncbi.nlm.nih.gov/pmc/"
                pdf_url = None

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.PMC,
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # PMC efetch 不直接提供引用数
                journal=journal,
                open_access_url=source_url if pmcid else None,
                raw={
                    "pmcid": pmcid or None,
                    "pmid": pmid or None,
                    "paper_id": paper_id or None,
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
        """搜索 PMC 文献（两步: esearch → efetch）。

        Args:
            query: PMC 检索式（与 PubMed 语法兼容，支持 MeSH 等）。
            retmax: 返回条数，上限 10000。
            retstart: 起始偏移量。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        # ---- Step 1: esearch 获取 PMCID 列表 ----
        await self._limiter.acquire()

        search_params = self._common_params()
        search_params.update(
            {
                "db": "pmc",
                "term": query,
                "retmax": str(min(retmax, 10000)),
                "retstart": str(retstart),
                "retmode": "xml",
            }
        )

        search_resp = await self._client.get("/esearch.fcgi", params=search_params)
        try:
            search_root = ET.fromstring(search_resp.text)
        except ET.ParseError as exc:
            raise ParseError(f"PMC esearch XML 解析失败: {exc}") from exc

        # 总数
        count_el = search_root.find("Count")
        try:
            total = int(count_el.text) if count_el is not None and count_el.text else 0
        except ValueError:
            total = 0

        # PMCID 列表（esearch 返回的 Id 为不带 PMC 前缀的纯数字）
        pmcids: list[str] = []
        id_list = search_root.find("IdList")
        if id_list is not None:
            for id_el in id_list.findall("Id"):
                if id_el.text:
                    pmcids.append(id_el.text.strip())

        page = (retstart // retmax) + 1 if retmax > 0 else 1

        if not pmcids:
            return SearchResponse(
                query=query,
                total_results=total,
                page=page,
                per_page=retmax,
                results=[],
                source=SourceType.PMC,
            )

        # ---- Step 2: efetch 获取 JATS XML 详情 ----
        results = await self.fetch(pmcids)

        return SearchResponse(
            query=query,
            total_results=total,
            page=page,
            per_page=retmax,
            results=results,
            source=SourceType.PMC,
        )

    async def fetch(self, pmcids: list[str]) -> list[PaperResult]:
        """根据 PMCID 列表批量获取论文 JATS XML 详情。

        Args:
            pmcids: PMC ID 列表（可带或不带 PMC 前缀，efetch 接受纯数字）。

        Returns:
            PaperResult 列表（解析失败的条目会被跳过并记录日志）。
        """
        if not pmcids:
            return []

        # efetch 接受纯数字 ID（不带 PMC 前缀），逗号分隔
        clean_ids: list[str] = []
        for pid in pmcids:
            s = (pid or "").strip()
            if not s:
                continue
            if s.upper().startswith("PMC"):
                s = s[3:]
            clean_ids.append(s)

        if not clean_ids:
            return []

        await self._limiter.acquire()

        fetch_params = self._common_params()
        fetch_params.update(
            {
                "db": "pmc",
                "id": ",".join(clean_ids),
                "retmode": "xml",
            }
        )

        fetch_resp = await self._client.get("/efetch.fcgi", params=fetch_params)
        try:
            fetch_root = ET.fromstring(fetch_resp.text)
        except ET.ParseError as exc:
            raise ParseError(f"PMC efetch XML 解析失败: {exc}") from exc

        # efetch 顶层为 <pmc-articleset>，内含若干 <article>
        articles: list[ET.Element] = list(fetch_root.iter("article"))
        if not articles and fetch_root.tag == "article":
            articles = [fetch_root]

        results: list[PaperResult] = []
        for article_el in articles:
            try:
                results.append(self._parse_article(article_el))
            except ParseError as exc:
                logger.debug("跳过解析失败的 PMC article: %s", exc)

        return results
